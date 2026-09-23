"""Tier 0 detection: declarative matchers, plain-text documents, and the adoption gate.

The invariants under test: nothing from the ledger is executed (D-11), only an
accepted rule runs (D-10), a finding's confidence is None until calibrated
(D-12), detectors see no markup (D-13), and a matcher reaches the ledger only
when its rule's own examples agree and the manual's prose stays within budget
(ADR-004, ADR-011), by a named human.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from derek.corpus.normalise import NormalisedPage
from derek.detect import proposals as props
from derek.detect.document import Document
from derek.detect.engine import check_examples, detect, load
from derek.detect.matchers import MatcherError, compile_matcher
from derek.ledger.model import Detection
from derek.ledger.store import load_ledger, write_ledger

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "ledger" / "rules.jsonl"
PAGES = REPO / "corpus" / "pages"
PRONOUNS = "grammar-punctuation-and-conventions/types-words/pronouns.md"
LATIN = "c99b24f6e85c5c4a"   # Don't use commas with Latin shortened forms


# ---------------------------------------------------------------------------
# Matchers are data (D-11)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,spec,why", [
    ("regex", {"pattern": "a", "exec": "print(1)"}, "unknown matcher key"),
    ("regex", {"pattern": "("}, "does not compile"),
    ("regex", {}, "non-empty string"),
    ("literal_set", {"terms": []}, "non-empty list"),
    ("structural_predicate", {"name": "x"}, "not evaluable at Tier 0"),
    ("regex", {"pattern": "a", "unless": "b"}, "list of patterns"),
])
def test_a_matcher_outside_the_vocabulary_is_refused(method, spec, why):
    with pytest.raises(MatcherError, match=why):
        compile_matcher(method, spec)


def test_a_term_list_matches_whole_words_longest_first():
    m = compile_matcher("literal_set", {"terms": ["old", "old people"], "skip_quoted": False})
    text = "Older people and old people and bold people."
    assert [text[a:z] for a, z in m.find(text)] == ["old people"]


def test_a_quoted_mention_is_not_a_use():
    """The manual discusses a term in quotes; that is not the rule being broken (F4)."""
    m = compile_matcher("literal_set", {"terms": ["old people"]})
    assert m.find("Don’t use the term ‘old people’. It is disrespectful.") == []
    text = "The program helps old people."
    assert [text[a:z] for a, z in m.find(text)] == ["old people"]
    # An apostrophe is not a closing quote.
    assert m.find("The manager’s old people programme") != []


def test_unless_scopes_a_pattern_without_code():
    m = compile_matcher("regex", {"pattern": r"\b\d{5,}\b", "unless": [r"\+\d"], "window": 10})
    assert m.find("Call +61 491570159 today") == []
    assert m.find("We received 125000 enquiries") == [(12, 18)]


def test_an_empty_match_is_not_a_finding():
    assert compile_matcher("regex", {"pattern": r"x*"}).find("abc") == []


# ---------------------------------------------------------------------------
# The document model (ADR-012)
# ---------------------------------------------------------------------------

def _page_doc(rel: str) -> Document:
    return Document.from_page(rel, NormalisedPage(rel, (PAGES / rel).read_text(encoding="utf-8")).text)


@pytest.mark.parametrize("rel", sorted(str(p.relative_to(PAGES)) for p in PAGES.rglob("*.md"))[::17])
def test_every_block_is_a_slice_of_the_text(rel):
    doc = _page_doc(rel)
    assert all(doc.text[b.start:b.end] == b.text for b in doc.blocks)
    assert "](" not in doc.text and "**" not in doc.text, "detectors see no markup (D-13)"


def test_plain_text_blocks_are_slices_too():
    text = "One para.\n\nTwo, with a comma.\n\n\n\nThree."
    doc = Document.from_text(text)
    assert [b.text for b in doc.blocks] == ["One para.", "Two, with a comma.", "Three."]
    assert all(doc.text[b.start:b.end] == b.text for b in doc.blocks)


def test_the_manuals_wrong_examples_are_not_linted_but_the_rules_after_them_are():
    doc = _page_doc(PRONOUNS)
    off = {b.text for b in doc.blocks if not b.lintable}
    assert "The manager emailed myself." in off
    rule = next(b for b in doc.blocks if b.text.startswith("Don’t use a reflexive pronoun if"))
    assert rule.lintable, "prose under a label heading is prose, not an example"


# ---------------------------------------------------------------------------
# The engine (D-10, D-12)
# ---------------------------------------------------------------------------

def _latin():
    """The Latin-forms rule, with its state set here rather than read from review.

    The live ledger is what reviewers change, so a test that relied on this
    rule staying accepted, or on its examples staying as marked, would fail the
    day someone did their job.
    """
    rule = load_ledger(LEDGER)[LATIN]
    rule.review.status = "accepted"
    rule.compliant_examples = ["Exports of rare earths (e.g. lithium, europium) have soared."]
    rule.violating_examples = ["Exports of rare earths (e.g., lithium and europium) have soared."]
    return rule


def _with_matcher(rule, pattern=r"\b(?:e\.g|i\.e)\.,"):
    rule.detection = Detection(tier=0, method="regex", matcher={"pattern": pattern}, detectable=True)
    return rule


def test_only_an_accepted_rule_runs_and_confidence_is_never_invented():
    rules = load_ledger(LEDGER)
    latin = _with_matcher(_latin())
    proposed = next(r for r in rules.values() if r.review.status == "proposed")
    _with_matcher(proposed, r"soared")
    loaded = load([latin, proposed])
    assert [r.uid for r, _ in loaded.rules] == [LATIN]

    [f] = detect(Document.from_text("Rare earths (e.g., lithium) have soared."), loaded)
    assert f.quote == "e.g.," and f.rule_uid == LATIN
    assert f.confidence is None, "D-12: uncalibrated confidence is null, never a number"
    assert f.severity == "warning"


def test_a_grouped_example_is_not_matched_across_its_join():
    m = compile_matcher("regex", {"pattern": r"for example:\nred"})
    assert check_examples(m, [], ["Some colours, for example:\nred"]).missed


# ---------------------------------------------------------------------------
# Proposals and adoption
# ---------------------------------------------------------------------------

def test_every_proposal_is_data_and_brings_no_examples_of_its_own():
    """D-1: a matcher is judged on the rule's examples, never on its own."""
    rows = props.load_proposals()
    assert rows
    for row in rows:
        compile_matcher(row["method"], row["matcher"])
        assert not {"compliant_examples", "violating_examples", "examples"} & set(row), row["uid"]
        assert row.get("proposed_by"), "say who drafted it"
        if row.get("expected_density"):
            assert row.get("density_justification"), row["uid"]


