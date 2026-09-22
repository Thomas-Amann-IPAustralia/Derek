"""Tests for the review UI's guard rails.

The review tool is where a human gates the runtime
([ADR-008](../docs/02-decisions.md#adr-008-human-acceptance-is-a-gate-not-a-review-queue)),
so its guard rails are as load-bearing as anything in the pipeline. Three of
them in particular:

* **No unexplained option.** Every value a reviewer can pick must be
  documented in `glossary.json`. A button nobody explained is a decision made
  on a guess, and a guess recorded as a judgement is exactly how Octavius
  accumulated 3,114 rows nobody could defend.
* **The reviewer cannot touch provenance.** `uid`, `source` and `derivation`
  are the pipeline's; a rebuild must never clobber a human decision and a
  human must never be able to corrupt a rule's lineage.
* **Scope is not optional.** Round 1 exists to establish `unit` and `clarity`.
  A UI that let someone swipe past them would be a faster way of producing the
  same unreviewed pile.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from derek.extract.modality import Modality          # noqa: E402
from derek.ledger.model import (                     # noqa: E402
    Clarity, Derivation, Direction, ReviewStatus, Rule, Source, Unit,
)


def _load_server():
    """Import tools/review/server.py, which is not on a package path."""
    spec = importlib.util.spec_from_file_location(
        "derek_review_server", REPO / "tools" / "review" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = _load_server()


def a_rule(**over) -> Rule:
    return Rule(
        uid="0" * 16,
        source=Source(page_path="p.md", heading_path=["A", "B"], statement="Use commas"),
        derivation=Derivation(statement_form="imperative"),
        **over,
    )


# ---------------------------------------------------------------------------
# Every option a reviewer can pick is explained
# ---------------------------------------------------------------------------

def test_glossary_covers_every_vocabulary_value():
    """load_glossary raises SystemExit rather than serving an unlabelled button."""
    glossary = server.load_glossary()          # the assertion is inside
    assert glossary["buckets"]

    for bucket, vocabulary in (
        ("review_status", ReviewStatus.ALL),
        ("unit", Unit.ALL),
        ("clarity", Clarity.ALL),
        ("direction", Direction.ALL),
        ("modality", frozenset(Modality.ALL)),
    ):
        assert set(glossary["buckets"][bucket]["options"]) == set(vocabulary), bucket


def test_every_explained_option_actually_explains_something():
    glossary = server.load_glossary()
    thin = []
    for bucket, spec in glossary["buckets"].items():
        for key, opt in spec["options"].items():
            if not opt.get("label") or not opt.get("means"):
                thin.append(f"{bucket}.{key}: no label or no meaning")
            elif not opt.get("system_only") and not opt.get("effect"):
                thin.append(f"{bucket}.{key}: does not say what it does to the data")
    assert not thin, "an option a reviewer can pick must say what picking it does:\n  " + "\n  ".join(thin)


def test_reviewer_is_never_offered_a_pipeline_owned_status():
    """quarantined / superseded / orphaned / proposed are the pipeline's."""
    offered = set(server.reviewer_options(server.load_glossary())["review_status"])
    assert offered == set(server.REVIEWER_STATUSES)
    assert not offered & {
        ReviewStatus.QUARANTINED, ReviewStatus.SUPERSEDED,
        ReviewStatus.ORPHANED, ReviewStatus.PROPOSED,
    }


# ---------------------------------------------------------------------------
# The reviewer cannot corrupt provenance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["uid", "source", "derivation", "uid_history", "confidence"])
def test_pipeline_owned_fields_are_rejected(field):
    with pytest.raises(ValueError, match="not editable"):
        server._apply(a_rule(), {field: "anything"}, "TA")


def test_pipeline_only_statuses_are_rejected():
    for status in (ReviewStatus.QUARANTINED, ReviewStatus.SUPERSEDED,
                   ReviewStatus.ORPHANED, ReviewStatus.PROPOSED):
        with pytest.raises(ValueError, match="not settable"):
            server._apply(a_rule(), {"review_status": status}, "TA")


@pytest.mark.parametrize("patch", [
    {"unit": "paragraphs"}, {"clarity": "clear"},
    {"direction": "both"}, {"modality": "MAYBE"},
])
def test_values_outside_the_vocabulary_are_rejected(patch):
    with pytest.raises(ValueError, match="unknown"):
        server._apply(a_rule(), patch, "TA")


# ---------------------------------------------------------------------------
# Scope is not optional
# ---------------------------------------------------------------------------

