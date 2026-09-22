"""Project a corpus page into addressable blocks of plain text (ADR-023).

    python -m derek.extract.blocks --lock     # regenerate data/blocks.lock.json
    python -m derek.extract.blocks --check    # CI: fail if the lock is stale

The golden set records rules as *spans of text a human selected*, and a span
needs an address that survives the round trip from a browser selection, through
a JSONL export, back into Python. That is harder than it looks: the corpus is
Markdown, the reviewer reads rendered text, and ``[label](url)`` means the
rendered characters are not the source characters. Offsets into the ``.md``
cannot be mapped to a DOM selection.

So this module defines one projection, in Python, and both sides use it:

* ``plain`` is the markup-free text the reviewer sees. **Span offsets index
  this**, scoped to a single block.
* ``marks`` are the inline spans (link, emphasis, code) as offsets into
  ``plain``, so the browser can rebuild the formatting without ever changing
  the character count.

Deliberately **no HTML is generated here.** The annotator builds its DOM by
slicing ``plain`` at mark boundaries, which makes ``element.textContent ==
block.plain`` true by construction rather than by assertion — and sidesteps an
escaping trap that matters in this corpus specifically, where the manual quotes
HTML as content (``<figcaption>``, ``&nbsp;``) and it must render literally.

Heading structure is **not re-derived**. ``segment.parse_page`` already owns it,
fence handling and all, so this walks that tree. Two parsers for one question is
how they come to disagree.

Everything is a pure function of the input text: no model, no clock, no
randomness, stdlib only (D-7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from derek.extract.segment import Node, iter_nodes, parse_page

__all__ = [
    "RENDER_VERSION", "Mark", "Block", "parse_blocks", "block_id",
    "page_digest", "build_lock", "load_lock", "LOCK_PATH",
]

# Bumped deliberately when this module's output changes. A bump invalidates
# every recorded span offset, so it is followed by a rebase pass — see ADR-024.
RENDER_VERSION = "1.0.0"

REPO = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).resolve().parent / "data" / "blocks.lock.json"
PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"

BLOCK_KINDS = frozenset({"heading", "para", "li", "cell", "quote"})
MARK_KINDS = frozenset({"em", "strong", "code", "link"})

_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


@dataclass(frozen=True)
class Mark:
    """An inline run, as offsets into the block's ``plain`` text."""

    start: int
    end: int
    kind: str                 # em | strong | code | link
    href: str = ""

    def to_dict(self) -> dict:
        out = {"start": self.start, "end": self.end, "kind": self.kind}
        if self.href:
            out["href"] = self.href
        return out


@dataclass(frozen=True)
class Block:
    """One addressable run of text on a page.

    ``id`` is content-addressed over (page, heading path, text, occurrence), so
    editing one paragraph changes that paragraph's address and nothing else.
    Page-global character offsets would have made an edit to paragraph 2
    invalidate every span in paragraph 40.
    """

    id: str
    kind: str
    level: int                # the heading's level, or its enclosing heading's
    heading_path: tuple[str, ...]
    plain: str
    marks: tuple[Mark, ...]
    line: int                 # 0-based source line
    list_depth: int = 0
    cell: tuple[int, int] | None = None

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "kind": self.kind,
            "level": self.level,
            "heading_path": list(self.heading_path),
            "plain": self.plain,
            "line": self.line,
        }
        if self.marks:
            out["marks"] = [m.to_dict() for m in self.marks]
        if self.list_depth:
            out["list_depth"] = self.list_depth
        if self.cell is not None:
            out["cell"] = list(self.cell)
        return out


