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
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from derek.corpus.normalise import (
    BOILERPLATE_HEADINGS,
    COMPLIANT_EXAMPLE_HEADINGS,
    EXAMPLE_HEADINGS,
    VIOLATING_EXAMPLE_HEADINGS,
)
from derek.extract.segment import Node, iter_nodes, parse_page

__all__ = [
    "Candidate",
    "CandidateKind",
    "classify_heading",
    "has_polarised_examples",
    "extract_candidates",
    "candidate_uid",
    "IMPERATIVE_VERBS",
    "IMPERATIVE_HEADINGS",
    "TABLE_PATH",
]

_DATA = Path(__file__).parent / "data"
IMPERATIVE_VERBS: frozenset[str] = frozenset(
    line.strip().lower()
    for line in (_DATA / "imperative_verbs.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)

# Verdicts from the pinned POS tagger, precomputed offline by
# tools/postag/tag_headings.py and checked in (ADR-021, resolving Q8).
#
# What it contributes is recall the verb list cannot reach at any length: an
# imperative whose verb is not the first word, because a fronted adverbial or a
# leading adverb stands in front of it. "In civil cases, use sentence case",
# "Only use the contraction 'no' with numerals".
#
# It is consulted only *after* the verb list and only to admit, never to reject
# — see classify_heading. The tagger can in principle also tell the "Place a
# comma after adverbs" sense of a word from the "Place of publication of a book"
# sense, which no word list can, but that ability is deliberately unused:
# acting on it would mean removing candidates, and docs/07 established that
# those noun-phrase headings sit at the site of a real rule.
#
# It is read as data, never run, for the reason this whole tier is stdlib-only:
# extraction must be reproducible from the corpus alone, and a model that runs
# at extraction time could change the rulebook without the Style Manual
# changing a word (ADR-002, D-7). Reading a checked-in table instead makes the
# tagger's contribution a reviewable diff and leaves CI able to rebuild the
# ledger byte-identically with no model installed.
TABLE_PATH = _DATA / "imperative_headings.json"


def _load_imperative_headings() -> dict[str, bool]:
    """The verdict table, or empty when it has not been generated yet.

    Absent is a supported state: without it every branch falls back to the verb
    list and extraction still runs, just with the recall docs/07 measured.
    tests/test_invariants.py asserts the table is present and current, so a
    stale or missing table fails loudly rather than quietly dropping rules.
    """
    if not TABLE_PATH.is_file():
        return {}
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return table.get("verdicts", {})


IMPERATIVE_HEADINGS: dict[str, bool] = _load_imperative_headings()

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
    statement_form: str          # imperative | negative_imperative | modal | exemplified
    level: int
    body: str
    line_start: int
    examples: dict[str, list[str]] = field(default_factory=dict)
    # Where this candidate came from: the heading walk, or a span a human marked
    # in the annotator (ADR-023). Both are declared inputs and neither involves a
    # model, but the ledger has to be able to say which — a heading candidate is
    # regenerated by the extractor, a human span is only regenerated because the
    # golden set records it.
    origin: str = "heading"      # heading | golden
    preconditions: tuple[str, ...] = ()
    # A lineage the human stated, rather than one the reconciler inferred: the
    # uid of the candidate this span replaces, set when a reviewer moves a span
    # off the heading the extractor proposed and onto the text that actually
    # states the rule. Empty for everything the extractor produces.
    supersedes: str = ""
    # Whether this candidate occupies a heading slot. A body-prose span does not:
    # it was never at a heading position, so it cannot have been reworded from
    # one, and matching it against heading siblings is a category error that
    # reports a supersession where there is no lineage at all.
    positional: bool = True

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
    # The verb list is consulted first and the tagger can only add to it, never
    # overrule it. That is not deference to the older mechanism; it is what the
    # corpus-wide diff showed (docs/07). en_core_web_sm rejects ~120 headings
    # the list correctly admits — "Italicise genus and species names", "Cite
    # plays and poems correctly", "Number the questions" — because a heading
    # supplies too little context for a small model to commit to a verb
    # reading, and because a US-trained model does not know the -ise spellings
    # this corpus is written in. Q8 proposed replacing the list; the
    # measurement it asked for refutes that, so the tagger is additive.
    #
    # What it adds is what no word list can reach: an imperative standing
    # behind a fronted adverbial or a leading adverb, where words[0] is not the
    # verb at all. "In civil cases, use sentence case", "Only use the
    # contraction 'no' with numerals", "After first mention, use the short
    # title in roman type".
    if IMPERATIVE_HEADINGS.get(t):
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


def has_polarised_examples(node: Node) -> bool:
    """Did the Style Manual's editors attach a compliant AND a violating example?

    This is testimony, not inference. When the manual puts a ``Write this``
    beside a ``Not this`` under a heading, its editors have asserted that the
    heading governs a right and a wrong way to write something — which is what
    a rule is. ADR-011 already treats those pairs as ground truth for
    evaluation; there is no coherent reading under which they are ground truth
    for testing a rule but not for finding one.

    It matters because ``classify_heading`` reads grammar, and the manual does
    not state every rule as an instruction. The 2026-09-21 hand audit
    (docs/07) found 58 headings carrying a full example pair that the
    grammatical branches filed as sections — among them "Noun trains are hard
    to understand", "'With' is not a conjunction" and "Style for Act titles is
    title case, not always italics". Each is a real, detectable rule, and each
    arrives with its gold examples already attached.

    Deliberately strict: BOTH polarities are required. One ``Write this`` with
    no counterpart is an illustration, and promoting on that alone would admit
    the section labels that merely happen to contain an example.
    """
    labels = {normalise_statement(c.title).lower() for c in node.children}
    return bool(labels & COMPLIANT_EXAMPLE_HEADINGS) and bool(
        labels & VIOLATING_EXAMPLE_HEADINGS
    )


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
            # A heading the grammatical branches declined, but which the
            # manual itself furnished with a compliant/violating example
            # pair, is a rule on the manual's own testimony. Only SECTION is
            # eligible: an example block may nest a polarised pair of its own,
            # and page chrome is never a rule however it is illustrated.
            if kind != CandidateKind.SECTION or not has_polarised_examples(node):
                continue
            kind, form = CandidateKind.RULE, "exemplified"
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