def test_a_rule_cannot_be_kept_without_clarity():
    rule = a_rule()
    assert rule.clarity == Clarity.UNREVIEWED
    with pytest.raises(ValueError, match="set clarity"):
        server._apply(rule, {"review_status": ReviewStatus.ACCEPTED}, "TA")
    assert rule.review.status == ReviewStatus.PROPOSED


def test_an_interpretation_has_to_be_written_down():
    """ADR-017: an assumption nobody recorded is indistinguishable from a reading."""
    rule = a_rule()
    with pytest.raises(ValueError, match="write it down"):
        server._apply(rule, {
            "review_status": ReviewStatus.ACCEPTED,
            "clarity": Clarity.AMBIGUOUS_RESOLVABLE,
        }, "TA")

    rule = a_rule()
    server._apply(rule, {
        "review_status": ReviewStatus.ACCEPTED,
        "clarity": Clarity.AMBIGUOUS_RESOLVABLE,
        "specification": "flag sentences over 25 words",
    }, "TA")
    assert rule.review.status == ReviewStatus.ACCEPTED
    assert rule.disambiguation_log, "the assumption must be logged, not just noted"
    assert rule.disambiguation_log[0]["by"] == "TA"
    assert rule.disambiguation_log[0]["assumption"] == "flag sentences over 25 words"


def test_an_interpretation_in_the_note_alone_is_refused():
    """A note is commentary; `specification` is what detection implements.

    `Rule.effective_statement` returns ``specification or source.statement``, so
    an interpretation recorded only in the note leaves the detector matching the
    ambiguous original wording — a rule that does not do what its record says,
    which is the Octavius shape. The schema agrees: `ambiguous_resolvable`
    requires `specification`. Four decisions landed through the older, laxer
    check and made the ledger fail its own schema.
    """
    rule = a_rule()
    with pytest.raises(ValueError, match="your interpretation"):
        server._apply(rule, {
            "review_status": ReviewStatus.ACCEPTED,
            "clarity": Clarity.AMBIGUOUS_RESOLVABLE,
            "note": "assumed 'short' means under 25 words",
        }, "TA")
    assert rule.review.status == ReviewStatus.PROPOSED
    assert not rule.disambiguation_log


def test_every_resolved_ambiguity_in_the_ledger_carries_its_specification():
    """The schema's conditional, asserted against the real ledger.

    `tests/test_invariants.py` checks this too, from the schema side. This one
    names the gate that has to hold it: `server._apply`.
    """
    from derek.ledger.store import load_ledger
    ledger = Path(__file__).resolve().parents[1] / "ledger" / "rules.jsonl"
    for rule in load_ledger(ledger).values():
        if rule.clarity == Clarity.AMBIGUOUS_RESOLVABLE:
            assert rule.specification, rule.uid
            assert rule.disambiguation_log, rule.uid


def test_rejecting_needs_no_scope_but_records_the_reasons():
    rule = a_rule()
    server._apply(rule, {
        "review_status": ReviewStatus.REJECTED,
        "unit": Unit.ARTIFACT, "clarity": Clarity.NOT_AUTOMATABLE,
        "reasons": ["not_text"], "note": "governs a video",
    }, "TA")
    assert rule.review.status == ReviewStatus.REJECTED
    assert "not_text" in rule.review.note
    assert not rule.loadable


def test_a_kept_rule_still_does_not_load():
    """Keeping is not shipping: a matcher and a passing gate come first."""
    rule = a_rule()
    server._apply(rule, {
        "review_status": ReviewStatus.ACCEPTED, "clarity": Clarity.UNAMBIGUOUS,
        "unit": Unit.SENTENCE,
    }, "TA")
    assert rule.review.status == ReviewStatus.ACCEPTED
    assert not rule.loadable, "no detection method yet — nothing should load"


# ---------------------------------------------------------------------------
# Scoring cannot be farmed
# ---------------------------------------------------------------------------

def test_a_hasty_decision_is_marked_in_the_ledger():
    rule = a_rule()
    server._apply(rule, {
        "review_status": ReviewStatus.DEFERRED, "elapsed_ms": 200,
    }, "TA")
    assert "(hasty)" in rule.review.note


def test_a_hasty_decision_scores_nothing():
    rules = {}
    for i, elapsed in enumerate((200, 9000)):
        rule = a_rule()
        rule.uid = f"{i:016d}"
        server._apply(rule, {"review_status": ReviewStatus.DEFERRED, "elapsed_ms": elapsed}, "TA")
        rules[rule.uid] = rule
    board = server.leaderboard(rules, "all")["board"]
    entry = next(e for e in board if e["initials"] == "TA")
    assert entry["decisions"] == 2
    assert entry["hasty"] == 1
    assert entry["score"] == server.POINTS["decision"], "only the considered one should score"


