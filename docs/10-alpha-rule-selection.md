# Choosing the alpha's rules

**Status: proposed, with the owner's first decisions recorded (2026-10-26).** A plan for
picking the first cohort of rules Derek runs. It was written after the owner's review of
~100 consensus rules raised the question of how many of the 1,184 accepted rules can
actually be enforced. Nothing here changes the ledger. The cohort it produces is a
declared list, the way corpus eligibility is (D-4). Every count below can be re-derived
from `ledger/rules.jsonl` as of the commit that last changed this file.

---

## The recommendation in one paragraph

Select by **property, not by section**. A rule makes the alpha when:

- the evidence for a violation is inside what its detector reads;
- two readers would agree on it;
- it needs no knowledge the text does not carry;
- it survives the dogfood gate.

There are four stages to get there:

1. Deterministic gates on the ledger's own fields. These are free and need no model.
2. A two-family batch that answers **closed factual questions** about each survivor,
   instead of giving it an "enforceability score".
3. An **empirical learnability probe** on the Tier 1 candidates.
4. A cohort size set by an aggregate false-finding budget, not a target count.

The owner's verdicts on a random sample are the yardstick for every automated stage. No
stage's output is used on the rest of the ledger until it agrees with the owner on the
sample.

## Decisions so far

| | Decision | Effect |
|---|---|---|
| Findings budget | **Lower than 2 per 1,000 words.** Provisionally 0.5, see below | A smaller Tier 1 pilot; the alpha leans on Tier 0 |
| Input format | **Markdown** | Headings, lists, tables, links and italics become visible. See [Markdown](#markdown-and-what-it-brings-into-reach) |
| Referencing and attribution | **Cut from the alpha** | 332 rules out of the population; a later "citations" cohort |
| Yardstick | **200 rules drawn at random**, plus the ~100 reviewed on 2026-10-25 | `golden/selection/yardstick.json`, drawn by `tools/select/yardstick.py` |

---

## The questions behind this

### Does a classifier rule have to fit in one sentence?

No. An earlier draft of this document said it did, and that overstated the case. The
sentence-only input is a **current choice**, not a law. [Q3b](05-open-questions.md#q3--what-should-be-encoded-in-the-classifiers-training-input)
recommended it as the place to start, and [ADR-010](02-decisions.md#adr-010--detection-tiers-and-cheapest-viable-routing)
routes document-global rules to Tier 0 or defers them. Both can be revisited. There are
three windows a classifier can read:

| Window | Handles | Costs |
|---|---|---|
| **The sentence** (+ block-type token) | Word choice, voice, punctuation, local grammar | Cheapest data (sentence pairs); milliseconds on a CPU |
| **The sentence and its neighbours**, or the paragraph | "The table below", pronoun reference, a list and its lead-in | Somewhat longer inputs; examples need their context sentences |
| **The whole document** | Structure, emphasis, "most important information first" | See below |

**A whole-document classifier is possible.** ModernBERT reads up to 8,192 tokens, about
6,000 words, so most APS web pages fit in one pass, and it can mark spans anywhere in
what it reads. The real costs are elsewhere:

- **Training data.** Every example becomes a whole document with **every** violation of
  every rule labelled. A violation left unlabelled teaches the model that it is fine. A
  sentence pair takes seconds to check. A labelled document takes minutes, and it has to
  be checked for every rule at once.
- **Fewer examples, harder learning.** Each document is one example. The model has to
  find the few tokens that matter among thousands, from far fewer examples.
- **Latency.** Seconds rather than milliseconds on a free-tier CPU. That is fine for a
  document checker, and too slow for checking as someone types.

**There are two kinds of document-level rule.**

- **Exact relations.** Examples are "spell out an acronym at first use", "use one
  spelling consistently", "don't skip heading levels" and "number figures in order". A
  deterministic predicate over the `Document` gets these right every time. Neural models
  are unreliable at *first*, *same as* and *in order*. These belong in Tier 0 whatever
  the classifier can read.
- **Judgements about the whole.** Examples are "put the most important information
  first" and "use a tone suited to the audience". These do need a model with the whole
  document. They are also the rules readers agree on least.

So the property that matters is **the evidence is inside the window its detector
reads**. The window is chosen per rule. For the alpha:

- Tier 0 predicates may read the whole document.
- The classifier reads the sentence, plus its neighbours where a rule needs them.
- A whole-document model is an experiment after the alpha pilot. It goes ahead if the
  pilot shows that the rules needing it are worth the labelling cost.

The other three properties still hold, whatever the window:

- **Readers agree.** If two careful readers disagree on whether a sentence breaks "Write
  exactly what you mean", the labels disagree too, and no model can be trained past
  that.
- **No outside knowledge.** "Italicise the names of ships" needs to know that
  *Endeavour* is a ship. A list of ships belongs in Tier 0 data, not in what a model
  learns from synthetic sentences.
- **Visible in the input.** Markdown now decides this. See below.

### How many rules can we reliably train?

The number of labels is not the limit. A shared encoder with a few hundred output labels
is routine ([ADR-010](02-decisions.md#adr-010--detection-tiers-and-cheapest-viable-routing)).
Two other things are the limits.

**False findings add up across rules.** The manual averages about 17 words a sentence, so
1,000 words is about 60 sentences. Suppose each of *N* classifier rules wrongly flags a
fraction *p* of correct sentences. Then the raw output on clean prose is about
60 × *N* × *p* findings per 1,000 words. Octavius scored 1,438.

| Per-rule false-flag rate *p* | Rules allowed at budget 2 | at **0.5** | at 0.25 |
|---|---|---|---|
| 0.5% of sentences | 6 | 1 | 0 |
| 0.1% | 33 | 8 | 4 |
| 0.05% | 66 | 16 | 8 |
| 0.02% | 166 | 41 | 20 |

The owner wants fewer than 2. This plan takes **0.5 raw findings per 1,000 words of the
manual, across the whole cohort**, until a measurement argues otherwise. In practice
that means three things:

- Tier 0 rules have to be at or near zero on the manual. That is already the default
  budget for MUST rules in [ADR-011](02-decisions.md#adr-011--the-dogfood-gate).
- The Tier 1 pilot is **10 to 15 rules**, not 25.
- More rules come in only as precision improves. The budget is fixed; the cohort is
  sized to fit it.

The budget is measured on the manual because the manual is the only text known to be
correct. On real APS documents, true findings come on top of it. The independent
document set (Stage D) measures precision there.

**Each rule needs human-checked training data.** Phase 5 expands the manual's examples
into synthetic pairs, which a human reviews in the triage app. At a few hundred pairs a
rule and a few seconds a pair, 15 rules is a few days of review. 300 rules is not
something one person can do.

### How would image metadata reach the checker?

This is a question for the input adapter, not for training. ADR-019 already provides for
it: alt text and captions arrive as their own blocks with a block-type token
(`[ALT_TEXT]`, `[CAPTION]`). The classifier never needs to know where the text came from.

Markdown can carry alt text (the bracketed text in an image link), so a Markdown adapter could expose it. But
**the alpha leaves image rules out anyway.** Most of them are about whether the alt text
suits the image, and the checker cannot see the image.

### How would the GUI apply only the relevant rules?

By **masking, not separate classifiers.** One forward pass scores every Tier 1 rule, and
Tier 0 matchers run in microseconds. A filter drops findings whose rule metadata
(`applies_to`, section, modality, confidence) excludes them. Examples are "this is an
email", "hide citation rules" and "show MUST only". A classifier per filter would
multiply the cost and split the training data each label learns from.

There is one exception: context that changes *what is correct*, not just whether you
care. A contraction can be fine in conversational web copy and wrong in a formal letter.
That rule is either split into context-specific rules, or the context reaches the model
as an input token ([Q3a](05-open-questions.md#q3--what-should-be-encoded-in-the-classifiers-training-input)).
The alpha admits only rules whose context is "always" or a whole-rule on/off switch.

Two caveats carry over from the external review:

- Masking has to happen in the engine, not only in the display. Today `applies_to` is
  recorded but not enforced (R08).
- Rule quality is still measured on the unmasked output (D-14).

---

## Markdown, and what it brings into reach

**Yes, Markdown captures italics.** It also carries bold, links, headings, lists and
tables. Two rules keep this from breaking anything that is already settled:

- **The classifier still never sees markup** ([ADR-019](02-decisions.md#adr-019--training-inputs-carry-no-format-markup), D-13).
  The adapter splits Markdown into plain text plus **marks**: spans tagged `em`,
  `strong`, `code` or `link` as offsets into the text. `derek/extract/blocks.py` already
  does exactly this for the manual (its `Mark` and `_inline`), so the alpha's adapter
  reuses it rather than inventing a second parser. Tier 0 matchers can ask "is this span
  emphasised?". The classifier reads the same plain text it always would.
- **Only some formatting survives.** Markdown has no superscript, small caps, underline
  or colour. A non-breaking space survives only if the author typed the character.
  Rules about those stay out.

**Italics rules.** Markdown makes the mark visible. It does not tell the checker what
*should* be italic. Of the 22 italics rules that pass the other gates, a few can be
decided from the mark and the words alone:

- a Latin shortened form in italics;
- "HMAS" inside an italicised ship name;
- an italicised plural of a single letter;
- italics across a whole paragraph.

The rest need to know that something names a ship, a species or a published work. That
is outside knowledge, and those rules wait.

**Other rules Markdown brings in.**

- Headings: no full stop, sentence case, 70 characters or fewer, no questions.
- List punctuation and lead-ins.
- Link text, such as "click here".
- Table headers.

Most of these are Tier 0, and they are among the most common problems in real content.
58 block- and paragraph-level rules pass the gates below that a plain-text alpha would
have excluded.

**For people writing in Word.** Their documents need converting to Markdown in a way
that keeps italics, for example with pandoc. The Word adapter proper is still deferred
([ADR-012](02-decisions.md#adr-012--format-independent-document-model)).

---

## On "every rule under *Grammar, punctuation and conventions*"

The owner proposed taking the alpha's rules from this section. It is a good instinct but
a poor boundary. It holds 558 of the 1,184 accepted rules, and about two-thirds of the
rules that pass the property gates. As a boundary it is wrong in both directions:

- **It lets in about 230 rules that fail on property.**
  - Of the 80 rules on titles and forms of address, many need to know who someone is or
    what office they hold.
  - Much of *names and terms* needs to know whether a word names a ship, a species or a
    company.
  - Most of its 35 italics rules have the same problem.
- **It leaves out what the product is for.** Derek is a *plain-language* checker, and the
  plain-language rules are outside the section:
  - active voice, double negatives, bureaucratic words and slang (`sentences.md`,
    `plain-language-and-word-choice.md`, `voice-and-tone.md`);
  - the inclusive-language word lists ('the blind', 'differently abled', 'ATSI',
    'elderly'). These are among the cheapest high-value rules in the ledger, because
    most are Tier 0 literal sets;
  - with Markdown, the heading, list and link rules in *Structuring content*.

Select by property, and use the section as a tie-breaker.

## On a Sol + Flash enforceability rating

The owner suggested a batch run asking Sol and Flash to rate enforceability. Run one,
but do not ask for a 1–5 score. A score is an opinion with no ground truth: two models
disagreeing about a 3 or a 4 tells you nothing, and agreeing tells you little more.
Instead, ask closed questions that each have a checkable answer (Stage B), and
**measure** learnability separately (Stage C).

The infrastructure is already there:

- `tools/draft/batch.py` for the submission;
- the content-addressed cache (D-9);
- the cross-family pattern in `verify.py`.

---

## The selection procedure

### The yardstick

`tools/select/yardstick.py draw` drew 200 rules uniformly at random (seed
`alpha-yardstick`). The population is every accepted or amended rule outside
`referencing-and-attribution/`, less the 50 in the ADR-027 human check: **817 rules**.
The owner marks each one in the alpha, not yet, or unsure. Reasons come from a closed
list that mirrors the Stage B questions, so the owner's reasons and the models' answers
can be compared one for one.

The verdicts are recorded in `golden/selection/verdicts.jsonl`. With the ~100 reviewed
on 2026-10-25, they are the test set for Stages A and B.

**Why 200, and why random.** With 300 verdicts, an automated stage that agrees with the
owner on 90% of them has a 95% interval of roughly 86–93%. With 50, it would be 78–96%,
which is too wide to act on. A sample chosen by hand would measure agreement on the
rules that were easy to choose.

### Stage A — Gates on the ledger's own fields (no model)

| Gate | Keeps | Why |
|---|---|---|
| Accepted or amended, outside referencing | 852 | D-10; referencing cut |
| `applies_to: [any]` | 717 | No document profile to check against yet (R08) |
| `unit` is not document, section or artifact | 624 | Block-level is in reach with Markdown; whole-document predicates come later |
| `clarity` unambiguous or resolvable, with the assumption logged | 570 | A deferred ambiguity cannot be labelled consistently |
| Evidence is not formatting Markdown lacks | 537 | D-13; no superscript, small caps, underline or colour |
| Not about images, media or print | 493 | Postmortem F5; the image itself is not visible |

Of the 493, the drafters tagged 118 as Tier 0 and 352 as Tier 1 (23 untagged).

The first four gates use recorded fields. The last two are **keyword matches** on the
statement, violation condition and preconditions. Treat those two as an estimate for
sizing the work, not a decision on any single rule. Stage B replaces them with recorded
answers, and the yardstick says whether the gates themselves cut where the owner would.

### Stage B — Closed questions, both families, recorded as data

For each Stage A survivor, both `PAIR` models answer the same fixed questions, with the
manual's page as context. The prompt is hash-pinned like the drafting prompt.

| Question | Answers |
|---|---|
| What must a reader see to decide? | the sentence · nearby sentences · the whole document |
| Does deciding need knowledge the text does not carry? | none · what something is (ship, species, office…) · document purpose or audience · a source being quoted |
| Is the evidence visible in Markdown? | yes · no (names the formatting) |
| What do its preconditions amount to? | none or precedence only · a user-declared switch · inferable from the text · needs outside knowledge |
| Could a word list or pattern catch it? | literal set · pattern · structural predicate · needs judgement |
| How often would typical APS web or report content break it? | never seen · rare · occasional · common |

Agreement is taken. A difference becomes an item for the owner, the same way consensus
items are now. The answers go to a selection file with one record per uid. Each record
carries both models' answers and any adjudication with its reason.

**Run it on the yardstick first.** Run Stage B on the yardstick's 300 rules before the
other ~500. Compare its implied verdict with the owner's, overall and reason by reason.
If they disagree on more than about one rule in ten, change the questions, not the
threshold, and rerun. This is what makes the selection defensible: an automated judgement
is used only where it has been shown to match the owner's.

### Stage C — A learnability probe for Tier 1 candidates

This stage asks one question of each rule: **can its violations be told apart reliably
by someone who has only the rule?** If two strong models from different families cannot
do it, a small classifier trained on similar data will not either. Nor would a user
trust its findings.

**How it runs, for one rule.** Take "Avoid double negatives":

1. **Write.** Sol writes 20 realistic APS-style sentences. Ten break the rule ("It is
   not uncommon for applicants to not receive a reply"). Ten come close but do not
   ("Applicants who do not reply will not be contacted again", which has two negatives
   but is not a double negative). The near misses matter most. They are where a
   classifier would produce false flags.
2. **Judge blind.** Flash sees only the rule's statement and violation condition, plus
   the 20 sentences in random order, with no labels. It answers "breaks the rule" or "does
   not" for each one.
3. **Judge the manual's own examples.** Flash also classifies the rule's *Write this*
   and *Not this* examples from the manual. No model wrote these, so they are the one
   part of the test with an independent answer key (D-1).
4. **Swap.** Flash writes and Sol judges. Every rule gets 40 synthetic judgements across
   both directions.

**The two numbers, and what they mean.**

- **κ (Cohen's kappa) between writer and judge on the synthetic sentences.** κ measures
  agreement after removing what chance alone would give. With half the sentences
  violating, a judge who guessed would agree about 50% of the time; κ counts that as 0.
  κ = 1 is perfect agreement, and κ = 0.8 is about 90% raw agreement on a balanced set.
  In annotation work, 0.8 is the usual line for "reliable enough to train on". Below
  about 0.6, the label itself is in doubt.
- **The judge's accuracy on the manual's examples.** This checks the rule's own
  wording. A rule whose statement does not let a reader recognise the manual's own
  examples is badly specified, whatever the synthetic score says.

**The proposed thresholds: κ ≥ 0.8 in both directions, and at least 90% on the manual's
examples** (where a rule has at least four of them).

- **Passes:** goes on to Stage D.
- **0.6 ≤ κ < 0.8:** rewrite. Look at the sentences the models disagreed on. They usually
  show a missing exception or a vague term. Fix the rule's specification, as ADR-017
  does for the table-headings rule, and probe again once.
- **κ < 0.6:** not yet. Record the disagreements as the reason.

**Why the thresholds are fixed before the probe runs.** If the line is drawn after the
results are seen, it can be drawn to admit whichever rules someone hoped for. That is
the same self-confirming loop as Octavius's tests, which were written by the call that
wrote the rules. Fixing the numbers first makes the probe a test, not a justification.

**What this costs and saves.** About 40 short generations and 40 short judgements per
rule, batched, for the 352 Tier 1 candidates after Stages A and B trim them. The
sentences are not wasted. Those both families agree on are the first draft of the Phase
5 training set. Those they disagree on are exactly the ones a human reviewer should see.

This does not breach D-1. The probe *selects* rules; it does not validate them.
Validation is still the dogfood gate and the independent evaluation (R14).

### Stage D — Rank by value

Order the Stage C survivors by expected prevalence. Stage B gives a modelled estimate.
The better source is the independent APS document set that R14 asks for anyway: a few
hundred pages of real agency web content and reports, in Markdown, not the manual.

- Tier 0 matchers run on it directly. This gives a hit rate, and a precision sample the
  owner can hand-check.
- For Tier 1, the modelled estimate stands until a classifier exists.

Break ties toward MUST/SHOULD over PREFER, and toward rules with paired manual examples.

### Stage E — Size the cohort by budget

- **Tier 0:** every rule whose matcher passes the existing gates joins, as long as its
  density on the manual is near zero. The gates are: its own examples agree, the
  manual's prose stays within budget, and a named human adopts it (ADR-026).
- **Tier 1:** a pilot of 10–15 rules from the top of the Stage D ranking, trained and
  calibrated. Their measured false-flag rate sets how much more the budget allows.
  Later tranches go through the same probe and the same budget.

The cohort is declared in a file, say `ledger/cohorts/alpha.yaml`. It has one entry per
uid, with the stage outcomes as its reason, the way `corpus/eligibility.yaml` declares
eligible pages. The engine loads accepted rules **that are in the cohort**. A rule
leaves the cohort only by an edit with a reason, never because something upstream
changed.

---

## "All the deterministic matchers"

Today there are 9 proposals, 4 of them ready and none adopted. The real Tier 0 pool is
larger:

- the **118** Stage A survivors the drafters tagged Tier 0;
- any rule Stage B says a literal set, a pattern or a structural predicate can catch;
- the exact document-level relations above (first use, consistency), as structural
  predicates.

For all of these, the work is to write matchers. The existing gate already decides which
survive.

Two things from the external review must be fixed before any Tier 0 rule runs for a
user:

- **R08.** Applicability must be enforced in the engine, at least the `unit` and
  `applies_to` checks.
- **R09 and R10.** "Ready" is not the same as "safe on real documents". The
  thousands-separator matcher fires on reference numbers. The reflexive matcher fires on
  legitimate objects. Every Tier 0 rule runs on the independent APS set before it is
  adopted, not only on the manual.

---

## What the alpha leaves out, and what brings it back

| Left out | Rough count | Comes back when |
|---|---|---|
| Citation and referencing rules | 332 | A "citations" cohort, with a signal that marks a span as a citation |
| Rules scoped to one document type | ~135 | R08 is built and the UI asks for the document type |
| Document and section rules that need a model (structure, inverted pyramid) | ~90 | A whole-document classifier, if the pilot justifies its labelling cost |
| Formatting Markdown lacks (superscript, small caps, NBSP) | ~35 | A format-aware adapter (Word, the editor) |
| Images, alt text, captions, video, print | ~45 | An adapter that can describe the image, which is not on the roadmap |
| Rules needing outside knowledge (ships, species, offices, published works) | Stage B says | A gazetteer or entity list, authored as Tier 0 data |
| Rules readers would not agree on | Stage C says | Rewritten into checkable parts (the ADR-017 pattern) |

None of these is rejected. They stay `accepted` in the ledger. They are simply not in
the alpha cohort.

---

## Still to decide

1. **The budget's number.** 0.5 is provisional. At 0.25 the Tier 1 pilot is about 4–8
   rules, which may be too few to learn anything from.
2. **The Stage C thresholds**, fixed before the probe runs. The proposal is κ ≥ 0.8 both
   ways, and at least 90% on the manual's examples.
3. **The 2026-10-25 verdicts.** The ~100 rules the owner reviewed are not in the
   repository. Only the 50 drawn into `golden/consensus/sample.json` are known by uid,
   and their verdicts are not recorded. Committing them (`yardstick.py record`) adds
   them to the yardstick, and gives R13 the approval record it asks for.

## Order of work

1. The owner marks the 200 yardstick rules. Commit them and the 2026-10-25 verdicts.
2. In parallel: the Markdown `Document` adapter (reusing `blocks.py`'s marks), and the
   minimum of R08.
3. Stage A as a script that writes its funnel, checked against the yardstick.
4. Stage B on the yardstick, then on all survivors. Write Tier 0 matchers for the pool,
   and assemble the independent APS set.
5. Stage C on the Tier 1 candidates, then the Stage D ranking. Declare `alpha.yaml`.
6. Adopt the Tier 0 cohort. Train the 10–15 rule Tier 1 pilot (Phase 5). Measure it,
   then size the next tranche from the budget.
