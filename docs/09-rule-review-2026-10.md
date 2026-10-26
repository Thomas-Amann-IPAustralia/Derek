# Rule review, October 2026

A review of every accepted rule in `ledger/rules.jsonl` after the consensus batch
(ADR-027) landed: 1,228 accepted or amended rules on 113 pages, read page by page against
the manual's own text, `docs/08-rule-grain.md` and the invariants in `CLAUDE.md`. The
external review in [`Derek-APS-Style-Rule-Review.md`](Derek-APS-Style-Rule-Review.md)
(R01–R17) was used as a checklist of defect classes; every finding here was checked
against the page itself, and several of its classes turned out to be far more common
than its examples suggested.

Each correction carries its reason. The reason is in the rule's review history (notes
start `[rule review 2026-10-25]`), and for a dropped rule it is also in its page's sweep
`dropped` list. The corrections were made the way the pipeline expects, not by editing
the ledger: one annotator op file,
[`golden/applied/20261025T210000Z-rule-review-20261025.jsonl`](../golden/applied/20261025T210000Z-rule-review-20261025.jsonl),
replayed through `tools/annotate/apply_spans.py`. `derek.extract.build --check` passes on
the result.

## Outcome

| | |
|---|---|
| Rules corrected | 313, on 87 pages |
| Dropped (now `orphaned`, listed in the sweep's `dropped`) | 53 |
| Rejected (human pages, where the span stays as marked) | 6 |
| Added (a rule on the page that nothing had marked) | 15, 6 of them reviving an orphaned uid with its history |
| Accepted or amended, before → after | 1,228 → 1,184 |
| Violation conditions written where there were none | 30 (the other 7 empty ones were dropped or rejected) |
| Violation conditions rewritten to match their anchor or examples | 27 |
| Direction corrected | 66 |
| Modality corrected | 44 |
| Preconditions rewritten (mostly precedence between overlapping rules) | 63 |
| Examples removed / moved to the rule they show / added from the page | 44 / 57 / 53 |
| Grouped examples split into independent ones | 111 |

`golden_lint` before → after: `fix` 35 → 3 (the 3 left are pages marked but not swept,
which is the owner's call); every D-2 (no violation condition) and G-3 (permission marked
as a rule) finding is gone; E-1 7 → 6, E-4 15 → 12, G-6 173 → 164. The ADR-006 `check`
count rose (407 → 442) because capitalisation and italics rules were moved to `presence`,
which that heuristic reads the other way (ADR-027 records this).

## What was wrong, by class

**Anchor and condition from different sentences (R01).** Consensus pairs a rule from
each model and keeps one model's anchor with the other's condition. Where the pair was
two different instructions, the accepted rule checked something its sentence does not
say. Examples fixed: the broadcast-media page, whose year-in-parentheses sentence carried
the italics condition while the radio heading carried the year condition (swapped back;
the page's italics sentence is now its own rule); `legal-material.md`, where "Always list
the legislation or case name first in a basic note" checked superscript markers;
`telephone-numbers.md`, where the foreign-number MUST absorbed the Australian-number
SHOULD; `age-diversity.md`, where the general age rule absorbed the level-of-study rule.
The pairing score (`derek.eval.draft_score.pair_score`) pairs a heading with a sentence
under it, or two rules that share examples, without requiring the two to say the same
thing; 154 pairs on accepted rules have no textual overlap. Each was read; the code is
unchanged.

**Headings dropped as restatements that were not (consensus G-4).**
`consensus._dropped_candidates` drops a heading as "restated by the kept rule" on
position alone. Six of those headings were the only statement of a rule whose examples
then hung on nothing: for example "Use words instead of symbols to improve
accessibility" (mathematical relationships, four Write this / Not this pairs
unattached), "Choose the right word and spell it correctly" (21 confusable pairs, only 9
marked), "Use respectful language" (disability), "Refer to people living in Australia as
‘Australians’". These are restored on their headings, reviving the old uid and its
review history (`derek/extract/build.py` now keeps an orphan's history when its uid is
marked again).

**One defect, two or three findings (R15, G-6).** The commonest defect. A rule stated
on a subject page is restated on an overview page (`punctuation-and-capitalisation.md`,
`full-stops.md`, `types-structure.md`, `italics.md` for legal titles,
`legal-material.md`), or a general rule overlaps a specific one (`dashes.md` and
`dates-and-time.md` on every kind of span; `hyphens.md` and `adjectives.md` on compound
adjectives; three passive-voice rules; four salutation-and-close rules for the
Governor-General). 38 copies were dropped on G-6 and 4 on R15. Where both rules are
needed, the general one now names the specific one in a precondition ("…is
dates-and-time.md's rule (8809b475eea6d34a), so it is not flagged here as well").

**Pages that disagree (R05).** Each now says which wins: `abbreviations.md`'s plural
`s` against `dates-and-time.md`'s "never add an s" to time units; `verbs.md`'s MUST
agreement against `nouns.md`'s plural verb for a collective noun; the acronyms page's
first-use exceptions against `plain-language-and-word-choice.md`'s exception-free copy
(dropped); `spelling.md` against quoted US spellings; `plain-language` against
`voice-and-tone.md` on slang; `commercial-terms.md` against `organisation-names.md` on
lower-case names; `age-diversity.md` against the sentence-opening rules.

**Examples that test another rule (R03).** 57 examples moved to the rule they show:
`Smith A.B.` and `Smith, AB` were examples of "family name before initials", which both
satisfy; the reflexive and level-of-study examples sat on neighbouring rules; the
semicolon-list examples sat on the rule that says to prefer a bullet list instead.

**Formatting the corpus does not keep (R02).** A violating example whose only fault is
a non-breaking space, superscript, a link boundary, a bullet marker or italics becomes,
flattened, an ordinary correct sentence. As a fixture it teaches a checker to flag
correct text, Octavius's polarity failure. These were removed; the compliant side is
kept for a format-aware adapter (D-13). Typical: "The People team manages the add a new
employee form." on both sides of the link-text rule; "2x2 − 2x + 12 = 161" (a
superscript note marker read as an exponent); a bullet list whose Not this differs only
in hollow bullets.

**No violation condition (D-2).** 37 accepted rules had none: 23 on `commas.md`, 5 each
on `pronouns.md` and `treaties.md`, 4 elsewhere. Four of them had a Tier 0 matcher
reported "ready to adopt" (R07). Every accepted rule now has one; the rest of the 37 were
dropped or rejected.

**Readings of tags.** Applied the same way on every page:

- *Modality.* ADR-027's settle rule (MUST only for *must, never, always, required,
  illegal, mandatory*) was applied to agreed rules as well as disputed ones. PREFER is
  used only where the text leaves the alternative acceptable (the glossary: "both are
  acceptable"), so an unhedged "X, not Y", "instead of" or "rather than" is SHOULD and an
  unhedged "Avoid" is SHOULD_NOT. A permission (MAY) is not a rule (G-3).
- *Direction.* ADR-027's rule: a wrong hyphenation, capitalisation or italics is a wrong
  form present (`presence`); a missing comma between items, a missing expansion or a
  missing element is `absence`. 13 hyphenation rules and 18 italics rules had `absence`.
- *Clarity.* A rule that can only be judged against a source the text does not carry
  ("use the original spelling of the quoted material", "add context the quotation
  needs") is `not_automatable`, like the omission rule beside it.

**Human-marked pages.** `commas.md`, `pronouns.md` and `treaties.md` were marked by the
owner before `docs/08` existed and are blind pages, so their spans are what
`draft_score` measures drafts against. A model's spans there would be scored as the
human's, so these pages were corrected with review decisions (`decide` ops: violation
conditions, tags, rejection) and the spans were left as marked. The one span edit is a
deletion: "The committee said the secretary was incompetent" was a violating example,
which `docs/08` E-1 names as the case not to mark. Six rules that `docs/08` itself uses as
examples of what is not a rule (the G-1 section heading, the G-3 permissions, the G-6
duplicates) are rejected rather than deleted. The bracketed glosses on these pages'
examples ("[Affirmative emphasis]") are left as the owner marked them.

**Not about text.** Six rules about print were dropped as `not_text`, following
ADR-027's line (page numbering and report structure stay; page sides, covers and the
publication format go): odd pages on the right, the outside cover of a bound volume,
separate ISSNs for print and digital editions, publishing a report in volumes, and two
rules about where a print line breaks a URL or a slash, which no plain-text reader can
see.

