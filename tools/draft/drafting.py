"""Model-drafted rule spans: the prompt, the pointer check, the cache (ADR-025).

Everything here is stdlib, so CI can test the prompt, the validation and the
cache layout with no model installed and no key. The one function that calls a
model lives in ``draft_spans.py`` and imports the SDK lazily.

**The model only points.** It is shown one page as numbered blocks, and every
rule, example and exclusion it returns is a block id plus a quote copied from
that block. ``resolve`` turns each quote into offsets in the manual's own text
or refuses it. Nothing the model *wrote* can become a rule statement or an
example; the most it can author is the violation condition and the other tags,
which a reviewer confirms field by field. That is the structural difference
from Octavius, where the same model call wrote the rules and the tests that
passed them (postmortem F4, D-1).

**It is a cache, not a step (ADR-003).** A draft is written once per
(page, prompt version, model) under ``golden/drafts/``, carrying a hash of its
exact input. Re-running is a no-op; a changed prompt without a version bump is
refused as stale rather than silently overwritten. ``tests/test_drafting.py``
pins the prompt's hash, so editing the prompt or the grain policy it embeds
fails CI until ``PROMPT_VERSION`` is bumped, which makes the blast radius of
a prompt edit visible before anyone pays for it.

**Nothing in extraction reads a draft.** ``golden/drafts/`` is not a declared
input to ``derek.extract.build``. Only a span a human accepted, in
``golden/spans.jsonl``, is. That keeps D-7 intact: a model proposes, a human
decides a rule exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

import sys  # noqa: E402

sys.path.insert(0, str(REPO))

from derek.corpus.eligibility import load_eligibility                  # noqa: E402
from derek.corpus.normalise import NormalisedPage                      # noqa: E402
from derek.extract.blocks import RENDER_VERSION, Block, parse_blocks   # noqa: E402
from derek.extract.modality import Modality                             # noqa: E402
from derek.ledger.model import DetectionHint, Direction, Unit           # noqa: E402

PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
POLICY = REPO / "docs" / "08-rule-grain.md"
GLOSSARY = REPO / "tools" / "review" / "glossary.json"
DRAFTS = REPO / "golden" / "drafts"
BLIND = REPO / "golden" / "blind.json"

# Bump PROMPT_VERSION whenever the rendered prompt changes, including any edit to
# docs/08-rule-grain.md, which it embeds. tests/test_drafting.py compares the
# live prompt against PROMPT_SHA256 and fails until both are updated together.
PROMPT_VERSION = "p1"
PROMPT_SHA256 = "cedc0382b5e520e095289965a6d4c4df383ec023dd299f399c64c7e63a2e41cd"

# Pinned for the same reason the tagger and the HTML parser are (ADR-001,
# ADR-021): a different model is a different set of drafts, so a change is a
# deliberate event with its own cache directory and its own score.
MODEL = "claude-opus-5"
EFFORT = "high"
MAX_TOKENS = 64000

SCHEMA_VERSION = 1

# A permission is not a rule (G-3), so the model is never offered MAY.
RULE_MODALITIES = sorted(set(Modality.ALL) - {"MAY"})
RULE_UNITS = sorted(Unit.ALL - {Unit.ARTIFACT})
CLARITY_SUGGESTIONS = ["unambiguous", "ambiguous_resolvable", "ambiguous_deferred",
                       "not_automatable"]
NOT_RULE_REASONS = ["section", "permission", "restatement", "advice", "duplicate",
                    "not_text", "description"]
LABELS = {"example", "examples", "correct", "incorrect", "write this", "not this"}


# ---------------------------------------------------------------------------
# The page, as the model sees it
# ---------------------------------------------------------------------------

@dataclass
class Page:
    path: str
    sha256: str
    blocks: list[Block]
    seeds: dict[str, str]          # heading block id -> candidate uid

    @property
    def title(self) -> str:
        return next((b.plain for b in self.blocks if b.kind == "heading" and b.level == 1),
                    self.path)


def load_page(rel: str) -> Page:
    """The page and the heading walk's candidates on it.

    The candidates come from ``extract_candidates``, a pure function of the page,
    and not from the ledger. The ledger changes every time a reviewer decides
    something, and a draft's input hash must not, or reviewing a page would make
    its own draft stale.
    """
    from derek.extract.candidates import extract_candidates

    src = PAGES / rel
    page = NormalisedPage(rel, src.read_text(encoding="utf-8", errors="replace"))
    blocks = parse_blocks(rel, page.text)
    by_line = {b.line: b.id for b in blocks if b.kind == "heading"}
    seeds = {by_line[c.line_start]: c.uid for c in extract_candidates(rel, page.text)
             if c.line_start in by_line}
    return Page(rel, page.sha256, blocks, seeds)


def render_page(page: Page) -> str:
    """One line per block: ``[id] KIND text``. Plain text only: no Markdown (D-13)."""
    lines = [f"PAGE: {page.path}", f"TITLE: {page.title}", ""]
    for b in page.blocks:
        if b.kind == "heading":
            tag = f"H{b.level}"
            if b.id in page.seeds:
                tag += " ⟨candidate⟩"
            elif b.plain.strip().lower() in LABELS:
                tag += " ⟨label⟩"
        elif b.kind == "li":
            tag = "LI" + ("." * b.list_depth) + (" ordered" if b.ordered else "")
        elif b.kind == "cell":
            tag = f"CELL {b.cell[0]},{b.cell[1]}" if b.cell else "CELL"
        else:
            tag = {"para": "P"}.get(b.kind, b.kind.upper())
        lines.append(f"[{b.id}] {tag}  {b.plain}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

def _options(bucket: str, keys: list[str] | None = None) -> str:
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))["buckets"][bucket]
    out = []
    for key, opt in g["options"].items():
        if keys is not None and key not in keys:
            continue
        if opt.get("system_only"):
            continue
        out.append(f"  - `{key}`: {opt.get('means', '')}")
    return "\n".join(out)


def system_prompt() -> str:
    policy = POLICY.read_text(encoding="utf-8")
    return f"""\
