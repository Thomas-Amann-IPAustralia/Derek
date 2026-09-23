"""The golden span set as a declared extraction input (ADR-023).

The headline property, and the reason the extractor's 736 candidates are worth
keeping rather than discarding: a span that exactly covers a heading lands on the
*same* uid as the candidate that heading produced, so confirming the extractor's
guess carries every review decision forward for free.

Everything else here is a refusal. A span is a human's judgement written down;
resolving one wrongly moves that judgement onto text they never read, and the
dangerous failure is not a span that fails to resolve but one that resolves to the
wrong sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import NormalisedPage
from derek.extract.blocks import parse_blocks
from derek.extract.candidates import candidate_uid, extract_candidates
from derek.extract.golden import (
    GOLD_COMPLIANT, GOLD_VIOLATING, GoldenError, GoldenSet, Span, golden_candidates,
    load_golden, resolve_span, span_id, write_golden,
)
from derek.ledger.reconcile import reconcile
from derek.ledger.store import load_ledger

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "ledger" / "rules.jsonl"
PAGE = "grammar-punctuation-and-conventions/punctuation/commas.md"


def page_text(rel: str = PAGE) -> str:
    src = REPO / "corpus" / "pages" / rel
    return NormalisedPage(rel, src.read_text(encoding="utf-8")).text


def make_span(block, start=None, end=None, *, kind="rule", of="", page=PAGE,
              tags=None, preconditions=(), disambiguator="", quote=None, seed_uid=""):
    start = 0 if start is None else start
    end = len(block.plain) if end is None else end
    return Span(
        span_id=span_id(page, block.id, start, end, kind),
        kind=kind, page_path=page, page_sha256="",
        block_id=block.id, start=start, end=end,
        quote=block.plain[start:end] if quote is None else quote,
        prefix=block.plain[max(0, start - 32):start],
        suffix=block.plain[end:end + 32],
        of=of, tags=dict(tags or {}), preconditions=tuple(preconditions),
        disambiguator=disambiguator, seed_uid=seed_uid,
        by="TA", at="2026-09-22T00:00:00Z",
    )


@pytest.fixture(scope="module")
def blocks():
    return parse_blocks(PAGE, page_text())


# ---------------------------------------------------------------------------
# UID continuity — the mechanism that makes the first cut reusable
# ---------------------------------------------------------------------------

def test_a_span_covering_a_heading_reuses_that_candidate_uid(blocks):
    text = page_text()
    heading = next(b for b in blocks if b.kind == "heading" and b.level >= 2)
    extracted = {c.uid: c for c in extract_candidates(PAGE, text)}
    expected = next(c for c in extracted.values() if c.statement == heading.plain)

    [got] = golden_candidates(PAGE, text, [make_span(heading)])
    assert got.uid == expected.uid
    assert got.statement == expected.statement
    assert got.heading_path == expected.heading_path
    assert got.origin == "golden"


def test_confirming_a_candidate_keeps_every_review_decision(blocks):
    """Through the real reconciler, against the real ledger.

    If this ever files as `added` instead of `unchanged`, confirming a candidate
    silently discards whatever a reviewer already decided about it.
    """
    text = page_text()
    ledger = load_ledger(LEDGER)
    heading = next(
        b for b in blocks
        if b.kind == "heading" and b.level >= 2
        and any(r.source.statement == b.plain and r.source.page_path == PAGE
                for r in ledger.values())
    )
    gold = golden_candidates(PAGE, text, [make_span(heading)])
    rec = reconcile(gold, {c.uid: ledger[c.uid] for c in gold})
    assert len(rec.unchanged) == 1, rec.summary()
    assert not rec.added and not rec.reworded and not rec.orphaned


def test_adjusting_a_span_links_the_lineage_the_human_stated(blocks):
    """The 18% case: the heading is the right place and the wrong words.

    Moving the span to the sentence below changes the statement, so it changes
    the uid. The span carries `seed_uid` — the candidate it came from — so the
    lineage is a thing the human said rather than a thing the reconciler
    inferred from position, which is strictly better and is what this module's
    own docstring asks for wherever something more exact is available.
    """
    text = page_text()
    heading, prose = next(
        (h, p) for h in blocks if h.kind == "heading" and h.level >= 2
        for p in blocks if p.kind == "para" and p.heading_path == h.heading_path
    )

    original = {c.uid: c for c in extract_candidates(PAGE, text)}
    was = next(c for c in original.values() if c.statement == heading.plain)

    [moved] = golden_candidates(PAGE, text, [make_span(prose, seed_uid=was.uid)])
    assert moved.uid != was.uid
    assert moved.statement == prose.plain
    assert moved.supersedes == was.uid

    rec = reconcile([moved], {was.uid: _as_rule(was)})
    assert len(rec.reworded) == 1, rec.summary()
    old, cand = rec.reworded[0]
    assert old.uid == was.uid and cand.uid == moved.uid


def test_a_prose_span_with_no_stated_lineage_is_simply_new(blocks):
    """It must not be matched against the heading rules around it.

    A body-prose rule never occupied a heading slot, so it cannot have been
    reworded from one. Running the positional branch over it matches it against
    every heading rule under the same parent and reports "LINEAGE UNRESOLVED:
    may supersede <uid>" for a rule that supersedes nothing — which is a
    human decision requested for no reason, on every prose span, forever.
    """
    text = page_text()
    heading, prose = next(
        (h, p) for h in blocks if h.kind == "heading" and h.level >= 2
        for p in blocks if p.kind == "para" and p.heading_path == h.heading_path
    )
    neighbours = {c.uid: _as_rule(c) for c in extract_candidates(PAGE, text)
                  if c.heading_path[:-1] == heading.heading_path[:-1]}
    assert len(neighbours) > 1, "this page needs sibling headings for the test to bite"

    [fresh] = golden_candidates(PAGE, text, [make_span(prose)])
    assert not fresh.positional
    rec = reconcile([fresh], neighbours)
    assert len(rec.added) == 1, rec.summary()
    assert not rec.ambiguous and not rec.reworded


def test_confirming_a_seed_declares_no_supersession(blocks):
    """The span IS that candidate, so there is nothing for it to replace."""
    text = page_text()
    heading = next(b for b in blocks if b.kind == "heading" and b.level >= 2)
    expected = next(c for c in extract_candidates(PAGE, text)
                    if c.statement == heading.plain)
    [got] = golden_candidates(PAGE, text, [make_span(heading, seed_uid=expected.uid)])
    assert got.uid == expected.uid
    assert got.supersedes == ""


def _as_rule(cand):
    from derek.extract.build import candidate_to_rule
    return candidate_to_rule(cand, {}, {}, "2026-09-22T00:00:00+00:00")


def test_a_body_prose_span_gets_a_stable_uid(blocks):
    """The ~60 rules stated as description, which no heading branch reaches."""
    text = page_text()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    span = make_span(prose)
    a = golden_candidates(PAGE, text, [span])[0]
    b = golden_candidates(PAGE, text, [span])[0]
    assert a.uid == b.uid
    assert a.uid == candidate_uid(PAGE, prose.heading_path, prose.plain)
    assert a.statement_form == "descriptive" or a.statement_form


def test_a_partial_span_records_only_the_text_it_covers(blocks):
    text = page_text()
    prose = next(b for b in blocks if b.kind == "para" and len(b.plain) > 60)
    [got] = golden_candidates(PAGE, text, [make_span(prose, 10, 50)])
    assert got.statement == prose.plain[10:50]


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_an_example_overlapping_its_own_rule_is_refused(blocks):
    """D-5 / postmortem F4, and the one way a reviewer could reintroduce it.

    A rule tested against the sentence that states it always passes and proves
    nothing. The schema cannot catch this — both strings are legitimate on their
    own — so only provenance makes it wrong, and provenance is what a span keeps.
    """
    text = page_text()
    prose = next(b for b in blocks if b.kind == "para" and len(b.plain) > 60)
    rule = make_span(prose, 0, 50)
    example = make_span(prose, 30, 60, kind="violating", of=rule.span_id)
    with pytest.raises(GoldenError, match="D-5"):
        golden_candidates(PAGE, text, [rule, example])


def test_an_example_elsewhere_in_the_same_block_is_fine(blocks):
    text = page_text()
    prose = next(b for b in blocks if b.kind == "para" and len(b.plain) > 70)
    rule = make_span(prose, 0, 30)
    example = make_span(prose, 40, 70, kind="compliant", of=rule.span_id)
    [got] = golden_candidates(PAGE, text, [rule, example])
    assert got.examples[GOLD_COMPLIANT] == [prose.plain[40:70]]


def _lead_in_list(blocks):
    """commas.md's "…, for example:" and the single-word items under it."""
    lead = next(b for b in blocks if b.plain.endswith("to distinguish, for example:"))
    i = blocks.index(lead)
    items = []
    for b in blocks[i + 1:]:
        if b.kind != "li":
            break
        items.append(b)
    assert [b.plain for b in items] == ["red", "green", "orange", "brown", "blue", "purple."]
    return lead, items


