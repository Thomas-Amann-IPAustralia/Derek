#!/usr/bin/env python3
"""Two drafters, one adjudicator: model consensus as golden spans (ADR-027).

    python tools/draft/consensus.py queue --all          # what the two drafts disagree on
    python tools/draft/consensus.py status --all         # how much is decided
    python tools/draft/consensus.py export --all         # golden/inbox/consensus-*.jsonl
    python tools/draft/consensus.py sample --n 50        # the human verification sample
    python tools/draft/consensus.py score --blind        # against the human-marked pages

Each page is drafted by two models from different families (``providers.PAIR``),
with the same pinned prompt and the same pointer check (ADR-025). This module
lines the two drafts up and sorts every difference into one of two piles:

* **Agreed.** Both models pointed at the same rule, the same example with the
  same polarity, the same tag. Taken as is.
* **Disputed.** One model only, or two different answers. Each becomes an
  *item* in ``golden/consensus/queue.jsonl`` with a stable id, and nothing is
  exported from a page until every item on it has a decision in
  ``golden/consensus/adjudications.jsonl``. The decisions are written by a
  third model family (Claude, in a working session) and carry a reason.

``export`` writes the result in the annotator's own op format, so it goes into
the golden set and the ledger through ``tools/annotate/apply_spans.py`` and
``server._apply``, with every refusal those already make. Nothing here writes to
``golden/spans.jsonl`` or the ledger directly.

What stays true from ADR-025: every rule statement and every example is a
pointer into the manual, so no text a model wrote becomes a rule or a test of
one (D-1, D-5, postmortem F4). What changes (ADR-027): a model, checked by a
second model and an adjudicator, now decides that a rule exists, and a human
gates the batch through ``sample`` rather than each rule.

Deterministic: the same drafts and the same adjudications give the same queue
and the same export, apart from the export's timestamp. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from drafting import (  # noqa: E402
    PROMPT_VERSION, REPO, eligible_pages, load_blind, load_drafts, load_page,
)
from providers import PAIR  # noqa: E402

from derek.eval.draft_score import pair_score  # noqa: E402
from derek.extract.blocks import RENDER_VERSION  # noqa: E402

CONSENSUS = REPO / "golden" / "consensus"
QUEUE = CONSENSUS / "queue.jsonl"
ADJUDICATIONS = CONSENSUS / "adjudications.jsonl"
INBOX = REPO / "golden" / "inbox"
LEDGER = REPO / "ledger" / "rules.jsonl"

# Whose free text (violation condition, specification, conditions) an agreed
# rule takes when the adjudicator has not picked. Chosen on the sample pages
# (ADR-027); the other model's text stays in the item for the adjudicator.
PRIMARY = PAIR[0]

# Reviewer initials as server.clean_initials keeps them (six characters).
BY_CONSENSUS = "MODELS"
BY_ADJUDICATOR = "CLAUDE"

TAGS = ("direction", "modality", "unit", "detection_hint", "clarity", "applies_to")

_COMPLIANT_LABELS = {"write this", "correct", "example", "examples"}
_VIOLATING_LABELS = {"not this", "incorrect"}


# ---------------------------------------------------------------------------
# Lining two drafts up
# ---------------------------------------------------------------------------

def _key(anchor: dict) -> tuple[str, int, int]:
    return anchor["block_id"], anchor["start"], anchor["end"]


def _overlap(a: tuple[str, int, int], b: tuple[str, int, int]) -> int:
    if a[0] != b[0]:
        return 0
    return max(0, min(a[2], b[2]) - max(a[1], b[1]))


def _example_keys(rule: dict) -> set[tuple[str, int, int]]:
    return {_key(p) for ex in rule.get("examples", []) for p in ex["parts"]}


def match_rules(page, a_rules: list[dict], b_rules: list[dict]) -> list[tuple[int, int]]:
    """One-to-one pairs (i, j) of rules both drafts found.

    ``derek.eval.draft_score.pair_score`` decides what counts as the same rule,
    the same test that matches a draft against a human. Best pairs first, so a
    weak match never takes a rule a strong one needed.
    """
    by_id = {b.id: b for b in page.blocks}

    def side(r: dict) -> tuple:
        return _key(r["anchor"]), r["anchor"]["quote"], _example_keys(r)

    scored = []
    for i, ra in enumerate(a_rules):
        for j, rb in enumerate(b_rules):
            sc = pair_score(by_id, side(ra), side(rb))
            if sc:
                scored.append((sc, i, j))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_a, used_b, pairs = set(), set(), []
    for _, i, j in scored:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j))
    return sorted(pairs)


def _tags(rule: dict) -> dict:
    t = dict(rule.get("tags") or {})
    t["clarity"] = rule.get("clarity_suggestion", "")
    t["applies_to"] = sorted(t.get("applies_to") or ["any"])
    return {k: t.get(k, "") for k in TAGS} | {
        "violation_condition": t.get("violation_condition", ""),
        "specification": t.get("specification", ""),
    }


_HARD = re.compile(r"\b(must|never|always|required|requires|illegal|mandatory)\b", re.I)
_STRENGTH = {"SHOULD": "MUST", "SHOULD_NOT": "MUST_NOT"}


def settle_modality(statement: str, a: str, b: str) -> str:
    """One model said SHOULD, the other MUST (or the _NOT pair): settle it by rule.

    ADR-016, and the drafting prompt's own instruction: a bare instruction is
    SHOULD unless the text makes it a hard requirement. On the sample pages
    this was the commonest disagreement by far, and it is a reading of the
    statement's words rather than a judgement, so it is decided here the same
    way every time instead of by hand. Any other pair is left to the
    adjudicator.
    """
    pair = {a, b}
    for soft, hard in _STRENGTH.items():
        if pair == {soft, hard}:
            return hard if _HARD.search(statement) else soft
    return ""


# Smallest to largest: the piece of writing a checker must read (ADR-007).
_UNITS = ["character", "token", "phrase", "sentence", "paragraph", "block", "section",
          "document"]
# Least to most cautious about whether a checker can be built as written (ADR-017).
_CLARITY = ["unambiguous", "ambiguous_resolvable", "ambiguous_deferred", "not_automatable"]


def settle_unit(_statement: str, a: str, b: str) -> str:
    """The larger unit. A checker given more text than it needs can still
    decide; one given less cannot."""
    if a in _UNITS and b in _UNITS:
        return _UNITS[max(_UNITS.index(a), _UNITS.index(b))]
    return ""


def settle_clarity(_statement: str, a: str, b: str) -> str:
    """The more cautious reading. Two careful readers disagreeing about whether
    a rule is operational as written is itself evidence that it is not clearly
    so, and a rule marked less automatable than it is costs a missed finding,
    where the reverse costs false ones (postmortem: 1,438 per 1,000 words)."""
    if a in _CLARITY and b in _CLARITY:
        return _CLARITY[max(_CLARITY.index(a), _CLARITY.index(b))]
    return ""


def settle_hint(_statement: str, a: str, b: str) -> str:
    """A routing guess, refined when a matcher is written (ADR-010, ADR-026):
    a definite answer beats `unsure`, and otherwise the primary drafter's."""
    if "unsure" in (a, b):
        return b if a == "unsure" else a
    return a if PRIMARY == PAIR[0] else b


