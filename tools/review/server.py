#!/usr/bin/env python3
"""Rule triage UI (ADR-008).

    python tools/review/server.py        # http://localhost:8765

Round 1 of review: disqualification. For each candidate the reviewer answers
one question — *is this detectable in text at all?* — and sets `unit`,
`applies_to`, `direction`, `clarity` and `modality` accordingly. See
docs/04-roadmap.md.

This is built BEFORE the rule volume grows, not after. Octavius's decisive
failure was delegating interpretation to a batch job and arriving at 3,114
rows, which is past the point where anyone can review them (postmortem F9).

Decisions are written straight to `ledger/rules.jsonl`, in canonical form,
so every decision is a git diff: reviewable, attributable, revertable, and
it survives this tool being rewritten. Deliberately not a database.

Stdlib only — no build step, no npm, nothing to install.

Three things here are not obvious, and each is deliberate:

**The scoreboard is derived, never stored.** Points and rankings are computed
from `review.history` in the ledger plus the attention-check log. There is no
score field anyone can write to, so a leaderboard cannot be inflated and
clearing browser storage cannot erase work.

**Attention checks are graded server-side.** The question is generated from
gold examples whose polarity the Style Manual already asserted, and the answer
never reaches the browser. A check whose answer is in the page is decoration.

**Undo is a transition, not an erasure.** Reverting writes a move back to
`proposed` into the same history it came from. A reviewer can change their
mind; nobody can make it look as though they never decided (ADR-008).
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from derek.extract.modality import Modality  # noqa: E402
from derek.ledger.model import (  # noqa: E402
    Clarity, DetectionHint, Direction, ReviewStatus, Rule, Unit,
)
from derek.ledger.store import load_ledger, write_ledger  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "ledger" / "rules.jsonl"
ACTIVITY = REPO / "ledger" / "review_activity.jsonl"
EXAMPLE_VERDICTS = REPO / "ledger" / "example_reviews.jsonl"
HERE = Path(__file__).parent
INDEX = HERE / "index.html"
GLOSSARY = HERE / "glossary.json"

PORT = int(os.environ.get("DEREK_REVIEW_PORT", "8765"))
DEFAULT_REVIEWER = (
    os.environ.get("DEREK_REVIEWER") or os.environ.get("USER") or "reviewer"
)

# Fields a reviewer may set. Anything the pipeline owns (uid, source,
# derivation) is rejected, so a rebuild can never clobber a human decision
# and a human can never corrupt provenance.
EDITABLE = {
    "review_status", "unit", "applies_to", "clarity", "direction",
    "modality", "violation_condition", "specification", "note",
    "reasons", "elapsed_ms", "detection_hint",
}

# A decision this fast was not a decision. Scored as zero and marked, so the
# scoreboard cannot be farmed by swiping and a hasty batch stays findable.
HASTY_MS = 2500

POINTS = {"decision": 10, "example": 5, "attention_pass": 25, "attention_fail": -15}

# Non-terminal statuses a reviewer may set from the UI. The rest
# (quarantined / superseded / orphaned / proposed) belong to the pipeline.
REVIEWER_STATUSES = frozenset({
    ReviewStatus.ACCEPTED, ReviewStatus.AMENDED,
    ReviewStatus.REJECTED, ReviewStatus.DEFERRED,
})

_INITIALS = re.compile(r"[^A-Z0-9_-]")

# nonce -> (correct_answer, issued_at). Attention checks only; in memory on
# purpose, so a restart voids outstanding questions rather than leaving
# gradeable tokens lying around.
_PENDING: dict[str, tuple[str, datetime]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_initials(raw: str) -> str:
    return _INITIALS.sub("", (raw or "").strip().upper())[:6] or "ANON"


# ---------------------------------------------------------------------------
# Glossary — the reviewer-facing explanation of every option
# ---------------------------------------------------------------------------

def load_glossary() -> dict:
    """Read glossary.json and refuse to start if it has drifted from the code.

    A reviewer being shown a button nobody explained is how you get decisions
    made on a guess. The vocabularies live in derek/ledger/model.py; this
    asserts the explanations still cover them.
    """
    data = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    buckets = data["buckets"]
    expected = {
        "review_status": ReviewStatus.ALL,
        "unit": Unit.ALL,
        "clarity": Clarity.ALL,
        "direction": Direction.ALL,
        "modality": frozenset(Modality.ALL),
        "detection_hint": DetectionHint.ALL,
    }
    problems = []
    for bucket, vocabulary in expected.items():
        if bucket not in buckets:
            problems.append(f"glossary has no entry for '{bucket}'")
            continue
        documented = set(buckets[bucket]["options"])
        for value in sorted(vocabulary - documented):
            problems.append(f"{bucket}: '{value}' exists in code but is unexplained")
        for value in sorted(documented - set(vocabulary)):
            problems.append(f"{bucket}: '{value}' is explained but no longer exists")
    if problems:
        raise SystemExit(
            "tools/review/glossary.json is out of step with derek/ledger/model.py:\n  "
            + "\n  ".join(problems)
            + "\n\nEvery option a reviewer can pick must say what it means."
        )
    return data


def reviewer_options(glossary: dict) -> dict[str, list[str]]:
    """Option order for the UI, straight from the glossary so the two agree."""
    out: dict[str, list[str]] = {}
    for bucket, spec in glossary["buckets"].items():
        if spec.get("read_only"):
            continue                      # shown on the card, never chosen
        out[bucket] = [
            key for key, opt in spec["options"].items()
            if not opt.get("system_only") and not opt.get("read_only")
        ]
    return out


# ---------------------------------------------------------------------------
# Ledger view
# ---------------------------------------------------------------------------

def _rule_view(r: Rule) -> dict:
    return {
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
        "specification": r.specification,
        "violation_condition": r.violation_condition,
        "compliant": r.compliant_examples,
        "violating": r.violating_examples,
        "status": r.review.status,
        "note": r.review.note,
        "decided_by": r.review.decided_by,
        "decided_at": r.review.decided_at,
        "history": r.review.history,
        # Whether the manual itself supplied a polarised example pair is the
        # strongest signal on the card, so it is surfaced rather than inferred.
        "has_gold_pair": bool(r.compliant_examples and r.violating_examples),
    }


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
        "counts": counts,
        "total": len(rules),
        "rules": [_rule_view(r) for r in ordered],
    }


def _apply(rule: Rule, patch: dict, reviewer: str) -> None:
    for key in patch:
        if key not in EDITABLE:
            raise ValueError(f"field not editable from the review UI: {key}")

    if "unit" in patch:
        if patch["unit"] not in Unit.ALL:
            raise ValueError(f"unknown unit: {patch['unit']!r}")
        rule.unit = patch["unit"]
    if "applies_to" in patch:
        rule.applies_to = list(patch["applies_to"]) or ["any"]
    if "clarity" in patch:
        if patch["clarity"] not in Clarity.ALL:
            raise ValueError(f"unknown clarity: {patch['clarity']!r}")
        rule.clarity = patch["clarity"]
    if "direction" in patch:
        if patch["direction"] not in Direction.ALL:
            raise ValueError(f"unknown direction: {patch['direction']!r}")
        rule.direction = patch["direction"]
    if "modality" in patch:
        if patch["modality"] not in Modality.ALL:
            raise ValueError(f"unknown modality: {patch['modality']!r}")
        rule.modality = patch["modality"]
        rule.modality_basis = f"set by {reviewer} during review"
    if "detection_hint" in patch:
        # ADR-010: the tier is a routing decision recorded at review, not a
        # runtime fallback. The hint is the reviewer's closed-vocabulary answer
        # to "how would this be checked?"; only the tier reaches the ledger.
        if patch["detection_hint"] not in DetectionHint.ALL:
            raise ValueError(f"unknown detection hint: {patch['detection_hint']!r}")
        rule.detection.tier = DetectionHint.TIER[patch["detection_hint"]]
    if "violation_condition" in patch:
        rule.violation_condition = patch["violation_condition"]
    if "specification" in patch:
        # ADR-017: the manual's wording is never edited. A reviewer's
        # restatement lives beside it and is what detectors implement.
        rule.specification = patch["specification"]

    status = patch.get("review_status")
    if not status:
        return
    if status not in REVIEWER_STATUSES:
        raise ValueError(f"status not settable from the review UI: {status!r}")

    note = patch.get("note", "")
    if reasons := [r for r in patch.get("reasons", []) if r]:
        joined = ", ".join(reasons)
        note = f"[{joined}] {note}".strip()
    if patch.get("elapsed_ms") is not None and patch["elapsed_ms"] < HASTY_MS:
        note = (note + " (hasty)").strip()

    # ADR-017 again: an interpretation that was made has to be written down,
    # or the next person cannot tell an assumption from a reading.
    #
    # It has to be written down in `specification`, not in the note. This check
    # used to accept any of the three, and four decisions landed with the
    # interpretation in `note` alone — which the schema rejects
    # (`clarity: ambiguous_resolvable` requires `specification`), so CI went red,
    # and which `Rule.effective_statement` would have silently ignored: detection
    # implements `specification or source.statement`, so an interpretation in a
    # note would have left the detector matching the ambiguous original. That is
    # the Octavius shape — a rule that does not do what its record says.
    if rule.clarity == Clarity.AMBIGUOUS_RESOLVABLE and not rule.specification:
        raise ValueError(
            "clarity 'ambiguous_resolvable' means an interpretation was made — "
            "write it down in 'your interpretation', not the note: that field "
            "is what detection implements, and a note is not"
        )
    if status in (ReviewStatus.ACCEPTED, ReviewStatus.AMENDED):
        if rule.clarity == Clarity.UNREVIEWED:
            raise ValueError("set clarity before keeping a rule")

    rule.review.transition(status, reviewer, _now(), note)

    if rule.clarity == Clarity.AMBIGUOUS_RESOLVABLE:
        rule.disambiguation_log.append({
            "by": reviewer,
            "at": _now(),
            "assumption": rule.specification,
        })


# ---------------------------------------------------------------------------
# Activity log — attention checks and example verdicts
# ---------------------------------------------------------------------------

def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Scoreboard — derived from the record, never stored
# ---------------------------------------------------------------------------

def _within(stamp: str, since: datetime | None) -> bool:
    if since is None:
        return True
    try:
        return datetime.fromisoformat(stamp) >= since
    except (TypeError, ValueError):
        return False


def leaderboard(rules: dict[str, Rule], window: str) -> dict:
    """Rank reviewers by work actually recorded in the ledger.

    Computed rather than stored, so it cannot be gamed and survives anyone
    clearing their browser. Every point traces back to a line in a git diff.
    """
    now = datetime.now(timezone.utc)
    since = {
        "day": now - timedelta(days=1),
        "week": now - timedelta(days=7),
        "all": None,
    }.get(window, now - timedelta(days=1))

    board: dict[str, dict] = {}

    def slot(who: str) -> dict:
        return board.setdefault(who, {
            "initials": who, "decisions": 0, "hasty": 0, "examples": 0,
            "checks_passed": 0, "checks_failed": 0, "score": 0,
        })

    for rule in rules.values():
        for move in rule.review.history:
            if move.get("to") == ReviewStatus.PROPOSED:
                continue                      # an undo is not work
            if not _within(move.get("at", ""), since):
                continue
            who = clean_initials(move.get("by", ""))
            entry = slot(who)
            entry["decisions"] += 1
            if "(hasty)" in (move.get("note") or ""):
                entry["hasty"] += 1
            else:
                entry["score"] += POINTS["decision"]

    for row in _read_jsonl(ACTIVITY):
        if not _within(row.get("at", ""), since):
            continue
        entry = slot(clean_initials(row.get("by", "")))
        if row.get("kind") == "attention":
            key = "checks_passed" if row.get("correct") else "checks_failed"
            entry[key] += 1
            entry["score"] += POINTS[
                "attention_pass" if row.get("correct") else "attention_fail"
            ]

    for row in _read_jsonl(EXAMPLE_VERDICTS):
        if not _within(row.get("at", ""), since):
            continue
        entry = slot(clean_initials(row.get("by", "")))
        entry["examples"] += 1
        entry["score"] += POINTS["example"]

    ranked = sorted(board.values(), key=lambda e: (-e["score"], e["initials"]))
    for i, entry in enumerate(ranked, 1):
        entry["rank"] = i
        checks = entry["checks_passed"] + entry["checks_failed"]
        entry["accuracy"] = (
            round(100 * entry["checks_passed"] / checks) if checks else None
        )
    return {"window": window, "board": ranked}


def agreement(rules: dict[str, Rule]) -> dict:
    """How often two reviewers independently reached the same verdict.

    The point of asking for initials. Low agreement means the options are not
    being read the same way, which is a problem with the glossary or the
    queue — not with either reviewer.
    """
    both = agreed = 0
    for rule in rules.values():
        verdicts: dict[str, str] = {}
        for move in rule.review.history:
            if move.get("to") in REVIEWER_STATUSES:
                verdicts[clean_initials(move.get("by", ""))] = move["to"]
        if len(verdicts) > 1:
            both += 1
            agreed += len(set(verdicts.values())) == 1
    return {
        "double_reviewed": both,
        "agreed": agreed,
        "rate": round(100 * agreed / both) if both else None,
    }


# ---------------------------------------------------------------------------
# Attention checks — generated from gold data, graded server-side
# ---------------------------------------------------------------------------

def make_attention_check(rules: dict[str, Rule], glossary: dict) -> dict:
    """A question with a known answer, drawn from real data where possible.

    The polarity variety is the good one: a Style Manual example with its
    label hidden. The manual already asserted the answer, so the check tests
    attention against ground truth rather than against a puzzle someone made
    up. The glossary variety is the fallback and teaches while it tests.
    """
    # Only rules whose WORDING states the rule can be asked about. A heading
    # admitted on its examples alone is usually a topic label ("Centuries",
    # "Symbols"), and "does this follow the rule 'Centuries'?" has no answer.
    # An unanswerable check does not measure attention, it just punishes it.
    def askable(r: Rule) -> bool:
        return (
            r.derivation.statement_form != "exemplified"
            and 24 <= len(r.source.statement) <= 110
            and any(len(x) >= 18 for x in r.compliant_examples)
            and any(len(x) >= 18 for x in r.violating_examples)
        )

    paired = [r for r in rules.values() if askable(r)]
    nonce = secrets.token_urlsafe(9)

    if paired and random.random() < 0.75:
        rule = random.choice(paired)
        violating = random.random() < 0.5
        pool = rule.violating_examples if violating else rule.compliant_examples
        sentence = random.choice([x for x in pool if len(x) >= 18])
        answer = "violating" if violating else "compliant"
        question = {
            "nonce": nonce,
            "kind": "polarity",
            "prompt": "Does this follow the rule, or break it?",
            "rule": rule.source.statement,
            "subject": sentence,
            "choices": [
                {"key": "compliant", "label": "Follows the rule"},
                {"key": "violating", "label": "Breaks the rule"},
            ],
            "note": "Taken from the Style Manual's own Write this / Not this block.",
        }
    else:
        bucket = random.choice(["unit", "clarity", "direction", "modality"])
        spec = glossary["buckets"][bucket]
        pickable = [
            (key, opt) for key, opt in spec["options"].items()
            if not opt.get("system_only") and opt.get("means")
        ]
        correct_key, correct_opt = random.choice(pickable)
        distractors = [o for k, o in pickable if k != correct_key]
        random.shuffle(distractors)
        choices = [{"key": correct_key, "label": correct_opt["label"]}] + [
            {"key": f"d{i}", "label": o["label"]} for i, o in enumerate(distractors[:3])
        ]
        random.shuffle(choices)
        answer = correct_key
        question = {
            "nonce": nonce,
            "kind": "glossary",
            "prompt": f"Which “{spec['title']}” option means this?",
            "rule": correct_opt["means"],
            "subject": "",
            "choices": choices,
            "note": "Straight from the field guide. Open it any time — it is not cheating.",
        }

    _PENDING[nonce] = (answer, datetime.now(timezone.utc))
    # Keep the pending table small; a check nobody answered in an hour is gone.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    for key in [k for k, (_, at) in _PENDING.items() if at < cutoff]:
        _PENDING.pop(key, None)
    return question


def grade_attention_check(nonce: str, answer: str, reviewer: str) -> dict:
    expected = _PENDING.pop(nonce, None)
    if expected is None:
        return {"ok": False, "error": "that check has expired — take another"}
    correct = answer == expected[0]
    _append(ACTIVITY, {
        "kind": "attention", "by": reviewer, "at": _now(),
        "correct": correct, "answered": answer, "expected": expected[0],
    })
    return {"ok": True, "correct": correct, "expected": expected[0],
            "points": POINTS["attention_pass" if correct else "attention_fail"]}


# ---------------------------------------------------------------------------
# Example queue — gold examples now, synthetic examples later
# ---------------------------------------------------------------------------

SYNTHETIC = REPO / "ledger" / "training_candidates.jsonl"


def example_queue(rules: dict[str, Rule]) -> dict:
    """Items for the example-checking screen.

    Today it serves the gold examples harvested from the manual's own
    Write this / Not this blocks, because those are what the dogfood gate and
    the confidence calibration will be measured against (ADR-011, ADR-013) and
    nobody has read them end to end. The moment
    `ledger/training_candidates.jsonl` exists, the same screen serves that
    instead — identical shape, identical decisions, no second tool to learn.
    """
    if SYNTHETIC.exists():
        rows = _read_jsonl(SYNTHETIC)
        items = [
            {
                "id": row.get("id") or f"syn-{i}",
                "origin": "synthetic",
                "rule_uid": row.get("rule_uid", ""),
                "rule": row.get("rule", ""),
                "text": row.get("text", ""),
                "claimed": row.get("polarity", "compliant"),
            }
            for i, row in enumerate(rows)
        ]
    else:
        items = []
        for rule in rules.values():
            for polarity, pool in (
                ("compliant", rule.compliant_examples),
                ("violating", rule.violating_examples),
            ):
                for i, text in enumerate(pool):
                    items.append({
                        "id": f"{rule.uid}-{polarity}-{i}",
                        "origin": "style_manual",
                        "rule_uid": rule.uid,
                        "rule": rule.source.statement,
                        "text": text,
                        "claimed": polarity,
                    })
        items.sort(key=lambda it: it["id"])

    done = {row["id"] for row in _read_jsonl(EXAMPLE_VERDICTS)}
    return {
        "origin": "synthetic" if SYNTHETIC.exists() else "style_manual",
        "total": len(items),
        "done": len(done),
        "items": [it for it in items if it["id"] not in done],
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    glossary: dict = {}

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _reviewer(self, payload: dict) -> str:
        return clean_initials(payload.get("reviewer") or DEFAULT_REVIEWER)

    # -- GET ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        query = parse_qs(route.query)
        try:
            if route.path in ("/", "/index.html"):
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif route.path == "/api/bootstrap":
                rules = load_ledger(LEDGER)
                self._json(200, {
                    "default_reviewer": DEFAULT_REVIEWER,
                    "glossary": self.glossary,
                    "options": reviewer_options(self.glossary),
                    "points": POINTS,
                    "hasty_ms": HASTY_MS,
                    **_payload(rules),
                })
            elif route.path == "/api/rules":
                self._json(200, _payload(load_ledger(LEDGER)))
            elif route.path == "/api/leaderboard":
                rules = load_ledger(LEDGER)
                window = (query.get("window") or ["day"])[0]
                self._json(200, {
                    **leaderboard(rules, window),
                    "agreement": agreement(rules),
                })
            elif route.path == "/api/attention":
                self._json(200, make_attention_check(load_ledger(LEDGER), self.glossary))
            elif route.path == "/api/examples":
                self._json(200, example_queue(load_ledger(LEDGER)))
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:                      # noqa: BLE001
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # -- POST --------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        try:
            payload = self._body()
            reviewer = self._reviewer(payload)

            if route.path == "/api/decide":
                rules = load_ledger(LEDGER)
                for patch in payload.get("patches", []):
                    patch = dict(patch)
                    uid = patch.pop("uid")
                    if uid not in rules:
                        raise KeyError(f"unknown uid: {uid}")
                    _apply(rules[uid], patch, reviewer)
                write_ledger(LEDGER, rules.values())
                self._json(200, {"ok": True, **_payload(rules)})

            elif route.path == "/api/undo":
                rules = load_ledger(LEDGER)
                uid = payload["uid"]
                rule = rules[uid]
                if rule.review.status == ReviewStatus.PROPOSED:
                    raise ValueError("nothing to undo on that rule")
                # Reverting is itself a decision and is recorded as one.
                rule.review.transition(
                    ReviewStatus.PROPOSED, reviewer, _now(),
                    f"undone by {reviewer}",
                )
                write_ledger(LEDGER, rules.values())
                self._json(200, {"ok": True, **_payload(rules)})

            elif route.path == "/api/attention":
                self._json(200, grade_attention_check(
                    payload.get("nonce", ""), payload.get("answer", ""), reviewer,
                ))

            elif route.path == "/api/example-verdict":
                _append(EXAMPLE_VERDICTS, {
                    "id": payload["id"],
                    "rule_uid": payload.get("rule_uid", ""),
                    "origin": payload.get("origin", ""),
                    "claimed": payload.get("claimed", ""),
                    "verdict": payload["verdict"],
                    "reasons": payload.get("reasons", []),
                    "note": payload.get("note", ""),
                    "by": reviewer,
                    "at": _now(),
                })
                self._json(200, {"ok": True})

            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:                      # noqa: BLE001
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *args) -> None:             # keep the console readable
        pass


def main() -> int:
    if not LEDGER.exists():
        print("No ledger yet. Run: python -m derek.extract.build")
        return 1

    Handler.glossary = load_glossary()                # raises if it has drifted
    rules = load_ledger(LEDGER)
    pending = sum(1 for r in rules.values() if r.review.status == ReviewStatus.PROPOSED)
    url = f"http://localhost:{PORT}"

    print(f"Derek review — {len(rules)} rules, {pending} awaiting triage")
    print(f"Reviewer: {DEFAULT_REVIEWER}   (set in the app, or DEREK_REVIEWER)")
    print(f"Serving {url}\n")
    try:
        webbrowser.open(url)
    except Exception:                                 # noqa: BLE001
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
