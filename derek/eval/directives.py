"""Sentences that read like instructions: a baseline, never an extractor.

A deliberately dumb sentence-level pattern: a sentence that opens with a verb
from ``imperative_verbs.txt``, with *Don't / Always / Never / Avoid*, with
*If / When …,* followed by one of those, or that carries *should / must / need
to*. Measured against the first three annotated pages, it reached 11 of the 13
rules a human marked in body prose, both misses being permissions, and it
proposed about five sentences for every hit, most of them restatements of a
heading rule.

That ratio is why it lives in ``derek/eval/`` and not in ``derek/extract/``. It
is a *yardstick*: the golden-set lint uses it to point at directive sentences no
span accounts for (the human's possible misses), and ``derek.eval.draft_score``
reports it beside a model's drafts, so "the model found 12 of 13" can be read
against "a regex found 11". It decides nothing, and it is not a candidate
source. The prose pass ``derivation.method: imperative_sentence`` names is still
unbuilt, and this does not build it.

One structural fact it had to learn: prose after an *Example* / *Correct* /
*Incorrect* block sits **inside** that example heading in the parsed tree, since
Markdown has no way to close a heading. All three reflexive-pronoun rules on
``pronouns.md`` sit under ``### Incorrect``. Anything that skips example
sections, including a first version of this, cannot see them.

Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from derek.extract.blocks import Block

VERBS_PATH = Path(__file__).resolve().parents[1] / "extract" / "data" / "imperative_verbs.txt"

_APOS = "[’']"
_NEG = re.compile(rf"^(don{_APOS}t|do not|never|avoid|always|only)\b", re.I)
_COND = re.compile(r"^(if|when|where|unless|for|in|after|before|within)\b[^,]{2,120},\s*(\w+)", re.I)
_MODAL = re.compile(
    rf"\b(should|must|need to|needs to|don{_APOS}t need|do not need|does not form part|is not part)\b",
    re.I)
_LEAD = re.compile(r"^(generally|usually|also|then),?\s+", re.I)
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+[’']?|$)")


def _verbs() -> frozenset[str]:
    return frozenset(
        line.strip() for line in VERBS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#"))


VERBS = _verbs()


@dataclass(frozen=True)
class Directive:
    block_id: str
    start: int
    end: int
    text: str
    cue: str          # imperative | negative | conditional | modal


def classify(sentence: str) -> str | None:
    """The cue that makes a sentence read as an instruction, or None."""
    s = _LEAD.sub("", sentence.strip())
    words = re.findall(r"[A-Za-z’']+", s)
    if not words:
        return None
    if _NEG.match(s):
        return "negative"
    if words[0].lower() in VERBS:
        return "imperative"
    m = _COND.match(s)
    if m and m.group(2).lower() in VERBS | {"don’t", "don't", "do", "never", "always"}:
        return "conditional"
    if _MODAL.search(s):
        return "modal"
    return None


def sentences(text: str) -> list[tuple[int, int, str]]:
    """(start, end, text) for each sentence, offsets into ``text``."""
    out = []
    for m in _SENTENCE.finditer(text):
        raw = m.group(0)
        lead = len(raw) - len(raw.lstrip())
        body = raw.strip()
        if body:
            start = m.start() + lead
            out.append((start, start + len(body), body))
    return out


def directive_sentences(blocks: list[Block]) -> list[Directive]:
    """Every sentence on a page that reads as an instruction, in page order.

    Headings are skipped because the heading walk already classifies them, and
    so are table cells, which in this corpus are data rather than prose.
    """
    out = []
    for b in blocks:
        if b.kind in ("heading", "cell"):
            continue
        for start, end, text in sentences(b.plain):
            cue = classify(text)
            if cue:
                out.append(Directive(b.id, start, end, text, cue))
    return out