You are drafting the rule inventory for one page of the Australian Government \
Style Manual. The draft is for Derek, a checker that flags text breaking a Style \
Manual rule. A human reviewer will accept, correct or discard each item you \
return in an annotation tool, then mark the page as fully reviewed. A faithful \
draft saves them hours. A plausible-looking wrong one costs them more than no \
draft at all, because it is harder to spot than a gap.

The page arrives as numbered blocks, one per line: `[block_id] KIND  text`. KIND \
is H1–H6 for headings, P for a paragraph, LI for a list item (dots show nesting), \
QUOTE, or CELL row,col. A heading marked ⟨candidate⟩ is one an earlier heuristic \
proposed as a rule. ⟨label⟩ marks the manual's example labels (Example, Correct, \
Incorrect, Write this, Not this). Markdown cannot close a heading, so prose that \
follows an example block still sits under that label heading. It is ordinary \
prose, and it often states the next rule.

## You only point

Every rule, example part, and exclusion you return is a `block_id` plus a `quote` \
copied character for character from that block's text. A quote that cannot be \
found in its block is discarded automatically, so copy curly quotes, dashes and \
spacing exactly as they appear. Never paraphrase inside a quote, and never join \
text from two blocks into one quote.

A rule's quote is the shortest span that states the rule, usually one heading or \
one sentence. When a heading is the right place but the wrong words (a label, or \
a description of English rather than an instruction), quote the body sentence \
that states the rule instead.

## What counts as one rule

This is the project's policy, and the reviewer checks your draft against it:

<policy>
{policy}
</policy>

## Fields for each rule

