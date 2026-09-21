# Extraction hand-audit — 2026-09-21

A heading-by-heading reading of a random sample of corpus pages, checking whether
`classify_heading` makes the right call and, where it does not, which branch is wrong.

Repeatable:

```bash
python -m derek.eval.audit_headings sample 10 20260921   # trace a random page sample
python -m derek.eval.audit_headings counts               # corpus-wide census
python -m derek.eval.audit_headings modal                # every modal-branch candidate
python -m derek.eval.audit_headings gold-recall          # regression guard, exits 1 on failure
python -m derek.eval.audit_headings fronted              # imperatives behind a fronted clause
python -m derek.eval.audit_headings lexicon              # verb-list gaps and dead weight
python -m derek.eval.audit_headings octavius             # like-for-like count comparison
```

This is a different question from [06-extraction-audit.md](06-extraction-audit.md).
That one asked *did the corpus survive conversion?* — it diffed markdown against the
source DOM and found conversion clean. This one takes the corpus as given and asks
whether the **classifier** is reading it correctly.

---

## The question that prompted it

> 801 rules from an LLM against 662 from a deterministic walk. The gap is large enough
> to be suspicious of the walk.

**The gap is almost entirely an artefact of comparing different things.** Controlling
for them:

| | |
|---|---|
| Octavius working draft | 3,114 |
| — of which its own tests passed: the "801" | **801** |
| — shipped, from a page path since renamed | 30 |
| — shipped, from a page Derek declares non-normative ([ADR-005](02-decisions.md#adr-005-corpus-eligibility-is-declared-not-inferred)) | 112 |
| — **shipped, from a page Derek actually reads** | **659** |
| Derek candidates, same pages | **662** (before this audit) |

Two methods with nothing in common — one a model reading prose, one a deterministic
heading walk — landed within 0.5% of each other over the same 126 pages. The 801 was
never 801 rules about APS writing: 112 of them came from the changelog, the blog, the
handbook and *"how to cite the Style Manual"*, which is [postmortem
F3](00-postmortem-octavius.md) measured rather than asserted.

Also worth saying plainly: **801 was not Octavius's extraction count.** Octavius
extracted 3,114 and shipped the 801 whose tests passed — tests written by the same
model call that wrote the rules ([ADR-011](02-decisions.md#adr-011-the-dogfood-gate)).
The honest comparison of *extraction* is 3,114 against 662, and the 3,114 is the number
the postmortem exists to explain.

### Equal totals are not equal rulebooks

The reassuring headline hides a real disagreement. Per page, the correlation between
the two counts is only **r = 0.36**. They find the same number of rules in different
places, and the pattern is systematic:

| Page | Octavius | Derek | Why |
|---|---|---|---|
| `spelling/common-misspellings-and-word-confusion.md` | 22 | 3 | A lookup table. Octavius emitted one rule per confusable pair; Derek emits one rule whose matcher is a `literal_set` ([ADR-009](02-decisions.md#adr-009-no-generated-code-in-the-runtime)). |
| `titles-honours/royalty-vice-royalty-and-nobility.md` | 17 | 3 | Same shape: a table of forms of address. |
| `legal-material/bills-and-explanatory-material.md` | 12 | 0 | Every rule on the page is stated as a fact, not an instruction. See below. |
| `content-types/forms.md` | 9 | 29 | Rules stated as imperative headings; Octavius read the prose and missed most of them. |
| `content-types/emails-and-letters.md` | 0 | 14 | Same. |

The first two are a **counting convention**, not a recall failure, and Derek's is the
one that survives contact with [ADR-009](02-decisions.md#adr-009-no-generated-code-in-the-runtime):
22 near-identical rules with one word each is 22 chances to get polarity wrong. The
third is a real recall failure, and it is what most of this audit is about.

---

## What was read

| | |
|---|---|
| Pages sampled | **24 of 128 eligible (19%)**, three independent random samples, seeds 20260921 / 777 / 31415 |
| Headings read | **765** |
| Candidates covered | **121 (18% of the ledger)** |

Every heading was traced through the classifier branch by branch, and the branch that
decided it recorded, so a wrong answer names its own cause.

---

## Determinism: verified, not assumed

Checked directly against the corpus rather than taken from the docs.

| Claim | Result |
|---|---|
| Two runs produce identical candidates | identical (SHA-256 over uid+path+statement) |
| Extracting a page alone == extracting it in a batch | 0 of 112 pages differ |
| UIDs unique | 720 of 720 |
| `uid == blake2s(page, heading_path, statement)` | holds for every candidate |
| `normalise_text` idempotent | 186 of 186 pages |
| Heading-repair promotions | **0** across the corpus (ADR-020's self-disabling gate holds) |

No clock, no randomness, no model, no network in Layers 0–1. That part of the design is
exactly as advertised.

---

## Precision: what the 121 sampled candidates actually are

| | | |
|---|---|---|
| Sound — the heading states a rule | 91 | **75%** |
| **Label, not statement** — real rule, unusable wording | 22 | 18% |
| Not a rule at all | 8 | 7% |

### The 18%: "label, not statement"

Almost all on referencing pages, where the manual labels a citation-format subsection
with a noun phrase that happens to start with a word also used as a verb:

> *Reference list entries for films* · *Report that is part of a series* ·
> *Place of publication of a book* · *Post or article with authors listed* ·
> *Order of reference symbols* · *Address blocks*

The candidate is at the right place in the corpus — there genuinely is a rule under
each — but `source.statement` cannot be read as a rule, so `violation_condition` has to
be written from the body. Worth knowing before triage, because these are the ones where
"accept" costs four minutes rather than twenty seconds.

This is the [Q8](05-open-questions.md#q8--should-imperative-detection-use-a-pos-tagger)
noun/verb ambiguity showing up as a cost rather than as an error. A POS tagger would
resolve it; the hand-curated lexicon cannot.

### The 7%: not rules

Almost all from the **modal branch**, and specifically from `can` and `may`:

> *Nouns can be singular or plural* · *Nouns can be countable or uncountable* ·
> *Common nouns can be concrete or abstract* · *Pronouns can function as determiners* ·
> *Numbers can function as determiners* · *Decisions can differ between judges or
> magistrates* · *Voice search may be longer and more complex*

These are facts about English or about the world, not instructions about writing. Read
the whole branch with `audit_headings modal`: of its 24 candidates, roughly 8 are
solidly normative (`must`, `needs to`, and permissive rules such as *"Numeric dates can
have 2-digit elements"*), 2 are borderline, and 14 are exposition.

**Deliberately not fixed.** Narrowing the modal branch to `must`/`should`/`shall`/
`needs to` would delete *"Verbs must 'agree' with the subject"* — one of the better
rules in the ledger — unless the permissive cases were enumerated by hand, and that is
a lexicon treadmill. Fourteen candidates is about four minutes of triage, and
[ADR-008](02-decisions.md#adr-008-human-acceptance-is-a-gate-not-a-review-queue) puts a
human there precisely so extraction can afford to be generous. Recorded so the reviewer
recognises the shape on sight and rejects it without deliberating.

### Where precision is excellent

Pages that state rules as imperative headings are essentially perfect. `full-stops.md`
7 of 7, `percentages.md` 4 of 4, `lists.md` 20 of 20, `sequential-structure.md` 3 of 3,
`academics-and-professionals.md` 8 of 8 — no false positives in any of them. And the
`section` bucket is right far more often than not: its most frequent opening words are
*Accessibility* (55), *Print* (32), *Copyright* (14), *Digital* (13) — page furniture
the classifier correctly declines.

---

## Recall: the real finding

The extractor reads grammar. The Style Manual does not state every rule grammatically.

### Exhibit: `legal-material/bills-and-explanatory-material.md`

Four rule headings, **zero candidates**:

```
## Style for bill titles is roman type, title case
## Lower case is correct, unless the reference is to a specific bill
## The basic unit of a bill is a clause (cl)
## Explanatory material titles use roman type, title case
```

Every one is a real, detectable, Tier-0 rule. Every one is phrased as a description.
Octavius got 12 rules off this page — inflated, since three of them restate a single
rule about explanatory-material titles, but far from nothing.

The same page genre repeats: `cases-and-legal-authorities.md` (34 headings, 3
candidates, ~9 real rules stated as facts), `treaties.md` (9 headings, 0 candidates),
`pronouns.md` (17 headings, 0 candidates).

### Measured, not estimated

Of 796 `section` headings, **156** are four words or more and carry a normative-looking
predicate. Hand-reading a random 45 of them found **18 real rules (40%)**, which puts
the descriptive-normative class at roughly **60 missed rules corpus-wide**, ±10 at this
sample size.

Three further causes, each small and each deterministic:

| Cause | Count | Example |
|---|---|---|
| Verb absent from `imperative_verbs.txt` | ~15 | *Construct positive, unambiguous sentences* · *Vary sentence structure* · *Compare measurements using the same units* · *Space en dashes in sentences* |
| Imperative behind a fronted clause (`words[0]` cannot see it) | 10, of which 8 real | *In civil cases, use sentence case and italics for* Re *and* Ex parte |
| Imperative behind a leading adverb | ~4 | *Only use the contraction 'no' with numerals* |

`audit_headings lexicon` and `audit_headings fronted` regenerate both lists.

### The one recall figure that is not an opinion

Everything above rests on the auditor's judgement about what counts as a rule. One
measurement does not.

When the Style Manual puts a **`Write this`** beside a **`Not this`** under a heading,
its own editors have asserted that the heading governs a right and a wrong way to write
something. [ADR-011](02-decisions.md#adr-011-the-dogfood-gate) already treats those
pairs as ground truth for *evaluating* rules. So:

> **171 headings carry both polarities. The extractor recognised 113. It filed 58 as
> sections — recall 66%.**

Those 58 were not rejected. They were **never shown to a reviewer at all**, and each
one arrives with hand-authored gold examples already attached — the most valuable rules
in the corpus, invisible. Among them:

> *Noun trains are hard to understand* · *'With' is not a conjunction* ·
> *Style for Act titles is title case, not always italics* · *Construct positive,
> unambiguous sentences* · *Only use the contraction 'no' with numerals* ·
> *Some words only work with specific prepositions* · *Compare measurements using the
> same units*

---

## What changed as a result

**One change, structural, no lexicon involved.** `extract_candidates` now admits a
`section` heading as a rule candidate when the manual attached both a compliant and a
violating example block beneath it. `statement_form` records it as `exemplified`, so a
rule admitted on the manual's testimony is never mistaken for one admitted on its
wording.

```
662 candidates → 720
reconciliation: 58 added · 0 reworded · 0 rehomed · 0 orphaned
```

Strictly additive. No existing UID moved, so no review decision could have been
invalidated — and at the time of the change the queue held none.

Why this and not more verbs: growing `imperative_verbs.txt` again is the treadmill
[Q8](05-open-questions.md#q8--should-imperative-detection-use-a-pos-tagger) already
names, and the next Style Manual edit defeats it. Example-pair admission depends on no
word list at all, and it happens to recover *Construct*, *Vary* and *Compare* anyway —
the three lexicon gaps that mattered most — because the manual gave all three an
example pair.

Guarded by four tests in `tests/test_invariants.py`, and by `audit_headings
gold-recall`, which now reads 100% and **exits non-zero** if it ever does not.

**To revert:** `git revert` the commit. The ledger rebuilds to 662 with
`python -m derek.extract.build`.

---

## What is still known-broken

Recorded rather than patched, because each needs a decision rather than a fix.

1. **~60 descriptive-normative rules are still missed.** The
   `bills-and-explanatory-material.md` class. No safe deterministic test separates
   *"Style for bill titles is roman type, title case"* from *"Nouns can be singular or
   plural"* — both are present-tense statements about language. This is the strongest
   argument in the repository for [Q8](05-open-questions.md#q8--should-imperative-detection-use-a-pos-tagger),
   and the case is now quantified rather than anecdotal.
2. **Imperatives behind a fronted clause (8 real rules).** A `^<clause>,\s+<verb>`
   test would recover them at a cost of 2 noun false positives. Cheap, but it is a
   deliberate loosening of a branch that has been kept strict on purpose, so it is
   offered rather than taken.
3. **The modal branch's 14 exposition candidates.** Left in; see above.
4. **The 18% "label, not statement" cost is unavoidable at heading granularity.**
   [ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity) makes the
   heading the rule's identity. Where the manual uses a noun-phrase label, the rule
   text lives in the body and a human has to write `specification`. That is
   [ADR-017](02-decisions.md#adr-017-ambiguity-is-classified-and-formalised) working as
   designed, but it is slower than the 20-seconds-per-rule the roadmap budgets.

---

## Verdict

The extraction methodology is **sound where it claims to be sound** and **honest about
where it is not**.

- Determinism, purity and reproducibility: verified independently, no caveats.
- Precision: ~75% clean, ~18% right-place-wrong-wording, ~7% not rules. All three land
  in front of a human before anything loads ([D-10](../CLAUDE.md)).
- Recall: the weak axis. Good on imperative pages, poor on descriptive ones, and the
  gap is a property of *how a page is written*, not a random error rate.

The count was never the thing to be suspicious of. **662 was almost exactly what
Octavius found on the same pages**, and the difference from 801 is pages Octavius
should not have been reading. What deserved suspicion — and got it — was the 58 rules
with gold examples attached that the classifier never showed anyone.
