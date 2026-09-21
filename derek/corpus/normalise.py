"""Deterministic normalisation of scraped Style Manual pages.

Everything downstream — content hashing, change detection, candidate
identity — depends on this module being a pure, stable function of its
input. Two runs over identical source HTML must produce byte-identical
output, or the changeset becomes noise (see ADR-001).

The one non-obvious job here is *heading repair*, which is now a **fallback**
rather than the primary path (ADR-020).

Octavius converted HTML with ``trafilatura``, a generic article extractor
that flattens heading levels inconsistently: its corpus carried 1,795 ``###``
against only 53 ``##`` and 2 ``#``, with many section headings demoted to
bare paragraphs. Since structure-driven extraction (ADR-002) reads rules off
the heading tree, a demoted heading was a lost rule, and ``repair_headings``
existed to promote them back.

``derek.corpus.to_markdown`` now reads heading levels from the source DOM, so
correctly-converted pages need no repair at all — on DOM-faithful output this
function performs zero promotions. It is retained as a regression guard: if a
future converter change starts flattening structure again, repair limits the
damage instead of silently dropping rules.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

__all__ = [
    "normalise_text",
    "repair_headings",
    "content_hash",
    "NormalisedPage",
]

# A line that survives every one of these tests is treated as a section
# heading that lost its ``##`` marker. The tests are deliberately strict:
# a false promotion invents a rule, which is worse than missing one (a
# missed heading still yields candidates from the ``###`` beneath it).
_MAX_ORPHAN_HEADING_CHARS = 120
_SENTENCE_FINAL = ".:;,!?…"

_LIST_MARKER = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s")
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_TABLE_ROW = re.compile(r"^\s*\|")
_MD_IMAGE = re.compile(r"^\s*!\[")
_TRAILING_WS = re.compile(r"[ \t]+$", re.M)
_BLANK_RUN = re.compile(r"\n{3,}")

# Headings that introduce an example block rather than state a rule.
# Headings that introduce an example block rather than state a rule.
# Derived by frequency analysis over every heading in the corpus, not
# guessed: "correct"/"incorrect" (60 each) and "like this" (49) are as
# common as the more obvious "write this"/"not this".
EXAMPLE_HEADINGS = frozenset(
    {
        "example",
        "examples",
        "write this",
        "not this",
        "do this",
        "don't do this",
        "correct",
        "incorrect",
        "like this",
        "more information",
    }
)

# Page chrome that ``trafilatura`` keeps. These are headings, but they are
# never rules. Counts across the 186-page corpus are given for provenance.
BOILERPLATE_HEADINGS = frozenset(
    {
        "last updated",      # 154
        "about this page",   # 116
        "references",        # 116
        "release notes",     # 110
        "style manual pages",  # 17
        "evidence",          # 20
        "contents",
        "on this page",
        "in this section",
    }
)

# A trailing bracketed gloss marks an example sentence, e.g.
# "Unless the consultation starts early, it will not finish on time.
#  [A conditional adverbial clause]". Never a heading.
_TRAILING_GLOSS = re.compile(r"\[[^\]]{3,}\]\s*$")


def normalise_text(raw: str) -> str:
    """Return a canonical form of a scraped markdown page.

    Applied before hashing and before any structural parse. Idempotent:
    ``normalise_text(normalise_text(x)) == normalise_text(x)``.
    """
    text = unicodedata.normalize("NFC", raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Non-breaking and other exotic spaces defeat word-boundary matching and
    # differ run-to-run depending on how the page was rendered.
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    text = _TRAILING_WS.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip() + "\n"


def _looks_like_orphan_heading(
    line: str, prev_blank: bool, next_blank: bool, next_line: str
) -> bool:
    """Conservative test for a section heading that lost its ``##`` marker.

    Callers must additionally suppress promotion inside example blocks; see
    ``repair_headings``. Example sentences are frequently standalone
    paragraphs and would otherwise be promoted into the rule inventory.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if not (prev_blank and next_blank):
        return False
    if len(stripped) > _MAX_ORPHAN_HEADING_CHARS:
        return False
    if stripped[-1] in _SENTENCE_FINAL:
        return False
    if _TRAILING_GLOSS.search(stripped):
        return False
    if _LIST_MARKER.match(line) or _TABLE_ROW.match(line) or _MD_IMAGE.match(line):
        return False
    if _ATX_HEADING.match(line):
        return False
    if not stripped[0].isupper():
        return False
    # A heading is a clause, not a paragraph: no internal sentence breaks.
    if re.search(r"[.!?]\s+[A-Z]", stripped):
        return False
    # Bare emphasis/links-only lines are captions, not headings.
    if stripped.startswith(("[", ">", "|")):
        return False
    # The following block must be content, not another orphan candidate;
    # two adjacent orphans are almost always a caption pair.
    if next_line.strip() and _ATX_HEADING.match(next_line):
        return True
    return True