def test_a_grouped_example_is_one_example_in_document_order(blocks):
    """A list's lead-in and its items are one example, not four.

    The block projection splits a list into one block per item, so before groups
    the reviewer's only option was four "examples", three of them the single
    words 'green', 'orange' and 'red', which illustrate nothing on their own.
    (That is what the first annotation of commas.md recorded.)
    """
    text = page_text()
    lead, items = _lead_in_list(blocks)
    rule_block = next(b for b in blocks if b.plain.startswith("If you’re introducing a bullet list"))
    rule = make_span(rule_block)
    group = span_id(PAGE, lead.id, 0, len(lead.plain), "compliant")
    parts = [make_span(b, kind="compliant", of=rule.span_id) for b in [lead, *items]]
    parts = [Span(**{**p.__dict__, "group": group}) for p in parts]
    # Handed over out of order: document order is golden.py's job, not the export's.
    [got] = golden_candidates(PAGE, text, [rule, *reversed(parts)])
    assert got.examples[GOLD_COMPLIANT] == [
        "Some colours are difficult for people with colour blindness to distinguish, "
        "for example:\nred\ngreen\norange\nbrown\nblue\npurple."]


def test_a_group_cannot_both_comply_and_violate(blocks):
    text = page_text()
    lead, items = _lead_in_list(blocks)
    rule_block = next(b for b in blocks if b.plain.startswith("If you’re introducing a bullet list"))
    rule = make_span(rule_block)
    a = Span(**{**make_span(lead, kind="compliant", of=rule.span_id).__dict__, "group": "g"})
    b = Span(**{**make_span(items[0], kind="violating", of=rule.span_id).__dict__, "group": "g"})
    with pytest.raises(GoldenError, match="comply and violate"):
        golden_candidates(PAGE, text, [rule, a, b])


