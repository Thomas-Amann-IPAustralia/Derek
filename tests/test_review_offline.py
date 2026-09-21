"""Tests for the published dashboard and the road back from it.

The review tool can now be served two ways: by `tools/review/server.py`, which
writes decisions straight to the ledger, and as a static site on GitHub Pages,
where there is no server and decisions queue in the browser until someone
exports them ([ADR-008](../docs/02-decisions.md#adr-008-human-acceptance-is-a-gate-not-a-review-queue)).

The second route only earns its place if it cannot become a way *around* the
gate. So the things asserted here are:

* **The same guard rails apply on the way in.** An export is replayed through
  the same `_apply` the server uses — a rule still cannot be kept without
  `clarity`, and `uid` / `source` / `derivation` are still not writable from a
  reviewer's hands. A file with one bad op writes nothing at all.
* **Replaying is safe.** Ops carry an id and are logged, so a reviewer who
  uploads the same file twice — or exports early and often, which they should —
  cannot double-record a decision.
* **The record keeps the reviewer's own time.** An offline decision made on
  Tuesday is not recorded as having been made whenever the file was uploaded.
* **The page works from a subpath.** Project pages live under `/Derek/`, so an
  absolute `/api/...` in the page would break the published copy while passing
  every local test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from derek.ledger.model import (                     # noqa: E402
    Clarity, Derivation, ReviewStatus, Rule, Source,
)

INDEX = REPO / "tools" / "review" / "index.html"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


server = _load("derek_review_server", REPO / "tools" / "review" / "server.py")
build_static = _load("derek_build_static", REPO / "tools" / "review" / "build_static.py")
apply_mod = _load("derek_apply_decisions", REPO / "tools" / "review" / "apply_decisions.py")


def a_rule(uid: str) -> Rule:
    return Rule(
        uid=uid,
        source=Source(page_path="p.md", heading_path=["A"], statement="Use commas"),
        derivation=Derivation(statement_form="imperative"),
        compliant_examples=["A sentence that follows the rule, with a comma."],
        violating_examples=["A sentence that does not follow the rule at all."],
    )


@pytest.fixture
def bench(tmp_path, monkeypatch):
    """A ledger, an example log and an op log, all in a temp directory."""
    ledger = tmp_path / "rules.jsonl"
    server.write_ledger(ledger, [a_rule("a" * 16), a_rule("b" * 16)])
    monkeypatch.setattr(server, "LEDGER", ledger)
    monkeypatch.setattr(server, "EXAMPLE_VERDICTS", tmp_path / "example_reviews.jsonl")
    monkeypatch.setattr(apply_mod, "OPS_LOG", tmp_path / "review_ops.jsonl")
    return tmp_path


def op(kind: str, op_id: str, **extra) -> dict:
    return {"op": kind, "op_id": op_id, "by": "TA",
            "at": "2026-01-02T03:04:05.000Z", **extra}


def keep(uid: str = "a" * 16, **patch) -> dict:
    base = {"review_status": "accepted", "unit": "sentence",
            "clarity": "unambiguous", "applies_to": ["any"], "elapsed_ms": 9000}
    return op("decide", "op-keep", uid=uid, patch={**base, **patch})


def write_ops(path: Path, ops: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(o) for o in ops) + "\n", encoding="utf-8")
    return path


def run(files: list[Path], **kw) -> dict:
    report = apply_mod.apply_ops(apply_mod.read_ops(files), server, **kw)
    if not report["errors"]:
        apply_mod.commit(report, server)
    return report


# ---------------------------------------------------------------------------
# The published page
# ---------------------------------------------------------------------------

def test_the_page_never_calls_an_absolute_api_path():
    """Project pages are served from /Derek/, not /.

    An absolute `/api/bootstrap` works on localhost and 404s on the published
    site — a break that no local test would ever see.
    """
    html = INDEX.read_text(encoding="utf-8")
    assert 'fetch("/' not in html
    assert '"/api/' not in html


def test_the_backend_marker_is_exactly_where_the_build_expects_it():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count(build_static.BACKEND_MARKER) == 1


def test_build_writes_a_site_the_page_can_boot_from(bench, tmp_path):
    manifest = build_static.build(tmp_path / "site", server=server)
    site = tmp_path / "site"

    assert (site / ".nojekyll").exists()            # Pages would run Jekyll otherwise
    assert 'window.DEREK_BACKEND = "static";' in (site / "index.html").read_text("utf-8")

    boot = json.loads((site / "data" / "bootstrap.json").read_text("utf-8"))
    assert boot["static"] is True
    assert len(boot["rules"]) == 2
    assert boot["counts"] == {ReviewStatus.PROPOSED: 2}
    # Everything the page reads out of /api/bootstrap has to be here too.
    for key in ("glossary", "options", "points", "hasty_ms", "rules", "counts", "total"):
        assert key in boot, key
    assert boot["hasty_ms"] == server.HASTY_MS

    board = json.loads((site / "data" / "leaderboard.json").read_text("utf-8"))
    assert set(board) == {"build", "day", "week", "all"}
    assert board["day"]["board"] == []               # nothing decided yet

    examples = json.loads((site / "data" / "examples.json").read_text("utf-8"))
    assert examples["total"] == 4                    # two rules, a pair each
    assert manifest["rules"] == 2


def test_build_refuses_a_glossary_that_has_drifted(bench, tmp_path, monkeypatch):
    """An unexplained option fails the Pages build, as it fails startup."""
    monkeypatch.setattr(server, "load_glossary",
                        lambda: (_ for _ in ()).throw(SystemExit("drifted")))
    with pytest.raises(SystemExit):
        build_static.build(tmp_path / "site", server=server)


# ---------------------------------------------------------------------------
# The road back: replaying an export into the ledger
# ---------------------------------------------------------------------------

def test_an_export_lands_in_the_ledger(bench):
    report = run([write_ops(bench / "e.jsonl", [
        {"op": "meta", "op_id": "m1", "by": "TA", "at": "2026-01-02T03:04:06Z"},
        keep(),
    ])])
    assert not report["errors"]

    rule = server.load_ledger(server.LEDGER)["a" * 16]
    assert rule.review.status == ReviewStatus.ACCEPTED
    assert rule.review.decided_by == "TA"
    assert rule.clarity == Clarity.UNAMBIGUOUS


def test_the_ledger_records_when_the_decision_was_made(bench):
    """Not when the file happened to be uploaded, which is nobody's fact."""
    run([write_ops(bench / "e.jsonl", [keep()])])
    move = server.load_ledger(server.LEDGER)["a" * 16].review.history[-1]
    assert move["at"] == "2026-01-02T03:04:05.000Z"


