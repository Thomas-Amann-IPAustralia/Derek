"""What a matcher is adopted on, and the record it leaves (ADR-028).

The owner's three conditions, as tests:

* a test sentence may stand in for a missing manual example, but only one that
  both model families agreed on and a named person confirmed;
* every example used carries where it came from, into the adoption record;
* nobody adopts a matcher without the full results in front of them, enforced by
  a fingerprint of the card they read.

No model runs here. Test-sentence records and verdicts are built by hand.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from derek.detect import examples as ex
from derek.detect import proposals as props
from derek.detect.document import Document
from derek.extract.golden import load_golden
from derek.ledger.store import load_ledger, write_ledger

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "ledger" / "rules.jsonl"
LATIN = "c99b24f6e85c5c4a"
PATTERN = r"\b(?:e\.g|i\.e)\.,"
DOC = [("t", Document.from_text("Plain compliant prose, e.g. this sentence, with nothing wrong in it."))]


@pytest.fixture(scope="module")
def golden():
    return load_golden()


def _rule(violating=("Exports of rare earths (e.g., lithium and europium) have soared.",)):
    rule = load_ledger(LEDGER)[LATIN]
    rule.review.status = "accepted"
    rule.compliant_examples = ["Exports of rare earths (e.g. lithium, europium) have soared."]
    rule.violating_examples = list(violating)
    return rule


def _record(*sentences):
    """A cached test-sentence record: (text, polarity, agreed, near_miss)."""
    return {LATIN: {
        "uid": LATIN, "statement": "Don't use commas with Latin shortened forms",
        "input_sha256": "f" * 64, "prompt_version": "s1", "_path": "ledger/proposals/examples/x.json",
        "writer": {"model": "gpt-6.1-sol", "effort": "medium", "served_model": "gpt-6.1-sol"},
        "checker": {"model": "gemini-3.1-pro-preview", "served_model": "gemini-3.1-pro-preview"},
        "sentences": [{"text": t, "polarity": p, "agreed": a, "near_miss": n,
                       "checker": "violates" if p == "violating" else "complies",
                       "checker_reason": "", "how": ""} for t, p, a, n in sentences],
    }}


def _verdict(text, verdict="accept", by="TA", at="2026-10-10T00:00:00Z"):
    sid = ex.test_sentence_id(LATIN, text)
    return {sid: {"id": sid, "verdict": verdict, "by": by, "at": at}}


def _check(rule, records, verdicts, golden, pattern=PATTERN):
    proposal = {"uid": LATIN, "method": "regex", "matcher": {"pattern": pattern},
                "expected_density": 0.0, "_source": "test", "proposed_by": "test"}
    [c] = props.check([proposal], {LATIN: rule}, docs=DOC, words=1000,
                      golden=golden, records=records, verdicts=verdicts)
    return c


# ---------------------------------------------------------------------------
# Which test sentences count
# ---------------------------------------------------------------------------

V1 = "Bring ID (e.g., a passport)."
V2 = "Bring ID (eg, a passport)."          # a form the pattern does not cover
C1 = "Bring ID, e.g. a passport."
C2 = "Bring ID (e.g., a passport) or not."


def test_only_agreed_and_personally_confirmed_sentences_count():
    recs = _record((V1, "violating", True, False), (V2, "violating", False, False),
                   (C1, "compliant", True, True))
    verdicts = {**_verdict(V1), **_verdict(V2), **_verdict(C1, by="")}
    got = ex.confirmed(recs[LATIN], verdicts)
    assert [e.text for e in got] == [V1], "not agreed, or confirmed by nobody, does not count"
    p = got[0].provenance
    assert p["confirmed_by"] == "TA" and p["writer"]["model"] == "gpt-6.1-sol"
    assert p["checker"]["model"] == "gemini-3.1-pro-preview" and p["record_input_sha256"] == "f" * 64


def test_a_later_verdict_replaces_an_earlier_one(tmp_path):
    path = tmp_path / "v.jsonl"
    sid = ex.test_sentence_id(LATIN, V1)
    path.write_text("\n".join(json.dumps({"id": sid, "verdict": v, "by": "TA", "at": a})
                              for v, a in (("accept", "1"), ("reject", "2"))) + "\n")
    assert ex.load_verdicts(path)[sid]["verdict"] == "reject"
    assert not ex.confirmed(_record((V1, "violating", True, False))[LATIN], ex.load_verdicts(path))


def test_the_queue_asks_only_about_agreed_sentences_nobody_has_ruled_on():
    recs = _record((V1, "violating", True, False), (V2, "violating", False, False),
                   (C1, "compliant", True, True))
    items = ex.queue_items(recs, _verdict(V1))
    assert [it["text"] for it in items] == [C1]
    assert items[0]["origin"] == "synthetic" and items[0]["claimed"] == "compliant"


def test_a_test_sentence_id_is_the_rule_and_the_text_and_nothing_else():
    assert ex.test_sentence_id(LATIN, V1) == ex.test_sentence_id(LATIN, V1)
    assert ex.test_sentence_id(LATIN, V1) != ex.test_sentence_id(LATIN, V1 + " ")


def test_a_marked_example_is_traced_to_the_spans_that_marked_it(golden):
    rule = _rule()
    [c, v] = ex.ledger_examples(rule, golden)
    assert {c.source, v.source} == {ex.HUMAN_SPAN}
    assert v.provenance["span_ids"] and v.provenance["marked_by"] == ["TA"]
    rule.violating_examples = ["A sentence nobody marked, e.g., anywhere."]
    [_, v] = ex.ledger_examples(rule, golden)
    assert v.source == ex.STYLE_MANUAL and v.provenance["page_path"] == rule.source.page_path


# ---------------------------------------------------------------------------
# What a confirmed test sentence does in the harness
# ---------------------------------------------------------------------------

def test_a_confirmed_sentence_stands_in_for_a_missing_manual_example(golden):
    rule = _rule(violating=())
    assert any("no violating example" in b for b in _check(rule, {}, {}, golden).blockers)

    recs = _record((V1, "violating", True, False))
    c = _check(rule, recs, _verdict(V1), golden)
    assert c.ready, c.blockers
    assert c.tally((ex.TEST_SENTENCE,), "violating") == (1, 1)


def test_a_stand_in_must_actually_be_caught(golden):
    rule = _rule(violating=())
    c = _check(rule, _record((V2, "violating", True, False)), _verdict(V2), golden)
    assert any("none of the 1 confirmed violating test sentence" in b for b in c.blockers)


def test_a_false_alarm_on_a_confirmed_sentence_blocks(golden):
    c = _check(_rule(), _record((C2, "compliant", True, True)), _verdict(C2), golden)
    assert any("follow the rule fire" in b for b in c.blockers)


def test_a_missed_test_sentence_is_reported_not_blocking(golden):
    recs = _record((V1, "violating", True, False), (V2, "violating", True, False))
    c = _check(_rule(), recs, {**_verdict(V1), **_verdict(V2)}, golden)
    assert c.ready, c.blockers
    assert c.tally((ex.TEST_SENTENCE,), "violating") == (1, 2)
    assert f"| flagged | {V2} |" in props.card_body(c) and "✗ missed" in props.card_body(c)


def test_an_unconfirmed_sentence_is_previewed_but_never_counted(golden):
    c = _check(_rule(), _record((C2, "compliant", True, True)), {}, golden)
    assert c.ready, "a false alarm on a sentence nobody confirmed does not block"
    body = props.card_body(c)
    assert "awaiting a person" in body and "it flags 1" in body


# ---------------------------------------------------------------------------
# The card and the record
# ---------------------------------------------------------------------------

def test_the_card_is_deterministic_and_changes_with_the_evidence(golden):
    recs = _record((V1, "violating", True, False))
    a = props.card_body(_check(_rule(), recs, {}, golden))
    assert a == props.card_body(_check(_rule(), recs, {}, golden))
    b = props.card_body(_check(_rule(), recs, _verdict(V1), golden))
    assert props.fingerprint(a) != props.fingerprint(b), "confirming a sentence changes the card"


@pytest.fixture
def adopting(tmp_path, golden):
    ledger = tmp_path / "rules.jsonl"
    rules = load_ledger(LEDGER)
    rules[LATIN] = rule = _rule()
    write_ledger(ledger, rules.values())
    recs = _record((V1, "violating", True, False), (C1, "compliant", True, True))
    c = _check(rule, recs, {**_verdict(V1), **_verdict(C1)}, golden)
    assert c.ready, c.blockers
    return ledger, c, tmp_path / "adoptions"


def test_adoption_refuses_without_the_cards_fingerprint(adopting):
    ledger, c, out = adopting
    assert props.adopt([LATIN], "TA", ledger=ledger, checks=[c], adoptions=out) == 0
    assert props.adopt([LATIN], "TA", ledger=ledger, checks=[c], cards={LATIN: "0" * 12},
                       adoptions=out) == 0
    assert not load_ledger(ledger)[LATIN].detection.detectable and not out.exists()


def test_adoption_records_every_example_with_its_provenance(adopting):
    ledger, c, out = adopting
    fp = props.fingerprint(props.card_body(c))
    assert props.adopt([LATIN], "TA", ledger=ledger, checks=[c], cards={LATIN: fp[:12]},
                       adoptions=out) == 1

    path = out / f"{LATIN}.json"
    text = path.read_text(encoding="utf-8")
    rec = json.loads(text)
    assert rec["adopted_by"] == "TA" and rec["card_sha256"] == fp
    assert rec["card"] == props.card_body(c), "the record holds the card that was read"
    sources = {(e["source"], e["polarity"]) for e in rec["examples"]}
    assert sources == {(ex.HUMAN_SPAN, "compliant"), (ex.HUMAN_SPAN, "violating"),
                       (ex.TEST_SENTENCE, "compliant"), (ex.TEST_SENTENCE, "violating")}
    synth = [e for e in rec["examples"] if e["source"] == ex.TEST_SENTENCE]
    assert all(e["provenance"]["confirmed_by"] == "TA" and e["provenance"]["writer"]["model"]
               and e["provenance"]["checker"]["model"] for e in synth)

    entry = load_ledger(ledger)[LATIN].review.history[-1]
    assert entry["by"] == "TA" and entry["card_sha256"] == fp
    assert entry["record_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert entry["record"].endswith(f"{LATIN}.json")


# ---------------------------------------------------------------------------
# Where a person confirms them
# ---------------------------------------------------------------------------

def _server():
    spec = importlib.util.spec_from_file_location("derek_review_server",
                                                  REPO / "tools" / "review" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_example_screen_puts_test_sentences_first(monkeypatch, tmp_path):
    server = _server()
    monkeypatch.setattr(ex, "load_test_sentences", lambda root=None: _record(
        (V1, "violating", True, False), (V2, "violating", False, False)))
    monkeypatch.setattr(server, "TEST_SENTENCES", tmp_path)
    monkeypatch.setattr(server, "EXAMPLE_VERDICTS", tmp_path / "none.jsonl")
    monkeypatch.setattr(server, "SYNTHETIC", tmp_path / "absent.jsonl")
    q = server.example_queue(load_ledger(LEDGER))
    assert q["items"][0]["text"] == V1 and q["items"][0]["origin"] == "synthetic"
    assert V2 not in {it["text"] for it in q["items"]}, "a sentence the families disputed is not asked"
    assert q["origin"] == "mixed" and any(it["origin"] == "style_manual" for it in q["items"])
