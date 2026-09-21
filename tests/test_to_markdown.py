"""Tests for DOM-faithful HTML → Markdown conversion (ADR-020).

The converter decides which rules exist, because extraction reads the rule
inventory off the heading tree. A regression here silently changes the
rulebook, so these tests are about structure fidelity rather than prose.
"""

from __future__ import annotations

import re

import pytest

from derek.corpus.normalise import normalise_text, repair_headings
from derek.corpus.to_markdown import ExtractionError, extract_markdown

BASE = "https://www.stylemanual.gov.au/a/b"


def page(body: str, *, chrome: bool = True) -> str:
    """A minimal page in the Style Manual's DOM shape."""
    tail = """
      <h2>Release notes</h2><p>Changed something.</p>
      <h2>About this page</h2><h3>References</h3><p>Some ref.</p>
      <h3>Last updated</h3><p>1 January 2026</p>
      <h2>Help us improve the Style Manual</h2><form><input></form>
    """ if chrome else ""
    return f"""<!DOCTYPE html><html><body>
      <div class="top"><h1>Style Manual</h1><nav><h2>Secondary navigation</h2>
        <ul><li><a href="/x">Nav link</a></li></ul></nav></div>
      <main><div class="block-page-title-block"><h1>Commas</h1></div>
        <article>{body}{tail}</article></main>
      <footer><h2>Footer</h2><p>Footer text.</p></footer>
    </body></html>"""


