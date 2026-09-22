"""Measure the heading heuristic against the golden set (ADR-023).

    python -m derek.eval.span_recall              # the report
    python -m derek.eval.span_recall missed       # the rules no heading reaches
    python -m derek.eval.span_recall spurious     # headings the human did not mark
    python -m derek.eval.span_recall pages        # per-page, worst first

This is the instrument the golden set exists to make possible, and the thing that
says when a candidate heuristic is good enough to unfreeze the corpus (ADR-024).

**It only reads swept pages.** A page with spans but no `status: complete` marker
tells you nothing about precision: a heading with no span there might be a rule
nobody has got to yet. A swept page is a human saying "I read this and these are
all its rules", which is what turns every unmarked heading into a labelled
negative — and a labelled negative is the whole difference between a set you can
fit a heuristic to and one you can also measure it on.

The number that matters most is not precision or recall. It is
**`missed_not_a_heading`**: golden rules that are not headings at all. No heading
heuristic can reach those at any threshold, because there is no heading there to
classify. `docs/07-extraction-hand-audit.md` estimated roughly 60 corpus-wide by
hand-reading a sample; this counts them.

Everything here is a measuring instrument. It reads and prints; it never writes
the ledger, never writes the golden set, and never feeds a value back into
extraction. Stdlib-only, like the layers it measures.
"""

from __future__ import annotations

import collections
import sys
from dataclasses import dataclass, field
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import NormalisedPage
from derek.extract.blocks import parse_blocks
from derek.extract.candidates import extract_candidates
from derek.extract.golden import RULE, load_golden, resolve_span

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"


@dataclass
class PageResult:
    page_path: str
    hits: list[str] = field(default_factory=list)          # heading marked as a rule
    missed_heading: list[str] = field(default_factory=list)  # rule on a heading, not proposed
    missed_prose: list[str] = field(default_factory=list)    # rule not on a heading at all
    spurious: list[str] = field(default_factory=list)        # proposed, not marked
    forms: collections.Counter = field(default_factory=collections.Counter)

    @property
    def golden(self) -> int:
        return len(self.hits) + len(self.missed_heading) + len(self.missed_prose)

    @property
    def reachable(self) -> int:
        """Golden rules a heading heuristic could reach even in principle."""
        return len(self.hits) + len(self.missed_heading)


def measure(spans_path: Path | None = None, pages_path: Path | None = None) -> list[PageResult]:
    """Compare `classify_heading`'s verdict against the golden set, per swept page."""
    eligibility = load_eligibility(ELIGIBILITY)
    kwargs = {}
    if spans_path is not None:
        kwargs["spans_path"] = spans_path
    if pages_path is not None:
        kwargs["pages_path"] = pages_path
    golden = load_golden(eligibility=eligibility, **kwargs)

    out: list[PageResult] = []
    for rel in sorted(golden.authoritative):
        src = PAGES / rel
        if not src.exists():
            continue
        text = NormalisedPage(rel, src.read_text(encoding="utf-8")).text
        blocks = parse_blocks(rel, text)
        by_id = {b.id: b for b in blocks}

        # What the extractor proposed, keyed by the heading text it proposed it from.
        proposed = {c.statement: c for c in extract_candidates(rel, text)}

        # What the human marked, split by whether a heading was even available.
        marked_headings: set[str] = set()
        result = PageResult(page_path=rel)
        for span in golden.spans.get(rel, []):
            if span.kind != RULE:
                continue
            block = by_id.get(span.block_id)
            if block is None:
                try:
                    block = resolve_span(span, blocks).block
                except Exception:                     # noqa: BLE001 — reported, not raised
                    result.missed_prose.append(span.quote)
                    continue
            covers_whole_heading = (
                block.kind == "heading"
                and span.start == 0 and span.end == len(block.plain))
            if not covers_whole_heading:
                result.missed_prose.append(span.quote)
                continue
            marked_headings.add(block.plain)
            if block.plain in proposed:
                result.hits.append(block.plain)
                result.forms[proposed[block.plain].statement_form] += 1
            else:
                result.missed_heading.append(block.plain)

        result.spurious = sorted(s for s in proposed if s not in marked_headings)
        out.append(result)
    return out


