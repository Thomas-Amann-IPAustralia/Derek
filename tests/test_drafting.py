"""Model drafts (ADR-025): the prompt is pinned, the model only points, the cache holds.

No model runs here and no SDK is imported. ``call_model`` is replaced by a fake
that returns what a model might, including the ways a model gets it wrong,
because the resolver's refusals are the part that has to be right.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "draft"


def _load_drafting():
    """tools/draft/drafting.py, by path like every other tool the tests use.

    Registered as ``drafting`` because that is the name draft_spans.py imports
    it by, so the command and the tests share one module and one DRAFTS path.
    """
    if "drafting" in sys.modules:
        return sys.modules["drafting"]
    spec = importlib.util.spec_from_file_location("drafting", TOOL / "drafting.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["drafting"] = module
    spec.loader.exec_module(module)
    return module


drafting = _load_drafting()

PRONOUNS = "grammar-punctuation-and-conventions/types-words/pronouns.md"
FULL_STOPS = "grammar-punctuation-and-conventions/punctuation/full-stops.md"


@pytest.fixture(scope="module")
def page():
    return drafting.load_page(FULL_STOPS)


def _block(page, prefix):
    return next(b for b in page.blocks if b.plain.startswith(prefix))


def _rule(block_id, quote, **extra):
    base = {
        "block_id": block_id, "quote": quote,
        "violation_condition": "something a checker flags", "direction": "presence",
        "modality": "SHOULD", "unit": "sentence", "applies_to": ["any"],
        "detection_hint": "pattern", "clarity_suggestion": "unambiguous",
        "specification": "", "when": [], "examples": [], "covers": [], "why": "",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def test_the_prompt_is_pinned():
    """ADR-003: a prompt change is a version bump, visible before it is paid for.

    If this fails you edited the prompt, the output schema, the glossary options
    it quotes, or docs/08-rule-grain.md. Bump PROMPT_VERSION in
    tools/draft/drafting.py and set PROMPT_SHA256 to the value below, together.
    """
    assert drafting.prompt_sha256() == drafting.PROMPT_SHA256, drafting.prompt_sha256()


def test_the_prompt_carries_the_grain_policy_verbatim():
    policy = (REPO / "docs" / "08-rule-grain.md").read_text(encoding="utf-8")
    assert policy in drafting.system_prompt()


def test_a_permission_is_not_offered_as_a_modality():
    """G-3 in the schema itself: a draft cannot propose a MAY rule."""
    rule = drafting.output_schema()["properties"]["rules"]["items"]
    assert "MAY" not in rule["properties"]["modality"]["enum"]
    assert "artifact" not in rule["properties"]["unit"]["enum"]


def test_the_page_is_shown_as_plain_blocks_with_the_heading_walks_candidates(page):
    text = drafting.render_page(page)
    lines = [l for l in text.splitlines() if l.startswith("[")]
    assert len(lines) == len(page.blocks)
    assert "**" not in text and "](" not in text, "no Markdown reaches the model (D-13)"
    assert "[7e2a0c5e492e] H2 ⟨candidate⟩  Complete a sentence with a full stop" in text
    assert " ⟨label⟩  Example" in text


def test_the_input_hash_ignores_the_ledger(page, monkeypatch):
    """Reviewing a page must not make its own draft stale."""
    before = drafting.input_sha256(page)
    again = drafting.load_page(FULL_STOPS)
    assert drafting.input_sha256(again) == before


# ---------------------------------------------------------------------------
# The model only points
# ---------------------------------------------------------------------------

def test_a_quote_resolves_to_the_manuals_own_characters(page):
    """A straight apostrophe from the model lands on the manual's curly one."""
    b = _block(page, "Following the same rule")
    raw = {"rules": [_rule(b.id, b.plain.replace("’", "'"))], "not_rules": []}
    [got] = drafting.resolve(page, raw).rules
    assert got["anchor"]["quote"] == b.plain
    assert "’" in got["anchor"]["quote"]


def test_a_quote_that_is_not_in_the_manual_is_refused(page):
    b = _block(page, "Don’t use full stops with contractions")
    raw = {"rules": [_rule(b.id, "Never use full stops with abbreviations of any kind.")],
           "not_rules": []}
    res = drafting.resolve(page, raw)
    assert not res.rules
    assert res.refused[0]["why"].startswith("not found exactly once")


def test_a_quote_on_an_unknown_block_is_refused(page):
    res = drafting.resolve(page, {"rules": [_rule("000000000000", "anything")], "not_rules": []})
    assert not res.rules and "no block" in res.refused[0]["why"]


def test_a_quote_that_appears_twice_in_its_block_is_refused():
    """Two places it could point is a guess, and a guess is refused."""
    from derek.extract.blocks import Block
    b = Block(id="b", kind="para", level=2, heading_path=("x",),
              plain="Use it. Use it.", marks=(), line=0)
    assert drafting.locate(b, "Use it.") is None
    assert drafting.locate(b, "Use it. Use") == (0, 11)


def test_the_page_title_is_not_a_rule(page):
    title = page.blocks[0]
    res = drafting.resolve(page, {"rules": [_rule(title.id, title.plain)], "not_rules": []})
    assert not res.rules and "title" in res.refused[0]["why"]


