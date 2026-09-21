"""Hand-audit instrument for the deterministic extractor.

``derek.eval.audit_extraction`` answers *did the corpus survive conversion?* by
diffing markdown against the source DOM. This module answers the different
question a reader asks when the candidate count surprises them:

    Given the corpus exactly as it stands, is the extractor making the right
    call on each heading — and when it is wrong, which branch is wrong?

Everything here is a **measuring instrument**. It reads the corpus and prints;
it never writes the ledger and never feeds a value back into extraction. The
classification is reproduced branch by branch rather than by calling
the extractor and inferring, so the output names the specific test that
decided each heading. ``counts`` asserts the mirror still agrees with
``derek.extract.candidates`` on every heading, so it cannot drift silently.

Stdlib-only, like the tier it audits.

    python -m derek.eval.audit_headings sample [pages] [seed]
    python -m derek.eval.audit_headings counts
    python -m derek.eval.audit_headings modal
    python -m derek.eval.audit_headings gold-recall
    python -m derek.eval.audit_headings fronted
    python -m derek.eval.audit_headings lexicon
    python -m derek.eval.audit_headings octavius [jsonl]
"""

from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path

from derek.corpus.eligibility import load_eligibility
from derek.corpus.normalise import (
    BOILERPLATE_HEADINGS, EXAMPLE_HEADINGS, NormalisedPage,
)
from derek.extract.candidates import (
    IMPERATIVE_VERBS, CandidateKind, classify_heading, has_polarised_examples,
    normalise_statement,
    _CONTACT_FRAGMENT, _MODAL, _NEGATIVE_OPENERS, _PERSON_AFFILIATION, _WORD,
)
from derek.extract.segment import Node, iter_nodes, parse_page

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
OCTAVIUS = REPO / "reference" / "octavius-v1" / "rules_working_draft.v1.jsonl"

# Example-block labels whose polarity the Style Manual's own editors asserted.
# A heading that owns one of each is a rule by the manual's own testimony,
# whatever grammatical form its wording happens to take (ADR-011).
POLARITY = {
    "write this": "compliant", "do this": "compliant",
    "correct": "compliant", "like this": "compliant",
    "not this": "violating", "don't do this": "violating",
    "incorrect": "violating",
}

# A heading of the shape "In civil cases, use sentence case ..." — a fronted
# adverbial, then the imperative. ``classify_heading`` only inspects words[0].
_FRONTED = re.compile(r"^(?:[A-Z][^,]{2,60}),\s+(?P<rest>.+)$")

_MARK = {
    CandidateKind.RULE: "RULE",
    CandidateKind.SECTION: "sect",
    CandidateKind.EXAMPLE: "eg  ",
    CandidateKind.BOILERPLATE: "boil",
}


# ---------------------------------------------------------------------------
# Corpus walk
# ---------------------------------------------------------------------------

def eligible_pages() -> list[Path]:
    """Every page extraction is allowed to read, in deterministic order."""
    elig = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    return [
        p for p in sorted(PAGES.rglob("*.md"))
        if elig.decide(str(p.relative_to(PAGES)))[0]
    ]


def walk(pages: list[Path] | None = None):
    """Yield ``(rel_path, node)`` for every heading on every eligible page."""
    for path in pages if pages is not None else eligible_pages():
        rel = str(path.relative_to(PAGES))
        page = NormalisedPage(rel, path.read_text(encoding="utf-8"))
        for node in iter_nodes(parse_page(page.text)):
            yield rel, node


