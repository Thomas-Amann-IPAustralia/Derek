"""Score model drafts against the golden set (ADR-025).

    python -m derek.eval.draft_score                   # the report
    python -m derek.eval.draft_score --json
    python -m derek.eval.draft_score --prompt p1 --model claude-opus-5

Two different questions, answered on two different sets of pages, and never
added together:

**How good are the drafts?** Only a *blind* page can answer that
(``golden/blind.json``): the human marked it without seeing a draft, so their
marks are independent of it. On a blind page this reports rule recall, rule
precision (once the page is swept; before that, a draft rule the human did not
mark may be one they missed), whether the draft attached the same examples with
the same polarity, and whether it chose the same direction and modality. Beside
it, on the same pages, the two baselines a draft has to beat: the heading walk
and a sentence regex (``derek.eval.directives``). A drafter that finds 12 of 13
rules is only interesting if a regex does not find 11.

**How much of the draft did the reviewer keep?** That is a seeded page, where
the draft was on screen. Acceptance is useful to know, and to watch for
rubber-stamping, but it measures the reviewer and the draft together, so it is
reported separately and never as quality.

It reads and prints. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import NormalisedPage
from derek.eval.directives import directive_sentences
from derek.extract.blocks import parse_blocks
from derek.extract.candidates import extract_candidates
from derek.extract.golden import EXAMPLE_KINDS, RULE, GoldenError, load_golden, resolve_span

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
DRAFTS = REPO / "golden" / "drafts"
BLIND = REPO / "golden" / "blind.json"

TAGS = ("direction", "modality", "unit", "detection_hint")


@dataclass
class PageScore:
    page_path: str
    blind: bool
    swept: bool
    golden: int = 0
    drafted: int = 0
    matched: int = 0
    exact_extent: int = 0
    refused: int = 0
    served_model: str = ""
    missed: list[str] = field(default_factory=list)       # golden rules no draft rule matched
    extra: list[str] = field(default_factory=list)        # draft rules matching no golden rule
    examples_golden: int = 0
    examples_found: int = 0
    polarity_conflicts: list[str] = field(default_factory=list)
    tag_agree: dict = field(default_factory=dict)          # tag -> [agree, compared]
    accepted_from_draft: int = 0                           # seeded pages only
    human_added: int = 0
    heading_walk_hits: int = 0
    heading_walk_candidates: int = 0
    regex_hits: int = 0
    regex_candidates: int = 0


def _latest(root: Path) -> tuple[str, str] | None:
    runs = sorted((p.parent.name, p.name) for p in root.glob("*/*") if p.is_dir())
    return runs[-1] if runs else None


def load_drafts(prompt: str, model: str, root: Path = DRAFTS) -> dict[str, dict]:
    out = {}
    for p in sorted((root / prompt / model).rglob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[rec["page_path"]] = rec
    return out


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2}


def _same_section(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """One heading path contains the other: a heading and the prose beneath it,
    or prose and the example label it runs on under."""
    n = min(len(a), len(b))
    return n > 0 and tuple(a[:n]) == tuple(b[:n])


def _overlap(a: tuple[str, int, int], b: tuple[str, int, int]) -> int:
    if a[0] != b[0]:
        return 0
    return max(0, min(a[2], b[2]) - max(a[1], b[1]))


def score_page(rel: str, draft: dict, golden, blind: bool) -> PageScore:
    text = NormalisedPage(rel, (PAGES / rel).read_text(encoding="utf-8")).text
    blocks = parse_blocks(rel, text)
    by_id = {b.id: b for b in blocks}
    swept = rel in golden.authoritative
    s = PageScore(rel, blind, swept, refused=len(draft.get("refused", [])),
                  served_model=draft.get("served_model", ""))

    spans = golden.spans.get(rel, [])
    resolved = {}
    for sp in spans:
        try:
            resolved[sp.span_id] = resolve_span(sp, blocks)
        except GoldenError:
            continue
    g_rules = [r for r in resolved.values() if r.span.kind == RULE]
    g_rules.sort(key=lambda r: (blocks.index(r.block), r.span.start))
    d_rules = draft.get("rules", [])
    s.golden, s.drafted = len(g_rules), len(d_rules)

    # One-to-one matching: character overlap in the same block first, then a
    # rule marked on the same heading's body with most of the same words (the
    # "right place, other extent" case, which is agreement about the rule).
    free = set(range(len(d_rules)))
    pairs = []
    for g in g_rules:
        gk = (g.block.id, g.span.start, g.span.end)
        best, best_score = None, 0.0
        for i in free:
            a = d_rules[i]["anchor"]
            ov = _overlap(gk, (a["block_id"], a["start"], a["end"]))
            if ov:
                score = 1.0 + ov
            else:
                db = by_id.get(a["block_id"])
                if db is None or not _same_section(db.heading_path, g.block.heading_path):
                    continue
                gw, dw = _words(g.text), _words(a["quote"])
                j = len(gw & dw) / len(gw | dw) if gw | dw else 0.0
                if j < 0.5:
                    continue
                score = j
            if score > best_score:
                best, best_score = i, score
        if best is None:
            s.missed.append(g.text[:120])
            continue
        free.discard(best)
        pairs.append((g, d_rules[best]))
        a = d_rules[best]["anchor"]
        if gk == (a["block_id"], a["start"], a["end"]):
            s.exact_extent += 1
    s.matched = len(pairs)
    s.extra = [d_rules[i]["anchor"]["quote"][:120] for i in sorted(free)]

    kids = [r for r in resolved.values() if r.span.kind in EXAMPLE_KINDS]
    for g, d in pairs:
        mine = {k.text: k.span.kind for k in kids if k.span.of == g.span.span_id}
        theirs = {p["quote"]: ex["kind"] for ex in d.get("examples", []) for p in ex["parts"]}
        s.examples_golden += len(mine)
        for quote, kind in mine.items():
            if quote in theirs:
                s.examples_found += 1
                if theirs[quote] != kind:
                    s.polarity_conflicts.append(
                        f"{quote[:90]} — human: {kind}, draft: {theirs[quote]}")
        for tag in TAGS:
            human = (g.span.tags or {}).get(tag) or ""
            if not human:
                continue
            got = s.tag_agree.setdefault(tag, [0, 0])
            got[1] += 1
            got[0] += int(d.get("tags", {}).get(tag) == human)

    if not blind:
        s.accepted_from_draft = sum(1 for g in g_rules if g.span.seed_draft)
        s.human_added = s.golden - s.accepted_from_draft

    # The baselines, on the same page and against the same marks.
    seeds = extract_candidates(rel, text)
    by_line = {b.line: b for b in blocks if b.kind == "heading"}
    seed_blocks = {by_line[c.line_start].id for c in seeds if c.line_start in by_line}
    s.heading_walk_candidates = len(seed_blocks)
    s.heading_walk_hits = sum(1 for g in g_rules if g.block.id in seed_blocks)
    regex = directive_sentences(blocks)
    s.regex_candidates = len(regex)
    s.regex_hits = sum(1 for g in g_rules if any(
        _overlap((g.block.id, g.span.start, g.span.end), (d.block_id, d.start, d.end))
        for d in regex))
    return s


def score(prompt: str | None = None, model: str | None = None,
          drafts_root: Path = DRAFTS, blind_path: Path = BLIND,
          spans_path: Path | None = None, pages_path: Path | None = None) -> tuple[str, str, list[PageScore]]:
    if prompt is None or model is None:
        latest = _latest(drafts_root)
        if latest is None:
            return "", "", []
        prompt, model = prompt or latest[0], model or latest[1]
    drafts = load_drafts(prompt, model, drafts_root)
    blind = set(json.loads(blind_path.read_text(encoding="utf-8")).get("pages", {})) \
        if blind_path.exists() else set()
    kwargs = {}
    if spans_path is not None:
        kwargs["spans_path"] = spans_path
    if pages_path is not None:
        kwargs["pages_path"] = pages_path
    golden = load_golden(eligibility=load_eligibility(ELIGIBILITY), **kwargs)
    out = [score_page(rel, rec, golden, rel in blind)
           for rel, rec in sorted(drafts.items()) if golden.spans.get(rel)]
    return prompt, model, out


# ---------------------------------------------------------------------------

def _pct(n: int, d: int) -> str:
    return f"{n / d:.0%} ({n}/{d})" if d else "—"


def _tag_rows(rows: list[PageScore], label: str) -> list[str]:
    out = []
    for tag in TAGS:
        a = sum(r.tag_agree.get(tag, [0, 0])[0] for r in rows)
        n = sum(r.tag_agree.get(tag, [0, 0])[1] for r in rows)
        if n:
            out.append(f"| {label} `{tag}` | {_pct(a, n)} |")
    return out


def _details(rows: list[PageScore], *, blind: bool) -> list[str]:
    lines = []
    conflicts = [c for r in rows for c in r.polarity_conflicts]
    if conflicts:
        lines += ["**Polarity conflicts.** The human and the model disagree on whether "
                  "the manual shows this text as right or wrong. Read each one: one "
                  "side is teaching a checker the opposite of the manual (E-1).", ""]
        lines += [f"- {c}" for c in conflicts] + [""]
    for r in rows:
        if not (r.missed or r.extra):
            continue
        lines.append(f"### `{r.page_path}`" + (" (swept)" if r.swept else " (not swept)"))
        miss = "missed by the draft" if blind else "added by the reviewer"
        lines += [f"- {miss}: {m}" for m in r.missed]
        extra = ("draft only" + ("" if r.swept else ", which may be a rule the human has not reached yet")
                 if blind else ("not kept" if r.swept else "not yet reviewed"))
        lines += [f"- {extra}: {x}" for x in r.extra]
        lines.append("")
    return lines


def _quality(rows: list[PageScore]) -> list[str]:
    """Blind pages: the draft against marks made without it."""
    if not rows:
        return []
    t = lambda attr: sum(getattr(r, attr) for r in rows)  # noqa: E731
    swept = [r for r in rows if r.swept]
    lines = ["## Blind pages: how good are the drafts?", "",
             f"{len(rows)} page(s), {len(swept)} swept. Precision needs a swept page: "
             f"until then, a draft rule the human has not marked may be one they have "
             f"not reached.", "", "| | |", "|---|---|",
             f"| Rules the human marked | {t('golden')} |",
             f"| Rules the draft proposed | {t('drafted')} |",
             f"| **Recall**: the human's rules the draft found | **{_pct(t('matched'), t('golden'))}** |"]
    if swept:
        m, d = sum(r.matched for r in swept), sum(r.drafted for r in swept)
        lines.append(f"| **Precision**: draft rules the human also marked (swept pages) | **{_pct(m, d)}** |")
    lines += [f"| Same extent, exactly | {_pct(t('exact_extent'), t('matched'))} |",
              f"| The human's examples the draft also attached | {_pct(t('examples_found'), t('examples_golden'))} |",
              f"| Examples with opposite polarity | {sum(len(r.polarity_conflicts) for r in rows)} |",
              *_tag_rows(rows, "Same"),
              f"| Pointers refused (quote not in the manual) | {t('refused')} |",
              f"| *Baseline:* heading walk recall | {_pct(t('heading_walk_hits'), t('golden'))} from {t('heading_walk_candidates')} candidates |",
              f"| *Baseline:* sentence regex recall | {_pct(t('regex_hits'), t('golden'))} from {t('regex_candidates')} candidates |",
              ""]
    return lines + _details(rows, blind=True)


def _acceptance(rows: list[PageScore]) -> list[str]:
    """Seeded pages: what the reviewer kept. Never a quality number."""
    if not rows:
        return []
    t = lambda attr: sum(getattr(r, attr) for r in rows)  # noqa: E731
    swept = [r for r in rows if r.swept]
    lines = ["## Seeded pages: how much did the reviewer keep?", "",
             f"{len(rows)} page(s), {len(swept)} swept. The draft was on screen here, so "
             f"none of this measures its quality. It measures the draft and the reviewer "
             f"together. Tags left exactly as drafted near 100% across many pages is the "
             f"number to watch: it is what rubber-stamping looks like.", "",
             "| | |", "|---|---|",
             f"| Rules marked | {t('golden')} |",
             f"| … accepted from the draft | {_pct(t('accepted_from_draft'), t('golden'))} |",
             f"| … added by the reviewer | {t('human_added')} |",
             f"| Draft rules proposed | {t('drafted')} |"]
    if swept:
        kept = sum(r.matched for r in swept)
        lines.append(f"| Draft rules not kept (swept pages) | {sum(r.drafted for r in swept) - kept} |")
    lines += [*_tag_rows(rows, "Left as drafted:"),
              f"| Draft examples the reviewer kept | {_pct(t('examples_found'), t('examples_golden'))} |",
              ""]
    return lines + _details(rows, blind=False)


def report(prompt: str, model: str, rows: list[PageScore]) -> str:
    if not rows:
        return ("No drafts overlap any annotated page yet. Draft the blind pages "
                "(`python tools/draft/draft_spans.py --blind`) and sweep them.\n")
    lines = [f"# Draft score — prompt `{prompt}`, model `{model}`", ""]
    odd = sorted({r.served_model for r in rows} - {model, ""})
    if odd:
        lines += [f"> Some pages were drafted by a fallback model ({', '.join(odd)}) "
                  f"after a refusal; they are included, and marked in the records.", ""]
    lines += _quality([r for r in rows if r.blind])
    lines += _acceptance([r for r in rows if not r.blind])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prompt")
    ap.add_argument("--model")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    prompt, model, rows = score(args.prompt, args.model)
    if args.json:
        json.dump({"prompt": prompt, "model": model, "pages": [asdict(r) for r in rows]},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        sys.stdout.write(report(prompt, model, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
