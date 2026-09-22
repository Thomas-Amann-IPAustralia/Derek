"""Build the rule ledger from the corpus snapshot.

    python -m derek.extract.build [--check] [--ledger PATH]

Deterministic end to end: corpus in, ledger out, no model calls. Every entry
lands as ``review_status: proposed`` and must be accepted by a human before
the runtime will load it (ADR-008).

``--check`` runs the build and fails if the on-disk ledger would change,
which is how CI proves the "two runs, same rules" requirement.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import (
    COMPLIANT_EXAMPLE_HEADINGS, VIOLATING_EXAMPLE_HEADINGS, NormalisedPage,
)
from derek.extract.candidates import Candidate, extract_candidates
from derek.extract.modality import classify_modality
from derek.ledger.model import (
    Clarity, Derivation, Detection, Direction, ReviewStatus, Rule, Source, Unit,
    body_excerpt,
)
from derek.ledger.reconcile import reconcile
from derek.ledger.store import load_ledger, write_ledger

EXTRACTOR_VERSION = "1.0.0"

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
SNAPSHOT_LOCK = REPO / "corpus" / "snapshot.lock.json"
DEFAULT_LEDGER = REPO / "ledger" / "rules.jsonl"

def _display(path: Path) -> str:
    """Repo-relative path where possible; absolute otherwise.

    ``--ledger`` accepts any path, including one outside the repository
    (tests use a tmpdir), so this must not assume containment.
    """
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def _url_index() -> dict[str, str]:
    """Map corpus-relative page paths to their Style Manual URLs.

    Read from the snapshot lock, which is the authority on corpus state
    (ADR-001), so a rule's `source.url` always matches the snapshot the
    rule was derived from.
    """
    if not SNAPSHOT_LOCK.exists():
        return {}
    lock = json.loads(SNAPSHOT_LOCK.read_text(encoding="utf-8"))
    return {p: v.get("url", "") for p, v in lock.get("pages", {}).items()}


def collect_candidates() -> tuple[list[Candidate], dict[str, str]]:
    """Extract every candidate from every eligible page, in a stable order."""
    eligibility = load_eligibility(ELIGIBILITY)
    hashes: dict[str, str] = {}
    out: list[Candidate] = []

    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        if not eligibility.decide(rel)[0]:
            continue
        page = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace"))
        hashes[rel] = page.sha256
        out.extend(extract_candidates(rel, page.text))

    out.sort(key=lambda c: (c.page_path, c.line_start, c.uid))
    return out, hashes


def _polarity_seed(cand: Candidate) -> tuple[list[str], list[str]]:
    """Seed compliant/violating examples from the manual's own example blocks.

    ``Write this`` / ``Do this`` / ``Correct`` / ``Like this`` are compliant;
    ``Not this`` / ``Don't do this`` / ``Incorrect`` are violating. This is
    editorially authored, correctly polarised data
    that Octavius ignored in favour of model-generated test strings — the
    root of its polarity inversions (postmortem F1, D-5).

    A bare ``Example`` block is NOT used: it is unlabelled, and guessing its
    polarity is exactly the mistake being guarded against.

    The labels are read from the frozensets in ``derek.corpus.normalise`` rather
    than restated here. They were restated once, and the two drifted: ``like
    this`` counted toward admitting a rule as ``exemplified`` but was not read
    back out, so 79 editorially-authored compliant sentences across 45 rules
    were harvested and silently dropped. A hand-written list of a vocabulary
    that lives somewhere else is that bug waiting to recur.

    Sorted, because a frozenset has no order and Layer 1 output must not depend
    on one (ADR-002).
    """
    compliant = [
        line
        for label in sorted(COMPLIANT_EXAMPLE_HEADINGS)
        for line in cand.examples.get(label, [])
    ]
    violating = [
        line
        for label in sorted(VIOLATING_EXAMPLE_HEADINGS)
        for line in cand.examples.get(label, [])
    ]
    return compliant, violating


def _refresh_gold(rule: Rule, cand: Candidate) -> None:
    """Re-seed a rule's example lists from the corpus.

    The example lists are pipeline-owned: they are not in the review API's
    ``EDITABLE`` whitelist, so the corpus is their only source and a rebuild
    should reproduce them exactly. Keeping a stale copy is how the ledger and
    the manual drift apart silently, which is the class of failure ADR-002
    exists to make impossible.
    """
    rule.compliant_examples, rule.violating_examples = _polarity_seed(cand)


def candidate_to_rule(
    cand: Candidate, url_index: dict[str, str], page_hashes: dict[str, str], now: str
) -> Rule:
    modality, basis = classify_modality(cand.statement, cand.statement_form)
    compliant, violating = _polarity_seed(cand)

    return Rule(
        uid=cand.uid,
        source=Source(
            page_path=cand.page_path,
            heading_path=list(cand.heading_path),
            statement=cand.statement,
            url=url_index.get(cand.page_path, ""),
            body_excerpt=body_excerpt(cand.body),
            snapshot_sha256=page_hashes.get(cand.page_path, ""),
            line_start=cand.line_start,
        ),
        derivation=Derivation(
            method="heading_structure",
            extractor_version=EXTRACTOR_VERSION,
            statement_form=cand.statement_form,
            derived_at=now,
        ),
        modality=modality,
        modality_basis=basis,
        # Every field below is deliberately left at a conservative default.
        # Filling them in is the review task (ADR-008) — the pipeline must
        # not manufacture judgements it has not made.
        clarity=Clarity.UNREVIEWED,
        direction=(
            Direction.PRESENCE
            if cand.statement_form == "negative_imperative"
            else Direction.ABSENCE
        ),
        unit=Unit.SENTENCE,
        compliant_examples=compliant,
        violating_examples=violating,
        detection=Detection(detectable=False, not_detectable_reason="awaiting review"),
    )


def build(ledger_path: Path, check: bool) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidates, page_hashes = collect_candidates()
    url_index = _url_index()
    existing = load_ledger(ledger_path)

    rec = reconcile(candidates, existing)
    print("Reconciliation:", json.dumps(rec.summary(), indent=2))

    merged: dict[str, Rule] = {}

    # Terminal states are retained verbatim across every rebuild. A rule the
    # Style Manual removed, or replaced, is history — "we used to flag this
    # and stopped" is information, and dropping it would make the ledger
    # quietly forget decisions. The reconciler excludes these from matching,
    # so they must be carried forward here or they vanish.
    for rule in existing.values():
        if rule.review.status in (ReviewStatus.ORPHANED, ReviewStatus.SUPERSEDED):
            merged[rule.uid] = rule

    by_uid = {cand.uid: cand for cand in candidates}

    for rule in rec.unchanged:
        # Nothing about the rule changed, but its gold examples are derived
        # data and are refreshed from the corpus like any other derived field.
        _refresh_gold(rule, by_uid[rule.uid])
        merged[rule.uid] = rule
    for old, cand in rec.body_altered:
        # Source text moved under a rule whose statement is unchanged. Keep
        # every human decision; refresh only the provenance.
        old.source.body_excerpt = body_excerpt(cand.body)
        old.source.snapshot_sha256 = page_hashes.get(cand.page_path, "")
        old.source.line_start = cand.line_start
        _refresh_gold(old, cand)
        merged[old.uid] = old
    for old, cand in rec.rehomed:
        # Same rule, new address. Carry every human decision across, refresh
        # provenance, and record the old UID so the change is traceable
        # without pretending the Style Manual was edited.
        migrated = Rule.from_dict({**old.to_dict(), "uid": cand.uid})
        migrated.source.heading_path = list(cand.heading_path)
        migrated.source.page_path = cand.page_path
        migrated.source.body_excerpt = body_excerpt(cand.body)
        migrated.source.snapshot_sha256 = page_hashes.get(cand.page_path, "")
        migrated.source.line_start = cand.line_start
        migrated.source.url = url_index.get(cand.page_path, migrated.source.url)
        migrated.derivation.uid_history = list(old.derivation.uid_history) + [old.uid]
        migrated.derivation.extractor_version = EXTRACTOR_VERSION
        # Gold examples come from the new address's corpus text, not the old
        # one's. They are derived data, so there is nothing here to preserve.
        _refresh_gold(migrated, cand)
        merged[migrated.uid] = migrated

    for old, cand in rec.reworded:
        fresh = candidate_to_rule(cand, url_index, page_hashes, now)
        fresh.derivation.supersedes = old.uid
        old.review.transition("superseded", "derek.extract.build", now,
                              f"reworded upstream; superseded by {fresh.uid}")
        merged[old.uid] = old
        merged[fresh.uid] = fresh
    for cand in rec.added:
        merged[cand.uid] = candidate_to_rule(cand, url_index, page_hashes, now)
    for rule in rec.orphaned:
        if rule.review.status != "orphaned":
            rule.review.transition("orphaned", "derek.extract.build", now,
                                   "source heading no longer present in corpus")
        merged[rule.uid] = rule
    for old, cand in rec.ambiguous:
        fresh = candidate_to_rule(cand, url_index, page_hashes, now)
        fresh.review.note = (
            f"LINEAGE UNRESOLVED: may supersede {old.uid}. Human decision required."
        )
        merged[fresh.uid] = fresh

    if check:
        before = ledger_path.read_bytes() if ledger_path.exists() else b""
        tmp = ledger_path.with_suffix(".check.jsonl")
        write_ledger(tmp, merged.values())
        after = tmp.read_bytes()
        tmp.unlink()
        if before != after:
            print("\nFAIL: rebuilding the ledger would change it.", file=sys.stderr)
            print("The extractor must be a pure function of the corpus (ADR-002).", file=sys.stderr)
            return 1
        print("\nOK: ledger is reproducible from the corpus.")
        return 0

    n = write_ledger(ledger_path, merged.values())
    print(f"\nWrote {n} rules to {_display(ledger_path)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--check", action="store_true",
                    help="fail if rebuilding would change the ledger")
    args = ap.parse_args(argv)
    return build(args.ledger, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
