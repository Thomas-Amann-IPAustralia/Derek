# Extraction audit — 2026-09-21

An audit of extracted rule candidates against the source HTML the Style Manual
actually publishes. Repeatable:

```bash
python -m derek.eval.audit_extraction <html-dir> [sample-size] [seed]
```

It answers the question the ledger cannot answer about itself: **did anything get lost
between the page as published and the candidates we ended up with?**

---

## Why this was run

Extraction reads the rule inventory off the heading tree
([ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity)), so heading
fidelity decides which rules exist. The previous corpus was converted with
`trafilatura`, which flattens heading levels, and a repair heuristic guessed the
structure back. That left **390 of 546 candidates (71%) depending on a heuristic** —
too much weight for a guess to carry.

[ADR-020](02-decisions.md#adr-020-heading-levels-come-from-the-dom) replaced the
converter with one that reads levels from the DOM. This audit checks whether that
worked, and what else was wrong.

**Source of the HTML.** The live site's Akamai edge returns `403` to this environment's
IP range, so the source HTML was retrieved from the Wayback Machine (snapshot
`20260920`, one day old). That is the same document the scraper fetches; only the
transport differs. The scraper's own network path remains unexercised from here.

---

## Headline result

| | Before (trafilatura) | After (DOM) |
|---|---|---|
| Corpus heading levels | `h1: 2 · h2: 53 · h3: 1795 · h4: 782 · h5: 141` | `h1: 185 · h2: 727 · h3: 1510 · h4: 781 · h5: 142` |
| Candidates depending on a repair heuristic | **390 of 546 (71%)** | **0** |
| Boilerplate heading nodes the classifier had to filter | 473 | 1 |
| Rule candidates | 546 | **662** |
| Candidates with hand-authored gold examples | 318 | 366 |
| Candidates with *paired* compliant + violating examples | 77 | 83 |

Heading repair is retained as a regression guard and is now **self-disabling**: it
returns the text unchanged when a level-1 or level-2 heading is already present. It
performs **zero** promotions on the current corpus. A non-zero count on a fresh scrape
now means the converter has broken.

### Conversion fidelity

Three independent random samples of 30 pages each, measured against the source DOM:

| Seed | Pages | Candidates | Headings missing | Level mismatches | Headings not in source |
|---|---|---|---|---|---|
| 777 | 30 | 163 | **0** | **0** | **0** |
| 20260921 | 30 | 133 | **0** | **0** | **0** |
| 31415 | 30 | 145 | **0** | **0** | **0** |

---

## Defects the audit found

All three were invisible to the test suite, because the tests check the pipeline
against its own assumptions. Only comparison against the published page surfaced them.

### 1. Emphasis markers leaking into rule statements

The Style Manual uses `<h2><strong>…</strong></h2>` on some pages. The converter
rendered the emphasis, producing headings like:

```
## **Respectful language use starts with the basics**
```

A rule's `statement` is its provenance record **and** an input to its
content-addressed UID, so `**` in a heading corrupts both. Ten headings were affected;
none happened to be classified as rules, so no ledger entry was polluted — this was a
latent bug, caught before it mattered.

**Fixed.** Emphasis wrapping an *entire* heading is stripped as presentational.
Emphasis on *part* of a heading is preserved, because there it is the rule's subject:
in *"use sentence case and italics for `*Re*` and `*Ex parte*`"* the italics are what
the rule is about.

### 2. Block text running together inside example cards

The manual nests `<h4>` and `<p>` inside `<li>` to build example cards. The inline
renderer concatenated them without a separator:

```
- Symposium Series 2025Plain language: 3–5 March
```

Cosmetic in prose, but **example text feeds the gold evaluation set**
([ADR-011](02-decisions.md#adr-011-the-dogfood-gate),
[ADR-013](02-decisions.md#adr-013-confidence-is-calibrated-not-raw)), so corrupted
example sentences would have propagated into calibration data.

**Fixed.** A block-level child inside an inline context now gets a separator.

### 3. A ~10% recall gap in imperative detection

The most consequential finding. Reading classifications against source pages showed
real rules filed as sections:

- *"Meet WCAG level AA, but aim higher"*
- *"Join nouns with an en dash to show an equal relationship"*
- *"Draw attention to words using quotation marks"*
- *"Get permissions and licences for copyright material"*
- *"Split large reports into volumes"*

Measured across the whole corpus with a POS tagger (used **only as a measuring
instrument**, not shipped), **65 imperative headings were classified as sections**:

| Cause | Count |
|---|---|
| Verb absent from `imperative_verbs.txt` | 50 |
| Rejected by the three-word minimum (e.g. *"Provide context"*) | 15 |

**Fixed**, to the extent a lexicon can be:

- 47 verbs added, every one evidenced by the audit rather than guessed
  (`address`, `meet`, `join`, `draw`, `split`, `quantify`, `alphabetise`, …).
- The minimum lowered from three words to two. A single word cannot carry a verb and
  an object; two words can (*"Provide context"*).

Residual after the fix: **10 headings**, of which **9 are false positives of the POS
tagger** (`Summary`, `Comparative`, `Viewpoint`, and the word-pair labels
`accept/except`, `affect/effect`, `lose/loose`) and 1 was a genuine miss since fixed.

**This fix does not solve the class of problem.** A hand-curated verb list cannot be
complete, and the next Style Manual edit that uses an unlisted verb will silently drop
a rule. See [Q8](05-open-questions.md#q8--should-imperative-detection-use-a-pos-tagger)
for the proposed replacement.

---

## Defects found in the pipeline while auditing

Two bugs surfaced that the audit was not looking for.

### A converter upgrade was being recorded as 537 upstream edits

Re-deriving the corpus changed every rule's content-addressed UID, because the heading
path changed. The reconciler classified all 537 as **reworded** and superseded them —
writing 537 fictional Style Manual edits into the ledger's history and discarding the
review state of rules nobody had touched.

**Fixed.** The reconciler now distinguishes:

- **reworded** — the statement text changed upstream → supersede, as before.
- **rehomed** — the statement is *identical*, only our address for it changed → migrate
  the UID in place, keep every human decision, and record the old UID in
  `derivation.uid_history`.

`Reconciliation.requires_review` excludes rehomings: nothing about them changed except
our address, so there is nothing new to review.

A related fix: when the manual repeats a statement verbatim across pages (*"Use commas
in numbers with 4 or more digits"* appears on two), lineage is resolved by page path
before the reconciler declares ambiguity. That removed 8 spurious
`needs_human_lineage_decision` entries without guessing.

### Orphaned rules vanished on rebuild

`ledger/rules.jsonl` documents that nothing is ever deleted — *"we used to flag this and
stopped"* is information. In fact an `orphaned` rule was excluded from candidate
matching and then never carried forward, so it silently disappeared on the next
rebuild, taking its review history with it.

**Fixed**, with a test (`test_terminal_rules_survive_every_rebuild`).

---

## A finding that changed nothing, deliberately

16 eligible pages are **section landing pages** (a page with a sibling directory, e.g.
`grammar-punctuation-and-conventions/punctuation.md`). Their `h2`s are navigation cards
linking to child pages, which the converter correctly renders as a link list rather
than headings.

The obvious tidy-up — excluding landing pages from eligibility — was checked before
being applied, and **would have silently dropped 30 real rules**: 6 of the 16 carry
rules alongside their navigation (`content-types/images.md` has 9,
`referencing-and-attribution/author-date.md` has 8).

Eligibility is unchanged. Recorded here because the next person to notice those pages
will have the same idea.

---

## What this audit cannot tell you

- **Precision is unverified at scale.** The audit prints every candidate for human
  reading; it cannot decide whether a heading is *genuinely* a detectable rule. That is
  the triage pass ([04-roadmap.md](04-roadmap.md)).
- **Descriptive-normative statements are still missed.** Six headings state rules as
  facts — *"A descriptive phrase doesn't need an apostrophe"*, *"A possessive pronoun
  doesn't need an apostrophe"* — and are classified as sections. Both are real,
  detectable rules. Fixing this generally risks admitting large amounts of descriptive
  prose, so it is recorded rather than patched.
- **The scraper's network path is unexercised.** Conversion, normalisation, hashing,
  changeset and reconciliation all ran for real; the fetch did not.

---

## Reproducing

```bash
# Fidelity + classification over a random sample
python -m derek.eval.audit_extraction <html-dir> 30 777

# Ledger reproducibility
python -m derek.extract.build --check

# Invariants
pytest tests/ -v
```
