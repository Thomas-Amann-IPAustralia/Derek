"""The batch path (ADR-027): same request, same parser, same cache as a live draft.

No network: the provider calls are replaced by fakes that answer the way each
batch API does, including a request that failed inside an otherwise good batch.
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
batch = _load("batch")

PAGES = ["grammar-punctuation-and-conventions/punctuation/full-stops.md",
         "grammar-punctuation-and-conventions/types-words/prepositions.md"]


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(drafting, "DRAFTS", tmp_path / "drafts")
    monkeypatch.setattr(batch, "BATCHES", tmp_path / "drafts" / "batches")
    return tmp_path


def _answer(rel: str) -> dict:
    page = drafting.load_page(rel)
    h = next(b for b in page.blocks if b.kind == "heading" and b.level == 2)
    return {"rules": [{
        "block_id": h.id, "quote": h.plain, "violation_condition": "x", "direction": "presence",
        "modality": "SHOULD", "unit": "sentence", "applies_to": ["any"],
        "detection_hint": "pattern", "clarity_suggestion": "unambiguous", "specification": "",
        "when": [], "examples": [], "covers": [], "why": ""}], "not_rules": []}


def _submit(monkeypatch, model, effort, sent):
    def fake_post(url, body, headers, method="POST", sse=False):
        sent.append((url, body))
        return {"id": "batch_1"} if "openai" in url else {"name": "batches/g1"}
    monkeypatch.setattr(batch, "_post", fake_post)
    monkeypatch.setattr(batch, "_openai_upload", lambda jsonl: sent.append(("upload", jsonl)) or "file-1")
    return batch.main(["submit", "--model", model, "--effort", effort, *PAGES])


def test_an_openai_batch_round_trips_into_the_cache(cache, monkeypatch):
    sent = []
    assert _submit(monkeypatch, "gpt-6.1-sol", "high", sent) == 0
    upload = next(b for u, b in sent if u == "upload").decode("utf-8").splitlines()
    first = json.loads(upload[0])
    assert first["url"] == "/v1/responses" and first["body"]["reasoning"] == {"effort": "high"}
    [(path, m)] = batch.manifests()

    ok = {"status": "completed", "model": "gpt-6.1-sol",
          "output": [{"type": "message", "content": [
              {"type": "output_text", "text": json.dumps(_answer(PAGES[0]))}]}],
          "usage": {"input_tokens": 100, "output_tokens": 1000}}
    lines = [json.dumps({"custom_id": "p0000", "response": {"status_code": 200, "body": ok}}),
             json.dumps({"custom_id": "p0001", "response": {
                 "status_code": 200, "body": {"status": "incomplete",
                                              "incomplete_details": {"reason": "max_output_tokens"}}}})]
    monkeypatch.setattr(batch, "_post", lambda *a, **k: {
        "status": "completed", "output_file_id": "out-1", "error_file_id": None})
    monkeypatch.setattr(batch, "_download", lambda fid: "\n".join(lines))
    assert batch.main(["collect"]) == 1, "one page failed, so collect says so"

    rec = json.loads(drafting.draft_path(PAGES[0], model="gpt-6.1-sol").read_text())
    assert rec["usage"]["batch"] == 1 and rec["effort"] == "high"
    assert rec["input_sha256"] == drafting.input_sha256(drafting.load_page(PAGES[0]), "gpt-6.1-sol", "high")
    assert len(rec["rules"]) == 1
    assert not drafting.draft_path(PAGES[1], model="gpt-6.1-sol").exists(), \
        "a cut-off page is left uncached for the next submit"
    assert json.loads(path.read_text())["collected"]


def test_a_gemini_batch_round_trips_into_the_cache(cache, monkeypatch):
    sent = []
    assert _submit(monkeypatch, "gemini-3.8-flash", "low", sent) == 0
    url, body = sent[0]
    assert url.endswith("gemini-3.8-flash:batchGenerateContent")
    req = body["batch"]["input_config"]["requests"]["requests"][0]
    config = req["request"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    # The batch API refuses responseJsonSchema with this schema; see openapi_schema.
    assert "responseJsonSchema" not in config
    assert config["responseSchema"]["type"] == "OBJECT"
    assert "additionalProperties" not in json.dumps(config["responseSchema"])

    good = {"candidates": [{"content": {"parts": [{"text": json.dumps(_answer(PAGES[1]))}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 500}}
    monkeypatch.setattr(batch, "_post", lambda *a, **k: {
        "name": "batches/g1", "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
        "response": {"inlinedResponses": {"inlinedResponses": [
            {"metadata": {"key": "p0001"}, "response": good},
            {"metadata": {"key": "p0000"}, "error": {"code": 13, "message": "internal"}}]}}})
    assert batch.main(["collect"]) == 1
    assert drafting.draft_path(PAGES[1], model="gemini-3.8-flash@low").exists(), \
        "results are matched by key, not by position"
    assert not drafting.draft_path(PAGES[0], model="gemini-3.8-flash@low").exists()


def test_a_page_in_an_open_batch_is_not_sent_again(cache, monkeypatch):
    sent = []
    _submit(monkeypatch, "gpt-6.1-sol", "high", sent)
    again = []
    _submit(monkeypatch, "gpt-6.1-sol", "high", again)
    assert again == [], "nothing uploaded or created the second time"


def test_a_batch_is_billed_at_half_price():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert providers.cost("gpt-6.1-sol", usage | {"batch": 1}) == providers.cost("gpt-6.1-sol", usage) / 2
