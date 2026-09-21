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
from derek.corpus.normalise import NormalisedPage
from derek.corpus.to_markdown import ExtractionError, extract_markdown

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
LOCK = REPO / "corpus" / "snapshot.lock.json"
CHANGES = REPO / "corpus" / "changes"
HEARTBEAT = REPO / "corpus" / ".heartbeat"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"

DEFAULT_SITEMAP_URL = "https://www.stylemanual.gov.au/sitemap.xml"
SWEEP_SLICES = 7          # a full re-hash spread across a week
EXTRACTOR_ID = "derek.to_markdown/1"


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
    Sweep: additionally, a deterministic 1/7th of the corpus, so every page
    is re-hashed weekly regardless of what the site claims (ADR-001).
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
        elif sweep_slice is not None and hash(path) % SWEEP_SLICES == sweep_slice:
            selected.append(entry); reasons[path] = "sweep"
    return selected, reasons


def run(full: bool, sweep_slice: int | None, sitemap_url: str, dry_run: bool) -> int:
    # Imported lazily: the transport needs selenium, which the rest of the
    # corpus layer deliberately does not.
    from derek.corpus import fetch as transport

    eligibility = load_eligibility(ELIGIBILITY)
    previous = load_lock(LOCK)

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
                if (prev := previous.pages.get(rel)):
                    current.pages[rel] = prev
                continue

            page = NormalisedPage(rel, markdown)
            target = PAGES / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page.text, encoding="utf-8")

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
        target = PAGES / path
        if target.exists():
            target.unlink()
            print(f"removed upstream: {path}")

    changeset = diff_snapshots(previous, current)
    write_lock(LOCK, current)
    HEARTBEAT.write_text(
        datetime.now(timezone.utc).isoformat(timespec="seconds") + "\n", encoding="utf-8"
    )

    print("\nchangeset:", changeset.summary(), f"({changeset.kind})")
    if not changeset.empty:
        out = write_changeset(CHANGES, changeset)
        print(f"wrote {out.relative_to(REPO)}")

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
        snap = scan_disk()
        cs = diff_snapshots(load_lock(LOCK), snap)
        write_lock(LOCK, snap)
        print(f"rebuilt lock from disk: {len(snap.pages)} pages")
        print("changeset:", cs.summary(), f"({cs.kind})")
        return 0

    return run(args.full, args.sweep_slice, args.sitemap, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