def explain(node: Node) -> tuple[str, str, str]:
    """``(kind, statement_form, branch)`` — mirrors the extractor step for step.

    Kept parallel by hand rather than refactored into the extractor: the
    extractor is a tier that must stay free of anything only an audit needs.
    ``counts`` asserts the two agree on every heading in the corpus, so the
    mirror cannot drift unnoticed.
    """
    t = normalise_statement(node.title)
    low = t.lower()

    if low in EXAMPLE_HEADINGS:
        return CandidateKind.EXAMPLE, "", "example-heading-lexicon"
    if not t:
        return CandidateKind.BOILERPLATE, "", "empty-heading"
    if low in BOILERPLATE_HEADINGS:
        return CandidateKind.BOILERPLATE, "", "boilerplate-lexicon"
    if _CONTACT_FRAGMENT.match(t):
        return CandidateKind.BOILERPLATE, "", "contact-fragment"
    if _PERSON_AFFILIATION.match(t):
        return CandidateKind.BOILERPLATE, "", "person-affiliation"

    words = _WORD.findall(t)
    if len(words) < 2:
        if has_polarised_examples(node):
            return CandidateKind.RULE, "exemplified", "example-pair"
        return CandidateKind.SECTION, "", "under-two-words"
    if low.startswith(_NEGATIVE_OPENERS):
        return CandidateKind.RULE, "negative_imperative", "negative-opener"
    if words[0].lower() in IMPERATIVE_VERBS:
        return CandidateKind.RULE, "imperative", f"imperative-verb:{words[0].lower()}"
    if (m := _MODAL.search(t)) is not None:
        return CandidateKind.RULE, "modal", f"modal:{m.group(0).lower()}"
    # Grammar declined it; the manual's own example pair may still carry it.
    if has_polarised_examples(node):
        return CandidateKind.RULE, "exemplified", "example-pair"
    return CandidateKind.SECTION, "", "descriptive-fallthrough"


