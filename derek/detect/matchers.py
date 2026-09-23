"""Tier 0 matchers: declarative data in, character spans out (ADR-009, ADR-010).

A matcher is a dict from the ledger's ``detection.matcher``, drawn from a closed
vocabulary. ``compile_matcher`` validates it and returns something that finds
spans in plain text. Nothing here evaluates code from the ledger: a pattern is
a regular expression, a term list is a list of strings, and a key this module
does not know is refused rather than ignored. Ignoring it would mean a rule
silently doing less than its record says.

Two methods are implemented, the two ADR-010 puts first:

``regex``
    ``pattern`` (required), ``ignore_case`` (default false).
``literal_set``
    ``terms`` (required, non-empty), ``ignore_case`` (default true), whole
    words only.

Both take the scope keys that make an absence or a pattern rule precise
without code (ADR-006):

``unless``
    Regular expressions tried against the text around a hit (``window``
    characters either side, default 40). A hit any of them matches is not a
    finding. This is how "a 5-digit number" becomes "a 5-digit number that is
    not a phone number or a citation".
``skip_quoted``
    Drop hits inside single quotation marks (‘…’). The Style Manual *mentions*
    a term in quotes when it discusses it ("Don't use the term ‘old people’"),
    and a mention is not a use. That is how a rule ends up flagging the
    sentence that states it, which is the Octavius failure the dogfood gate
    catches (postmortem F4). Default true for ``literal_set``, false for
    ``regex``, whose patterns may need to see quotes (direct speech).

Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["MatcherError", "Matcher", "compile_matcher", "SUPPORTED"]

SUPPORTED = frozenset({"regex", "literal_set"})

_KEYS = {
    "regex": {"pattern", "ignore_case", "unless", "window", "skip_quoted"},
    "literal_set": {"terms", "ignore_case", "unless", "window", "skip_quoted"},
}


class MatcherError(ValueError):
    """A matcher the runtime cannot honour exactly as written."""


@dataclass(frozen=True)
class Matcher:
    method: str
    rx: re.Pattern
    unless: tuple[re.Pattern, ...] = ()
    window: int = 40
    skip_quoted: bool = False
    spec: dict = field(default_factory=dict, compare=False)

    def find(self, text: str) -> list[tuple[int, int]]:
        quoted = _quoted_ranges(text) if self.skip_quoted else []
        out = []
        for m in self.rx.finditer(text):
            a, z = m.span()
            if a == z:
                continue          # an empty match is not a finding
            if quoted and any(qa <= a and z <= qz for qa, qz in quoted):
                continue
            if self.unless:
                ctx = text[max(0, a - self.window):min(len(text), z + self.window)]
                if any(u.search(ctx) for u in self.unless):
                    continue
            out.append((a, z))
        return out


# A mention in single quotes. The closing mark must not be an apostrophe inside
# a word (don’t, manager’s), so it has to be followed by something that is not a
# letter. Double quotes are left alone: the manual uses single quotes for
# mentions, and double quotes only inside quoted speech.
_QUOTED = re.compile(r"‘[^‘’\n]{1,120}?’(?![A-Za-z])")


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _QUOTED.finditer(text)]


def _compile(pattern: str, flags: int, what: str) -> re.Pattern:
    if not isinstance(pattern, str) or not pattern:
        raise MatcherError(f"{what} must be a non-empty string")
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise MatcherError(f"{what} does not compile: {exc}") from exc


def compile_matcher(method: str, spec: dict) -> Matcher:
    """Validate a declarative matcher and build it. Raises MatcherError."""
    if method not in SUPPORTED:
        raise MatcherError(f"method {method!r} is not evaluable at Tier 0 "
                           f"(supported: {sorted(SUPPORTED)})")
    if not isinstance(spec, dict):
        raise MatcherError("matcher must be an object")
    unknown = set(spec) - _KEYS[method]
    if unknown:
        raise MatcherError(f"unknown matcher key(s) for {method}: {sorted(unknown)}")

    default_case = method == "literal_set"
    flags = re.IGNORECASE if spec.get("ignore_case", default_case) else 0
    if method == "regex":
        rx = _compile(spec.get("pattern"), flags, "pattern")
    else:
        terms = spec.get("terms")
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) and t for t in terms):
            raise MatcherError("terms must be a non-empty list of strings")
        # Longest first, so "old people" is tried before "old".
        alts = "|".join(re.escape(t) for t in sorted(set(terms), key=lambda t: (-len(t), t)))
        rx = re.compile(rf"(?<![\w’'-])(?:{alts})(?![\w-])", flags)

    unless = spec.get("unless", [])
    if not isinstance(unless, list):
        raise MatcherError("unless must be a list of patterns")
    window = spec.get("window", 40)
    if not isinstance(window, int) or not 0 <= window <= 200:
        raise MatcherError("window must be an integer from 0 to 200")
    skip = spec.get("skip_quoted", method == "literal_set")
    if not isinstance(skip, bool):
        raise MatcherError("skip_quoted must be true or false")

    return Matcher(
        method=method, rx=rx,
        unless=tuple(_compile(u, flags, "an unless pattern") for u in unless),
        window=window, skip_quoted=skip, spec=dict(spec),
    )