SETTLE = {"modality": lambda s, a, b: settle_modality(s, a, b),
          "unit": settle_unit, "clarity": settle_clarity, "detection_hint": settle_hint}


def _label_polarity(page, block_id: str) -> str:
    """What the manual's own label says an example is, if it says anything."""
    block = next((b for b in page.blocks if b.id == block_id), None)
    if block is None or not block.heading_path:
        return ""
    label = block.heading_path[-1].strip().lower()
    if label in _VIOLATING_LABELS:
        return "violating"
    if label in _COMPLIANT_LABELS:
        return "compliant"
    return ""


def item_id(page_path: str, kind: str, *parts) -> str:
    h = hashlib.sha256("\x00".join([page_path, kind, *map(str, parts)]).encode("utf-8"))
    return h.hexdigest()[:12]


def _rule_view(rule: dict) -> dict:
    """What the adjudicator needs to see of one model's rule."""
    return {
        "anchor": rule["anchor"],
        "tags": _tags(rule),
        "when": rule.get("when", []),
        "examples": [{"kind": e["kind"], "quotes": [p["quote"] for p in e["parts"]]}
                     for e in rule.get("examples", [])],
        "why": rule.get("why", ""),
    }


def page_plan(rel: str, drafts: dict[str, dict]) -> dict:
    """The agreed rules and the disputed items for one page."""
    page = load_page(rel)
    a_name, b_name = PAIR
    a, b = drafts[a_name], drafts[b_name]
    a_rules, b_rules = a.get("rules", []), b.get("rules", [])
    pairs = match_rules(page, a_rules, b_rules)
    paired_a = {i for i, _ in pairs}
    paired_b = {j for _, j in pairs}

    rules, items = [], []

    for i, j in pairs:
        ra, rb = a_rules[i], b_rules[j]
        anchor, chosen_from = _choose_anchor(page, ra, rb)
        rid = item_id(rel, "rule", *_key(anchor))
        ta, tb = _tags(ra), _tags(rb)
        conflicts = {k: {a_name: ta[k], b_name: tb[k]} for k in TAGS if ta[k] != tb[k]}
        tags = {k: ta[k] for k in TAGS if k not in conflicts}
        for field in list(conflicts):
            settled = SETTLE.get(field, lambda *_: "")(anchor["quote"], ta[field], tb[field])
            if settled:
                tags[field] = settled
                del conflicts[field]
        primary, other = (ra, rb) if PRIMARY == a_name else (rb, ra)
        examples, ex_items = _merge_examples(page, rel, rid, ra, rb)
        rules.append({
            "rid": rid, "anchor": anchor, "found_by": [a_name, b_name],
            "anchor_from": chosen_from,
            "seed_uid": ra.get("seed_uid") or rb.get("seed_uid") or "",
            "tags": tags,
            "violation_condition": _tags(primary)["violation_condition"],
            "specification": (_tags(primary)["specification"]
                              or _tags(other)["specification"]),
            "when": primary.get("when", []),
            "examples": examples,
        })
        if conflicts:
            items.append({
                "item_id": item_id(rel, "tags", rid), "page_path": rel, "kind": "tags",
                "rid": rid, "statement": anchor["quote"], "conflicts": conflicts,
                "views": {a_name: _rule_view(ra), b_name: _rule_view(rb)},
                "ask": "Pick a value for each conflicting tag. Optionally replace "
                       "violation_condition or specification.",
            })
        items.extend(ex_items)

    for name, rs, paired in ((a_name, a_rules, paired_a), (b_name, b_rules, paired_b)):
        for n, r in enumerate(rs):
            if n in paired:
                continue
            rid = item_id(rel, "rule", *_key(r["anchor"]))
            other = b_name if name == a_name else a_name
            verdict = _not_rule_verdict(drafts[other], r["anchor"])
            items.append({
                "item_id": item_id(rel, "single", rid), "page_path": rel, "kind": "single",
                "rid": rid, "statement": r["anchor"]["quote"],
                "heading_path": list(_heading_path(page, r["anchor"]["block_id"])),
                "found_by": name, "other_said": verdict,
                "view": _rule_view(r),
                "ask": f"Only {name} returned this as a rule. Keep it (as drafted, "
                       f"or with tag changes) or drop it.",
            })
            rules.append({
                "rid": rid, "anchor": r["anchor"], "found_by": [name], "anchor_from": name,
                "seed_uid": r.get("seed_uid", ""), "tags": _tags(r) | {},
                "violation_condition": _tags(r)["violation_condition"],
                "specification": _tags(r)["specification"],
                "when": r.get("when", []),
                "examples": [_example_out(e, name) for e in r.get("examples", [])],
                "single": True,
            })

    dropped_items, restated = _dropped_candidates(page, rel, rules, drafts)
    items.extend(dropped_items)
    return {"page_path": rel, "page_sha256": page.sha256, "rules": rules, "items": items,
            "restated": restated}