def _totals(results: list[PageResult]) -> dict:
    hits = sum(len(r.hits) for r in results)
    missed_heading = sum(len(r.missed_heading) for r in results)
    missed_prose = sum(len(r.missed_prose) for r in results)
    spurious = sum(len(r.spurious) for r in results)
    golden = hits + missed_heading + missed_prose
    reachable = hits + missed_heading
    return {
        "pages_swept": len(results),
        "golden_rules": golden,
        "hits": hits,
        "missed_heading": missed_heading,
        "missed_not_a_heading": missed_prose,
        "spurious": spurious,
        "precision": hits / (hits + spurious) if (hits + spurious) else None,
        "recall_overall": hits / golden if golden else None,
        "recall_reachable": hits / reachable if reachable else None,
    }


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def report(results: list[PageResult]) -> None:
    if not results:
        print("No swept pages yet.\n")
        print("The golden set can only be measured on pages a human has marked as")
        print("swept in the annotator (press F). Until then, a heading with no span")
        print("on it might be a rule nobody has reached — which is not a negative")
        print("example, and precision computed over it would be fiction.")
        return

    t = _totals(results)
    print(f"Swept pages: {t['pages_swept']}    Golden rules on them: {t['golden_rules']}")
    print()
    print("Heading heuristic, measured against what a human actually marked:")
    print(f"  proposed and marked      {t['hits']:>5}")
    print(f"  proposed, not marked     {t['spurious']:>5}   ← noise a reviewer has to bin")
    print(f"  marked, not proposed     {t['missed_heading']:>5}   ← a heading the branches missed")
    print(f"  marked, not a heading    {t['missed_not_a_heading']:>5}   ← unreachable by ANY heading rule")
    print()
    print(f"  precision                {_pct(t['precision']):>6}")
    print(f"  recall, all golden rules {_pct(t['recall_overall']):>6}")
    print(f"  recall, heading rules    {_pct(t['recall_reachable']):>6}   ← the ceiling for this method")
    print()

    forms = collections.Counter()
    for r in results:
        forms.update(r.forms)
    if forms:
        print("Confirmed candidates by the branch that found them:")
        for form, n in forms.most_common():
            print(f"  {form:<22} {n:>5}")
        print()

    if t["missed_not_a_heading"]:
        share = t["missed_not_a_heading"] / t["golden_rules"]
        print(f"{_pct(share)} of the golden rules on these pages are not headings. No")
        print("heading heuristic reaches them at any threshold; a prose pass would be")
        print("a different method, and docs/05 Q6 is where that decision lives.")
    print()
    print("Unfreezing (ADR-024) is worth considering when a candidate heuristic")
    print("reproduces the golden set closely enough that re-extracting costs less")
    print("review than it saves. This report is how you tell.")


def _listing(results: list[PageResult], which: str) -> None:
    field_name = {"missed": "missed_prose", "spurious": "spurious"}[which]
    total = 0
    for r in results:
        rows = getattr(r, field_name)
        if which == "missed":
            rows = rows + r.missed_heading
        if not rows:
            continue
        print(f"\n{r.page_path}")
        for row in rows:
            print(f"  {row[:110]}")
            total += 1
    print(f"\n{total} total.")
    if not total:
        print("Nothing to show — either nothing is swept, or the heuristic agreed.")


def _pages(results: list[PageResult]) -> None:
    print(f"{'page':<62} {'golden':>6} {'hit':>4} {'miss':>5} {'prose':>6} {'spur':>5}")
    worst = sorted(results, key=lambda r: (-(len(r.missed_prose) + len(r.missed_heading)),
                                           -len(r.spurious), r.page_path))
    for r in worst:
        print(f"{r.page_path[:62]:<62} {r.golden:>6} {len(r.hits):>4} "
              f"{len(r.missed_heading):>5} {len(r.missed_prose):>6} {len(r.spurious):>5}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else "report"
    results = measure()

    if command == "report":
        report(results)
    elif command in ("missed", "spurious"):
        _listing(results, command)
    elif command == "pages":
        _pages(results)
    else:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
