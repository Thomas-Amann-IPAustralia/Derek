"""Two-model consensus (ADR-027): agreement is taken, disagreement is adjudicated.

No model runs here. Two fake drafts, written the way ``drafting.resolve`` writes
real ones, are lined up on a real page; the tests pin what is taken without a
decision, what is held for one, and what the export refuses to emit.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "draft"


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, TOOL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


drafting = _load("drafting")
providers = _load("providers")
consensus = _load("consensus")

FULL_STOPS = "grammar-punctuation-and-conventions/punctuation/full-stops.md"
A, B = providers.PAIR


@pytest.fixture(scope="module")
def page():
    return drafting.load_page(FULL_STOPS)


@pytest.fixture(autouse=True)
def no_ledger(tmp_path, monkeypatch):
    """The fake drafts, not the live ledger's review history, decide these tests."""
    monkeypatch.setattr(consensus, "LEDGER", tmp_path / "rules.jsonl")


def _block(page, prefix):
    return next(b for b in page.blocks if b.plain.startswith(prefix))


def _rule(block, *, examples=(), **tags):
    base = {"unit": "sentence", "direction": "presence", "modality": "SHOULD",
            "applies_to": ["any"], "detection_hint": "pattern",
            "violation_condition": "a sentence with no full stop", "specification": ""}
    base.update(tags)
    clarity = base.pop("clarity", "unambiguous")
    return {
        "anchor": drafting.anchor(block, 0, len(block.plain)),
        "seed_uid": "", "tags": base, "clarity_suggestion": clarity, "when": [],
        "examples": [{"kind": k, "parts": [drafting.anchor(b, 0, len(b.plain))], "note": ""}
                     for k, b in examples],
        "covers": [], "why": "",
    }


def _draft(*rules, not_rules=()):
    return {"rules": list(rules), "not_rules": list(not_rules)}


def test_the_pair_is_two_families():
    """SOP §14.3: the second drafter checks the first only if it is not the same family."""
    assert providers.PROVIDERS[A] != providers.PROVIDERS[B]


def test_agreement_is_taken_without_a_decision(page):
    b = _block(page, "Complete a sentence with a full stop")
    plan = consensus.page_plan(FULL_STOPS, {A: _draft(_rule(b)), B: _draft(_rule(b))})
    [rule] = plan["rules"]
    assert rule["found_by"] == [A, B] and not rule.get("single")
    assert not [it for it in plan["items"] if it["rid"] == rule["rid"]]


def test_a_rule_only_one_model_found_waits_for_the_adjudicator(page):
    b = _block(page, "Complete a sentence with a full stop")
    plan = consensus.page_plan(FULL_STOPS, {A: _draft(_rule(b)), B: _draft()})
    [item] = [it for it in plan["items"] if it["kind"] == "single"]
    assert item["found_by"] == A
    ops, undecided = consensus.export_page(plan, {}, "2026-10-25T00:00:00.000Z")
    assert not ops and undecided == [item["item_id"]], "nothing exported until decided"


def test_a_dropped_single_rule_is_not_exported(page):
    b = _block(page, "Complete a sentence with a full stop")
    plan = consensus.page_plan(FULL_STOPS, {A: _draft(_rule(b)), B: _draft()})
    adj = {it["item_id"]: {"decision": {"keep": False}, "reason": "advice"}
           for it in plan["items"]}
    ops, undecided = consensus.export_page(plan, adj, "2026-10-25T00:00:00.000Z")
    assert not undecided
    assert not [o for o in ops if o["op"] == "span"]
    assert ops[-1]["op"] == "page" and ops[-1]["status"] == "complete"


def test_conflicting_tags_are_one_item_and_the_decision_wins(page):
    b = _block(page, "Complete a sentence with a full stop")
    plan = consensus.page_plan(FULL_STOPS, {
        A: _draft(_rule(b, direction="absence")), B: _draft(_rule(b, direction="presence"))})
    [item] = [it for it in plan["items"] if it["kind"] == "tags"]
    assert set(item["conflicts"]) == {"direction"}
    adj = {it["item_id"]: {"decision": {"tags": {"direction": "absence"}}, "reason": "r"}
           for it in plan["items"]}
    ops, _ = consensus.export_page(plan, adj, "2026-10-25T00:00:00.000Z")
    [rule] = [o for o in ops if o["op"] == "span" and o["span"]["kind"] == "rule"]
    assert rule["span"]["tags"]["direction"] == "absence"
    assert rule["by"] == consensus.BY_ADJUDICATOR