def _heading_path(page, block_id: str) -> tuple[str, ...]:
    block = next((b for b in page.blocks if b.id == block_id), None)
    return block.heading_path if block else ()


def _choose_anchor(page, ra: dict, rb: dict) -> tuple[dict, str]:
    """Which of two agreeing anchors the rule takes.

    The same extent, trivially. Otherwise the one that is a whole candidate
    heading, because that keeps the heading candidate's uid and any review it
    already carries (ADR-023's UID continuity). Otherwise the shorter, because
    the prompt asked for the shortest span that states the rule and the longer
    one is the likelier to have taken in a second sentence.
    """
    a_name, b_name = PAIR
    if _key(ra["anchor"]) == _key(rb["anchor"]):
        return ra["anchor"], "both"
    if ra.get("seed_uid") and not rb.get("seed_uid"):
        return ra["anchor"], a_name
    if rb.get("seed_uid") and not ra.get("seed_uid"):
        return rb["anchor"], b_name
    la = ra["anchor"]["end"] - ra["anchor"]["start"]
    lb = rb["anchor"]["end"] - rb["anchor"]["start"]
    return (ra["anchor"], a_name) if la <= lb else (rb["anchor"], b_name)


def _example_out(ex: dict, source: str) -> dict:
    return {"kind": ex["kind"], "parts": ex["parts"], "source": source}


