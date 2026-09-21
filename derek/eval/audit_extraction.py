"""Audit extracted candidates against the source HTML they came from.

    python -m derek.eval.audit_extraction <html-dir> [sample-size] [seed]

Answers the question the ledger cannot answer about itself: did anything get
lost between the page as the Style Manual publishes it and the rule
candidates we ended up with?

Three checks per sampled page:

1. **Fidelity**  — every content heading in the source DOM appears in the
   converted Markdown, at the same level. Catches converter loss.
2. **Coverage**  — every heading the classifier did NOT call a rule, so a
   human can spot a real rule filed as a section.
3. **Precision** — every candidate emitted, so a human can confirm each is
   genuinely a rule statement.

`<html-dir>` holds the source HTML, laid out by URL path, with an
`_index.json` mapping URL to filename. `derek.corpus.snapshot` does not
retain HTML, so this is run against a deliberate capture.

The first run of this audit (2026-09-21) found three real defects that the
test suite could not: emphasis markers leaking into rule statements, block
text running together inside example cards, and a ~10% recall gap where
imperative headings were filed as sections because the verb was missing from
the lexicon. See docs/06-extraction-audit.md.
"""
import json
import random
import re
import sys
from pathlib import Path



from bs4 import BeautifulSoup  # noqa: E402

from derek.corpus.eligibility import load_eligibility  # noqa: E402
from derek.corpus.normalise import (  # noqa: E402
    BOILERPLATE_HEADINGS, EXAMPLE_HEADINGS, NormalisedPage,
)
from derek.corpus.to_markdown import CHROME_HEADINGS, extract_markdown  # noqa: E402
from derek.extract.candidates import (  # noqa: E402
    CandidateKind, classify_heading, extract_candidates, normalise_statement,
)

REPO = Path(__file__).resolve().parents[2]
PAGES = REPO / "corpus" / "pages"
HEADING = re.compile(r"^h[1-6]$")


def source_headings(html: str) -> list[tuple[int, str, bool]]:
    """Content headings in the source DOM, with chrome removed.

    Mirrors the converter's own chrome rules so that a difference means
    genuine loss rather than a definitional mismatch.
    """
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("main") or soup.select_one("article") or soup.body
    if root is None:
        return []
    for t in root.find_all(["script", "style", "nav", "footer", "header",
                            "aside", "noscript", "form", "button", "svg"]):
        t.decompose()
    out: list[tuple[int, str, bool]] = []
    for h in root.find_all(HEADING):
        # No separator: HTML inline elements do not imply a word boundary,
        # and the Style Manual wraps some apostrophes in nested <span>s
        # ("Don<span>’</span>t"). Using " " here produces "Don ’ t" and
        # reports a phantom difference against a correct conversion.
        title = re.sub(r"\s+", " ", h.get_text("", strip=False)).strip()
        key = title.lower().rstrip(":")
        if key in CHROME_HEADINGS:
            break                      # chrome: rest of page is not content
        if not title:
            continue
        # A heading nested inside a list item is a navigation/example CARD
        # title, not a document section. The converter renders these as list
        # content (with their link), which is correct: emitting them as
        # headings would corrupt the outline. Tag them so the audit can tell
        # expected behaviour from genuine loss.
        in_card = any(a.name == "li" for a in h.parents)
        out.append((int(h.name[1]), title, in_card))
    # The site title h1 sits outside main on most pages; drop it if present.
    return [(lvl, t, card) for lvl, t, card in out if t.lower() != "style manual"]


def markdown_headings(md: str) -> list[tuple[int, str]]:
    return [(len(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"^(#{1,6})\s+(.*?)\s*$", md, re.M)]


def audit(html_dir: Path, sample_size: int, seed: int) -> None:
    index = json.loads((html_dir / "_index.json").read_text())
    el = load_eligibility(REPO / "corpus" / "eligibility.yaml")

    pages = []
    for url, fname in sorted(index.items()):
        rel = (url.split("//", 1)[-1].split("/", 1)[1].strip("/") or "index") + ".md"
        if not el.decide(rel)[0]:
            continue
        if (html_dir / fname).exists() and (PAGES / rel).exists():
            pages.append((rel, url, html_dir / fname))

    random.seed(seed)
    sample = random.sample(pages, min(sample_size, len(pages)))
    sample.sort()

    tot_missing = tot_levelmismatch = tot_extra = tot_cands = 0

    for rel, url, src in sample:
        html = src.read_text(encoding="utf-8", errors="replace")
        md = (PAGES / rel).read_text(encoding="utf-8")
        srcs_all = source_headings(html)
        srcs = [(lvl, t) for lvl, t, card in srcs_all if not card]
        cards = [(lvl, t) for lvl, t, card in srcs_all if card]
        mds = markdown_headings(md)
        cands = extract_candidates(rel, md)
        tot_cands += len(cands)

        src_map = {normalise_statement(t): lvl for lvl, t in srcs}
        md_map = {normalise_statement(t): lvl for lvl, t in mds}

        missing = [(lvl, t) for lvl, t in srcs if normalise_statement(t) not in md_map]
        extra = [(lvl, t) for lvl, t in mds if normalise_statement(t) not in src_map]
        mismatch = [(t, src_map[k], md_map[k]) for lvl, t in srcs
                    if (k := normalise_statement(t)) in md_map and src_map[k] != md_map[k]]

        tot_missing += len(missing)
        tot_extra += len(extra)
        tot_levelmismatch += len(mismatch)

        print("=" * 76)
        print(f"{rel}")
        print(f"  {url}")
        print(f"  source section headings: {len(srcs)}   card headings (expected as list items): {len(cards)}")
        print(f"  markdown headings: {len(mds)}   candidates: {len(cands)}")
        if missing:
            print(f"  !! GENUINELY MISSING FROM MARKDOWN ({len(missing)}):")
            for lvl, t in missing:
                print(f"       h{lvl}  {t[:70]}")
        if mismatch:
            print(f"  !! LEVEL MISMATCH ({len(mismatch)}):")
            for t, a, b in mismatch:
                print(f"       src h{a} -> md h{b}  {t[:64]}")
        if extra:
            print(f"  ?? IN MARKDOWN BUT NOT SOURCE ({len(extra)}):")
            for lvl, t in extra:
                print(f"       h{lvl}  {t[:70]}")

        print("  --- classification of every heading ---")
        for lvl, t in mds:
            kind, form = classify_heading(t)
            mark = {CandidateKind.RULE: "RULE  ", CandidateKind.SECTION: "sect  ",
                    CandidateKind.EXAMPLE: "ex    ", CandidateKind.BOILERPLATE: "boil  "}[kind]
            print(f"    {mark} h{lvl} {t[:66]}" + (f"   [{form}]" if form else ""))
        print()

    print("=" * 76)
    print("SAMPLE TOTALS")
    print(f"  pages sampled                 : {len(sample)}")
    print(f"  candidates extracted          : {tot_cands}")
    print(f"  section headings genuinely missing: {tot_missing}")
    print(f"  heading level mismatches       : {tot_levelmismatch}")
    print(f"  markdown headings not in source: {tot_extra}")


if __name__ == "__main__":
    audit(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 12,
          int(sys.argv[3]) if len(sys.argv) > 3 else 20260921)
