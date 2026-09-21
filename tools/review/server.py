#!/usr/bin/env python3
"""Rule triage UI (ADR-008).

    python tools/review/server.py        # http://localhost:8765

Pass 1 of review: disqualification. For each candidate you answer one
question — *is this detectable in text at all?* — and set `unit`,
`applies_to` and `clarity` accordingly. See docs/04-roadmap.md.

This is built BEFORE the rule volume grows, not after. Octavius's decisive
failure was delegating interpretation to a batch job and arriving at 3,114
rows, which is past the point where anyone can review them (postmortem F9).

Decisions are written straight to `ledger/rules.jsonl`, in canonical form,
so every decision is a git diff: reviewable, attributable, revertable, and
it survives this tool being rewritten. Deliberately not a database.

Stdlib only — no build step, no npm, nothing to install.
"""

from __future__ import annotations

import json
import os
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from derek.ledger.model import ReviewStatus, Rule  # noqa: E402
from derek.ledger.store import load_ledger, write_ledger  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "ledger" / "rules.jsonl"
INDEX = Path(__file__).parent / "index.html"
PORT = int(os.environ.get("DEREK_REVIEW_PORT", "8765"))
REVIEWER = os.environ.get("DEREK_REVIEWER") or os.environ.get("USER") or "reviewer"

# Fields a reviewer may set. Anything the pipeline owns (uid, source,
# derivation) is rejected, so a rebuild can never clobber a human decision
# and a human can never corrupt provenance.
EDITABLE = {
    "review_status", "unit", "applies_to", "clarity", "direction",
    "modality", "violation_condition", "note",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _payload(rules: dict[str, Rule]) -> dict:
    ordered = sorted(
        rules.values(),
        key=lambda r: (r.review.status != ReviewStatus.PROPOSED,
                       r.source.page_path, r.source.line_start),
    )
    counts: dict[str, int] = {}
    for r in rules.values():
        counts[r.review.status] = counts.get(r.review.status, 0) + 1
    return {
        "reviewer": REVIEWER,
        "counts": counts,
        "total": len(rules),
        "rules": [
            {
                "uid": r.uid,
                "statement": r.source.statement,
                "page": r.source.page_path,
                "heading_path": r.source.heading_path,
                "url": r.source.url,
                "body": r.source.body_excerpt,
                "form": r.derivation.statement_form,
                "modality": r.modality,
                "modality_basis": r.modality_basis,
                "clarity": r.clarity,
                "direction": r.direction,
                "unit": r.unit,
                "applies_to": r.applies_to,
                "violation_condition": r.violation_condition,
                "compliant": r.compliant_examples,
                "violating": r.violating_examples,
                "status": r.review.status,
                "note": r.review.note,
            }
            for r in ordered
        ],
    }


def _apply(rule: Rule, patch: dict) -> None:
    for key, value in patch.items():
        if key not in EDITABLE:
            raise ValueError(f"field not editable from the review UI: {key}")
    if "unit" in patch:
        rule.unit = patch["unit"]
    if "applies_to" in patch:
        rule.applies_to = patch["applies_to"] or ["any"]
    if "clarity" in patch:
        rule.clarity = patch["clarity"]
    if "direction" in patch:
        rule.direction = patch["direction"]
    if "modality" in patch:
        rule.modality = patch["modality"]
        rule.modality_basis = f"set by {REVIEWER} during review"
    if "violation_condition" in patch:
        rule.violation_condition = patch["violation_condition"]
    if (status := patch.get("review_status")):
        rule.review.transition(status, REVIEWER, _now(), patch.get("note", ""))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/rules":
            self._json(200, _payload(load_ledger(LEDGER)))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/decide":
            self._json(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            patches = json.loads(self.rfile.read(n))          # [{uid, ...}, …]
            rules = load_ledger(LEDGER)
            for patch in patches:
                uid = patch.pop("uid")
                if uid not in rules:
                    raise KeyError(f"unknown uid: {uid}")
                _apply(rules[uid], patch)
            write_ledger(LEDGER, rules.values())
            self._json(200, {"ok": True, "counts": _payload(rules)["counts"]})
        except Exception as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *args) -> None:  # keep the console readable
        pass


def main() -> int:
    if not LEDGER.exists():
        print("No ledger yet. Run: python -m derek.extract.build")
        return 1
    rules = load_ledger(LEDGER)
    pending = sum(1 for r in rules.values() if r.review.status == ReviewStatus.PROPOSED)
    url = f"http://localhost:{PORT}"
    print(f"Derek review — {len(rules)} rules, {pending} awaiting triage")
    print(f"Reviewer: {REVIEWER}   (set DEREK_REVIEWER to change)")
    print(f"Serving {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