def _merge_examples(page, rel: str, rid: str, ra: dict, rb: dict):
    """Examples both models attached with one polarity are taken; the rest are
    taken when the manual's own label agrees, and otherwise disputed."""
    a_name, b_name = PAIR
    pol: dict[tuple, dict[str, str]] = {}
    for name, r in ((a_name, ra), (b_name, rb)):
        for ex in r.get("examples", []):
            for p in ex["parts"]:
                pol.setdefault(_key(p), {})[name] = ex["kind"]

    out, items, emitted = [], [], set()
    order = (ra, a_name), (rb, b_name)
    if PRIMARY == b_name:
        order = order[::-1]
    for r, name in order:
        for ex in r.get("examples", []):
            keys = [_key(p) for p in ex["parts"]]
            if any(k in emitted for k in keys):
                continue
            votes = [pol[k] for k in keys]
            agreed = all(len(v) == 2 and len(set(v.values())) == 1 and
                         next(iter(v.values())) == ex["kind"] for v in votes)
            label = {_label_polarity(page, k[0]) for k in keys} - {""}
            if agreed:
                out.append(_example_out(ex, "both"))
            elif len(label) == 1 and label == {ex["kind"]} and \
                    all(len(set(v.values())) == 1 for v in votes):
                # One model only, but the manual labels it so, and the other
                # model did not call it the opposite.
                out.append(_example_out(ex, f"{name}+label"))
            else:
                iid = item_id(rel, "example", rid, *keys)
                items.append({
                    "item_id": iid, "page_path": rel, "kind": "example", "rid": rid,
                    "statement": ra["anchor"]["quote"],
                    "example": [p["quote"] for p in ex["parts"]],
                    "proposed": ex["kind"], "proposed_by": name,
                    "votes": [v for v in votes], "label": sorted(label),
                    "ask": "Is this an example of the rule, and which way: "
                           "compliant, violating, or drop?",
                })
                out.append(_example_out(ex, name) | {"item_id": iid})
            emitted.update(keys)
    return out, items


def _not_rule_verdict(draft: dict, anchor: dict) -> str:
    """What the other model said about this text, if it said anything."""
    k = _key(anchor)
    for x in draft.get("not_rules", []):
        if _overlap(k, _key(x["anchor"])):
            return f"not a rule: {x.get('reason', '')} {x.get('note', '')}".strip()
    return "nothing"


def _dropped_candidates(page, rel: str, rules: list[dict],
                        drafts) -> tuple[list[dict], list[dict]]:
    """Heading candidates the sweep would refuse to drop silently.

    ``apply_spans._check_sweeps`` holds back a candidate already accepted or
    amended, or carrying the manual's paired examples, unless the sweep lists it
    in ``dropped`` with a reason.

    Returns ``(items, restated)``. A candidate whose heading is restated by a
    rule both models agreed on, usually the sentence directly under it, is not
    a decision: the rule was kept, on the sentence the manual states it with
    (G-4). Those go straight into ``dropped`` with that reason. On the sample's
    commas page they were 16 of the 17 items this used to raise. Only a
    candidate nothing agreed covers is put to the adjudicator. A single-model
    rule does not count as cover, because the adjudicator may yet drop it.
    """
    if not LEDGER.exists():
        return [], []
    from derek.ledger.store import load_ledger

    covered = {r["anchor"]["block_id"] for r in rules
               if r["anchor"]["start"] == 0 and r.get("seed_uid")}
    seeds_by_uid = {uid: bid for bid, uid in page.seeds.items()}
    by_id = {b.id: b for b in page.blocks}
    agreed = [r for r in rules if not r.get("single")]
    items, restated = [], []
    for rule in sorted(load_ledger(LEDGER).values(), key=lambda r: r.uid):
        if rule.source.page_path != rel or rule.review.status in ("rejected", "deferred"):
            continue
        accepted = rule.review.status in ("accepted", "amended")
        paired = bool(rule.compliant_examples and rule.violating_examples)
        if not (accepted or paired):
            continue
        bid = seeds_by_uid.get(rule.uid)
        if bid in covered:
            continue
        if any(r.get("seed_uid") == rule.uid for r in rules):
            continue
        cover = _covering_rule(by_id, _candidate_side(page, bid, rule.source.statement), agreed)
        if cover is not None:
            restated.append({
                "uid": rule.uid,
                "reason": f"G-4: restated by the kept rule «{cover['anchor']['quote'][:120]}», "
                          f"which both models marked instead of this heading",
            })
            continue
        said = {name: _not_rule_verdict(drafts[name], {"block_id": bid or "", "start": 0,
                                                        "end": 10 ** 6})
                for name in PAIR}
        items.append({
            "item_id": item_id(rel, "dropped", rule.uid), "page_path": rel,
            "kind": "dropped", "uid": rule.uid, "block_id": bid or "",
            "statement": rule.source.statement, "status": rule.review.status,
            "compliant": rule.compliant_examples, "violating": rule.violating_examples,
            "models_said": said,
            "ask": "Neither model kept this candidate, but it is "
                   + ("already accepted" if accepted else "carrying the manual's paired "
                      "examples") + ". Keep it as a rule, or let it go with a reason.",
        })
    return items, restated


