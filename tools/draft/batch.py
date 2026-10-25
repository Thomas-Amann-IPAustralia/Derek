#!/usr/bin/env python3
"""Draft pages through the providers' batch APIs, at half price (ADR-027).

    python tools/draft/batch.py submit --model gpt-6.1-sol --all --dry-run
    python tools/draft/batch.py submit --model gpt-6.1-sol --all
    python tools/draft/batch.py submit --model gemini-3.8-flash --effort low --all
    python tools/draft/batch.py submit --model gpt-6.1-sol PAGE --limit 1   # a smoke test
    python tools/draft/batch.py collect      # poll every open batch once; write what finished
    python tools/draft/batch.py status

The same request as ``draft_spans.py`` makes live (``providers.openai_body``,
``providers.gemini_body``), answered within 24 hours instead of minutes, and
read by the same parsers and the same pointer check into the same cache. A
page drafted by batch is indistinguishable from one drafted live except that
its usage carries ``batch: 1``, so ``providers.cost`` reports the half price
actually paid.

Each submission is recorded in ``golden/drafts/batches/`` before anything is
sent: the provider's batch id, and which page each request is. ``collect`` reads
those manifests, so a batch outlives the session that submitted it. A page
already cached, or waiting in an open batch, is never sent twice (ADR-003).

A page that fails inside a batch (cut off, refused, not valid JSON) is reported
by ``collect`` and left uncached, so the next ``submit`` picks it up. Nothing is
retried automatically: a retry is a new bill.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from drafting import (  # noqa: E402
    DRAFTS, EFFORT, PROMPT_SHA256, PROMPT_VERSION, draft_path, drafter_id, eligible_pages,
    input_sha256, load_blind, load_page, output_schema, prompt_sha256, record, resolve,
    system_prompt, user_message, write_record,
)
from draft_spans import PROVIDER_MAX_TOKENS, status  # noqa: E402
from providers import (  # noqa: E402
    PROVIDERS, DraftError, _gemini_headers, _openai_headers, _post, cost, gemini_body,
    openai_body, parse_gemini, parse_openai,
)

BATCHES = DRAFTS / "batches"
OPENAI = "https://api.openai.com/v1"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------

def manifests() -> list[tuple[Path, dict]]:
    if not BATCHES.exists():
        return []
    return [(p, json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(BATCHES.glob("*.json"))]


def _save(path: Path, m: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def in_flight(drafter: str) -> set[str]:
    """Pages waiting in a batch that has not been collected."""
    return {r["page"] for _, m in manifests()
            if m["drafter"] == drafter and not m.get("collected")
            for r in m["requests"]}


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------

def _multipart(fields: dict[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                f"{v}\r\n").encode("utf-8")
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/jsonl\r\n\r\n").encode("utf-8")
    out += content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return out, f"multipart/form-data; boundary={boundary}"


def _openai_upload(jsonl: bytes) -> str:
    body, ctype = _multipart({"purpose": "batch"}, "drafts.jsonl", jsonl)
    req = urllib.request.Request(f"{OPENAI}/files", data=body, method="POST",
                                 headers={"Content-Type": ctype, **_openai_headers()})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))["id"]


def submit_openai(model: str, effort: str, reqs: list[dict], system: str, schema: dict) -> str:
    lines = []
    for r in reqs:
        body = openai_body(model, system, r["_user"], schema, effort=effort,
                           max_tokens=PROVIDER_MAX_TOKENS["openai"])
        lines.append(json.dumps({"custom_id": r["id"], "method": "POST",
                                 "url": "/v1/responses", "body": body}, ensure_ascii=False))
    file_id = _openai_upload(("\n".join(lines) + "\n").encode("utf-8"))
    out = _post(f"{OPENAI}/batches", {"input_file_id": file_id, "endpoint": "/v1/responses",
                                       "completion_window": "24h",
                                       "metadata": {"prompt": PROMPT_VERSION, "model": model,
                                                    "effort": effort}},
                _openai_headers())
    return out["id"]


def submit_gemini(model: str, effort: str, reqs: list[dict], system: str, schema: dict) -> str:
    requests = [{
        "request": gemini_body(system, r["_user"], schema, effort=effort,
                               max_tokens=PROVIDER_MAX_TOKENS["gemini"], stream=False),
        "metadata": {"key": r["id"]},
    } for r in reqs]
    out = _post(f"{GEMINI}/models/{model}:batchGenerateContent", {
        "batch": {"display_name": f"derek-{PROMPT_VERSION}-{model}-{effort}",
                  "input_config": {"requests": {"requests": requests}}},
    }, _gemini_headers())
    return out["name"]


def submit(args) -> int:
    if prompt_sha256() != PROMPT_SHA256:
        raise SystemExit("the prompt has changed without a version bump; see draft_spans.py")
    model, effort = args.model, args.effort
    drafter = drafter_id(model, effort)
    provider = PROVIDERS[model]
    if provider not in ("openai", "gemini"):
        raise SystemExit(f"{model} has no batch path here")

    pages = args.pages or (sorted(load_blind()) if args.blind else
                           eligible_pages() if args.all else [])
    if not pages:
        raise SystemExit("name pages, or use --all or --blind")
    waiting = in_flight(drafter)
    todo = [p for p in pages if p not in waiting and status(p, model, effort) == "new"]
    if args.limit:
        todo = todo[:args.limit]
    chars = sum(len(user_message(load_page(p))) for p in todo)
    print(f"{len(pages)} page(s): {len(todo)} to submit to the {provider} batch API "
          f"as {drafter} ({chars:,} characters of page), "
          f"{len([p for p in pages if p in waiting])} already in an open batch.")
    if args.dry_run or not todo:
        print("--dry-run: nothing sent." if args.dry_run else "Nothing to do.")
        return 0

    system, schema = system_prompt(), output_schema()
    reqs = []
    for n, rel in enumerate(todo):
        page = load_page(rel)
        reqs.append({"id": f"p{n:04d}", "page": rel,
                     "input_sha256": input_sha256(page, model, effort),
                     "_user": user_message(page)})
    send = submit_openai if provider == "openai" else submit_gemini
    batch_id = send(model, effort, reqs, system, schema)
    at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_id = batch_id.rsplit("/", 1)[-1]
    path = BATCHES / f"{at}-{drafter.replace('@', '-')}-{safe_id}.json"
    _save(path, {
        "provider": provider, "model": model, "effort": effort, "drafter": drafter,
        "prompt_version": PROMPT_VERSION, "batch_id": batch_id, "submitted_at": at,
        "requests": [{k: v for k, v in r.items() if not k.startswith("_")} for r in reqs],
        "collected": False,
    })
    print(f"submitted {batch_id}; manifest {path.name}")
    return 0


# ---------------------------------------------------------------------------
# Collecting
# ---------------------------------------------------------------------------

def _download(file_id: str) -> str:
    req = urllib.request.Request(f"{OPENAI}/files/{file_id}/content", headers=_openai_headers())
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read().decode("utf-8")


def _results_openai(m: dict) -> tuple[str, dict[str, tuple]]:
    """(state, {request id: parsed answer or the error})."""
    b = _post(f"{OPENAI}/batches/{m['batch_id']}", None, _openai_headers(), method="GET")
    state = b.get("status", "")
    if state not in ("completed", "expired", "cancelled", "failed"):
        counts = b.get("request_counts") or {}
        return f"{state} ({counts.get('completed', 0)}/{counts.get('total', 0)} done)", {}
    out: dict[str, tuple] = {}
    for fid in (b.get("output_file_id"), b.get("error_file_id")):
        if not fid:
            continue
        for line in _download(fid).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            resp = row.get("response") or {}
            if row.get("error") or resp.get("status_code") != 200:
                why = row.get("error") or (resp.get("body") or {}).get("error")
                out[row["custom_id"]] = ("error", str(why)[:300])
                continue
            try:
                out[row["custom_id"]] = ("ok", parse_openai(resp["body"], m["model"]))
            except DraftError as exc:
                out[row["custom_id"]] = ("error", str(exc))
    if state == "failed" and not out:
        errs = (b.get("errors") or {}).get("data") or []
        return "failed: " + "; ".join(e.get("message", "") for e in errs)[:300], {}
    return state, out


def _results_gemini(m: dict) -> tuple[str, dict[str, tuple]]:
    b = _post(f"{GEMINI}/{m['batch_id']}", None, _gemini_headers(), method="GET")
    meta = b.get("metadata") or {}
    state = b.get("state") or meta.get("state") or ("DONE" if b.get("done") else "")
    if not state.endswith(("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED", "DONE")):
        return state, {}
    dest = b.get("dest") or (b.get("response") or {}) or (meta.get("output") or {})
    inlined = dest.get("inlinedResponses") or []
    if isinstance(inlined, dict):
        inlined = inlined.get("inlinedResponses") or []
    out: dict[str, tuple] = {}
    for n, row in enumerate(inlined):
        rid = (row.get("metadata") or {}).get("key") or m["requests"][n]["id"]
        if row.get("error"):
            out[rid] = ("error", json.dumps(row["error"])[:300])
            continue
        try:
            out[rid] = ("ok", parse_gemini([row.get("response") or {}], m["model"],
                                           PROVIDER_MAX_TOKENS["gemini"]))
        except DraftError as exc:
            out[rid] = ("error", str(exc))
    if state.endswith("FAILED") and not out:
        return f"{state}: {json.dumps(b.get('error') or meta.get('error'))[:300]}", {}
    return state, out


def collect(_args) -> int:
    open_ = [(p, m) for p, m in manifests() if not m.get("collected")]
    if not open_:
        print("No open batches.")
        return 0
    spent, failures, waiting = 0.0, [], 0
    for path, m in open_:
        state, results = (_results_openai if m["provider"] == "openai" else _results_gemini)(m)
        if not results:
            print(f"{m['drafter']} {m['batch_id']}: {state}")
            waiting += 1
            continue
        wrote = 0
        for r in m["requests"]:
            got = results.get(r["id"])
            if got is None:
                failures.append((r["page"], "no result in the batch output"))
                continue
            kind, val = got
            if kind == "error":
                failures.append((r["page"], val))
                continue
            page = load_page(r["page"])
            if input_sha256(page, m["model"], m["effort"]) != r["input_sha256"]:
                failures.append((r["page"], "the page or prompt changed since submission"))
                continue
            raw, served, usage, stop = val
            usage["batch"] = 1
            resolved = resolve(page, raw)
            write_record(record(page, raw, resolved, served_model=served, usage=usage,
                                stop_reason=stop, model=m["model"], effort=m["effort"]),
                         draft_path(r["page"], model=m["drafter"]))
            spent += cost(m["drafter"], usage)
            wrote += 1
        m["collected"] = True
        m["collected_state"] = state
        m["written"] = wrote
        _save(path, m)
        print(f"{m['drafter']} {m['batch_id']}: {state}; wrote {wrote} of "
              f"{len(m['requests'])} draft(s)")
    if spent:
        print(f"cost of what was collected: about ${spent:.2f} at batch prices")
    if failures:
        print(f"\n{len(failures)} page(s) failed and are left uncached "
              f"(the next submit sends them again):", file=sys.stderr)
        for page, why in failures:
            print(f"  {page}: {why}", file=sys.stderr)
    return 1 if failures else 0


def show(_args) -> int:
    for _, m in manifests():
        done = f"collected ({m.get('collected_state')}, {m.get('written', 0)} written)" \
            if m.get("collected") else "open"
        print(f"{m['submitted_at']} {m['drafter']:28} {len(m['requests']):4} page(s) "
              f"{m['batch_id']}  {done}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("submit")
    s.add_argument("pages", nargs="*")
    s.add_argument("--model", required=True, choices=sorted(PROVIDERS))
    s.add_argument("--effort", default=EFFORT)
    s.add_argument("--all", action="store_true")
    s.add_argument("--blind", action="store_true")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("collect")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    return {"submit": submit, "collect": collect, "status": show}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