def polarities(node: Node) -> set[str]:
    """Which example polarities the manual attached directly under this heading."""
    return {
        POLARITY[label]
        for child in node.children
        if (label := normalise_statement(child.title).lower()) in POLARITY
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def cmd_sample(argv: list[str]) -> int:
    """Print every heading of a random page sample, with the deciding branch."""
    n = int(argv[0]) if argv else 12
    seed = int(argv[1]) if len(argv) > 1 else 20260921
    pages = eligible_pages()
    chosen = sorted(random.Random(seed).sample(pages, min(n, len(pages))))

    print(f"# Heading audit — {len(chosen)} of {len(pages)} eligible pages, seed {seed}")
    print("#\n# h<level> [outcome] <branch that decided it>  <heading>\n")
    for path in chosen:
        rel = str(path.relative_to(PAGES))
        page = NormalisedPage(rel, path.read_text(encoding="utf-8"))
        nodes = list(iter_nodes(parse_page(page.text)))
        rules = sum(
            1 for nd in nodes
            if nd.level > 1 and explain(nd)[0] == CandidateKind.RULE
        )
        print("=" * 78)
        print(f"## {rel}")
        print(f"   {len(nodes)} headings · {rules} rules · repair promotions {page.promotions}\n")
        for node in nodes:
            kind, _, branch = explain(node)
            # A level-1 heading is the page title, excluded structurally before
            # classification is consulted at all (ADR-020).
            mark = "h1-x" if node.level <= 1 else _MARK[kind]
            print(f"  h{node.level} [{mark}] {branch:<30} {node.title}")
            if body := " ".join(node.body.split())[:104]:
                print(f"            · {body}")
        print()
    return 0


def cmd_counts(_: list[str]) -> int:
    """Corpus-wide outcome census, plus a check that the mirror has not drifted."""
    outcome: collections.Counter[str] = collections.Counter()
    branch: collections.Counter[str] = collections.Counter()
    level: collections.Counter[int] = collections.Counter()
    drift: list[str] = []

    for rel, node in walk():
        kind, form, br = explain(node)
        expect = classify_heading(node.title)
        if expect[0] != CandidateKind.RULE and kind == CandidateKind.RULE:
            expect = (CandidateKind.RULE, "exemplified")   # example-pair promotion
        if (kind, form) != expect:
            drift.append(f"{rel}: {node.title!r}")
        if node.level <= 1:
            outcome["h1 excluded (page title)"] += 1
            continue
        outcome[f"{kind}/{form}" if form else kind] += 1
        branch[br.split(":")[0]] += 1
        if kind == CandidateKind.RULE:
            level[node.level] += 1

    total = sum(outcome.values())
    print(f"{total} headings on {len(eligible_pages())} eligible pages\n")
    for name, n in outcome.most_common():
        print(f"  {n:5d}  {n/total:5.1%}  {name}")
    print("\nby deciding branch (excluding h1):")
    for name, n in branch.most_common():
        print(f"  {n:5d}  {name}")
    print("\nrule candidates by heading level:")
    for lv, n in sorted(level.items()):
        print(f"  h{lv}: {n}")

    if drift:
        print(f"\n!! {len(drift)} headings where this audit disagrees with "
              f"classify_heading — the mirror is stale:")
        for d in drift[:10]:
            print(f"   {d}")
        return 1
    print("\nmirror agrees with classify_heading on every heading.")
    return 0


def cmd_modal(_: list[str]) -> int:
    """Every candidate admitted by the modal branch, for hand judgement.

    Worth reading in full: ``must``/``should``/``needs to`` are reliably
    normative, but ``can``/``may`` also match grammar exposition — "Nouns can
    be singular or plural" is a fact about English, not a rule about writing.
    """
    by_modal: dict[str, list[tuple[str, str, int]]] = {}
    for rel, node in walk():
        if node.level <= 1:
            continue
        kind, form, branch = explain(node)
        if kind == CandidateKind.RULE and form == "modal":
            by_modal.setdefault(branch.split(":", 1)[1], []).append(
                (normalise_statement(node.title), rel, node.level)
            )
    total = sum(len(v) for v in by_modal.values())
    print(f"{total} candidates admitted by the modal branch\n")
    for modal in sorted(by_modal, key=lambda m: -len(by_modal[modal])):
        print(f"--- '{modal}' — {len(by_modal[modal])} ---")
        for stmt, rel, lv in sorted(by_modal[modal]):
            print(f"  h{lv}  {stmt}\n        {rel}")
        print()
    return 0


def cmd_gold_recall(_: list[str]) -> int:
    """Recall measured against the manual's own testimony.

    A heading with both a compliant and a violating example block beneath it
    is one the Style Manual's editors treated as a rule. That judgement is
    independent of Derek, so it is the one recall figure here that does not
    rest on the auditor's opinion.

    Since the extractor now admits these directly (``has_polarised_examples``),
    this reads 100% and is a **regression guard**: anything less means the
    promotion has broken and rules with gold examples attached are being
    dropped. It was 66.1% (113 of 171) before the 2026-09-21 hand audit.
    """
    found: list[tuple[str, str, int]] = []
    missed: list[tuple[str, str, int]] = []
    for rel, node in walk():
        if node.level <= 1 or len(polarities(node)) < 2:
            continue
        stmt = normalise_statement(node.title)
        row = (stmt, rel, node.level)
        if explain(node)[0] == CandidateKind.RULE:
            found.append(row)
        else:
            missed.append(row)

    total = len(found) + len(missed)
    print(f"{total} headings carry BOTH a compliant and a violating example block.")
    print(f"  extracted as rules : {len(found)}")
    print(f"  filed as sections  : {len(missed)}")
    print(f"  recall             : {len(found)/total:.1%}\n")
    if not missed:
        print("No regression: every example-paired heading is a rule candidate.")
        return 0
    print("REGRESSION — the manual furnished a polarised example pair and the")
    print("extractor still did not call it a rule:\n")
    for stmt, rel, lv in sorted(missed, key=lambda r: (r[1], r[0])):
        print(f"  h{lv}  {stmt}\n        {rel}")
    return 1


def cmd_fronted(_: list[str]) -> int:
    """Imperatives hidden behind a fronted clause, which words[0] cannot see."""
    rows = []
    for rel, node in walk():
        if node.level <= 1 or explain(node)[0] != CandidateKind.SECTION:
            continue
        stmt = normalise_statement(node.title)
        if (m := _FRONTED.match(stmt)) is None:
            continue
        rest = m.group("rest")
        head = _WORD.findall(rest)
        if not head:
            continue
        if head[0].lower() in IMPERATIVE_VERBS or rest.lower().startswith(_NEGATIVE_OPENERS):
            rows.append((head[0].lower(), stmt, rel, node.level))
    print(f"{len(rows)} section headings are an imperative behind a fronted clause\n")
    for verb, stmt, rel, lv in sorted(rows):
        print(f"  h{lv}  [{verb}]  {stmt}\n        {rel}")
    return 0


def cmd_lexicon(_: list[str]) -> int:
    """Where the hand-curated verb list is thin, and where it is dead weight."""
    fires: collections.Counter[str] = collections.Counter()
    heads: collections.Counter[str] = collections.Counter()
    example: dict[str, str] = {}

    for rel, node in walk():
        if node.level <= 1:
            continue
        stmt = normalise_statement(node.title)
        words = _WORD.findall(stmt)
        if len(words) < 2:
            continue
        first = words[0].lower()
        kind, form, _ = explain(node)
        if kind == CandidateKind.RULE and form == "imperative":
            fires[first] += 1
        elif kind == CandidateKind.SECTION:
            heads[first] += 1
            example.setdefault(first, f"{stmt}  [{rel}]")

    unused = sorted(IMPERATIVE_VERBS - set(fires))
    print(f"lexicon: {len(IMPERATIVE_VERBS)} verbs · {len(fires)} fire · {len(unused)} never fire\n")
    print("Never fires on this corpus (harmless today, a false positive waiting"
          " for the next Style Manual edit):")
    print("  " + ", ".join(unused) + "\n")
    print("Most frequent first words of SECTION headings — a verb in this list")
    print("is a lexicon gap; a noun is the branch working correctly:\n")
    for word, n in heads.most_common(40):
        print(f"  {n:4d}  {word:14s} e.g. {example[word][:92]}")
    return 0


def cmd_octavius(argv: list[str]) -> int:
    """Like-for-like count against Octavius, controlling for page eligibility.

    The headline comparison people reach for — 801 against 662 — is not
    like for like. Octavius *extracted* 3,114 rules; 801 is the subset whose
    self-authored tests passed, and those 801 include rules from pages Derek
    declares non-normative (ADR-005). Controlling for both is the whole point
    of this report.
    """
    path = Path(argv[0]) if argv else OCTAVIUS
    if not path.exists():
        print(f"No Octavius reference at {path}")
        return 1

    elig = load_eligibility(REPO / "corpus" / "eligibility.yaml")
    corpus = {str(p.relative_to(PAGES)) for p in PAGES.rglob("*.md")}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def rel_of(row: dict) -> str:
        return re.sub(r"^content/", "", row["source_file"])

    shipped = [r for r in rows if r.get("test_result") == "pass"]
    drifted = [r for r in shipped if rel_of(r) not in corpus]
    known = [r for r in shipped if rel_of(r) in corpus]
    on_eligible = [r for r in known if elig.decide(rel_of(r))[0]]
    on_excluded = [r for r in known if not elig.decide(rel_of(r))[0]]

    derek: collections.Counter[str] = collections.Counter()
    for rel, node in walk():
        if node.level > 1 and explain(node)[0] == CandidateKind.RULE:
            derek[rel] += 1

    print(f"Octavius working draft            {len(rows):5d}")
    print(f"  of which tests passed (shipped) {len(shipped):5d}   <- the '801'")
    print(f"  shipped, page path since renamed{len(drifted):5d}")
    print(f"  shipped, page Derek excludes    {len(on_excluded):5d}   (ADR-005: not rule sources)")
    print(f"  shipped, page Derek reads       {len(on_eligible):5d}")
    print(f"Derek candidates                  {sum(derek.values()):5d}\n")
    print("Like for like — same pages, both methods:"
          f" {len(on_eligible)} vs {sum(derek.values())}\n")

    oct_page: collections.Counter[str] = collections.Counter(rel_of(r) for r in on_eligible)
    pages = sorted(set(oct_page) | set(derek))
    print("Equal totals are not equal rulebooks. Largest per-page gaps:\n")
    print("  octavius  derek   page")
    gaps = sorted(pages, key=lambda p: derek[p] - oct_page[p])
    for p in gaps[:8]:
        print(f"  {oct_page[p]:8d}  {derek[p]:5d}   {p}")
    print("  ...")
    for p in gaps[-8:]:
        print(f"  {oct_page[p]:8d}  {derek[p]:5d}   {p}")
    return 0


COMMANDS = {
    "sample": cmd_sample,
    "counts": cmd_counts,
    "modal": cmd_modal,
    "gold-recall": cmd_gold_recall,
    "fronted": cmd_fronted,
    "lexicon": cmd_lexicon,
    "octavius": cmd_octavius,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        print("commands: " + ", ".join(COMMANDS))
        return 2
    try:
        return COMMANDS[argv[0]](argv[1:])
    except BrokenPipeError:
        # These reports are long and meant to be piped through `head` or
        # `less`; a closed pipe is the reader leaving, not a failure.
        try:
            sys.stdout.close()
        finally:
            return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
