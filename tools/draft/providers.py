"""The model transports the drafter can use (ADR-025, ADR-027).

One function per provider, each taking the same (system, user, schema) and
returning the same tuple: (parsed JSON, served model, usage, stop reason). The
prompt, the pointer check and the cache are shared and live in ``drafting.py``;
only the wire format differs here.

Stdlib only (``urllib``), so adding a provider adds no dependency: the OpenAI
and Gemini calls are one HTTPS POST each, and a second SDK would be one more
pinned thing to keep in step for no gain. The Anthropic path keeps its SDK
because ``draft_spans.py`` already uses its streaming and refusal-fallback
features.

Keys come from the environment (``OPENAI_API_KEY``, ``GEMINI_API_KEY``) when
set, as they are in Actions. In a cloud session the egress proxy injects them,
so an unset key is not an error here; the provider's 401 is.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


class DraftError(RuntimeError):
    """A page that could not be drafted. Names the page and why."""


# Which transport each pinned model goes through. A model not listed here
# cannot be drafted with, which is the point: pinning is a code change.
PROVIDERS = {
    "claude-opus-5": "anthropic",
    "gpt-6-astra": "openai",
    "gpt-6.1-sol": "openai",
    "gpt-6-luna": "openai",
    "gemini-3.1-pro-preview": "gemini",
    "gemini-3.8-flash": "gemini",
}

# The two drafters ADR-027 runs side by side, as drafter ids (`model` or
# `model@effort`, the cache directory each writes to). Different families, so
# one's blind spots are not the other's (SOP §14.3); a third family adjudicates.
# Adopted by the owner on 2026-10-25 after the commas.md comparison: Sol at high
# effort (below it, no model returned examples), Flash at low (at high it spent
# its whole output on reasoning). The sample's seven pages were drawn by
# ("gpt-6-astra", "gemini-3.1-pro-preview") and stay as applied.
PAIR = ("gpt-6.1-sol", "gemini-3.8-flash@low")

TIMEOUT_S = 900
RETRIES = 4


# A request that sends nothing for about 35 seconds is cut by the egress proxy
# with a 502, and a page drafted at high effort thinks for minutes. So no call
# here waits silently: OpenAI runs in background mode and is polled, Gemini
# streams its thought summaries as server-sent events.
POLL_S = 10


def _post(url: str, body: dict | None, headers: dict, *, method: str = "POST",
          sse: bool = False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last = ""
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                if sse:
                    return _read_sse(resp)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}"
            # 4xx other than rate limiting is a request we built wrongly;
            # retrying it only bills the same mistake again.
            if exc.code not in (408, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = f"transport: {exc}"
        time.sleep(2 ** (attempt + 1))
    raise DraftError(last)


def _read_sse(resp) -> list[dict]:
    events = []
    for line in resp:
        line = line.decode("utf-8").strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    return events


def _parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError(f"the model's output is not the JSON asked for: {exc}") from exc


def _openai_headers() -> dict:
    headers = {}
    if key := os.environ.get("OPENAI_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _gemini_headers() -> dict:
    headers = {}
    if key := os.environ.get("GEMINI_API_KEY"):
        headers["x-goog-api-key"] = key
    return headers


# The request bodies and the answer parsers are shared by the live calls here
# and the batch path in batch.py, so a page drafted either way is the same
# request and is read the same way: the cache key (drafting.input_sha256) does
# not record the transport, and must not need to.

def openai_body(model: str, system: str, user: str, schema: dict, *,
                effort: str, max_tokens: int) -> dict:
    return {
        "model": model,
        "instructions": system,
        "input": user,
        "reasoning": {"effort": effort},
        "max_output_tokens": max_tokens,
        "text": {"format": {"type": "json_schema", "name": "draft",
                            "schema": schema, "strict": True}},
    }


def parse_openai(out: dict, model: str) -> tuple[dict, str, dict, str]:
    status = out.get("status", "")
    if status in ("failed", "cancelled"):
        raise DraftError(f"{status}: {(out.get('error') or {}).get('message', '')[:300]}")
    if status == "incomplete":
        why = (out.get("incomplete_details") or {}).get("reason", "")
        raise DraftError(f"incomplete ({why}); the draft was cut off")
    text, refusal = "", ""
    for item in out.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                text += part.get("text", "")
            elif part.get("type") == "refusal":
                refusal = part.get("refusal", "")
    if refusal:
        raise DraftError(f"declined: {refusal[:200]}")
    u = out.get("usage") or {}
    usage = {
        "input_tokens": int(u.get("input_tokens") or 0),
        "cached_input_tokens": int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0),
        "output_tokens": int(u.get("output_tokens") or 0),
        "reasoning_tokens": int((u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0),
    }
    return _parse(text), out.get("model", model), usage, status or "completed"


def call_openai(model: str, system: str, user: str, schema: dict, *,
                effort: str, max_tokens: int) -> tuple[dict, str, dict, str]:
    headers = _openai_headers()
    body = openai_body(model, system, user, schema, effort=effort, max_tokens=max_tokens)
    # Background mode needs the response stored provider-side until it is
    # fetched. The input is the published Style Manual, so nothing private is
    # kept; the cache under golden/drafts/ is still the only record we read
    # (ADR-003).
    out = _post("https://api.openai.com/v1/responses",
                body | {"background": True, "store": True}, headers)
    started = time.monotonic()
    while out.get("status") in ("queued", "in_progress"):
        if time.monotonic() - started > TIMEOUT_S * 2:
            raise DraftError(f"still {out.get('status')} after {TIMEOUT_S * 2}s")
        time.sleep(POLL_S)
        out = _post(f"https://api.openai.com/v1/responses/{out['id']}", None, headers,
                    method="GET")
    return parse_openai(out, model)


def gemini_body(system: str, user: str, schema: dict, *, effort: str, max_tokens: int,
                stream: bool) -> dict:
    thinking = {"thinkingLevel": effort}
    if stream:
        # Thought summaries are asked for only so a live stream keeps moving
        # while the model thinks; they are dropped by parse_gemini. A batch
        # request has no connection to keep alive.
        thinking["includeThoughts"] = True
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": thinking,
        },
    }


def parse_gemini(chunks: list[dict], model: str, max_tokens: int) -> tuple[dict, str, dict, str]:
    """One answer, from a stream's chunks or from a single (batch) response."""
    if not chunks:
        raise DraftError("the stream ended with no events")
    parts, finish, out = [], "", chunks[-1]
    for ev in chunks:
        for cand in ev.get("candidates") or []:
            parts.extend((cand.get("content") or {}).get("parts", []))
            finish = cand.get("finishReason", finish)
    if not parts:
        block = (out.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise DraftError(f"declined: {block}")
    if finish == "MAX_TOKENS":
        raise DraftError(f"ran out of output at {max_tokens} tokens; the draft is incomplete")
    if finish not in ("STOP", ""):
        raise DraftError(f"stopped with {finish}")
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = out.get("usageMetadata") or {}
    usage = {
        "input_tokens": int(u.get("promptTokenCount") or 0),
        "cached_input_tokens": int(u.get("cachedContentTokenCount") or 0),
        "output_tokens": int(u.get("candidatesTokenCount") or 0),
        "reasoning_tokens": int(u.get("thoughtsTokenCount") or 0),
    }
    return _parse(text), out.get("modelVersion", model), usage, finish or "STOP"


def call_gemini(model: str, system: str, user: str, schema: dict, *,
                effort: str, max_tokens: int) -> tuple[dict, str, dict, str]:
    events = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":streamGenerateContent?alt=sse",
        gemini_body(system, user, schema, effort=effort, max_tokens=max_tokens, stream=True),
        _gemini_headers(), sse=True)
    return parse_gemini(events, model, max_tokens)


