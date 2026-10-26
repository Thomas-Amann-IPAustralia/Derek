#!/usr/bin/env python3
"""Build the rule inspector as a static site.

    python tools/inspect/build_static.py                  # → site/inspect/
    python tools/inspect/build_static.py --out _site/inspect

One rule at a time: everything the repository knows about it on the left, and
the page it came from on the right, reconstructed from the frozen corpus with
the text that states the rule highlighted where it sits. The triage deck shows a
rule without its page and the annotator shows a page without one rule's whole
story; checking that a rule is fit for purpose needs both at once, because most
of what goes wrong with a rule is visible only in its context — a span cut from
the middle of a qualified sentence, an example that belongs to the paragraph
above, a heading that was a label rather than an instruction (docs/07).

**Read-only.** It writes nothing, queues nothing and exports nothing. Changing a
rule is still done in the annotator or the triage app, through their single
gate (ADR-022, ADR-023); this is where a reviewer decides whether to.

**Python places every highlight; the browser only draws it.** Which span a rule
came from is not stored on the rule — it is whatever span ``golden_rules``
turns into that rule's uid on every rebuild. So the build asks the same function
the extractor uses, rather than letting the page guess by matching text, and
records *how* each highlight was placed so the page can say how far to trust it:

``golden_span``  The span in ``golden/spans.jsonl`` that mints this uid. Exact.
``heading``      The heading block at the rule's source line, for a rule the
                 heading walk derived (ADR-002). Exact.
``statement``    The rule's statement, found in the block at its source line.
                 For a span-derived rule whose span has since been removed from
                 the golden set (it is orphaned), so no span mints its uid now.
``unplaced``     Not found. Said on the page rather than drawn somewhere wrong.

Stdlib only, like the other two builders: pages.yml runs it with no install.
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
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent

sys.path.insert(0, str(REPO))

from derek.corpus.eligibility import load_eligibility            # noqa: E402
from derek.corpus.freeze import load_freeze                      # noqa: E402
from derek.corpus.normalise import NormalisedPage                # noqa: E402
from derek.extract.blocks import RENDER_VERSION, Block, parse_blocks  # noqa: E402
from derek.extract.candidates import normalise_statement         # noqa: E402
from derek.extract.golden import (                               # noqa: E402
    RULE, GoldenError, Span, golden_rules, load_golden, resolve_span,
)
from derek.ledger.model import Rule                              # noqa: E402
from derek.ledger.store import load_ledger                       # noqa: E402

PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
LOCK = REPO / "corpus" / "snapshot.lock.json"
LEDGER = REPO / "ledger" / "rules.jsonl"
PROPOSALS = REPO / "ledger" / "proposals"
GLOSSARY = REPO / "tools" / "review" / "glossary.json"
DRAFT_TOOL = REPO / "tools" / "draft"
SAMPLE = REPO / "golden" / "consensus" / "sample.json"
GOLDEN_PAGES = REPO / "golden" / "pages.jsonl"

GOLDEN_SPAN, HEADING, STATEMENT, UNPLACED = "golden_span", "heading", "statement", "unplaced"


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


def _write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(body, encoding="utf-8")
    return len(body.encode("utf-8"))


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _slug(rel: str) -> str:
    """The annotator's payload naming, so a page has one name across both apps."""
    return rel[:-3] if rel.endswith(".md") else rel


def _url_index() -> dict[str, str]:
    if not LOCK.exists():
        return {}
    pages = json.loads(LOCK.read_text(encoding="utf-8")).get("pages", {})
    return {rel: state.get("url", "") for rel, state in pages.items()}


