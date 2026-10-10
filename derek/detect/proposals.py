"""Check proposed Tier 0 matchers, show their full results, and let a named human adopt them.

    python -m derek.detect.proposals                       # the report: ready or blocked, and why
    python -m derek.detect.proposals card UID [UID…]       # one rule's full results, with a fingerprint
    python -m derek.detect.proposals adopt UID:FINGERPRINT [UID:FINGERPRINT…] --by TA

A proposal (``ledger/proposals/*.jsonl``) is a declarative matcher for a rule
that is already accepted. It is data, never code (ADR-009), so it is safe to
review whoever drafted it, and ``proposed_by`` says who did. It reaches the
ledger only through ``adopt``, which a person runs with their initials (D-10),
and only when these hold, each the answer to a documented Octavius failure:

1. **The rule's own examples agree** (ADR-004). Every violating example fires
   and no compliant one does. These are the rule's examples in the ledger: the
   manual's own, or spans a human marked.
2. **There is something to catch.** At least one violating example fires. A
   matcher with nothing it must catch passes any harness vacuously, which is
   postmortem F4 in its purest form. Where the manual gives no violating
   example, a confirmed **test sentence** may stand in for one (ADR-028).
3. **No confirmed test sentence that follows the rule fires.** A false alarm is a
   false alarm wherever the sentence came from. A test sentence the matcher
   misses does *not* block: a Tier 0 pattern often covers part of a rule and
   says which part in ``limits``, so a miss is reported in the card as measured
   coverage for the person adopting to weigh.
4. **The manual does not trip it** (ADR-011). Its density on the Style Manual's
   own prose, raw and un-suppressed (D-14), is within the proposal's budget, and
   any budget above zero carries a written justification.
5. **The examples were not written for it** (D-1). A proposal cannot bring
   examples of its own. A test sentence is written by a model that never saw the
   matcher, labelled blind by a second model family, and confirmed by a named
   person (``derek.detect.examples``).

**The card.** ``card`` prints everything about one proposal: the rule, the
matcher, every example with where it came from and whether it fired, every
test sentence and where it stands, and every hit on the manual in context. It
ends with a fingerprint, a hash of the card's own text. ``adopt`` refuses a
rule unless it is given the fingerprint of the card as it stands now, so a
person adopts exactly the results they read, and a change to any of them (a
newly confirmed sentence, an edited matcher, a corpus change) means reading the
card again (ADR-028).

**The record.** ``adopt`` writes ``ledger/adoptions/<uid>.json``: the card, the
matcher, every example with its provenance, every test sentence's state, every
manual hit, and who adopted it when. The rule's review history gains an entry
naming that file and its hash, so the ledger points at its own evidence.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from derek.detect import examples as ex
from derek.detect.engine import check_examples
from derek.detect.matchers import MatcherError, compile_matcher
from derek.ledger.model import Detection, ReviewStatus
from derek.ledger.store import load_ledger, write_ledger

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "ledger" / "rules.jsonl"
PROPOSALS = REPO / "ledger" / "proposals"
ADOPTIONS = REPO / "ledger" / "adoptions"

FINGERPRINT_CHARS = 12
CANONICAL = (ex.STYLE_MANUAL, ex.HUMAN_SPAN)


@dataclass
class Check:
    uid: str
    statement: str
    proposal: dict
    blockers: list[str] = field(default_factory=list)
    examples: tuple[int, int] = (0, 0)             # the rule's own: compliant, violating
    missed: list[str] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)
    findings: int = 0
    density: float = 0.0
    words: int = 0
    samples: list[tuple[str, str]] = field(default_factory=list)   # the first few, for the report
    hits: list[tuple[str, str]] = field(default_factory=list)      # every one, for the card
    tested: list[tuple[ex.Example, bool]] = field(default_factory=list)   # (example, fired)
    sentences: list[dict] = field(default_factory=list)   # every test sentence, with its state
    rule: object = None

    @property
    def ready(self) -> bool:
        return not self.blockers

    def tally(self, source_in, polarity: str) -> tuple[int, int]:
        """(fired, total) over the tested examples from these sources."""
        rows = [f for e, f in self.tested if e.source in source_in and e.polarity == polarity]
        return sum(rows), len(rows)


def load_proposals(root: Path = PROPOSALS) -> list[dict]:
    out = []
    for path in sorted(root.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                row["_source"] = f"{path.relative_to(REPO)}:{n}"
                out.append(row)
    return out


def _fires(matcher, text: str) -> bool:
    return not check_examples(matcher, [], [text]).missed


def check(proposals: list[dict], rules, docs=None, words: int | None = None, *,
          golden=None, records: dict | None = None, verdicts: dict | None = None) -> list[Check]:
    if docs is None:
        from derek.eval.dogfood import load_documents
        docs, words = load_documents()
    if golden is None:
        from derek.extract.golden import load_golden
        golden = load_golden()
    records = ex.load_test_sentences() if records is None else records
    verdicts = ex.load_verdicts() if verdicts is None else verdicts
    out = []
    for p in proposals:
        rule = rules.get(p["uid"])
        c = Check(p["uid"], rule.source.statement if rule else p.get("statement", ""), p, rule=rule)
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

        # 1. The rule's own examples: every one must agree.
        ex_check = check_examples(m, rule.compliant_examples, rule.violating_examples)
        c.examples = (len(rule.compliant_examples), len(rule.violating_examples))
        c.missed, c.false_alarms = ex_check.missed, ex_check.false_alarms
        if ex_check.missed:
            c.blockers.append(f"{len(ex_check.missed)} violating example(s) do not fire")
        if ex_check.false_alarms:
            c.blockers.append(f"{len(ex_check.false_alarms)} compliant example(s) fire")

        # Every example that may test it, each with where it came from.
        for e in ex.rule_examples(rule, golden=golden, records=records, verdicts=verdicts):
            c.tested.append((e, _fires(m, e.text)))
        rec = records.get(rule.uid)
        if rec:
            c.sentences = [{**s, "fires": _fires(m, s["text"])}
                           for s in ex.test_sentence_status(rec, verdicts)]

        # 2. Something to catch: a rule's own violating example, or a confirmed
        #    test sentence standing in for a missing one.
        caught_own, own = c.tally(CANONICAL, "violating")
        caught_test, tests = c.tally((ex.TEST_SENTENCE,), "violating")
        if not own and not tests:
            c.blockers.append("no violating example, so nothing shows the matcher catches "
                              "anything (ADR-004). The manual gives none for this rule; a "
                              "confirmed test sentence can stand in for one (ADR-028)")
        elif not own and not caught_test:
            c.blockers.append(f"none of the {tests} confirmed violating test sentence(s) fires, "
                              f"so nothing shows the matcher catches anything (ADR-004)")

        # 3. No false alarm on a confirmed test sentence.
        flagged, _ = c.tally((ex.TEST_SENTENCE,), "compliant")
        if flagged:
            c.blockers.append(f"{flagged} confirmed test sentence(s) that follow the rule fire")

        # 4. The manual's own prose.
        for rel, doc in docs:
            for b in doc.blocks:
                if not b.lintable:
                    continue
                for a, z in m.find(b.text):
                    c.findings += 1
                    ctx = (rel, b.text[max(0, a - 40):z + 30].replace("\n", " "))
                    c.hits.append(ctx)
                    if len(c.samples) < 6:
                        c.samples.append(ctx)
        c.words = words or 0
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
             f"{len(checks) - len(ready)} blocked. Read a rule's full results with "
             f"`python -m derek.detect.proposals card UID`; adopt with "
             f"`python -m derek.detect.proposals adopt UID:FINGERPRINT --by <initials>`.", "",
             "| Rule | Own examples (✓/✗) | Test sentences: wrong caught · right flagged | "
             "On the manual | Status |", "|---|---|---|---|---|"]
    for c in checks:
        status = "**ready**" if c.ready else "blocked"
        vc, vt = c.tally((ex.TEST_SENTENCE,), "violating")
        cf, ct = c.tally((ex.TEST_SENTENCE,), "compliant")
        waiting = sum(1 for s in c.sentences if s["state"] == "awaiting a person")
        tests = (f"{vc}/{vt} · {cf}/{ct}" if vt or ct else "none confirmed") + \
                (f" ({waiting} awaiting)" if waiting else "")
        lines.append(f"| {c.statement[:60]} `{c.uid}` | {c.examples[0]}/{c.examples[1]} "
                     f"| {tests} | {c.findings} ({c.density:.2f}/10k) | {status} |")
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


# ---------------------------------------------------------------------------
# The card: one rule's full results, and the fingerprint adoption asks for
# ---------------------------------------------------------------------------

def _source_label(e: ex.Example) -> str:
    p = e.provenance
    if e.source == ex.HUMAN_SPAN:
        who = ", ".join(p.get("marked_by") or []) or "a reviewer"
        return f"marked by {who} in the annotator ({(p.get('marked_at') or '')[:10]})"
    if e.source == ex.STYLE_MANUAL:
        return "the Style Manual's example block"
    return (f"test sentence confirmed by {p.get('confirmed_by')} "
            f"({(p.get('confirmed_at') or '')[:10]}); written by {p['writer'].get('model')}, "
            f"labelled {p['checker'].get('verdict')} by {p['checker'].get('model')}")


def _result(polarity: str, fired: bool) -> str:
    if polarity == "violating":
        return "✓ flagged" if fired else "✗ missed"
    return "✗ false alarm" if fired else "✓ not flagged"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " / ")


def card_body(c: Check) -> str:
    """Everything a person adopting this matcher should read, as Markdown.

    Deterministic: it carries no clock, so the same evidence always gives the
    same fingerprint.
    """
    rule, p = c.rule, c.proposal
    L = [f"# {c.statement}", ""]
    if rule is not None:
        src = rule.source
        L += [f"`{c.uid}` · `{src.page_path}`" + (f" · [on the Style Manual]({src.url})" if src.url else ""),
              "", f"Review status **{rule.review.status}**"
              + (f", decided by {rule.review.decided_by} on {rule.review.decided_at[:10]}"
                 if rule.review.decided_by else "") + ".", ""]
    L += ["## Verdict", "", "**Ready to adopt.**" if c.ready else "**Blocked.**", ""]
    L += [f"- {b}" for b in c.blockers] + ([""] if c.blockers else [])

    if rule is not None:
        L += ["## The rule", "",
              f"- **The manual says:** {rule.source.statement}",
              f"- **What makes text wrong:** "
              + (rule.violation_condition or "*not written yet (D-2 asks for it before acceptance)*"),
              f"- **Interpretation:** {rule.specification or '*none recorded*'}",
              f"- **Direction / modality / unit / applies to:** {rule.direction} · {rule.modality}"
              f" · {rule.unit} · {', '.join(rule.applies_to)}", ""]

    L += ["## The matcher", "", f"Method `{p['method']}`, proposed by: {p.get('proposed_by', '*not said*')}"
          f" (`{p.get('_source', '')}`).", "",
          f"```json\n{json.dumps(p['matcher'], ensure_ascii=False, indent=1, sort_keys=True)}\n```", ""]
    if p.get("limits"):
        L += [f"**What it deliberately leaves alone.** {p['limits']}", ""]

    L += ["## Tested on the rule's examples", "",
          "Every example that may test this matcher, with where it came from. The rule's own "
          "examples must all agree. A confirmed test sentence that follows the rule must not "
          "be flagged; one that breaks it and is missed is reported here, not blocking.", ""]
    if c.tested:
        L += ["| Should be | Example | Where it came from | Result |", "|---|---|---|---|"]
        for e, fired in c.tested:
            L.append(f"| {'flagged' if e.polarity == 'violating' else 'left alone'} | "
                     f"{_cell(e.text)} | {_source_label(e)} | {_result(e.polarity, fired)} |")
        L.append("")
    else:
        L += ["*No examples at all.*", ""]
    oc, ot = c.tally(CANONICAL, "violating")
    tc, tt = c.tally((ex.TEST_SENTENCE,), "violating")
    fc, ft = c.tally(CANONICAL, "compliant")
    tf, tn = c.tally((ex.TEST_SENTENCE,), "compliant")
    L += ["| | Wrong, flagged | Right, flagged by mistake |", "|---|---|---|",
          f"| The rule's own examples | {oc} of {ot} | {fc} of {ft} |",
          f"| Confirmed test sentences | {tc} of {tt} | {tf} of {tn} |", ""]

    if c.sentences:
        by_state: dict[str, int] = {}
        for s in c.sentences:
            by_state[s["state"]] = by_state.get(s["state"], 0) + 1
        pending = [s for s in c.sentences if s["state"] == "awaiting a person"]
        pv = [s for s in pending if s["polarity"] == "violating"]
        pc = [s for s in pending if s["polarity"] == "compliant"]
        L += ["## Test sentences, all of them", "",
              "Written by a model that never saw this matcher, labelled blind by a second model "
              "family, then put to a person in the triage app's example screen. Only confirmed "
              "ones count above.", "",
              "States: " + ", ".join(f"{n} {k}" for k, n in sorted(by_state.items())) + ".", ""]
        if pending:
            L += [f"*Not yet counted, as a preview:* of the {len(pv)} awaiting a person that break the "
                  f"rule, it flags {sum(s['fires'] for s in pv)}; of the {len(pc)} that follow it, it "
                  f"flags {sum(s['fires'] for s in pc)}.", ""]
        L += ["| Should be | Sentence | Near miss | State | Result |", "|---|---|---|---|---|"]
        for s in sorted(c.sentences, key=lambda s: (s["state"], s["polarity"], s["text"])):
            L.append(f"| {'flagged' if s['polarity'] == 'violating' else 'left alone'} | {_cell(s['text'])} | "
                     f"{'yes' if s.get('near_miss') else ''} | {s['state']} | {_result(s['polarity'], s['fires'])} |")
        L.append("")

    budget = float(p.get("expected_density") or 0.0)
    L += ["## On the Style Manual's own prose", "",
          f"{c.findings} finding(s) in {c.words:,} words: {c.density:.2f} per 10,000, against a "
          f"budget of {budget}." + (f" Budget justification: {p['density_justification']}"
                                     if p.get("density_justification") else ""), ""]
    L += [f"- `{rel}`: …{_cell(ctx)}…" for rel, ctx in c.hits]
    if c.hits:
        L.append("")

    counts: dict[str, int] = {}
    for e, _ in c.tested:
        counts[e.source] = counts.get(e.source, 0) + 1
    records = sorted({e.provenance.get("record", "") for e, _ in c.tested if e.source == ex.TEST_SENTENCE} - {""})
    L += ["## Provenance", "",
          "Examples by source: " + (", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(counts.items()))
                                    or "none") + "."]
    for r in records:
        rec_hash = next(e.provenance.get("record_input_sha256", "") for e, _ in c.tested
                        if e.provenance.get("record") == r)
        L.append(f"Test sentences from `{r}` (input `{rec_hash[:12]}`).")
    L.append("")
    return "\n".join(L)


def fingerprint(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def card(c: Check) -> str:
    body = card_body(c)
    fp = fingerprint(body)[:FINGERPRINT_CHARS]
    tail = (f"Adopt exactly these results with "
            f"`python -m derek.detect.proposals adopt {c.uid}:{fp} --by <initials>`."
            if c.ready else "Blocked, so it cannot be adopted as it stands.")
    return body + f"\n---\n\nCard fingerprint **`{fp}`**. {tail}\n"


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------

def _record(c: Check, by: str, at: str, body: str) -> dict:
    p = c.proposal
    return {
        "uid": c.uid, "statement": c.statement,
        "adopted_by": by, "adopted_at": at,
        "card_sha256": fingerprint(body), "card": body,
        "proposal": {k: v for k, v in sorted(p.items()) if k != "_source"},
        "proposal_source": p.get("_source", ""),
        "examples": [{**e.to_dict(), "fired": fired} for e, fired in c.tested],
        "test_sentences": [{k: s.get(k) for k in ("id", "text", "polarity", "near_miss", "state",
                                                 "checker", "checker_reason", "fires")}
                           | {"verdict": s["verdict"]} for s in c.sentences],
        "manual": {"findings": c.findings, "words": c.words, "per_10k": round(c.density, 4),
                   "budget": float(p.get("expected_density") or 0.0),
                   "hits": [{"page": rel, "context": ctx} for rel, ctx in c.hits]},
    }


def adopt(uids: list[str], by: str, *, ledger: Path = LEDGER, checks: list[Check],
          cards: dict[str, str] | None = None, adoptions: Path = ADOPTIONS) -> int:
    """Adopt each ready proposal whose card fingerprint matches the one given.

    ``cards`` maps a uid to the fingerprint (or any prefix of eight or more
    characters) printed at the foot of its card.
    """
    cards = cards or {}
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
        body = card_body(c)
        given = cards.get(uid, "")
        if len(given) < 8 or not fingerprint(body).startswith(given):
            print(f"  {uid}: not adopted: read its card first "
                  f"(python -m derek.detect.proposals card {uid}) and adopt with the "
                  f"fingerprint at its foot. "
                  + ("None was given." if not given else
                     f"{given!r} is not this card's; the results have changed since it was read."),
                  file=sys.stderr)
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

        adoptions.mkdir(parents=True, exist_ok=True)
        path = adoptions / f"{uid}.json"
        text = json.dumps(_record(c, by, now, body), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8")
        where = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
        # The review status does not change; the record of who adopted what, on
        # what evidence, does.
        rule.review.transition(rule.review.status, by, now,
                               f"adopted Tier 0 matcher from {p.get('_source', 'a proposal')}")
        rule.review.history[-1].update({
            "record": where,
            "record_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "card_sha256": fingerprint(body),
        })
        done += 1
        print(f"  {uid}: adopted ({c.statement[:60]}); evidence in {where}")
    if done:
        write_ledger(ledger, rules.values())
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    k = sub.add_parser("card", help="one rule's full results, ending in its fingerprint")
    k.add_argument("uids", nargs="+")
    a = sub.add_parser("adopt", help="write ready proposals into the ledger")
    a.add_argument("pairs", nargs="+", metavar="UID:FINGERPRINT",
                   help="each rule with the fingerprint at the foot of its card")
    a.add_argument("--by", required=True, help="your initials (D-10: a human adopts)")
    args = ap.parse_args(argv)

    rules = load_ledger(LEDGER)
    checks = check(load_proposals(), rules)
    if args.cmd == "card":
        by_uid = {c.uid: c for c in checks}
        unknown = [u for u in args.uids if u not in by_uid]
        if unknown:
            ap.error(f"no proposal for {', '.join(unknown)}")
        sys.stdout.write("\n\n".join(card(by_uid[u]) for u in args.uids))
        return 0
    if args.cmd == "adopt":
        by = "".join(ch for ch in args.by.upper() if ch.isalnum())[:6]
        if not by:
            ap.error("--by needs your initials")
        cards = dict(pair.split(":", 1) if ":" in pair else (pair, "") for pair in args.pairs)
        n = adopt(list(cards), by, checks=checks, cards=cards)
        print(f"{n} matcher(s) adopted.")
        return 0 if n == len(cards) else 1
    sys.stdout.write(report(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