def test_replaying_the_same_export_changes_nothing(bench):
    path = write_ops(bench / "e.jsonl", [keep()])
    run([path])
    before = server.LEDGER.read_text(encoding="utf-8")

    second = run([path])
    assert second["applied"] == []
    assert any("already applied" in s for s in second["skipped"])
    assert server.LEDGER.read_text(encoding="utf-8") == before


def test_an_op_without_an_id_is_refused(bench):
    """An op that cannot be de-duplicated would be applied again on any replay."""
    bad = keep()
    del bad["op_id"]
    report = apply_mod.apply_ops(
        apply_mod.read_ops([write_ops(bench / "e.jsonl", [bad])]), server)
    assert any("op_id" in e for e in report["errors"])


@pytest.mark.parametrize("patch, expected", [
    ({"clarity": Clarity.UNREVIEWED}, "clarity"),          # kept without scope
    ({"uid": "hijacked"}, "not editable"),                 # provenance
    ({"source": {"statement": "mine now"}}, "not editable"),
    ({"review_status": "quarantined"}, "not settable"),    # pipeline's to give
    ({"unit": "invented"}, "unknown unit"),
])
def test_the_guard_rails_survive_the_round_trip(bench, patch, expected):
    decision = keep()
    decision["patch"].update(patch)
    report = apply_mod.apply_ops(
        apply_mod.read_ops([write_ops(bench / "e.jsonl", [decision])]), server)
    assert any(expected in e for e in report["errors"]), report["errors"]