def test_an_example_drawn_from_its_own_rule_is_refused(page):
    """D-5, enforced on the model the same way as on a human."""
    b = _block(page, "Following the same rule")
    ex = {"polarity": "compliant", "note": "", "parts": [{"block_id": b.id, "quote": b.plain[:40]}]}
    res = drafting.resolve(page, {"rules": [_rule(b.id, b.plain, examples=[ex])], "not_rules": []})
    assert res.rules[0]["examples"] == []
    assert "D-5" in res.refused[0]["why"]


def test_a_multi_part_example_keeps_every_part(page):
    b = _block(page, "Following the same rule")
    lead = _block(page, "The committee met yesterday")
    items = [_block(page, t) for t in ("office space", "working hours", "managers")]
    ex = {"polarity": "compliant", "note": "",
          "parts": [{"block_id": x.id, "quote": x.plain} for x in (lead, *items)]}
    res = drafting.resolve(page, {"rules": [_rule(b.id, b.plain, examples=[ex])], "not_rules": []})
    [got] = res.rules[0]["examples"]
    assert [p["quote"] for p in got["parts"]] == [lead.plain] + [x.plain for x in items]


def test_a_tag_outside_the_vocabulary_is_blanked_not_trusted(page):
    b = _block(page, "Following the same rule")
    raw = {"rules": [_rule(b.id, b.plain, unit="paragraph-ish", direction="sideways")],
           "not_rules": []}
    tags = drafting.resolve(page, raw).rules[0]["tags"]
    assert tags["unit"] == "" and tags["direction"] == ""


def test_a_draft_on_a_candidate_heading_carries_its_uid(page):
    """So accepting it confirms the candidate rather than minting a second rule."""
    h = _block(page, "Don’t end web or email addresses")
    [got] = drafting.resolve(page, {"rules": [_rule(h.id, h.plain)], "not_rules": []}).rules
    assert got["seed_uid"] == page.seeds[h.id]


# ---------------------------------------------------------------------------
# The cache and the command
# ---------------------------------------------------------------------------

def _load_cli():
    spec = importlib.util.spec_from_file_location("derek_draft_spans", TOOL / "draft_spans.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(tmp_path, monkeypatch):
    module = _load_cli()
    monkeypatch.setattr(drafting, "DRAFTS", tmp_path / "drafts")
    calls = []

    def fake(system, user, schema):
        calls.append(user.splitlines()[0])
        page = drafting.load_page(user.splitlines()[0].removeprefix("PAGE: "))
        h = next(b for b in page.blocks if b.kind == "heading" and b.level == 2)
        return ({"rules": [_rule(h.id, h.plain)], "not_rules": []},
                drafting.MODEL, {"input_tokens": 10, "output_tokens": 5}, "end_turn")

    monkeypatch.setattr(module, "call_model", fake)
    module.calls = calls
    return module


def test_a_page_is_drafted_once_and_then_read_from_the_cache(cli, capsys):
    assert cli.main([FULL_STOPS]) == 0
    assert len(cli.calls) == 1
    path = drafting.draft_path(FULL_STOPS)
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["prompt_version"] == drafting.PROMPT_VERSION and rec["model"] == drafting.MODEL
    assert rec["input_sha256"] == drafting.input_sha256(drafting.load_page(FULL_STOPS))
    assert rec["rules"] and rec["raw"]["rules"]

    assert cli.main([FULL_STOPS]) == 0
    assert len(cli.calls) == 1, "a cached page must not be paid for twice"


def test_a_dry_run_calls_nothing_and_writes_nothing(cli):
    assert cli.main([FULL_STOPS, "--dry-run"]) == 0
    assert cli.calls == []
    assert not drafting.draft_path(FULL_STOPS).exists()


def test_an_unpinned_prompt_is_refused_before_anything_is_spent(cli, monkeypatch):
    monkeypatch.setattr(cli, "PROMPT_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="Bump PROMPT_VERSION"):
        cli.main([FULL_STOPS])
    assert cli.calls == []


def test_the_command_imports_no_sdk_at_module_level():
    """CI never installs the SDK; only call_model may import it."""
    tree = ast.parse((TOOL / "draft_spans.py").read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {a.name.split(".")[0] for n in top for a in n.names} | \
            {(n.module or "").split(".")[0] for n in top if isinstance(n, ast.ImportFrom)}
    assert "anthropic" not in names


# ---------------------------------------------------------------------------
# The blind set
# ---------------------------------------------------------------------------

def test_the_blind_set_is_the_declared_rule():
    blind = drafting.load_blind()
    pages = set(drafting.eligible_pages())
    assert set(blind) <= pages, "every blind page is a rule source"
    for p in ("grammar-punctuation-and-conventions/punctuation/commas.md", PRONOUNS,
              "referencing-and-attribution/legal-material/treaties.md"):
        assert p in blind, f"{p} was annotated before drafts existed"
    assert {p for p in pages if drafting.holdout(p)} <= set(blind), \
        "the standing holdout is listed explicitly, so it cannot drift"


def test_the_annotator_never_ships_a_draft_for_a_blind_page():
    spec = importlib.util.spec_from_file_location(
        "derek_annotate_build", REPO / "tools" / "annotate" / "build_static.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rec = {"prompt_version": "p1", "model": "m", "rules": [{"n": 0}], "not_rules": []}
    assert module._draft_payload(rec, blind=True) is None
    assert module._draft_payload(rec, blind=False)["rules"] == [{"n": 0}]
    assert module._draft_payload(None, blind=False) is None
