"""The dogfood gate (ADR-011).

Fire every loadable rule at the Style Manual's own prose. That corpus is
213,000 words of professionally edited APS content written by the people who
author the rules, so it is the most compliant text that exists. A rule that
fires on it is almost certainly inverted, over-broad, scoped to the wrong
unit, or matching the manual's description of the rule rather than the
pattern the rule describes — the four failure modes that made Octavius
unusable (postmortem F1, F2, F4, F5).

The gate runs on RAW, UN-SUPPRESSED output: before firing budgets, before
dedup, before document-level gating. Octavius introduced all three to make
its output tolerable, which removed the pressure to notice that its rulebook
scored 1,441 findings per 1,000 words (postmortem Defect 6).

    python -m derek.eval.dogfood                       # gate the Derek ledger
    python -m derek.eval.dogfood --octavius PATH       # reproduce the postmortem

Exit code is non-zero if any rule exceeds its declared density budget.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

from derek.corpus.normalise import EXAMPLE_HEADINGS, NormalisedPage

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
DEFAULT_LEDGER = REPO / "ledger" / "rules.jsonl"

# A rule may not spend longer than this on one page. A pattern that does is
# a catastrophic-backtracking bug and is reported as a failure, not waited on.
_PER_PAGE_TIMEOUT_S = 2.0

# Blocks whose content is deliberately non-compliant. The manual quotes bad
# examples under these headings, so their spans are removed before the gate
# runs (ADR-011).
_NEGATIVE_BLOCKS = frozenset({"not this", "incorrect", "don't do this"})

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)


class _Timeout(Exception):
    pass


def _on_alarm(signum, frame):  # pragma: no cover - signal handler
    raise _Timeout()


@dataclass
class RuleResult:
    rule_id: str
    statement: str
    findings: int
    pages_hit: int
    density: float          # findings per 10,000 words
    budget: float
    error: str = ""

    @property
    def over_budget(self) -> bool:
        return not self.error and self.density > self.budget


def strip_negative_blocks(text: str) -> str:
    """Remove "Not this" / "Incorrect" blocks from a page.

    Their content is deliberately non-compliant and would otherwise be
    counted against every rule that correctly detects it.
    """
    out: list[str] = []
    skip_level: int | None = None
    for line in text.split("\n"):
        m = _HEADING.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip().lower()
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if title in _NEGATIVE_BLOCKS:
                skip_level = level
                continue
        if skip_level is None:
            out.append(line)
    return "\n".join(out)


def load_corpus() -> tuple[list[tuple[str, str]], int]:
    """Return ``([(path, text)], total_words)`` with negative blocks removed."""
    docs: list[tuple[str, str]] = []
    for md in sorted(PAGES.rglob("*.md")):
        page = NormalisedPage(str(md), md.read_text(encoding="utf-8", errors="replace"))
        docs.append((str(md.relative_to(PAGES)), strip_negative_blocks(page.text)))
    return docs, sum(len(t.split()) for _, t in docs)


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------

def _derek_matcher(rule: dict):
    """Build a callable from a declarative Derek matcher (ADR-009).

    Never executes code from the ledger. Unsupported methods return None and
    the rule is skipped with a recorded reason rather than silently passing.
    """
    det = rule.get("detection") or {}
    method, spec = det.get("method"), det.get("matcher") or {}

    if method == "regex":
        pattern = spec.get("pattern")
        if not pattern:
            return None
        flags = re.IGNORECASE if spec.get("ignore_case", True) else 0
        rx = re.compile(pattern, flags)
        return lambda t: len(rx.findall(t))

    if method == "literal_set":
        terms = [re.escape(x) for x in spec.get("terms", []) if x]
        if not terms:
            return None
        rx = re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)
        return lambda t: len(rx.findall(t))

    # token_pattern / length_constraint / structural_predicate / classifier
    # are evaluated by the runtime, not here; they need a parsed Document.
    return None


def _octavius_matcher(row: dict):
    """Compile a v1 rulebook row, to reproduce the postmortem figures.

    v1 stored executable Python in ``trigger_code`` (postmortem Defect 2).
    This is run only against the retained historical rulebook, never in any
    Derek runtime path.
    """
    tax, code = row.get("taxonomy"), row.get("trigger_code")
    if not code:
        return None
    try:
        if tax == "regex":
            rx = re.compile(code, re.IGNORECASE)
            return lambda t: sum(1 for _ in rx.finditer(t))
        if tax in ("lookup", "structural"):
            ns: dict = {"re": re, "__builtins__": __builtins__}
            exec(compile(code, f"<{row['rule_id']}>", "exec"), ns)  # noqa: S102
            fn = ns.get("check_rule")
            if fn is None:
                return None
            if tax == "lookup":
                ll = row.get("lookup_list") or []
                return lambda t: len(fn(t, ll) or [])
            return lambda t: len(fn(t) or [])
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------

def run_gate(rules: list[tuple[str, str, float, object]], docs, total_words) -> list[RuleResult]:
    """Fire each ``(rule_id, statement, budget, matcher)`` at the corpus."""
    results: list[RuleResult] = []
    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        signal.signal(signal.SIGALRM, _on_alarm)

    for rule_id, statement, budget, fn in rules:
        total, pages_hit, error = 0, 0, ""
        for _, text in docs:
            try:
                if has_alarm:
                    signal.setitimer(signal.ITIMER_REAL, _PER_PAGE_TIMEOUT_S)
                n = fn(text)
                if has_alarm:
                    signal.setitimer(signal.ITIMER_REAL, 0)
            except _Timeout:
                error = f"timeout (>{_PER_PAGE_TIMEOUT_S}s on one page)"
                break
            except Exception as exc:
                if has_alarm:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                error = f"{type(exc).__name__}: {exc}"
                break
            if n:
                total += n
                pages_hit += 1
        density = 10_000 * total / total_words if total_words else 0.0
        results.append(RuleResult(rule_id, statement, total, pages_hit, density, budget, error))

    results.sort(key=lambda r: (-r.findings, r.rule_id))
    return results


def _report(results: list[RuleResult], total_words: int, n_docs: int, label: str) -> int:
    total = sum(r.findings for r in results)
    fired = [r for r in results if r.findings]
    over = [r for r in results if r.over_budget]
    errored = [r for r in results if r.error]

    print("=" * 70)
    print(f"DOGFOOD GATE — {label}")
    print("=" * 70)
    print(f"corpus                      : {n_docs} pages, {total_words:,} words")
    print(f"rules evaluated             : {len(results)}")
    print(f"total findings              : {total:,}")
    print(f"findings per 1,000 words    : {1000 * total / total_words:,.1f}" if total_words else "")
    print(f"rules that fired            : {len(fired)}")
    print(f"rules over density budget   : {len(over)}")
    print(f"rules that errored/timed out: {len(errored)}")

    if over:
        print("\nOVER BUDGET — these would be quarantined:")
        for r in over[:25]:
            print(f"  {r.findings:>7,} findings ({r.density:>8,.1f}/10k words, budget {r.budget})  {r.rule_id}")
            print(f"          \"{r.statement[:80]}\"")
    if errored:
        print("\nERRORED:")
        for r in errored[:10]:
            print(f"  {r.rule_id}: {r.error}")
    if not over and not errored:
        print("\nPASS — no rule exceeds its density budget.")
    return 1 if (over or errored) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--octavius", type=Path,
                    help="reproduce the postmortem figures from a v1 rulebook JSONL")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args(argv)

    docs, total_words = load_corpus()

    if args.octavius:
        rows = [json.loads(l) for l in args.octavius.read_text(encoding="utf-8").splitlines() if l.strip()]
        passing = [r for r in rows if r.get("test_result") == "pass"]
        rules = []
        for row in passing:
            fn = _octavius_matcher(row)
            if fn is not None:
                rules.append((row["rule_id"], row.get("rule_summary") or "", 0.0, fn))
        print(f"loaded {len(rules)} of {len(passing)} 'passing' v1 rules "
              f"({len(passing) - len(rules)} could not be compiled)\n")
        results = run_gate(rules, docs, total_words)
        code = _report(results, total_words, len(docs), "Octavius v1 rulebook (historical)")
        print(f"\nTOP {args.top} NOISIEST:")
        for r in results[:args.top]:
            print(f"  {r.findings:>7,}  {r.rule_id}\n           \"{r.statement[:76]}\"")
        return code

    rules = []
    skipped = 0
    for line in args.ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rule = json.loads(line)
        if rule["review"]["status"] not in ("accepted", "amended"):
            continue
        if not (rule.get("detection") or {}).get("detectable"):
            continue
        fn = _derek_matcher(rule)
        if fn is None:
            skipped += 1
            continue
        rules.append((
            rule["uid"],
            rule["source"]["statement"],
            float(rule["validation"].get("expected_density") or 0.0),
            fn,
        ))

    if skipped:
        print(f"note: {skipped} accepted rule(s) use a matcher this gate cannot "
              f"evaluate standalone (token_pattern/classifier); they are covered "
              f"by the runtime gate instead.\n")
    if not rules:
        print("No accepted, statically-evaluable rules in the ledger yet — nothing to gate.")
        print("This is expected until rules pass review (ADR-008).")
        return 0

    results = run_gate(rules, docs, total_words)
    return _report(results, total_words, len(docs), "Derek ledger")


if __name__ == "__main__":
    raise SystemExit(main())
