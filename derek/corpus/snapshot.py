"""Maintain the offline Style Manual snapshot (Layer 0, ADR-001).

    python -m derek.corpus.snapshot                 # daily incremental pass
    python -m derek.corpus.snapshot --full          # full re-hash sweep
    python -m derek.corpus.snapshot --sweep-slice N # 1/7th of the corpus (staggered)
    python -m derek.corpus.snapshot --rebuild-lock  # re-derive the lock from disk

Three things Octavius got wrong, fixed here (postmortem F7):

1. **Content hash is the authority.** ``lastmod`` only decides what is worth
   re-fetching. A page edited without a ``lastmod`` bump was invisible to
   Octavius forever; the full sweep catches it here.
2. **Removals are processed.** A URL that leaves the sitemap has its page
   deleted and is recorded in the changeset, so its rules can be orphaned
   rather than staying live indefinitely.
3. **An explicit changeset is emitted** every run, as the input to rule-level
   reconciliation.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from derek.corpus.diff import (
    PageState, Snapshot, diff_snapshots, load_lock, write_changeset, write_lock,
)
from derek.corpus.eligibility import load_eligibility
from derek.corpus.freeze import load_freeze
from derek.corpus.normalise import NormalisedPage
from derek.corpus.to_markdown import ExtractionError, extract_markdown

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
LOCK = REPO / "corpus" / "snapshot.lock.json"
CHANGES = REPO / "corpus" / "changes"
DRIFT = REPO / "corpus" / "drift.json"
HEARTBEAT = REPO / "corpus" / ".heartbeat"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"

DEFAULT_SITEMAP_URL = "https://www.stylemanual.gov.au/sitemap.xml"
SWEEP_SLICES = 7          # a full re-hash spread across a week
EXTRACTOR_ID = "derek.to_markdown/1"


def _display(path: Path) -> str:
    """Repo-relative where possible, absolute otherwise (paths move under test)."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def sweep_slice_of(path: str) -> int:
    """Which of the ``SWEEP_SLICES`` daily slices a page belongs to.

    ``hash()`` was used here, and it is randomised per process by
    ``PYTHONHASHSEED``. The slices were therefore a different random partition
    every day rather than a fixed one, so "every page is re-hashed weekly"
    (ADR-001) was false: over a week the sweep covered roughly two thirds of
    the corpus and which third it missed was never the same twice.

    That is a nuisance while the corpus is being rewritten daily. It stops
    being one the moment the corpus is frozen, because the sweep is then the
    only thing looking for upstream drift at all.
    """
    digest = hashlib.blake2s(path.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % SWEEP_SLICES


def url_to_path(url: str) -> str:
    """Corpus-relative markdown path for a Style Manual URL."""
    path = urlparse(url).path.strip("/") or "index"
    return f"{path}.md"


def _legacy_lastmod() -> dict[str, tuple[str, str | None]]:
    """Recover per-URL ``lastmod`` from the Octavius sitemap state.

    The corpus was carried over from Octavius, which recorded ``lastmod``
    per URL even though it used it wrongly. Seeding the lock with that
    history means the first Derek run only re-fetches genuinely stale pages
    rather than the whole corpus.
    """
    legacy = REPO / "corpus" / "sitemap_state.legacy.json"
    if not legacy.exists():
        return {}
    import json
    out: dict[str, tuple[str, str | None]] = {}
    for url, lastmod in json.loads(legacy.read_text(encoding="utf-8")).items():
        out[url_to_path(url)] = (url, lastmod)
    return out


def scan_disk() -> Snapshot:
    """Build a Snapshot from what is currently on disk.

    Used by ``--rebuild-lock`` to seed the lock file from a corpus carried
    over from Octavius, which had no hashes of normalised content.
    """
    legacy = _legacy_lastmod()
    snap = Snapshot(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        page = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace"))
        url, lastmod = legacy.get(rel, ("", None))
        snap.pages[rel] = PageState(
            url=url, path=rel, sha256=page.sha256,
            lastmod=lastmod, extractor=EXTRACTOR_ID,
        )
    return snap


def _select_for_fetch(entries, lock: Snapshot, full: bool, sweep_slice: int | None):
    """Decide which URLs to re-fetch this run.

    Incremental: anything new, plus anything whose ``lastmod`` advanced.
    Sweep: additionally, the 1/7th of the corpus in today's slice, so every
    page is re-hashed weekly regardless of what the site claims (ADR-001).
    The partition is fixed across processes — see ``sweep_slice_of``.
    """
    selected, reasons = [], {}
    for entry in entries:
        url = entry["loc"]
        path = url_to_path(url)
        prev = lock.pages.get(path)
        if full:
            selected.append(entry); reasons[path] = "full"
        elif prev is None:
            selected.append(entry); reasons[path] = "new"
        elif prev.lastmod != entry.get("lastmod"):
            selected.append(entry); reasons[path] = "lastmod"
        elif sweep_slice is not None and sweep_slice_of(path) == sweep_slice:
            selected.append(entry); reasons[path] = "sweep"
    return selected, reasons


def _write_page(rel: str, text: str, frozen: bool) -> bool:
    """Write one corpus page. A no-op while the corpus is frozen (ADR-024).

    Named, rather than inline, so the freeze guard is a single thing a test can
    watch. Golden-set span offsets are anchored to this text; rewriting it under
    a recorded span is the one failure the freeze exists to prevent.
    """
    if frozen:
        return False
    target = PAGES / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return True


def _remove_page(rel: str, frozen: bool) -> bool:
    """Delete a page that left the sitemap. Also a no-op while frozen.

    Deliberately included: a page vanishing upstream must not delete the local
    file out from under an annotation session. It is reported in drift.json
    instead, and acted on at unfreeze.
    """
    if frozen:
        return False
    target = PAGES / rel
    if not target.exists():
        return False
    target.unlink()
    return True


def _write_drift(current: Snapshot, previous: Snapshot, checked: set[str],
                 freeze) -> dict:
    """Record how far the live site has moved from the frozen corpus.

    Cumulative and timestamp-free, both on purpose. Cumulative because one run
    only re-hashes the pages in today's sweep slice, so an overwritten
    report would forget yesterday's finding; timestamp-free because an
    unchanged report then produces a byte-identical file and no daily commit —
    ``git log -- corpus/drift.json`` becomes the drift timeline, with no noise
    between real entries.
    """
    import json

    existing = {}
    if DRIFT.exists():
        for row in json.loads(DRIFT.read_text(encoding="utf-8")).get("drifted", []):
            existing[row["path"]] = row

    for rel in sorted(checked):
        live = current.pages.get(rel)
        frozen_state = previous.pages.get(rel)
        if live is None:
            continue
        if frozen_state is None:
            existing[rel] = {"path": rel, "url": live.url, "state": "added",
                             "frozen_sha256": "", "live_sha256": live.sha256}
        elif live.sha256 != frozen_state.sha256:
            existing[rel] = {"path": rel, "url": live.url, "state": "altered",
                             "frozen_sha256": frozen_state.sha256,
                             "live_sha256": live.sha256}
        else:
            existing.pop(rel, None)          # drifted back, or never had

    for rel in sorted(set(previous.pages) - set(current.pages)):
        existing[rel] = {"path": rel, "url": previous.pages[rel].url,
                         "state": "removed",
                         "frozen_sha256": previous.pages[rel].sha256,
                         "live_sha256": ""}

    report = {
        "_meta": {
            "note": ("How far stylemanual.gov.au has moved from the frozen "
                     "corpus. Cumulative across runs and carries no timestamp, "
                     "so an unchanged report is a byte-identical file. See "
                     "corpus/freeze.yaml and ADR-024."),
            "frozen_at": freeze.frozen_at,
            "lock_digest": freeze.lock_digest,
        },
        "drifted": [existing[k] for k in sorted(existing)],
    }
    DRIFT.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def run(full: bool, sweep_slice: int | None, sitemap_url: str, dry_run: bool) -> int:
    # Imported lazily: the transport needs selenium, which the rest of the
    # corpus layer deliberately does not.
    from derek.corpus import fetch as transport

    eligibility = load_eligibility(ELIGIBILITY)
    previous = load_lock(LOCK)
    freeze = load_freeze()
    print(freeze.banner())

    driver = transport.initialize_driver()
    if driver is None:
        print("FATAL: could not initialise WebDriver", file=sys.stderr)
        return 2

    try:
        base = f"{urlparse(sitemap_url).scheme}://{urlparse(sitemap_url).netloc}"
        if not transport.check_robots_txt(base, driver):
            print("FATAL: robots.txt disallows crawling", file=sys.stderr)
            return 2

        body = transport.fetch_sitemap_with_retry(sitemap_url, driver)
        if body is None:
            print("FATAL: could not fetch sitemap", file=sys.stderr)
            return 2

        entries = transport.parse_sitemap(body, sitemap_url, driver)
        if not entries:
            print("FATAL: sitemap parsed but yielded 0 URLs", file=sys.stderr)
            return 2
        print(f"sitemap: {len(entries)} URLs")

        to_fetch, reasons = _select_for_fetch(entries, previous, full, sweep_slice)
        print(f"fetching {len(to_fetch)} page(s): "
              f"{ {r: list(reasons.values()).count(r) for r in set(reasons.values())} }")
        if dry_run:
            return 0

        current = Snapshot(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        failed: list[str] = []
        # Paths we tried and could not read. A failed fetch teaches us nothing,
        # so it must not count as "checked and clean" and clear a drift entry
        # recorded on an earlier run.
        unread: set[str] = set()

        # Carry forward pages we did not re-fetch this run.
        sitemap_paths = {url_to_path(e["loc"]) for e in entries}
        for path, state in previous.pages.items():
            if path in sitemap_paths and path not in reasons:
                current.pages[path] = state

        for i, entry in enumerate(to_fetch, 1):
            url = entry["loc"]
            rel = url_to_path(url)
            print(f"[{i}/{len(to_fetch)}] {url}")

            html = transport.fetch_with_retry(url, driver)
            if html is None:
                failed.append(url)
                unread.add(rel)
                if (prev := previous.pages.get(rel)):
                    current.pages[rel] = prev      # never drop a page on a fetch failure
                continue

            # DOM-faithful conversion: heading levels come from the source
            # <h1>-<h6> tags rather than being inferred (ADR-020). Raises
            # rather than returning empty, so a blocked or broken fetch can
            # never be written to the corpus as a legitimately empty page.
            try:
                markdown = extract_markdown(html, url)
            except ExtractionError as exc:
                print(f"    extraction failed: {exc}", file=sys.stderr)
                failed.append(url)
                unread.add(rel)
                if (prev := previous.pages.get(rel)):
                    current.pages[rel] = prev
                continue

            page = NormalisedPage(rel, markdown)
            _write_page(rel, page.text, freeze.frozen)

            current.pages[rel] = PageState(
                url=url, path=rel, sha256=page.sha256,
                lastmod=entry.get("lastmod"),
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                extractor=EXTRACTOR_ID,
            )
            if i < len(to_fetch):
                time.sleep(random.uniform(2, 4))
    finally:
        driver.quit()

    # Removals: a page in the lock but no longer in the sitemap is gone.
    for path in sorted(set(previous.pages) - set(current.pages)):
        if _remove_page(path, freeze.frozen):
            print(f"removed upstream: {path}")
        elif freeze.frozen:
            print(f"removed upstream (frozen, kept on disk): {path}")

    # The heartbeat is refreshed either way. The CI freshness gate asks whether
    # the crawler is alive, not whether the corpus is current, and the 60-day
    # scheduled-workflow-disable trap it guards does not care that we are frozen
    # (ADR-001).
    HEARTBEAT.write_text(
        datetime.now(timezone.utc).isoformat(timespec="seconds") + "\n", encoding="utf-8"
    )

    if freeze.frozen:
        # Nothing is applied: the lock still describes the frozen corpus, and no
        # changeset is written because nothing changed on disk to reconcile.
        checked = set(reasons) - unread
        report = _write_drift(current, previous, checked, freeze)
        n = len(report["drifted"])
        print(f"\nfrozen: read {len(checked)} of {len(reasons)} page(s); "
              f"{n} page(s) now differ from the frozen corpus.")
        if n:
            print(f"see {_display(DRIFT)}; unfreezing is ADR-024's runbook.")
        return 0

    changeset = diff_snapshots(previous, current)
    write_lock(LOCK, current)

    print("\nchangeset:", changeset.summary(), f"({changeset.kind})")
    if not changeset.empty:
        out = write_changeset(CHANGES, changeset)
        print(f"wrote {_display(out)}")

    if changeset.removed or changeset.altered:
        print("\nRules derived from these pages need reconciliation:")
        print("  python -m derek.extract.build")

    ineligible = [p for p in changeset.added if not eligibility.decide(p)[0]]
    if ineligible:
        print(f"\n{len(ineligible)} new page(s) are unclassified and excluded from "
              f"extraction until triaged in corpus/eligibility.yaml (ADR-005):")
        for p in ineligible[:10]:
            print(f"  {p}")

    if failed:
        print(f"\nWARNING: {len(failed)} page(s) failed to fetch; their previous "
              f"content was retained:", file=sys.stderr)
        for u in failed[:10]:
            print(f"  {u}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true", help="re-fetch and re-hash every page")
    ap.add_argument("--sweep-slice", type=int, default=None,
                    help=f"also re-hash 1/{SWEEP_SLICES} of the corpus (0-{SWEEP_SLICES - 1})")
    ap.add_argument("--sitemap", default=DEFAULT_SITEMAP_URL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild-lock", action="store_true",
                    help="re-derive the lock file from the corpus on disk, no network")
    args = ap.parse_args(argv)

    if args.rebuild_lock:
        freeze = load_freeze()
        if freeze.frozen:
            # Safe while frozen: it re-derives the lock from a corpus nothing is
            # rewriting, so it can only be a no-op or a repair.
            print(freeze.banner())
        snap = scan_disk()
        cs = diff_snapshots(load_lock(LOCK), snap)
        write_lock(LOCK, snap)
        print(f"rebuilt lock from disk: {len(snap.pages)} pages")
        print("changeset:", cs.summary(), f"({cs.kind})")
        return 0

    return run(args.full, args.sweep_slice, args.sitemap, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
