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
from derek.extract.golden import (
    GOLD_COMPLIANT, GOLD_VIOLATING, golden_candidates, load_golden,
)
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
GOLDEN_SPANS = REPO / "golden" / "spans.jsonl"
GOLDEN_PAGES = REPO / "golden" / "pages.jsonl"
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


def collect_candidates() -> tuple[list[Candidate], dict[str, str], set[str]]:
    """Extract every candidate from every eligible page, in a stable order.

    A pure function of the corpus and its two declared inputs:
    ``corpus/eligibility.yaml``, which says which pages are rule sources
    (ADR-005), and ``golden/spans.jsonl``, which says which text a human marked
    as a rule (ADR-023). No model runs and no model decides a rule exists (D-7).

    Two modes, per page:

    * **Union** — the default. The heading walk's candidates plus the golden
      spans, with a golden span winning any uid collision, because a span that
      covers a heading exactly *is* that candidate, confirmed, and carries the
      human's tags.
    * **Authoritative** — once a human has swept the page. The golden set is the
      whole inventory, and a heading candidate no span confirms is not a rule.
      That absence is the negative evidence the golden set exists to produce; the
      reconciler turns the dropped candidates into ``orphaned``, so nothing is
      deleted and their review history survives.
    """
    eligibility = load_eligibility(ELIGIBILITY)
    golden = load_golden(GOLDEN_SPANS, GOLDEN_PAGES, eligibility)
    hashes: dict[str, str] = {}
    out: list[Candidate] = []

    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        if not eligibility.decide(rel)[0]:
            continue
        page = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace"))
        hashes[rel] = page.sha256

        gold = golden_candidates(rel, page.text, golden.spans.get(rel, []))
        if rel in golden.authoritative:
            out.extend(gold)
            continue
        merged = {c.uid: c for c in extract_candidates(rel, page.text)}
        merged.update({c.uid: c for c in gold})
        out.extend(merged.values())

    out.sort(key=lambda c: (c.page_path, c.line_start, c.uid))
    return out, hashes, golden.authoritative


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
    # Examples a human attached to a rule span (ADR-023). They arrive under keys
    # that cannot collide with a heading label, so the manual's own testimony and
    # a reviewer's stay distinguishable, and they are appended rather than
    # merged in so the manual's comes first where a rule has both.
    compliant += cand.examples.get(GOLD_COMPLIANT, [])
    violating += cand.examples.get(GOLD_VIOLATING, [])
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
            method="human_span" if cand.origin == "golden" else "heading_structure",
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
        # Preconditions ride with the candidate for the same reason the examples
        # do: they come from the corpus (a span) or from the golden record, not
        # from the review API, so a rebuild reproduces them.
        context_preconditions=list(cand.preconditions),
        compliant_examples=compliant,
        violating_examples=violating,
        detection=Detection(detectable=False, not_detectable_reason="awaiting review"),
    )


def build(ledger_path: Path, check: bool) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidates, page_hashes, authoritative = collect_candidates()
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
        # Nothing a human decided changed, but the derived fields are refreshed
        # from the candidate like any other pipeline-owned data. `method` matters
        # here beyond tidiness: a candidate the extractor proposed and a candidate
        # a human confirmed by drawing a span over it have the same uid by design
        # (ADR-023), and `derivation.method` is the only thing in the record that
        # can tell them apart.
        cand = by_uid[rule.uid]
        _refresh_gold(rule, cand)
        rule.derivation.method = (
            "human_span" if cand.origin == "golden" else rule.derivation.method)
        rule.context_preconditions = list(cand.preconditions) or rule.context_preconditions
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
        swept = rule.source.page_path in authoritative
        already_judged = swept and rule.review.status == ReviewStatus.REJECTED
        if rule.review.status != ReviewStatus.ORPHANED and not already_judged:
            # Two different things end up here and they must not claim to be the
            # same. On a swept page the heading is still in the corpus; what
            # happened is that a human read the page and did not mark it as a
            # rule, which is a judgement and the whole output of ADR-023. Saying
            # "no longer present" there would be false.
            rule.review.transition(
                "orphaned", "derek.extract.build", now,
                "not marked as a rule in the golden set for this page"
                if swept else "source heading no longer present in corpus")
        # A reviewer who rejected this candidate and said why is left alone.
        # Rejection and orphaning agree on the outcome — the rule does not load —
        # and "we binned it because it labels a section rather than stating a
        # rule" is the useful output of the round, where "not marked in the
        # golden set" is a restatement of the input. Every other verdict
        # (accepted, amended, deferred) DISAGREES with the sweep, so the sweep
        # wins there and the disagreement stays visible in the history.
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
