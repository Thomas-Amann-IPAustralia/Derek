"""Every internal documentation link resolves.

The docs are not decoration here. CLAUDE.md's invariant table is thirteen links
into `docs/02-decisions.md`, and the instruction at the top of that table is to
read the ADR before changing the thing it governs. A link that silently lands at
the top of the file instead of at the reasoning makes that instruction
unfollowable, and nothing else would notice.

That is not hypothetical: 129 anchors were broken when this test was written.
GitHub's slugger deletes an em dash rather than replacing it with a space, so
`## ADR-001 — Snapshot integrity` is `adr-001--snapshot-integrity` with two
hyphens, and every reference written with one hyphen went nowhere. Confirmed
against the rendered page rather than inferred:

    id="user-content-adr-001--snapshot-integrity-over-site-metadata"
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Every markdown file that is documentation rather than corpus content. The
# corpus is a snapshot of somebody else's website and its links are their
# problem, not ours.
DOC_GLOBS = ("*.md", "docs/*.md", "tools/**/*.md", "ledger/**/*.md", "golden/**/*.md")


def _slug(heading: str) -> str:
    """GitHub's heading slug: lowercase, delete punctuation, spaces to hyphens.

    Note it deletes rather than replaces, so `A — B` yields `a--b`, and it does
    not collapse the repeated hyphen.
    """
    return re.sub(r"[^\w\s-]", "", heading.lower().strip(), flags=re.U).replace(" ", "-")


def _docs() -> dict[Path, set[str]]:
    out: dict[Path, set[str]] = {}
    for pattern in DOC_GLOBS:
        for path in REPO.glob(pattern):
            if path.is_file():
                out[path.resolve()] = {
                    _slug(h) for h in
                    re.findall(r"^#{1,6} (.+)$", path.read_text(encoding="utf-8"), re.M)
                }
    return out


DOCS = _docs()


def test_every_internal_doc_link_resolves():
    broken: list[str] = []
    for path, own_headings in sorted(DOCS.items()):
        rel = path.relative_to(REPO)
        for link in sorted(set(re.findall(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")))):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target, _, fragment = link.partition("#")
            if target:
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    broken.append(f"{rel} -> {link}  (no such file)")
                    continue
                headings = DOCS.get(resolved)
                if headings is None:
                    continue          # a link to code, not to a doc
            else:
                headings = own_headings
            if fragment and fragment not in headings:
                broken.append(f"{rel} -> {link}  (no such heading)")
    assert not broken, "\n  " + "\n  ".join(broken)


def test_the_adr_index_lists_every_adr():
    """The table at the top of the decision log is how anyone finds an ADR."""
    src = (REPO / "docs" / "02-decisions.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (ADR-(\d+).+)$", src, re.M)
    listed = set(re.findall(r"^\| \[(\d+)\]\(#", src, re.M))
    assert {n for _, n in headings} == listed, (
        f"index lists {sorted(listed)}, file has {sorted(n for _, n in headings)}")


def test_every_invariant_in_claude_md_cites_a_reachable_rationale():
    """D-1 to D-14 each cite their reasoning; a dead citation is an unexplained rule.

    Most cite an ADR. D-5 cites the postmortem section that found the failure,
    which is the better primary source for it, so the test checks that a citation
    exists and resolves rather than insisting on which document it points at.
    """
    claude = REPO / "CLAUDE.md"
    src = claude.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (D-\d+) \| (.+?) \| (.+?) \|\s*$", src, re.M)
    assert len(rows) == 14, f"expected D-1..D-14, found {len(rows)}"

    problems = []
    for name, _rule, citation in rows:
        links = re.findall(r"\]\(([^)\s]+)\)", citation)
        if not links:
            problems.append(f"{name} cites nothing")
            continue
        for link in links:
            target, _, fragment = link.partition("#")
            resolved = (claude.parent / target).resolve()
            if not resolved.exists():
                problems.append(f"{name} -> {link} (no such file)")
            elif fragment and fragment not in DOCS.get(resolved, {fragment}):
                problems.append(f"{name} -> {link} (no such heading)")
    assert not problems, "\n  " + "\n  ".join(problems)
