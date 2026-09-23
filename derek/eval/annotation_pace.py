"""How fast pages are being annotated, from the reviewer's own timestamps.

    python -m derek.eval.annotation_pace
    python -m derek.eval.annotation_pace --json

The question ADR-025 has to answer with a number: do drafts make annotation
faster, and by how much? Every op the annotator exports carries the time the
reviewer made it, and ``golden/span_ops.jsonl`` keeps every applied op, so the
pace of each page can be read back without anyone keeping a timesheet.

**How time is counted.** All ops, on every page, go on one timeline. Each gap
between consecutive ops is credited to the page of the later op, so moving
between pages is not counted twice. A gap longer than ``BREAK_MINUTES`` is a
break and counts for nothing. That makes every figure a **lower bound**: the
reading done before a page's first op is invisible, and so is a long think.
Compare pages with each other, not with a clock.

It reads and prints. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.extract.golden import RULE, load_golden

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
SPAN_OPS = REPO / "golden" / "span_ops.jsonl"
BLIND = REPO / "golden" / "blind.json"

BREAK_MINUTES = 10


@dataclass
class Pace:
    page_path: str
    words: int
    ops: int
    minutes: float
    rules: int
    swept: bool
    mode: str            # blind | seeded | unassisted

    @property
    def words_per_minute(self) -> float | None:
        return self.words / self.minutes if self.minutes else None

    @property
    def minutes_per_rule(self) -> float | None:
        return self.minutes / self.rules if self.rules else None


def _when(op: dict) -> datetime | None:
    try:
        return datetime.fromisoformat((op.get("at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _page_of(op: dict) -> str:
    return op.get("page_path") or (op.get("span") or {}).get("page_path") or ""


def _words(rel: str) -> int:
    src = PAGES / rel
    return len(re.findall(r"\w+", src.read_text(encoding="utf-8"))) if src.exists() else 0


def measure(ops_path: Path = SPAN_OPS, blind_path: Path = BLIND,
            spans_path: Path | None = None, pages_path: Path | None = None) -> list[Pace]:
    ops = []
    if ops_path.exists():
        for line in ops_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                op = json.loads(line)
                if op.get("op") != "meta" and _page_of(op) and _when(op):
                    ops.append(op)
    ops.sort(key=lambda o: (_when(o), o.get("op_id", "")))

    minutes: dict[str, float] = {}
    count: dict[str, int] = {}
    for prev, op in zip([None, *ops], ops):
        page = _page_of(op)
        count[page] = count.get(page, 0) + 1
        minutes.setdefault(page, 0.0)
        if prev is not None:
            gap = (_when(op) - _when(prev)).total_seconds() / 60
            if 0 <= gap <= BREAK_MINUTES:
                minutes[page] += gap

    blind = set(json.loads(blind_path.read_text(encoding="utf-8")).get("pages", {})) \
        if blind_path.exists() else set()
    kwargs = {}
    if spans_path is not None:
        kwargs["spans_path"] = spans_path
    if pages_path is not None:
        kwargs["pages_path"] = pages_path
    golden = load_golden(eligibility=load_eligibility(ELIGIBILITY), **kwargs)

    out = []
    for page in sorted(count):
        spans = golden.spans.get(page, [])
        rules = [s for s in spans if s.kind == RULE]
        if page in blind:
            mode = "blind"
        elif any(s.seed_draft for s in spans):
            mode = "seeded"
        else:
            mode = "unassisted"
        out.append(Pace(page, _words(page), count[page], round(minutes[page], 1),
                        len(rules), page in golden.authoritative, mode))
    return out


def remaining_words(paces: list[Pace]) -> int:
    eligibility = load_eligibility(ELIGIBILITY)
    done = {p.page_path for p in paces if p.swept}
    return sum(_words(str(md.relative_to(PAGES))) for md in PAGES.rglob("*.md")
               if eligibility.decide(str(md.relative_to(PAGES)))[0]
               and str(md.relative_to(PAGES)) not in done)


def report(paces: list[Pace]) -> str:
    if not paces:
        return "No annotation ops recorded yet (golden/span_ops.jsonl is empty).\n"
    lines = ["# Annotation pace", "",
             f"Lower bounds: gaps over {BREAK_MINUTES} minutes are breaks, and reading "
             f"before a page's first op is invisible. Compare pages with each other.", "",
             "| Page | Mode | Swept | Words | Minutes | Words/min | Rules | Min/rule |",
             "|---|---|---|---|---|---|---|---|"]
    for p in paces:
        wpm = f"{p.words_per_minute:.0f}" if p.words_per_minute else "—"
        mpr = f"{p.minutes_per_rule:.1f}" if p.minutes_per_rule else "—"
        lines.append(f"| `{p.page_path.split('/')[-1]}` | {p.mode} | {'yes' if p.swept else 'no'} "
                     f"| {p.words:,} | {p.minutes:.0f} | {wpm} | {p.rules} | {mpr} |")
    lines.append("")
    by_mode: dict[str, list[Pace]] = {}
    for p in paces:
        if p.words_per_minute:
            by_mode.setdefault(p.mode, []).append(p)
    rest = remaining_words(paces)
    for mode, ps in sorted(by_mode.items()):
        words = sum(p.words for p in ps)
        mins = sum(p.minutes for p in ps)
        wpm = words / mins
        lines.append(f"- **{mode}**: {len(ps)} page(s), {wpm:.0f} words a minute overall "
                     f"(median page {statistics.median(p.words_per_minute for p in ps):.0f}). "
                     f"At that pace the {rest:,} words on unswept eligible pages take about "
                     f"{rest / wpm / 60:.0f} hours.")
    if "seeded" not in by_mode:
        lines.append("- No seeded pages yet, so there is nothing to compare the unassisted "
                     "pace with. That comparison is the number ADR-025 is waiting for.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    paces = measure()
    if args.json:
        json.dump([{**asdict(p), "words_per_minute": p.words_per_minute,
                    "minutes_per_rule": p.minutes_per_rule} for p in paces],
                  sys.stdout, indent=1)
        print()
    else:
        sys.stdout.write(report(paces))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
