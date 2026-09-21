"""Parse a normalised corpus page into a heading tree.

The Style Manual states its rules *as headings* (ADR-002). This module turns
a repaired markdown page into the tree those headings describe, so the
extractor can read the rule inventory off document structure rather than
asking a model to invent one.

Everything here is a pure function of the input text. No model, no network,
no clock, no randomness — re-running over an unchanged page yields an
identical tree, which is what makes candidate identity stable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["Node", "parse_page", "iter_nodes"]

_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")


@dataclass
class Node:
    """A heading and the content directly beneath it.

    ``path`` is the chain of ancestor heading titles, root first, which is
    what gives a candidate a stable address inside a page even when
    surrounding content is edited.
    """

    level: int
    title: str
    path: tuple[str, ...]
    body: str = ""
    line_start: int = 0
    children: list["Node"] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """Dotted address of this node within its page."""
        return " > ".join(self.path)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Node(h{self.level}, {self.title!r}, {len(self.children)} children)"


def parse_page(text: str) -> Node:
    """Build the heading tree for one normalised page.

    The returned root is a synthetic level-0 node whose ``body`` is the
    page preamble — the lead paragraph that sits above the first heading.
    Style Manual pages routinely lose their ``#`` page title during
    extraction, so the root is deliberately not assumed to exist in the text.
    """
    root = Node(level=0, title="", path=())
    stack: list[Node] = [root]
    buf: list[str] = []
    in_fence = False

    def flush(into: Node) -> None:
        into.body = "\n".join(buf).strip("\n")
        buf.clear()

    for lineno, line in enumerate(text.split("\n")):
        if _FENCE.match(line):
            in_fence = not in_fence
            buf.append(line)
            continue

        m = None if in_fence else _ATX.match(line)
        if m is None:
            buf.append(line)
            continue

        flush(stack[-1])

        level = len(m.group(1))
        title = m.group(2).strip()

        # Close any open nodes at or below this level. Levels in the corpus
        # skip (a repaired ``##`` may be followed directly by ``####``), so
        # this pops by comparison rather than by decrementing.
        while len(stack) > 1 and stack[-1].level >= level:
            stack.pop()

        node = Node(
            level=level,
            title=title,
            path=stack[-1].path + (title,),
            line_start=lineno,
        )
        stack[-1].children.append(node)
        stack.append(node)

    flush(stack[-1])
    return root


def iter_nodes(node: Node):
    """Depth-first walk over every heading node, excluding the synthetic root."""
    for child in node.children:
        yield child
        yield from iter_nodes(child)