def test_an_ungrouped_span_writes_no_group_key(blocks):
    """So every span recorded before groups existed is byte-identical on disk."""
    prose = next(b for b in blocks if b.kind == "para")
    plain = make_span(prose, kind="compliant", of="x")
    assert "group" not in plain.to_dict()
    grouped = Span(**{**plain.__dict__, "group": "abc"})
    assert Span.from_dict(grouped.to_dict()).group == "abc"


def test_an_example_pointing_at_nothing_is_refused(blocks):
    text = page_text()
    prose = next(b for b in blocks if b.kind == "para")
    with pytest.raises(GoldenError, match="not a rule span"):
        golden_candidates(PAGE, text, [make_span(prose, kind="compliant", of="nope")])


def test_a_span_on_an_excluded_page_is_refused(tmp_path):
    """D-4 / ADR-005. Eligibility is a property of the page, declared once."""
    rel = "about-style-manual/changelog.md"
    blocks_there = parse_blocks(rel, page_text(rel))
    span = make_span(blocks_there[1], page=rel)
    spans = tmp_path / "spans.jsonl"
    spans.write_text(json.dumps(span.to_dict()) + "\n", encoding="utf-8")
    eligibility = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    with pytest.raises(GoldenError, match="ADR-005"):
        load_golden(spans, tmp_path / "pages.jsonl", eligibility)


