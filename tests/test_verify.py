"""The second reading (ADR-027): it only judges, and only across families.

No model runs here. Verdicts are written into a temporary cache the way
verify.py writes real ones, and consensus is checked for what it does with them.
"""

from __future__ import annotations

import importlib.util
import json
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
verify = _load("verify")

FULL_STOPS = "grammar-punctuation-and-conventions/punctuation/full-stops.md"
A, B = providers.PAIR


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "VERIFY", tmp_path / "verify")
    monkeypatch.setattr(consensus, "LEDGER", tmp_path / "rules.jsonl")


@pytest.fixture(scope="module")
def page():
    return drafting.load_page(FULL_STOPS)


def _rule(block, examples=()):
    return {"anchor": drafting.anchor(block, 0, len(block.plain)), "seed_uid": "",
            "tags": {"unit": "sentence", "direction": "presence", "modality": "SHOULD",
                     "applies_to": ["any"], "detection_hint": "pattern",
                     "violation_condition": "x", "specification": ""},
            "clarity_suggestion": "unambiguous", "when": [],
            "examples": [{"kind": k, "parts": [drafting.anchor(b, 0, len(b.plain))], "note": ""}
                         for k, b in examples], "covers": [], "why": ""}


def _verdict(rel, drafts, verdict):
    plan = consensus.page_plan(rel, drafts)
    cands = verify.candidates(plan, A)
    user = verify.user_message(rel, plan, cands)
    verify.write(rel, user, *verify.VERIFIER,
                 {"verdicts": [{"id": f"C{n}", "verdict": verdict, "restates": "", "note": "n"}
                               for n in range(1, len(cands) + 1)]}, "m", {})


def test_the_prompt_is_pinned():
    """Bump VERIFY_VERSION and set VERIFY_SHA256 together when the prompt changes."""
    assert verify.prompt_sha256() == verify.VERIFY_SHA256, verify.prompt_sha256()


def test_the_prompt_carries_the_grain_policy_and_no_cross_page_verdict():
    policy = (REPO / "docs" / "08-rule-grain.md").read_text(encoding="utf-8")
    assert policy in verify.system_prompt()
    assert "duplicate" not in verify.VERDICTS, "a one-page reader cannot judge G-6"


def test_only_another_family_verifies():
    assert verify.verifier_for(A) is not None
    assert verify.verifier_for(B) is None, "Gemini cannot confirm what Gemini found"


def test_a_confirmed_rule_is_taken_and_a_rejected_one_waits(page):
    b = next(x for x in page.blocks if x.plain.startswith("Complete a sentence with a full stop"))
    drafts = {A: {"rules": [_rule(b)], "not_rules": []}, B: {"rules": [], "not_rules": []}}
    _verdict(FULL_STOPS, drafts, "rule")
    plan = consensus.page_plan(FULL_STOPS, drafts)
    assert not [it for it in plan["items"] if it["kind"] == "single"]
    [rule] = plan["rules"]
    assert rule["verified"]["by"] == "@".join(verify.VERIFIER)
    ops, undecided = consensus.export_page(plan, {}, "t")
    assert not undecided and any(o["op"] == "span" and o["span"]["kind"] == "rule" for o in ops)

    _verdict(FULL_STOPS, drafts, "advice")
    plan = consensus.page_plan(FULL_STOPS, drafts)
    [item] = [it for it in plan["items"] if it["kind"] == "single"]
    assert item["second_reading"]["verdict"] == "advice"


def test_a_confirmed_rule_keeps_only_label_confirmed_examples(page):
    """Existence is two families; polarity is still one model's, so an unlabelled
    example goes to the adjudicator."""
    b = next(x for x in page.blocks if x.plain.startswith("Complete a sentence with a full stop"))
    ex = next(x for x in page.blocks if x.kind != "heading" and x.id != b.id
              and x.heading_path[-1].strip().lower() not in ("example", "examples", "correct",
                                                              "incorrect", "write this", "not this"))
    drafts = {A: {"rules": [_rule(b, [("violating", ex)])], "not_rules": []},
              B: {"rules": [], "not_rules": []}}
    _verdict(FULL_STOPS, drafts, "rule")
    plan = consensus.page_plan(FULL_STOPS, drafts)
    assert [it["kind"] for it in plan["items"]] == ["example"]


def test_a_stale_verdict_is_ignored(page):
    """New candidates on the page mean the verdicts were about other rules."""
    b = next(x for x in page.blocks if x.plain.startswith("Complete a sentence with a full stop"))
    drafts = {A: {"rules": [_rule(b)], "not_rules": []}, B: {"rules": [], "not_rules": []}}
    _verdict(FULL_STOPS, drafts, "rule")
    other = next(x for x in page.blocks if x.kind == "heading" and x.level == 2 and x.id != b.id)
    drafts[A]["rules"].append(_rule(other))
    plan = consensus.page_plan(FULL_STOPS, drafts)
    assert len([it for it in plan["items"] if it["kind"] == "single"]) == 2
