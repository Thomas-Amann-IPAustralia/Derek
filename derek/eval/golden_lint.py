"""Check the golden set against the invariants and the grain policy.

    python -m derek.eval.golden_lint                  # the worklist, as Markdown
    python -m derek.eval.golden_lint --page commas    # one page (substring match)
    python -m derek.eval.golden_lint --json           # what the annotator ships

The golden set is the yardstick everything else is measured against: the heading
heuristic (``span_recall``), a model's drafts (``draft_score``), and eventually
every detector's examples. So its mistakes are the expensive kind, because they
make whatever is measured against it look right when it is wrong. The first three
annotated pages had one example with inverted polarity, two rules with inverted
direction, 44 accepted rules with no violation condition, and parent and child
rules both kept. None of those was carelessness. They are what a 3-hour session
with no checklist produces, and this is the checklist.

Three levels, because they cost different amounts to ignore:

``fix``    breaks an invariant or loses information. The page is not done.
``check``  the policy (docs/08-rule-grain.md) says this is probably wrong. It may
           be right, but it should be a decision.
``look``   something on the page that no span accounts for. Often nothing.

It reads and prints. It never writes the golden set or the ledger, because every
finding is a human's call. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import NormalisedPage
from derek.eval.directives import classify, directive_sentences, sentences
from derek.extract.blocks import Block, parse_blocks
from derek.extract.candidates import normalise_statement
from derek.extract.golden import (
    EXAMPLE_KINDS, RULE, GoldenError, load_golden, golden_rules, resolve_span,
)
from derek.ledger.model import ReviewStatus
from derek.ledger.store import load_ledger

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
LEDGER = REPO / "ledger" / "rules.jsonl"

LEVELS = ("fix", "check", "look")

# How the manual labels its example blocks. `Example` is neutral: it shows usage,
# and a sentence under it is not a mistake unless the text says so (E-1).
POSITIVE_LABELS = frozenset({"correct", "write this"})
NEGATIVE_LABELS = frozenset({"incorrect", "not this"})
NEUTRAL_LABELS = frozenset({"example", "examples"})
LABELS = POSITIVE_LABELS | NEGATIVE_LABELS | NEUTRAL_LABELS

_PROHIBITION = re.compile(r"^(don[’']t|do not|never|avoid)\b", re.I)
_NUMBER = re.compile(r"\b\d+\b")
_STOP = frozenset("""
a an and are as at be been but by can for from has have if in into is it its of on
or so such than that the their them then there these they this to use using was
when where which while with you your not no do don t s
""".split())


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    ref: str
    page_path: str
    message: str
    statement: str = ""
    rule_uid: str = ""
    span_key: str = ""      # the annotator's key for the span, so it can select it
    quote: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key(block_id: str, start: int, end: int, kind: str) -> str:
    return f"{block_id}|{start}|{end}|{kind}"


def _label(block: Block) -> str:
    return (block.heading_path[-1] if block.heading_path else "").strip().lower()


def _example_blocks(blocks: list[Block]) -> set[str]:
    """Blocks the manual presents as examples, not as prose.

    A label heading (Example, Correct, Not this, …) cannot be closed in Markdown,
    so the prose that follows it sits under it too. Its examples are the list
    items directly beneath it, or failing those its first paragraph, and nothing
    after the first paragraph that follows either.
    """
    out: set[str] = set()
    current: tuple[str, ...] | None = None
    seen_li = seen_para = False
    for b in blocks:
        if b.kind == "heading":
            current = b.heading_path if _label(b) in LABELS else None
            seen_li = seen_para = False
            continue
        if current is None or b.heading_path != current:
            continue
        if b.kind == "li" and not seen_para:
            out.add(b.id)
            seen_li = True
        elif b.kind in ("para", "quote") and not seen_li and not seen_para:
            out.add(b.id)
            seen_para = True
        else:
            current = None
    return out


def _words(text: str) -> frozenset[str]:
    out = set()
    for w in re.findall(r"[a-z]+", text.lower().replace("’", "'")):
        if w in _STOP or len(w) < 3:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return frozenset(out)


def _is_heading_rule(rule) -> bool:
    hp = rule.source.heading_path
    return bool(hp) and normalise_statement(hp[-1]) == normalise_statement(rule.source.statement)


def _page_text(rel: str) -> str | None:
    src = PAGES / rel
    if not src.exists():
        return None
    return NormalisedPage(rel, src.read_text(encoding="utf-8")).text


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def lint(ledger_path: Path = LEDGER, spans_path: Path | None = None,
         pages_path: Path | None = None, *, cross_page: bool = True) -> list[Finding]:
    eligibility = load_eligibility(ELIGIBILITY)
    kwargs = {}
    if spans_path is not None:
        kwargs["spans_path"] = spans_path
    if pages_path is not None:
        kwargs["pages_path"] = pages_path
    golden = load_golden(eligibility=eligibility, **kwargs)
    rules = load_ledger(ledger_path) if ledger_path.exists() else {}

    out: list[Finding] = []
    marked: list[tuple[str, object]] = []      # (page, rule) for the cross-page pass

    for page in sorted(golden.spans):
        text = _page_text(page)
        if text is None:
            out.append(Finding("fix", "page-missing", "ADR-024", page,
                               "this page is no longer in the corpus"))
            continue
        blocks = parse_blocks(page, text)
        spans = golden.spans[page]
        try:
            paired = golden_rules(page, text, spans)
        except GoldenError as exc:
            out.append(Finding("fix", "golden-refused", "ADR-023", page, str(exc)))
            continue
        page_rules = []
        for span, cand in paired:
            rule = rules.get(cand.uid)
            if rule is not None:
                page_rules.append((span, rule))
                if rule.review.status in ReviewStatus.LOADABLE:
                    marked.append((page, rule))

        out.extend(_check_sweep(page, golden, page_rules))
        for span, rule in page_rules:
            out.extend(_check_rule(page, span, rule))
        out.extend(_check_nesting(page, page_rules))
        out.extend(_check_shared_examples(page, page_rules))
        out.extend(_check_example_polarity(page, spans, blocks))
        out.extend(_check_unused_labelled_examples(page, spans, blocks))
        out.extend(_check_unmarked_directives(page, spans, blocks, page_rules))

    if cross_page and marked:
        out.extend(_check_cross_page(marked, eligibility))

    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    out.sort(key=lambda f: (f.page_path, order[f.level], f.code, f.statement, f.quote))
    return out


def _check_sweep(page, golden, page_rules) -> list[Finding]:
    if page in golden.authoritative or not page_rules:
        return []
    return [Finding(
        "fix", "not-swept", "ADR-023", page,
        "Rules are marked here but the page is not marked swept (F). Until it is, a "
        "heading you skipped reads as 'not reached', not 'not a rule', and "
        "span_recall and draft_score cannot measure anything on this page.")]


def _check_rule(page, span, rule) -> list[Finding]:
    if rule.review.status not in ReviewStatus.LOADABLE:
        return []
    out = []
    key = _key(span.block_id, span.start, span.end, RULE)
    st = rule.source.statement
    f = lambda level, code, ref, msg: Finding(level, code, ref, page, msg, st, rule.uid, key)  # noqa: E731

    stated = st + " " + rule.source.body_excerpt
    if rule.clarity == "unambiguous":
        chosen = sorted({n for p in rule.context_preconditions
                         for n in _NUMBER.findall(p) if n not in _NUMBER.findall(stated)})
        if chosen:
            out.append(f("check", "chosen-threshold", "E-4",
                         f"{', '.join(chosen)} appears in the conditions but not in the "
                         f"manual's wording. A number you chose is an interpretation: "
                         f"'ambiguous_resolvable', with the threshold in the "
                         f"interpretation field (ADR-017)."))

    if rule.modality == "MAY":
        out.append(f("check", "permission-as-rule", "G-3",
                     "A permission can never produce a finding: there is nothing to "
                     "violate. Record it under 'When' on the rule it relaxes, or leave "
                     "it unmarked if it relaxes nothing."))
        return out

    if not rule.violation_condition.strip():
        msg = "No violation condition: the rule never says what makes text wrong."
        spec = rule.specification.strip()
        if spec and classify(spec) in ("imperative", "conditional"):
            msg += (f" The interpretation ('{spec[:70]}') says what is right. D-2 "
                    f"needs the opposite, the text a checker should flag.")
        out.append(f("fix", "no-violation-condition", "D-2", msg))

    if not rule.direction:
        out.append(f("fix", "no-direction", "ADR-006", "Direction is not set."))
    else:
        cue = classify(st)
        if rule.direction == "presence" and cue in ("imperative", "conditional") \
                and not _PROHIBITION.match(st):
            out.append(f("check", "direction-looks-inverted", "ADR-006",
                         "Tagged 'something is there that shouldn't be', but the rule "
                         "tells the writer to add something. If the mistake is that it "
                         "is missing, this is 'absence'."))
        elif rule.direction == "absence" and _PROHIBITION.match(st):
            out.append(f("check", "direction-looks-inverted", "ADR-006",
                         "Tagged 'something is missing', but the rule forbids something. "
                         "The mistake is its presence."))

    for p in rule.context_preconditions:
        if normalise_statement(p) == normalise_statement(st):
            out.append(f("check", "precondition-restates-rule", "G-4",
                         "A precondition repeats the rule itself, so it limits nothing."))
            break
    return out


def _check_nesting(page, page_rules) -> list[Finding]:
    """G-1: a heading rule with other rules marked beneath it."""
    live = [(s, r) for s, r in page_rules if r.review.status in ReviewStatus.LOADABLE]
    out = []
    for span, parent in live:
        if not _is_heading_rule(parent):
            continue
        hp = parent.source.heading_path
        kids = [r for _, r in live if r.uid != parent.uid
                and tuple(r.source.heading_path[:len(hp)]) == tuple(hp)]
        if not kids:
            continue
        names = "; ".join(f"'{k.source.statement[:60]}'" for k in kids[:6])
        more = f" and {len(kids) - 6} more" if len(kids) > 6 else ""
        out.append(Finding(
            "check", "parent-and-children", "G-1", page,
            f"{len(kids)} other rule(s) are marked under this heading: {names}{more}. "
            f"If the heading only groups them it is a section, not a rule (G-1); if "
            f"one restates it, keep one wording (G-4); a permission among them is an "
            f"exception (G-3). Where they overlap, the same text is flagged twice, "
            f"citing two rules.",
            parent.source.statement, parent.uid,
            _key(span.block_id, span.start, span.end, RULE)))
    return out


def _check_shared_examples(page, page_rules) -> list[Finding]:
    live = [r for _, r in page_rules if r.review.status in ReviewStatus.LOADABLE]
    owners: dict[str, list] = {}
    for r in live:
        for ex in {*r.compliant_examples, *r.violating_examples}:
            owners.setdefault(ex, []).append(r)
    out = []
    for ex, rs in sorted(owners.items()):
        if len(rs) < 2:
            continue
        names = "; ".join(f"'{r.source.statement[:50]}'" for r in rs)
        out.append(Finding(
            "check", "example-on-two-rules", "G-1", page,
            f"The same example is attached to {len(rs)} rules ({names}). If both would "
            f"judge it, they overlap and one is probably a section or a restatement.",
            quote=ex[:120]))
    return out


def _check_example_polarity(page, spans, blocks) -> list[Finding]:
    """E-1: a label the manual gave the text, contradicted by the label a human gave it."""
    by_id = {b.id: b for b in blocks}
    rule_keys = {s.span_id: _key(s.block_id, s.start, s.end, RULE)
                 for s in spans if s.kind == RULE}
    rule_quotes = {s.span_id: s.quote for s in spans if s.kind == RULE}
    out = []
    for s in spans:
        if s.kind not in EXAMPLE_KINDS:
            continue
        try:
            block = resolve_span(s, blocks).block
        except GoldenError:
            continue
        label = _label(by_id.get(block.id, block))
        msg = None
        level = "check"
        if s.kind == "violating" and label in POSITIVE_LABELS:
            msg, level = f"Marked 'Not this', but the manual labels it '{label}'.", "fix"
        elif s.kind == "compliant" and label in NEGATIVE_LABELS:
            msg, level = f"Marked 'Write this', but the manual labels it '{label}'.", "fix"
        elif s.kind == "violating" and label in NEUTRAL_LABELS:
            msg = ("Marked 'Not this', but the manual shows it under a neutral "
                   "'Example', not as a mistake. If it is a correct sentence with a "
                   "different meaning, it is not a violation, and training on it "
                   "teaches a checker to flag correct text (E-1).")
        if msg:
            out.append(Finding(level, "example-polarity", "E-1", page, msg,
                               rule_quotes.get(s.of, ""), "", rule_keys.get(s.of, ""),
                               s.quote[:120]))
    return out


def _check_unused_labelled_examples(page, spans, blocks) -> list[Finding]:
    """E-2: the manual's own Correct / Incorrect text, attached to no rule."""
    covered = {s.block_id for s in spans}
    examples = _example_blocks(blocks)
    groups: dict[tuple, list[Block]] = {}
    for b in blocks:
        if b.id in examples and b.id not in covered \
                and _label(b) in POSITIVE_LABELS | NEGATIVE_LABELS:
            groups.setdefault(b.heading_path, []).append(b)
    out = []
    for hp, bs in groups.items():
        label = hp[-1]
        under = hp[-2] if len(hp) > 1 else ""
        text = " / ".join(b.plain[:70] for b in bs[:3])
        out.append(Finding(
            "look", "labelled-example-unused", "E-2", page,
            f"The manual labels {len(bs)} block(s) '{label}' under '{under}', and no "
            f"rule uses them. They are the most reliable examples on the page: the "
            f"editors' own judgement of right and wrong.", quote=text))
    return out


