#!/usr/bin/env python3
"""A focused second reading of the rules only one drafter found (ADR-027).

    python tools/draft/verify.py run PAGE [PAGE ...]       # a few pages, live
    python tools/draft/verify.py submit --all [--dry-run]  # every unsettled page, batched
    python tools/draft/verify.py collect

The drafting pass asks a model to find every rule on a page. A cheap drafter at
low effort reads less of the page than a strong one, so most of what only the
strong one found was never looked at by the other at all: on the full batch, 626
of 969 single-model rules were ones Flash said nothing about. This asks the
other family a narrower question, page by page: here are the rules both
drafters agreed on, and here are rules only one found; for each of the latter,
is it a rule of its own under docs/08, or a restatement, section, advice,
permission, duplicate, not-text or description?

**What a verdict decides** (the owner's decision, 2026-10-25): a candidate the
second reading calls a rule is taken, because two families then agree it exists.
Any other verdict sends it to the adjudicator, with the verdict attached. A
verdict from the same family as the finder counts for nothing, so only rules
found by OpenAI are verified, by Gemini; a Gemini-only rule goes to the
adjudicator as before.

The second reading only judges. It never adds a rule, moves one, or changes a
tag or an example: those stay the finder's, pointer-checked as before.

A cache, like the drafts (ADR-003): one call per (page, prompt version, model,
effort, candidates), keyed on a hash of the exact input. The prompt is
hash-pinned by tests/test_verify.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from drafting import POLICY, REPO, eligible_pages, load_page, render_page  # noqa: E402
from providers import PAIR, PROVIDERS, DraftError, cost  # noqa: E402

VERIFY = REPO / "golden" / "consensus" / "verify"
VERIFY_VERSION = "v2"
VERIFY_SHA256 = "e185c99edfd872570ba718a74ee49e250c2e70d90f09df6c067f76029d3c6dca"
VERIFIER = ("gemini-3.8-flash", "medium")   # reads what OpenAI alone found
MAX_TOKENS = 32000

# No `duplicate` (G-6): the reader sees one page, so a verdict that a rule
# "belongs on another page" is a guess about a page it cannot see. v1 offered
# it and used it on five of seven commas.md candidates. Cross-page duplicates
# are found by comparing the finished pages instead (ADR-027's cleanup pass).
VERDICTS = ["rule", "restatement", "section", "advice", "permission", "not_text",
            "description"]


def family(drafter: str) -> str:
    return PROVIDERS[drafter.partition("@")[0]]


def verifier_for(finder: str) -> tuple[str, str] | None:
    """The second reader for a rule one drafter found, or None if none qualifies."""
    model, effort = VERIFIER
    return (model, effort) if PROVIDERS[model] != family(finder) else None


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def system_prompt() -> str:
    policy = POLICY.read_text(encoding="utf-8")
    return f"""\
You are checking a draft inventory of the rules on one page of the Australian \
Government Style Manual, for Derek, a checker that flags text breaking a Style \
Manual rule. Two models drafted the page independently. The rules they agreed on \
are settled. You are given the ones only one model found, and you decide for each \
whether it is a rule of its own.

The page arrives as numbered blocks, one per line: `[block_id] KIND  text`. After \
it come the AGREED rules (settled, for reference) and the CANDIDATES (yours to \
judge), each with an id, the block it sits in, its quote, and the violation \
condition its finder wrote.

## The policy you apply

<policy>
{policy}
</policy>

## Your verdict for each candidate

- `rule`: one thing a checker would flag and cite, which no AGREED rule and no \
earlier candidate already covers.
- `restatement`: the same check as another rule in other words, or one of its \
conditions or exceptions (G-2, G-4). Put that rule's id (A… or C…) in `restates`.
- `section`: a heading or lead-in that only groups the rules under it (G-1).
- `advice`: tells the writer what to do, not what the text must be (G-5).
- `permission`: relaxes a rule and can never itself be broken (G-3).
- `not_text`: about images, video, files, layout or publication format, not words.
- `description`: describes English and instructs nothing.

