"""Ledger persistence: JSONL in git (ADR-008).

Not a database. Every decision is a reviewable diff, attributable and
revertable, and survives the review tool being rewritten.

Entries are written in a canonical form — sorted keys, stable ordering by
uid, one entry per line — so that a re-run with no semantic change produces
no diff. This is what makes "re-running over an unchanged corpus is a no-op"
(ADR-003) observable rather than merely claimed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from derek.ledger.model import Rule, ReviewStatus

__all__ = ["load_ledger", "write_ledger", "iter_ledger", "LedgerError"]


class LedgerError(RuntimeError):
    pass


def iter_ledger(path: Path) -> Iterator[Rule]:
    """Stream rules from a ledger file."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield Rule.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                raise LedgerError(f"{path}:{lineno}: {exc}") from exc


def load_ledger(path: Path) -> dict[str, Rule]:
    """Load a ledger into a uid-keyed dict, rejecting duplicate uids."""
    rules: dict[str, Rule] = {}
    for rule in iter_ledger(path):
        if rule.uid in rules:
            raise LedgerError(f"duplicate uid in {path}: {rule.uid}")
        rules[rule.uid] = rule
    return rules


def write_ledger(path: Path, rules: Iterable[Rule]) -> int:
    """Write rules in canonical form. Returns the number written."""
    ordered = sorted(rules, key=lambda r: (r.source.page_path, r.source.line_start, r.uid))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as fh:
        for rule in ordered:
            fh.write(json.dumps(rule.to_dict(), sort_keys=True, ensure_ascii=False))
            fh.write("\n")
            n += 1
    tmp.replace(path)
    return n


def loadable_rules(path: Path) -> list[Rule]:
    """The rules the runtime may execute: accepted/amended and detectable."""
    return [r for r in iter_ledger(path) if r.loadable]


def summarise(path: Path) -> dict[str, int]:
    """Counts by review status, for CI reporting."""
    counts = {s: 0 for s in sorted(ReviewStatus.ALL)}
    for rule in iter_ledger(path):
        counts[rule.review.status] = counts.get(rule.review.status, 0) + 1
    return counts