# Dollars per million tokens, from the providers' published prices as found on
# 2026-10-25 (third-party listings agreed; recheck before trusting a total).
# Used only to report what a run cost, never to decide anything.
PRICES = {
    "gpt-6-astra": {"input": 10.0, "cached_input": 1.0, "output": 50.0},
    "gpt-6.1-sol": {"input": 2.0, "cached_input": 0.2, "output": 10.0},
    "gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "output": 0.50},
    "gemini-3.1-pro-preview": {"input": 2.0, "cached_input": 0.2, "output": 12.0},
    "gemini-3.8-flash": {"input": 0.75, "cached_input": 0.075, "output": 3.75},
}


# Both providers bill a batch request at half the standard rate. A record
# drafted through batch.py says so in its usage, so cost() reports what was paid.
BATCH_DISCOUNT = 0.5


def cost(model: str, usage: dict) -> float:
    """What one call cost in USD. Reasoning is billed as output by both."""
    p = PRICES.get(model.partition("@")[0])
    if not p:
        return 0.0
    cached = usage.get("cached_input_tokens", 0)
    fresh = usage.get("input_tokens", 0) - cached
    out = usage.get("output_tokens", 0)
    if model.startswith("gemini"):
        # Gemini reports thinking separately from the answer; OpenAI counts it
        # inside output_tokens already.
        out += usage.get("reasoning_tokens", 0)
    total = (fresh * p["input"] + cached * p["cached_input"] + out * p["output"]) / 1e6
    return total * BATCH_DISCOUNT if usage.get("batch") else total
