"""HTML → Markdown for Style Manual pages, preserving heading levels.

Replaces ``trafilatura`` in the snapshot path. trafilatura is a generic
article extractor: it recovers prose well but flattens heading levels
inconsistently. On the Octavius corpus that left 1,795 ``###`` against only
53 ``##`` and 2 ``#``, with many section headings demoted to bare
paragraphs — so 71% of extracted rule candidates depended on a repair
heuristic guessing structure back (see docs/00-postmortem-octavius.md
Defect 1, and ADR-020).

The Style Manual's DOM already carries a clean outline:

    h1  page title            ("Commas")
    h2    section / rule      ("Separate introductory words … with a comma")
    h3      rule              ("Place a comma after adverbs …")
    h4        example block   ("Write this" / "Not this" / "Example")
    h5          example label ("Non-essential" / "Essential")

so the right answer is to read it rather than infer it. This module walks
the content subtree in document order and emits the levels verbatim.

Deterministic by construction: no heuristics, no scoring, no randomness.
Same HTML in, byte-identical Markdown out.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

__all__ = ["extract_markdown", "ExtractionError", "CONTENT_SELECTORS", "CHROME_HEADINGS"]


class ExtractionError(RuntimeError):
    """Raised when a page yields no usable content — never silently empty."""


# Tried in order. ``main`` holds the page-title block plus the body article;
# ``article`` alone omits the page title, so it is a fallback only.
CONTENT_SELECTORS = ("main", "article", "#main-content", "body")

# Elements that never carry rule content.
_DROP_TAGS = frozenset({
    "script", "style", "noscript", "iframe", "svg", "button", "form",
    "nav", "footer", "header", "aside", "template", "select", "input",
})

_DROP_SELECTORS = (
    "[role=navigation]", "[role=banner]", "[role=contentinfo]",
    "[role=search]", "[aria-hidden=true]",
    ".noprint", ".visually-hidden", ".sr-only", ".skip-link",
    "#sidebar", ".breadcrumb", ".pager", ".feed-icons",
    ".block-page-title-block ~ .contextual", ".contextual",
)

# Once one of these headings appears, the rest of the page is site chrome:
# release notes, evidence/references, feedback form, footer. Everything from
# the first match onward is discarded.
CHROME_HEADINGS = frozenset({
    "release notes",
    "about this page",
    "help us improve the style manual",
    "help us improve",
    "footer",
    "secondary navigation",
    "style manual pages",
})

_BLOCK = frozenset({
    "p", "div", "section", "ul", "ol", "li", "table", "blockquote",
    "pre", "figure", "figcaption", "dl", "dt", "dd", "hr", "br",
    "h1", "h2", "h3", "h4", "h5", "h6",
})

_WS = re.compile(r"[ \t ]+")
_MD_SPECIAL = re.compile(r"([\\`*_\[\]])")

# A heading wrapped entirely in emphasis — the Style Manual uses
# ``<h2><strong>…</strong></h2>`` on some pages — is presentational, and the
# markers must not leak into the rule statement or its content-addressed UID.
# Emphasis on *part* of a heading is left alone: in
# "use sentence case and italics for '*Re*'" the italics are the rule's
# subject, not decoration.
_WHOLLY_EMPHASISED = re.compile(r"^(\*\*|\*|_)(?P<inner>.+)\1$", re.S)


def _clean(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()


def _heading_key(tag: Tag) -> str:
    return _clean(tag.get_text(" ", strip=True)).lower().rstrip(":")


def _inline(node, base_url: str, *, escape: bool = False) -> str:
    """Render inline content, resolving links and emphasis."""
    if isinstance(node, NavigableString):
        text = _WS.sub(" ", unicodedata.normalize("NFC", str(node)))
        return _MD_SPECIAL.sub(r"\\\1", text) if escape else text
    if not isinstance(node, Tag):
        return ""
    if node.name in _DROP_TAGS:
        return ""

    # Block-level children inside an inline context (the Style Manual nests
    # <h4> and <p> inside <li> to build example cards) must not have their
    # text run together with the next sibling's.
    parts: list[str] = []
    for child in node.children:
        rendered = _inline(child, base_url, escape=escape)
        if not rendered:
            continue
        if (isinstance(child, Tag) and child.name in _BLOCK
                and parts and not parts[-1].endswith((" ", "\n"))):
            parts.append(" ")
        parts.append(rendered)
    inner = "".join(parts)

    if node.name == "br":
        return "\n"
    if node.name == "a":
        href = (node.get("href") or "").strip()
        label = inner.strip()
        if not label:
            return ""
        if not href or href.startswith("#"):
            return label
        return f"[{label}]({urljoin(base_url, href) if base_url else href})"
    if node.name in ("strong", "b"):
        return f"**{inner.strip()}**" if inner.strip() else ""
    if node.name in ("em", "i", "cite"):
        return f"*{inner.strip()}*" if inner.strip() else ""
    if node.name == "code":
        return f"`{inner.strip()}`" if inner.strip() else ""
    if node.name in ("sup", "sub"):
        return inner
    return inner


def _render_table(table: Tag, base_url: str) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if cells:
            rows.append([_clean(_inline(c, base_url)) for c in cells])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, body = rows[0], rows[1:]
    out = ["| " + " | ".join(head) + " |",
           "| " + " | ".join(["---"] * width) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)


def _render_list(lst: Tag, base_url: str, depth: int = 0) -> str:
    ordered = lst.name == "ol"
    lines: list[str] = []
    n = 0
    for li in lst.find_all("li", recursive=False):
        n += 1
        nested: list[str] = []
        for sub in li.find_all(["ul", "ol"], recursive=False):
            nested.append(_render_list(sub, base_url, depth + 1))
            sub.extract()
        text = _clean(_inline(li, base_url))
        marker = f"{n}." if ordered else "-"
        indent = "  " * depth
        if text:
            lines.append(f"{indent}{marker} {text}")
        lines.extend(x for x in nested if x)
    return "\n".join(lines)


def _pick_root(soup: BeautifulSoup) -> Tag:
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None and node.find(re.compile(r"^h[1-6]$")) is not None:
            return node
    body = soup.body
    if body is None:
        raise ExtractionError("document has no <body>")
    return body


def _strip_chrome(root: Tag) -> None:
    """Remove non-content elements, then truncate at the first chrome heading."""
    for tag in root.find_all(lambda t: isinstance(t, Tag) and t.name in _DROP_TAGS):
        tag.decompose()
    for selector in _DROP_SELECTORS:
        for tag in root.select(selector):
            tag.decompose()

    headings = root.find_all(re.compile(r"^h[1-6]$"))
    cut_from = next((h for h in headings if _heading_key(h) in CHROME_HEADINGS), None)
    if cut_from is None:
        return
    # Everything from the chrome heading onward, in document order, goes.
    for node in list(cut_from.find_all_next()):
        if node.parent is not None:
            node.extract()
    cut_from.extract()


def extract_markdown(html: str, base_url: str = "") -> str:
    """Convert a Style Manual page to Markdown with its DOM heading levels.

    Raises ``ExtractionError`` rather than returning empty output, so a
    blocked or broken fetch can never be written to the corpus as a
    legitimately empty page.
    """
    soup = BeautifulSoup(html, "lxml")
    root = _pick_root(soup)
    _strip_chrome(root)

    out: list[str] = []
    seen_ids: set[int] = set()

    def emit(block: str) -> None:
        block = block.strip("\n")
        if block:
            out.append(block)

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                text = _clean(str(child))
                if text:
                    emit(text)
                continue
            if not isinstance(child, Tag) or child.name in _DROP_TAGS:
                continue
            if id(child) in seen_ids:
                continue

            name = child.name
            if re.fullmatch(r"h[1-6]", name):
                seen_ids.add(id(child))
                title = _clean(_inline(child, base_url))
                while (m := _WHOLLY_EMPHASISED.match(title)):
                    stripped = m.group("inner").strip()
                    if not stripped:
                        break
                    title = stripped
                if title:
                    emit("#" * int(name[1]) + " " + title)
            elif name in ("ul", "ol"):
                seen_ids.add(id(child))
                emit(_render_list(child, base_url))
            elif name == "table":
                seen_ids.add(id(child))
                emit(_render_table(child, base_url))
            elif name == "blockquote":
                seen_ids.add(id(child))
                inner = _clean(_inline(child, base_url))
                if inner:
                    emit("\n".join(f"> {ln}" for ln in inner.split("\n")))
            elif name == "pre":
                seen_ids.add(id(child))
                code = child.get_text("", strip=False).strip("\n")
                if code:
                    emit(f"```\n{code}\n```")
            elif name == "p" or (name in ("figcaption", "dt", "dd")):
                seen_ids.add(id(child))
                text = _clean(_inline(child, base_url))
                if text:
                    emit(text)
            elif name == "hr":
                emit("---")
            else:
                # Structural wrapper: recurse.
                walk(child)

    walk(root)

    markdown = "\n\n".join(out).strip()
    if not markdown:
        raise ExtractionError("no content extracted")
    if not re.search(r"^#{1,6}\s+\S", markdown, re.M):
        raise ExtractionError("content extracted but contains no headings")
    return markdown + "\n"