def _candidate_side(page, heading_id: str | None, statement: str) -> tuple | None:
    """Where a ledger candidate sits on the page, as ``pair_score`` takes it.

    A heading candidate is its heading block. A rule marked on a body sentence
    has no heading block, so its statement is found in the page's text instead.
    """
    by_id = {b.id: b for b in page.blocks}
    if heading_id in by_id:
        b = by_id[heading_id]
        return (b.id, 0, len(b.plain)), b.plain, set()
    from drafting import _FOLD   # the same typographic folding the pointer check uses

    want = statement.translate(_FOLD)
    for b in page.blocks:
        at = b.plain.translate(_FOLD).find(want)
        if want and at != -1:
            return (b.id, at, at + len(want)), statement, set()
    return None


def _covering_rule(by_id: dict, side: tuple | None, rules: list[dict]) -> dict | None:
    """The kept rule that states this candidate's rule, in its words or others."""
    if side is None:
        return None
    best, best_score = None, 0.0
    for r in rules:
        sc = pair_score(by_id, side, (_key(r["anchor"]), r["anchor"]["quote"], _example_keys(r)))
        if sc > best_score:
            best, best_score = r, sc
    return best


# ---------------------------------------------------------------------------
# Adjudications
# ---------------------------------------------------------------------------

def load_adjudications(path: Path = ADJUDICATIONS) -> dict[str, dict]:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["item_id"]] = row          # the last decision on an item wins
    return out


def _pages(args) -> list[str]:
    if args.pages:
        return args.pages
    if args.blind:
        return sorted(load_blind())
    pages = eligible_pages()
    if args.all:
        return pages
    raise SystemExit("name pages, or use --blind or --all")


def _drafted(pages: list[str]) -> tuple[dict[str, dict[str, dict]], list[str]]:
    by_model = {m: load_drafts(prompt_version=PROMPT_VERSION, model=m) for m in PAIR}
    ready, missing = {}, []
    for rel in pages:
        if all(rel in by_model[m] for m in PAIR):
            ready[rel] = {m: by_model[m][rel] for m in PAIR}
        else:
            missing.append(rel)
    return ready, missing


def human_pages() -> set[str]:
    """Pages a human marked. They are the measurement, so consensus never writes
    to them (ADR-027): a model's rules there would be scored against themselves."""
    from derek.extract.golden import load_golden

    return {p for p, spans in load_golden().spans.items()
            if any(s.by not in (BY_CONSENSUS, BY_ADJUDICATOR) for s in spans)}


def build_queue(pages: list[str]) -> tuple[list[dict], list[str]]:
    ready, missing = _drafted(pages)
    skip = human_pages()
    items = []
    for rel in sorted(ready):
        if rel in skip:
            continue
        items.extend(page_plan(rel, ready[rel])["items"])
    return items, missing


# ---------------------------------------------------------------------------
# Export: the annotator's op format
# ---------------------------------------------------------------------------

def _anchor_key(anchor: dict, kind: str) -> str:
    return f"{anchor['block_id']}|{anchor['start']}|{anchor['end']}|{kind}"


