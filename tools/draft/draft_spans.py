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

Needs ``requirements-draft.txt`` and an ``ANTHROPIC_API_KEY`` (or any credential
the SDK resolves). ``.github/workflows/draft-spans.yml`` runs it from a browser,
with the key as a repository secret.

Refusal fallback is on (``fallbacks: "default"``): if the model declines a page,
the API re-runs it on Anthropic's recommended fallback model. Declines on Style
Manual text should be vanishingly rare, but a fallback changes which model
drafted the page, so every record carries ``served_model`` and ``draft_score``
reports any page where it differs from ``model``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from drafting import (  # noqa: E402
    EFFORT, MAX_TOKENS, MODEL, PROMPT_SHA256, PROMPT_VERSION, draft_path, eligible_pages,
    input_sha256, load_blind, load_page, output_schema, prompt_sha256, record, resolve,
    system_prompt, user_message, write_record,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class DraftError(RuntimeError):
    """A page that could not be drafted. Names the page and why."""


def call_model(system: str, user: str, schema: dict) -> tuple[dict, str, dict, str]:
    """One page, one request. Returns (parsed JSON, served model, usage, stop reason)."""
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

    if args.dry_run:
        system = system_prompt()
        for rel in todo:
            print(f"  {rel}: {len(user_message(load_page(rel)))} chars of page, "
                  f"{len(system)} chars of (cached) instructions")
        print("--dry-run: nothing called, nothing written.")
        return 0

    system, schema = system_prompt(), output_schema()
    failed: list[tuple[str, str]] = []
    totals: dict[str, int] = {}
    for rel in todo:
        page = load_page(rel)
        try:
            raw, served, usage, stop = call_model(system, user_message(page), schema)
        except DraftError as exc:
            failed.append((rel, str(exc)))
            print(f"  FAILED {rel}: {exc}", file=sys.stderr)
            continue
        resolved = resolve(page, raw)
        write_record(record(page, raw, resolved, served_model=served, usage=usage,
                            stop_reason=stop), draft_path(rel))
        for k, v in usage.items():
            totals[k] = totals.get(k, 0) + v
        note = f" (served by {served})" if served != MODEL else ""
        print(f"  {rel}: {len(resolved.rules)} rule(s), {len(resolved.not_rules)} "
              f"not-rule(s), {len(resolved.refused)} pointer(s) refused{note}")

    if totals:
        print("usage: " + ", ".join(f"{k} {v:,}" for k, v in sorted(totals.items())))
    if failed:
        print(f"\n{len(failed)} page(s) failed and were not written.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