def test_undo_does_not_score_as_work():
    rule = a_rule()
    server._apply(rule, {"review_status": ReviewStatus.ACCEPTED,
                         "clarity": Clarity.UNAMBIGUOUS, "elapsed_ms": 9000}, "TA")
    rule.review.transition(ReviewStatus.PROPOSED, "TA", "2026-09-21T00:00:00+00:00", "undone")
    entry = next(e for e in server.leaderboard({rule.uid: rule}, "all")["board"]
                 if e["initials"] == "TA")
    assert entry["decisions"] == 1, "the revert should not count as a second decision"


def test_undo_is_recorded_rather_than_erased():
    rule = a_rule()
    server._apply(rule, {"review_status": ReviewStatus.REJECTED,
                         "reasons": ["duplicate"]}, "TA")
    rule.review.transition(ReviewStatus.PROPOSED, "TA", "2026-09-21T00:00:00+00:00", "undone by TA")
    assert rule.review.status == ReviewStatus.PROPOSED
    assert len(rule.review.history) == 2, "the original decision stays on the record"
    assert rule.review.history[0]["to"] == ReviewStatus.REJECTED


# ---------------------------------------------------------------------------
# Inter-reviewer agreement
# ---------------------------------------------------------------------------

def test_agreement_counts_only_rules_two_people_decided():
    solo = a_rule(); solo.uid = "1" * 16
    server._apply(solo, {"review_status": ReviewStatus.DEFERRED}, "TA")

    shared = a_rule(); shared.uid = "2" * 16
    server._apply(shared, {"review_status": ReviewStatus.DEFERRED}, "TA")
    server._apply(shared, {"review_status": ReviewStatus.DEFERRED}, "JW")

    split = a_rule(); split.uid = "3" * 16
    server._apply(split, {"review_status": ReviewStatus.DEFERRED}, "TA")
    server._apply(split, {"review_status": ReviewStatus.REJECTED, "reasons": ["duplicate"]}, "JW")

    got = server.agreement({r.uid: r for r in (solo, shared, split)})
    assert got["double_reviewed"] == 2
    assert got["agreed"] == 1
    assert got["rate"] == 50


# ---------------------------------------------------------------------------
# Attention checks must be answerable and graded server-side
# ---------------------------------------------------------------------------

def test_attention_check_never_leaks_its_answer():
    from derek.ledger.store import load_ledger
    rules = load_ledger(REPO / "ledger" / "rules.jsonl")
    glossary = server.load_glossary()
    for _ in range(30):
        q = server.make_attention_check(rules, glossary)
        assert "answer" not in q and "expected" not in q and "correct" not in q
        assert q["choices"] and q["nonce"]


def test_attention_check_is_graded_once_and_only_once():
    from derek.ledger.store import load_ledger
    rules = load_ledger(REPO / "ledger" / "rules.jsonl")
    q = server.make_attention_check(rules, server.load_glossary())
    server.ACTIVITY = REPO / "ledger" / ".pytest_activity.jsonl"
    try:
        first = server.grade_attention_check(q["nonce"], q["choices"][0]["key"], "TA")
        assert first["ok"] is True
        replay = server.grade_attention_check(q["nonce"], q["choices"][0]["key"], "TA")
        assert replay["ok"] is False, "a nonce must not be gradeable twice"
    finally:
        server.ACTIVITY.unlink(missing_ok=True)
        server.ACTIVITY = REPO / "ledger" / "review_activity.jsonl"


def test_polarity_checks_only_use_rules_whose_wording_states_the_rule():
    """"Does this follow the rule 'Centuries'?" has no answer.

    Headings admitted on their examples alone are usually topic labels
    (docs/07), so asking about them measures nothing and punishes the reviewer
    for the extractor's shape.
    """
    from derek.ledger.store import load_ledger
    rules = load_ledger(REPO / "ledger" / "rules.jsonl")
    glossary = server.load_glossary()
    by_statement = {r.source.statement: r for r in rules.values()}
    for _ in range(60):
        q = server.make_attention_check(rules, glossary)
        if q["kind"] != "polarity":
            continue
        rule = by_statement[q["rule"]]
        assert rule.derivation.statement_form != "exemplified"
        assert len(q["subject"]) >= 18, f"unanswerably short example: {q['subject']!r}"