- `violation_condition`: describe the text a checker should flag, meaning what \
is present or missing that makes the text wrong. Never restate the instruction. \
Not "Use commas in numbers with 4 or more digits" but "a number of 4 or more \
digits written without a thousands comma, other than a year or postcode or the \
digits after a decimal point".
- `direction`: `presence` if the mistake is something that is in the text, \
`absence` if something required is missing.
- `modality`: `MUST`, `MUST_NOT`, `SHOULD`, `SHOULD_NOT`, or `PREFER` (one option \
preferred over a named alternative). A bare instruction is `SHOULD` unless the \
text makes it a hard requirement. There is no permission option: a permission \
is not a rule (G-3), so record it under `when` on the rule it relaxes.
- `unit`: the smallest piece of writing you must read to decide whether the rule \
is broken:
{_options("unit", RULE_UNITS)}
- `applies_to`: which kinds of documents the rule is for. Use `any` unless the \
page limits it:
{_options("applies_to")}
- `detection_hint`: how a checker could find it:
{_options("detection_hint")}
- `clarity_suggestion`: could someone build a checker from it without asking a \
question? A threshold you had to choose (e.g. "very short" read as "4 words or \
fewer") makes it `ambiguous_resolvable`, with the threshold stated in \
`specification` (E-4).
- `specification`: your restatement, only when the manual's wording leaves \
room. Otherwise empty.
- `when`: short plain sentences for the conditions that limit when the rule \
applies, and its exceptions (G-2, G-3).
- `examples`: the manual's own examples of this rule, each with one or more \
verbatim `parts`. Follow E-1: text under Correct or Write this is `compliant`, \
text under Incorrect or Not this is `violating`, and text under Example shows \
correct usage unless the page says it is wrong. A contrast pair of two correct \
sentences with different meanings is two compliant examples, not a violation. \
A list's lead-in line and its items are one example with several parts (E-3). \
Quote the example sentence without a trailing bracketed gloss such as \
"[Adverb]". Never use the text that states a rule as that rule's example (D-5).
- `covers`: verbatim quotes of other headings or sentences this rule absorbs \
(its restatements, conditions and exceptions), so the reviewer can see what \
you consolidated.
- `why`: one line naming the policy points that decided this rule's extent.

## What is not a rule

In `not_rules`, list every heading marked ⟨candidate⟩ that you do not return as \
a rule, and every sentence that reads like an instruction but is not one. Give \
each a reason: `section` (G-1), `permission` (G-3), `restatement` (G-4), \
`advice` to the writer (G-5), `duplicate` of a rule stated elsewhere (G-6), \
`not_text` (about images, video, files or page settings rather than words), or \
`description` (describes English and instructs nothing).

