"""The rule inspector is a published static page, like the other two apps.

What it adds is a claim: *this highlighted text is where this rule came from.*
That claim is only worth anything if it is the same answer the extractor gives,
so these tests check the shipped placement against ``golden_rules`` itself — the
function that mints a span rule's uid — rather than against anything the
inspector computed for its own purposes. A highlight on the wrong sentence
would be worse than none, because it would be believed.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from derek.corpus.normalise import NormalisedPage
from derek.extract.blocks import RENDER_VERSION, parse_blocks
from derek.extract.golden import golden_rules, load_golden
from derek.ledger.model import ReviewStatus
from derek.ledger.store import load_ledger

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "tools" / "inspect" / "index.html"
HTML = PAGE.read_text(encoding="utf-8")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _script_without_comments() -> str:
    body = re.findall(r"<script>(.*?)</script>", HTML, re.S)[-1]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", body)


@pytest.fixture(scope="module")
def module():
    return _load("derek_inspect_build", REPO / "tools" / "inspect" / "build_static.py")


@pytest.fixture(scope="module")
def built(module, tmp_path_factory):
    """Build the inspector once, into a `site/` its siblings already occupy."""
    site = tmp_path_factory.mktemp("site")
    (site / "annotate").mkdir()
    (site / "annotate" / "index.html").write_text("annotator", encoding="utf-8")
    (site / "index.html").write_text("triage", encoding="utf-8")
    out = site / "inspect"
    out.mkdir()
    (out / "stale.json").write_text("{}", encoding="utf-8")
    manifest = module.build(out)
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    pages = {}
    for meta in index["pages"]:
        if meta["slug"]:
            pages[meta["path"]] = json.loads(
                (out / "data" / "pages" / f"{meta['slug']}.json").read_text(encoding="utf-8"))
    return {"site": site, "out": out, "manifest": manifest, "index": index, "pages": pages}


def _entries(built):
    for path, payload in built["pages"].items():
        for entry in payload["rules"]:
            yield path, payload, entry


# ---------------------------------------------------------------------------
# ADR-022: a published page that assumes nothing about where it is served
# ---------------------------------------------------------------------------

def test_the_page_never_calls_an_absolute_path():
    assert 'fetch("/' not in HTML
    assert '"/data/' not in HTML
    assert "'/data/" not in HTML


def test_the_page_loads_no_external_resource():
    tags = re.findall(r"<(script|link|img|iframe|source)\b[^>]*>", HTML, re.I)
    for tag in tags:
        for url in re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', tag):
            assert url.startswith("data:") or not re.match(r"https?:|//", url), tag


def test_the_page_writes_nothing_another_app_would_replay():
    """Read-only, and localStorage is shared by every app on the origin.

    The annotator replays `derek.spans.v1` into the golden set and the triage app
    replays `derek.ops.v1` into the ledger. The inspector must touch neither.
    """
    code = _script_without_comments()
    assert '"derek.spans.v1"' not in code
    assert '"derek.ops.v1"' not in code
    keys = set(re.findall(r'const K_\w+ = "([^"]+)";', code))
    assert keys == {"derek.theme", "derek.inspect.split", "derek.inspect.rule",
                    "derek.inspect.filter", "derek.inspect.view", "derek.annotate.page"}, keys


def test_open_in_annotator_names_the_annotators_own_page_key():
    """The inspector lands the annotator on a page by writing the key the
    annotator reads at boot. If the annotator renames it, this link silently
    opens the wrong page — so the two are asserted to agree."""
    annotator = (REPO / "tools" / "annotate" / "index.html").read_text(encoding="utf-8")
    theirs = re.search(r'const K_PAGE = "([^"]+)";', annotator).group(1)
    ours = re.search(r'const K_ANNOTATE_PAGE = "([^"]+)";', HTML).group(1)
    assert ours == theirs


def test_the_page_places_nothing_itself():
    """Placement is settled in Python by the function that mints the uid; the
    page draws offsets it was given. No text search decides a highlight."""
    code = _script_without_comments()
    for forbidden in (".indexOf(quote", ".indexOf(statement", "plain.indexOf", "plain.search("):
        assert forbidden not in code, forbidden


# ---------------------------------------------------------------------------
# What the build ships
# ---------------------------------------------------------------------------

def test_the_build_writes_a_site_the_page_can_boot_from(built):
    out = built["out"]
    assert (out / "index.html").read_text(encoding="utf-8") == HTML
    assert (out / ".nojekyll").exists()
    for key in ("build", "freeze", "glossary", "pages", "rules", "totals"):
        assert key in built["index"], key
    assert built["index"]["build"]["render_version"] == RENDER_VERSION


def test_every_rule_in_the_ledger_is_listed_once(built):
    ledger = load_ledger(REPO / "ledger" / "rules.jsonl")
    listed = [r["uid"] for r in built["index"]["rules"]]
    assert len(listed) == len(set(listed))
    assert set(listed) == set(ledger)
    in_payloads = [e["rule"]["uid"] for _, _, e in _entries(built)]
    assert sorted(in_payloads) == sorted(listed)


def test_the_shipped_blocks_are_the_corpus_projection(built):
    for path, payload in built["pages"].items():
        text = (REPO / "corpus" / "pages" / path).read_text(encoding="utf-8")
        page = NormalisedPage(path, text)
        assert [b.to_dict() for b in parse_blocks(path, page.text)] == payload["blocks"], path
        assert payload["sha256"] == page.sha256


def test_every_highlight_points_at_text_in_its_block(built):
    for path, payload, entry in _entries(built):
        plain = {b["id"]: b["plain"] for b in payload["blocks"]}
        o = entry["origin"]
        if o["anchor"]:
            a = o["anchor"]
            assert plain[a["block_id"]][a["start"]:a["end"]] == a["quote"], entry["rule"]["uid"]
        for part in [p for x in o["examples"] + o["preconditions"] for p in x["parts"]]:
            assert 0 <= part["start"] < part["end"] <= len(plain[part["block_id"]])


def test_a_span_rule_is_shown_on_the_span_that_mints_its_uid(built):
    """The claim the whole page makes, checked against the extractor itself."""
    golden = load_golden()
    checked = 0
    for path, payload in built["pages"].items():
        text = NormalisedPage(path, (REPO / "corpus" / "pages" / path)
                              .read_text(encoding="utf-8")).text
        minted = {cand.uid: span for span, cand in
                  golden_rules(path, text, golden.spans.get(path, []))}
        for entry in payload["rules"]:
            uid = entry["rule"]["uid"]
            o = entry["origin"]
            if uid in minted:
                span = minted[uid]
                assert o["how"] == "golden_span", uid
                assert o["span"]["span_id"] == span.span_id, uid
                assert (o["anchor"]["block_id"], o["anchor"]["start"], o["anchor"]["end"]) \
                    == (span.block_id, span.start, span.end), uid
                checked += 1
            else:
                assert o["how"] != "golden_span", uid
    assert checked > 1000


def test_a_heading_rule_is_shown_on_its_heading(built):
    for path, payload, entry in _entries(built):
        rule, o = entry["rule"], entry["origin"]
        if o["how"] != "heading":
            continue
        assert rule["derivation"]["method"] == "heading_structure"
        block = next(b for b in payload["blocks"] if b["id"] == o["anchor"]["block_id"])
        assert block["kind"] == "heading"
        assert block["line"] == rule["source"]["line_start"]
        assert o["anchor"]["start"] == 0 and o["anchor"]["end"] == len(block["plain"])


def test_every_live_rule_is_placed_exactly(built):
    """A rule that loads at runtime has to be traceable to the manual's words.

    `statement` placement is for retired rules whose span has gone; a live rule
    landing there would mean its uid no longer comes from where it is shown.
    """
    for _, _, entry in _entries(built):
        rule = entry["rule"]
        if rule["review"]["status"] in ReviewStatus.LOADABLE:
            assert entry["origin"]["how"] in ("golden_span", "heading"), rule["uid"]


def test_an_example_span_keeps_the_text_it_was_drawn_on(built):
    """An example tied to a span shows exactly that span's text, joined as
    golden.py joins a group, so the left pane and the page cannot disagree."""
    seen = 0
    for path, payload, entry in _entries(built):
        plain = {b["id"]: b["plain"] for b in payload["blocks"]}
        for x in entry["origin"]["examples"]:
            if x["how"] not in ("span", "span_only"):
                continue
            drawn = "\n".join(plain[p["block_id"]][p["start"]:p["end"]] for p in x["parts"])
            if x["how"] == "span_only":
                assert drawn == x["text"]
            seen += 1
    assert seen > 1000


def test_consensus_items_are_found_by_the_id_consensus_minted(built, module):
    consensus = module._consensus()
    linked = 0
    for path, _, entry in _entries(built):
        span = entry["origin"]["span"]
        for c in entry["consensus"]:
            item = c["item"]
            if item.get("rid"):
                a = span["anchor"]
                assert item["rid"] == consensus.item_id(path, "rule", a["block_id"],
                                                        a["start"], a["end"])
            else:
                assert item["uid"] == entry["rule"]["uid"]
            assert item["page_path"] == path
            linked += 1
    assert linked > 100


# ---------------------------------------------------------------------------
# Finding a ledger string in the page text
# ---------------------------------------------------------------------------

def test_text_is_found_through_canonical_quotes_and_whitespace(module):
    from derek.extract.blocks import Block

    block = Block(id="b", kind="para", level=2, heading_path=("P", "H"),
                  plain="Write  ‘don’t’ here.", marks=(), line=0)
    start, end = module._find("'don't' here", block)
    assert block.plain[start:end] == "‘don’t’ here"


def test_markdown_left_in_a_harvested_example_is_ignored(module):
    assert module._unmarked("*Theoretical Studies*, 2019") == "Theoretical Studies, 2019"


def test_a_clean_build_does_not_delete_its_siblings(built):
    """`site/` holds all three apps; the inspector owns `inspect/` and only that."""
    site = built["site"]
    assert (site / "annotate" / "index.html").read_text(encoding="utf-8") == "annotator"
    assert (site / "index.html").read_text(encoding="utf-8") == "triage"
    assert not (built["out"] / "stale.json").exists()
