# Choosing the alpha's rules

**Status: proposed.** A plan for picking the first cohort of rules Derek runs, written
after the owner's review of ~100 consensus rules raised the question of how many of the
1,184 accepted rules can actually be enforced. Nothing here changes the ledger. The
cohort it produces is a declared list, the way corpus eligibility is (D-4), and every
number below can be re-derived from `ledger/rules.jsonl` as of this commit.

---

## The recommendation in one paragraph

Select by **property, not by section**. A rule makes the alpha when the evidence for a
violation is inside the sentence the checker reads, two readers would agree on it, it
needs no knowledge the text does not carry, and it survives the dogfood gate. Get there in
four stages: deterministic gates on the ledger's own fields (free, no model), a
two-family batch that answers **closed factual questions** about each survivor rather
than giving it an "enforceability score", an **empirical learnability probe** on the
Tier 1 candidates, and a cohort size set by an aggregate false-finding budget rather than
a target count. Your ~100 verdicts are the test set for every automated stage: no stage's
output is used on the other ~1,080 rules until it agrees with you on yours.

---

## First, the four questions behind this

### How complex can a rule be for a classifier?

Length or wording of the rule matters much less than **where its evidence is**. The Tier 1
design is one encoder reading one sentence plus a block-type token ([ADR-019](02-decisions.md#adr-019--training-inputs-carry-no-format-markup),
[Q3b](05-open-questions.md#q3--what-should-be-encoded-in-the-classifiers-training-input)).
A rule is learnable at that grain when:

1. **The evidence is local.** Everything needed to decide is in the sentence. "Use active
   voice" passes. "Spell out an acronym at first use" fails: the first use is elsewhere.
2. **Readers agree.** Two competent readers given the rule and a sentence reach the same
   verdict. "Avoid double negatives" passes. "Write exactly what you mean" fails, and no
   amount of training data fixes that, because the labels themselves would disagree.
3. **It needs no outside knowledge.** "Italicise the names of ships" needs to know that
   *Endeavour* is a ship. The sentence does not say, so the classifier would be learning
   a list of ship names from a few hundred synthetic sentences.
4. **It is visible in plain text.** Italics, superscripts, non-breaking spaces and link
   boundaries are gone before the model sees the text (D-13). 77 accepted rules depend on
   italics alone.

A rule that fails 1 can still be Tier 0 with a structural predicate. A rule that fails 2
or 3 is not ready for anything, and should wait.

### How many rules can we reliably train?

The number of labels is not the limit. A shared encoder with a few hundred output labels
is routine ([ADR-010](02-decisions.md#adr-010--detection-tiers-and-cheapest-viable-routing)).
Two other things are the limits, and both can be estimated now.

**False findings add up across rules.** The manual averages about 17 words a sentence, so
1,000 words is about 60 sentences. If each of *N* Tier 1 rules wrongly flags a fraction
*p* of clean sentences, the raw output on clean prose is about 60 × *N* × *p* findings
per 1,000 words. Octavius scored 1,438. A budget of 2, which is noisy but usable, allows:

| Per-rule false-flag rate *p* | Rules the budget allows |
|---|---|
| 0.5% of sentences | 6 |
| 0.1% | 33 |
| 0.05% | 66 |

A 0.1% false-flag rate on clean prose is a good classifier. So the first Tier 1 cohort
is a few dozen rules at most, and it grows only as precision is measured. That is the
reason this plan sizes the cohort from a budget rather than choosing a number.

**Each rule needs human-checked training data.** The Phase 5 plan expands the manual's
examples into synthetic pairs and has a human review them in the triage app. At a few
hundred pairs a rule and a few seconds a pair, 25 rules is a working week of review, not a
month. 300 rules is not something one person can do.

### How would image metadata reach the checker?

This one is an adapter question, not a training question. ADR-019 already provides for
it: alt text and captions would arrive as their own blocks with a block-type token
(`[ALT_TEXT]`, `[CAPTION]`), from an adapter that can read them (HTML, the editor, later
Word). The classifier never needs to know where the text came from. A plain-text alpha
cannot see alt text at all, so those rules wait for that adapter. Nothing about how they
are labelled has to change in the meantime.

### How would the GUI apply only the relevant rules?

By **masking, not separate classifiers.** One forward pass scores every Tier 1 rule at
once. Tier 0 matchers run in microseconds anyway. A filter ("this is an email", "hide
referencing rules", "show MUST only") drops findings whose rule metadata
(`applies_to`, section, modality, confidence) excludes them. Training one classifier per
filter would multiply cost, and it would fragment the data each label is trained on.

There is one exception. Some context changes *what is correct*, not just whether you
care. For example, a contraction can be fine in conversational web copy and wrong in a
formal letter. A mask cannot express that. Such a rule is either split into
context-specific rules, or the context reaches the model as an input token
([Q3a](05-open-questions.md#q3--what-should-be-encoded-in-the-classifiers-training-input),
which needs an ablation). The alpha takes neither route: it admits only rules whose
context is "always" or a whole-rule on/off switch.

Two caveats carry over from the external review. Masking has to happen in the engine,
not only in the display (R08: `applies_to` is recorded but not enforced today). And rule
quality is still measured on the unmasked output (D-14).

---

## On "every rule under *Grammar, punctuation and conventions*"

It is a good instinct and a poor boundary. The numbers:

| | Accepted rules | Pass the Stage A gates below |
|---|---|---|
| Grammar, punctuation and conventions | 558 | 328 |
| Referencing and attribution | 332 | 108 |
| Accessible and inclusive content | 49 | 33 |
| Writing and designing content | 29 | 15 |
| Structuring content | 103 | 10 |
| Content types | 113 | 0 |
| **All** | **1,184** | **494** |

The section does hold two-thirds of the rules that pass the gates, so as a prior it is
right. As a boundary it is wrong in both directions:

- **It lets in about 230 rules that fail on property.** 35 depend on italics. Only 35 of
  80 titles-and-forms-of-address rules pass, and most of those still need to know who
  someone is or what office they hold. Much of *names and terms* needs to know whether a
  word names a ship, a species or a company.
- **It leaves out what the product is for.** Derek is a *plain-language* checker, and the
  plain-language rules are outside the section: active voice, double negatives,
  bureaucratic words, slang (`sentences.md`, `plain-language-and-word-choice.md`,
  `voice-and-tone.md`). So are the inclusive-language word lists ('the blind',
  'differently abled', 'ATSI', 'elderly'), which are among the cheapest and highest-value
  rules in the ledger, because most are Tier 0 literal sets.

Select by property, and use the section as a tie-breaker.

## On a Sol + Flash enforceability rating

Run a batch, yes, but do not ask for a 1–5 enforceability score. A score is an opinion
with no ground truth. Two models disagreeing about a 3 or a 4 tells you nothing, and
agreeing tells you little more. That is exactly the self-assessment loop the postmortem
warns about. Instead, ask closed questions that each have a checkable answer (Stage B),
and **measure** learnability separately (Stage C). The infrastructure is already there:
`tools/draft/batch.py` for the submission, the content-addressed cache (D-9), and the
cross-family pattern in `verify.py`.

---

## The selection procedure

### Stage A — Gates on the ledger's own fields (no model)

| Gate | Keeps | Why |
|---|---|---|
| `status` accepted or amended | 1,184 | D-10 |
| `applies_to: [any]` | 1,045 | The alpha has no document profile to check against yet (R08) |
| `unit` is token, character, phrase or sentence | 706 | What the alpha's plain-text adapter and the sentence classifier can see |
| `clarity` unambiguous or resolvable, with the assumption logged | 659 | A deferred ambiguity cannot be labelled consistently |
| Evidence is not formatting | 575 | D-13. Plain text has no italics, superscript or NBSP |
| Not about images, media, links or print | 528 | Postmortem F5; these wait for an adapter |
| No cross-sentence reference (first use, consistency) | 494 | Q3b; these are Tier 0 structural predicates, later |
| At least one example from the manual | 353 | Something to measure the probe against that no model wrote (D-1) |

Of the 494, the drafters tagged 135 as Tier 0 and 341 as Tier 1 (18 untagged).

These counts use the recorded fields for the first four gates and **keyword matches** on
the statement, violation condition and preconditions for the next three (for example
`italic|superscript|non-breaking…`). They are an estimate, good enough to size the work
but not to decide individual rules. Stage B replaces the keyword gates with recorded
answers.

The `unit` gate deliberately excludes block-level rules: headings (full stop, length,
sentence case), lists and tables. These are common, often Tier 0, and very visible to
users, but a plain-text adapter has no headings or list items. See decision 2 below.

### Stage B — Closed questions, both families, recorded as data

For each Stage A survivor, both `PAIR` models answer the same fixed questions with the
manual's page as context. The prompt is hash-pinned like the drafting prompt.

| Question | Answers |
|---|---|
| Can a reader decide from the one sentence alone? | yes · needs neighbouring sentences · needs the whole document |
| Does deciding need knowledge the text does not carry? | none · entity type (ship, species, office…) · document purpose or audience · a source being quoted |
| Does the violation survive conversion to plain text? | yes · no (names the formatting) |
| What do its preconditions amount to? | none or precedence only · a user-declared switch · inferable from the sentence · needs outside knowledge |
| Could a word list or pattern catch it? | literal set · pattern · needs judgement |
| How often would typical APS web or report content break it? | never seen · rare · occasional · common |

Agreement is taken. A difference becomes an item for you, the same way consensus items
are now. The answers are written to a selection file, one record per uid, each carrying
the models' answers and any adjudication with its reason.

**Gate on your verdicts first.** Before the answers are used on the other ~1,080 rules,
run them on the ~100 you have already reviewed. Compare "would pass Stage B" with your
keep/defer calls. If they disagree on more than about one in ten, the questions are
wrong, and they get fixed before the full batch runs. This is the step that makes the
selection defensible: an automated judgement is used only where it has been shown to
match yours.

### Stage C — A learnability probe for Tier 1 candidates

For each rule still standing and tagged Tier 1:

1. One family writes 20 realistic sentences: 10 that break the rule, 10 that come close
   but do not.
2. The **other** family judges each sentence blind, given only the rule's statement and
   violation condition.
3. The judge also classifies the manual's own *Write this* / *Not this* examples for that
   rule.

Report two numbers per rule: cross-family agreement on the synthetic set (Cohen's κ), and
the judge's accuracy on the manual's examples. Then swap the families and repeat.

The reasoning: if two frontier models from different families cannot agree on what breaks
a rule, a 150-million-parameter encoder trained on the same kind of data will not learn
it, and a user will not trust its findings. A proposed threshold is **κ ≥ 0.8 and at least
90% on the manual's examples**, to be fixed before the probe runs, not after.

This does not breach D-1. The probe selects rules; it does not validate them. Validation
is still the dogfood gate and an independent evaluation (R14). Its sentences are also the
first draft of the Phase 5 training set, so that spending is not wasted. A sentence that
two families disagree on is exactly the kind a human reviewer should see.

### Stage D — Rank by value

Order the Stage C survivors by expected prevalence. Stage B gives a modelled estimate.
The better source is the independent APS document sample that R14 asks for anyway: a few
hundred pages of real agency web content and reports, not the manual. Tier 0 matchers run
on it directly, giving a hit rate and a precision sample you can hand-check. For Tier 1
the modelled estimate stands until a classifier exists.

Break ties toward MUST/SHOULD over PREFER, and toward rules with paired manual examples.

### Stage E — Size the cohort by budget

Pick a raw-findings budget on the manual before any results are in. This plan suggests 2
per 1,000 words for the whole cohort, which is still three orders of magnitude below
Octavius. Then:

- **Tier 0:** every rule whose matcher passes the existing gates (examples, density,
  adoption by a named human, ADR-026) joins, until the Tier 0 share of the budget is
  used.
- **Tier 1:** a pilot of about 25 rules from the top of the Stage D ranking, trained and
  calibrated. Their measured false-flag rate sets how many more the budget allows. Later
  tranches of about 25 go through the same probe and the same budget.

The cohort is declared in a file, say `ledger/cohorts/alpha.yaml`: one entry per uid,
with the stage outcomes as its reason. It works the way `corpus/eligibility.yaml`
declares eligible pages. The engine loads accepted rules **that are in the cohort**. A
rule leaves the cohort by an edit with a reason, never because something else changed
upstream.

---

## "All the deterministic matchers"

Today that means 9 proposals, 4 of them ready, none adopted. The real Tier 0 pool is the
**135** Stage A survivors the drafters tagged Tier 0, plus any rule Stage B says a literal
set or pattern can catch. For those, the work is to write matchers. The existing gate
already says which survive: their own examples agree, the manual's prose stays within
budget, and a human adopts each one.

Two things from the external review must be fixed before any Tier 0 rule runs for a
user:

- **R08.** Applicability must be enforced in the engine, at least the `unit` and
  `applies_to` checks.
- **R09/R10.** "Ready" is not "safe on real documents". The thousands-separator matcher
  fires on reference numbers. The reflexive matcher fires on legitimate objects. Run every
  Tier 0 rule on the independent APS sample before adoption, not only on the manual.

---

## What the alpha leaves out, and what brings it back

| Left out | Rough count | Comes back when |
|---|---|---|
| Rules scoped to one document type | ~140 | R08 is built and the UI asks for the document type |
| Block, section and document rules (headings, lists, tables, report structure) | ~340 | A Markdown/editor adapter exposes block kinds. Many are then Tier 0 structural predicates |
| Formatting-dependent rules (italics, superscript, NBSP) | ~80 | A format-aware adapter carries marks beside the text (D-13 keeps them out of training) |
| Images, alt text, captions, video, links | ~50 | An HTML/editor adapter emits `[ALT_TEXT]`/`[CAPTION]` blocks (ADR-019) |
| Cross-sentence rules (first use, consistency) | ~35 | Tier 0 structural predicates over the `Document` |
| Rules needing outside knowledge (ships, species, offices, honours) | many of the 80 titles rules and much of names-and-terms | A gazetteer or entity list, authored as Tier 0 data, not learnt |
| Rules readers would not agree on | Stage C says | Rewritten into checkable parts (the ADR-017 table-headings pattern) |

None of these is rejected. They stay `accepted` in the ledger and simply are not in the
alpha cohort.

---

## Decisions for the owner

1. **Is the budget 2 raw findings per 1,000 words on the manual?** The cohort size
   follows from it.
2. **Does the alpha read Markdown, or only plain text?** A Markdown adapter is small. It
   would bring heading and list rules (full stops in headings, sentence case, list
   punctuation) into reach as Tier 0, and these are among the most common problems in
   real content. Recommendation: yes, as the first thing after the Stage B batch.
3. **Is referencing in the alpha?** 108 referencing rules pass Stage A, but they need to
   know that a span is a citation. Recommendation: no. Ship them later as a separate
   "citations" cohort, once there is an `is_citation` signal.
4. **The Stage C thresholds** (κ ≥ 0.8, ≥ 90% on the manual's examples), fixed before the
   probe runs.
5. **Where your ~100 verdicts live.** They are not in the repository yet. Commit them
   (export from the triage app, or the sample file with a verdict per uid) so Stage B can
   be checked against them. That also gives R13 the approval record it asks for.

## Order of work

1. Commit your ~100 verdicts. Fix R08's minimum (enforce `unit` and `applies_to`).
2. Stage A as a script that writes its funnel. Stage B on your ~100 first, then on all
   survivors.
3. In parallel: write Tier 0 matchers for the Stage A/B Tier 0 pool, and assemble the
   independent APS sample.
4. Stage C on the Tier 1 candidates. Stage D ranking. Declare `alpha.yaml`.
5. Adopt the Tier 0 cohort. Train the 25-rule Tier 1 pilot (Phase 5). Measure, then size
   the next tranche from the budget.