def test_a_span_on_the_page_title_is_refused(blocks):
    text = page_text()
    title = next(b for b in blocks if b.kind == "heading" and b.level == 1)
    with pytest.raises(GoldenError, match="page title"):
        golden_candidates(PAGE, text, [make_span(title)])


def test_two_spans_resolving_to_one_rule_are_refused_not_merged(blocks):
    """`build.py` merges candidates by uid and would silently drop one."""
    text = page_text()
    # Two spans over the same extent, differing only in id — which is what a
    # hand-edited or double-applied export looks like.
    target = next(b for b in blocks if b.kind == "li")
    a = make_span(target)
    b = Span(**{**a.__dict__, "span_id": "deadbeefcafe"})
    with pytest.raises(GoldenError, match="same rule id"):
        golden_candidates(PAGE, text, [a, b])


def test_a_disambiguator_separates_two_genuinely_distinct_rules(blocks):
    text = page_text()
    li = next(b for b in blocks if b.kind == "li")
    a = make_span(li)
    b = Span(**{**a.__dict__, "span_id": "deadbeefcafe", "disambiguator": "second"})
    got = golden_candidates(PAGE, text, [a, b])
    assert len({c.uid for c in got}) == 2


def test_an_empty_disambiguator_changes_nothing(blocks):
    """Otherwise every existing uid would move the moment the field was added."""
    text = page_text()
    heading = next(b for b in blocks if b.kind == "heading" and b.level >= 2)
    plain = golden_candidates(PAGE, text, [make_span(heading)])[0]
    with_empty = golden_candidates(
        PAGE, text, [make_span(heading, disambiguator="")])[0]
    assert plain.uid == with_empty.uid


# ---------------------------------------------------------------------------
# Resolution and re-anchoring
# ---------------------------------------------------------------------------

def test_a_span_resolves_by_block_id_while_the_corpus_is_frozen(blocks):
    prose = next(b for b in blocks if b.kind == "para")
    r = resolve_span(make_span(prose, 5, 25), blocks)
    assert r.text == prose.plain[5:25]
    assert not r.rebased


def test_a_span_re_anchors_by_quote_when_its_block_moves(blocks):
    """The unfreeze path (ADR-024): offsets are the fast route, the quote is the
    recovery one."""
    prose = next(b for b in blocks if b.kind == "para" and len(b.plain) > 60)
    span = make_span(prose, 10, 40)
    from dataclasses import replace
    stale = replace(span, block_id="0000deadbeef", start=999, end=1099)
    r = resolve_span(stale, blocks)
    assert r.rebased
    assert r.text == prose.plain[10:40]
    assert r.span.block_id == prose.id and r.span.start == 10


def test_a_span_that_cannot_be_placed_fails_loudly(blocks):
    prose = next(b for b in blocks if b.kind == "para")
    from dataclasses import replace
    lost = replace(make_span(prose), block_id="0000deadbeef", start=0, end=5,
                   quote="this sentence is not anywhere in the Style Manual",
                   prefix="", suffix="")
    with pytest.raises(GoldenError, match="cannot be placed"):
        resolve_span(lost, blocks)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

def test_the_golden_file_is_canonical_and_idempotent(tmp_path, blocks):
    gs = GoldenSet()
    prose = [b for b in blocks if b.kind == "para"][:3]
    gs.spans[PAGE] = [make_span(b) for b in reversed(prose)]
    gs.swept[PAGE] = {"page_path": PAGE, "status": "complete", "by": "TA"}

    spans, pages = tmp_path / "spans.jsonl", tmp_path / "pages.jsonl"
    write_golden(gs, spans, pages)
    first = spans.read_bytes()

    write_golden(load_golden(spans, pages), spans, pages)
    assert spans.read_bytes() == first, "a round trip through disk changed the file"