def _consensus():
    """tools/draft/consensus.py, for ``item_id`` and its file locations.

    Imported rather than restated: an adjudication is linked to a rule by the id
    consensus.py minted for it, and a second copy of that hash is a second place
    for it to drift. Loaded by path, as the annotator loads drafting.py; it
    inserts its own directory on sys.path for its siblings.
    """
    spec = importlib.util.spec_from_file_location(
        "derek_inspect_consensus", DRAFT_TOOL / "consensus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Finding text on the page
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _normalised(plain: str) -> tuple[str, tuple[int, ...]]:
    """``plain`` in ``normalise_statement``'s canonical form, with an index map.

    A statement is stored normalised (curly quotes straightened, whitespace
    collapsed) while a block keeps the manual's characters, so the two are
    compared in the canonical form and the hit is mapped back to offsets in
    ``plain``. Each character goes through ``normalise_statement`` itself, so
    the canonical form is that function's and not a copy of it.
    """
    out: list[str] = []
    index: list[int] = []
    gap = False
    for i, ch in enumerate(plain):
        if ch.isspace():
            if not gap:
                out.append(" ")
                index.append(i)
            gap = True
            continue
        gap = False
        for c in normalise_statement(ch) or ch:
            out.append(c)
            index.append(i)
    return "".join(out), tuple(index)


def _find(needle: str, block: Block) -> tuple[int, int] | None:
    want = normalise_statement(needle)
    if not want:
        return None
    hay, index = _normalised(block.plain)
    at = hay.find(want)
    if at < 0:
        return None
    return index[at], index[at + len(want) - 1] + 1


@lru_cache(maxsize=None)
def _unmarked(text: str) -> str:
    """``text`` as the block projection would show it, Markdown removed.

    An example harvested from a ``Write this`` block keeps its source markup
    (``*Theoretical Studies*``), which the page's plain text does not have. The
    projection itself does the stripping, so this agrees with what is drawn.
    """
    return " ".join(b.plain for b in parse_blocks("", text))


def _within(blocks: list[Block], prefix: tuple[str, ...]) -> list[Block]:
    return [b for b in blocks if b.heading_path[:len(prefix)] == prefix]


def _locate_text(text: str, blocks: list[Block], section: tuple[str, ...]) -> list[dict]:
    """Where a string the ledger holds sits on the page, or [] if it does not.

    For examples and conditions that no span records. A string the manual
    split across blocks (a list lead-in and its items) was joined with newlines
    when it was harvested, so each line is looked for on its own; all of them
    have to be found or none is shown. The rule's own section is searched
    first, because the same sentence can appear under two headings.
    """
    parts = [p for p in text.split("\n") if p.strip()]
    if not parts:
        return []
    scope = _within(blocks, section) if section else []
    found = []
    for part in parts:
        hit = None
        for needle in dict.fromkeys((part, _unmarked(part))):
            for b in scope + blocks:
                loc = _find(needle, b)
                if loc:
                    hit = {"block_id": b.id, "start": loc[0], "end": loc[1]}
                    break
            if hit:
                break
        if hit is None:
            return []
        found.append(hit)
    return found


# ---------------------------------------------------------------------------
# One rule's origin
# ---------------------------------------------------------------------------

def _anchor(block: Block, start: int, end: int) -> dict:
    return {"block_id": block.id, "start": start, "end": end,
            "quote": block.plain[start:end]}


def _kid_examples(kids) -> list[dict]:
    """A rule's example spans, joined into examples the way golden.py joins them."""
    out: list[dict] = []
    grouped: dict[str, dict] = {}
    for k in kids:
        if k.span.kind not in ("compliant", "violating"):
            continue
        part = {"block_id": k.block.id, "start": k.span.start, "end": k.span.end}
        if k.span.group:
            g = grouped.get(k.span.group)
            if g is None:
                g = grouped[k.span.group] = {"polarity": k.span.kind, "texts": [], "parts": []}
                out.append(g)
            g["texts"].append(k.text)
            g["parts"].append(part)
        else:
            out.append({"polarity": k.span.kind, "texts": [k.text], "parts": [part]})
    return [{"polarity": e["polarity"], "text": "\n".join(e["texts"]), "parts": e["parts"]}
            for e in out]


def _match(text: str, pool: list[dict], taken: set[int]) -> dict | None:
    """The span-backed entry a ledger string came from.

    Exact text first, then canonical form, and an entry not yet claimed before
    one that is: the ledger can list the same example twice, and two spans can
    differ only in a thin space against a narrow one.
    """
    free = [e for e in pool if id(e) not in taken]
    want = normalise_statement(text)
    for entries in (free, pool):
        for same in (lambda e: e["text"] == text,
                     lambda e: normalise_statement(e["text"]) == want):
            for e in entries:
                if same(e):
                    taken.add(id(e))
                    return e
    return None


def _origin(rule: Rule, blocks: list[Block], by_line: dict[int, list[Block]],
            pair: tuple[Span, object] | None, resolved: dict, kids_of: dict) -> dict:
    """Where on its page a rule came from, and how sure the placement is."""
    src = rule.source
    span_record = None
    kids = []
    how, anchor, rebased = UNPLACED, None, False

    if pair is not None:
        span = pair[0]
        r = resolved[span.span_id]
        how = GOLDEN_SPAN
        anchor = _anchor(r.block, r.span.start, r.span.end)
        rebased = r.rebased
        span_record = span.to_dict()
        kids = kids_of.get(span.span_id, [])
    else:
        here = by_line.get(src.line_start, [])
        heading = next((b for b in here if b.kind == "heading"), None)
        if rule.derivation.method == "heading_structure" and heading is not None:
            how, anchor = HEADING, _anchor(heading, 0, len(heading.plain))
        else:
            for b in here + blocks:
                loc = _find(src.statement, b)
                if loc:
                    how, anchor = STATEMENT, _anchor(b, *loc)
                    break

    block = next((b for b in blocks if anchor and b.id == anchor["block_id"]), None)
    section = tuple(block.heading_path) if block else tuple(src.heading_path)

    # Examples: the ledger's strings, each tied to the page text it came from.
    from_spans = _kid_examples(kids)
    examples = []
    claimed: set[int] = set()
    for polarity, strings in (("compliant", rule.compliant_examples),
                              ("violating", rule.violating_examples)):
        pool = [e for e in from_spans if e["polarity"] == polarity]
        for text in strings:
            hit = _match(text, pool, claimed)
            if hit is not None:
                examples.append({"polarity": polarity, "text": text, "how": "span",
                                 "parts": hit["parts"]})
                continue
            parts = _locate_text(text, blocks, section)
            examples.append({"polarity": polarity, "text": text,
                             "how": "text" if parts else "none", "parts": parts})
    # An example span the ledger no longer carries is still part of the record.
    for e in from_spans:
        if id(e) not in claimed:
            examples.append({"polarity": e["polarity"], "text": e["text"],
                             "how": "span_only", "parts": e["parts"]})

    conds = [{"text": k.text, "parts": [{"block_id": k.block.id, "start": k.span.start,
                                         "end": k.span.end}]}
             for k in kids if k.span.kind == "precondition"]
    preconditions = []
    used: set[int] = set()
    for text in rule.context_preconditions:
        hit = _match(text, conds, used)
        if hit is not None:
            preconditions.append({"text": text, "how": "span", "parts": hit["parts"]})
            continue
        parts = _locate_text(text, blocks, section)
        preconditions.append({"text": text, "how": "text" if parts else "typed",
                              "parts": parts})

    return {
        "how": how,
        "anchor": anchor,
        "rebased": rebased,
        "section": list(section),
        "span": span_record,
        "examples": examples,
        "preconditions": preconditions,
    }


# ---------------------------------------------------------------------------
# Everything else the repository records about a rule
# ---------------------------------------------------------------------------

def _consensus_index(consensus) -> tuple[dict, dict]:
    """Queue items by the rule id they discuss, and by heading-candidate uid."""
    by_rid: dict[tuple[str, str], list[dict]] = {}
    by_uid: dict[str, list[dict]] = {}
    for item in _rows(consensus.QUEUE):
        if item.get("rid"):
            by_rid.setdefault((item["page_path"], item["rid"]), []).append(item)
        if item.get("uid"):
            by_uid.setdefault(item["uid"], []).append(item)
    return by_rid, by_uid


def _consensus_for(rule: Rule, span: dict | None, consensus, by_rid, by_uid,
                   adjudications) -> list[dict]:
    items = list(by_uid.get(rule.uid, []))
    if span is not None:
        a = span["anchor"]
        rid = consensus.item_id(rule.source.page_path, "rule",
                                a["block_id"], a["start"], a["end"])
        items = by_rid.get((rule.source.page_path, rid), []) + items
    out = []
    for item in items:
        out.append({"item": item, "decision": adjudications.get(item["item_id"])})
    return out


def _proposals() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if PROPOSALS.exists():
        for path in sorted(PROPOSALS.glob("*.jsonl")):
            for row in _rows(path):
                if row.get("uid"):
                    out.setdefault(row["uid"], []).append(
                        {**row, "file": str(path.relative_to(REPO))})
    return out


def _sampled() -> dict:
    if not SAMPLE.exists():
        return {"uids": set(), "seed": "", "population": 0}
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return {"uids": {r["uid"] for r in raw.get("rules", [])},
            "seed": raw.get("seed", ""), "population": raw.get("population", 0)}


def _summary(rule: Rule, page_index: int, how: str) -> dict:
    """The row the rule list and the search need, and nothing heavier."""
    return {
        "uid": rule.uid,
        "statement": rule.source.statement,
        "page": page_index,
        "heading": " › ".join(rule.source.heading_path[1:]),
        "line": rule.source.line_start,
        "status": rule.review.status,
        "method": rule.derivation.method,
        "modality": rule.modality,
        "unit": rule.unit,
        "how": how,
    }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def build(out: Path, *, clean: bool = True) -> dict:
    """Write the inspector to `out` and return its manifest."""
    if not LEDGER.exists():
        raise SystemExit(f"No ledger at {LEDGER}. Run: python -m derek.extract.build")

    rules = load_ledger(LEDGER)
    eligibility = load_eligibility(ELIGIBILITY)
    golden = load_golden(eligibility=eligibility)
    freeze = load_freeze()
    urls = _url_index()
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    consensus = _consensus()
    by_rid, by_uid = _consensus_index(consensus)
    adjudications = consensus.load_adjudications()
    proposals = _proposals()
    sampled = _sampled()
    sweeps = {row["page_path"]: row for row in _rows(GOLDEN_PAGES)}

    from derek.eval.golden_lint import lint
    findings: dict[str, list[dict]] = {}
    for f in lint(LEDGER):
        if f.rule_uid:
            findings.setdefault(f.rule_uid, []).append(
                {"level": f.level, "code": f.code, "ref": f.ref, "message": f.message})

    build_info = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "render_version": RENDER_VERSION,
        "repo": os.environ.get("GITHUB_REPOSITORY", "Thomas-Amann-IPAustralia/Derek"),
    }

    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    on_page: dict[str, list[Rule]] = {}
    for rule in rules.values():
        on_page.setdefault(rule.source.page_path, []).append(rule)

    index_pages: list[dict] = []
    index_rules: list[dict] = []
    sizes: dict[str, int] = {}
    hows: dict[str, int] = {}

    for rel in sorted(on_page):
        page_rules = sorted(on_page[rel], key=lambda r: (r.source.line_start, r.uid))
        md = PAGES / rel
        eligible, reason = eligibility.decide(rel)
        page_no = len(index_pages)

        if not md.exists():
            # A page the corpus no longer has (ADR-001). The rules are still in the
            # ledger and still worth reading; there is just no text to show them in.
            index_pages.append({"path": rel, "slug": "", "title": rel,
                                "section": rel.split("/")[0], "rules": len(page_rules),
                                "eligible": eligible, "missing": True})
            for rule in page_rules:
                index_rules.append(_summary(rule, page_no, UNPLACED))
                hows[UNPLACED] = hows.get(UNPLACED, 0) + 1
            continue

        page = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace"))
        blocks = parse_blocks(rel, page.text)
        by_line: dict[int, list[Block]] = {}
        for b in blocks:
            by_line.setdefault(b.line, []).append(b)

        spans = golden.spans.get(rel, [])
        golden_error = ""
        try:
            pairs = {cand.uid: (span, cand) for span, cand in golden_rules(rel, page.text, spans)}
            resolved = {s.span_id: resolve_span(s, blocks) for s in spans}
        except GoldenError as exc:
            # The build would refuse this page too; say so on every rule of it
            # and fall back to placing each statement by text.
            pairs, resolved, golden_error = {}, {}, str(exc)
        kids_of: dict[str, list] = {}
        for r in resolved.values():
            if r.span.kind != RULE and r.span.of:
                kids_of.setdefault(r.span.of, []).append(r)
        position = {b.id: i for i, b in enumerate(blocks)}
        for kids in kids_of.values():
            kids.sort(key=lambda k: (position.get(k.block.id, 0), k.span.start))

        sweep = sweeps.get(rel)
        dropped = {d.get("uid"): d.get("reason", "") for d in (sweep or {}).get("dropped", [])}

        payload_rules = []
        for rule in page_rules:
            origin = _origin(rule, blocks, by_line, pairs.get(rule.uid), resolved, kids_of)
            hows[origin["how"]] = hows.get(origin["how"], 0) + 1
            payload_rules.append({
                "rule": rule.to_dict(),
                "origin": origin,
                "snapshot_matches": rule.source.snapshot_sha256 == page.sha256,
                "consensus": _consensus_for(rule, origin["span"], consensus, by_rid,
                                            by_uid, adjudications),
                "lint": findings.get(rule.uid, []),
                "proposals": proposals.get(rule.uid, []),
                "sampled": rule.uid in sampled["uids"],
                "dropped_by_sweep": dropped.get(rule.uid),
            })
            index_rules.append(_summary(rule, page_no, origin["how"]))

        title = next((b.plain for b in blocks if b.kind == "heading" and b.level == 1), rel)
        payload = {
            "path": rel,
            "title": title,
            "url": urls.get(rel, ""),
            "sha256": page.sha256,
            "eligible": eligible,
            "eligibility_reason": reason,
            "golden_error": golden_error,
            "sweep": {k: v for k, v in (sweep or {}).items() if k != "dropped"} or None,
            "blocks": [b.to_dict() for b in blocks],
            "rules": payload_rules,
        }
        name = f"data/pages/{_slug(rel)}.json"
        sizes[name] = _write_json(out / name, payload)
        index_pages.append({"path": rel, "slug": _slug(rel), "title": title,
                            "section": rel.split("/")[0], "rules": len(page_rules),
                            "eligible": eligible, "missing": False})

    statuses: dict[str, int] = {}
    methods: dict[str, int] = {}
    for r in index_rules:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        methods[r["method"]] = methods.get(r["method"], 0) + 1

    index = {
        "static": True,
        "build": build_info,
        "freeze": {"frozen": freeze.frozen, "frozen_at": freeze.frozen_at,
                   "reason": freeze.reason},
        "glossary": glossary["buckets"],
        "sample": {"seed": sampled["seed"], "population": sampled["population"],
                   "size": len(sampled["uids"])},
        "pages": index_pages,
        "rules": index_rules,
        "totals": {"rules": len(index_rules), "pages": len(index_pages),
                   "status": dict(sorted(statuses.items())),
                   "method": dict(sorted(methods.items())),
                   "how": dict(sorted(hows.items()))},
    }

    (out / "index.html").write_text((HERE / "index.html").read_text(encoding="utf-8"),
                                    encoding="utf-8")
    # Pages runs Jekyll over an uploaded tree unless told not to.
    (out / ".nojekyll").write_text("", encoding="utf-8")
    sizes["index.html"] = (out / "index.html").stat().st_size
    sizes["data/index.json"] = _write_json(out / "data" / "index.json", index)

    manifest = {
        **build_info,
        "totals": index["totals"],
        "bytes": {k: sizes[k] for k in ("index.html", "data/index.json")},
        "page_payload_bytes": sum(v for k, v in sizes.items() if k.startswith("data/pages/")),
    }
    _write_json(out / "data" / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "site" / "inspect",
                    help="directory to write into (default: site/inspect/)")
    ap.add_argument("--no-clean", action="store_true",
                    help="keep anything already in --out")
    args = ap.parse_args(argv)

    manifest = build(args.out.resolve(), clean=not args.no_clean)
    t = manifest["totals"]
    how = ", ".join(f"{n} {k}" for k, n in t["how"].items())
    print(f"Built {args.out}: {t['rules']} rules on {t['pages']} pages")
    print(f"  placed by {how}")
    print(f"  shell {sum(manifest['bytes'].values()) / 1024:.0f} KB + "
          f"{manifest['page_payload_bytes'] / 1024:.0f} KB of page payloads, "
          f"fetched one page at a time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
