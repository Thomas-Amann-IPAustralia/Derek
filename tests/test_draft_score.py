"""The draft score: quality on blind pages, acceptance on seeded ones, never mixed."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from derek.eval.draft_score import report, score
from derek.extract.golden import GoldenSet, Span, span_id, write_golden

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "draft"


def _load_drafting():
    """tools/draft/drafting.py, by path like every other tool the tests use.

    Registered as ``drafting`` because that is the name draft_spans.py imports
    it by, so the command and the tests share one module and one DRAFTS path.
    """
    if "drafting" in sys.modules:
        return sys.modules["drafting"]
    spec = importlib.util.spec_from_file_location("drafting", TOOL / "drafting.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["drafting"] = module
    spec.loader.exec_module(module)
    return module


drafting = _load_drafting()

PRONOUNS = "grammar-punctuation-and-conventions/types-words/pronouns.md"      # blind
FULL_STOPS = "grammar-punctuation-and-conventions/punctuation/full-stops.md"  # seeded


def _span(page, block, kind="rule", of="", seed_draft=""):
    return Span(span_id=span_id(page, block.id, 0, len(block.plain), kind), kind=kind,
                page_path=page, page_sha256="", block_id=block.id, start=0,
                end=len(block.plain), quote=block.plain, of=of, seed_draft=seed_draft,
                tags={"direction": "presence", "modality": "SHOULD_NOT"} if kind == "rule" else {},
                by="TA", at="2026-09-23T00:00:00Z")


def _find(page, prefix):
    return next(b for b in page.blocks if b.plain.startswith(prefix))


def _raw_rule(block, examples=(), **tags):
    return {"block_id": block.id, "quote": block.plain,
            "violation_condition": "x", "direction": tags.get("direction", "presence"),
            "modality": tags.get("modality", "SHOULD_NOT"), "unit": "sentence",
            "applies_to": ["any"], "detection_hint": "pattern",
            "clarity_suggestion": "unambiguous", "specification": "", "when": [],
            "examples": list(examples), "covers": [], "why": ""}


@pytest.fixture
def world(tmp_path):
    """A blind page and a seeded page, each with human marks and a draft."""
    blind_page = drafting.load_page(PRONOUNS)
    reflexive = _find(blind_page, "Don’t use a reflexive pronoun if")
    case = _find(blind_page, "Use the correct case when writing pronouns.")
    relative = _find(blind_page, "Relative pronouns show")
    good = _find(blind_page, "I emailed myself.")
    bad = _find(blind_page, "The manager emailed myself.")

    rule = _span(PRONOUNS, reflexive)
    human = [rule, _span(PRONOUNS, case),
             _span(PRONOUNS, good, "compliant", rule.span_id),
             _span(PRONOUNS, bad, "violating", rule.span_id)]

    seeded_page = drafting.load_page(FULL_STOPS)
    web = _find(seeded_page, "Don’t end web or email addresses")
    kept = [_span(FULL_STOPS, web, seed_draft="p1/claude-opus-5"),
            _span(FULL_STOPS, _find(seeded_page, "Don’t use full stops with contractions"))]

    gs = GoldenSet(spans={PRONOUNS: human, FULL_STOPS: kept})
    sp, pp = tmp_path / "spans.jsonl", tmp_path / "pages.jsonl"
    write_golden(gs, sp, pp)

    drafts = tmp_path / "drafts"
    # The draft finds the reflexive rule but calls the manual's Incorrect sentence
    # compliant, misses the case rule, and adds the relative-pronoun heading.
    ex = [{"polarity": "compliant", "note": "", "parts": [{"block_id": good.id, "quote": good.plain}]},
          {"polarity": "compliant", "note": "", "parts": [{"block_id": bad.id, "quote": bad.plain}]}]
    for page, rules in ((blind_page, [_raw_rule(reflexive, ex), _raw_rule(relative)]),
                        (seeded_page, [_raw_rule(web)])):
        raw = {"rules": rules, "not_rules": []}
        rec = drafting.record(page, raw, drafting.resolve(page, raw),
                              served_model=drafting.MODEL, usage={}, stop_reason="end_turn")
        drafting.write_record(rec, drafting.draft_path(page.path, root=drafts))
    return {"spans": sp, "pages": pp, "drafts": drafts, "gs": gs}


def _run(world):
    _, _, rows = score("p1", "claude-opus-5", drafts_root=world["drafts"],
                       spans_path=world["spans"], pages_path=world["pages"])
    return {r.page_path: r for r in rows}


def test_a_blind_page_measures_recall_and_names_the_polarity_conflict(world):
    r = _run(world)[PRONOUNS]
    assert r.blind and not r.swept
    assert (r.golden, r.drafted, r.matched) == (2, 2, 1)
    [missed] = r.missed
    assert missed.startswith("Use the correct case when writing pronouns.")
    assert r.examples_golden == 2 and r.examples_found == 2
    assert len(r.polarity_conflicts) == 1 and "The manager emailed myself." in r.polarity_conflicts[0]
    assert r.tag_agree["direction"] == [1, 1]


def test_precision_waits_for_the_sweep(world):
    text = report("p1", "claude-opus-5", list(_run(world).values()))
    assert "**Precision**" not in text, "an unswept page cannot say a draft rule is wrong"

    world["gs"].swept[PRONOUNS] = {"page_path": PRONOUNS, "status": "complete", "by": "TA"}
    write_golden(world["gs"], world["spans"], world["pages"])
    text = report("p1", "claude-opus-5", list(_run(world).values()))
    assert "**Precision**: draft rules the human also marked (swept pages) | **50% (1/2)**" in text


def test_a_seeded_page_reports_acceptance_and_never_quality(world):
    rows = _run(world)
    seeded = rows[FULL_STOPS]
    assert not seeded.blind
    assert (seeded.accepted_from_draft, seeded.human_added) == (1, 1)

    text = report("p1", "claude-opus-5", list(rows.values()))
    blind_part, seeded_part = text.split("## Seeded pages")
    assert "Recall" in blind_part and "Recall" not in seeded_part
    assert "accepted from the draft | 50% (1/2)" in seeded_part


def test_the_baselines_are_measured_on_the_same_pages(world):
    r = _run(world)[PRONOUNS]
    # Both human rules sit in body prose, which the heading walk cannot reach,
    # and both start with a directive the regex does reach.
    assert r.heading_walk_hits == 0
    assert r.regex_hits == 2
