"""Run accepted rules over a Document and return findings (Layer 3).

Only a rule a human accepted loads (D-10), only a declarative matcher runs
(D-11), and a finding's ``confidence`` is ``None`` until it has been calibrated
on held-out data (D-12). A number nobody measured would be the invented
confidence ADR-013 forbids.

Tier 0 only. A rule routed to Tier 1 or with no matcher is reported as not
loaded, with the reason, never silently skipped.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

from derek.detect.document import Document
from derek.detect.matchers import SUPPORTED, Matcher, MatcherError, compile_matcher
from derek.extract.modality import default_severity
from derek.ledger.model import ReviewStatus, Rule, Unit

__all__ = ["Finding", "Loaded", "load", "detect", "check_examples", "ExampleCheck"]


@dataclass(frozen=True)
class Finding:
    rule_uid: str
    start: int
    end: int
    quote: str
    block_id: str
    severity: str
    confidence: float | None = None


@dataclass
class Loaded:
    rules: list[tuple[Rule, Matcher]]
    skipped: list[tuple[str, str]]       # (uid, why)


def load(rules: dict[str, Rule] | list[Rule]) -> Loaded:
    """The rules that may run, compiled, and the reason for each that may not."""
    out = Loaded([], [])
    for rule in (rules.values() if isinstance(rules, dict) else rules):
        det = rule.detection
        if rule.review.status not in ReviewStatus.LOADABLE:
            continue
        if rule.unit == Unit.ARTIFACT:
            out.skipped.append((rule.uid, "unit is artifact: not about text (D-6)"))
            continue
        if not det.detectable or det.method not in SUPPORTED:
            out.skipped.append((rule.uid, det.not_detectable_reason
                                or f"method {det.method!r} is not Tier 0"))
            continue
        try:
            out.rules.append((rule, compile_matcher(det.method, det.matcher)))
        except MatcherError as exc:
            out.skipped.append((rule.uid, f"matcher refused: {exc}"))
    return out


def detect(doc: Document, loaded: Loaded) -> list[Finding]:
    """Every finding, raw: no budgets, no dedup, no suppression (D-14)."""
    found = []
    for rule, matcher in loaded.rules:
        severity = default_severity(rule.modality)
        for b in doc.blocks:
            if not b.lintable:
                continue
            for a, z in matcher.find(b.text):
                found.append(Finding(rule.uid, b.start + a, b.start + z, b.text[a:z],
                                     b.id, severity))
    found.sort(key=lambda f: (f.start, f.end, f.rule_uid))
    return found


@dataclass
class ExampleCheck:
    missed: list[str]          # violating examples that did not fire
    false_alarms: list[str]    # compliant examples that did

    @property
    def passed(self) -> bool:
        return not self.missed and not self.false_alarms


def check_examples(matcher: Matcher, compliant: list[str], violating: list[str]) -> ExampleCheck:
    """ADR-004: every violating example fires, and no compliant one does.

    An example is judged block by block, as a document would be, so a grouped
    example (a list's lead-in and its items, joined by newlines) is not matched
    across the join.
    """
    def fires(text: str) -> bool:
        return any(matcher.find(part) for part in text.split("\n"))
    return ExampleCheck(
        missed=[v for v in violating if not fires(v)],
        false_alarms=[c for c in compliant if fires(c)],
    )
