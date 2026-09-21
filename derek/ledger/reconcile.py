"""Reconcile a freshly extracted candidate set against the existing ledger.

This is the layer that satisfies "must correctly identify new rules, rules
which have been altered and rules which have been removed". Octavius could
not do any of the three (postmortem F7).

Nothing here guesses. Lineage is matched by exact and normalised string
equality only; anything that does not match cleanly is surfaced for a human
decision rather than resolved by similarity heuristics, because a wrong
lineage silently transfers a human's acceptance onto a rule they never saw.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from derek.extract.candidates import Candidate, normalise_statement
from derek.ledger.model import Rule, ReviewStatus

__all__ = ["Reconciliation", "reconcile"]


@dataclass
class Reconciliation:
    """The outcome of comparing candidates to the ledger."""

    unchanged: list[Rule] = field(default_factory=list)
    added: list[Candidate] = field(default_factory=list)
    body_altered: list[tuple[Rule, Candidate]] = field(default_factory=list)
    rehomed: list[tuple[Rule, Candidate]] = field(default_factory=list)
    reworded: list[tuple[Rule, Candidate]] = field(default_factory=list)
    orphaned: list[Rule] = field(default_factory=list)
    ambiguous: list[tuple[Rule, Candidate]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "unchanged": len(self.unchanged),
            "added": len(self.added),
            "body_altered": len(self.body_altered),
            "rehomed": len(self.rehomed),
            "reworded": len(self.reworded),
            "orphaned": len(self.orphaned),
            "needs_human_lineage_decision": len(self.ambiguous),
        }

    @property
    def requires_review(self) -> bool:
        """Rehomed rules are deliberately excluded: nothing about them changed
        except our address for them, so there is nothing new to review."""
        return bool(self.added or self.body_altered or self.reworded
                    or self.orphaned or self.ambiguous)


def _address(page_path: str, heading_path) -> tuple[str, str]:
    """Positional address of a rule: page plus its parent heading chain.

    Deliberately excludes the rule's own heading, so a reworded heading in
    an unchanged position is recognisable as the same rule.
    """
    parents = tuple(heading_path)[:-1]
    return page_path, " > ".join(parents)


def reconcile(
    candidates: list[Candidate],
    ledger: dict[str, Rule],
    removed_pages: frozenset[str] = frozenset(),
) -> Reconciliation:
    """Classify each candidate and each existing rule.

    ``removed_pages`` are corpus-relative paths deleted upstream since the
    last snapshot; their rules become ``orphaned`` rather than vanishing.
    """
    result = Reconciliation()
    by_uid = {c.uid: c for c in candidates}

    # Index surviving ledger rules for lineage matching.
    live = {
        uid: r for uid, r in ledger.items()
        if r.review.status not in {ReviewStatus.SUPERSEDED, ReviewStatus.ORPHANED}
    }
    by_address: dict[tuple[str, str], list[Rule]] = {}
    by_statement: dict[str, list[Rule]] = {}
    for rule in live.values():
        by_address.setdefault(_address(rule.source.page_path, rule.source.heading_path), []).append(rule)
        by_statement.setdefault(normalise_statement(rule.source.statement), []).append(rule)

    matched_uids: set[str] = set()

    for cand in candidates:
        existing = live.get(cand.uid)
        if existing is not None:
            matched_uids.add(cand.uid)
            if existing.source.body_excerpt.strip() != cand.body.strip():
                result.body_altered.append((existing, cand))
            else:
                result.unchanged.append(existing)
            continue

        # Identical statement, different UID. The Style Manual did not change
        # a word; our address for the rule changed, because the UID is
        # content-addressed over the heading path and a converter upgrade
        # corrected that path (ADR-020). This is a REHOMING, not a rewording:
        # treating it as a supersession would write 537 fictional upstream
        # edits into the ledger's history and discard the review state of a
        # rule nobody touched.
        same_statement = [
            r for r in by_statement.get(normalise_statement(cand.statement), [])
            if r.uid not in by_uid and r.uid not in matched_uids
        ]
        # The Style Manual repeats some statements verbatim across pages
        # ("Use commas in numbers with 4 or more digits" appears on both
        # commas.md and choosing-numerals-or-words.md). Page path resolves
        # them without guessing: a rule cannot move pages and keep its
        # wording without that being a genuinely new rule on the new page.
        if len(same_statement) > 1:
            on_page = [r for r in same_statement if r.source.page_path == cand.page_path]
            if len(on_page) == 1:
                same_statement = on_page
        if len(same_statement) == 1:
            result.rehomed.append((same_statement[0], cand))
            matched_uids.add(same_statement[0].uid)
            continue
        if len(same_statement) > 1:
            result.ambiguous.append((same_statement[0], cand))
            continue

        # Same position, different wording → the rule was reworded in place.
        siblings = [
            r for r in by_address.get(_address(cand.page_path, cand.heading_path), [])
            if r.uid not in by_uid and r.uid not in matched_uids
        ]
        if len(siblings) == 1:
            result.reworded.append((siblings[0], cand))
            matched_uids.add(siblings[0].uid)
            continue
        if len(siblings) > 1:
            # Several candidates for the same slot. A model could guess; we
            # will not. The reviewer decides which rule this supersedes.
            result.ambiguous.append((siblings[0], cand))
            continue

        result.added.append(cand)

    for uid, rule in live.items():
        if uid in matched_uids or uid in by_uid:
            continue
        if rule.source.page_path in removed_pages or rule.source.page_path not in {
            c.page_path for c in candidates
        }:
            result.orphaned.append(rule)
        else:
            result.orphaned.append(rule)

    return result