def test_one_bad_op_holds_back_the_whole_file(bench):
    """Half a session in the ledger is worse than none: the reviewer can see a
    refusal, but cannot see which of their decisions quietly did not land."""
    report = run([write_ops(bench / "e.jsonl", [
        keep(),
        op("decide", "op-bad", uid="b" * 16,
           patch={"review_status": "accepted", "clarity": Clarity.UNREVIEWED}),
    ])])
    assert report["errors"]
    rules = server.load_ledger(server.LEDGER)
    assert rules["a" * 16].review.status == ReviewStatus.PROPOSED
    assert not apply_mod.OPS_LOG.exists()


def test_skip_invalid_applies_the_rest(bench):
    report = run([write_ops(bench / "e.jsonl", [
        keep(),
        op("decide", "op-bad", uid="b" * 16,
           patch={"review_status": "accepted", "clarity": Clarity.UNREVIEWED}),
    ])], skip_invalid=True)
    assert not report["errors"]
    rules = server.load_ledger(server.LEDGER)
    assert rules["a" * 16].review.status == ReviewStatus.ACCEPTED
    assert rules["b" * 16].review.status == ReviewStatus.PROPOSED


def test_an_undo_is_recorded_rather_than_erased(bench):
    run([write_ops(bench / "e.jsonl", [
        keep(),
        op("undo", "op-undo", uid="a" * 16),
    ])])
    review = server.load_ledger(server.LEDGER)["a" * 16].review
    assert review.status == ReviewStatus.PROPOSED
    assert [m["to"] for m in review.history] == [
        ReviewStatus.ACCEPTED, ReviewStatus.PROPOSED]


def test_a_hasty_offline_decision_is_still_marked(bench):
    """The threshold belongs to the ledger, not to the page that collected it."""
    run([write_ops(bench / "e.jsonl", [keep(elapsed_ms=200)])])
    note = server.load_ledger(server.LEDGER)["a" * 16].review.history[-1]["note"]
    assert "(hasty)" in note


def test_a_rejection_keeps_its_reasons(bench):
    run([write_ops(bench / "e.jsonl", [op(
        "decide", "op-bin", uid="a" * 16,
        patch={"review_status": "rejected", "reasons": ["not_text"],
               "unit": "artifact", "clarity": Clarity.NOT_AUTOMATABLE,
               "elapsed_ms": 9000},
    )])])
    rule = server.load_ledger(server.LEDGER)["a" * 16]
    assert rule.review.status == ReviewStatus.REJECTED
    assert "[not_text]" in rule.review.note


def test_example_verdicts_land_in_their_own_log(bench):
    run([write_ops(bench / "e.jsonl", [op(
        "example", "op-ex",
        item={"id": "a" * 16 + "-compliant-0", "rule_uid": "a" * 16,
              "origin": "style_manual", "claimed": "compliant"},
        verdict="accept", reasons=[], note="",
    )])])
    rows = [json.loads(x) for x in
            server.EXAMPLE_VERDICTS.read_text("utf-8").splitlines() if x.strip()]
    assert [r["verdict"] for r in rows] == ["accept"]
    assert rows[0]["by"] == "TA"


def test_ops_from_several_files_apply_in_the_order_they_were_made(bench):
    """Two reviewers' exports read as one chronology, not as two piles."""
    first = write_ops(bench / "one.jsonl", [
        {**keep(), "op_id": "late", "at": "2026-01-02T05:00:00Z"}])
    second = write_ops(bench / "two.jsonl", [
        {**op("decide", "early", uid="a" * 16,
              patch={"review_status": "deferred", "elapsed_ms": 9000}),
         "at": "2026-01-02T04:00:00Z"}])
    run([first, second])
    history = server.load_ledger(server.LEDGER)["a" * 16].review.history
    assert [m["to"] for m in history] == [
        ReviewStatus.DEFERRED, ReviewStatus.ACCEPTED]


def test_a_file_that_is_not_an_export_is_refused(bench):
    (bench / "junk.jsonl").write_text('{"hello": "world"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        apply_mod.read_ops([bench / "junk.jsonl"])