Judge each candidate on this page's text, not on the finder's violation \
condition, which may overstate it. You cannot see the other pages of the \
manual, so do not judge whether a rule belongs on another page: that is \
checked separately once every page is done. A rule this page states is a \
`rule` here even if another page might state it too. When two candidates are the same check, call \
the first `rule` and the others `restatement` of it. Be strict: a rule kept \
that should not be is a false finding in every document Derek checks, and a \
missed one costs less. Give a one-line `note` with the policy point that decided \
each verdict.
"""


def output_schema() -> dict:
    return {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "verdict": {"type": "string", "enum": VERDICTS},
                "restates": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["id", "verdict", "restates", "note"],
            "additionalProperties": False,
        }}},
        "required": ["verdicts"],
        "additionalProperties": False,
    }


def prompt_sha256() -> str:
    body = json.dumps({"system": system_prompt(), "schema": output_schema()},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# One page's question
# ---------------------------------------------------------------------------

def candidates(plan: dict, finder: str) -> list[dict]:
    """The single-model rules on a page that ``finder`` found, in page order."""
    return [r for r in plan["rules"] if r.get("single") and r["found_by"] == [finder]]


def user_message(rel: str, plan: dict, cands: list[dict]) -> str:
    page = load_page(rel)
    lines = [render_page(page), "", "AGREED"]
    agreed = [r for r in plan["rules"] if not r.get("single")]
    for n, r in enumerate(agreed, 1):
        lines.append(f"A{n} [{r['anchor']['block_id']}] {r['anchor']['quote']}")
    if not agreed:
        lines.append("(none)")
    lines += ["", "CANDIDATES"]
    for n, r in enumerate(cands, 1):
        lines.append(f"C{n} [{r['anchor']['block_id']}] {r['anchor']['quote']}")
        if r.get("violation_condition"):
            lines.append(f"    finder's violation condition: {r['violation_condition']}")
    return "\n".join(lines)


def input_sha256(user: str, model: str, effort: str) -> str:
    body = json.dumps({"version": VERIFY_VERSION, "prompt_sha256": prompt_sha256(),
                       "model": model, "effort": effort, "user": user},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def cache_path(rel: str, model: str, effort: str) -> Path:
    return VERIFY / VERIFY_VERSION / f"{model}@{effort}" / (rel[:-3] + ".json")


def load_verdicts(rel: str, plan: dict, finder: str) -> dict[str, dict]:
    """Verdicts by the candidate's rid, if a current verification is cached."""
    who = verifier_for(finder)
    if who is None:
        return {}
    cands = candidates(plan, finder)
    if not cands:
        return {}
    path = cache_path(rel, *who)
    if not path.exists():
        return {}
    rec = json.loads(path.read_text(encoding="utf-8"))
    if rec.get("input_sha256") != input_sha256(user_message(rel, plan, cands), *who):
        return {}            # the candidates changed: the verdicts are about other rules
    by_id = {v["id"]: v for v in rec.get("verdicts", [])}
    out = {}
    for n, r in enumerate(cands, 1):
        v = by_id.get(f"C{n}")
        if v and v.get("verdict") in VERDICTS:
            out[r["rid"]] = v | {"by": f"{who[0]}@{who[1]}"}
    return out


def write(rel: str, user: str, model: str, effort: str, parsed: dict, served: str,
          usage: dict) -> None:
    path = cache_path(rel, model, effort)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"page_path": rel, "version": VERIFY_VERSION, "prompt_sha256": prompt_sha256(),
           "input_sha256": input_sha256(user, model, effort), "model": model,
           "served_model": served, "effort": effort, "usage": usage,
           "verdicts": parsed.get("verdicts", [])}
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


# ---------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------

def _questions(pages: list[str]) -> list[tuple[str, str, str, str]]:
    """(page, user message, model, effort) for every page that needs a verdict."""
    import consensus

    if prompt_sha256() != VERIFY_SHA256:
        # ADR-003: a prompt nobody versioned is a prompt nobody reviewed.
        raise SystemExit("the second-reading prompt changed: bump VERIFY_VERSION and "
                         "VERIFY_SHA256 in tools/draft/verify.py together")

    ready, _ = consensus._drafted(pages)
    out = []
    for rel in sorted(ready):
        plan = consensus.page_plan(rel, ready[rel])
        for finder in PAIR:
            who = verifier_for(finder)
            cands = candidates(plan, finder)
            if who is None or not cands:
                continue
            user = user_message(rel, plan, cands)
            path = cache_path(rel, *who)
            if path.exists() and json.loads(path.read_text())["input_sha256"] == \
                    input_sha256(user, *who):
                continue
            out.append((rel, user, *who))
    return out


