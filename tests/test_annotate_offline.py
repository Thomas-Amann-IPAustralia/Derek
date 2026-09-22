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


# ---------------------------------------------------------------------------
# The return leg: export → golden set → ledger
# ---------------------------------------------------------------------------

SAMPLE = "grammar-punctuation-and-conventions/punctuation/commas.md"


@pytest.fixture
def replay(tmp_path, monkeypatch):
    """`apply_spans.py` pointed at a throwaway golden set and ledger.

    Every path it writes is redirected, including the ones `derek.extract.build`
    reads for itself — the module-level `GOLDEN_SPANS` the rebuild consults has
    to be the same file the replay just wrote, or the two stages would disagree
    about what the golden set is.
    """
    import importlib.util
    import shutil
    import sys

    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    apply_spans = load("derek_apply_spans", REPO / "tools" / "annotate" / "apply_spans.py")
    from derek.extract import build as build_mod

    spans = tmp_path / "spans.jsonl"
    pages = tmp_path / "pages.jsonl"
    ops = tmp_path / "span_ops.jsonl"
    ledger = tmp_path / "rules.jsonl"
    shutil.copy(REPO / "ledger" / "rules.jsonl", ledger)

    for target, name, value in (
        (apply_spans, "GOLDEN_SPANS", spans), (apply_spans, "GOLDEN_PAGES", pages),
        (apply_spans, "SPAN_OPS", ops), (apply_spans, "LEDGER", ledger),
        (build_mod, "GOLDEN_SPANS", spans), (build_mod, "GOLDEN_PAGES", pages),
    ):
        monkeypatch.setattr(target, name, value)

    server = apply_spans._load("derek_review_server",
                               REPO / "tools" / "review" / "server.py")
    monkeypatch.setattr(server, "LEDGER", ledger)
    monkeypatch.setattr(apply_spans, "_load", lambda name, path: (
        server if path.name == "server.py" else load(name, path)))

    import types
    return types.SimpleNamespace(
        module=apply_spans, tmp=tmp_path, spans=spans, pages=pages,
        ops=ops, ledger=ledger, server=server,
    )


def _blocks_of(rel: str = SAMPLE):
    src = REPO / "corpus" / "pages" / rel
    return parse_blocks(rel, NormalisedPage(rel, src.read_text(encoding="utf-8")).text)


def _export(tmp_path, ops: list[dict], *, render_version: str | None = None,
            name: str = "derek-spans-TA-1.jsonl") -> Path:
    """An op log in exactly the shape the browser downloads."""
    meta = {
        "op": "meta", "op_id": "00000000-0000-4000-8000-00000000meta",
        "by": "TA", "at": "2026-09-22T00:00:00.000Z", "app": "annotate",
        "render_version": render_version or RENDER_VERSION,
    }
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(o) for o in [meta, *ops]) + "\n", encoding="utf-8")
    return path


def _span_op(block, start=None, end=None, *, kind="rule", of="", tags=None,
             preconditions=(), seed_uid="", oid="op-1", at="2026-09-22T01:00:00.000Z"):
    start = 0 if start is None else start
    end = len(block.plain) if end is None else end
    span = {
        "kind": kind, "page_path": SAMPLE, "page_sha256": "",
        "anchor": {
            "block_id": block.id, "start": start, "end": end,
            "quote": block.plain[start:end],
            "prefix": block.plain[max(0, start - 32):start],
            "suffix": block.plain[end:end + 32],
        },
        "of": of,
    }
    if kind == "rule":
        span["tags"] = dict(tags or {})
        span["preconditions"] = list(preconditions)
        span["seed_uid"] = seed_uid
    return {"op": "span", "op_id": oid, "by": "TA", "at": at, "span": span}


ACCEPT = {
    "review_status": "accepted", "unit": "sentence", "clarity": "unambiguous",
    "direction": "absence", "modality": "MUST", "applies_to": ["any"],
}


def test_an_export_reaches_the_golden_set_and_the_ledger(replay):
    """The whole loop, end to end.

    A rule span on prose — the class the heading walk cannot reach at all — plus
    an example attached to it, through export, golden set, rebuild and the
    review gate.
    """
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    item = next(b for b in blocks if b.kind == "li")

    rule = _span_op(prose, tags=ACCEPT, preconditions=["in body prose"], oid="op-rule")
    example = _span_op(
        item, kind="violating",
        of=f"{prose.id}|0|{len(prose.plain)}|rule", oid="op-ex")
    path = _export(replay.tmp, [rule, example])

    assert replay.module.main([str(path)]) == 0

    spans = [json.loads(x) for x in replay.spans.read_text(encoding="utf-8").splitlines()]
    assert {s["kind"] for s in spans} == {"rule", "violating"}
    # The browser sends the parent as the tuple it was drawn at; Python mints the id.
    parent = next(s for s in spans if s["kind"] == "rule")
    child = next(s for s in spans if s["kind"] == "violating")
    assert child["of"] == parent["span_id"]

    from derek.ledger.store import load_ledger
    rules = load_ledger(replay.ledger)
    made = [r for r in rules.values() if r.derivation.method == "human_span"]
    assert len(made) == 1, [r.source.statement for r in made]
    got = made[0]
    assert got.source.statement == prose.plain
    assert got.source.page_path == SAMPLE
    assert got.violating_examples == [item.plain]
    assert got.context_preconditions == ["in body prose"]
    assert got.review.status == "accepted"
    assert got.unit == "sentence" and got.modality == "MUST"
    # The decision is recorded at the reviewer's own time, not the upload's.
    assert got.review.history[-1]["by"] == "TA"
    assert got.review.history[-1]["at"].startswith("2026-09-22T01:00")