def _check_unmarked_directives(page, spans, blocks, page_rules) -> list[Finding]:
    """Sentences that read as instructions that nothing on the page accounts for.

    Grouped under the marked heading rule they sit beneath, because most of them
    are that rule's own body: its restatement (G-4), the condition that triggers
    it, its exception (G-3), or the very sentence its violation condition should
    be written from. One finding per rule reads as "finish this rule". Thirty
    loose sentences read as noise. A sentence under no marked rule stands alone,
    and those are the likeliest missed rules.
    """
    by_id = {b.id: b for b in blocks}
    examples = _example_blocks(blocks)
    taken = [(s.block_id, s.start, s.end) for s in spans]
    restated = " ".join(
        normalise_statement(t) for _, r in page_rules
        for t in (r.specification, *r.context_preconditions, r.source.statement))
    heads = sorted(
        ((tuple(r.source.heading_path), s, r) for s, r in page_rules
         if r.review.status in ReviewStatus.LOADABLE and _is_heading_rule(r)),
        key=lambda t: -len(t[0]))

    under: dict[str, list] = {}
    loose = []
    for d in directive_sentences(blocks):
        if d.block_id in examples:
            continue
        if any(b == d.block_id and s < d.end and d.start < e for b, s, e in taken):
            continue
        if normalise_statement(d.text).rstrip(".") in restated:
            continue
        hp = by_id[d.block_id].heading_path
        owner = next((h for h in heads if tuple(hp[:len(h[0])]) == h[0]), None)
        if owner:
            under.setdefault(owner[2].uid, [owner, []])[1].append(d)
        else:
            loose.append(d)

    out = []
    for (hp, span, rule), ds in under.values():
        out.append(Finding(
            "look", "rule-body-unaccounted", "G-2/G-4", page,
            f"{len(ds)} sentence(s) under this rule read as instructions and are not in "
            f"its wording, interpretation or conditions. Each is probably one of: its "
            f"restatement (G-4), what triggers it or an exception (When, G-2/G-3), the "
            f"basis of its violation condition, or a separate rule.",
            rule.source.statement, rule.uid,
            _key(span.block_id, span.start, span.end, RULE),
            " | ".join(d.text[:110] for d in ds)))
    for d in loose:
        out.append(Finding(
            "look", "unmarked-directive", "recall", page,
            f"Reads like an instruction ({d.cue}), sits under no marked rule, and no "
            f"span accounts for it. The likeliest kind of missed rule.",
            quote=d.text[:160], span_key=_key(d.block_id, d.start, d.end, "sentence")))
    return out


