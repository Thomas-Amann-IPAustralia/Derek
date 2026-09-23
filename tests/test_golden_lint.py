"""The golden-set lint: each check fires on the shape it names, and only that.

Built on throwaway golden sets and ledgers rather than the committed ones. The
committed golden set is exactly what the lint exists to get *changed*, so a test
pinned to today's findings would fail the day a reviewer fixes one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from derek.eval import golden_lint
from derek.eval.golden_lint import _example_blocks, lint
from derek.extract.blocks import parse_blocks
from derek.extract.build import candidate_to_rule
from derek.extract.golden import GoldenSet, Span, golden_candidates, span_id, write_golden
from derek.ledger.store import write_ledger

from tests.test_golden import PAGE, page_text

PRONOUNS = "grammar-punctuation-and-conventions/types-words/pronouns.md"


@pytest.fixture(scope="module")
def blocks():
    return parse_blocks(PAGE, page_text())


def _span(block, start=None, end=None, *, kind="rule", of="", page=PAGE, pre=()):
    start = 0 if start is None else start
    end = len(block.plain) if end is None else end
    return Span(
        span_id=span_id(page, block.id, start, end, kind), kind=kind, page_path=page,
        page_sha256="", block_id=block.id, start=start, end=end,
        quote=block.plain[start:end], of=of, preconditions=tuple(pre),
        tags={"review_status": "accepted"} if kind == "rule" else {},
        by="TA", at="2026-09-23T00:00:00Z")


def _find(blocks, text, kind=None):
    return next(b for b in blocks if b.plain.startswith(text) and (kind is None or b.kind == kind))


def _run(tmp_path, spans, *, swept=False, page=PAGE, **fields):
    """Write a golden set and a ledger in which every rule span is accepted.

    ``fields`` maps a statement prefix to the ledger fields that rule should have,
    standing in for what the reviewer's tags would have set through _apply.
    """
    gs = GoldenSet(spans={page: spans})
    if swept:
        gs.swept[page] = {"page_path": page, "status": "complete", "by": "TA"}
    sp, pp = tmp_path / "spans.jsonl", tmp_path / "pages.jsonl"
    write_golden(gs, sp, pp)

    text = page_text(page)
    rules = {}
    for cand in golden_candidates(page, text, spans):
        rule = candidate_to_rule(cand, {}, {}, "2026-09-23T00:00:00+00:00")
        rule.review.status = "accepted"
        rule.clarity = "unambiguous"
        rule.modality = "SHOULD"
        rule.direction = "absence"
        rule.violation_condition = "something a checker can flag"
        for prefix, values in fields.get("rules", {}).items():
            if rule.source.statement.startswith(prefix):
                for k, v in values.items():
                    setattr(rule, k, v)
        rules[rule.uid] = rule
    ledger = tmp_path / "rules.jsonl"
    write_ledger(ledger, rules.values())
    return lint(ledger, sp, pp, cross_page=False)


def _codes(findings):
    return sorted({f.code for f in findings})


# ---------------------------------------------------------------------------

def test_an_unswept_page_is_a_fix_and_a_swept_one_is_not(tmp_path, blocks):
    rule = _span(_find(blocks, "Place a comma after adverbs", "heading"))
    assert "not-swept" in _codes(_run(tmp_path, [rule]))
    assert "not-swept" not in _codes(_run(tmp_path, [rule], swept=True))


def test_a_kept_rule_without_a_violation_condition_is_a_fix(tmp_path, blocks):
    """D-2, and the one the first 44 accepted rules all had."""
    rule = _span(_find(blocks, "Separate items in lists", "heading"))
    got = _run(tmp_path, [rule], rules={"Separate items": {
        "violation_condition": "", "specification": "Use commas between items in a sentence list."}})
    [f] = [f for f in got if f.code == "no-violation-condition"]
    assert f.level == "fix"
    assert "says what is right" in f.message, "the inverted-polarity hint is the useful part"
    assert "no-violation-condition" not in _codes(_run(tmp_path, [rule]))


def test_a_permission_is_flagged_as_one_and_owes_no_violation(tmp_path, blocks):
    """G-3: "you don't need a comma…" has nothing to violate."""
    block = _find(blocks, "You don’t need a comma after an introductory word")
    rule = _span(block, 0, block.plain.index(".") + 1, pre=["For any sentences with 4 or fewer words."])
    got = _run(tmp_path, [rule], rules={"You don": {"modality": "MAY", "violation_condition": ""}})
    codes = _codes(got)
    assert "permission-as-rule" in codes
    assert "no-violation-condition" not in codes
    # E-4 still applies to a permission: "4 or fewer words" is a chosen number.
    assert "chosen-threshold" in codes


@pytest.mark.parametrize("prefix,direction,flagged", [
    ("Separate items in lists", "presence", True),     # an instruction to add commas
    ("Separate items in lists", "absence", False),
    ("Don’t use commas with Latin", "absence", True),   # a prohibition
    ("Don’t use commas with Latin", "presence", False),
])
def test_direction_is_checked_against_the_wording(tmp_path, blocks, prefix, direction, flagged):
    rule = _span(_find(blocks, prefix, "heading"))
    got = _run(tmp_path, [rule], rules={"": {"direction": direction}})
    assert ("direction-looks-inverted" in _codes(got)) is flagged


def test_a_contrast_pair_labelled_as_a_violation_is_caught(tmp_path, blocks):
    """E-1: the committee sentence is correct English with a different meaning."""
    rule = _span(_find(blocks, "Mark out non", "heading"))
    neutral = _span(_find(blocks, "The committee said the secretary"), kind="violating",
                    of=rule.span_id)
    [f] = [f for f in _run(tmp_path, [rule, neutral]) if f.code == "example-polarity"]
    assert f.level == "check" and "different meaning" in f.message


def test_an_example_against_the_manual_label_is_a_fix(tmp_path, blocks):
    rule = _span(_find(blocks, "Don’t use commas with Latin", "heading"))
    correct = _find(blocks, "Exports of rare earths (e.g. lithium")
    incorrect = _find(blocks, "Exports of rare earths (e.g., lithium")
    swapped = [_span(correct, kind="violating", of=rule.span_id),
               _span(incorrect, kind="compliant", of=rule.span_id)]
    got = [f for f in _run(tmp_path, [rule, *swapped]) if f.code == "example-polarity"]
    assert len(got) == 2 and {f.level for f in got} == {"fix"}

    right = [_span(correct, kind="compliant", of=rule.span_id),
             _span(incorrect, kind="violating", of=rule.span_id)]
    assert "example-polarity" not in _codes(_run(tmp_path, [rule, *right]))


def test_a_parent_heading_kept_with_its_children_is_named(tmp_path, blocks):
    """G-1: the introductory-words section was marked at both levels."""
    parent = _span(_find(blocks, "Separate introductory words", "heading"))
    child = _span(_find(blocks, "Place a comma after adverbs", "heading"))
    [f] = [f for f in _run(tmp_path, [parent, child]) if f.code == "parent-and-children"]
    assert f.statement.startswith("Separate introductory words")
    assert "Place a comma after adverbs" in f.message
    assert "parent-and-children" not in _codes(_run(tmp_path, [child]))


def test_the_manuals_own_labelled_examples_are_pointed_at_when_unused(tmp_path, blocks):
    rule = _span(_find(blocks, "Don’t use commas with Latin", "heading"))
    got = [f for f in _run(tmp_path, [rule]) if f.code == "labelled-example-unused"]
    assert any("Exports of rare earths" in f.quote for f in got)


def test_body_sentences_are_grouped_under_the_rule_they_sit_beneath(tmp_path, blocks):
    """One finding per rule, not thirty loose sentences."""
    rule = _span(_find(blocks, "Mark out non", "heading"))
    got = [f for f in _run(tmp_path, [rule]) if f.code == "rule-body-unaccounted"]
    [f] = [f for f in got if f.statement.startswith("Mark out non")]
    assert "Always check for the second comma" in f.quote


def test_prose_after_a_label_heading_is_not_an_example():
    """The three reflexive-pronoun rules sit under `### Incorrect` in the tree."""
    blocks = parse_blocks(PRONOUNS, page_text(PRONOUNS))
    examples = _example_blocks(blocks)
    me = _find(blocks, "My colleague and me travelled")
    rule = _find(blocks, "Sentences can have reflexive pronouns")
    assert me.id in examples
    assert rule.id not in examples


def test_the_lint_writes_nothing(tmp_path, monkeypatch, capsys):
    repo = Path(golden_lint.__file__).resolve().parents[2]
    watched = [repo / "golden" / "spans.jsonl", repo / "golden" / "pages.jsonl",
               repo / "ledger" / "rules.jsonl"]
    before = [p.read_bytes() if p.exists() else None for p in watched]
    assert golden_lint.main(["--no-cross-page"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Golden-set worklist") or out.startswith("No findings")
    assert [p.read_bytes() if p.exists() else None for p in watched] == before
