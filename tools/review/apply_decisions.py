#!/usr/bin/env python3
"""Replay decisions made on the static dashboard into the ledger (ADR-022).

    python tools/review/apply_decisions.py ledger/inbox/*.jsonl
    python tools/review/apply_decisions.py export.jsonl --dry-run

The dashboard on GitHub Pages has no server to write to, so a reviewer's
decisions queue up in their browser and come out as a JSONL op log. This
replays that log into `ledger/rules.jsonl` and `ledger/example_reviews.jsonl`.

**The guard rails live here, not in the browser.** Every decision goes through
the same `_apply` the local server uses, so a rule still cannot be kept without
`clarity`, an `ambiguous_resolvable` reading still has to be written down, and
`uid` / `source` / `derivation` are still un-writable from a reviewer's hands
(ADR-008). The page checks the same things while you work so you find out then
rather than later, but this is where it is enforced — the browser is a drafting
surface, the ledger is the record.

**Replaying is safe.** Every op carries an `op_id`; the ones applied are
recorded in `ledger/review_ops.jsonl` and skipped on any later run. Uploading
the same export twice does nothing the second time.

**The timestamp is the reviewer's, not the upload's.** `_apply` stamps history
with `server._now()`; for an offline session that would record when the file
happened to be uploaded, which is not a fact anyone wants. The op's own `at` is
substituted for the duration of that op instead — see `_at`.

Op log format, one JSON object per line:

    {"op": "decide",  "op_id": "…", "by": "TA", "at": "2026-09-21T04:11:02Z",
     "uid": "f8f3ddac1581e5c6", "patch": {"review_status": "accepted", …}}
    {"op": "undo",    "op_id": "…", "by": "TA", "at": "…", "uid": "…"}
    {"op": "example", "op_id": "…", "by": "TA", "at": "…", "verdict": "accept",
     "item": {"id": "…", "rule_uid": "…", "origin": "…", "claimed": "…"},
     "reasons": [], "note": ""}
    {"op": "meta", …}                      ← provenance; ignored on replay

Stdlib only.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
OPS_LOG = REPO / "ledger" / "review_ops.jsonl"

KNOWN_OPS = frozenset({"decide", "undo", "example", "meta"})


def _load_server():
    """Import tools/review/server.py, which is not on a package path."""
    spec = importlib.util.spec_from_file_location(
        "derek_review_server", HERE / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _at(server, stamp: str):
    """Make `server._now()` return the reviewer's timestamp for one op.

    The alternative is a ledger that says every offline decision was made the
    moment someone got round to uploading the file, which would quietly break
    the thing review history is for.
    """
    try:
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        yield                                  # unparseable: keep the real clock
        return
    original = server._now
    server._now = lambda: stamp
    try:
        yield
    finally:
        server._now = original


def read_ops(paths: list[Path]) -> list[dict]:
    """Read op logs, in reviewer-time order so history reads chronologically."""
    ops: list[dict] = []
    for path in paths:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: not JSON — {exc}") from exc
            if not isinstance(row, dict) or "op" not in row:
                raise SystemExit(f"{path}:{n}: no 'op' field — is this a Derek export?")
            row.setdefault("_source", path.name)
            ops.append(row)
    ops.sort(key=lambda o: (str(o.get("at") or ""), str(o.get("op_id") or "")))
    return ops


def applied_ids(path: Path | None = None) -> set[str]:
    path = path or OPS_LOG
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            with contextlib.suppress(json.JSONDecodeError, KeyError):
                seen.add(json.loads(line)["op_id"])
    return seen


def apply_ops(
    ops: list[dict],
    server,
    *,
    skip_invalid: bool = False,
    already: set[str] | None = None,
) -> dict:
    """Apply ops to the in-memory ledger. Returns a report; writes nothing."""
    already = already if already is not None else applied_ids()
    rules = server.load_ledger(server.LEDGER)

    report: dict = {
        "rules": rules, "examples": [], "applied": [],
        "skipped": [], "errors": [], "reviewers": set(),
    }

    for op in ops:
        kind = op.get("op")
        op_id = str(op.get("op_id") or "")
        where = f"{op.get('_source', '?')} {kind} {op_id[:8] or '—'}"

        if kind == "meta":
            continue
        if kind not in KNOWN_OPS:
            report["errors"].append(f"{where}: unknown op kind {kind!r}")
            continue
        if not op_id:
            report["errors"].append(f"{where}: op has no op_id, so it cannot be "
                                    "de-duplicated on a later run")
            continue
        if op_id in already:
            report["skipped"].append(f"{where}: already applied")
            continue
        already.add(op_id)                      # a repeat inside one file, too

        by = server.clean_initials(op.get("by", ""))
        report["reviewers"].add(by)
        stamp = str(op.get("at") or "")

        try:
            if kind == "decide":
                rule = rules.get(op.get("uid", ""))
                if rule is None:
                    raise KeyError(
                        f"unknown uid {op.get('uid')!r} — the ledger has been rebuilt "
                        "since this decision was made"
                    )
                with _at(server, stamp):
                    server._apply(rule, dict(op.get("patch") or {}), by)

            elif kind == "undo":
                rule = rules.get(op.get("uid", ""))
                if rule is None:
                    raise KeyError(f"unknown uid {op.get('uid')!r}")
                if rule.review.status == server.ReviewStatus.PROPOSED:
                    raise ValueError("nothing to undo on that rule")
                rule.review.transition(
                    server.ReviewStatus.PROPOSED, by,
                    stamp or server._now(), f"undone by {by}",
                )

            elif kind == "example":
                item = op.get("item") or {}
                if not item.get("id"):
                    raise ValueError("example verdict has no item id")
                if not op.get("verdict"):
                    raise ValueError("example verdict has no verdict")
                report["examples"].append({
                    "id": item["id"],
                    "rule_uid": item.get("rule_uid", ""),
                    "origin": item.get("origin", ""),
                    "claimed": item.get("claimed", ""),
                    "verdict": op["verdict"],
                    "reasons": op.get("reasons", []),
                    "note": op.get("note", ""),
                    "by": by,
                    "at": stamp or server._now(),
                })

            report["applied"].append(op)
        except Exception as exc:                # noqa: BLE001
            message = f"{where}: {type(exc).__name__}: {exc}"
            if not skip_invalid:
                report["errors"].append(message)
            else:
                report["skipped"].append(message)

    return report


def commit(report: dict, server, *, source: str = "") -> None:
    """Write the ledger, the example verdicts and the op log."""
    server.write_ledger(server.LEDGER, report["rules"].values())
    for row in report["examples"]:
        server._append(server.EXAMPLE_VERDICTS, row)
    stamped = server._now()
    for op in report["applied"]:
        row = {k: v for k, v in op.items() if not k.startswith("_")}
        row["applied_at"] = stamped
        row["applied_from"] = op.get("_source", source)
        server._append(OPS_LOG, row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path, help="exported op logs (JSONL)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and report; write nothing")
    ap.add_argument("--skip-invalid", action="store_true",
                    help="apply what is valid instead of refusing the whole file")
    args = ap.parse_args(argv)

    missing = [p for p in args.files if not p.exists()]
    if missing:
        print("No such file: " + ", ".join(str(p) for p in missing), file=sys.stderr)
        return 1

    server = _load_server()
    server.load_glossary()                      # same drift check as startup
    ops = read_ops(args.files)
    report = apply_ops(ops, server, skip_invalid=args.skip_invalid)

    for line in report["skipped"]:
        print(f"  skipped  {line}")
    for line in report["errors"]:
        print(f"  REFUSED  {line}", file=sys.stderr)

    decisions = sum(1 for o in report["applied"] if o["op"] == "decide")
    undos = sum(1 for o in report["applied"] if o["op"] == "undo")
    who = ", ".join(sorted(report["reviewers"])) or "nobody"

    if report["errors"]:
        print(
            f"\nRefusing to write: {len(report['errors'])} op(s) would not survive the "
            "ledger's guard rails.\nFix the export, or re-run with --skip-invalid to "
            "apply the rest.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{decisions} decision(s), {undos} undo(s), "
          f"{len(report['examples'])} example verdict(s) from {who}"
          f"{' — dry run, nothing written' if args.dry_run else ''}")

    if args.dry_run or not report["applied"]:
        return 0

    commit(report, server)
    counts: dict[str, int] = {}
    for rule in report["rules"].values():
        counts[rule.review.status] = counts.get(rule.review.status, 0) + 1
    print("Ledger now: " + ", ".join(
        f"{k} {v}" for k, v in sorted(counts.items()) if v))
    print(f"Wrote {server.LEDGER.relative_to(REPO)} and "
          f"{OPS_LOG.relative_to(REPO)}. Commit the diff.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
