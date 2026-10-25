# Derek: review of the extracted Australian Government Style Manual rules

**Review date:** 25 October 2026 (UTC)  
**Repository:** Thomas-Amann-IPAustralia/Derek  
**Branch:** `claude/nifty-darwin-xrufg9`  
**Commit reviewed:** `61f167cda1036a63dba3541015b5cd863c72b342`  
**Scope:** rule extraction, source fidelity, consensus, examples, applicability, activation and evaluation, assessed against the failures documented for Octavius.

## Assessment

**Derek is a substantial architectural improvement over Octavius, but its accepted ledger is not yet a validated APS rulebook. Matcher adoption should wait until the defects in source representation, semantic agreement and activation checks described below are repaired.** The present branch provides a useful point to do that: all 1,228 accepted or amended records remain non-detectable. There are no active detectors in the reviewed ledger.

The most consequential discovery is that two-model consensus can combine the source anchor for one instruction with the violation condition for another. Other confirmed defects include identical compliant and violating examples after formatting is removed, examples attached to the wrong rule, an example missing the symbol that makes it wrong, and exceptions that are not carried across pages. These are defects in the rule evidence itself; better matchers alone cannot fix them.

The activation path also has gaps. Four proposals are labelled ready even though activating their records would breach the rule schema. The runtime does not enforce most applicability metadata. Two ready proposals produce demonstrable false positives on ordinary identifier and grammatical constructions. These are **pre-activation findings**, not evidence of errors already shown to live users.

The recommended response is targeted repair and a staged release gate, preserving the corpus, provenance and declarative runtime work. Do not use the current accepted ledger as verified training labels or as an authoritative, complete compliance checklist.

## What was reviewed and how

The review combined a complete structural census of `ledger/rules.jsonl`, inspection of the snapshot and golden-span pipeline, targeted semantic comparisons between records and their source passages, inspection of the consensus and adjudication process, execution of the existing tests and checks, and in-memory matcher probes. Selected current official Style Manual pages were also checked against the relevant frozen passages.

The Octavius comparison uses the repository's postmortem and the earlier Octavius specification and presentation available in the project context. Historical Octavius totals are reported evidence, not a fresh execution of the old generated Python rules.

This is an extensive risk-based review, **not a claim that all 1,228 records have received independent human semantic certification**. Complete enumeration establishes counts and structural properties. The specific semantic findings below establish real defects, but do not estimate the overall error rate or extraction recall. No repository files were changed, no matchers adopted and no remote writes made.

All repository links below are pinned to the reviewed commit. The corpus is intentionally frozen under ADR-024, with `frozen_at` 22 September 2026. I did not perform a full live-versus-frozen comparison of all 186 pages. A controlled freeze is reasonable; it should not be described as proof that every rule reflects the latest website.

### Inventory at the reviewed commit

| Measure | Result | Meaning |
|---|---:|---|
| Snapshot pages | 186 | Entire stored corpus |
| Eligible rule-source pages | 128 | Declared extraction scope |
| Ledger records, all statuses | 1,807 | Includes history/orphans, not 1,807 operational rules |
| Orphaned records | 564 | Excluded from the accepted inventory |
| Accepted / amended | 1,227 / 1 | 1,228 records assessed as the accepted inventory |
| Other non-orphaned records | 12 rejected; 3 proposed | Not accepted |
| Accepted decisions attributed to MODELS / CLAUDE / TA | 914 / 277 / 37 | Attribution in the ledger, not independent validation |
| Accepted records marked detectable | **0** | No active detectors |
| Accepted validation status | **1,228 untested** | Acceptance does not mean tested detection |
| Accepted confidence values | **1,228 null** | Appropriate: no fabricated probability |
| Both compliant and violating examples | 174 (14.2%) | Pair availability, not proof the pairs are correct |
| Compliant examples only | 472 | Missing a negative case |
| Violating examples only | 5 | Missing a positive case |
| Neither example type | 577 | Requires other evidence before activation |
| Empty violation condition | 37 | All currently non-detectable |
| `applies_to: ["any"]` | 1,087 (88.5%) | Needs scrutiny, but is not inherently wrong |
| Clarity | 943 unambiguous; 149 resolvable; 131 deferred; 5 not automatable | Accepted inventory includes acknowledged uncertainty |
| Matcher proposals | 9 | 4 reported ready; 5 blocked |

Source: [ledger](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl), [corpus freeze](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/corpus/freeze.yaml), [proposals](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/proposals/tier0.jsonl). Golden spans contain 1,231 rule spans, 1,806 compliant-example spans, 298 violating-example spans and 3 precondition spans. Span counts and final rule/example counts are different units and should not be compared as if interchangeable.

