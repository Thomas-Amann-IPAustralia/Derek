# Rule grain: what counts as one rule

**Status: proposed.** Drafted from the first three annotated pages (`commas.md`,
`pronouns.md`, `treaties.md`); it takes effect when a human who annotates agrees
to it. Until then it is what `derek.eval.golden_lint` checks and what the
drafting prompt ([ADR-025](02-decisions.md#adr-025--a-model-may-draft-spans-a-human-marks-them))
is told. Changing it changes that prompt's version, so an edit here invalidates
every cached draft that used the old wording, which is what should happen.

**Why this exists.** On `commas.md` the same situation, a parent heading with
child headings under it, was handled three different ways:

| Section | What was marked | Effect |
|---|---|---|
| Separate introductory words… | parent **and** both children | the same comma is flagged twice, citing two rules |
| Mark out non-essential information… | parent; two children folded into it; question tags kept separately **and** listed in the parent | question tags flagged twice |
| Punctuate sentence lists and strings of adjectives | children only | as intended |

None of those was wrong on its own; there was no rule to be consistent with. A
model will not supply one either. Without a written policy it is only
inconsistent in a different way.

---

## The test

> **One rule is one thing a checker would flag and cite.**
> If two marked rules would flag the same text for the same reason, they are one
> rule. If one marked rule would flag two unrelated things, it is two.

Everything below is that test applied to the shapes the Style Manual actually
uses.

## The policy

**G-1 · A heading that only groups its children is a section, not a rule.** Mark
the children. The parent's summary sentence is the section's introduction. The
children are more specific, and they carry their own examples, which is what a
checker is built from. *Separate introductory words, phrases and clauses with a
comma* and *Punctuate sentence lists and strings of adjectives* are sections.

**G-2 · Cases that change *when* one check applies are one rule.** If the text
lists conditions or exceptions but the violation stays the same, keep one rule
and record the cases under **When** (`preconditions`). Example: *Place commas
between principal clauses…*, where different subjects need a comma, a shared
subject doesn't, and three or more clauses do. Same violation, different
triggers.

**G-3 · A permission is an exception, not a rule.** *"You don't need a comma
after an introductory word if the sentence is very short"* and *"Sentences can
have reflexive pronouns when the subject is also the object"* can never produce
a finding, because there is nothing to violate. Record them under **When** on the
rule they relax. A permission that relaxes nothing is not marked.

**G-4 · A restatement is the rule's wording, not a second rule.** When the body
restates its heading (*"Use commas between items in a sentence list"* under
*"Separate items in lists of nouns or adjectives with commas"*), mark whichever
wording a checker could act on and put the other in the interpretation field.
Never both. If the heading is the right place but the wrong words (a label, or a
description), mark the body sentence instead.

**G-5 · Advice to the writer is not a rule about the text.** *"Check carefully"*,
*"use the Australian Treaties Database to search"* and *"follow the correct
style"* describe what a writer should do, not a property of the text. No text
violates them. Leave them unmarked.

**G-6 · A rule stated on two pages is marked once, on the page whose subject it
is.** *"Use numerals and words for large, rounded numbers"* is on `commas.md` and
`choosing-numerals-or-words.md`. It belongs to the numbers page. On the other
page, leave it unmarked and give the reason when you sweep (*"duplicate of the
rule on choosing-numerals-or-words.md"*). A per-page reader, human or model,
cannot see this, so the lint reports cross-page duplicates it can find.

## Examples

**E-1 · "Not this" is only for text the manual presents as wrong.** A contrast
pair showing two *correct* sentences with different meanings is not a violation.
*"The committee said the secretary was incompetent"* is correct English with a
different meaning, and labelling it violating teaches a classifier to flag
correct text: Octavius's polarity failure, reached by hand. Mark both sentences
as **Write this**, or leave the one that is merely different unmarked.

**E-2 · The manual's own Correct/Incorrect blocks go with the nearest rule they
test.** The nearest rule is usually the sentence directly above them, which is
not always the heading.

**E-3 · A list's lead-in and its items are one example.** Select them together
and press <kbd>⇧C</kbd> or <kbd>⇧V</kbd>.

**E-4 · A made-up threshold is an interpretation, not a reading.** *"Very short"*
becoming *"4 or fewer words"* is a reasonable decision, but it is a decision:
`clarity: ambiguous_resolvable`, with the threshold in the interpretation field,
so the next person can see it was chosen rather than read (ADR-017).