Be complete. The reviewer marks the page as fully reviewed after working \
through your draft, so a rule you miss is likely to stay missed. Equally, \
do not split one rule into several (G-1, G-2) or promote explanation into rules.
"""


def user_message(page: Page) -> str:
    return render_page(page)


def _pointer() -> dict:
    return {
        "type": "object",
        "properties": {"block_id": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["block_id", "quote"],
        "additionalProperties": False,
    }


def _applies_to_keys() -> list[str]:
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))["buckets"]["applies_to"]
    return [k for k, o in g["options"].items() if not o.get("system_only")]


def output_schema() -> dict:
    """The JSON the model must return (structured outputs)."""
    example = {
        "type": "object",
        "properties": {
            "polarity": {"type": "string", "enum": ["compliant", "violating"]},
            "parts": {"type": "array", "items": _pointer()},
            "note": {"type": "string"},
        },
        "required": ["polarity", "parts", "note"],
        "additionalProperties": False,
    }
    rule = {
        "type": "object",
        "properties": {
            "block_id": {"type": "string"},
            "quote": {"type": "string"},
            "violation_condition": {"type": "string"},
            "direction": {"type": "string", "enum": sorted(Direction.ALL)},
            "modality": {"type": "string", "enum": RULE_MODALITIES},
            "unit": {"type": "string", "enum": RULE_UNITS},
            "applies_to": {"type": "array", "items": {"type": "string", "enum": _applies_to_keys()}},
            "detection_hint": {"type": "string", "enum": sorted(DetectionHint.ALL)},
            "clarity_suggestion": {"type": "string", "enum": CLARITY_SUGGESTIONS},
            "specification": {"type": "string"},
            "when": {"type": "array", "items": {"type": "string"}},
            "examples": {"type": "array", "items": example},
            "covers": {"type": "array", "items": _pointer()},
            "why": {"type": "string"},
        },
        "required": ["block_id", "quote", "violation_condition", "direction", "modality",
                     "unit", "applies_to", "detection_hint", "clarity_suggestion",
                     "specification", "when", "examples", "covers", "why"],
        "additionalProperties": False,
    }
    not_rule = {
        "type": "object",
        "properties": {
            "block_id": {"type": "string"},
            "quote": {"type": "string"},
            "reason": {"type": "string", "enum": NOT_RULE_REASONS},
            "note": {"type": "string"},
        },
        "required": ["block_id", "quote", "reason", "note"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "rules": {"type": "array", "items": rule},
            "not_rules": {"type": "array", "items": not_rule},
        },
        "required": ["rules", "not_rules"],
        "additionalProperties": False,
    }


def prompt_sha256() -> str:
    """Hash of everything that shapes the model's answer except the page itself."""
    body = json.dumps({"system": system_prompt(), "schema": output_schema()},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def input_sha256(page: Page) -> str:
    body = json.dumps({
        "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_sha256(),
        "model": MODEL, "effort": EFFORT, "user": user_message(page),
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Pointing back at the manual — the check that makes a draft safe to show
# ---------------------------------------------------------------------------

# Typographic variants a model routinely normalises when it copies text. Matching
# through them still lands on the manual's own characters, because the offsets
# are found in a folded copy of the block and the quote is re-read from the
# original.
_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                       "‐": "-", " ": " ", " ": " "})


def locate(block: Block, quote: str) -> tuple[int, int] | None:
    """Offsets of ``quote`` in ``block.plain``, or None. Never guesses between two."""
    q = quote.strip()
    if not q:
        return None
    for hay, needle in ((block.plain, q), (block.plain.translate(_FOLD), q.translate(_FOLD))):
        at = hay.find(needle)
        if at != -1:
            if hay.find(needle, at + 1) != -1:
                return None          # appears twice: ambiguous, so refused
            return at, at + len(needle)
    return None


def anchor(block: Block, start: int, end: int) -> dict:
    return {
        "block_id": block.id, "start": start, "end": end,
        "quote": block.plain[start:end],
        "prefix": block.plain[max(0, start - 32):start],
        "suffix": block.plain[end:end + 32],
    }


@dataclass
class Resolved:
    rules: list[dict] = field(default_factory=list)
    not_rules: list[dict] = field(default_factory=list)
    refused: list[dict] = field(default_factory=list)


def resolve(page: Page, raw: dict) -> Resolved:
    """Turn the model's pointers into anchors in the manual's text, or refuse them."""
    by_id = {b.id: b for b in page.blocks}
    out = Resolved()

    def point(p: dict, what: str):
        block = by_id.get(p.get("block_id", ""))
        if block is None:
            out.refused.append({"what": what, "quote": p.get("quote", "")[:200],
                                "why": f"no block {p.get('block_id')!r} on this page"})
            return None
        hit = locate(block, p.get("quote", ""))
        if hit is None:
            out.refused.append({"what": what, "quote": p.get("quote", "")[:200],
                                "why": f"not found exactly once in block {block.id}"})
            return None
        return block, hit

    seen: set[tuple[str, int, int]] = set()
    for n, r in enumerate(raw.get("rules", [])):
        got = point(r, "rule")
        if got is None:
            continue
        block, (start, end) = got
        if block.kind == "heading" and block.level <= 1:
            out.refused.append({"what": "rule", "quote": r.get("quote", ""),
                                "why": "the page title is not a rule"})
            continue
        key = (block.id, start, end)
        if key in seen:
            out.refused.append({"what": "rule", "quote": r.get("quote", ""),
                                "why": "the same span was returned twice"})
            continue
        seen.add(key)

        examples = []
        for ex in r.get("examples", []):
            parts = []
            for p in ex.get("parts", []):
                hit = point(p, "example")
                if hit is None:
                    continue
                eb, (a, z) = hit
                if eb.id == block.id and a < end and start < z:
                    # D-5: never an example drawn from the sentence that states the rule.
                    out.refused.append({"what": "example", "quote": p.get("quote", ""),
                                        "why": "overlaps the rule it illustrates (D-5)"})
                    continue
                parts.append(anchor(eb, a, z))
            if parts and ex.get("polarity") in ("compliant", "violating"):
                examples.append({"kind": ex["polarity"], "parts": parts,
                                 "note": ex.get("note", "")})

        covers = []
        for p in r.get("covers", []):
            hit = point(p, "covers")
            if hit is not None:
                cb, (a, z) = hit
                covers.append(anchor(cb, a, z))

        tags = {
            "unit": r.get("unit") if r.get("unit") in Unit.ALL else "",
            "direction": r.get("direction") if r.get("direction") in Direction.ALL else "",
            "modality": r.get("modality") if r.get("modality") in Modality.ALL else "",
            "applies_to": [a for a in r.get("applies_to", []) if a in _applies_to_keys()],
            "detection_hint": (r.get("detection_hint")
                               if r.get("detection_hint") in DetectionHint.ALL else ""),
            "violation_condition": (r.get("violation_condition") or "").strip(),
            "specification": (r.get("specification") or "").strip(),
        }
        out.rules.append({
            "n": n,
            "anchor": anchor(block, start, end),
            "seed_uid": page.seeds.get(block.id, "")
                        if block.kind == "heading" and (start, end) == (0, len(block.plain)) else "",
            "tags": tags,
            "clarity_suggestion": r.get("clarity_suggestion", ""),
            "when": [w.strip() for w in r.get("when", []) if w.strip()],
            "examples": examples,
            "covers": covers,
            "why": r.get("why", ""),
        })

    for x in raw.get("not_rules", []):
        got = point(x, "not_rule")
        if got is None:
            continue
        block, (a, z) = got
        out.not_rules.append({
            "anchor": anchor(block, a, z),
            "seed_uid": page.seeds.get(block.id, "") if block.kind == "heading" else "",
            "reason": x.get("reason", ""), "note": x.get("note", ""),
        })
    return out


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------

# Paths are read from the module at call time, not bound as defaults, so a test
# can point the whole cache at a temporary directory.
def draft_path(rel: str, *, prompt_version: str = PROMPT_VERSION, model: str = MODEL,
               root: Path | None = None) -> Path:
    base = (root or DRAFTS) / prompt_version / model
    return base / (rel[:-3] + ".json" if rel.endswith(".md") else rel + ".json")


def record(page: Page, raw: dict, resolved: Resolved, *, served_model: str,
           usage: dict, stop_reason: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "page_path": page.path,
        "page_sha256": page.sha256,
        "render_version": RENDER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": prompt_sha256(),
        "input_sha256": input_sha256(page),
        "model": MODEL,
        "served_model": served_model,
        "effort": EFFORT,
        "stop_reason": stop_reason,
        "usage": usage,
        "rules": resolved.rules,
        "not_rules": resolved.not_rules,
        "refused": resolved.refused,
        "raw": raw,
    }


def write_record(rec: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def load_drafts(*, prompt_version: str = PROMPT_VERSION, model: str = MODEL,
                root: Path | None = None) -> dict[str, dict]:
    """Every cached draft for one (prompt version, model), by page path."""
    base = (root or DRAFTS) / prompt_version / model
    out: dict[str, dict] = {}
    if not base.exists():
        return out
    for p in sorted(base.rglob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[rec["page_path"]] = rec
    return out


# ---------------------------------------------------------------------------
# The blind set
# ---------------------------------------------------------------------------

def load_blind(path: Path | None = None) -> dict[str, str]:
    """Pages whose drafts are never shown to the reviewer: page path -> reason.

    A draft shown on a page shapes what the human marks there, so a page
    annotated with a draft in view can measure how often drafts are accepted but
    never how good they are. Only a page marked without one can do that.
    """
    path = path or BLIND
    if not path.exists():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")).get("pages", {}))


# One page in sixteen. The trade: every blind page is annotated at the unassisted
# pace (13-32 words a minute on the first three), so a large holdout costs the
# reviewer the time drafts exist to save; too small and the measurement is noise.
# Eight pages at roughly ten rules each is ~80 blind rules, enough to tell a
# drafter that finds 90% of rules from one that finds 70%.
HOLDOUT_ONE_IN = 16


def holdout(rel: str) -> bool:
    """The standing holdout, by a hash that is stable across processes."""
    return hashlib.blake2s(rel.encode("utf-8")).digest()[0] % HOLDOUT_ONE_IN == 0


def eligible_pages() -> list[str]:
    eligibility = load_eligibility(ELIGIBILITY)
    return sorted(str(p.relative_to(PAGES)) for p in PAGES.rglob("*.md")
                  if eligibility.decide(str(p.relative_to(PAGES)))[0])
