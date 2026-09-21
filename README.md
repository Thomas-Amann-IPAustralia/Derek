# Derek

A plain-language compliance system for Australian Public Service content, built on the
[Australian Government Style Manual](https://www.stylemanual.gov.au/).

Derek finds text that breaks a style rule, flags it with a calibrated confidence, and
lets the user keep the original or accept a change. It is the successor to **Octavius**.

> **Read [`docs/00-postmortem-octavius.md`](docs/00-postmortem-octavius.md) first.**
> Octavius shipped 801 rules that, fired at the Style Manual's own professionally-edited
> prose, raised **1,438 findings per 1,000 words** — roughly 1.4 violations per word on
> text that is by definition correct. Every rule passed its own test suite. Most of
> Derek's design is a direct response to a specific, documented failure there, and the
> postmortem says which.

---

## What is different this time

| | Octavius | Derek |
|---|---|---|
| Rule inventory | LLM proposed 3,114 "rules" from 181 pages | Read deterministically off document structure |
| Heading fidelity | `trafilatura` flattened levels; structure was guessed back | Levels taken from the source DOM |
| Reproducibility | Re-running produced a different rulebook | Byte-identical across runs; CI-enforced |
| Polarity | No field for it; 62% of rules detected the compliant pattern | `violation_condition` + separate compliant/violating examples, guarded three ways |
| Test data | Model-generated alongside the rule it tested | **489 gold sentences** harvested from the manual's own *Write this* / *Not this* blocks |
| Quality gate | None; product-level suppression hid the problem | Dogfood gate on raw output, in CI |
| Human review | 3,114 rows, reviewed after the fact | Nothing loads until a human accepts it |
| Rules | Model-generated Python, `exec()`d with full builtins | Declarative data from a closed matcher vocabulary |
| Change detection | Trusted the sitemap's `lastmod`; never noticed removals | Content hashes, weekly full re-hash, explicit add/alter/remove changesets |

---

## Status

Foundations built; no rules reviewed yet — by design.

| | |
|---|---|
| Offline Style Manual snapshot | 186 pages |
| Eligible rule-source pages | 128 |
| Deterministic rule candidates | **661** |
| With hand-authored gold examples | 366 (55%) |
| With *paired* compliant + violating examples | 83 |
| Gold example sentences | 520 |
| Accepted into the runtime | **0** |

Built and tested: the snapshot layer (content-addressed, with add/alter/remove
changesets), deterministic extraction, the rule ledger, the dogfood gate, and the
triage UI. 67 invariant tests pass.

Not yet done: the snapshot has not been run against the live site from this repository,
and **no rule has been triaged**. The first triage pass is the next task — see
[`docs/04-roadmap.md`](docs/04-roadmap.md).

---

## Quick start

```bash
pip install -r requirements.txt

# Rebuild the rule ledger from the corpus (deterministic, no model calls)
python -m derek.extract.build

# Prove reproducibility — fails if rebuilding would change the ledger
python -m derek.extract.build --check

# Fire accepted rules at the Style Manual's own prose
python -m derek.eval.dogfood

# Triage rules — keyboard-first: A accept, R reject, D defer, N not-text
python tools/review/server.py

# Refresh the offline snapshot (needs requirements-pipeline.txt)
python -m derek.corpus.snapshot --sweep-slice 0

# Reproduce the Octavius postmortem figures
python -m derek.eval.dogfood --octavius reference/octavius-v1/rules_working_draft.v1.jsonl

pytest tests/ -v
```

---

## How it works

```
  stylemanual.gov.au
        │  Layer 0 — SNAPSHOT        content-addressed; add/alter/remove changesets
        ▼
  corpus/pages/**.md
        │  Layer 1 — EXTRACTION      pure function of the corpus; no model
        ▼
  661 candidates (stable uid, statement, heading path, gold examples)
        │  Layer 2 — INTERPRETATION  model proposes, human decides
        ▼
  ledger/rules.jsonl
        │  Layer 3 — DETECTION       accepted rules only
        ▼
  Tier 0 deterministic · Tier 1 classifier · Tier 2 generator (deferred)
        │  Layer 4 — INTERFACES
        ▼
  HTTP · MCP · CLI · LLM middleware · review UI
```

Each layer is reproducible from the one below it. Full detail in
[`docs/01-architecture.md`](docs/01-architecture.md).

### Rules are read off the document, not invented

The Style Manual states its rules as headings, and publishes them with a clean outline
(`h1` page title → `h2` section → `h3` rule → `h4` example block):

```markdown
### Place a comma after adverbs and other introductory words
### Use a comma after phrases and clauses that change the whole sentence
### Avoid beginning a sentence with a string of numbers and dates
```

So the rule inventory is a pure function of the corpus. A model may later classify or
formalise a candidate; it may never decide that one exists. That is what makes
"two runs extract the same rules" true by construction rather than by hope.

This only works if the conversion preserves those levels. Octavius used `trafilatura`,
which flattens them, so 71% of its structure had to be guessed back by a heuristic.
Derek reads the levels from the DOM instead
([ADR-020](docs/02-decisions.md#adr-020-heading-levels-come-from-the-dom)).

### The manual ships its own test set

```markdown
#### Write this
There were 16.5 million people enrolled to vote in Australian elections on 18 April 2019.

#### Not this
On 18 April 2019, 16.5 million people were enrolled to vote in Australian elections.
```

122 *Write this* blocks, 169 *Not this* blocks, 1,055 *Example* blocks — hand-authored,
correctly polarised, attributable to a specific rule by position. Octavius generated its
own test strings and inverted them wholesale. Derek harvests these instead, and they are
the seed for the fine-tuning set.

### Every rule carries three provenance tags

1. **`derivation`** — how we arrived at the rule
2. **`detection`** — the method through which it is implemented
3. **`source`** — the original Style Manual rule, verbatim, with URL and page hash

Plus deontic modality, clarity (and the formal `specification` where an ambiguity was
resolved, with the assumptions logged), scope, polarity, calibrated confidence, and the
full review history. See [`docs/03-rule-ledger-schema.md`](docs/03-rule-ledger-schema.md).

---

## Documentation

| Document | What it is for |
|---|---|
| [00 — Postmortem: Octavius v1](docs/00-postmortem-octavius.md) | Every failure mode, with reproducible evidence. **Read before changing extraction or detection.** |
| [01 — Architecture](docs/01-architecture.md) | The layered design and what each layer guarantees |
| [02 — Decision log](docs/02-decisions.md) | 19 ADRs: what was decided, why, what it costs |
| [03 — Rule ledger](docs/03-rule-ledger-schema.md) | The data contract |
| [04 — Roadmap](docs/04-roadmap.md) | Phases, and how to get from 661 candidates to working rules |
| [05 — Open questions](docs/05-open-questions.md) | What is genuinely undecided, with recommendations |
| [06 — Extraction audit](docs/06-extraction-audit.md) | Candidates checked against the pages they came from, and what that found |

---

## Repository layout

```
corpus/       offline Style Manual snapshot + eligibility + changesets
ledger/       rules.jsonl — the rule ledger
derek/        corpus · extract · ledger · detect · eval · interfaces
schema/       machine-checkable ledger contract
tools/        review UI
docs/         the documentation set above
reference/    curated markdown; Octavius v1 artifacts (NON-AUTHORITATIVE)
tests/
```

`reference/octavius-v1/` exists for two purposes only: a **recall checklist** (did the
deterministic extractor find what a model found?) and a **permanent negative test set**
for the dogfood gate. It is never a source of rules.

---

## Design principles

1. **Each layer is reproducible from the one below it.** Otherwise you cannot tell a
   Style Manual change from model variance.
2. **A model may propose; only a human decides.** Nothing reaches the runtime without an
   explicit human transition.
3. **Rules are data, not code.** Declarative matchers from a closed vocabulary, never
   `exec()`.
4. **Polarity is explicit everywhere.** Detect the violation, never the compliant pattern.
5. **Measure quality before any suppression.** Budgets and dedup make a broken rulebook
   look merely noisy.
6. **Use the cheapest tier that works.** No model where a regex will do.
7. **Deferred features get their structural accommodation now.** Word round-tripping and
   MCP serving are deferred; the indirection that makes them cheap is already in place.
