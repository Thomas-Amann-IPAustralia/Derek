"""Run the accepted Tier 0 rules over a text file.

    python -m derek.detect FILE.txt
    python -m derek.detect -          # stdin

Prints one line per finding, raw (D-14). Only accepted rules with an adopted
matcher run (D-10), and confidence is blank until calibrated (D-12).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from derek.detect.document import Document
from derek.detect.engine import detect, load
from derek.ledger.store import load_ledger

LEDGER = Path(__file__).resolve().parents[2] / "ledger" / "rules.jsonl"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")

    rules = load_ledger(args.ledger)
    loaded = load(rules)
    findings = detect(Document.from_text(text), loaded)
    for f in findings:
        line = text.count("\n", 0, f.start) + 1
        print(f"{line}:{f.start}-{f.end}  {f.severity:<10} {rules[f.rule_uid].source.statement[:60]}"
              f"  «{f.quote}»")
    print(f"{len(findings)} finding(s) from {len(loaded.rules)} rule(s); "
          f"{len(loaded.skipped)} accepted rule(s) have no Tier 0 matcher yet.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