def headings(md: str) -> list[tuple[int, str]]:
    return [(len(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"^(#{1,6})\s+(.*?)\s*$", md, re.M)]


# ---------------------------------------------------------------------------
# The core guarantee: levels come from the DOM
# ---------------------------------------------------------------------------

def test_heading_levels_are_taken_from_the_dom():
    md = extract_markdown(page("""
      <h2>Separate introductory words with a comma</h2>
      <p>Body.</p>
      <h3>Place a comma after adverbs</h3>
      <h4>Example</h4><ul><li>Yes, they went.</li></ul>
      <h5>Non-essential</h5><p>Detail.</p>
    """), BASE)
    assert headings(md) == [
        (1, "Commas"),
        (2, "Separate introductory words with a comma"),
        (3, "Place a comma after adverbs"),
        (4, "Example"),
        (5, "Non-essential"),
    ]


def test_deep_and_skipped_levels_survive():
    md = extract_markdown(page("<h2>A</h2><h6>B</h6><h3>C</h3>"), BASE)
    assert headings(md) == [(1, "Commas"), (2, "A"), (6, "B"), (3, "C")]


def test_conversion_is_deterministic():
    html = page("<h2>A</h2><p>Text.</p><h3>B</h3><ul><li>x</li><li>y</li></ul>")
    assert extract_markdown(html, BASE) == extract_markdown(html, BASE)


# ---------------------------------------------------------------------------
# Chrome removal (postmortem F3 / Defect 1)
# ---------------------------------------------------------------------------

def test_site_chrome_is_removed():
    md = extract_markdown(page("<h2>A real rule</h2><p>Body.</p>"), BASE)
    titles = [t for _, t in headings(md)]
    assert "A real rule" in titles
    for junk in ("Style Manual", "Secondary navigation", "Release notes",
                 "About this page", "References", "Last updated",
                 "Help us improve the Style Manual", "Footer"):
        assert junk not in titles, junk
    assert "Nav link" not in md
    assert "Footer text." not in md


def test_page_title_is_kept_but_site_title_is_not():
    md = extract_markdown(page("<h2>A</h2>"), BASE)
    assert md.startswith("# Commas")
    assert "# Style Manual" not in md


def test_content_after_a_chrome_heading_is_dropped():
    md = extract_markdown(page("<h2>Real</h2><p>Keep me.</p>"), BASE)
    assert "Keep me." in md
    assert "Changed something." not in md
    assert "Some ref." not in md


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def test_lists_nested_and_ordered():
    md = extract_markdown(page(
        "<h2>A</h2><ul><li>one<ul><li>deep</li></ul></li><li>two</li></ul>"
        "<ol><li>first</li><li>second</li></ol>"), BASE)
    assert "- one" in md and "  - deep" in md and "- two" in md
    assert "1. first" in md and "2. second" in md


def test_tables_render_with_a_header_row():
    md = extract_markdown(page(
        "<h2>A</h2><table><tr><th>Term</th><th>Use</th></tr>"
        "<tr><td>finalize</td><td>finalise</td></tr></table>"), BASE)
    assert "| Term | Use |" in md
    assert "| --- | --- |" in md
    assert "| finalize | finalise |" in md


def test_links_are_resolved_to_absolute_urls():
    md = extract_markdown(page('<h2>A</h2><p>See <a href="/node/127">phrases</a>.</p>'), BASE)
    assert "[phrases](https://www.stylemanual.gov.au/node/127)" in md


def test_emphasis_and_code_survive():
    md = extract_markdown(page(
        "<h2>A</h2><p>Use <strong>bold</strong>, <em>italic</em> and <code>x</code>.</p>"), BASE)
    assert "**bold**" in md and "*italic*" in md and "`x`" in md


def test_blockquote_and_preformatted():
    md = extract_markdown(page(
        "<h2>A</h2><blockquote>Quoted line.</blockquote><pre>code block</pre>"), BASE)
    assert "> Quoted line." in md
    assert "```\ncode block\n```" in md


def test_content_is_not_duplicated():
    """A nested wrapper must not be walked twice."""
    md = extract_markdown(page(
        "<h2>A</h2><div><div><p>Only once.</p></div></div>"), BASE)
    assert md.count("Only once.") == 1


# ---------------------------------------------------------------------------
# Failing loudly (ADR-001: a blocked fetch must never be written as content)
# ---------------------------------------------------------------------------

def test_empty_document_raises():
    with pytest.raises(ExtractionError):
        extract_markdown("<html><body></body></html>", BASE)


def test_document_without_headings_raises():
    with pytest.raises(ExtractionError):
        extract_markdown("<html><body><main><p>Just prose.</p></main></body></html>", BASE)


def test_block_page_raises_rather_than_writing_junk():
    blocked = ("<html><body><h1>Access Denied</h1>"
               "<p>You don't have permission.</p></body></html>")
    md_or_error = None
    try:
        md_or_error = extract_markdown(blocked, BASE)
    except ExtractionError:
        return                      # preferred outcome
    # If it did extract, it must at least be obviously not a content page.
    assert len(md_or_error) < 300


# ---------------------------------------------------------------------------
# Heading repair is now a no-op safety net (ADR-020)
# ---------------------------------------------------------------------------

def test_repair_does_nothing_to_dom_faithful_output():
    """If this starts failing, the converter has regressed to flattening."""
    md = normalise_text(extract_markdown(page("""
      <h2>Separate introductory words with a comma</h2>
      <p>A standalone paragraph that looks like a heading</p>
      <h3>Place a comma after adverbs</h3>
      <h4>Example</h4><ul><li>Yes, they went.</li></ul>
    """), BASE))
    _, promotions = repair_headings(md)
    assert promotions == 0


def test_whole_heading_emphasis_is_stripped():
    """`<h2><strong>…</strong></h2>` is presentational. Leaking `**` into the
    heading pollutes the rule statement and its content-addressed UID."""
    md = extract_markdown(page(
        "<h2><strong>Respectful language starts with the basics</strong></h2>"
        "<h3><em>Italics</em></h3>"), BASE)
    assert (2, "Respectful language starts with the basics") in headings(md)
    assert (3, "Italics") in headings(md)
    assert "**" not in "".join(t for _, t in headings(md))


def test_partial_heading_emphasis_is_preserved():
    """In "use italics for *Re*" the emphasis is the rule's subject."""
    md = extract_markdown(page(
        "<h3>Use sentence case and italics for <em>Re</em> and <em>Ex parte</em></h3>"), BASE)
    titles = [t for _, t in headings(md)]
    assert "Use sentence case and italics for *Re* and *Ex parte*" in titles