def export_page(plan: dict, adj: dict[str, dict], at: str) -> tuple[list[dict], list[str]]:
    """Ops for one page, or a list of what is still undecided."""
    rel = plan["page_path"]
    undecided = [it["item_id"] for it in plan["items"] if it["item_id"] not in adj]
    if undecided:
        return [], undecided

    decided = {it["item_id"]: (it, adj[it["item_id"]]) for it in plan["items"]}
    tag_dec = {it["rid"]: d for it, d in decided.values() if it["kind"] == "tags"}
    single_dec = {it["rid"]: d for it, d in decided.values() if it["kind"] == "single"}

    ops, used_parts, seen_anchor, refused = [], set(), set(), []
    page = load_page(rel)
    by_id = {b.id: b for b in page.blocks}

    def op(span: dict, by: str) -> dict:
        body = json.dumps(span, sort_keys=True)
        return {"op": "span", "op_id": "consensus-" + hashlib.sha256(
                    body.encode("utf-8")).hexdigest()[:24],
                "by": by, "at": at, "span": span}

    for rule in plan["rules"]:
        by = BY_CONSENSUS
        tags = dict(rule["tags"])
        vc, spec, when = rule["violation_condition"], rule["specification"], rule["when"]
        note = "two-model consensus: " + " + ".join(PAIR)
        if rule.get("single"):
            d = single_dec.get(rule["rid"], {}).get("decision", {})
            if not d.get("keep"):
                continue
            by, note = BY_ADJUDICATOR, f"found by {rule['found_by'][0]} only; kept by " \
                                       f"the adjudicator: {single_dec[rule['rid']].get('reason', '')}"
        if rule["rid"] in tag_dec:
            d = tag_dec[rule["rid"]].get("decision", {})
            by = BY_ADJUDICATOR
            note += f"; tags adjudicated: {tag_dec[rule['rid']].get('reason', '')}"
        else:
            d = single_dec.get(rule["rid"], {}).get("decision", {}) if rule.get("single") else {}
        tags.update(d.get("tags", {}))
        vc = d.get("violation_condition", vc)
        spec = d.get("specification", spec)
        when = d.get("when", when)

        anchor = rule["anchor"]
        block = by_id.get(anchor["block_id"])
        if block is None or len(block.heading_path) < 2:
            # The page title, or the page's introduction above its first
            # section: golden.py would give the rule level 1, which no candidate
            # may have (ADR-002). Said aloud rather than dropped silently.
            refused.append(f"{rel}: «{anchor['quote'][:70]}» sits in the page "
                           f"introduction; mark the section that states it instead")
            continue
        akey = _anchor_key(anchor, "rule")
        if akey in seen_anchor:
            continue
        seen_anchor.add(akey)

        clarity = tags.get("clarity", "")
        if clarity == "ambiguous_resolvable" and not spec.strip():
            clarity = "ambiguous_deferred"   # server._apply refuses the first without one
        span_tags = {
            "unit": tags.get("unit", ""), "clarity": clarity,
            "direction": tags.get("direction", ""), "modality": tags.get("modality", ""),
            "applies_to": list(tags.get("applies_to") or ["any"]),
            "detection_hint": tags.get("detection_hint", ""),
            "violation_condition": vc, "specification": spec,
            "review_status": "accepted", "note": note[:500],
        }
        full_heading = block.kind == "heading" and anchor["start"] == 0 and \
            anchor["end"] == len(block.plain)
        ops.append(op({
            "page_path": rel, "page_sha256": plan["page_sha256"], "kind": "rule",
            "anchor": anchor, "of": "",
            "seed_uid": page.seeds.get(block.id, "") if full_heading else "",
            "seed_draft": f"{PROMPT_VERSION}/{'+'.join(rule['found_by'])}",
            "tags": span_tags, "preconditions": list(when),
        }, by))

        for ex in rule["examples"]:
            kind = ex["kind"]
            if "item_id" in ex:
                d = adj[ex["item_id"]].get("decision", {})
                kind = d.get("kind", kind)
                if kind == "drop":
                    continue
            keys = [_key(p) for p in ex["parts"]]
            if any((k, kind) in used_parts for k in keys):
                continue                 # one example span, one rule (span ids are per extent)
            if any(k[0] == anchor["block_id"] and k[1] < anchor["end"] and anchor["start"] < k[2]
                   for k in keys):
                continue                 # D-5: never the sentence that states the rule
            group = _anchor_key(ex["parts"][0], kind) if len(ex["parts"]) > 1 else ""
            for p in ex["parts"]:
                used_parts.add((_key(p), kind))
                span = {"page_path": rel, "page_sha256": plan["page_sha256"], "kind": kind,
                        "anchor": p, "of": akey}
                if group:
                    span["group"] = group
                ops.append(op(span, by))

    dropped = list(plan.get("restated", []))
    for it, d in decided.values():
        if it["kind"] != "dropped":
            continue
        dec = d.get("decision", {})
        if dec.get("keep") and it["block_id"]:
            block = by_id[it["block_id"]]
            akey = _anchor_key({"block_id": block.id, "start": 0, "end": len(block.plain)}, "rule")
            if akey in seen_anchor:
                continue
            seen_anchor.add(akey)
            ops.append(op({
                "page_path": rel, "page_sha256": plan["page_sha256"], "kind": "rule",
                "anchor": {"block_id": block.id, "start": 0, "end": len(block.plain),
                           "quote": block.plain, "prefix": "", "suffix": ""},
                "of": "", "seed_uid": it["uid"], "tags": {}, "preconditions": [],
            }, BY_ADJUDICATOR))
        else:
            dropped.append({"uid": it["uid"], "reason": d.get("reason", "")})

    ops.append({"op": "page", "op_id": f"consensus-page-{item_id(rel, 'page', plan['page_sha256'])}",
                "by": BY_CONSENSUS, "at": at, "page_path": rel,
                "page_sha256": plan["page_sha256"], "status": "complete",
                "note": "swept by two-model consensus with adjudication (ADR-027)",
                "dropped": dropped})
    for why in refused:
        print(f"  refused: {why}", file=sys.stderr)
    return ops, []


# ---------------------------------------------------------------------------
# The verification sample
# ---------------------------------------------------------------------------

