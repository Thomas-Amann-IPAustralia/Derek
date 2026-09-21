# Architecture

Derek is a plain-language compliance system for Australian Public Service content,
built on the Australian Government Style Manual. It replaces Octavius; read
[00-postmortem-octavius.md](00-postmortem-octavius.md) before changing anything here.

The organising principle: **each layer must be reproducible from the one below it.**
Given the same corpus you get the same candidates; given the same candidates and the
same review decisions you get the same ledger; given the same ledger you get the same
findings. Octavius had no such property at any layer, which is why nobody could tell a
Style Manual change from model variance.

---

## The stack

```
  stylemanual.gov.au
        │
        │  Layer 0 — SNAPSHOT            deterministic, content-addressed
        ▼
  corpus/pages/**.md  +  corpus/snapshot.lock.json  +  corpus/changes/<date>.json
        │
        │  Layer 1 — EXTRACTION          pure function of the corpus, no model
        ▼
  Candidates  (stable uid, statement, heading path, gold examples)
        │
        │  Layer 2 — INTERPRETATION      model proposes, human decides
        ▼
  ledger/rules.jsonl   review_status ∈ {proposed, accepted, amended, rejected, …}
        │
        │  Layer 3 — DETECTION           accepted rules only
        ▼
  Tier 0 deterministic ──┐
  Tier 1 classifier    ──┼──►  Finding{span, rule_uid, confidence, severity}
  Tier 2 generator     ──┘     (deferred)
        │
        │  Layer 4 — INTERFACES          thin adapters over one core call
        ▼
  HTTP  ·  MCP  ·  CLI  ·  LLM middleware  ·  review UI
```

Every arrow is a boundary a test enforces. `--check` modes exist at Layers 0 and 1 so
CI can assert the reproducibility claim rather than trusting it.

---

## Layer 0 — Snapshot

**Job:** keep an accurate offline mirror of the Style Manual and say precisely what
changed since last time.

| Module | Role |
|---|---|
| `derek/corpus/fetch.py` | Transport: robots.txt, XSLT-sitemap parsing, Selenium fallback. Carried over from Octavius, which solved this correctly. |
| `derek/corpus/to_markdown.py` | HTML → Markdown, preserving DOM heading levels (ADR-020). |
| `derek/corpus/normalise.py` | Canonical form + content hash + heading repair (fallback only). |
| `derek/corpus/eligibility.py` | Which pages are rule sources (ADR-005). |
| `derek/corpus/snapshot.py` | Fetch, write, update the lock file. |
| `derek/corpus/diff.py` | Emit `added` / `altered` / `removed` changesets. |

