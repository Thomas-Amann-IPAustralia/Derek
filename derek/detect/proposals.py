"""Check proposed Tier 0 matchers, and let a named human adopt the ready ones.

    python -m derek.detect.proposals                   # the report: ready or blocked, and why
    python -m derek.detect.proposals adopt UID [UID…] --by TA

A proposal (``ledger/proposals/*.jsonl``) is a declarative matcher for a rule
that is already accepted. It is data, never code (ADR-009), so it is safe to
review whoever drafted it, and ``proposed_by`` says who did. It reaches the
ledger only through ``adopt``, which a person runs with their initials (D-10),
and only when three things hold, each the answer to a documented Octavius
failure:

1. **The rule's own examples agree** (ADR-004). Every violating example fires,
   no compliant one does, and there is *at least one* violating example. A
   matcher with nothing it must catch passes any harness vacuously, which is
   postmortem F4 in its purest form.
2. **The manual does not trip it** (ADR-011). Its density on the Style Manual's
   own prose, raw and un-suppressed (D-14), is within the proposal's budget, and
   any budget above zero carries a written justification.
3. **The examples were not written for it** (D-1). They are the rule's examples
   in the ledger: the manual's own, or spans a human marked. A proposal cannot
   bring examples of its own.

``adopt`` writes ``detection`` and ``validation`` and appends a history entry.
From then on the CI dogfood gate runs the rule on every push.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from derek.detect.engine import check_examples
from derek.detect.matchers import MatcherError, compile_matcher
from derek.ledger.model import Detection, ReviewStatus
from derek.ledger.store import load_ledger, write_ledger

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "ledger" / "rules.jsonl"
PROPOSALS = REPO / "ledger" / "proposals"


@dataclass
class Check:
    uid: str
    statement: str
    proposal: dict
    blockers: list[str] = field(default_factory=list)
    examples: tuple[int, int] = (0, 0)             # compliant, violating
    missed: list[str] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)
    findings: int = 0
    density: float = 0.0
    samples: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.blockers


def load_proposals(root: Path = PROPOSALS) -> list[dict]:
    out = []
    for path in sorted(root.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                row["_source"] = f"{path.relative_to(REPO)}:{n}"
                out.append(row)
    return out


def check(proposals: list[dict], rules, docs=None, words: int | None = None) -> list[Check]:
    if docs is None:
        from derek.eval.dogfood import load_documents
        docs, words = load_documents()
    out = []
    for p in proposals:
        rule = rules.get(p["uid"])
        c = Check(p["uid"], rule.source.statement if rule else p.get("statement", ""), p)
        out.append(c)
        if rule is None:
            c.blockers.append("no such rule in the ledger")
            continue
        if rule.review.status not in ReviewStatus.LOADABLE:
            c.blockers.append(f"the rule is {rule.review.status}, and only accepted rules load (D-10)")
        try:
            m = compile_matcher(p["method"], p["matcher"])
        except (MatcherError, KeyError) as exc:
            c.blockers.append(f"matcher refused: {exc}")
            continue

        ex = check_examples(m, rule.compliant_examples, rule.violating_examples)
        c.examples = (len(rule.compliant_examples), len(rule.violating_examples))
        c.missed, c.false_alarms = ex.missed, ex.false_alarms
        if not rule.violating_examples:
            c.blockers.append("no violating example, so nothing shows the matcher catches "
                              "anything (ADR-004). The manual gives none for this rule; one "
                              "has to come from a reviewed source, not from the proposal (D-1)")
        if ex.missed:
            c.blockers.append(f"{len(ex.missed)} violating example(s) do not fire")
        if ex.false_alarms:
            c.blockers.append(f"{len(ex.false_alarms)} compliant example(s) fire")

        for rel, doc in docs:
            for b in doc.blocks:
                if not b.lintable:
                    continue
                for a, z in m.find(b.text):
                    c.findings += 1
                    if len(c.samples) < 6:
                        c.samples.append((rel, b.text[max(0, a - 40):z + 30].replace("\n", " ")))
        c.density = 10_000 * c.findings / words if words else 0.0
        budget = float(p.get("expected_density") or 0.0)
        if c.density > budget + 1e-9:
            c.blockers.append(f"fires {c.density:.2f} times per 10,000 words of the manual, "
                              f"over its budget of {budget} (ADR-011)")
        if budget > 0 and not (p.get("density_justification") or "").strip():
            c.blockers.append("a budget above zero needs a written justification (ADR-011)")
    return out


def report(checks: list[Check]) -> str:
    ready = [c for c in checks if c.ready]
    lines = ["# Tier 0 matcher proposals", "",
             f"{len(checks)} proposal(s): **{len(ready)} ready to adopt**, "
             f"{len(checks) - len(ready)} blocked. Adopt with "
             f"`python -m derek.detect.proposals adopt UID --by <initials>`.", "",
             "| Rule | Examples (✓/✗) | On the manual | Status |", "|---|---|---|---|"]
    for c in checks:
        status = "**ready**" if c.ready else "blocked"
        lines.append(f"| {c.statement[:60]} `{c.uid}` | {c.examples[0]}/{c.examples[1]} "
                     f"| {c.findings} ({c.density:.2f}/10k) | {status} |")
    lines.append("")
    for c in checks:
        lines += [f"## {c.statement}", "", f"`{c.uid}` · {c.proposal['method']} · "
                  f"budget {c.proposal.get('expected_density', 0)}/10k words", "",
                  f"```json\n{json.dumps(c.proposal['matcher'], ensure_ascii=False, indent=1)}\n```", ""]
        if c.proposal.get("limits"):
            lines += [f"**Limits.** {c.proposal['limits']}", ""]
        if c.proposal.get("density_justification"):
            lines += [f"**Budget.** {c.proposal['density_justification']}", ""]
        for b in c.blockers:
            lines.append(f"- ⛔ {b}")
        for x in c.missed:
            lines.append(f"- missed: {x[:120]}")
        for x in c.false_alarms:
            lines.append(f"- fires on a compliant example: {x[:120]}")
        for rel, ctx in c.samples:
            lines.append(f"- on the manual, `{rel}`: …{ctx}…")
        lines.append("")
    return "\n".join(lines) + "\n"


def adopt(uids: list[str], by: str, *, ledger: Path = LEDGER, checks: list[Check]) -> int:
    rules = load_ledger(ledger)
    by_uid = {c.uid: c for c in checks}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    done = 0
    for uid in uids:
        c = by_uid.get(uid)
        if c is None:
            print(f"  {uid}: no proposal", file=sys.stderr)
            continue
        if not c.ready:
            print(f"  {uid}: not adopted, blocked: {'; '.join(c.blockers)}", file=sys.stderr)
            continue
        rule = rules[uid]
        p = c.proposal
        rule.detection = Detection(tier=0, method=p["method"], matcher=dict(p["matcher"]),
                                   detectable=True, not_detectable_reason="")
        v = rule.validation
        v.status, v.examples_pass = "pass", True
        v.dogfood_density = round(c.density, 4)
        v.expected_density = float(p.get("expected_density") or 0.0)
        v.last_run = now
        v.notes = (p.get("density_justification") or "").strip()
        # The review status does not change; the record of who adopted what does.
        rule.review.transition(rule.review.status, by, now,
                               f"adopted Tier 0 matcher from {p.get('_source', 'a proposal')}")
        done += 1
        print(f"  {uid}: adopted ({c.statement[:60]})")
    if done:
        write_ledger(ledger, rules.values())
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("adopt", help="write ready proposals into the ledger")
    a.add_argument("uids", nargs="+")
    a.add_argument("--by", required=True, help="your initials (D-10: a human adopts)")
    args = ap.parse_args(argv)

    rules = load_ledger(LEDGER)
    checks = check(load_proposals(), rules)
    if args.cmd == "adopt":
        by = "".join(ch for ch in args.by.upper() if ch.isalnum())[:6]
        if not by:
            ap.error("--by needs your initials")
        n = adopt(args.uids, by, checks=checks)
        print(f"{n} matcher(s) adopted.")
        return 0 if n == len(args.uids) else 1
    sys.stdout.write(report(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
