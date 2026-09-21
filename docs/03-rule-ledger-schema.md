# The rule ledger

`ledger/rules.jsonl` is Derek's single source of truth about rules. One JSON object per
line, git-tracked, canonically ordered so that a semantically identical rebuild produces
no diff.

It is **not a database**. Every decision is a reviewable diff, attributable, revertable,
and it survives the review tool being rewritten
([ADR-008](02-decisions.md#adr-008-human-acceptance-is-a-gate-not-a-review-queue)).

Machine-checkable contract: [`schema/rule.schema.json`](../schema/rule.schema.json).
Python model: `derek/ledger/model.py`.

---

## The three provenance tags

These are the project's non-negotiable requirement. Every entry answers all three.

| Tag | Field | Answers |
|---|---|---|
| **1. How we arrived at the rule** | `derivation` | Which extractor, which version, what statement form, what it supersedes, and which fields a model proposed |
| **2. How it should be implemented** | `detection` | Tier, method, declarative matcher, and whether it is detectable at all |
| **3. The original rule it came from** | `source` | Page path, heading path, the manual's wording verbatim, URL, snapshot hash, line |

`source.statement` is **never edited**. An interpretation goes in `specification`
([ADR-017](02-decisions.md#adr-017-ambiguity-is-classified-and-formalised)), so the
manual's wording stays citable and the interpretation stays reviewable as an
interpretation.

---

## Field reference

### Identity

| Field | Type | Notes |
|---|---|---|
| `uid` | `string(16 hex)` | `blake2s(page_path ‖ heading_path ‖ normalised_statement)`. Deterministic ([ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity)). |
| `schema_version` | `int` | Currently `1`. |

### `source` — provenance tag 3

| Field | Notes |
|---|---|
| `page_path` | Corpus-relative, e.g. `grammar-punctuation-and-conventions/punctuation/commas.md` |
| `heading_path` | Ancestor heading chain, root first |
| `statement` | The manual's wording, verbatim |
| `url` | Live Style Manual URL |
| `body_excerpt` | Prose beneath the heading (≤1,200 chars) — the reviewer's context |
| `snapshot_sha256` | Hash of the page this was derived from; ties the rule to a corpus state |
| `line_start` | Line in the normalised page |

### `derivation` — provenance tag 1

| Field | Notes |
|---|---|
| `method` | `heading_structure` · `imperative_sentence` · `manual` |
| `extractor_version` | Bumped when extraction logic changes |
| `statement_form` | `imperative` · `negative_imperative` · `modal` · `descriptive` |
| `supersedes` | UID of the rule this replaces after an upstream rewording |
| `model_decisions` | `field → "<prompt_version>/<model_id>"`. A model-proposed value is never mistaken for a human one, and a prompt bump invalidates exactly the right entries ([ADR-003](02-decisions.md#adr-003-model-calls-are-a-cache-not-a-step)) |

### Interpretation

| Field | Values | Notes |
|---|---|---|
| `modality` | `MUST` `MUST_NOT` `SHOULD` `SHOULD_NOT` `MAY` `PREFER` | Deontic force ([ADR-016](02-decisions.md#adr-016-deontic-modality-taxonomy)). Drives severity and the dogfood budget. |
| `modality_basis` | free text | Why — e.g. `lexical cue: 'avoid'`. Shown in review so it can be overruled in one keystroke. |
| `clarity` | `unambiguous` `ambiguous_resolvable` `ambiguous_deferred` `not_automatable` | ([ADR-017](02-decisions.md#adr-017-ambiguity-is-classified-and-formalised)) |
| `specification` | free text | Formal restatement. **Detectors implement this where present.** |
| `disambiguation_log` | `[{by, at, assumption, basis}]` | Mandatory when `clarity = ambiguous_resolvable`. Schema-enforced. |

### Scope

| Field | Notes |
|---|---|
| `applies_to` | Content types, or `["any"]` |
| `unit` | `character` `token` `phrase` `sentence` `paragraph` `block` `section` `document` `artifact` |
| `context_preconditions` | Drawn from the shared context vocabulary ([ADR-015](02-decisions.md#adr-015-context-variables-chosen-by-betweenness)) |

`unit: artifact` rules (image contrast, video captions, file naming) are recorded but
**never loaded into the text runtime** — schema-enforced. Octavius applied them to prose
and they were among its worst noise sources
([postmortem F5](00-postmortem-octavius.md#f5--rules-about-artifacts-not-text)).

### Polarity — the field set that killed Octavius

| Field | Notes |
|---|---|
| `direction` | `presence` (something wrong is in the text) or `absence` (something required is missing) ([ADR-006](02-decisions.md#adr-006-presence-vs-absence-and-the-scope-requirement)) |
| `violation_condition` | **What makes text wrong.** Mandatory for detectable rules |
| `compliant_examples` | Must **never** fire |
| `violating_examples` | Must **always** fire |

Three independent guards, because one was not enough last time
([ADR-004](02-decisions.md#adr-004-polarity-is-a-first-class-schema-field)):

1. **Schema** — a detectable rule must carry `violation_condition` and both example lists.
2. **Test harness** — violating examples fire, compliant examples do not.
3. **Dogfood gate** — the rule is fired at the manual's own prose, which nobody wrote for it.

Guard 3 is the one that catches an author who has convinced themselves the wrong way round.

Seed examples come from the manual's own `Write this` / `Not this` and `Correct` /
`Incorrect` blocks — editorially authored and correctly polarised. Unlabelled `Example`
blocks are harvested but **not** assigned a polarity.

### `detection` — provenance tag 2

| Field | Notes |
|---|---|
| `tier` | `0` deterministic · `1` classifier · `2` generative · `null` undecided |
| `method` | `literal_set` `regex` `token_pattern` `length_constraint` `structural_predicate` `classifier` `none` |
| `matcher` | **Declarative data only.** The runtime never executes code from the ledger ([ADR-009](02-decisions.md#adr-009-no-generated-code-in-the-runtime)) |
| `detectable` | Gates loading |
| `not_detectable_reason` | Required when `detectable: false` |

### `validation` — deliberately separate from review

| Field | Notes |
|---|---|
| `status` | `untested` `pass` `fail` |
| `examples_pass` | Did the polarity harness pass? |
| `dogfood_density` | Findings per 10,000 words on the manual's own prose |
| `expected_density` | Budget. Default `0`; non-zero needs written justification |

Octavius conflated "tests passed" with "we decided to ship this" in a single
`test_result` field, so a frozen rule and a failing rule were indistinguishable to the
loader ([postmortem Defect 4](00-postmortem-octavius.md#3-defects-that-were-not-rule-quality-problems)).

### Confidence and review

| Field | Notes |
|---|---|
| `confidence` | Calibrated P(finding is a true violation), comparable across tiers. `null` = unvalidated, never an invented number ([ADR-013](02-decisions.md#adr-013-confidence-is-calibrated-not-raw)) |
| `review.status` | `proposed` `accepted` `amended` `rejected` `deferred` `quarantined` `superseded` `orphaned` |
| `review.history` | Every transition: from, to, by, at, note |

**Only `accepted` and `amended` load.** A rule must additionally be `detectable`, have a
method other than `none`, and not be `unit: artifact` — see `Rule.loadable`.

---

## Lifecycle

```
                    ┌──────────► rejected
                    │
  candidate ──► proposed ──► accepted ──► quarantined   (failed the dogfood gate)
                    │            │
                    ├─► deferred └──► amended
                    │
                    ├─► superseded    (statement reworded upstream; `supersedes` links them)
                    └─► orphaned      (source page removed upstream)
```

`superseded` and `orphaned` are set by `derek.extract.build` during reconciliation, never
by hand. Nothing is ever deleted: a removed rule keeps its history, because "we used to
flag this and stopped" is information.

---

## Working with the ledger

```bash
python -m derek.extract.build            # rebuild from the corpus
python -m derek.extract.build --check    # CI: fail if rebuilding would change it
python -m derek.eval.dogfood             # gate accepted rules
python -m derek.eval.dogfood --octavius reference/octavius-v1/rules_working_draft.v1.jsonl
```

```python
from pathlib import Path
from derek.ledger.store import load_ledger, loadable_rules, summarise

summarise(Path("ledger/rules.jsonl"))       # counts by review status
loadable_rules(Path("ledger/rules.jsonl"))  # what the runtime may execute
```

**Rebuilding never discards a human decision.** Reconciliation
(`derek/ledger/reconcile.py`) matches candidates to existing rules by UID, then by
statement, then by position. Anything that does not match cleanly is surfaced as
`needs_human_lineage_decision` rather than guessed — a wrong lineage silently transfers
someone's acceptance onto a rule they never saw.
