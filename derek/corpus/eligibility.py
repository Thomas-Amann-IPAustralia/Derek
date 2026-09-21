"""Corpus eligibility: which pages are sources of content rules (ADR-005)."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Eligibility", "load_eligibility", "path_match"]

_ENTRY = re.compile(r"^\s{2}-\s+glob:\s*\"(?P<glob>[^\"]+)\"")
_FLAG = re.compile(r"^\s{4}requires_unit_review:\s*(?P<v>true|false)\s*$")
_SECTION = re.compile(r"^(eligible|excluded):\s*$")


def path_match(path: str, pattern: str) -> bool:
    """Glob match with directory semantics.

    ``fnmatch`` alone is wrong here: its ``*`` crosses ``/``, so a pattern
    meant to catch top-level landing pages (``*.md``) silently matches every
    page in the corpus. Segments are matched individually and ``**`` is the
    only wildcard permitted to span them.
    """
    pat_parts = pattern.split("/")
    path_parts = path.split("/")

    def match(pi: int, si: int) -> bool:
        while pi < len(pat_parts):
            if pat_parts[pi] == "**":
                if pi + 1 == len(pat_parts):
                    return True
                return any(match(pi + 1, k) for k in range(si, len(path_parts) + 1))
            if si >= len(path_parts):
                return False
            if not fnmatch.fnmatch(path_parts[si], pat_parts[pi]):
                return False
            pi += 1
            si += 1
        return si == len(path_parts)

    return match(0, 0)


@dataclass(frozen=True)
class Rule:
    glob: str
    eligible: bool
    requires_unit_review: bool = False


class Eligibility:
    """Path-glob allowlist. Unmatched paths are excluded by default."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def decide(self, rel_path: str) -> tuple[bool, str]:
        """Return ``(eligible, reason_code)`` for a corpus-relative path."""
        # Excluded rules are evaluated first and the most specific match
        # wins, so a broad `*.md` exclusion cannot shadow a nested allow.
        matches = [r for r in self._rules if path_match(rel_path, r.glob)]
        if not matches:
            return False, "unclassified"
        best = max(matches, key=lambda r: (r.glob.count("/"), len(r.glob)))
        return best.eligible, best.glob

    def requires_unit_review(self, rel_path: str) -> bool:
        for r in self._rules:
            if r.eligible and r.requires_unit_review and path_match(rel_path, r.glob):
                return True
        return False


def load_eligibility(path: Path) -> Eligibility:
    """Parse ``corpus/eligibility.yaml``.

    Deliberately parsed with a small hand-written reader rather than PyYAML:
    this module stays stdlib-only so eligibility can be consulted anywhere,
    including from the extraction layer, without pulling in a parser.
    """
    rules: list[Rule] = []
    section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if (m := _SECTION.match(line)):
            section = m.group(1)
            continue
        if (m := _ENTRY.match(line)) and section:
            rules.append(Rule(glob=m.group("glob"), eligible=(section == "eligible")))
            continue
        if (m := _FLAG.match(line)) and rules:
            last = rules[-1]
            rules[-1] = Rule(last.glob, last.eligible, m.group("v") == "true")
    return Eligibility(rules)