def test_an_example_both_models_attached_the_same_way_is_taken(page):
    rule_b = _block(page, "Complete a sentence with a full stop")
    ex = next(x for x in page.blocks if x.kind != "heading"
              and x.heading_path[:2] == rule_b.heading_path[:2] and x.id != rule_b.id)
    plan = consensus.page_plan(FULL_STOPS, {
        A: _draft(_rule(rule_b, examples=[("compliant", ex)])),
        B: _draft(_rule(rule_b, examples=[("compliant", ex)]))})
    assert not plan["items"]
    ops, _ = consensus.export_page(plan, {}, "2026-10-25T00:00:00.000Z")
    kids = [o["span"] for o in ops if o["op"] == "span" and o["span"]["kind"] == "compliant"]
    assert len(kids) == 1 and kids[0]["of"].startswith(rule_b.id)


def test_opposite_polarity_is_never_taken(page):
    """The Octavius inversion: two models disagreeing on polarity is a decision."""
    rule_b = _block(page, "Complete a sentence with a full stop")
    ex = next(x for x in page.blocks if x.kind != "heading"
              and x.heading_path[:2] == rule_b.heading_path[:2] and x.id != rule_b.id)
    plan = consensus.page_plan(FULL_STOPS, {
        A: _draft(_rule(rule_b, examples=[("compliant", ex)])),
        B: _draft(_rule(rule_b, examples=[("violating", ex)]))})
    assert [it["kind"] for it in plan["items"]] == ["example"]


def test_ambiguous_without_an_interpretation_is_downgraded(page):
    """server._apply refuses ambiguous_resolvable with no specification (ADR-017)."""
    b = _block(page, "Complete a sentence with a full stop")
    r = _rule(b, clarity="ambiguous_resolvable")
    plan = consensus.page_plan(FULL_STOPS, {A: _draft(r), B: _draft(r)})
    ops, _ = consensus.export_page(plan, {}, "2026-10-25T00:00:00.000Z")
    [rule] = [o for o in ops if o["op"] == "span" and o["span"]["kind"] == "rule"]
    assert rule["span"]["tags"]["clarity"] == "ambiguous_deferred"


def test_the_export_is_deterministic(page):
    b = _block(page, "Complete a sentence with a full stop")
    drafts = {A: _draft(_rule(b)), B: _draft(_rule(b))}
    one = consensus.export_page(consensus.page_plan(FULL_STOPS, drafts), {}, "t")
    two = consensus.export_page(consensus.page_plan(FULL_STOPS, drafts), {}, "t")
    assert one == two


def test_consensus_never_writes_to_a_human_page():
    """The pages a human marked are the measurement (ADR-027)."""
    assert "grammar-punctuation-and-conventions/punctuation/commas.md" in consensus.human_pages()


def test_a_bare_instruction_settles_to_should():
    """ADR-016: MUST only when the statement's own words make it one."""
    assert consensus.settle_modality("Use italics for titles.", "SHOULD", "MUST") == "SHOULD"
    assert consensus.settle_modality("Never use double spaces.", "SHOULD_NOT", "MUST_NOT") == "MUST_NOT"
    assert consensus.settle_modality("Use X.", "PREFER", "MUST") == "", "anything else is adjudicated"


def test_unit_and_clarity_settle_towards_caution():
    assert consensus.settle_unit("", "token", "sentence") == "sentence"
    assert consensus.settle_clarity("", "unambiguous", "ambiguous_deferred") == "ambiguous_deferred"


def test_direction_is_never_settled_by_rule():
    """ADR-006: presence vs absence decides the detection method, so a person or
    the adjudicator decides it, never a tie-break."""
    assert "direction" not in consensus.SETTLE


def test_a_rule_in_the_page_introduction_is_not_exported(page, capsys):
    """It would take level 1, which no candidate may have (ADR-002)."""
    intro = next(b for b in page.blocks if b.kind != "heading" and len(b.heading_path) == 1)
    plan = consensus.page_plan(FULL_STOPS, {A: _draft(_rule(intro)), B: _draft(_rule(intro))})
    ops, _ = consensus.export_page(plan, {}, "t")
    assert not [o for o in ops if o["op"] == "span"]
    assert "page introduction" in capsys.readouterr().err