def test_replaying_the_same_export_changes_nothing(replay):
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    path = _export(replay.tmp, [_span_op(prose, tags=ACCEPT)])

    assert replay.module.main([str(path)]) == 0
    after_first = (replay.spans.read_bytes(), replay.ledger.read_bytes())

    assert replay.module.main([str(path)]) == 0
    assert (replay.spans.read_bytes(), replay.ledger.read_bytes()) == after_first


def test_one_bad_op_writes_nothing(replay):
    """A session lands complete or not at all, as ADR-022 requires of the triage
    export for the same reason: half a session in the record is worse than none."""
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    good = _span_op(prose, tags=ACCEPT, oid="op-good")
    bad = _span_op(prose, tags=ACCEPT, oid="op-bad")
    bad["span"]["anchor"]["quote"] = "text that is not in this block at all"
    path = _export(replay.tmp, [good, bad])

    before = replay.ledger.read_bytes()
    assert replay.module.main([str(path)]) == 1
    assert not replay.spans.exists()
    assert replay.ledger.read_bytes() == before


def test_skip_invalid_applies_the_rest(replay):
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    good = _span_op(prose, tags=ACCEPT, oid="op-good")
    bad = _span_op(prose, tags=ACCEPT, oid="op-bad")
    bad["span"]["anchor"]["block_id"] = "0000deadbeef"
    path = _export(replay.tmp, [good, bad])

    assert replay.module.main([str(path), "--skip-invalid"]) == 0
    spans = [json.loads(x) for x in replay.spans.read_text(encoding="utf-8").splitlines()]
    assert len(spans) == 1


def test_a_dry_run_writes_nothing(replay):
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    path = _export(replay.tmp, [_span_op(prose, tags=ACCEPT)])
    assert replay.module.main([str(path), "--dry-run"]) == 0
    assert not replay.spans.exists()


def test_an_export_from_a_different_renderer_is_refused(replay):
    """A span's offsets mean nothing without the projection that produced them.

    The triage export needs no equivalent check — a decision is about a uid, and
    a uid is stable. A span is about a position (ADR-023).
    """
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    path = _export(replay.tmp, [_span_op(prose, tags=ACCEPT)], render_version="0.9.0")
    with pytest.raises(SystemExit, match="renderer"):
        replay.module.main([str(path)])
    assert not replay.spans.exists()


def test_tags_land_through_the_review_gate_not_the_build(replay):
    """`server._apply`'s refusals still apply to a decision typed in the annotator.

    Keeping a rule without setting clarity is refused there; it has to be refused
    here too, or the annotator would be a way around the gate (D-10).
    """
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    tags = {**ACCEPT, "clarity": "unreviewed"}
    path = _export(replay.tmp, [_span_op(prose, tags=tags)])
    with pytest.raises(ValueError, match="set clarity"):
        replay.module.main([str(path)])


def test_an_interpretation_still_has_to_be_written_down(replay):
    blocks = _blocks_of()
    prose = next(b for b in blocks if b.kind == "para" and b.heading_path)
    tags = {**ACCEPT, "clarity": "ambiguous_resolvable"}
    path = _export(replay.tmp, [_span_op(prose, tags=tags)])
    with pytest.raises(ValueError, match="your interpretation"):
        replay.module.main([str(path)])


def test_a_span_on_an_excluded_page_is_refused(replay):
    """D-4 / ADR-005, enforced at the point the span enters the record."""
    rel = "about-style-manual/changelog.md"
    block = next(b for b in _blocks_of(rel) if b.kind == "para")
    op = _span_op(block, tags=ACCEPT)
    op["span"]["page_path"] = rel
    op["span"]["anchor"]["block_id"] = block.id
    path = _export(replay.tmp, [op])

    assert replay.module.main([str(path)]) == 1
    assert not replay.spans.exists()


def test_confirming_a_heading_keeps_its_review_state(replay):
    """The reason the extractor's 736 are worth keeping rather than discarding."""
    from derek.ledger.store import load_ledger

    before = load_ledger(replay.ledger)
    blocks = _blocks_of()
    heading, existing = next(
        (b, r) for b in blocks if b.kind == "heading" and b.level >= 2
        for r in before.values()
        if r.source.page_path == SAMPLE and r.source.statement == b.plain
    )
    path = _export(replay.tmp, [
        _span_op(heading, tags=ACCEPT, seed_uid=existing.uid)])

    assert replay.module.main([str(path)]) == 0
    after = load_ledger(replay.ledger)
    assert len(after) == len(before), "confirming a candidate must not add a second rule"
    got = after[existing.uid]
    assert got.derivation.method == "human_span"
    assert got.source.statement == existing.source.statement
    assert got.derivation.supersedes is None
