"""Deontic modality classification (ADR-016).

A deterministic lexical pass proposes a modality for a rule statement. The
proposal is a *default in the review UI*, never a decision: bare imperatives
are genuinely ambiguous between MUST and SHOULD, and the Style Manual is not
consistent about which it means.

Modality drives severity, the confidence slider's defaults, and the dogfood
gate's density budget — a MUST rule that fires on the manual's own prose is
a hard failure, whereas a PREFER rule may legitimately fire.
"""

from __future__ import annotations

import re

__all__ = ["Modality", "classify_modality", "default_severity"]


class Modality:
    MUST = "MUST"
    MUST_NOT = "MUST_NOT"
    SHOULD = "SHOULD"
    SHOULD_NOT = "SHOULD_NOT"
    MAY = "MAY"
    PREFER = "PREFER"

    ALL = (MUST, MUST_NOT, SHOULD, SHOULD_NOT, MAY, PREFER)


_SEVERITY = {
    Modality.MUST: "error",
    Modality.MUST_NOT: "error",
    Modality.SHOULD: "warning",
    Modality.SHOULD_NOT: "warning",
    Modality.MAY: "info",
    Modality.PREFER: "suggestion",
}

# Ordered most-specific first: "must not" must be tested before "must".
_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (Modality.MUST_NOT, re.compile(r"\b(?:must not|must never|shall not|may not|cannot ever)\b", re.I)),
    (Modality.SHOULD_NOT, re.compile(r"\b(?:should not|shouldn't|don't|do not|never|avoid|try not to)\b", re.I)),
    (Modality.MUST, re.compile(r"\b(?:must|shall|is required to|are required to|always)\b", re.I)),
    (Modality.SHOULD, re.compile(r"\b(?:should|ought to|we recommend|recommended|needs? to)\b", re.I)),
    (Modality.PREFER, re.compile(r"\b(?:prefer|rather than|instead of|in preference to|wherever possible)\b", re.I)),
    (Modality.MAY, re.compile(r"\b(?:may|can|it's fine to|optionally|if you (?:want|prefer))\b", re.I)),
)


def classify_modality(statement: str, statement_form: str) -> tuple[str, str]:
    """Propose a modality. Returns ``(modality, basis)``.

    ``basis`` records why, so the review UI can show the reasoning and the
    reviewer can overrule it with one keystroke.
    """
    for modality, pattern in _CUES:
        if (m := pattern.search(statement)):
            return modality, f"lexical cue: '{m.group(0).lower()}'"

    # A bare imperative with no modal cue. The corpus convention on normative
    # pages is a direct instruction, which reads as MUST — but this is the
    # genuinely ambiguous case and is flagged as such for review.
    if statement_form == "negative_imperative":
        return Modality.MUST_NOT, "bare negative imperative (ambiguous: MUST_NOT vs SHOULD_NOT)"
    if statement_form == "imperative":
        return Modality.MUST, "bare imperative (ambiguous: MUST vs SHOULD)"
    return Modality.SHOULD, "no cue; defaulted"


def default_severity(modality: str) -> str:
    return _SEVERITY.get(modality, "warning")
