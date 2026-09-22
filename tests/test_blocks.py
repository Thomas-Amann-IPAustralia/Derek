"""Tests for the block projection that golden-set spans are anchored to.

A span in ``golden/spans.jsonl`` is ``(block_id, start, end)``. If this module's
output moves, every recorded span silently points somewhere else — and the
dangerous case is not a span that fails to resolve, it is one that resolves to
the *wrong* text. So the guarantees are asserted rather than assumed, and
``derek/extract/data/blocks.lock.json`` turns any change into a CI failure
rather than a quiet re-anchoring (ADR-023).
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import NormalisedPage
from derek.extract.blocks import (
    BLOCK_KINDS, MARK_KINDS, RENDER_VERSION, block_id, build_lock, load_lock,
    page_digest, parse_blocks,
)
from derek.extract.segment import iter_nodes, parse_page

REPO = Path(__file__).resolve().parents[1]
PAGES = REPO / "corpus" / "pages"


def _eligible() -> dict[str, str]:
    eligibility = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    out = {}
    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        if eligibility.decide(rel)[0]:
            out[rel] = NormalisedPage(rel, md.read_text(encoding="utf-8")).text
    return out


CORPUS = _eligible()


def blocks_of(md: str) -> list:
    return parse_blocks("t.md", NormalisedPage("t.md", md).text)


# ---------------------------------------------------------------------------
# The contract the annotator relies on
# ---------------------------------------------------------------------------

def test_every_mark_resolves_to_a_substring_of_its_own_block():
    """The property that makes a browser selection mappable back to Python.

    The annotator rebuilds formatting by slicing ``plain`` at mark boundaries,
    so a mark that runs past the end of ``plain`` — or into a neighbouring
    block — would put the reviewer's selection at the wrong offset.
    """
    for rel, text in CORPUS.items():
        for b in parse_blocks(rel, text):
            assert b.kind in BLOCK_KINDS, (rel, b.kind)
            for m in b.marks:
                assert m.kind in MARK_KINDS, (rel, m.kind)
                assert 0 <= m.start <= m.end <= len(b.plain), (rel, b.id, m)


def test_a_block_is_one_run_of_text():
    """No newlines in ``plain``.

    A block is the unit a span lives inside, and the annotator renders each as
    one element. A newline would mean the DOM contains text the offsets cannot
    address consistently across browsers.
    """
    for rel, text in CORPUS.items():
        for b in parse_blocks(rel, text):
            assert "\n" not in b.plain, (rel, b.id)
            assert b.plain.strip(), (rel, b.id)


def test_block_ids_are_unique_within_a_page():
    for rel, text in CORPUS.items():
        ids = [b.id for b in parse_blocks(rel, text)]
        dupes = [i for i, n in collections.Counter(ids).items() if n > 1]
        assert not dupes, (rel, dupes)


def test_the_occurrence_suffix_separates_identical_text():
    """Repeated text under one heading must still get distinct addresses."""
    md = "# P\n\n## S\n\nSame sentence.\n\nOther.\n\nSame sentence.\n"
    ids = [b.id for b in blocks_of(md)]
    assert len(set(ids)) == len(ids)
    assert block_id("t.md", ("P", "S"), "Same sentence.", 0) != \
           block_id("t.md", ("P", "S"), "Same sentence.", 1)


def test_parsing_is_deterministic():
    for rel, text in list(CORPUS.items())[:20]:
        first, second = parse_blocks(rel, text), parse_blocks(rel, text)
        assert [b.to_dict() for b in first] == [b.to_dict() for b in second]


# ---------------------------------------------------------------------------
# One parser for heading structure, not two
# ---------------------------------------------------------------------------

def test_headings_agree_with_segment_over_the_whole_corpus():
    """``parse_blocks`` walks ``segment.parse_page``; it must not diverge.

    Re-scanning for headings here would duplicate the ATX regex and the fence
    handling, and two parsers for one question is how they come to disagree —
    which for a rule inventory read off heading structure (ADR-002) would mean
    the annotator showing a different document from the one the extractor reads.
    """
    for rel, text in CORPUS.items():
        from_blocks = [
            (b.level, b.plain, b.line)
            for b in parse_blocks(rel, text) if b.kind == "heading"
        ]
        from_segment = [
            (n.level, n.title, n.line_start)
            for n in sorted(iter_nodes(parse_page(text)), key=lambda n: n.line_start)
        ]
        # Titles carrying inline markup differ by design: `plain` strips it.
        assert [(lv, ln) for lv, _, ln in from_blocks] == \
               [(lv, ln) for lv, _, ln in from_segment], rel


def test_a_heading_block_carries_its_own_title_in_its_heading_path():
    b = [x for x in blocks_of("# P\n\n## Use a comma\n\nBody.\n") if x.kind == "heading"]
    assert b[1].heading_path == ("P", "Use a comma")
    body = [x for x in blocks_of("# P\n\n## Use a comma\n\nBody.\n") if x.kind == "para"]
    assert body[0].heading_path == ("P", "Use a comma"), \
        "body blocks share their heading's path, which is what gives a prose span its address"


# ---------------------------------------------------------------------------
# Every construct the corpus actually contains
# ---------------------------------------------------------------------------

def test_a_link_renders_as_its_label_and_keeps_its_href():
    b = blocks_of("# P\n\n## S\n\nSee the [style manual](https://example.gov.au/x) today.\n")
    para = [x for x in b if x.kind == "para"][0]
    assert para.plain == "See the style manual today."
    link = [m for m in para.marks if m.kind == "link"][0]
    assert para.plain[link.start:link.end] == "style manual"
    assert link.href == "https://example.gov.au/x"


@pytest.mark.parametrize("md,plain,kind,marked", [
    ("Use *en dashes* here.", "Use en dashes here.", "em", "en dashes"),
    ("Use **en dashes** here.", "Use en dashes here.", "strong", "en dashes"),
    ("Use `--` here.", "Use -- here.", "code", "--"),
])
def test_inline_emphasis_is_a_mark_not_characters(md, plain, kind, marked):
    para = [x for x in blocks_of(f"# P\n\n## S\n\n{md}\n") if x.kind == "para"][0]
    assert para.plain == plain
    m = [x for x in para.marks if x.kind == kind][0]
    assert para.plain[m.start:m.end] == marked


def test_markup_with_no_closing_delimiter_is_literal():
    para = [x for x in blocks_of("# P\n\n## S\n\nA 3 * 4 grid and a [half link.\n")
            if x.kind == "para"][0]
    assert para.plain == "A 3 * 4 grid and a [half link."
    assert not para.marks


def test_quoted_html_and_entities_stay_literal():
    """The manual writes about HTML, so its tags are content, not markup.

    28 raw tags and 59 entities appear in the corpus, all inside accessibility
    guidance describing what to put in a document. Escaping them at render time
    is the browser's job; mangling them here would change the character count
    and move every offset after them.
    """
    para = [x for x in blocks_of(
        "# P\n\n## S\n\nUse a <figcaption> element, not a &nbsp; run.\n"
    ) if x.kind == "para"][0]
    assert para.plain == "Use a <figcaption> element, not a &nbsp; run."


def test_a_nested_list_item_records_its_depth():
    b = blocks_of("# P\n\n## S\n\n- outer item\n  - inner item\n")
    items = [x for x in b if x.kind == "li"]
    assert [(x.plain, x.list_depth) for x in items] == \
           [("outer item", 0), ("inner item", 1)]


def test_an_ordered_list_drops_its_numbering_but_records_that_it_had_some():
    """`plain` loses the ordinal, so the block has to say it was numbered.

    Otherwise a page about sequencing content renders its steps as bullets.
    """
    items = [x for x in blocks_of("# P\n\n## S\n\n1. first\n2. second\n") if x.kind == "li"]
    assert [(x.plain, x.ordered) for x in items] == [("first", True), ("second", True)]
    bullets = [x for x in blocks_of("# P\n\n## S\n\n- first\n") if x.kind == "li"]
    assert bullets[0].ordered is False


def test_a_table_becomes_one_block_per_cell():
    md = (
        "# P\n\n## S\n\n"
        "| **Capitalisation** | summer *not* Summer |\n"
        "| --- | --- |\n"
        "| Hyphenation | a blow-out |\n"
    )
    cells = [x for x in blocks_of(md) if x.kind == "cell"]
    assert [(x.plain, x.cell) for x in cells] == [
        ("Capitalisation", (0, 0)),
        ("summer not Summer", (0, 1)),
        ("Hyphenation", (1, 0)),
        ("a blow-out", (1, 1)),
    ], "the | --- | alignment row carries no content and is dropped"


def test_a_blockquote_is_its_own_block():
    b = blocks_of("# P\n\n## S\n\n> Quoted guidance.\n> Second line.\n")
    quotes = [x for x in b if x.kind == "quote"]
    assert [x.plain for x in quotes] == ["Quoted guidance. Second line."]


def test_a_fenced_block_does_not_produce_headings():
    """``segment`` suppresses ATX inside fences; this must inherit that."""
    b = blocks_of("# P\n\n## S\n\n```\n# not a heading\n```\n")
    assert [x.plain for x in b if x.kind == "heading"] == ["P", "S"]


# ---------------------------------------------------------------------------
# Nothing is silently dropped
# ---------------------------------------------------------------------------

def test_the_projection_loses_no_prose():
    """Alphanumeric content is preserved, save for list numbering.

    A block splitter that quietly swallows a paragraph would hide a rule from
    the annotator, and an invisible rule is the failure docs/07 measured. The
    only characters the projection is allowed to drop are the ordinals of
    ordered lists, which are structure the browser re-supplies.
    """
    import re
    for rel, text in CORPUS.items():
        ordinals = sum(
            len(m.group(1))
            for line in text.split("\n")
            if (m := re.match(r"^\s*(\d+)[.)]\s", line))
        )
        src = re.sub(r"[^0-9A-Za-z]", "", re.sub(r"\]\([^)]*\)", "]", text))
        got = re.sub(r"[^0-9A-Za-z]", "", "".join(b.plain for b in parse_blocks(rel, text)))
        assert len(src) - len(got) <= ordinals, rel


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------

def test_the_lock_matches_the_corpus():
    """ADR-023, the same discipline ADR-021 applies to the POS tagger.

    Without this, a change to the renderer re-anchors every recorded span with
    no signal. Regenerate deliberately:
    ``python -m derek.extract.blocks --lock``.
    """
    on_disk = load_lock()
    assert on_disk["pages"], "blocks.lock.json has not been generated"
    assert on_disk["_meta"]["render_version"] == RENDER_VERSION, (
        "render_version moved without the lock being regenerated — every span "
        "offset is anchored to the old projection"
    )
    fresh = build_lock(CORPUS)
    stale = sorted(
        rel for rel in set(on_disk["pages"]) | set(fresh["pages"])
        if on_disk["pages"].get(rel) != fresh["pages"].get(rel)
    )
    assert not stale, stale[:10]


def test_the_digest_notices_a_changed_mark():
    """A formatting-only change still moves offsets, so it must not be invisible."""
    a = page_digest(blocks_of("# P\n\n## S\n\nUse *en dashes* here.\n"))
    b = page_digest(blocks_of("# P\n\n## S\n\nUse en dashes here.\n"))
    assert a != b


def test_the_digest_notices_a_change_that_moves_no_offset():
    """The lock covers what the reviewer sees, not only what moves an offset.

    A bullet list becoming a numbered one leaves every `plain` identical, so it
    would slip past a digest over text alone — and a reviewer marking a rule
    about sequence would be reading the wrong document.
    """
    a = page_digest(blocks_of("# P\n\n## S\n\n- first\n- second\n"))
    b = page_digest(blocks_of("# P\n\n## S\n\n1. first\n2. second\n"))
    assert a != b