def _one(rule, **proposal):
    base = {"uid": rule.uid, "method": "regex", "matcher": {"pattern": r"\b(?:e\.g|i\.e)\.,"},
            "expected_density": 0.0, "_source": "test"}
    base.update(proposal)
    [c] = props.check([base], {rule.uid: rule}, docs=[("t", Document.from_text(
        "Plain compliant prose, e.g. this sentence, with nothing wrong in it."))], words=1000)
    return c


def test_a_matcher_with_nothing_to_catch_is_blocked():
    """A harness with no violating example passes anything (postmortem F4)."""
    rule = _latin()
    rule.violating_examples = []
    c = _one(rule)
    assert not c.ready and any("no violating example" in b for b in c.blockers)


def test_a_matcher_that_misses_its_violating_example_is_blocked():
    rule = _latin()
    c = _one(rule, matcher={"pattern": r"viz\.,"})
    assert any("do not fire" in b for b in c.blockers)


def test_a_matcher_over_budget_on_the_manual_is_blocked():
    rule = _latin()
    c = _one(rule, matcher={"pattern": r"\b(?:e\.g|i\.e)\.,?"})
    assert c.findings == 1 and any("over its budget" in b for b in c.blockers)
    ok = _one(rule, matcher={"pattern": r"\b(?:e\.g|i\.e)\.,?"}, expected_density=20.0,
              density_justification="test")
    assert not any("over its budget" in b for b in ok.blockers)


def test_adoption_is_by_a_named_human_and_the_gate_then_runs_it(tmp_path):
    ledger = tmp_path / "rules.jsonl"
    rules = load_ledger(LEDGER)
    rules[LATIN] = rule = _latin()
    write_ledger(ledger, rules.values())
    c = _one(rule)
    assert c.ready, c.blockers
    before = len(rule.review.history)

    assert props.adopt([LATIN], "TA", ledger=ledger, checks=[c]) == 1
    got = load_ledger(ledger)[LATIN]
    assert got.detection.detectable and got.detection.tier == 0 and got.detection.method == "regex"
    assert got.validation.examples_pass is True and got.validation.status == "pass"
    assert got.review.status == rule.review.status, "adoption does not change the verdict"
    assert len(got.review.history) == before + 1 and got.review.history[-1]["by"] == "TA"

    from derek.eval.dogfood import _derek_matcher
    fn = _derek_matcher(json.loads(json.dumps(got.to_dict())))
    assert fn(Document.from_text("See e.g., this.")) == 1


def test_a_blocked_proposal_cannot_be_adopted(tmp_path):
    ledger = tmp_path / "rules.jsonl"
    rules = load_ledger(LEDGER)
    rules[LATIN] = rule = _latin()
    write_ledger(ledger, rules.values())
    rule.violating_examples = []
    c = _one(rule)
    assert props.adopt([LATIN], "TA", ledger=ledger, checks=[c]) == 0
    assert not load_ledger(ledger)[LATIN].detection.detectable
