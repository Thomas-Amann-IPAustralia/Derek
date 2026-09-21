"""Imperative detection by POS tagging — the offline authoring step for Q8.

``classify_heading`` decides "this heading is an instruction" by looking up its
first word in ``derek/extract/data/imperative_verbs.txt``, a hand-curated list.
docs/07 measured what that costs: rules are missed when the manual uses a verb
nobody typed into the list, or puts the verb behind a fronted clause where
``words[0]`` cannot see it. Worse, the list cannot tell a verb from a noun, so
*"Place a comma after adverbs"* (a rule) and *"Place of publication of a book"*
(a citation-format label) are indistinguishable to it.

A tagger resolves both, and Q8 asks for one. The constraint is D-7: candidate
identity must be a pure function of the corpus, and ``derek/extract/`` is
stdlib-only because a silent dependency bump there would rewrite the rulebook
without the Style Manual changing a word (tests/test_dependency_tiers.py).

So the tagger never runs inside extraction. It runs **here**, offline, against
a pinned model, and writes its verdicts to a checked-in table that
``derek.extract.candidates`` reads with nothing but ``json``. The consequences
are the point:

* Extraction stays stdlib-only and reproducible with no model installed at all.
* CI rebuilds the ledger byte-identically without spaCy — determinism is
  *stronger* than it would be with a live tagger, not weaker.
* A model upgrade becomes a regenerated table and a reviewable git diff,
  which is how ADR-001 already treats the HTML converter's pin.

Usage::

    python tools/postag/tag_headings.py build   # write the verdict table
    python tools/postag/tag_headings.py diff    # lexicon vs tagger, with counts
    python tools/postag/tag_headings.py probe "Join nouns with an en dash"

Requires ``requirements-pipeline.txt`` (spaCy is deliberately absent from
``requirements.txt``, which is what CI installs).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from derek.corpus.eligibility import load_eligibility            # noqa: E402
from derek.corpus.normalise import NormalisedPage                # noqa: E402
from derek.extract.candidates import (                           # noqa: E402
    IMPERATIVE_VERBS,
    TABLE_PATH,
    _WORD,
    normalise_statement,
)
from derek.extract.segment import iter_nodes, parse_page         # noqa: E402

PAGES = REPO / "corpus" / "pages"

# PINNED, for the same reason the HTML parser is pinned (ADR-001, ADR-020): a
# model bump changes which rules exist, so it must be a deliberate, reviewed
# event with a diff attached, never a silent `pip install -U`.
MODEL = "en_core_web_sm"
MODEL_VERSION = "3.8.0"

# A heading is not a sentence: it carries no terminal punctuation, and without
# one the parser has to guess whether a bare capitalised token is a command or
# a label. It guesses badly — "Summary" alone tags as VB, and "Address blocks"
# parses as subject+verb. Supplying the full stop the heading omits fixes both.
# Applied to every heading, so it cannot become a per-heading judgement call.
_TERMINAL = (".", "!", "?", ":", ";")


def load_model():
    """Load the pinned model, refusing a version that is not the pinned one."""
    import spacy

    nlp = spacy.load(MODEL)
    actual = nlp.meta["version"]
    if actual != MODEL_VERSION:
        raise SystemExit(
            f"{MODEL} {actual} is installed but this tool pins {MODEL_VERSION}.\n"
            "A model change rewrites the verdict table and therefore the rulebook. "
            "Install the pinned version, or change MODEL_VERSION deliberately and "
            "commit the regenerated table as its own reviewable diff."
        )
    return nlp


def is_imperative(nlp, statement: str) -> tuple[bool, str]:
    """Is this heading a command? Returns ``(verdict, reason)``.

    An English imperative is a base-form verb heading its own clause with no
    subject: *"Join nouns with an en dash"*. Three properties carry that, and
    each rejects something the lexicon gets wrong:

    * the clause root is tagged ``VB`` (base form) — rejects *"Order of
      reference symbols"*, where ``Order`` is a noun, and *"Style for bill
      titles is roman type"*, where the root is ``is``;
    * the root has no subject of its own — rejects *"Noun trains are hard to
      understand"* and *"Nouns can be singular or plural"*;
    * anything to the left of the root is therefore adverbial, which is
      precisely the fronted case ``words[0]`` cannot reach: *"In civil cases,
      use sentence case"*, *"Only use the contraction 'no' with numerals"*.

    Subjecthood is tested on the root's **direct** children only. *"Use a comma
    after clauses that change the sentence"* contains an ``nsubj`` (``that``),
    but it belongs to the relative clause, not to ``Use``.
    """
    text = statement if statement.endswith(_TERMINAL) else statement + "."
    doc = nlp(text)

    sents = list(doc.sents)
    if not sents:
        return False, "unparsed"
    root = sents[0].root

    if root.tag_ != "VB":
        return False, f"root-{root.tag_ or 'none'}"
    # AUX covers "Be consistent" / "Do this"; the tag check already excludes
    # inflected auxiliaries such as the "is" of a descriptive statement.
    if root.pos_ not in ("VERB", "AUX"):
        return False, f"root-pos-{root.pos_}"
    if subj := [c.dep_ for c in root.children if c.dep_ in ("nsubj", "nsubjpass", "expl")]:
        return False, f"has-{subj[0]}"

    return True, f"imperative:{root.lemma_.lower()}"


def eligible_pages() -> list[Path]:
    elig = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    return [
        p for p in sorted(PAGES.rglob("*.md"))
        if elig.decide(str(p.relative_to(PAGES)))[0]
    ]


def corpus_headings() -> list[str]:
    """Every distinct normalised heading text in the eligible corpus, sorted.

    Keyed on text alone and covering every level, so the table does not depend
    on where ``classify_heading`` happens to consult it. Reordering the
    extractor's branches cannot silently invalidate a verdict.
    """
    seen: set[str] = set()
    for path in eligible_pages():
        rel = str(path.relative_to(PAGES))
        page = NormalisedPage(rel, path.read_text(encoding="utf-8"))
        for node in iter_nodes(parse_page(page.text)):
            if title := normalise_statement(node.title):
                seen.add(title)
    return sorted(seen)


def headings_digest(headings: list[str]) -> str:
    """Identity of the tagger's input set, so a stale table is detectable.

    A heading added upstream that the table has never seen would otherwise be
    judged by the lexicon fallback in silence — a silently dropped rule, which
    is the exact failure this work exists to remove.
    """
    h = hashlib.blake2s(digest_size=16)
    for text in headings:
        h.update(text.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def build_table(nlp, headings: list[str]) -> dict:
    verdicts = {text: is_imperative(nlp, text)[0] for text in headings}
    return {
        "_meta": {
            "generated_by": "tools/postag/tag_headings.py",
            "model": MODEL,
            "model_version": MODEL_VERSION,
            "heading_count": len(headings),
            "imperative_count": sum(verdicts.values()),
            "headings_digest": headings_digest(headings),
            "note": (
                "Generated, not hand-edited. Regenerate with "
                "`python tools/postag/tag_headings.py build` and commit the diff. "
                "Extraction reads this file with stdlib json only (D-7)."
            ),
        },
        "verdicts": {text: verdicts[text] for text in headings},
    }


def cmd_build(argv: list[str]) -> int:
    nlp = load_model()
    headings = corpus_headings()
    table = build_table(nlp, headings)

    # Determinism is the whole claim; verify it rather than assert it.
    again = build_table(nlp, headings)
    if again != table:
        raise SystemExit("the tagger is not deterministic on this model — refusing to write")

    TABLE_PATH.write_text(
        json.dumps(table, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    meta = table["_meta"]
    print(f"wrote {TABLE_PATH.relative_to(REPO)}")
    print(f"  {meta['heading_count']} headings · {meta['imperative_count']} imperative")
    print(f"  model {meta['model']} {meta['model_version']} · digest {meta['headings_digest']}")
    return 0


def cmd_diff(argv: list[str]) -> int:
    """Q8's "what would settle it": gains against false positives, counted."""
    nlp = load_model()
    headings = corpus_headings()

    lex_only: list[str] = []
    tag_only: list[tuple[str, str]] = []
    both = 0
    neither = 0

    for text in headings:
        # Tokenised with the extractor's own regex, not an approximation of it:
        # these counts are quoted in ADR-021, so they have to be the counts the
        # classifier would actually produce.
        words = _WORD.findall(text)
        lex = bool(words) and words[0].lower() in IMPERATIVE_VERBS
        tag, reason = is_imperative(nlp, text)
        if lex and tag:
            both += 1
        elif lex:
            lex_only.append(f"{text}   [{reason}]")
        elif tag:
            tag_only.append((text, reason))
        else:
            neither += 1

    print(f"{len(headings)} distinct headings in the eligible corpus\n")
    print(f"  both agree imperative     {both}")
    print(f"  both agree not imperative {neither}")
    print(f"  lexicon only (tagger rejects) {len(lex_only)}")
    print(f"  tagger only (lexicon misses)  {len(tag_only)}")

    print("\n--- lexicon says rule, tagger says no (candidates a swap would DROP) ---")
    for line in lex_only:
        print(f"  {line}")

    print("\n--- tagger says rule, lexicon says no (candidates a swap would ADD) ---")
    for text, reason in tag_only:
        print(f"  {text}   [{reason}]")
    return 0


def cmd_probe(argv: list[str]) -> int:
    if not argv:
        raise SystemExit('usage: tag_headings.py probe "some heading"')
    nlp = load_model()
    for text in argv:
        stmt = normalise_statement(text)
        verdict, reason = is_imperative(nlp, stmt)
        doc = nlp(stmt if stmt.endswith(_TERMINAL) else stmt + ".")
        print(f"{stmt!r}\n  {'IMPERATIVE' if verdict else 'not imperative'}  [{reason}]")
        print("  " + "  ".join(f"{t.text}/{t.tag_}/{t.dep_}" for t in doc))
    return 0


COMMANDS = {"build": cmd_build, "diff": cmd_diff, "probe": cmd_probe}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        print("commands: " + ", ".join(COMMANDS))
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
