"""The format-independent document detectors run on (ADR-012).

``text`` is plain text and the only thing a detector sees: no Markdown, no
HTML, no Word runs (D-13, ADR-019). ``blocks`` are character spans into it, so
a sentence-scoped rule cannot match across a paragraph break and a finding can
be mapped back to where it came from.

Two adapters for now: plain text, and a Style Manual page, which is how the
dogfood gate reads the manual. Every adapter must keep
``text[b.start:b.end] == b.text`` for every block, and the tests assert it.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

from derek.extract.blocks import Block, parse_blocks

__all__ = ["DocBlock", "Document", "example_block_ids", "NEGATIVE_LABELS",
           "POSITIVE_LABELS", "LABELS"]

POSITIVE_LABELS = frozenset({"correct", "write this"})
NEGATIVE_LABELS = frozenset({"incorrect", "not this", "don't do this", "don’t do this"})
LABELS = POSITIVE_LABELS | NEGATIVE_LABELS | frozenset({"example", "examples"})

_SEP = "\n\n"


@dataclass(frozen=True)
class DocBlock:
    id: str
    kind: str
    start: int
    end: int
    text: str
    heading_path: tuple[str, ...] = ()
    # False for text a checker must not judge: the manual's own deliberately
    # wrong examples under "Not this" and "Incorrect" (ADR-011).
    lintable: bool = True


@dataclass(frozen=True)
class Document:
    text: str
    blocks: tuple[DocBlock, ...]

    @classmethod
    def from_text(cls, text: str) -> "Document":
        """Plain text. Paragraphs are blocks, split on blank lines."""
        blocks, at = [], 0
        for i, chunk in enumerate(text.split(_SEP)):
            if chunk.strip():
                blocks.append(DocBlock(f"p{i}", "para", at, at + len(chunk), chunk))
            at += len(chunk) + len(_SEP)
        return cls(text, tuple(blocks))

    @classmethod
    def from_blocks(cls, blocks: list[Block], *, exclude: set[str] = frozenset()) -> "Document":
        parts, out, at = [], [], 0
        for b in blocks:
            if parts:
                at += len(_SEP)
            parts.append(b.plain)
            out.append(DocBlock(b.id, b.kind, at, at + len(b.plain), b.plain,
                                tuple(b.heading_path), b.id not in exclude))
            at += len(b.plain)
        return cls(_SEP.join(parts), tuple(out))

    @classmethod
    def from_page(cls, rel: str, normalised_text: str) -> "Document":
        """A Style Manual page, with its deliberately wrong examples not lintable."""
        blocks = parse_blocks(rel, normalised_text)
        return cls.from_blocks(blocks, exclude=example_block_ids(blocks, NEGATIVE_LABELS))

    @property
    def words(self) -> int:
        return sum(len(b.text.split()) for b in self.blocks if b.lintable)


def example_block_ids(blocks: list[Block], labels: frozenset[str] = LABELS) -> set[str]:
    """Blocks the manual presents as examples under one of ``labels``.

    A label heading cannot be closed in Markdown, so the prose after an example
    still sits under its label in the tree. All three reflexive-pronoun rules on
    pronouns.md sit under ``### Incorrect``. An example is therefore the list
    items directly beneath the label, or failing those its first paragraph, and
    nothing after. Treating the whole section as the example is how 212 lines of
    ordinary prose were harvested as gold examples (docs/05-open-questions.md,
    Q9).
    """
    out: set[str] = set()
    current: tuple[str, ...] | None = None
    seen_li = seen_para = False
    for b in blocks:
        if b.kind == "heading":
            current = tuple(b.heading_path) if b.plain.strip().lower() in labels else None
            seen_li = seen_para = False
            continue
        if current is None or tuple(b.heading_path) != current:
            continue
        if b.kind == "li" and not seen_para:
            out.add(b.id)
            seen_li = True
        elif b.kind in ("para", "quote") and not seen_li and not seen_para:
            out.add(b.id)
            seen_para = True
        else:
            current = None
    return out