def sample(n: int, seed: str, out: Path) -> int:
    """A uniform random sample of consensus rules, for a human to check (ADR-027).

    Drawn from the ledger, not the export, so it samples what actually landed:
    every live rule whose review was written by the consensus or the
    adjudicator. The seed is recorded, so the draw can be reproduced.
    """
    from derek.ledger.store import load_ledger

    rules = [r for r in load_ledger(LEDGER).values()
             if r.review.status in ("accepted", "amended")
             and r.review.decided_by in (BY_CONSENSUS, BY_ADJUDICATOR)]
    rules.sort(key=lambda r: r.uid)
    rng = random.Random(seed)
    picked = rng.sample(rules, min(n, len(rules)))
    rows = [{
        "uid": r.uid, "page_path": r.source.page_path, "statement": r.source.statement,
        "heading_path": list(r.source.heading_path),
        "violation_condition": r.violation_condition,
        "compliant_examples": r.compliant_examples,
        "violating_examples": r.violating_examples,
        "decided_by": r.review.decided_by, "url": r.source.url,
    } for r in picked]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": seed, "population": len(rules), "rules": rows},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"sampled {len(rows)} of {len(rules)} consensus rules (seed {seed!r}) -> {out}")
    return 0


# ---------------------------------------------------------------------------
# Measurement on the human pages
# ---------------------------------------------------------------------------

def score(pages: list[str]) -> int:
    """The consensus against what a human marked, on the pages a human marked.

    Reported two ways, as bounds, because consensus never adjudicates a human
    page (that would be grading the adjudicator against an answer it had seen):
    *agreed* counts only the rules both models found, *either* counts every rule
    either model found. The adjudicated result lies between them.
    """
    from derek.eval.draft_score import score_page
    from derek.extract.golden import load_golden

    golden = load_golden()
    ready, _ = _drafted(pages)
    marked = sorted(p for p in human_pages() if p in ready)
    if not marked:
        print("no human-marked page has drafts from both models")
        return 1
    rows = {"agreed": [], "either": []}
    for rel in marked:
        plan = page_plan(rel, ready[rel])
        for name, keep in (("agreed", lambda r: not r.get("single")), ("either", lambda r: True)):
            draft = {"rules": [{"anchor": r["anchor"], "tags": r["tags"],
                                "examples": r["examples"]} for r in plan["rules"] if keep(r)]}
            rows[name].append(score_page(rel, draft, golden, blind=True))
    print(f"Consensus against the human's marks on {len(marked)} page(s): "
          + ", ".join(marked) + "\n")
    print("| | agreed by both | found by either |\n|---|---|---|")

    def tot(name, f):
        return sum(f(r) for r in rows[name])

    for label, f in (("Rules the human marked", lambda r: r.golden),
                     ("Rules proposed", lambda r: r.drafted),
                     ("Human rules found", lambda r: r.matched),
                     ("Human examples also attached", lambda r: r.examples_found),
                     ("Examples with opposite polarity", lambda r: len(r.polarity_conflicts))):
        print(f"| {label} | {tot('agreed', f)} | {tot('either', f)} |")
    g = tot("agreed", lambda r: r.golden)
    for name in rows:
        m = tot(name, lambda r: r.matched)
        print(f"\nrecall ({name}): {m}/{g} = {m / g:.0%}" if g else "")
    for r in rows["either"]:
        for c in r.polarity_conflicts:
            print(f"  polarity: {r.page_path}: {c}")
    return 0