### Checks executed

| Check | Result | What it establishes |
|---|---|---|
| `python -m pytest tests/ -q` | **347 passed**, 29 deprecation warnings | Existing software tests pass; approximately 41 seconds, Python 3.12 |
| `python -m derek.extract.build --check` | Passed | Ledger rebuild is reproducible from declared inputs |
| `python -m derek.extract.blocks --check` | Passed | Eligible-page block representation is reproducible |
| `python -m derek.eval.dogfood` | Exit 0; no accepted statically evaluable rules | No active rules to evaluate; not a zero-false-positive result |
| `python -m derek.detect.proposals` | 4 ready, 5 blocked | Current proposal criteria, which have the gaps below |
| In-memory activation/schema checks | All 4 ready records fail the detectable-rule condition because the violation condition is empty | Readiness and schema disagree |
| In-memory runtime/context probes | Unsupported scope and failed-validation record loaded and fired | Loader/execution gates are incomplete |
| Selected adversarial matcher cases | Confirmed numeric-identifier and reflexive-object false positives | Existing examples and manual-density checks miss important cases |

The 29 warnings concern Beautiful Soup/lxml deprecation and are not evidence of rule accuracy problems. The existing tests were run successfully; a green result is consistent with the semantic defects below because the suite does not test those relationships.

## What Derek has learned from Octavius

The repository-reported Octavius run produced 297,038 findings over 206,511 words, or about 1,438 findings per 1,000 words. Its own tests had passed. That is evidence of catastrophic output noise, not a statistical estimate of the false-positive rate: the manual contains deliberate negative examples and instructional discussion, and is not an infallible all-correct test document.

The README's statement that 62% of rules detected compliant patterns is stronger than the underlying count supports. Positively worded instructions were counted; that does not independently prove that every associated detector was inverted. A positive instruction such as a requirement to use numerals can legitimately be implemented as detection of an incorrect word form in a known context. Future postmortem metrics should distinguish wording, actual polarity and observed detector errors.

Derek now has useful controls: explicit page eligibility, retained source locations and hashes, reproducible rebuilding, a review ledger, separate example polarities, declarative matchers instead of executing ledger-supplied Python, null confidence until measured, and raw-output checks. These should be retained.

The remaining issue is that several intended safeguards exist as metadata or documentation without being enforced end to end. ADR-027 explicitly authorises model consensus; using that process is not itself an unauthorised departure. The question is whether its claimed agreement, human sample and activation gates are effective.

| Octavius failure | Derek's improvement | Residual risk found here |
|---|---|---|
| Rule and test generation reinforcing each other | Source-pointing examples and separate polarities | Correct source text can still be attached to the wrong predicate or lose essential formatting |
| Compliant patterns treated as violations | Explicit violation condition | Consensus can mismatch that condition and its source; 37 accepted records have none |
| Every rule applied everywhere | `applies_to`, unit and preconditions | Most metadata does not constrain runtime execution |
| Process/artifact guidance treated as text errors | Artifact exclusion and clarity categories | Dropping non-executable advice can also discard necessary precedence information |
| Self-tests mistaken for quality | Manual-density gate and review history | No independent operational accuracy estimate; no active rules in the current gate |
| Duplicate/noisy output hidden at product level | Raw findings retained | Semantic overlaps still require resolution before activation |

Sources: [Octavius postmortem](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/docs/00-postmortem-octavius.md), [decisions including ADR-027](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/docs/02-decisions.md), [rule grain](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/docs/08-rule-grain.md).

## Prioritised findings

**Priority definitions:** P0 blocks activation because an essential correctness control is absent or unsound. P1 requires repair for the affected rule family or evaluation process. P2 improves consistency, traceability or maintainability. These priorities describe readiness risk, not a live production incident.

| ID | Priority | Finding |
|---|---|---|
| R01 | P0 | Consensus can join different instructions into one accepted record |
| R02 | P0 | Formatting loss makes opposite examples indistinguishable |
| R03 | P1 | Example polarity is mistaken for relevance to a specific rule |
| R04 | P1 | A currency example omits its decisive symbol |
| R05 | P1 | Cross-page exceptions and precedence are not consolidated |
| R06 | P1 | Dropped advice leaves missing contextual dependencies |
| R07 | P0 | Readiness, adoption, schema and loader gates disagree |
| R08 | P0 | Declared applicability does not constrain detection |
| R09 | P1 | Ready numeric matcher treats identifiers as quantities |
| R10 | P1 | Ready reflexive matcher does not establish grammatical role |
| R11 | P1 | Deliberate negative examples contaminate the dogfood corpus |
| R12 | P1 | Example testing cannot preserve whole structural fixtures |
| R13 | P1 | Documented human sample approval is not enforced |
| R14 | P1 | Independent extraction and detector quality remain unmeasured |
| R15 | P2 | Duplicate and overlapping obligations remain accepted |
| R16 | P2 | Operational interpretations need separate authority and severity |
| R17 | P2 | Provenance fields and status documentation misdescribe the current process |