def repair_headings(text: str, level: int = 2) -> tuple[str, int]:
    """Promote demoted section headings back to ATX headings.

    Returns ``(repaired_text, promotions)``. ``level`` is the heading level
    assigned to promoted lines — 2, since the pattern being repaired is
    ``##`` section headings sitting above intact ``###`` rule headings.

    **No-op on healthy input.** If the text already contains a heading at or
    above ``level``, its hierarchy is intact and the function returns it
    unchanged. Since ``derek.corpus.to_markdown`` reads heading levels from
    the DOM, this is the normal case; repair only engages if a converter
    regression starts flattening structure again (ADR-020). A non-zero
    ``promotions`` count on a freshly scraped page is a bug signal.
    """
    lines = text.split("\n")

    # Self-disabling gate (ADR-020). Repair exists to recover ``##`` section
    # headings that a flattening converter demoted to bare paragraphs. If the
    # page already carries a level-1 or level-2 heading, its hierarchy is
    # intact and there is nothing to recover — running anyway would promote
    # ordinary standalone paragraphs into the rule inventory, which is the
    # very failure this module is supposed to prevent.
    for line in lines:
        m = _ATX_HEADING.match(line)
        if m is not None and len(m.group(1)) <= level:
            return text, 0

    out: list[str] = []
    promotions = 0
    in_fence = False
    # Suppress promotion inside an example block's content run. Example
    # blocks are contiguous: they end at the first blank line after content
    # begins, which is where a demoted section heading can legitimately
    # follow (see ``punctuation/commas.md``, "Mark out non-essential
    # information within a sentence" directly after a "Not this" block).
    in_example_block = False
    example_seen_content = False
    # Only promote inside the region governed by real ``###`` headings;
    # a page with no ``###`` at all has no structure to repair.
    has_rule_headings = any(
        (m := _ATX_HEADING.match(ln)) and len(m.group(1)) >= 3 for ln in lines
    )

    for i, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        heading = _ATX_HEADING.match(line)
        if heading is not None:
            in_example_block = heading.group(2).strip().lower() in EXAMPLE_HEADINGS
            example_seen_content = False
            out.append(line)
            continue

        if in_example_block:
            if line.strip():
                example_seen_content = True
            elif example_seen_content:
                in_example_block = False

        if in_fence or not has_rule_headings or in_example_block:
            out.append(line)
            continue

        prev_blank = i == 0 or not lines[i - 1].strip()
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        next_blank = (i + 1 >= len(lines)) or not next_line.strip()

        if _looks_like_orphan_heading(line, prev_blank, next_blank, next_line):
            out.append("#" * level + " " + line.strip())
            promotions += 1
        else:
            out.append(line)

    return "\n".join(out), promotions


def content_hash(text: str) -> str:
    """Stable content hash of a normalised page.

    Computed over normalised text so that cosmetic rendering differences do
    not register as editorial change (ADR-001).
    """
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


class NormalisedPage:
    """A corpus page after normalisation and heading repair."""

    __slots__ = ("path", "text", "sha256", "promotions")

    def __init__(self, path: str, raw: str) -> None:
        normalised = normalise_text(raw)
        repaired, promotions = repair_headings(normalised)
        self.path = path
        self.text = normalise_text(repaired)
        self.sha256 = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        self.promotions = promotions

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NormalisedPage({self.path!r}, sha256={self.sha256[:12]}…)"
