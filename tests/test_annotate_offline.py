"""The annotator is a published static page, with the same constraints as the
triage dashboard (ADR-022) and one of its own.

The extra one: everything about a span's address — which block, which offsets —
is computed in the browser and resolved in Python. If the payload the build ships
stops matching what `derek.extract.blocks` produces, a reviewer's selection lands
at the wrong offset and the failure is silent, because a wrong offset still
resolves to *some* text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from derek.corpus.normalise import NormalisedPage
from derek.extract.blocks import RENDER_VERSION, parse_blocks

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "tools" / "annotate" / "index.html"
HTML = PAGE.read_text(encoding="utf-8")


def _script_without_comments() -> str:
    """The page's executable JavaScript, comments removed.

    The comments say what the code deliberately does NOT do, so a naive substring
    search over the whole file finds the very words it is checking for.
    """
    body = re.findall(r"<script>(.*?)</script>", HTML, re.S)[-1]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", body)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build the annotator once and hand the tests its output directory."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "derek_annotate_build", REPO / "tools" / "annotate" / "build_static.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    out = tmp_path_factory.mktemp("annotate")
    manifest = module.build(out)
    return {"out": out, "manifest": manifest, "module": module}


# ---------------------------------------------------------------------------
# ADR-022: the published page makes no assumption about where it is served from
# ---------------------------------------------------------------------------

def test_the_page_never_calls_an_absolute_path():
    """Project pages live under /Derek/, so a leading slash reaches the wrong host."""
    assert 'fetch("/' not in HTML
    assert '"/data/' not in HTML
    assert "'/data/" not in HTML


def test_the_backend_marker_is_exactly_where_the_build_expects_it():
    assert HTML.count('window.DEREK_BACKEND = "server";') == 1


def test_the_page_loads_no_external_resource():
    """No CDN, no font host, no framework — the same rule as the triage app.

    Links a reviewer can *click* (the live Style Manual page, the github.com
    upload form) are fine and are not what this is about: the test is that
    nothing is fetched to render the page.
    """
    tags = re.findall(r"<(script|link|img|iframe|source)\b[^>]*>", HTML, re.I)
    for tag in tags:
        urls = re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', tag)
        for url in urls:
            assert url.startswith("data:") or not re.match(r"https?:|//", url), tag


def test_the_annotator_does_not_share_the_triage_op_log():
    """localStorage is scoped to the ORIGIN, not the path.

    Both apps are served from the same github.io origin. A shared key would have
    the annotator's span ops replayed as triage decisions, and the corruption
    would be invisible until somebody exported.
    """
    assert '"derek.spans.v1"' in HTML
    assert '"derek.ops.v1"' not in HTML, \
        "that key belongs to tools/review/index.html and the two share an origin"
    assert '"derek.reviewer"' in HTML, "initials are shared on purpose"


def test_the_page_computes_no_ledger_value():
    """No UID, no hash, no modality inference in the browser (ADR-023).

    A span is recorded as the tuple it was drawn at; Python mints its id. A wrong
    JS hash would produce ops pointing at UIDs that do not exist, and the triage
    app's one JS mirror of a Python function already documents its discomfort.
    """
    code = _script_without_comments()
    # The hashing primitives, not the word "sha256": a span legitimately CARRIES
    # `page_sha256`, the content hash of the page it was drawn on. What it must
    # not do is compute one.
    for forbidden in ("blake2", "crypto.subtle", ".digest(", "sha256("):
        assert forbidden not in code, forbidden
    # And the span's own address is the tuple it was drawn at, hashed in Python.
    assert "keyOf" in code and "span_id" not in code, \
        "the browser should reference spans by their tuple, not by a minted id"


# ---------------------------------------------------------------------------
# What the build ships
# ---------------------------------------------------------------------------

def test_the_build_writes_a_site_the_page_can_boot_from(built):
    out = built["out"]
    assert (out / "index.html").exists()
    assert (out / ".nojekyll").exists()
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    for key in ("build", "freeze", "glossary", "options", "pages", "totals"):
        assert key in index, key
    assert index["static"] is True
    assert 'window.DEREK_BACKEND = "static";' in (out / "index.html").read_text(encoding="utf-8")


def test_every_listed_page_has_a_payload(built):
    out = built["out"]
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["totals"]["pages"] > 100
    for meta in index["pages"]:
        assert (out / "data" / "pages" / f"{meta['slug']}.json").exists(), meta["path"]


def test_the_shipped_blocks_are_the_ones_python_will_resolve_against(built):
    """The whole anchoring scheme rests on this.

    A reviewer's offset is computed against the `plain` in the payload; Python
    resolves it against `parse_blocks`. If the two ever differ the span silently
    moves, and it still resolves — to the wrong text.
    """
    out = built["out"]
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    checked = 0
    for meta in index["pages"]:
        if not meta["eligible"]:
            continue
        payload = json.loads(
            (out / "data" / "pages" / f"{meta['slug']}.json").read_text(encoding="utf-8"))
        source = REPO / "corpus" / "pages" / meta["path"]
        fresh = parse_blocks(
            meta["path"],
            NormalisedPage(meta["path"], source.read_text(encoding="utf-8")).text)
        assert [b.to_dict() for b in fresh] == payload["blocks"], meta["path"]
        assert payload["sha256"] == NormalisedPage(
            meta["path"], source.read_text(encoding="utf-8")).sha256
        checked += 1
    assert checked > 100


def test_the_payload_declares_the_renderer_it_was_built_with(built):
    """A span recorded against one projection cannot be trusted against another."""
    index = json.loads(
        (built["out"] / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["build"]["render_version"] == RENDER_VERSION


def test_every_seeded_candidate_maps_to_a_block(built):
    """The 736 heading candidates are the first cut, shown as confirmable
    highlights. One that cannot be placed is one the reviewer never sees, which
    is the failure mode this whole exercise exists to fix."""
    out = built["out"]
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    total = unmatched = 0
    for meta in index["pages"]:
        payload = json.loads(
            (out / "data" / "pages" / f"{meta['slug']}.json").read_text(encoding="utf-8"))
        ids = {b["id"] for b in payload["blocks"]}
        for seed in payload["seeds"]:
            total += 1
            if seed["block_id"] not in ids:
                unmatched += 1
    assert total > 700, total
    assert unmatched == 0, unmatched


def test_ineligible_pages_are_shown_but_carry_no_seeds(built):
    """Readable, so the reviewer can see the whole manual; not annotatable,
    because `corpus/eligibility.yaml` decides what a rule source is (D-4)."""
    out = built["out"]
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    ineligible = [p for p in index["pages"] if not p["eligible"]]
    assert ineligible, "the excluded pages should still be browsable"
    for meta in ineligible:
        payload = json.loads(
            (out / "data" / "pages" / f"{meta['slug']}.json").read_text(encoding="utf-8"))
        assert payload["seeds"] == []
        assert payload["eligibility_reason"]


def test_the_build_refuses_a_glossary_that_has_drifted(built, tmp_path, monkeypatch):
    """An unexplained option fails the Pages build, as it fails server startup."""
    module = built["module"]
    server = module._load_server()
    monkeypatch.setattr(server, "GLOSSARY", tmp_path / "glossary.json")
    (tmp_path / "glossary.json").write_text('{"buckets": {}}', encoding="utf-8")
    with pytest.raises(SystemExit):
        module.build(tmp_path / "site", server=server)


def test_a_clean_build_does_not_delete_its_sibling(tmp_path, built):
    """`site/` holds both apps. The triage build owns the root and the annotator
    owns `annotate/`; a clean run of either must not take the other with it."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "derek_review_build", REPO / "tools" / "review" / "build_static.py")
    review = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = review
    spec.loader.exec_module(review)

    site = tmp_path / "site"
    review.build(site)
    built["module"].build(site / "annotate")
    assert (site / "index.html").exists()
    assert (site / "annotate" / "index.html").exists()

    review.build(site, clean=False)
    assert (site / "annotate" / "index.html").exists(), \
        "a --no-clean rebuild of the triage app deleted the annotator"
