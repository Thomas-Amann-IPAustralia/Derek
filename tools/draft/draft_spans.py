#!/usr/bin/env python3
"""Draft rule spans for Style Manual pages with a model (ADR-025).

    python tools/draft/draft_spans.py PAGE [PAGE ...]    # these pages
    python tools/draft/draft_spans.py --blind             # the blind pages, for scoring
    python tools/draft/draft_spans.py --next 5            # the next 5 pages nobody has drafted
    python tools/draft/draft_spans.py --all
    python tools/draft/draft_spans.py --next 5 --dry-run  # what it would do; no key needed

Each page is drafted once per (prompt version, model) and cached under
``golden/drafts/`` (ADR-003). A cached page is skipped, so re-running is free. A
draft is a proposal the annotator shows as a seed; it becomes part of the golden
set only when a human accepts it there, and nothing in extraction reads it.

Needs ``requirements-draft.txt`` and the pinned model's key: ``OPENAI_API_KEY``
for a ``gpt-`` model, ``ANTHROPIC_API_KEY`` for a ``claude-`` one.
``.github/workflows/draft-spans.yml`` runs it from a browser, with the key as a
repository secret.

**Money.** Every call is priced as it returns, from the usage the provider
reports and the list prices in ``PRICES``, and the run stops before a page
whose estimate would take it past ``--max-usd``. ``--dry-run`` prints that
estimate and spends nothing. A model with no price here cannot be metered, so
it runs only with ``--max-usd 0``, which means "unmetered, I accept that".

On Anthropic, refusal fallback is on (``fallbacks: "default"``): a declined page
is re-run on the recommended fallback model. OpenAI has no fallback, so a
refusal fails the page. Either way every record carries ``served_model``, and
``draft_score`` names any page drafted by a model other than the pinned one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import os  # noqa: E402

from drafting import (  # noqa: E402
    EFFORT, MAX_TOKENS, MODEL, PROMPT_SHA256, PROMPT_VERSION, draft_path, eligible_pages,
    input_sha256, load_blind, load_page, output_schema, prompt_sha256, record, resolve,
    system_prompt, user_message, write_record,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# The base URL is fixed here rather than read from the environment, so an
# ambient OPENAI_BASE_URL cannot send the manual's text somewhere else.
OPENAI_BASE_URL = "https://api.openai.com/v1"

# USD per million tokens, from the provider's model and prompt-caching pages on
# 2026-10-10. Output includes reasoning tokens. A cache write is billed instead
# of, not on top of, the uncached rate.
PRICES = {
    "gpt-6.1-sol": {"input": 2.00, "cache_write": 2.50, "cached": 0.10, "output": 10.00},
}

# For the estimate only: about 3.5 characters a token on this text, and an
# answer up to about three times the page plus room for reasoning. Deliberately
# high, so the guard stops early rather than late.
CHARS_PER_TOKEN = 3.5
OUTPUT_PER_PAGE_TOKEN = 3.0
REASONING_ALLOWANCE = 6000


class DraftError(RuntimeError):
    """A page that could not be drafted. Names the page and why."""


def provider(model: str = MODEL) -> str:
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("claude-"):
        return "anthropic"
    raise SystemExit(f"no adapter for model {model!r}")


def cost_usd(usage: dict, model: str = MODEL) -> float | None:
    """What a call cost at list price, or None when the model is not priced here."""
    price = PRICES.get(model)
    if price is None:
        return None
    cached = usage.get("cached_tokens", 0)
    written = usage.get("cache_write_tokens", 0)
    uncached = usage.get("input_tokens", 0) - cached - written
    return (uncached * price["input"] + written * price["cache_write"]
            + cached * price["cached"] + usage.get("output_tokens", 0) * price["output"]) / 1e6


def estimate_usd(system: str, user: str, model: str = MODEL) -> float | None:
    """A pessimistic price for one page, before calling anything."""
    price = PRICES.get(model)
    if price is None:
        return None
    page = len(user) / CHARS_PER_TOKEN
    tokens_in = page + len(system) / CHARS_PER_TOKEN + 1000      # + the schema
    tokens_out = page * OUTPUT_PER_PAGE_TOKEN + REASONING_ALLOWANCE
    return (tokens_in * price["input"] + tokens_out * price["output"]) / 1e6


def call_model(system: str, user: str, schema: dict) -> tuple[dict, str, dict, str]:
    """One page, one request. Returns (parsed JSON, served model, usage, stop reason)."""
    if provider() == "openai":
        return _call_openai(system, user, schema)
    return _call_anthropic(system, user, schema)


def _call_openai(system: str, user: str, schema: dict) -> tuple[dict, str, dict, str]:
    import openai      # lazily: CI and the tests never install the SDK

    client = openai.OpenAI(base_url=OPENAI_BASE_URL, max_retries=4, timeout=1800)
    response = client.responses.create(
        model=MODEL,
        # The instructions and the schema are identical for every page, so they
        # form the cached prefix and only the page is new input after the first.
        instructions=system,
        input=user,
        reasoning={"effort": EFFORT},
        text={"format": {"type": "json_schema", "name": "rule_draft", "schema": schema,
                         "strict": True}},
        max_output_tokens=MAX_TOKENS,
        # The provider keeps no copy of the request. It is the manual's public
        # text, but nothing here needs it stored, so nothing is.
        store=False,
    )
    return parse_openai(response)


def parse_openai(response) -> tuple[dict, str, dict, str]:
    """A Responses API result -> (parsed JSON, served model, usage, stop reason).

    Separate from the call so the tests can exercise it with no SDK installed.
    """
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", "") == "refusal":
                raise DraftError(f"declined: {getattr(part, 'refusal', '')}")
    status = getattr(response, "status", "")
    if status != "completed":
        reason = getattr(getattr(response, "incomplete_details", None), "reason", "") or status
        if reason == "max_output_tokens":
            raise DraftError(f"ran out of output at {MAX_TOKENS} tokens; the draft is incomplete")
        raise DraftError(f"the response did not complete: {reason}")
    try:
        parsed = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise DraftError(f"the model's output is not the JSON asked for: {exc}") from exc

    u = response.usage
    details_in = getattr(u, "input_tokens_details", None)
    details_out = getattr(u, "output_tokens_details", None)
    usage = {
        "input_tokens": int(u.input_tokens or 0),
        "cached_tokens": int(getattr(details_in, "cached_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(details_in, "cache_write_tokens", 0) or 0),
        "output_tokens": int(u.output_tokens or 0),
        "reasoning_tokens": int(getattr(details_out, "reasoning_tokens", 0) or 0),
    }
    return parsed, response.model, usage, status


def _call_anthropic(system: str, user: str, schema: dict) -> tuple[dict, str, dict, str]:
    import anthropic   # lazily: CI and the tests never install the SDK

    client = anthropic.Anthropic(max_retries=4)
    # Streaming because a long page's draft plus adaptive thinking can run to
    # tens of thousands of tokens, past a non-streaming request's HTTP timeout.
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT,
                       "format": {"type": "json_schema", "schema": schema}},
        # The system prompt is identical for every page, so it is cached: only
        # the page itself is new input after the first request.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise DraftError(f"declined by every model in the fallback chain: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise DraftError(f"ran out of output at {MAX_TOKENS} tokens; the draft is incomplete")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError(f"the model's output is not the JSON asked for: {exc}") from exc

    u = message.usage
    usage = {k: int(getattr(u, k) or 0) for k in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens") if hasattr(u, k)}
    return parsed, message.model, usage, message.stop_reason


def status(rel: str) -> str:
    """cached | stale | new, for one page against the current prompt and model."""
    path = draft_path(rel)
    if not path.exists():
        return "new"
    rec = json.loads(path.read_text(encoding="utf-8"))
    return "cached" if rec.get("input_sha256") == input_sha256(load_page(rel)) else "stale"


def choose(args) -> list[str]:
    pages = eligible_pages()
    if args.pages:
        unknown = [p for p in args.pages if p not in pages]
        if unknown:
            raise SystemExit(f"not eligible rule-source pages: {unknown}")
        return args.pages
    if args.blind:
        return sorted(load_blind())
    if args.all:
        return pages
    if args.next:
        from derek.extract.golden import load_golden

        annotated = set(load_golden().spans)
        todo = [p for p in pages if p not in annotated and status(p) == "new"]
        return todo[:args.next]
    raise SystemExit("name pages, or use --blind, --next N or --all")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--blind", action="store_true", help="the pages in golden/blind.json")
    ap.add_argument("--next", type=int, default=0,
                    help="the next N eligible pages that nobody has annotated or drafted")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="report; call nothing")
    ap.add_argument("--force", action="store_true",
                    help="redraw a cached page (a new call, and a new bill)")
    ap.add_argument("--max-usd", type=float, default=1.50,
                    help="stop before a page that would take this run past this "
                         "many dollars at list price (default 1.50; 0 = unmetered)")
    args = ap.parse_args(argv)

    # ADR-003: a prompt nobody versioned is a prompt nobody reviewed. Refuse to
    # pay for one.
    if prompt_sha256() != PROMPT_SHA256:
        raise SystemExit(
            f"the prompt has changed (sha256 {prompt_sha256()[:12]}, pinned "
            f"{PROMPT_SHA256[:12]}). Bump PROMPT_VERSION and PROMPT_SHA256 in "
            f"tools/draft/drafting.py together, so the change gets its own cache "
            f"directory and its own score.")

    pages = choose(args)
    plan = [(rel, status(rel)) for rel in pages]
    todo = [rel for rel, st in plan if st != "cached" or args.force]
    stale = [rel for rel, st in plan if st == "stale"]
    print(f"{len(pages)} page(s): {len(todo)} to draft with {MODEL} "
          f"(prompt {PROMPT_VERSION}, effort {EFFORT}), {len(pages) - len(todo)} cached.")
    if stale and not args.force:
        raise SystemExit(
            "these drafts were made from a different input under the same prompt "
            "version, which should be impossible while the corpus is frozen:\n  "
            + "\n  ".join(stale) + "\nInvestigate before overwriting (--force).")

    system = system_prompt()
    if args.dry_run:
        total = 0.0
        for rel in todo:
            user = user_message(load_page(rel))
            est = estimate_usd(system, user)
            total += est or 0.0
            print(f"  {rel}: {len(user)} chars of page, {len(system)} chars of (cached) "
                  f"instructions" + (f", at most about ${est:.3f}" if est is not None else ""))
        if PRICES.get(MODEL):
            print(f"estimate: at most about ${total:.2f} at list price.")
        print("--dry-run: nothing called, nothing written.")
        return 0

    if PRICES.get(MODEL) is None and args.max_usd != 0:
        raise SystemExit(f"{MODEL} has no price in PRICES, so a budget cannot be enforced. "
                         f"Add its price, or pass --max-usd 0 to run it unmetered.")
    key = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider()]
    if not os.environ.get(key):
        raise SystemExit(f"no {key} in the environment; nothing was called.")

    schema = output_schema()
    failed: list[tuple[str, str]] = []
    totals: dict[str, int] = {}
    spent = 0.0
    for rel in todo:
        page = load_page(rel)
        user = user_message(page)
        est = estimate_usd(system, user)
        if args.max_usd and est is not None and spent + est > args.max_usd:
            print(f"  STOPPED before {rel}: ${spent:.3f} spent and this page could cost "
                  f"up to ${est:.3f}, past --max-usd {args.max_usd:.2f}.", file=sys.stderr)
            failed.append((rel, "budget"))
            break
        try:
            raw, served, usage, stop = call_model(system, user, schema)
        except DraftError as exc:
            failed.append((rel, str(exc)))
            print(f"  FAILED {rel}: {exc}", file=sys.stderr)
            continue
        cost = cost_usd(usage)
        if cost is not None:
            usage = {**usage, "cost_usd": round(cost, 6)}
            spent += cost
        resolved = resolve(page, raw)
        write_record(record(page, raw, resolved, served_model=served, usage=usage,
                            stop_reason=stop), draft_path(rel))
        for k, v in usage.items():
            if k != "cost_usd":
                totals[k] = totals.get(k, 0) + v
        note = f" (served by {served})" if not served.startswith(MODEL) else ""
        price = f", ${cost:.3f}" if cost is not None else ""
        print(f"  {rel}: {len(resolved.rules)} rule(s), {len(resolved.not_rules)} "
              f"not-rule(s), {len(resolved.refused)} pointer(s) refused{price}{note}")

    if totals:
        print("usage: " + ", ".join(f"{k} {v:,}" for k, v in sorted(totals.items())))
    if PRICES.get(MODEL):
        print(f"spent: ${spent:.3f} at list price (cap ${args.max_usd:.2f}).")
    if failed:
        print(f"\n{len(failed)} page(s) failed and were not written.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