def _pages(args) -> list[str]:
    import consensus

    if args.pages:
        return args.pages
    if args.all:
        settled = consensus.settled_pages()
        return [p for p in eligible_pages() if p not in settled]
    raise SystemExit("name pages, or use --all")


def run_live(args) -> int:
    from providers import call_gemini

    spent = 0.0
    for rel, user, model, effort in _questions(_pages(args)):
        try:
            parsed, served, usage, _ = call_gemini(model, system_prompt(), user, output_schema(),
                                                   effort=effort, max_tokens=MAX_TOKENS)
        except DraftError as exc:
            print(f"  FAILED {rel}: {exc}", file=sys.stderr)
            continue
        write(rel, user, model, effort, parsed, served, usage)
        spent += cost(model, usage)
        print(f"  {rel}: {len(parsed.get('verdicts', []))} verdict(s)")
    print(f"cost: about ${spent:.2f}")
    return 0


BATCHES = VERIFY / "batches"


def submit(args) -> int:
    import batch

    qs = _questions(_pages(args))
    print(f"{len(qs)} page(s) to verify")
    if args.dry_run or not qs:
        return 0
    model, effort = VERIFIER
    reqs = [{"id": f"v{n:04d}", "page": rel, "_user": user,
             "input_sha256": input_sha256(user, model, effort)}
            for n, (rel, user, _, _) in enumerate(qs)]
    batch_id = batch.submit_gemini(model, effort, reqs, system_prompt(), output_schema(),
                                   MAX_TOKENS)
    at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    BATCHES.mkdir(parents=True, exist_ok=True)
    path = BATCHES / f"{at}-{batch_id.rsplit('/', 1)[-1]}.json"
    path.write_text(json.dumps({
        "provider": "gemini", "model": model, "effort": effort, "batch_id": batch_id,
        "submitted_at": at, "version": VERIFY_VERSION, "collected": False,
        "requests": [{k: v for k, v in r.items() if k != "_user"} for r in reqs],
    }, indent=1) + "\n", encoding="utf-8")
    print(f"submitted {batch_id}")
    return 0


def collect(_args) -> int:
    import batch

    failed = 0
    for path in sorted(BATCHES.glob("*.json")) if BATCHES.exists() else []:
        m = json.loads(path.read_text(encoding="utf-8"))
        if m.get("collected"):
            continue
        state, results = batch._results_gemini(m)
        if not results:
            print(f"{m['batch_id']}: {state}")
            continue
        qs = {rel: user for rel, user, _, _ in _questions([r["page"] for r in m["requests"]])}
        spent, wrote = 0.0, 0
        for r in m["requests"]:
            kind, val = results.get(r["id"], ("error", "no result"))
            user = qs.get(r["page"])
            if kind == "error" or user is None or \
                    input_sha256(user, m["model"], m["effort"]) != r["input_sha256"]:
                failed += 1
                print(f"  {r['page']}: {val if kind == 'error' else 'question changed'}",
                      file=sys.stderr)
                continue
            parsed, served, usage, _ = val
            usage["batch"] = 1
            write(r["page"], user, m["model"], m["effort"], parsed, served, usage)
            spent += cost(m["model"], usage)
            wrote += 1
        m["collected"], m["written"] = True, wrote
        path.write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
        print(f"{m['batch_id']}: {state}; wrote {wrote}; about ${spent:.2f}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "submit"):
        s = sub.add_parser(name)
        s.add_argument("pages", nargs="*")
        s.add_argument("--all", action="store_true")
        s.add_argument("--dry-run", action="store_true")
    sub.add_parser("collect")
    args = ap.parse_args(argv)
    if args.command == "run":
        return run_live(args)
    return {"submit": submit, "collect": collect}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