def test_the_committed_golden_set_resolves_against_the_corpus():
    """Every span on disk still points at the text it was drawn on."""
    eligibility = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    gs = load_golden(eligibility=eligibility)
    for page, spans in sorted(gs.spans.items()):
        blocks_here = parse_blocks(page, page_text(page))
        for span in spans:
            r = resolve_span(span, blocks_here)
            assert r.text == span.quote, f"{page}: {span.span_id}"
            assert not r.rebased, (
                f"{page}: {span.span_id} had to be re-anchored — the corpus moved "
                f"under a recorded span, which corpus/freeze.yaml exists to prevent")


# ---------------------------------------------------------------------------
# Measurement (derek/eval/span_recall.py)
# ---------------------------------------------------------------------------

def _sweep(tmp_path, blocks, marked, page=PAGE):
    """A throwaway golden set: these spans, on a page declared swept."""
    spans = tmp_path / "spans.jsonl"
    pages = tmp_path / "pages.jsonl"
    spans.write_text(
        "\n".join(json.dumps(make_span(b, page=page).to_dict()) for b in marked) + "\n",
        encoding="utf-8")
    pages.write_text(
        json.dumps({"page_path": page, "status": "complete", "by": "TA"}) + "\n",
        encoding="utf-8")
    return spans, pages


def test_nothing_is_measured_until_a_page_is_swept(tmp_path, blocks):
    """Precision over an unswept page would be fiction.

    A heading with no span on it might be a rule nobody has reached yet. Only the
    sweep marker turns that absence into a labelled negative, and without
    negatives you can fit a heuristic but you cannot measure one.
    """
    from derek.eval import span_recall

    spans = tmp_path / "spans.jsonl"
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    spans.write_text(json.dumps(make_span(prose).to_dict()) + "\n", encoding="utf-8")
    (tmp_path / "pages.jsonl").write_text("", encoding="utf-8")

    assert span_recall.measure(spans, tmp_path / "pages.jsonl") == []


def test_the_report_separates_a_missed_heading_from_an_unreachable_rule(tmp_path, blocks):
    """The distinction the whole exercise turns on.

    A rule the branches missed on a heading is a heuristic that can be improved.
    A rule that is not on a heading at all is one no heading heuristic reaches at
    any threshold — the class docs/07 estimated at ~60 corpus-wide by hand, and
    the number that says whether a prose pass is needed (docs/05 Q6).
    """
    from derek.eval import span_recall

    text = page_text()
    proposed = {c.statement for c in extract_candidates(PAGE, text)}
    hit = next(b for b in blocks
               if b.kind == "heading" and b.plain in proposed)
    missed = next(b for b in blocks
                  if b.kind == "heading" and b.level >= 2 and b.plain not in proposed)
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)

    spans, pages = _sweep(tmp_path, blocks, [hit, missed, prose])
    [result] = span_recall.measure(spans, pages)

    assert result.hits == [hit.plain]
    assert result.missed_heading == [missed.plain]
    assert result.missed_prose == [prose.plain]
    assert result.golden == 3
    assert result.reachable == 2, "a prose rule is not reachable by a heading heuristic"
    assert hit.plain not in result.spurious
    assert result.spurious, "headings the human did not mark are the precision cost"


def test_the_totals_are_arithmetic_not_assertion(tmp_path, blocks):
    from derek.eval import span_recall

    text = page_text()
    proposed = {c.statement for c in extract_candidates(PAGE, text)}
    hits = [b for b in blocks if b.kind == "heading" and b.plain in proposed][:3]
    spans, pages = _sweep(tmp_path, blocks, hits)
    results = span_recall.measure(spans, pages)
    totals = span_recall._totals(results)

    assert totals["hits"] == len(hits)
    assert totals["golden_rules"] == sum(r.golden for r in results)
    assert totals["precision"] == totals["hits"] / (totals["hits"] + totals["spurious"])
    assert totals["recall_reachable"] >= totals["recall_overall"]
    span_recall.report(results)        # must not raise on real numbers