Three things Octavius got wrong and this layer fixes ([ADR-001](02-decisions.md#adr-001-snapshot-integrity-over-site-metadata)):

1. **Content hash is the authority**, not the sitemap's `lastmod`. A page edited without
   a `lastmod` bump was invisible to Octavius forever.
2. **Removals are processed.** A URL that leaves the sitemap gets its page deleted and
   its rules marked `orphaned`, rather than staying live indefinitely.
3. **Daily, not monthly.** The requirement is 3 days; a daily schedule gives three
   attempts inside the window. A weekly full re-hash sweep, staggered across seven days,
   catches silent edits.

**Heading fidelity** is the non-obvious part, and it decides which rules exist.

Octavius converted HTML with `trafilatura`, a generic article extractor that does not
preserve heading hierarchy: its corpus carried 1,795 `###` against only 53 `##` and 2
`#`, with section headings routinely demoted to bare paragraphs. A repair heuristic
recovered them, but that left **71% of rule candidates depending on a guess**.

`derek/corpus/to_markdown.py` reads heading levels from the source DOM instead
([ADR-020](02-decisions.md#adr-020-heading-levels-come-from-the-dom)). The Style Manual
publishes a clean outline — `h1` page title, `h2` sections, `h3` rules, `h4` example
blocks — so the levels are simply taken as given. Site chrome is removed structurally,
and `extract_markdown` raises rather than returning empty, so a blocked fetch can never
be written to the corpus as a legitimately empty page.

`repair_headings` is retained as a regression guard. It is **self-disabling**: if the
page already carries a level-1 or level-2 heading its hierarchy is intact and the
function returns the text unchanged. A non-zero promotion count on a fresh scrape now
means the converter has broken.

---

## Layer 1 — Extraction

**Job:** produce the rule inventory as a pure function of the corpus.

| Module | Role |
|---|---|
| `derek/extract/segment.py` | Markdown → heading tree. |
| `derek/extract/candidates.py` | Normativity classification, stable UIDs, gold-example harvesting. |
| `derek/extract/modality.py` | Deontic modality proposal (ADR-016). |
| `derek/extract/build.py` | Corpus → ledger, with reconciliation. |

**No model runs here.** The Style Manual states its rules as headings, so the inventory
is free and deterministic ([ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity)).
Octavius asked an LLM to decide what a rule was and got 3,114 of them — roughly twice
what the document contains — with no reproducibility.

Current output over the 128 eligible pages:

| | |
|---|---|
| Candidates | **661**, all with unique UIDs |
| Statement forms | imperative · negative imperative · modal |
| With hand-authored gold examples | 366 (55%) |
| With *paired* compliant + violating examples | 83 |
| Gold example sentences harvested | 520 |

Two runs produce byte-identical output; `python -m derek.extract.build --check` fails
CI if that ever stops being true.

**Gold examples.** The manual authors correctly-polarised example pairs directly into
the corpus under `Write this` / `Not this` and `Correct` / `Incorrect` headings. These
are harvested with provenance and become the seed evaluation set. Unlabelled `Example`
blocks are harvested but **not** assigned a polarity — guessing it is precisely the
mistake being guarded against. Octavius generated its own test strings instead and
inverted them wholesale.

661 is the number that matters. It is small enough for one person to review.

These counts are checked against the published pages by
`python -m derek.eval.audit_extraction` — see
[06-extraction-audit.md](06-extraction-audit.md).

---

## Layer 2 — Interpretation

**Job:** turn a candidate into a rule somebody has actually decided about.

This is where Octavius died — not because the model was bad, but because interpretation
was delegated before anyone had worked a single rule through by hand, and 3,114 rows is
past the point of reviewability
([postmortem F9](00-postmortem-octavius.md#f9--premature-delegation)).

The ledger entry ([03-rule-ledger-schema.md](03-rule-ledger-schema.md)) records:

- **Three provenance tags** — `derivation` (how we got here), `detection` (how it is
  implemented), `source` (the original rule, verbatim, with URL and page hash).
- **Polarity** — `direction`, `violation_condition`, `compliant_examples`,
  `violating_examples` ([ADR-004](02-decisions.md#adr-004-polarity-is-a-first-class-schema-field)).
- **Scope** — `applies_to`, `unit`, `context_preconditions` ([ADR-007](02-decisions.md#adr-007-scope-and-unit-are-mandatory)).
- **Clarity** — and, where an ambiguity was resolved, the `specification` plus a
  `disambiguation_log` of what was assumed ([ADR-017](02-decisions.md#adr-017-ambiguity-is-classified-and-formalised)).
- **Modality** — deontic force, driving severity and gate budgets ([ADR-016](02-decisions.md#adr-016-deontic-modality-taxonomy)).
- **Review** — status, who decided, when, and the full transition history.

**Model proposals are welcome; model decisions are not.** The pipeline pre-fills every
field it can so that review is *correction* rather than authoring. Proposals are
content-addressed by `(candidate_uid, prompt_version, model_id)` and committed, so
re-running is a no-op and a prompt change has a visible blast radius
([ADR-003](02-decisions.md#adr-003-model-calls-are-a-cache-not-a-step)).

The review UI (`tools/review/`) is built **before** the rule volume grows. It writes
git-tracked JSONL, so every decision is a reviewable diff. Bulk rejection is
first-class: most triage is "not applicable to text" or "artifact-scoped", and
disqualifying a hundred rules in a sitting must take minutes.

---

## Layer 3 — Detection

**Job:** find violations in a document, as cheaply as correctness allows.

| Tier | Mechanism | For |
|---|---|---|
| **0** | Literal sets, regex, POS/token patterns, length and structural predicates | Orthography, spelling, punctuation, shortened forms, measurable constraints |
| **1** | ModernBERT multi-label classifier over spans | Rules needing semantics: tone, inclusive language, contextual passive voice |
| **2** | Small generative model, rule-conditioned rewrite | **Deferred.** Suggestion only, never identification |

Routing is a recorded decision, not a runtime fallback
([ADR-010](02-decisions.md#adr-010-detection-tiers-and-cheapest-viable-routing)). Tier 1
is a single shared encoder emitting scores for all Tier-1 rules in one forward pass,
which is what makes neural detection affordable.

**Rules are data, not code.** A matcher is a declarative structure from a closed,
versioned vocabulary, validated against `schema/rule.schema.json`. The runtime never
`exec()`s anything from the ledger
([ADR-009](02-decisions.md#adr-009-no-generated-code-in-the-runtime)). Octavius `exec()`'d
model-generated Python with full `__builtins__` for thousands of unreviewed rules.

**Confidence is calibrated** ([ADR-013](02-decisions.md#adr-013-confidence-is-calibrated-not-raw)).
`confidence` means the same thing at every tier: the estimated probability that this
finding is a true violation. Tier 0 uses the rule's empirical precision with a Wilson
lower bound; Tier 1 uses temperature-scaled probabilities. A rule without enough
evaluation data gets `confidence: null` and shows as *unvalidated* — never an invented
number. This is what makes the confidence slider meaningful rather than decorative.

**The dogfood gate** ([ADR-011](02-decisions.md#adr-011-the-dogfood-gate)) fires every
accepted rule at the manual's own prose, on raw un-suppressed output. Octavius scored
**1,441 findings per 1,000 words** there and shipped anyway, because firing budgets and
document-level gating made the output look merely noisy. Quality is measured before any
suppression, permanently.

---

## Layer 4 — Interfaces

One core call, thin adapters
([ADR-014](02-decisions.md#adr-014-core-library-with-thin-adapters)):

```python
derek.core.check(document: Document, context: Context) -> list[Finding]
```

| Adapter | Purpose |
|---|---|
| `derek.interfaces.http` | FastAPI. The editor UI and any HTTP caller. |
| `derek.interfaces.mcp` | MCP server — Derek as a tool an LLM can call. |
| `derek.interfaces.cli` | Batch checking, CI use. |
| `derek.interfaces.middleware` | Filter between an LLM and its final output. |
| `tools/review/` | Rule triage. Reads and writes the ledger, not the runtime. |

The core is stateless, synchronous and dependency-light so it fits free-tier compute.
The Tier-1 model ships as int8 ONNX (~150 MB rather than ~600 MB at fp32) behind a
swappable backend interface.

**Middleware specifics, decided now rather than discovered later:** streaming output is
buffered to a **block boundary** before checking, because sentence rules need the whole
sentence and block rules need the whole block; the path has a latency budget and
**fails open**, because a style filter must never be able to block an LLM's output.

---

## The document model, and why Word is cheap to add later

Round-tripping with Word is deferred. The structural accommodation is made now, and
costs almost nothing ([ADR-012](02-decisions.md#adr-012-format-independent-document-model)).

```
Document
├── text: str              # normalised plain text — the ONLY thing detectors see
├── blocks: list[Block]    # kind, char span, ancestors, lintable
└── anchors: list[Anchor]  # char span → opaque, format-specific pointer
```

Invariants, property-tested on every adapter:

```
text[block.start : block.end] == block.text
adapter.resolve(adapter.anchor_for(i)) == i
```

Adding Word means adding an `Anchor` implementation over OOXML and **nothing else**: no
retraining, no rule changes, no re-evaluation. That holds only if the model never sees
format markup, which is why training input is plain text plus a block-type control token
from a vocabulary shared by every adapter
([ADR-019](02-decisions.md#adr-019-training-inputs-carry-no-format-markup)).

The known hard part is already written down: Word splits a logical span across multiple
`w:r` runs, so a replacement crossing a run boundary must decide which run's formatting
survives. That is adapter-local and never reaches the core. See
[08-open-questions.md](08-open-questions.md).

---

## Repository layout

```
Derek/
├── corpus/
│   ├── pages/**.md                  offline Style Manual snapshot (the kept foundation)
│   ├── eligibility.yaml             which pages are rule sources (ADR-005)
│   ├── snapshot.lock.json           per-page hash + lastmod + fetch metadata
│   └── changes/<date>.json          added / altered / removed changesets
├── ledger/
│   └── rules.jsonl                  the rule ledger — git-tracked, diffable
├── derek/
│   ├── corpus/                      Layer 0
│   ├── extract/                     Layer 1
│   ├── ledger/                      Layer 2 storage + reconciliation
│   ├── detect/                      Layer 3 runtime
│   ├── eval/                        dogfood gate, calibration, metrics
│   └── interfaces/                  Layer 4 adapters
├── schema/rule.schema.json          machine-checkable ledger contract
├── tools/review/                    rule triage UI
├── docs/                            this documentation set
├── reference/
│   ├── style-manual-curated/        hand-cleaned markdown, for cross-checking
│   └── octavius-v1/                 NON-AUTHORITATIVE: old rulebook, prompts, logs
└── tests/
```

`reference/octavius-v1/` is kept for exactly two purposes: a **recall checklist** (did
the deterministic extractor find what a model found?) and a **permanent negative test
set** for the dogfood gate. It is never a source of rules.
