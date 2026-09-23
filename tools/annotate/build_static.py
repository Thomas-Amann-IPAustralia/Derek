#!/usr/bin/env python3
"""Build the span annotator as a static site — ADR-022, ADR-023.

    python tools/annotate/build_static.py                 # → site/annotate/
    python tools/annotate/build_static.py --out _site/annotate

The annotator reconstructs the Style Manual from the frozen corpus and lets a
human mark the spans of text that state each rule. It is published because the
person doing that work has a browser and nothing else, which is the same reason
the triage dashboard is published (ADR-022) — and here it matters more, because
this is now the main way rules are identified at all.

**Static only.** There is no `tools/annotate/server.py`. The triage app has a
local server because it predates its published copy; the annotator does not need
one, and not having one means there is exactly one writer
(`tools/annotate/apply_spans.py`) and exactly one gate. Spans are queued in
`localStorage`, exported as JSONL, and replayed into `golden/spans.jsonl` and
then the ledger.

**No HTML is shipped for page content.** Each page arrives as the blocks
`derek.extract.blocks` produces — `plain` text plus inline `marks` as offsets
into it — and the browser builds the DOM by slicing `plain` at mark boundaries.
That makes `element.textContent == block.plain` true by construction, which is
what lets a selection be mapped back to an offset Python can resolve.

Stdlib only, and it imports `tools/review/server.py` rather than restating the
reviewer vocabulary, so the annotator's option chips cannot drift from the triage
app's. The glossary drift check runs here too, so an unexplained option fails the
Pages build.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
REVIEW = REPO / "tools" / "review"

sys.path.insert(0, str(REPO))

from derek.corpus.eligibility import load_eligibility            # noqa: E402
from derek.corpus.freeze import load_freeze                      # noqa: E402
from derek.corpus.normalise import NormalisedPage                # noqa: E402
from derek.extract.blocks import RENDER_VERSION, parse_blocks    # noqa: E402

PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
LOCK = REPO / "corpus" / "snapshot.lock.json"
DRAFT_TOOL = REPO / "tools" / "draft"
GOLDEN_SPANS = REPO / "golden" / "spans.jsonl"
GOLDEN_PAGES = REPO / "golden" / "pages.jsonl"

BACKEND_MARKER = 'window.DEREK_BACKEND = "server";'


def _load_server():
    """Import tools/review/server.py, which is not on a package path."""
    spec = importlib.util.spec_from_file_location(
        "derek_review_server", REVIEW / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _commit() -> str:
    if sha := os.environ.get("GITHUB_SHA"):
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _page() -> str:
    """index.html with its backend marker flipped, as ADR-022 does for triage."""
    html = (HERE / "index.html").read_text(encoding="utf-8")
    if html.count(BACKEND_MARKER) != 1:
        raise SystemExit(
            f"tools/annotate/index.html no longer contains exactly one "
            f"{BACKEND_MARKER!r} — the static build cannot mark itself."
        )
    return html.replace(BACKEND_MARKER, 'window.DEREK_BACKEND = "static";')


def _write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(body, encoding="utf-8")
    return len(body.encode("utf-8"))


def _url_index() -> dict[str, str]:
    if not LOCK.exists():
        return {}
    pages = json.loads(LOCK.read_text(encoding="utf-8")).get("pages", {})
    return {rel: state.get("url", "") for rel, state in pages.items()}


def _slug(rel: str) -> str:
    """Published filename for a page payload.

    Mirrors the corpus path so the tree is browsable and a page's payload is
    findable from its path alone, with `/` kept as directory structure.
    """
    return rel[:-3] if rel.endswith(".md") else rel


def _seeds_for(rel: str, blocks, rules) -> list[dict]:
    """The heading-derived candidates on this page, mapped to their blocks.

    These are the first cut: 736 rules the heading walk proposed. The annotator
    shows them as unconfirmed highlights so a reviewer can accept one with a
    keystroke, adjust its extent, or delete it — rather than re-selecting text
    the extractor already found (ADR-023).

    A candidate is matched to its heading block by source line, which is exact:
    `Source.line_start` and `Block.line` are both the 0-based index of the
    heading line, and both come from `segment.parse_page`.

    Rules derived from a golden span are NOT seeds. A seed is the extractor's
    unconfirmed guess, and a span is the answer to it — the page already ships
    those in `data/spans.json` and draws them as span highlights. Listing them
    here too would show a reviewer their own work back as something still to do,
    and a span drawn on body prose has no heading block to be listed against at
    all, so it would arrive unplaceable.
    """
    by_line = {b.line: b for b in blocks if b.kind == "heading"}
    out = []
    for rule in rules.values():
        if rule.source.page_path != rel:
            continue
        if rule.derivation.method == "human_span":
            continue
        block = by_line.get(rule.source.line_start)
        out.append({
            "uid": rule.uid,
            "block_id": block.id if block else "",
            "line": rule.source.line_start,
            "statement": rule.source.statement,
            "status": rule.review.status,
            "form": rule.derivation.statement_form,
            "modality": rule.modality,
            "unit": rule.unit,
            "clarity": rule.clarity,
            "direction": rule.direction,
            "applies_to": list(rule.applies_to),
            "specification": rule.specification,
            "violation_condition": rule.violation_condition,
            "note": rule.review.note,
            "compliant": list(rule.compliant_examples),
            "violating": list(rule.violating_examples),
        })
    out.sort(key=lambda s: (s["line"], s["uid"]))
    return out


def _drafting():
    """tools/draft/drafting.py, which is stdlib and not on a package path."""
    spec = importlib.util.spec_from_file_location("derek_drafting", DRAFT_TOOL / "drafting.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _draft_payload(rec: dict | None, blind: bool) -> dict | None:
    """What the annotator shows of one page's model draft (ADR-025).

    Nothing, on a blind page: a draft in view shapes what the reviewer marks,
    and the blind pages are what drafts are measured against. The raw model
    output stays in the repository; only the resolved pointers ship.
    """
    if rec is None or blind:
        return None
    return {
        "prompt_version": rec["prompt_version"], "model": rec["model"],
        "served_model": rec.get("served_model", ""),
        "rules": rec.get("rules", []), "not_rules": rec.get("not_rules", []),
        "refused": len(rec.get("refused", [])),
    }


def _read_golden() -> tuple[list[dict], list[dict]]:
    """The committed golden set, as the published baseline local ops replay over."""
    def rows(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    return rows(GOLDEN_SPANS), rows(GOLDEN_PAGES)


def build(out: Path, *, server=None, clean: bool = True) -> dict:
    """Write the annotator to `out` and return its manifest."""
    server = server or _load_server()

    if not server.LEDGER.exists():
        raise SystemExit(
            f"No ledger at {server.LEDGER}. Run: python -m derek.extract.build"
        )

    glossary = server.load_glossary()      # raises if it has drifted from the code
    rules = server.load_ledger(server.LEDGER)
    eligibility = load_eligibility(ELIGIBILITY)
    freeze = load_freeze()
    urls = _url_index()
    drafting = _drafting()
    drafts = drafting.load_drafts()
    blind = drafting.load_blind()

    build_info = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "render_version": RENDER_VERSION,
        "repo": os.environ.get("GITHUB_REPOSITORY", "Thomas-Amann-IPAustralia/Derek"),
    }

    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    index_pages: list[dict] = []
    sizes: dict[str, int] = {}
    total_blocks = 0

    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        eligible, reason = eligibility.decide(rel)
        page = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace"))
        blocks = parse_blocks(rel, page.text)
        if not blocks:
            continue
        seeds = _seeds_for(rel, blocks, rules) if eligible else []
        draft = _draft_payload(drafts.get(rel), rel in blind) if eligible else None
        title = next((b.plain for b in blocks if b.kind == "heading" and b.level == 1), rel)
        total_blocks += len(blocks)

        payload = {
            "path": rel,
            "title": title,
            "url": urls.get(rel, ""),
            "sha256": page.sha256,
            "eligible": eligible,
            "eligibility_reason": reason,
            "blocks": [b.to_dict() for b in blocks],
            "seeds": seeds,
            "drafts": draft,
            "blind": rel in blind,
        }
        name = f"data/pages/{_slug(rel)}.json"
        sizes[name] = _write_json(out / name, payload)

        index_pages.append({
            "path": rel,
            "slug": _slug(rel),
            "title": title,
            "section": rel.split("/")[0],
            "eligible": eligible,
            "eligibility_reason": reason,
            "blocks": len(blocks),
            "seeds": len(seeds),
            "drafted": len(draft["rules"]) if draft else 0,
            "blind": rel in blind,
            "sha256": page.sha256,
        })

    spans, page_marks = _read_golden()

    # The golden-set lint, as of this build. Shipped so the reviewer sees each
    # finding on the page where it is fixed, rather than in a report they would
    # need Python to produce. It goes stale as they work, and says so.
    from derek.eval.golden_lint import by_page, lint
    findings = by_page(lint(server.LEDGER))

    index = {
        "static": True,
        "build": build_info,
        "freeze": {
            "frozen": freeze.frozen,
            "frozen_at": freeze.frozen_at,
            "reason": freeze.reason,
            "banner": freeze.banner(),
        },
        "glossary": glossary,
        "options": server.reviewer_options(glossary),
        "span_kinds": ["rule", "compliant", "violating", "precondition"],
        "pages": index_pages,
        "totals": {
            "pages": len(index_pages),
            "eligible": sum(1 for p in index_pages if p["eligible"]),
            "blocks": total_blocks,
            "seeds": sum(p["seeds"] for p in index_pages),
            "spans": len(spans),
            "drafted_pages": sum(1 for p in index_pages if p["drafted"]),
        },
    }

    (out / "index.html").write_text(_page(), encoding="utf-8")
    # Pages runs Jekyll over an uploaded tree unless told not to, and a `data/`
    # directory of JSON is exactly what it would try to interpret.
    (out / ".nojekyll").write_text("", encoding="utf-8")

    sizes["index.html"] = (out / "index.html").stat().st_size
    sizes["data/index.json"] = _write_json(out / "data" / "index.json", index)
    sizes["data/spans.json"] = _write_json(
        out / "data" / "spans.json",
        {"build": build_info, "spans": spans, "pages": page_marks},
    )
    sizes["data/lint.json"] = _write_json(
        out / "data" / "lint.json", {"build": build_info, "pages": findings})

    manifest = {
        **build_info,
        "totals": index["totals"],
        "bytes": {k: sizes[k] for k in ("index.html", "data/index.json", "data/spans.json")},
        "page_payload_bytes": sum(v for k, v in sizes.items() if k.startswith("data/pages/")),
    }
    sizes["data/manifest.json"] = _write_json(out / "data" / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "site" / "annotate",
                    help="directory to write into (default: site/annotate/)")
    ap.add_argument("--no-clean", action="store_true",
                    help="keep anything already in --out")
    args = ap.parse_args(argv)

    manifest = build(args.out.resolve(), clean=not args.no_clean)
    t = manifest["totals"]
    shell = sum(manifest["bytes"].values())
    print(f"Built {args.out}: {t['eligible']} of {t['pages']} pages eligible, "
          f"{t['blocks']} blocks, {t['seeds']} seeded candidates, "
          f"{t['spans']} golden spans")
    print(f"  shell {shell / 1024:.0f} KB + {manifest['page_payload_bytes'] / 1024:.0f} KB "
          f"of page payloads, fetched one page at a time")
    print(f"  render {manifest['render_version']}, commit {manifest['commit'] or 'unknown'}")
    print("\nSpans marked there are exported and replayed with:"
          "\n  python tools/annotate/apply_spans.py <export.jsonl>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