### R01 — Consensus can combine a source for one rule with the condition for another

**Evidence.** [Rule `5f5d3af1fd4390f5`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1233) is anchored to the instruction about placing a film's production year after its title in roman type and parentheses. Its violation condition instead checks whether a film/program/podcast/script title is italicised. [Rule `6aaf1321505299a8`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1241) reverses the mismatch: the anchor concerns title/episode typography, while the condition concerns production-year formatting and omission. The official [broadcast-media guidance](https://www.stylemanual.gov.au/referencing-and-attribution/author-date/broadcast-media-and-podcasts-film-video-television-and-radio-programs) treats these as distinct obligations.

This is a reproducible pipeline defect. [`pair_score`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/eval/draft_score.py#L124) can pair a heading and body instruction merely because they occupy the same section, or because they share an example. [`page_plan`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/tools/draft/consensus.py#L251) then chooses an anchor separately from the primary model's violation condition and preconditions. Agreement on its comparison tags does not require semantic equivalence of those fields. Reconstructing the first record showed an anchor chosen from one model and a condition taken from the other. It is also present in the generated 50-record sample.

**Consequence.** A valid source pointer proves the words exist, not that they support the assembled rule. This can misdirect implementation, explanations and later tests despite apparent two-model agreement.

**Repair and acceptance criterion.** Compare the complete obligation: subject, predicate, scope, exceptions and violation condition. Positional similarity should propose a match for review, not establish agreement. Keep facet-level provenance and adjudicate semantic disagreements. Recheck every match based on shared sections/examples and every mixed-origin record. A regression must keep the title-style and production-year obligations distinct and ensure each condition is entailed by its cited evidence.

### R02 — Formatting loss creates contradictory example labels

Three accepted records contain exactly the same string in both example arrays:

| Rule | Lost distinction |
|---|---|
| [`1608b102c229ab6f`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L556), dates | Superscript versus ordinary ordinal suffix |
| [`24477c0c3e14b538`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L738), brackets | Typography of the brackets relative to surrounding text |
| [`7aefaa812fe9f887`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L844), full stops | Whether punctuation falls inside the hyperlink |

For the date rule, both arrays contain “She will leave by the 20th.” The relevant information is formatting, so no plain-string classifier could satisfy both labels.

Loss occurs at multiple layers. [`to_markdown.py`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/corpus/to_markdown.py#L124) removes superscript/subscript markup and discards link semantics for empty or fragment-only destinations. Some distinctions survive in Markdown or annotation marks but disappear when projected into plain example strings or [`Document`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/document.py). [`normalise.py`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/corpus/normalise.py) also maps non-breaking spaces to ordinary spaces, preventing checks that need that distinction.

**Repair and acceptance criterion.** Retain plain text alongside typed formatting spans, link boundaries and relevant whitespace semantics. Declare which capabilities each rule requires. Keep unsupported formatting rules as reference knowledge until a suitable adapter exists, and exclude flattened pairs from plain-text evaluation/training. Reject identical opposite-labelled examples when their full represented context is also identical. Test source HTML through annotation, example storage, document adaptation and the evaluator—not only an intermediate parser.

Official examples: [dates](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/numbers-and-measurements/dates-and-time), [brackets](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/punctuation/brackets-and-parentheses), [full stops](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/punctuation/full-stops).

### R03 — A correctly labelled source example can still be wrong for the attached rule

[`b5b1ad77049d9ecf`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L55) concerns treating disability as an uncountable noun in generic references. It has ten violating examples, but nine do not test countability. Terms such as “mute” and “invalid” come from the broader respectful-language example set. The one compliant example, “accessible parking”, also provides little evidence about countability.

The [disability guidance](https://www.stylemanual.gov.au/accessible-and-inclusive-content/inclusive-language/disability-and-neurodiversity) covers several distinct considerations. Copying a whole negative list into every nearby rule confuses the page's judgement with the predicate being tested.

**Consequence.** A matcher would be rewarded for detecting unrelated terminology, recreating Octavius's problem of tests endorsing the wrong behaviour. A future literal blacklist could also flag legitimate non-person uses, such as an invalid identifier.

**Repair and acceptance criterion.** Validate the relation between each fixture and its rule. Record the target span and reason it violates that particular obligation; allow one example to support multiple rules only with separate explanations. Keep relevant terminology guidance as separate records with its own context and preference exceptions. The countability rule's negative fixtures should actually contain a countability error, with hard negatives for legitimate specific-condition uses.

### R04 — The currency negative example is missing the symbol that creates the violation

[`f82ab84a36ce54fe`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L543) detects a single amount labelled with both a currency symbol and a currency code. Its stored negative example includes `7.25` and `USD` but **not `$`**. The [currency source](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/numbers-and-measurements/currency) includes the symbol; the snapshot splits the example into separate blocks and the selected group omits that block.

This is not just unattractive line wrapping. The labelled fixture cannot demonstrate the stated violation because its decisive token is absent.

**Repair and acceptance criterion.** Preserve complete multi-part examples and their ordered source components. Validate semantic completeness after joining them. A regression should demonstrate that the combined-symbol-and-code version violates this rule and that the otherwise equivalent version using only one designation does not violate this particular rule. Other currency-format requirements should be assessed separately.

### R05 — Exceptions and precedence are not reconciled across pages

The accepted records contain these unresolved interactions:

| General record | Relevant qualification elsewhere | Required treatment |
|---|---|---|
| [`a34e7b35ee56b6f2`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L519): numeral form for ages/school years | [`319984e74083ba08`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L36): sentence-initial age exception | Carry the exception into the age rule's effective applicability |
| [`e5774093744d4036`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1752): expand shortened forms at first use | [`dd18e2330be0850e`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L937): qualifications for established forms | Resolve the broad instruction against the detailed shortened-form guidance |
| [`b78a9d9b2dc6eaad`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L166): alt text for images | [`8067ec35218b13f1`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L187): decorative images require an empty value | Distinguish a missing attribute from an intentionally empty value |

The shortened-form record already acknowledges deferred ambiguity; that is good documentation, but the conflict is not resolved by a linked effective rule. The decorative-image record does exist, so the problem is not a missing exception everywhere; it is the absence of an explicit relationship and common operational interpretation.

**Repair and acceptance criterion.** Add canonical obligations and typed relations such as `exception_of`, `overrides` and `same_as`, with multiple source anchors where appropriate. Test both sides of each boundary. A sentence-initial age, an established acronym in its permitted context and a decorative image with empty alt text must not receive a contradictory general-rule finding.

Official detail: [age diversity](https://www.stylemanual.gov.au/accessible-and-inclusive-content/inclusive-language/age-diversity), [acronyms](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/shortened-words-and-phrases/acronyms-and-initialisms), [image alt text](https://www.stylemanual.gov.au/content-types/images/alt-text-captions-and-titles-images).

### R06 — Dropping writer advice can remove necessary rule dependencies

On the First Nations page, consensus dispositions drop guidance about specific community names, local spelling and the precedence of community preferences as advice. Relevant item IDs include `bf8c0baf37ee`, `b5d360f557a1` and `b8c540e50ff8`. Yet accepted capitalisation records [`fd79a610d2abb679`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L24) and [`aaaf7d8631b8aac1`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L29) depend on community preference. One specification explicitly refers to a community-preference rule that is not retained as an accepted rule on the page.

The [source guidance](https://www.stylemanual.gov.au/accessible-and-inclusive-content/inclusive-language/aboriginal-and-torres-strait-islander-peoples) makes those preferences material to correct usage. Whether a checker can automate discovering the preference is a separate question from whether it must retain that authority.

**Repair and acceptance criterion.** Separate executable rules from supporting knowledge, workflow advice and precedence constraints. Do not force all guidance into detectors, but do not delete contextual dependencies simply because they cannot be detected from prose. A record needing community preference should link to that guidance and either receive the relevant context or abstain. Audit other dropped permissions, advice and restatements for dependencies before accepting their removal as harmless deduplication.

### R07 — Readiness and loading do not enforce the detectable-rule contract

All four currently ready proposals target records with an empty violation condition:

| UID | Proposal |
|---|---|
| [`c99b24f6e85c5c4a`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L763) | Commas after Latin shortened forms |
| [`8d112f931549bb88`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L771) | Thousands grouping |
| [`eecab3e2f72ea6b8`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1124) | Reflexives used as subjects |
| [`046a4193f3fe6331`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L755) | Sentence-opening strings of numbers/dates |

The [schema](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/schema/rule.schema.json#L163) requires a non-empty condition and both example types when `detectable` is true. [`check`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/proposals.py#L78) does not validate the assembled active record and does not require a compliant example. [`adopt`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/proposals.py#L160) sets detection and validation fields without performing that schema validation. [`load`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/engine.py#L43) accepts these records when their matchers are assigned in memory. It does not require validation to have passed or deferred ambiguity to be resolved. The [adoption workflow](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/.github/workflows/adopt-matchers.yml) does not run the full schema test before pushing.

**Repair and acceptance criterion.** Introduce one shared activation validator used by preview, adoption, CI and runtime loading. Validate the final record, reviewed examples, condition, required capabilities, unresolved ambiguity, current approvals and versioned evaluation evidence. Fail with explicit reasons. Assert that an empty condition, missing positive fixture, failed validation or unresolved required context cannot reach execution, even if a caller bypasses the UI. Null confidence should remain permitted for an explicitly uncalibrated release; do not replace it with an invented number.

### R08 — Applicability is recorded but not executed

[`detect`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/engine.py#L64) loops over every loaded rule and every lintable block, passing each block's text to its matcher. Apart from artifact exclusion during loading, declared unit, content type and natural-language preconditions do not constrain execution. `Document` carries no document profile or resolved context sufficient to apply those conditions.

An in-memory contract probe set a copied rule to sentence scope, social-post-only applicability, deferred ambiguity and failed validation. With a simple Latin-comma matcher, it still loaded and emitted a finding in a heading block. This was deliberately constructed to test enforcement; it is not a shipped active rule.

**Repair and acceptance criterion.** Make applicability executable. Use document/block selectors, required features and explicit context outcomes: applicable, not applicable or unknown. Unknown prerequisites should cause abstention or a review-only suggestion, not unconditional execution. Sentence, list, section and document predicates must receive those units. Rejected contexts must produce no violation, and missing capabilities should be reported as coverage limitations. The high `any` count calls for review but does not justify inventing narrower scopes for universal grammar rules.

### R09 — The ready thousands matcher flags identifiers

The real proposed matcher for [`8d112f931549bb88`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L771) produced these results in memory:

| Input | Matched text | Assessment |
|---|---|---|
| `The reference number is 12345.` | `12345` | Identifier, not a quantity to comma-group |
| `The ABN is 12 345 678 901.` | `12 345 678 901` | Identifier formatting should not be rewritten as a quantity |
| `There were 12345 applicants.` | `12345` | Appropriate candidate for the quantity rule |

The proposal already documents exclusions and incomplete coverage, including untreated bare four-digit quantities. Those caveats are useful, but its current low density on the manual does not demonstrate safety on common administrative content.

**Repair and acceptance criterion.** Distinguish quantities from identifiers before this rule runs, or limit it to contexts where quantity status is known. Include reference numbers, identifiers, standards, dates, telephone numbers and actual counts in independent fixtures. Report deliberate coverage limits. Avoid an ever-growing set of local exclusions that merely fits the manual; no claim is made here that every identifier format currently fires.

### R10 — The ready reflexive matcher confuses adjacency with subjecthood

The real proposal for [`eecab3e2f72ea6b8`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1124) flags `and myself` in both:

- `My colleague and myself travelled.` — the intended subject error.
- `I pictured him and myself dressed in red.` — a legitimate reflexive object construction.

The matcher recognises a conjunction, reflexive form and following word shape. It does not establish that the reflexive is the subject of the relevant verb. The [pronoun guidance](https://www.stylemanual.gov.au/grammar-punctuation-and-conventions/types-words/pronouns) distinguishes grammatical roles, not just local sequences.

**Repair and acceptance criterion.** Require adequate syntactic evidence, or keep the pattern as a candidate for contextual review. Include coordinated objects, participial complements, emphatic reflexives and genuine subject errors. The second sentence must not be labelled a subject-pronoun violation. Detecting its words is not enough to implement this rule.

### R11 — The manual-density corpus still includes deliberately negative material

[`example_block_ids`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/document.py#L82) recognises a small label set and selects an initial paragraph or list. It does not consistently handle alternative labels, paragraph-form labels and multi-part examples. Comparing golden violating-example anchor parts with runtime lintability found **44 of 298 parts on 15 pages** still considered lintable.

This is a representation mismatch, not 44 independently adjudicated errors: the golden labels themselves also need the semantic repairs described above. Nevertheless, source-authored negative examples must not silently contribute to a supposed clean-prose noise budget. Cases include multi-part currency material and punctuation/list examples.

**Repair and acceptance criterion.** Use a common reviewed example registry and explicit span/group boundaries for both extraction and evaluation. Expand label handling based on the corpus, with end-boundary tests. Do not solve this by excluding entire sections: the repository already documents how that approach swallowed genuine instructions beneath example headings. The evaluator should distinguish deliberate negatives, ordinary explanatory prose and ambiguous quoted material, and report denominators for each.

### R12 — Example checks discard structural relationships

[`check_examples`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/derek/detect/engine.py#L89) splits fixtures on every newline and independently asks whether any part matches. Plain-text document adaptation instead splits on blank lines, while page adaptation uses parsed blocks. A list lead-in plus its items, a multi-block currency expression or a document-level first-use condition cannot reliably be tested as a bag of independent strings.

**Repair and acceptance criterion.** Store fixtures as documents with blocks, marks, metadata and expected finding spans. Run them through the same adapter and selection path as real content. Assert both correct detection and correct scope/location. A list relationship must be tested as a list; a document-level rule must see the relevant document context. Keep fast literal unit tests, but do not treat them as adequate evidence for structural rules.

### R13 — The documented human sample gate has no enforceable approval record

ADR-027 says a human verdict on a uniform random sample of 50 consensus rules gates the batch. [`sample.json`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/golden/consensus/sample.json) records seed, population and selected records; the sample-generation path does not record reviewer verdicts, a batch-content hash or approval status that export/adoption requires. The inspected paths do not enforce the promised verdict.

This does not establish that nobody reviewed the sample elsewhere. It establishes that the repository does not contain an enforceable, reproducible approval artefact for the gate it documents. The anchor/condition mismatch in R01 is already in that sample, making the proposed review substantive rather than ceremonial.

**Repair and acceptance criterion.** Record batch/version hash, sample identities, reviewer, decisions, reasons, defects and final disposition. Invalidate approval when relevant content changes. Require that result before activation of the covered batch. Preserve the owner's chosen model-consensus process; the necessary change is an actual batch gate, not an unsupported requirement for every record to be manually recreated.

### R14 — The available evidence cannot support a rulebook accuracy claim

Only 174 accepted records have examples of both polarities, and even that subset includes the defective examples above. All accepted records are untested. The 50-rule sample, once adjudicated, can assess accepted-record quality but cannot discover obligations omitted from the ledger. Seven of the ten nominal blind pages now carry model-derived consensus annotations; the repository acknowledges this limitation. The three preserved human pages remain valuable but are a small, narrow comparison set.

The manual is used for source extraction, examples and tuning proposal density. It is therefore a regression corpus, not independent evidence of generalisation to APS documents. A zero-active-rule dogfood run is especially incapable of establishing detector precision.

**Repair and acceptance criterion.** Maintain two independent evaluations: a source-page audit measuring extraction omissions, grain, exceptions and example attachment; and realistic APS document evaluation measuring finding precision, recall, false findings per 1,000 words, coverage and abstention. Stratify across rule families and content contexts. Split by page/document, not adjacent examples, to reduce leakage. Use independent editorial adjudication, retain disagreements and report uncertainty. As a scale illustration only, zero errors in 50 independent observations still permits an error rate of about 5.8% at a one-sided 95% bound; it does not prove 99% accuracy. No such zero-error outcome is claimed here.

### R15 — Canonical duplicates and compound overlaps remain

The thousands-grouping obligation appears as [`58393f55a617cf53`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L521) and the retained human-reviewed [`8d112f931549bb88`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L771). Lower-case century terminology appears as [`7ce336763a941baa`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L586) and [`a001d1316dc627a1`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L677). Parliamentary-title records also overlap: [`0aad7c36d7cdb33a`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L378) includes obligations separately represented by [`61ac4d74adfcc3f6`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L379) and [`ff27ed43128e97bf`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L380).

**Repair and acceptance criterion.** Maintain canonical obligations with multiple source anchors and preserve historical IDs via explicit mappings. Reconcile human-marked and model-marked duplicates through review without silently overwriting the human evidence. Split compound obligations where they would produce different findings. Test that one defect yields one canonical finding. Do not collapse genuinely different citation systems or contexts merely because their wording resembles each other, and do not hide duplicates only in the product display.

### R16 — Interpretations must remain distinguishable from authoritative requirements

Some records appropriately document ambiguity, but their operational predicates can still overstate the source if later presented as hard errors. [`07e6789d0e42293c`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L181) translates an approximate alt-text length recommendation into a precise 100-character boundary. [`897e04399740a4f4`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1766) records a discrepancy between a heading and its body about adjective/noun sequences. [`aa30e9eccb829b16`](https://github.com/Thomas-Amann-IPAustralia/Derek/blob/61f167cda1036a63dba3541015b5cd863c72b342/ledger/rules.jsonl#L1774) operationalises a caution about first-person singular; its specification sensibly describes a review flag.

**Repair and acceptance criterion.** Separate source requirement, chosen operational policy and finding severity. Preserve the existing caveats and surface them in review behaviour. Approximate advice should remain advisory or configurable; unresolved source inconsistency should block a definitive compliance verdict. Test boundary values and permitted exceptions. These records need not be deleted from the inventory, but acceptance must not erase their uncertainty.

### R17 — Provenance fields and documentation need to describe the actual pipeline

Every accepted record uses `derivation.method: human_span`, including model-produced records, and every accepted record has an empty `derivation.model_decisions`. Model attribution is available elsewhere in review notes, golden seed data and draft artefacts, so provenance is not wholly absent; the standalone ledger is misleading and hard to audit mechanically.

The README also describes 736 candidates, no triage and deterministic identification from document structure, while ADR-027 and the ledger reflect the newer model-assisted process. Deterministic reconstruction from stored model decisions is a real property, but different from model-free identification of the rules.

**Repair and acceptance criterion.** Use explicit derivation provenance for human, consensus and adjudicated decisions; link model/prompt/version, anchors and adjudication IDs without relying on free-text notes. Generate status counts from the ledger. Describe separately source acceptance, executable capability, activation, validation and calibration. Publish the corpus freeze date and drift status. Reconcile the proposed rule-grain document with the policy actually used to accept/drop records.

## Remediation order and release criteria

### Stage 1 — Preserve the safe baseline and repair representations

Keep matchers inactive while repairing R01, R02, R07 and R08. Introduce the shared activation contract first so subsequent work cannot accidentally mark an incomplete record runnable. Preserve existing IDs and review history when correcting records. Implement structured examples and required-capability declarations before regenerating formatting-dependent data.

**Exit evidence:** the four currently ready proposals are blocked for their missing conditions; unsupported formatting and context-dependent rules cannot execute; all known opposite-label collisions and mixed-obligation consensus cases are covered by meaningful regression fixtures.

### Stage 2 — Rebuild semantic confidence in the ledger

Re-audit consensus pairings, rule-to-example attachments, partial examples and dropped dependency guidance. Apply cross-page exceptions and canonicalisation. Address the affected families first: typography/hyperlinks, inclusive language, numbers and dates, acronyms, lists/punctuation, and references. Do not treat the 1,228 count as a target that must be preserved; correctness may require merging, splitting, deferring or restoring records.

**Exit evidence:** each candidate for activation has an entailed condition, complete source support, relevant positive/negative examples, explicit exceptions and no unresolved overlapping obligation. Supporting advice remains available where it determines applicability. Batch human review is recorded against the exact revised content.

### Stage 3 — Establish independent performance before activating a small cohort

Define quality targets before looking at held-out results. Build an independently adjudicated source-page set for extraction and a separate document set for detection. Include ordinary administrative identifiers, legitimate grammatical constructions, document-type differences, formatting boundaries and relevant community/user preferences. Use fresh cases for final evaluation after fixing the known examples in this report.

Start with a narrow, demonstrably reliable rule cohort. Report supported rule count and estimated coverage alongside quality, so abstention is visible. Keep advisory findings distinct from confirmed breaches. Measure raw output before any display grouping, and retain rollback to the last evaluated rule version.

**Exit evidence:** reproducible held-out results with uncertainty and denominators; precision, recall and noise within the team's predetermined targets; no critical scope or polarity defect; approvals and capability checks enforced by both CI and runtime.

### Minimum acceptance-test matrix

| Area | Required passing behaviour |
|---|---|
| Consensus identity | Title italics and production-year formatting remain separate, correctly cited obligations |
| Formatting | Visually different but text-identical examples retain distinct marks; plain-text-only evaluation abstains |
| Example attachment | Countability fixtures test countability, not unrelated respectful-language terms |
| Grouped examples | Currency symbol, amount and code survive as one complete fixture |
| Exceptions | Sentence-initial age and permitted shortened forms avoid contradictory findings |
| Accessibility | Missing alt attribute and deliberately empty decorative alt value are distinguished |
| Activation | Empty condition, missing example type, failed evidence or unavailable capability blocks loading |
| Scope | A social-post condition does not execute in unrelated content; sentence checks do not judge headings indiscriminately |
| Numeric context | Identifiers are preserved while malformed quantities remain detectable |
| Grammar | Valid reflexive objects pass; genuine subject errors are caught within declared coverage |
| Evaluation corpus | Deliberately negative source examples are classified consistently and not counted as clean prose |
| Structure | List/section/document fixtures run through their actual structural scope |
| Approval | Missing or stale batch sample verdict prevents activation |
| Canonicalisation | One underlying defect produces one canonical obligation finding |

## Reproduction appendix

Run against the pinned commit in a separate checkout. The following checks are read-only with respect to the rule ledger. The normal build check may create and remove its temporary comparison file. Do not invoke the adoption command as part of reproducing this review.

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q
python -m derek.extract.build --check
python -m derek.extract.blocks --check
python -m derek.eval.dogfood
python -m derek.detect.proposals
```

### Census and contradictory strings

```python
import json
from collections import Counter
from pathlib import Path

rows = [json.loads(line) for line in
        Path('ledger/rules.jsonl').read_text().splitlines() if line.strip()]
accepted = [r for r in rows if r['review']['status'] in ('accepted', 'amended')]
print(Counter(r['review']['status'] for r in rows))
print('accepted', len(accepted))
print('detectable', sum(r['detection']['detectable'] for r in accepted))
print('empty condition', sum(not r['violation_condition'] for r in accepted))
for r in accepted:
    overlap = set(r['compliant_examples']) & set(r['violating_examples'])
    if overlap:
        print(r['uid'], sorted(overlap))
```

Expected: 1,228 accepted/amended, zero detectable, 37 empty conditions and the three R02 UIDs.

### Ready proposals versus schema and runtime

```python
import json
from copy import deepcopy
from pathlib import Path
from jsonschema import Draft202012Validator
from derek.ledger.store import load_ledger
from derek.ledger.model import Detection
from derek.detect.proposals import check, load_proposals
from derek.detect.engine import load

rules = load_ledger(Path('ledger/rules.jsonl'))
schema = json.loads(Path('schema/rule.schema.json').read_text())
validator = Draft202012Validator(schema)
for c in check(load_proposals(), rules):
    if not c.ready:
        continue
    r = deepcopy(rules[c.uid])
    p = c.proposal
    r.detection = Detection(tier=0, method=p['method'], matcher=p['matcher'],
                            detectable=True, not_detectable_reason='')
    errors = [e.message for e in validator.iter_errors(r.to_dict())]
    print(c.uid, errors, 'loaded', len(load([r]).rules))
```

Each of the four ready proposals has a schema error for its empty condition, while the current loader still loads it. Nothing is written to the ledger.

### Ready-matcher counterexamples

```python
from derek.detect.proposals import load_proposals
from derek.detect.matchers import compile_matcher

proposals = {p['uid']: p for p in load_proposals()}
cases = {
    '8d112f931549bb88': [
        'The reference number is 12345.',
        'The ABN is 12 345 678 901.',
        'There were 12345 applicants.'
    ],
    'eecab3e2f72ea6b8': [
        'I pictured him and myself dressed in red.',
        'My colleague and myself travelled.'
    ]
}
for uid, texts in cases.items():
    p = proposals[uid]
    matcher = compile_matcher(p['method'], p['matcher'])
    for text in texts:
        print(uid, text, [text[a:z] for a, z in matcher.find(text)])
```

### Context and validation enforcement probe

```python
from copy import deepcopy
from pathlib import Path
from derek.ledger.store import load_ledger
from derek.ledger.model import Detection
from derek.detect.document import Document, DocBlock
from derek.detect.engine import load, detect

r = deepcopy(load_ledger(Path('ledger/rules.jsonl'))['c99b24f6e85c5c4a'])
r.unit = 'sentence'
r.applies_to = ['social_post']
r.context_preconditions = ['Only in social media posts.']
r.clarity = 'ambiguous_deferred'
r.validation.status = 'fail'
r.detection = Detection(tier=0, method='regex',
    matcher={'pattern': r'\be\.g\.,'}, detectable=True, not_detectable_reason='')
text = 'e.g.,'
doc = Document(text, (DocBlock('h1', 'heading', 0, len(text), text),))
print([(f.block_id, f.quote) for f in detect(doc, load([r]))])
```

Current output includes `('h1', 'e.g.,')`. This synthetic probe isolates missing enforcement; it does not claim this deliberately modified record exists in the shipped ledger.

### Interpreting the existing lint report

The full golden lint run reported 2,834 observations on 113 pages: 35 `fix`, 683 `check` and 2,116 `look`. The `fix` group comprises 32 missing violation conditions in its scope and 3 unswept pages. Other large categories include 1,889 unmarked directives and 407 direction warnings. These are **triage signals, not a count of confirmed defects**. Some reflect changed policy about direction or rule grain. Reconcile the linter with ADR-027 before treating its totals as a quality score, then inspect the underlying cases.

## Decision supported by this review

Continue Derek from the existing architecture, but treat the ledger as an auditable candidate knowledge base until the stated semantic and activation gates pass. The largest risk of repeating Octavius is accepting internally consistent machinery as proof that the extracted obligations and their tests are correct. Derek has enough provenance to investigate and repair that risk now, before active detection makes it a user-facing noise problem.
