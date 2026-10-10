"""A rule's examples, each with where it came from (ADR-026, ADR-028).

A matcher is adopted only when its rule's examples agree with it, so which
examples those are, and who stands behind each one, is part of the audit trail.
Three sources, and nothing else:

``style_manual``
    Harvested from the manual's own labelled example blocks under the rule's
    heading (``derek.extract.candidates``).
``human_span``
    Marked by a person in the annotator (``golden/spans.jsonl``).
``test_sentence``
    Written by a model that never saw the matcher, labelled the same way by a
    second model family that never saw the first one's labels, and confirmed by a
    named person in the triage app's example screen. All three, or it is not a
    test sentence and nothing counts it (D-1: the matcher's author, the writer,
    the checker and the confirmer are four different hands).

The first two are the rule's examples in the ledger. The third is read from the
cached records ``tools/synth/synth_examples.py`` writes under
``ledger/proposals/examples/`` and the verdicts in ``ledger/example_reviews.jsonl``,
so a test sentence never becomes part of the rule itself; it is evidence about a
matcher, kept with its provenance.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST_SENTENCES = REPO / "ledger" / "proposals" / "examples"
VERDICTS = REPO / "ledger" / "example_reviews.jsonl"

STYLE_MANUAL = "style_manual"
HUMAN_SPAN = "human_span"
TEST_SENTENCE = "test_sentence"


@dataclass(frozen=True)
class Example:
    text: str
    polarity: str                       # compliant | violating
    source: str                         # style_manual | human_span | test_sentence
    provenance: dict = field(default_factory=dict, compare=False, hash=False)

    def to_dict(self) -> dict:
        return {"text": self.text, "polarity": self.polarity, "source": self.source,
                "provenance": self.provenance}


def test_sentence_id(uid: str, text: str) -> str:
    """Stable across runs and machines: the rule and the sentence, nothing else."""
    return f"syn-{uid}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Test sentences and their verdicts
# ---------------------------------------------------------------------------

def load_test_sentences(root: Path = TEST_SENTENCES) -> dict[str, dict]:
    """Every cached test-sentence record, by rule uid."""
    out = {}
    for path in sorted(root.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["_path"] = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
        out[rec["uid"]] = rec
    return out


def load_verdicts(path: Path = VERDICTS) -> dict[str, dict]:
    """The latest verdict on each example id. A later verdict replaces an earlier one."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row
    return out


def agreed(rec: dict) -> list[dict]:
    """The sentences both families labelled the same way: the only ones a person is asked about."""
    return [s for s in rec.get("sentences", []) if s.get("agreed")]


def queue_items(records: dict[str, dict], verdicts: dict[str, dict]) -> list[dict]:
    """Agreed test sentences nobody has ruled on, in the triage app's item shape."""
    items = []
    for uid, rec in sorted(records.items()):
        for s in agreed(rec):
            sid = test_sentence_id(uid, s["text"])
            if sid in verdicts:
                continue
            items.append({"id": sid, "origin": "synthetic", "rule_uid": uid,
                          "rule": rec.get("statement", ""), "text": s["text"],
                          "claimed": s["polarity"]})
    return items


def test_sentence_status(rec: dict, verdicts: dict[str, dict]) -> list[dict]:
    """Every sentence in a record, with where it stands: what the card reports."""
    out = []
    for s in rec.get("sentences", []):
        sid = test_sentence_id(rec["uid"], s["text"])
        v = verdicts.get(sid)
        if not s.get("agreed"):
            state = "not agreed"
        elif v is None:
            state = "awaiting a person"
        elif v.get("verdict") == "accept" and v.get("by"):
            state = "confirmed"
        elif v.get("verdict") == "reject":
            state = "rejected by a person"
        else:
            state = "not sure"
        out.append({**s, "id": sid, "state": state, "verdict": v})
    return out


def confirmed(rec: dict, verdicts: dict[str, dict]) -> list[Example]:
    """Test sentences that may test a matcher: agreed by both families, confirmed by a person."""
    out = []
    for s in test_sentence_status(rec, verdicts):
        if s["state"] != "confirmed":
            continue
        v = s["verdict"]
        out.append(Example(s["text"], s["polarity"], TEST_SENTENCE, {
            "id": s["id"],
            "record": rec.get("_path", ""),
            "record_input_sha256": rec.get("input_sha256", ""),
            "prompt_version": rec.get("prompt_version", ""),
            "writer": {k: rec["writer"].get(k, "") for k in ("model", "effort", "served_model")},
            "checker": {"model": rec["checker"].get("model", ""),
                        "served_model": rec["checker"].get("served_model", ""),
                        "verdict": s.get("checker", ""), "reason": s.get("checker_reason", "")},
            "near_miss": bool(s.get("near_miss")),
            "confirmed_by": v.get("by", ""),
            "confirmed_at": v.get("at", ""),
        }))
    return out


# ---------------------------------------------------------------------------
# The ledger's own examples
# ---------------------------------------------------------------------------

def _spans_by_page(golden) -> dict[str, list]:
    return {page: [s for s in spans if s.kind in ("compliant", "violating")]
            for page, spans in (golden.spans.items() if golden else [])}


def ledger_examples(rule, golden=None) -> list[Example]:
    """The rule's examples in the ledger, traced to the spans a person marked
    where they were marked, otherwise to the manual block they were harvested from."""
    page = rule.source.page_path
    spans = _spans_by_page(golden).get(page, [])
    out = []
    for polarity, pool in (("compliant", rule.compliant_examples),
                           ("violating", rule.violating_examples)):
        for text in pool:
            parts = text.split("\n")
            hits = [s for s in spans if s.kind == polarity and s.quote in parts]
            if hits and {s.quote for s in hits} >= set(parts):
                out.append(Example(text, polarity, HUMAN_SPAN, {
                    "page_path": page, "input": "golden/spans.jsonl",
                    "span_ids": sorted({s.span_id for s in hits}),
                    "marked_by": sorted({s.by for s in hits if s.by}),
                    "marked_at": max((s.at for s in hits if s.at), default=""),
                }))
            else:
                out.append(Example(text, polarity, STYLE_MANUAL, {
                    "page_path": page, "heading_path": list(rule.source.heading_path),
                    "url": rule.source.url, "snapshot_sha256": rule.source.snapshot_sha256,
                    "harvested_by": "derek.extract.candidates",
                }))
    return out


def rule_examples(rule, *, golden=None, records: dict[str, dict] | None = None,
                  verdicts: dict[str, dict] | None = None) -> list[Example]:
    """Everything that may test this rule's matcher, each with its provenance."""
    records = load_test_sentences() if records is None else records
    verdicts = load_verdicts() if verdicts is None else verdicts
    out = ledger_examples(rule, golden)
    rec = records.get(rule.uid)
    if rec:
        out += confirmed(rec, verdicts)
    return out
