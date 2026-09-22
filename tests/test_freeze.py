"""The corpus freeze has to actually hold (ADR-024).

Golden-set spans are anchored to the page text they were drawn on. If the daily
snapshot rewrites `corpus/pages/` while the corpus is declared frozen, every
recorded span on an edited page silently moves — and the dangerous outcome is
not a span that fails to resolve but one that resolves to the wrong sentence.

So this drives `snapshot.run()` against a fake transport and asserts what it
does and does not touch, rather than trusting a flag to be read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from derek.corpus import snapshot
from derek.corpus.diff import PageState, Snapshot, load_lock, write_lock
from derek.corpus.freeze import Freeze, load_freeze, lock_digest

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# The declaration itself
# ---------------------------------------------------------------------------

def test_the_repo_declares_its_freeze_and_pins_the_corpus_it_froze():
    freeze = load_freeze()
    if not freeze.frozen:
        pytest.skip("corpus is live; nothing to pin")
    assert freeze.frozen_at, "a freeze with no date cannot be reasoned about"
    assert freeze.reason, "ADR-024: a freeze states why, or nobody knows when to lift it"
    assert freeze.lock_digest == lock_digest(REPO / "corpus" / "snapshot.lock.json"), (
        "freeze.yaml pins a different corpus from the one in snapshot.lock.json — "
        "either the lock moved while frozen, or the digest was never recorded"
    )


def test_an_absent_declaration_means_live():
    assert not load_freeze(REPO / "corpus" / "does-not-exist.yaml")


def test_the_reader_handles_the_folded_block_scalar():
    """`reason` is written as `>-` across several lines; it must come back whole."""
    freeze = load_freeze()
    if not freeze.frozen:
        pytest.skip("corpus is live")
    assert "\n" not in freeze.reason
    assert len(freeze.reason) > 80, "a folded scalar was truncated to its first line"


# ---------------------------------------------------------------------------
# What run() touches
# ---------------------------------------------------------------------------

class _Driver:
    def quit(self) -> None:
        pass


class _Transport:
    """Enough of `derek.corpus.fetch` to drive run() with no network."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def initialize_driver(self):
        return _Driver()

    def check_robots_txt(self, base, driver):
        return True

    def fetch_sitemap_with_retry(self, url, driver):
        return "<sitemap/>"

    def parse_sitemap(self, body, url, driver):
        return [{"loc": u, "lastmod": "2026-09-22T00:00:00+00:00"} for u in self.pages]

    def fetch_with_retry(self, url, driver):
        return self.pages[url]


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """A one-page corpus on disk, with a lock that matches it."""
    pages = tmp_path / "pages"
    pages.mkdir()
    rel = "a/b.md"
    (pages / "a").mkdir()
    original = "# Title\n\nOriginal sentence.\n"
    (pages / rel).write_text(original, encoding="utf-8")

    url = "https://www.stylemanual.gov.au/a/b"
    lock_path = tmp_path / "snapshot.lock.json"
    snap = Snapshot(generated_at="2026-09-22T00:00:00+00:00")
    from derek.corpus.normalise import NormalisedPage
    snap.pages[rel] = PageState(
        url=url, path=rel, sha256=NormalisedPage(rel, original).sha256,
        lastmod="2026-01-01T00:00:00+00:00", fetched_at="2026-01-01T00:00:00+00:00",
        extractor=snapshot.EXTRACTOR_ID,
    )
    write_lock(lock_path, snap)

    monkeypatch.setattr(snapshot, "PAGES", pages)
    monkeypatch.setattr(snapshot, "LOCK", lock_path)
    monkeypatch.setattr(snapshot, "CHANGES", tmp_path / "changes")
    monkeypatch.setattr(snapshot, "DRIFT", tmp_path / "drift.json")
    monkeypatch.setattr(snapshot, "HEARTBEAT", tmp_path / ".heartbeat")
    monkeypatch.setattr(snapshot, "ELIGIBILITY", REPO / "corpus" / "eligibility.yaml")
    monkeypatch.setattr(snapshot, "time", type("_T", (), {"sleep": staticmethod(lambda n: None)}))

    # The upstream page has been edited since the snapshot.
    edited = "<h1>Title</h1><p>Edited sentence.</p>"
    transport = _Transport({url: edited})
    import sys, types
    module = types.ModuleType("derek.corpus.fetch")
    for name in ("initialize_driver", "check_robots_txt", "fetch_sitemap_with_retry",
                 "parse_sitemap", "fetch_with_retry"):
        setattr(module, name, getattr(transport, name))
    monkeypatch.setitem(sys.modules, "derek.corpus.fetch", module)

    return types.SimpleNamespace(
        tmp=tmp_path, pages=pages, rel=rel, url=url, original=original,
        lock=lock_path, drift=tmp_path / "drift.json",
        heartbeat=tmp_path / ".heartbeat",
    )


