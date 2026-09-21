"""Deterministic rule-candidate extraction.

The set of candidates is a pure function of the corpus (ADR-002). A model
may later classify, formalise or annotate a candidate; it may never decide
that one exists. Two runs over the same corpus therefore produce byte-identical
candidate sets, which is the reproducibility requirement Octavius could not
meet (postmortem F8).

Identity is content-addressed:

    candidate_uid = blake2s(page_path || heading_path || normalised_statement)

so a reworded rule is a *new* candidate whose lineage is reconciled
explicitly rather than guessed (see ``derek.ledger.reconcile``).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from derek.corpus.normalise import BOILERPLATE_HEADINGS, EXAMPLE_HEADINGS
from derek.extract.segment import Node, iter_nodes, parse_page

__all__ = [
    "Candidate",
    "CandidateKind",
    "classify_heading",
    "extract_candidates",
    "candidate_uid",
    "IMPERATIVE_VERBS",
]

_DATA = Path(__file__).parent / "data"
IMPERATIVE_VERBS: frozenset[str] = frozenset(
    line.strip().lower()
    for line in (_DATA / "imperative_verbs.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)

# Negative imperatives; these open a MUST_NOT/SHOULD_NOT statement.
_NEGATIVE_OPENERS = (
    "don't ", "dont ", "do not ", "never ", "avoid ", "don’t ",
)

# Modals that make a descriptive sentence normative.
_MODAL = re.compile(
    r"\b(?:must|should|shall|need(?:s)? to|ought to|may|can|cannot|can't|is required to)\b",
    re.I,
)

# "Carly Summerell, content designer (seconded from …)" — acknowledgements,
# never a rule. Matches Name-shaped text with a parenthetical affiliation.
_PERSON_AFFILIATION = re.compile(
    r"^[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3}"
    r"(?:\s+[A-Z]{2,4})?\s*(?:,[^(]{0,60})?\([^)]+\)\s*$"
)

# Postal/contact fragments that survive extraction on some pages.
_CONTACT_FRAGMENT = re.compile(
    r"^(?:PO Box|GPO Box|Locked Bag|Level \d|Phone|Email|Fax|ABN|ACN)\b", re.I
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_WS = re.compile(r"\s+")

# Example lines carry editorial apparatus that must not reach training or
# evaluation data: a trailing bracketed gloss, and inline markdown links to
# other Style Manual pages.
# Excludes "[" from the link text so a nested link inside a gloss is
# resolved innermost-first rather than the outer bracket swallowing it.
_MD_LINK = re.compile(r"\[([^\[\]]*)\]\([^)]*\)")
_GLOSS_SUFFIX = re.compile(r"\s*\[[^\]]*\]\s*$")


class CandidateKind:
    """How a heading node was classified."""

    RULE = "rule"
    SECTION = "section"
    EXAMPLE = "example"
    BOILERPLATE = "boilerplate"


@dataclass
class Candidate:
    """A deterministically identified rule candidate."""

    uid: str
    page_path: str
    heading_path: tuple[str, ...]
    statement: str
    statement_form: str          # imperative | negative_imperative | modal | descriptive
    level: int
    body: str
    line_start: int
    examples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def source_anchor(self) -> str:
        """Human-readable address of this candidate in the corpus."""
        return f"{self.page_path}#{' > '.join(self.heading_path)}"


def normalise_statement(text: str) -> str:
    """Canonical form of a rule statement, used for identity and matching.

    Case and internal whitespace are preserved deliberately — the Style
    Manual's wording is the provenance record — but Unicode form, quote
    characters and edge whitespace are canonicalised so that a re-scrape
    cannot change a UID without the wording changing.
    """
    t = unicodedata.normalize("NFC", text)
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("‑", "-").replace("‐", "-")
    return _WS.sub(" ", t).strip()


def candidate_uid(page_path: str, heading_path: tuple[str, ...], statement: str) -> str:
    """Stable 16-hex-character identity for a candidate."""
    h = hashlib.blake2s(digest_size=8)
    h.update(page_path.encode("utf-8"))
    h.update(b"\x00")
    h.update(" > ".join(heading_path).encode("utf-8"))
    h.update(b"\x00")
    h.update(normalise_statement(statement).encode("utf-8"))
    return h.hexdigest()


def classify_heading(title: str) -> tuple[str, str]:
    """Classify a heading. Returns ``(kind, statement_form)``.

    ``statement_form`` is meaningful only when ``kind`` is ``RULE``.
    """
    t = normalise_statement(title)
    low = t.lower()

    if low in EXAMPLE_HEADINGS:
        return CandidateKind.EXAMPLE, ""
    if not t or low in BOILERPLATE_HEADINGS:
        return CandidateKind.BOILERPLATE, ""
    if _CONTACT_FRAGMENT.match(t) or _PERSON_AFFILIATION.match(t):
        return CandidateKind.BOILERPLATE, ""

    words = _WORD.findall(t)
    if len(words) < 2:
        # "Pronouns", "Hyphens", "Neurodiversity" — a topic label, not a
        # statement. A single word cannot carry a verb and an object.
        return CandidateKind.SECTION, ""

    if low.startswith(_NEGATIVE_OPENERS):
        return CandidateKind.RULE, "negative_imperative"
    if words[0].lower() in IMPERATIVE_VERBS:
        return CandidateKind.RULE, "imperative"
    if _MODAL.search(t):
        return CandidateKind.RULE, "modal"

    # A present-tense generalisation such as "Conjunctions join words,
    # phrases and clauses" is normative in this corpus, but so is a lot of
    # topical prose. Treated as a section: still recorded, reviewable, and
    # promotable by hand, but not asserted to be a rule.
    return CandidateKind.SECTION, ""


def clean_example(text: str) -> str:
    """Strip editorial apparatus from an example line.

    Resolves markdown links to their link text and removes the trailing
    bracketed gloss the manual uses to explain an example
    ("… [Adverbial phrase]"). Applied repeatedly because a gloss may itself
    contain a link, which leaves a second bracket pair behind.
    """
    prev = None
    out = text
    while out != prev:
        prev = out
        out = _MD_LINK.sub(r"\1", out)
        out = _GLOSS_SUFFIX.sub("", out).strip()
    return out


def _harvest_examples(node: Node) -> dict[str, list[str]]:
    """Collect labelled example blocks sitting directly under a rule node.

    The Style Manual authors correctly-polarised example pairs as ``Write
    this`` / ``Not this`` (and ``Correct`` / ``Incorrect``) blocks. These are
    the seed evaluation set (ADR-011, ADR-013) and the one thing Octavius
    never used.
    """
    buckets: dict[str, list[str]] = {}
    for child in node.children:
        label = normalise_statement(child.title).lower()
        if label not in EXAMPLE_HEADINGS:
            continue
        lines = [
            re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s*", "", ln).strip()
            for ln in child.body.split("\n")
        ]
        items = [
            cleaned
            for ln in lines
            if ln and not ln.startswith("[") and not ln.startswith("#")
            and (cleaned := clean_example(ln))
        ]
        if items:
            buckets.setdefault(label, []).extend(items)
    return buckets


def extract_candidates(page_path: str, normalised_text: str) -> list[Candidate]:
    """Extract every rule candidate from one normalised page.

    Pure function: same input, same output, always.
    """
    root = parse_page(normalised_text)
    out: list[Candidate] = []

    for node in iter_nodes(root):
        # A level-1 heading is the page title — its subject, not a normative
        # statement about text. Every rule in the Style Manual sits at h2 or
        # below. Some page titles read as imperatives ("Make content
        # accessible", "Apply accessibility principles") and would otherwise
        # be admitted as rules far too broad to detect.
        #
        # This structural exclusion is only safe because heading levels now
        # come from the DOM (ADR-020); under the old converter, levels could
        # not be trusted to mean anything.
        if node.level <= 1:
            continue
        kind, form = classify_heading(node.title)
        if kind != CandidateKind.RULE:
            continue
        statement = normalise_statement(node.title)
        out.append(
            Candidate(
                uid=candidate_uid(page_path, node.path, statement),
                page_path=page_path,
                heading_path=node.path,
                statement=statement,
                statement_form=form,
                level=node.level,
                body=node.body.strip(),
                line_start=node.line_start,
                examples=_harvest_examples(node),
            )
        )

    # Deterministic order: document order is already guaranteed by the
    # depth-first walk, but sort defensively so output never depends on
    # dict or set iteration anywhere upstream.
    out.sort(key=lambda c: (c.line_start, c.uid))
    return out