## Code

- `derek/extract/build.py`: a uid that is orphaned and then marked again keeps its
  review history and restarts as `proposed`, instead of a fresh record overwriting the
  orphan (and with it, a reviewer's acceptance).
- `derek/detect/proposals.py`: a matcher is blocked when its rule has no violation
  condition, no compliant example, or a clarity no matcher can implement (R07). The
  schema already required all three for a detectable rule; the gate did not check them.
- `derek/detect/engine.py`: the same checks when loading, so a hand-edited ledger cannot
  run such a rule either.
- `derek/detect/document.py`: the example-label vocabulary is ADR-027's census ('Avoid
  this', "Don't write", 'Write', 'Like this', 'Do this' were missing), and a label
  written as a bare paragraph opens an example as a label heading does (R11, in part).
  `golden_lint` now imports the vocabulary from here rather than keeping a copy.
- `ledger/proposals/tier0.jsonl`: the numbers matcher moved to the kept rule
  (`58393f55a617cf53`) and now fires only on a counted quantity, so reference numbers and
  ABNs stay out (R09); the reflexive matcher requires the sentence-initial subject
  position, so "I pictured him and myself dressed in red" does not fire (R10); the
  large-number matcher moved to its kept rule. Four proposals are ready; none was
  adopted, because adoption is the owner's step (D-10).

## The external review's findings

| | Status |
|---|---|
| R01 anchor and condition from different sentences | Fixed where found (see above); the pairing code is unchanged |
| R02 formatting loss | Violating fixtures removed; the root cause (NBSP and superscript dropped in `normalise.py`) is unchanged under the corpus freeze |
| R03 misattached examples | Fixed: 57 moved |
| R04 currency example missing '$' | Fixed (the split sentence is one grouped example again) |
| R05 cross-page precedence | Fixed: precedence written into the preconditions of each pair found |
| R06 dropped dependencies | Fixed: preconditions that pointed at rules that do not exist now state the dependency |
| R07 gates disagree | Fixed in the proposal gate and the loader |
| R08 applicability not enforced | Not fixed: the engine has no document type to check `applies_to` against. Needs a design decision |
| R09, R10 matcher false positives | Fixed in the proposals |
| R11 negative examples in the dogfood corpus | Partly: labels and paragraph labels. Multi-block examples (the split currency sentence) are still only partly excluded |
| R12 structural fixtures | Not fixed: design work |
| R13 sample approval not enforced | Not fixed: needs an approval artefact the export checks |
| R14 independent evaluation | Not fixed: needs an evaluation set outside the manual |
| R15 duplicates | Fixed: 42 dropped, the rest scoped by preconditions |
| R16 interpretations | The cited cases fixed (`aa30e9eccb829b16`, `897e04399740a4f4`); the broader point about authority for interpretations is a design question |
| R17 provenance | Not changed |

## Left for the owner

- **The corpus converter drops spaces at inline-markup boundaries.** Examples:
  "‘Conversational voice’,Journal of Communication", "Eades D (2013)Aboriginal ways of
  using English", "Criminal Code Act 1995.The Criminal Code", "*Legionella
  pneumophila*causes", "A man called Ove: a novel(Koch H trans)". These are in compliant
  fixtures, so they do not invert polarity, but a spacing rule would fire on them. The
  fix is in `derek/corpus/to_markdown.py` and needs the corpus unfrozen (ADR-024).
- **`derek/corpus/normalise.py`'s label sets** (`COMPLIANT_EXAMPLE_HEADINGS`,
  `VIOLATING_EXAMPLE_HEADINGS`) still lack 'Avoid this' and "Don't write". Changing them
  re-harvests heuristic candidates' examples, so it belongs with a deliberate rebuild.
- **Consensus heuristics.** The positional G-4 drop and the overlap-blind pairing
  produced most of the R01 and missing-rule defects above. Both are in
  `tools/draft/consensus.py` and `derek/eval/draft_score.py`; fixing them before the next
  batch would save the next review.
- **Glosses on the human pages** (`commas.md`, `pronouns.md`, `treaties.md`): the owner's
  spans include the manual's bracketed commentary in some examples.
- **Matchers ready to adopt:** `c99b24f6e85c5c4a`, `58393f55a617cf53`,
  `eecab3e2f72ea6b8`, `046a4193f3fe6331` (`python -m derek.detect.proposals`).