def _drop_from_sitemap(bench) -> None:
    """The page leaves the sitemap, but the sitemap is not empty.

    An empty sitemap is a fetch failure by design (`run` refuses rather than
    orphaning the whole corpus), so a removal has to be tested against a sitemap
    that still lists something.
    """
    import sys
    other = "https://www.stylemanual.gov.au/z/other"
    fetch = sys.modules["derek.corpus.fetch"]
    fetch.parse_sitemap = lambda *a: [
        {"loc": other, "lastmod": "2026-09-22T00:00:00+00:00"}
    ]
    fetch.fetch_with_retry = lambda url, driver: "<h1>Other</h1><p>Other page.</p>"


def _freeze(monkeypatch, frozen: bool) -> None:
    monkeypatch.setattr(
        snapshot, "load_freeze",
        lambda *a, **k: Freeze(
            frozen=frozen, frozen_at="2026-09-22T00:00:00+00:00",
            reason="test", lock_digest="deadbeef",
        ),
    )


def test_a_frozen_snapshot_does_not_rewrite_the_page(bench, monkeypatch):
    _freeze(monkeypatch, True)
    before = (bench.pages / bench.rel).read_bytes()
    lock_before = bench.lock.read_bytes()

    assert snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False) == 0

    assert (bench.pages / bench.rel).read_bytes() == before, \
        "a frozen corpus was rewritten — every span on this page just moved"
    assert bench.lock.read_bytes() == lock_before, \
        "the lock moved, so it no longer describes the frozen corpus"


def test_a_frozen_snapshot_still_reports_the_drift(bench, monkeypatch):
    _freeze(monkeypatch, True)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)

    report = json.loads(bench.drift.read_text(encoding="utf-8"))
    rows = {r["path"]: r for r in report["drifted"]}
    assert bench.rel in rows, "an upstream edit went unreported"
    assert rows[bench.rel]["state"] == "altered"
    assert rows[bench.rel]["frozen_sha256"] != rows[bench.rel]["live_sha256"]


def test_an_unchanged_drift_report_is_byte_identical(bench, monkeypatch):
    """So a quiet day produces no commit, and `git log` is the drift timeline."""
    _freeze(monkeypatch, True)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    first = bench.drift.read_bytes()
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    assert bench.drift.read_bytes() == first


def test_drift_clears_when_a_page_goes_back_to_matching(bench, monkeypatch):
    _freeze(monkeypatch, True)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    assert json.loads(bench.drift.read_text())["drifted"]

    import sys
    sys.modules["derek.corpus.fetch"].fetch_with_retry = \
        lambda url, driver: "<h1>Title</h1><p>Original sentence.</p>"
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    assert json.loads(bench.drift.read_text())["drifted"] == []


def test_a_frozen_snapshot_still_refreshes_the_heartbeat(bench, monkeypatch):
    """The freshness gate asks whether the crawler is alive (ADR-001).

    It guards GitHub disabling a scheduled workflow after 60 days of repository
    inactivity, and that trap does not care that the corpus is frozen.
    """
    _freeze(monkeypatch, True)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    assert bench.heartbeat.exists() and bench.heartbeat.read_text().strip()


def test_a_frozen_snapshot_keeps_a_page_that_left_the_sitemap(bench, monkeypatch):
    """A page vanishing upstream must not delete the file mid-annotation."""
    _freeze(monkeypatch, True)
    _drop_from_sitemap(bench)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)

    assert (bench.pages / bench.rel).exists(), "a frozen page was deleted"
    rows = {r["path"]: r for r in json.loads(bench.drift.read_text())["drifted"]}
    assert rows[bench.rel]["state"] == "removed", "the removal went unreported"


def test_a_live_snapshot_still_applies_everything(bench, monkeypatch):
    """The freeze is the special case; unfrozen behaviour must be untouched."""
    _freeze(monkeypatch, False)
    assert snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False) == 0

    from derek.corpus.normalise import NormalisedPage

    on_disk = (bench.pages / bench.rel).read_text(encoding="utf-8")
    assert "Edited sentence." in on_disk, "a live run must apply the upstream edit"
    assert load_lock(bench.lock).pages[bench.rel].sha256 == \
        NormalisedPage(bench.rel, on_disk).sha256, \
        "the lock must describe the page it just wrote"
    assert not bench.drift.exists(), "a live run should write no drift report"
    assert list((bench.tmp / "changes").glob("*.json")), "a live run writes a changeset"


def test_a_live_snapshot_deletes_a_page_that_left_the_sitemap(bench, monkeypatch):
    _freeze(monkeypatch, False)
    _drop_from_sitemap(bench)
    snapshot.run(False, None, "https://www.stylemanual.gov.au/sitemap.xml", False)
    assert not (bench.pages / bench.rel).exists()