def compare(pages: list[str]) -> int:
    """Every cached (model, effort) on human-marked pages: quality beside cost.

    For choosing drafters (ADR-027). Free to re-run: it reads the cache.
    """
    from derek.eval.draft_score import score_page
    from derek.extract.golden import load_golden
    from providers import cost

    golden = load_golden()
    marked = sorted(p for p in pages if p in human_pages())
    base = REPO / "golden" / "drafts" / PROMPT_VERSION
    drafters = sorted(d.name for d in base.iterdir() if d.is_dir()) if base.exists() else []
    print("| drafter | page | recall | examples | inverted | proposed | refused | out tokens | cost |")
    print("|---|---|---|---|---|---|---|---|---|")
    for drafter in drafters:
        drafts = load_drafts(prompt_version=PROMPT_VERSION, model=drafter)
        for rel in marked:
            if rel not in drafts:
                continue
            d = drafts[rel]
            sc = score_page(rel, d, golden, blind=True)
            u = d.get("usage", {})
            out = u.get("output_tokens", 0) + (u.get("reasoning_tokens", 0)
                                               if drafter.startswith("gemini") else 0)
            print(f"| {drafter} | {rel.rsplit('/', 1)[-1]} | {sc.matched}/{sc.golden} "
                  f"| {sc.examples_found}/{sc.examples_golden} | {len(sc.polarity_conflicts)} "
                  f"| {sc.drafted} | {sc.refused} | {out:,} | ${cost(drafter, u):.2f} |")

    # Pairs from different families: what consensus would make of them, and how
    # much it would leave for the adjudicator.
    global PAIR, PRIMARY
    saved = PAIR, PRIMARY
    family = lambda d: "openai" if d.startswith("gpt") else d.split("-")[0]
    print("\n| pair | agreed recall | either recall | inverted | single-model | tag items | cost |")
    print("|---|---|---|---|---|---|---|")
    try:
        for a in drafters:
            for b in drafters:
                if family(a) != "openai" or family(b) == "openai":
                    continue
                PAIR, PRIMARY = (a, b), a
                for rel in marked:
                    da = load_drafts(prompt_version=PROMPT_VERSION, model=a).get(rel)
                    db = load_drafts(prompt_version=PROMPT_VERSION, model=b).get(rel)
                    if not (da and db):
                        continue
                    plan = page_plan(rel, {a: da, b: db})
                    got = {}
                    for name, keep in (("agreed", lambda r: not r.get("single")),
                                       ("either", lambda r: True)):
                        draft = {"rules": [{"anchor": r["anchor"], "tags": r["tags"],
                                            "examples": r["examples"]}
                                           for r in plan["rules"] if keep(r)]}
                        got[name] = score_page(rel, draft, golden, blind=True)
                    singles = sum(1 for it in plan["items"] if it["kind"] == "single")
                    tagged = sum(1 for it in plan["items"] if it["kind"] == "tags")
                    c = cost(a, da.get("usage", {})) + cost(b, db.get("usage", {}))
                    print(f"| {a} + {b} | {got['agreed'].matched}/{got['agreed'].golden} "
                          f"| {got['either'].matched}/{got['either'].golden} "
                          f"| {len(got['either'].polarity_conflicts)} | {singles} | {tagged} "
                          f"| ${c:.2f} |")
    finally:
        PAIR, PRIMARY = saved
    return 0


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["queue", "status", "export", "sample", "score",
                                            "compare"])
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", default="adr-027")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    if args.command == "sample":
        return sample(args.n, args.seed, args.out or CONSENSUS / "sample.json")

    pages = _pages(args)
    if args.command == "score":
        return score(pages)
    if args.command == "compare":
        return compare(pages)
    items, missing = build_queue(pages)
    if missing:
        print(f"{len(missing)} page(s) lack a draft from both of {', '.join(PAIR)}:",
              file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)

    if args.command == "queue":
        CONSENSUS.mkdir(parents=True, exist_ok=True)
        with QUEUE.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
        kinds: dict[str, int] = {}
        for it in items:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        print(f"{len(items)} item(s) to adjudicate -> {QUEUE.relative_to(REPO)}: "
              + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
        return 0

    adj = load_adjudications()
    ready, _ = _drafted(pages)
    skip = human_pages()
    if args.command == "status":
        agreed = single = 0
        for rel in sorted(ready):
            if rel in skip:
                print(f"  {rel}: human-annotated, left alone")
                continue
            plan = page_plan(rel, ready[rel])
            open_ = sum(1 for it in plan["items"] if it["item_id"] not in adj)
            a = sum(1 for r in plan["rules"] if not r.get("single"))
            s = sum(1 for r in plan["rules"] if r.get("single"))
            agreed, single = agreed + a, single + s
            print(f"  {rel}: {a} agreed, {s} single-model, "
                  f"{len(plan['items'])} item(s), {open_} undecided")
        print(f"{agreed} agreed rule(s), {single} single-model; "
              f"{sum(1 for it in items if it['item_id'] not in adj)} item(s) undecided")
        return 0

    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ops = [{"op": "meta", "op_id": f"consensus-meta-{at}", "by": BY_CONSENSUS, "at": at,
            "app": "consensus", "render_version": RENDER_VERSION,
            "models": list(PAIR), "prompt_version": PROMPT_VERSION}]
    blocked = {}
    for rel in sorted(ready):
        if rel in skip:
            continue
        page_ops, undecided = export_page(page_plan(rel, ready[rel]), adj, at)
        if undecided:
            blocked[rel] = undecided
            continue
        ops.extend(page_ops)
    if blocked:
        print(f"{len(blocked)} page(s) held back with undecided items:", file=sys.stderr)
        for rel, ids in blocked.items():
            print(f"  {rel}: {len(ids)}", file=sys.stderr)
    out = args.out or INBOX / f"consensus-{at[:19].replace(':', '').replace('-', '')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for o in ops:
            fh.write(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"{len(ops) - 1} op(s) -> {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    print(f"Apply with: python tools/annotate/apply_spans.py {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