def block_id(page_path: str, heading_path: tuple[str, ...], plain: str,
             occurrence: int = 0) -> str:
    """Stable 12-hex address for a block.

    ``occurrence`` disambiguates two blocks with identical text under the same
    heading. Exactly one such pair exists in the eligible corpus, but a page
    that repeats a sentence must not hand two spans the same address.
    """
    h = hashlib.blake2s(digest_size=6)
    h.update(page_path.encode("utf-8"))
    h.update(b"\x00")
    h.update(" > ".join(heading_path).encode("utf-8"))
    h.update(b"\x00")
    h.update(plain.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(occurrence).encode("ascii"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------

def _inline(text: str, base: int = 0) -> tuple[str, list[Mark]]:
    """Split inline markup into plain text plus marks over that text.

    One left-to-right pass, most-specific delimiter first, and an unmatched
    delimiter is literal. The corpus needs exactly five constructs — link,
    ``**strong**``, ``*em*``, code span, and raw HTML that must stay literal —
    so this is a reader for what the Style Manual actually contains, not a
    CommonMark implementation. ``blocks.lock.json`` is what stops that
    distinction drifting unnoticed.
    """
    out: list[str] = []
    marks: list[Mark] = []
    n = 0                      # length of the plain text emitted so far
    i = 0

    def emit(s: str) -> None:
        nonlocal n
        out.append(s)
        n += len(s)

    while i < len(text):
        ch = text[i]

        if ch == "`":
            close = text.find("`", i + 1)
            if close != -1:
                inner = text[i + 1:close]
                marks.append(Mark(base + n, base + n + len(inner), "code"))
                emit(inner)
                i = close + 1
                continue

        if ch == "[" or (ch == "!" and text.startswith("![", i)):
            open_sq = i + 1 if ch == "!" else i
            close_sq = _match_bracket(text, open_sq)
            if close_sq != -1 and text.startswith("(", close_sq + 1):
                close_par = text.find(")", close_sq + 2)
                if close_par != -1:
                    label = text[open_sq + 1:close_sq]
                    href = text[close_sq + 2:close_par]
                    inner_plain, inner_marks = _inline(label, base + n)
                    marks.append(Mark(base + n, base + n + len(inner_plain),
                                      "link", href))
                    marks.extend(inner_marks)
                    emit(inner_plain)
                    i = close_par + 1
                    continue

        if text.startswith("**", i):
            close = text.find("**", i + 2)
            if close != -1 and close > i + 2:
                inner_plain, inner_marks = _inline(text[i + 2:close], base + n)
                marks.append(Mark(base + n, base + n + len(inner_plain), "strong"))
                marks.extend(inner_marks)
                emit(inner_plain)
                i = close + 2
                continue

        if ch == "*":
            close = text.find("*", i + 1)
            if close != -1 and close > i + 1:
                inner_plain, inner_marks = _inline(text[i + 1:close], base + n)
                marks.append(Mark(base + n, base + n + len(inner_plain), "em"))
                marks.extend(inner_marks)
                emit(inner_plain)
                i = close + 1
                continue

        emit(ch)
        i += 1

    marks.sort(key=lambda m: (m.start, -m.end, m.kind))
    return "".join(out), marks


def _match_bracket(text: str, open_at: int) -> int:
    """Index of the ``]`` closing the ``[`` at ``open_at``, or -1.

    Nesting matters: the manual writes ``[A. [Outer [inner](/n/1)]]``-shaped
    editorial glosses, and taking the first ``]`` would cut a link in half.
    """
    depth = 0
    for j in range(open_at, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                return j
    return -1


# ---------------------------------------------------------------------------
# Block structure
# ---------------------------------------------------------------------------

def _body_blocks(lines: list[tuple[int, str]]) -> list[tuple[str, str, int, int, tuple[int, int] | None]]:
    """Split a node's body lines into (kind, raw_text, line, list_depth, cell).

    Table rows become one block per cell, so a span is always inside one run of
    text. The ``| --- |`` alignment row carries no content and is dropped.
    """
    out: list[tuple[str, str, int, int, tuple[int, int] | None]] = []
    para: list[str] = []
    para_line = 0
    quote: list[str] = []
    quote_line = 0
    row = 0

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append(("para", " ".join(para), para_line, 0, None))
            para = []

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            out.append(("quote", " ".join(quote), quote_line, 0, None))
            quote = []

    for lineno, raw in lines:
        stripped = raw.strip()

        if not stripped:
            flush_para()
            flush_quote()
            row = 0
            continue

        if stripped.startswith("|"):
            flush_para()
            flush_quote()
            if _TABLE_RULE.match(raw):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            for col, cell in enumerate(cells):
                if cell:
                    out.append(("cell", cell, lineno, 0, (row, col)))
            row += 1
            continue

        qm = _QUOTE.match(raw)
        if qm:
            flush_para()
            if not quote:
                quote_line = lineno
            quote.append(qm.group(1).strip())
            continue

        bm = _BULLET.match(raw)
        if bm:
            flush_para()
            flush_quote()
            # Two spaces per level is the corpus's convention; nesting never
            # exceeds one level, so this does not need to be cleverer.
            out.append(("li", bm.group(2).strip(), lineno,
                        len(bm.group(1)) // 2, None))
            continue

        flush_para()  # a bullet or table ended; a new paragraph starts here
        if not para:
            para_line = lineno
        para.append(stripped)

    flush_para()
    flush_quote()
    return out


def parse_blocks(page_path: str, text: str) -> list[Block]:
    """Every addressable block on one normalised page, in document order."""
    root = parse_page(text)
    lines = text.split("\n")
    nodes: list[Node] = sorted(iter_nodes(root), key=lambda n: n.line_start)

    # Each node's body runs from the line after its heading to the line before
    # the next heading, whatever level that is. ``Node`` records no line_end;
    # consecutive line_starts give it without changing ``segment``.
    bounds: list[tuple[Node, int, int]] = []
    preamble_end = nodes[0].line_start if nodes else len(lines)
    for idx, node in enumerate(nodes):
        end = nodes[idx + 1].line_start if idx + 1 < len(nodes) else len(lines)
        bounds.append((node, node.line_start + 1, end))

    # (kind, text, level, heading_path, line, list_depth, cell)
    raw: list[tuple[str, str, int, tuple[str, ...], int, int, tuple[int, int] | None]] = []

    # The preamble above the first heading. Zero characters long on every
    # eligible page, but a page that loses its `#` title during conversion
    # would put real prose here, and dropping it silently is how a rule
    # becomes unreachable.
    for kind, body, line, depth, cell in _body_blocks(
        list(enumerate(lines[:preamble_end]))
    ):
        raw.append((kind, body, 0, (), line, depth, cell))

    for node, start, end in bounds:
        raw.append(("heading", node.title, node.level, node.path,
                    node.line_start, 0, None))
        numbered = [(n, lines[n]) for n in range(start, min(end, len(lines)))]
        for kind, body, line, depth, cell in _body_blocks(numbered):
            raw.append((kind, body, node.level, node.path, line, depth, cell))

    blocks: list[Block] = []
    seen: dict[tuple[str, str], int] = {}
    for kind, body, level, heading_path, line, depth, cell in raw:
        plain, marks = _inline(body)
        if not plain.strip():
            continue
        key = (" > ".join(heading_path), plain)
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        blocks.append(Block(
            id=block_id(page_path, heading_path, plain, occurrence),
            kind=kind,
            level=level,
            heading_path=heading_path,
            plain=plain,
            marks=tuple(marks),
            line=line,
            list_depth=depth,
            cell=cell,
        ))
    return blocks


# ---------------------------------------------------------------------------
# The lock — the renderer is pinned, like the tagger and the HTML converter
# ---------------------------------------------------------------------------

def page_digest(blocks: list[Block]) -> str:
    """Digest over everything a span offset depends on."""
    h = hashlib.sha256()
    for b in blocks:
        h.update(f"{b.id}\x1f{b.kind}\x1f{b.level}\x1f{b.line}\x1f{b.plain}".encode("utf-8"))
        for m in b.marks:
            h.update(f"\x1e{m.start},{m.end},{m.kind},{m.href}".encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _eligible_pages() -> dict[str, str]:
    from derek.corpus.eligibility import load_eligibility
    from derek.corpus.normalise import NormalisedPage

    eligibility = load_eligibility(ELIGIBILITY)
    out: dict[str, str] = {}
    for md in sorted(PAGES.rglob("*.md")):
        rel = str(md.relative_to(PAGES))
        if not eligibility.decide(rel)[0]:
            continue
        out[rel] = NormalisedPage(rel, md.read_text(encoding="utf-8", errors="replace")).text
    return out


def build_lock(pages: dict[str, str]) -> dict:
    """The checked-in record of what this renderer produces for the corpus."""
    entries = {}
    for rel in sorted(pages):
        blocks = parse_blocks(rel, pages[rel])
        entries[rel] = {
            "blocks": len(blocks),
            "digest": page_digest(blocks),
        }
    return {
        "_meta": {
            "generated_by": "derek/extract/blocks.py",
            "render_version": RENDER_VERSION,
            "pages": len(entries),
            "note": (
                "Generated, not hand-edited. Span offsets in golden/spans.jsonl "
                "are anchored to this projection; a change here re-anchors every "
                "one of them. Regenerate with "
                "`python -m derek.extract.blocks --lock` and treat the diff as a "
                "deliberate, reviewed event (ADR-023)."
            ),
        },
        "pages": entries,
    }


def load_lock(path: Path = LOCK_PATH) -> dict:
    if not path.exists():
        return {"_meta": {"render_version": ""}, "pages": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(lock: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lock", action="store_true", help="regenerate the lock")
    ap.add_argument("--check", action="store_true",
                    help="fail if the lock is stale")
    args = ap.parse_args(argv)

    fresh = build_lock(_eligible_pages())

    if args.check:
        on_disk = load_lock()
        if on_disk == fresh:
            print(f"OK: blocks.lock.json matches the corpus "
                  f"({fresh['_meta']['pages']} pages, render {RENDER_VERSION}).")
            return 0
        stale = sorted(
            rel for rel in set(on_disk["pages"]) | set(fresh["pages"])
            if on_disk["pages"].get(rel) != fresh["pages"].get(rel)
        )
        print("blocks.lock.json is stale. Differing pages:", file=sys.stderr)
        for rel in stale[:20]:
            print(f"  {rel}", file=sys.stderr)
        if len(stale) > 20:
            print(f"  ... and {len(stale) - 20} more", file=sys.stderr)
        print("\nRegenerate with: python -m derek.extract.blocks --lock",
              file=sys.stderr)
        print("Every recorded span offset is anchored to this projection, so "
              "read the diff before committing it.", file=sys.stderr)
        return 1

    if args.lock:
        _write(fresh, LOCK_PATH)
        print(f"Wrote {LOCK_PATH.relative_to(REPO)} "
              f"({fresh['_meta']['pages']} pages, render {RENDER_VERSION}).")
        return 0

    total = sum(e["blocks"] for e in fresh["pages"].values())
    print(f"{fresh['_meta']['pages']} eligible pages, {total} blocks, "
          f"render {RENDER_VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
