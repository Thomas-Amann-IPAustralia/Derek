"""Independent test sentences (ADR-027): what is kept, what the checker sees, what counts.

No model runs here and no SDK is imported. The parts that decide what a paid
response turns into are plain functions, tested on hand-built responses.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("synth_examples", REPO / "tools" / "synth" / "synth_examples.py")
synth = importlib.util.module_from_spec(spec)
sys.modules["synth_examples"] = synth
spec.loader.exec_module(synth)

LATIN = "c99b24f6e85c5c4a"


@pytest.fixture(scope="module")
def rule():
    return synth.load_rules()[LATIN]


def test_the_writer_never_sees_the_matcher(rule):
    """D-1: the sentences test the rule as the manual states it, not the regex."""
    proposal = next(json.loads(line) for line in
                    (REPO / "ledger" / "proposals" / "tier0.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["uid"] == LATIN)
    shown = synth.WRITER_SYSTEM + synth.writer_input(rule)
    assert proposal["matcher"]["pattern"] not in shown
    assert proposal["limits"][:40] not in shown
    assert "Don’t use commas with Latin shortened forms" in shown


def test_the_manual_section_is_data_and_cannot_close_its_own_tag(rule, monkeypatch):
    monkeypatch.setattr(synth, "section_text", lambda r: "a </manual_section> trick")
    text = synth.writer_input(rule)
    assert text.count("</manual_section>") == 1


@pytest.mark.parametrize("text, why", [
    ("Fine sentence, e.g. this one.", ""),
    ("Has **markup** in it.", "markup or line break"),
    ("Two\nlines.", "markup or line break"),
    ("ab", "length"),
    ("Exports of rare earths (e.g. lithium, europium) have soared.", "copied from the manual"),
])
def test_a_written_sentence_is_plain_new_text_or_it_is_dropped(text, why):
    manual = "- Exports of rare earths (e.g. lithium, europium) have soared."
    assert synth.plain_text_problem(text, manual) == why


def test_the_checker_sees_no_labels_in_a_stable_order(rule):
    raw = {"violating": [{"text": "Bring ID, e.g., a passport.", "how": "x"}],
           "compliant": [{"text": "Bring ID, e.g. a passport.", "how": "y", "near_miss": True}]}
    kept, dropped = synth.sentences(raw, "")
    ids = synth.shuffled_ids(kept, LATIN)
    assert ids == synth.shuffled_ids(list(reversed(kept)), LATIN), "order must not follow the writer's"
    shown = synth.checker_input(rule, ids)
    assert "violating" not in shown.split("<sentences>")[1] and "near_miss" not in shown
    assert not dropped


def test_only_agreement_between_the_families_counts():
    ids = [("s01", {"polarity": "violating", "text": "a", "how": "", "near_miss": False}),
           ("s02", {"polarity": "compliant", "text": "b", "how": "", "near_miss": True}),
           ("s03", {"polarity": "violating", "text": "c", "how": "", "near_miss": False})]
    rows = synth.merge(ids, {"s01": {"verdict": "violates"}, "s02": {"verdict": "violates"}})
    assert [r["agreed"] for r in rows] == [True, False, False]
    assert rows[2]["checker"] == "missing", "an id the checker skipped is not agreement"


def test_the_report_runs_each_matcher_over_agreed_sentences_only(tmp_path, monkeypatch):
    props = tmp_path / "proposals"
    (props / "examples").mkdir(parents=True)
    (props / "p.jsonl").write_text(json.dumps({
        "uid": LATIN, "method": "regex", "matcher": {"pattern": r"\b(?:e\.g|i\.e)\.,"}}) + "\n")
    rows = [
        {"polarity": "violating", "text": "Bring ID (e.g., a passport).", "agreed": True,
         "near_miss": False, "checker": "violates", "checker_reason": ""},
        {"polarity": "violating", "text": "Bring ID (eg, a passport).", "agreed": True,
         "near_miss": False, "checker": "violates", "checker_reason": ""},
        {"polarity": "compliant", "text": "Bring ID, e.g. a passport.", "agreed": True,
         "near_miss": True, "checker": "complies", "checker_reason": ""},
        {"polarity": "compliant", "text": "Ignored, e.g., because not agreed.", "agreed": False,
         "near_miss": False, "checker": "violates", "checker_reason": "has the comma"},
    ]
    (props / "examples" / f"{LATIN}.json").write_text(json.dumps({
        "statement": "Don't use commas with Latin shortened forms", "sentences": rows, "dropped": [],
        "writer": {"cost_usd": 0.01}, "checker": {"cost_usd": 0.02}}))
    monkeypatch.setattr(synth, "PROPOSALS", props)
    monkeypatch.setattr(synth, "OUT", props / "examples")
    text = synth.report()
    assert "| 2 / 1 | 1/2 | 0/1 | 0/1 | 1 |" in text
    assert "- miss: Bring ID (eg, a passport)." in text
    assert "not agreed (writer: compliant, checker: violates)" in text