# Set against the first three pages: 0.65 kept all three real duplicates
# (adjectives.md, and two on choosing-numerals-or-words.md) and dropped "commas
# with Latin shortened forms" ~ "italics for Latin shortened forms" at 0.60. It
# still pairs treaty titles with bill titles, whose rules share every word but
# the one that matters. A word-overlap measure cannot see which word matters,
# which is why this is a `check` and the message says "if".
CROSS_PAGE_OVERLAP = 0.65


def _check_cross_page(marked, eligibility) -> list[Finding]:
    """G-6: a marked rule whose wording closely matches a sentence on another page."""
    index: list[tuple[str, str, frozenset[str]]] = []
    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        if not eligibility.decide(rel)[0]:
            continue
        text = NormalisedPage(rel, md.read_text(encoding="utf-8")).text
        for b in parse_blocks(rel, text):
            if b.kind == "cell":
                continue
            pieces = [b.plain] if b.kind == "heading" else [t for _, _, t in sentences(b.plain)]
            for t in pieces:
                w = _words(t)
                if len(w) >= 4:
                    index.append((rel, t, w))
    out = []
    for page, rule in marked:
        mine = _words(rule.source.statement)
        if len(mine) < 4:
            continue
        best = None
        for rel, t, w in index:
            if rel == page:
                continue
            score = len(mine & w) / len(mine | w)
            if score >= CROSS_PAGE_OVERLAP and (best is None or score > best[0]):
                best = (score, rel, t)
        if best:
            out.append(Finding(
                "check", "stated-on-another-page", "G-6", page,
                f"Very close to a sentence on {best[1]} ({best[0]:.0%} word overlap). "
                f"If it is the same rule, mark it once, on the page whose subject it is.",
                rule.source.statement, rule.uid, quote=best[2][:160]))
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def by_page(findings: list[Finding]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in findings:
        out.setdefault(f.page_path, []).append(asdict(f))
    return out


def report(findings: list[Finding]) -> str:
    if not findings:
        return "No findings. Every annotated page passes.\n"
    lines = ["# Golden-set worklist", "",
             "Generated by `python -m derek.eval.golden_lint`. Nothing here is "
             "applied automatically: every item is a reviewer's call, made in the "
             "annotator. Policy references are to "
             "[docs/08-rule-grain.md](../docs/08-rule-grain.md).", ""]
    counts = {lvl: sum(1 for f in findings if f.level == lvl) for lvl in LEVELS}
    lines.append("| Level | Meaning | Count |\n|---|---|---|")
    meaning = {"fix": "breaks an invariant or loses information",
               "check": "the policy says probably wrong; make it a decision",
               "look": "on the page, accounted for by nothing"}
    for lvl in LEVELS:
        lines.append(f"| `{lvl}` | {meaning[lvl]} | {counts[lvl]} |")
    lines.append("")
    for page, items in by_page(findings).items():
        lines += [f"## `{page}`", ""]
        for lvl in LEVELS:
            these = [f for f in items if f["level"] == lvl]
            if not these:
                continue
            lines.append(f"### {lvl} ({len(these)})\n")
            for f in these:
                head = f"**{f['ref']}**"
                if f["statement"]:
                    head += f" · *{f['statement'][:90]}*"
                lines.append(f"- {head}  ")
                lines.append(f"  {f['message']}")
                if f["quote"]:
                    lines.append(f"  > {f['quote']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--page", help="only pages whose path contains this")
    ap.add_argument("--json", action="store_true", help="findings by page, as JSON")
    ap.add_argument("--level", choices=LEVELS, help="only this level and above")
    ap.add_argument("--no-cross-page", action="store_true",
                    help="skip the corpus-wide duplicate search (the slow part)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any 'fix' finding remains")
    args = ap.parse_args(argv)

    findings = lint(cross_page=not args.no_cross_page)
    if args.page:
        findings = [f for f in findings if args.page in f.page_path]
    if args.level:
        keep = LEVELS[:LEVELS.index(args.level) + 1]
        findings = [f for f in findings if f.level in keep]

    if args.json:
        json.dump(by_page(findings), sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
        print()
    else:
        sys.stdout.write(report(findings))
    if args.strict and any(f.level == "fix" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
