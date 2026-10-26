#!/usr/bin/env python3
"""The owner's yardstick for alpha selection (docs/10-alpha-rule-selection.md).

    python tools/select/yardstick.py draw --n 200      # golden/selection/yardstick.json
    python tools/select/yardstick.py record FILE.json  # verdicts -> golden/selection/verdicts.jsonl

A uniform random sample of the rules the alpha could draw from, for the owner to
mark "in the alpha", "not yet" or "unsure", with reasons. Every automated
selection stage is checked against these verdicts before it is used on the rest
of the ledger, so the sample has to be uniform over the same population those
stages run on.

The population is every accepted or amended rule, less two sets:

* ``referencing-and-attribution/`` pages, which the owner cut from the alpha
  (2026-10-26). A verdict on a rule that cannot be in the alpha measures nothing.
* The 50 rules of the ADR-027 human check (``golden/consensus/sample.json``),
  which the owner has already reviewed. Drawing them again would spend a
  verdict on a rule that already has one.

The seed is recorded, and the draw is over uid-sorted rules, so the same ledger
and seed give the same sample. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "ledger" / "rules.jsonl"
CONSENSUS_SAMPLE = REPO / "golden" / "consensus" / "sample.json"
OUT = REPO / "golden" / "selection" / "yardstick.json"
VERDICTS = REPO / "golden" / "selection" / "verdicts.jsonl"

EXCLUDED_SECTIONS = ("referencing-and-attribution/",)
VERDICT_VALUES = ("alpha", "not_yet", "unsure")
# The reasons are the Stage B questions in docs/10, phrased as the owner sees
# them, so a verdict and a model's answer can be compared reason by reason.
REASONS = (
    "needs_nearby_sentences", "needs_whole_document", "needs_outside_knowledge",
    "formatting_markdown_lacks", "depends_on_doc_type", "readers_would_disagree",
    "rare_in_practice", "not_about_text", "rule_is_wrong",
)


def _ledger() -> list[dict]:
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def draw(n: int, seed: str, out: Path) -> int:
    reviewed = {r["uid"] for r in json.loads(CONSENSUS_SAMPLE.read_text(encoding="utf-8"))["rules"]}
    population = sorted(
        (r for r in _ledger()
         if r["review"]["status"] in ("accepted", "amended")
         and not r["source"]["page_path"].startswith(EXCLUDED_SECTIONS)
         and r["uid"] not in reviewed),
        key=lambda r: r["uid"],
    )
    picked = random.Random(seed).sample(population, min(n, len(population)))
    rows = [{
        "uid": r["uid"],
        "page_path": r["source"]["page_path"],
        "heading_path": r["source"]["heading_path"],
        "statement": r["source"]["statement"],
        "body_excerpt": r["source"]["body_excerpt"],
        "violation_condition": r["violation_condition"],
        "context_preconditions": r["context_preconditions"],
        "compliant_examples": r["compliant_examples"],
        "violating_examples": r["violating_examples"],
        "unit": r["unit"], "applies_to": r["applies_to"], "clarity": r["clarity"],
        "direction": r["direction"], "modality": r["modality"],
        "tier": r["detection"]["tier"],
        "url": r["source"]["url"],
    } for r in picked]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "seed": seed, "population": len(population),
        "excluded": {"sections": list(EXCLUDED_SECTIONS), "already_reviewed": len(reviewed)},
        "rules": rows,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"sampled {len(rows)} of {len(population)} rules (seed {seed!r}) -> {out}")
    return 0


def record(path: Path, by: str) -> int:
    """Append verdicts from an export (a JSON list of {uid, verdict, reasons, note, at}).

    Refuses the whole file if any row names a uid outside the sample or a value
    outside the vocabulary, so a typo cannot quietly become a verdict.
    """
    sample = {r["uid"] for r in json.loads(OUT.read_text(encoding="utf-8"))["rules"]}
    rows = json.loads(path.read_text(encoding="utf-8"))
    bad = [r for r in rows
           if r.get("uid") not in sample or r.get("verdict") not in VERDICT_VALUES
           or any(x not in REASONS for x in r.get("reasons", []))]
    if bad:
        for r in bad:
            print(f"refused: {json.dumps(r, ensure_ascii=False)}", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with VERDICTS.open("a", encoding="utf-8") as f:
        for r in sorted(rows, key=lambda r: r["uid"]):
            f.write(json.dumps({
                "uid": r["uid"], "verdict": r["verdict"],
                "reasons": sorted(r.get("reasons", [])), "note": r.get("note", ""),
                "by": by, "at": r.get("at") or now,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"recorded {len(rows)} verdict(s) by {by} -> {VERDICTS}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--n", type=int, default=200)
    d.add_argument("--seed", default="alpha-yardstick")
    d.add_argument("--out", type=Path, default=OUT)
    rec = sub.add_parser("record")
    rec.add_argument("file", type=Path)
    rec.add_argument("--by", default="TA")
    args = ap.parse_args(argv)
    if args.command == "draw":
        return draw(args.n, args.seed, args.out)
    return record(args.file, args.by)


if __name__ == "__main__":
    sys.exit(main())
