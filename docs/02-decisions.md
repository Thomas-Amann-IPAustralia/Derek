# Decision log

Architecture Decision Records for Derek. Append-only. If a decision is reversed, add a
new ADR that supersedes it rather than editing the original — the reasoning that turned
out to be wrong is as useful as the reasoning that held.

Each ADR states the **decision**, the **reason**, what it **costs**, and — where
relevant — the **Octavius failure** it exists to prevent.

| ADR | Decision | Status |
|---|---|---|
| [001](#adr-001-snapshot-integrity-over-site-metadata) | Snapshot integrity over site metadata | Accepted |
| [002](#adr-002-deterministic-candidate-identity) | Deterministic candidate identity | Accepted |
| [003](#adr-003-model-calls-are-a-cache-not-a-step) | Model calls are a cache, not a step | Accepted |
| [004](#adr-004-polarity-is-a-first-class-schema-field) | Polarity is a first-class schema field | Accepted |
| [005](#adr-005-corpus-eligibility-is-declared-not-inferred) | Corpus eligibility is declared, not inferred | Accepted |
| [006](#adr-006-presence-vs-absence-and-the-scope-requirement) | Presence vs absence and the scope requirement | Accepted |
| [007](#adr-007-scope-and-unit-are-mandatory) | Scope and unit are mandatory | Accepted |
| [008](#adr-008-human-acceptance-is-a-gate-not-a-review-queue) | Human acceptance is a gate, not a review queue | Accepted |
| [009](#adr-009-no-generated-code-in-the-runtime) | No generated code in the runtime | Accepted |
| [010](#adr-010-detection-tiers-and-cheapest-viable-routing) | Detection tiers and cheapest-viable routing | Accepted |
| [011](#adr-011-the-dogfood-gate) | The dogfood gate | Accepted |
| [012](#adr-012-format-independent-document-model) | Format-independent document model | Accepted |
| [013](#adr-013-confidence-is-calibrated-not-raw) | Confidence is calibrated, not raw | Accepted |
| [014](#adr-014-core-library-with-thin-adapters) | Core library with thin adapters | Accepted |
| [015](#adr-015-context-variables-chosen-by-betweenness) | Context variables chosen by betweenness | Accepted |
| [016](#adr-016-deontic-modality-taxonomy) | Deontic modality taxonomy | Accepted |
| [017](#adr-017-ambiguity-is-classified-and-formalised) | Ambiguity is classified and formalised | Accepted |
| [018](#adr-018-derek-is-a-clean-repository-not-a-git-fork) | Derek is a clean repository, not a git fork | Accepted |
| [019](#adr-019-training-inputs-carry-no-format-markup) | Training inputs carry no format markup | Accepted |
| [020](#adr-020-heading-levels-come-from-the-dom) | Heading levels come from the DOM | Accepted |

---

## ADR-001 — Snapshot integrity over site metadata

**Decision.** The content hash of a normalised page is the only authority on whether a
page changed. `lastmod` from the sitemap is a scheduling hint and nothing more. Every
run emits an explicit changeset of `added` / `altered` / `removed` pages.

**Reason.** Octavius trusted `lastmod` exclusively (F7). A page edited without a
`lastmod` bump was never re-fetched, and a page deleted from the sitemap was never
removed from disk or from state. Both failures are silent, and both directly break the
requirement to identify altered and removed rules.

**Mechanism.**

1. **Daily incremental pass** — fetch pages whose `lastmod` advanced, plus any URL not
   yet in the lock file. Cheap; catches the common case.
2. **Weekly full sweep** — re-fetch and re-hash *every* eligible URL regardless of
   `lastmod`. This is the only thing that catches silent edits. Staggered across the
   week (1/7th of the corpus per day) so no single run is expensive.
3. **Removal detection** — any URL in the lock file but absent from the current sitemap
   is marked `removed`, its page is deleted from `corpus/pages/`, and a changeset entry
   is written. Rules derived from it move to `review_status: orphaned`, never silently
   deleted.
4. **Normalisation before hashing** — Unicode NFC, `\n` line endings, trailing
   whitespace stripped, collapsed blank runs, heading levels repaired (Defect 1),
   relative links resolved to absolute. Cosmetic rendering variation must not manifest
   as a content change, or the changeset becomes noise and gets ignored.
5. **Pinned extraction** — `trafilatura` and its options are version-pinned in
   `requirements-pipeline.txt`. An extractor upgrade is a deliberate, reviewed event
   that will rewrite many hashes at once; it gets its own changeset kind,
   `extractor_upgrade`, so it is never mistaken for editorial change.

**Freshness.** The requirement is 3 days. A daily schedule gives three independent
attempts inside the window. Two failure modes are accounted for:

- GitHub Actions can delay or drop scheduled runs under load. Three attempts absorb this.
- **GitHub disables scheduled workflows after 60 days of repository inactivity.** If the
  Style Manual is quiet for two months the snapshot job silently stops, and the first
  change after that is missed indefinitely. Mitigation: every run writes
  `corpus/.heartbeat` with a UTC timestamp and commits it at least weekly, keeping the
  repository active. The freshness check in CI fails if `.heartbeat` is older than 72 hours.

**Cost.** A weekly full sweep is ~186 page fetches spread over seven days, with
politeness delays. Negligible, and it is the only defence against silent edits.

---

## ADR-002 — Deterministic candidate identity

**Decision.** The set of rule candidates is a pure function of the corpus. A model may
classify, formalise or annotate a candidate; it may never decide that a candidate
exists. Identity is:

```
candidate_uid = blake2s(
    page_path || "\x00" || heading_path || "\x00" || normalised_statement
).hexdigest()[:16]
```

**Reason.** The requirement is that two runs over the same corpus extract exactly the
same rules. An LLM cannot provide this — temperature 0 is not determinism, batching
changes results, and model versions drift (F8). Structure can.

**Why structure works here.** The Style Manual encodes its rules *as headings*. On
`punctuation/commas.md` the `###` headings are the rules:

```
### Place a comma after adverbs and other introductory words
### Use a comma after phrases and clauses that change the whole sentence
### Avoid beginning a sentence with a string of numbers and dates
```

The corpus contains **1,795 `###` headings**. Octavius's model produced 3,114 "rules" —
roughly double — by fragmenting explanatory prose (F6). The headings are the
editorially-intended rule boundaries and they are free.

**Stability contract.** The UID is deliberately sensitive to statement text, because a
changed statement is a changed rule. Continuity across a reword is carried separately:

| Change | UID | Handling |
|---|---|---|
| Page content edited, heading untouched | unchanged | `altered` — re-review the body, rule identity holds |
| Heading reworded | **changes** | New candidate; reconciler matches on `(page_path, heading_path)` and records `supersedes: <old_uid>`; old rule → `review_status: superseded` |
| Page moved/renamed | **changes** | Reconciler matches on normalised statement across pages, records `supersedes` |
| Heading deleted | n/a | Old rule → `review_status: orphaned`, retained with its history |

Lineage is never inferred by a model. Matching uses exact and normalised string
equality only; anything that does not match cleanly is surfaced for human decision
rather than guessed.

**Cost.** Rules stated only in prose, with no heading, are missed by the primary
extractor. Accepted deliberately — a secondary *imperative-sentence* pass proposes
these as lower-priority candidates, still with deterministic IDs, flagged
`derivation.method: imperative_sentence` so review can prioritise heading-derived
candidates first.

---

## ADR-003 — Model calls are a cache, not a step

**Decision.** Every LLM output is content-addressed and committed to the repository:

```
decisions/<candidate_uid>/<prompt_version>.<model_id>.json
```

keyed additionally on a hash of the exact input. If the file exists, no call is made.
The pipeline is a cache-fill, not a transformation.

**Reason.** This is what makes a model-assisted pipeline reproducible (F8). Determinism
comes from **persistence**, not from sampling parameters. Re-running over an unchanged
corpus touches nothing. A changed corpus produces exactly the set of new calls implied
by the changeset, and the diff shows precisely which judgements changed and why.

**Consequences.**

- A prompt change is a `prompt_version` bump, which invalidates exactly the entries that
  used it. The blast radius of a prompt edit is visible in the diff before it is paid for.
- A model change is a `model_id` change, with the same property. Old decisions remain
  readable; they are not overwritten.
- Cost is bounded and predictable: each candidate is processed once per
  `(prompt_version, model_id)` pair, ever.
- **The cache holds proposals, not truth.** A cached decision still enters review as
  `proposed` (ADR-008).

---

## ADR-004 — Polarity is a first-class schema field

**Decision.** Every rule carries:

- `statement` — the Style Manual's wording, verbatim, quoted from the corpus.
- `violation_condition` — prose describing what makes text **wrong**. Mandatory.
- `compliant_examples` — text that must **never** fire.
- `violating_examples` — text that must **always** fire.

The schema rejects a rule with only one kind of example. The field names are chosen so
that a reversed implementation is visible on inspection.

**Reason.** F1, the defect that killed Octavius. "Use plurals when speaking about
collectives" was implemented as a detector for plurals, so it fired on correct text and
was silent on the error — and its tests passed, because `test_fire` / `test_no_fire`
are direction-neutral names that invited exactly this mistake.

**Enforcement.** Three independent checks, because one was not enough last time:

1. **Schema** — both example lists non-empty for any rule with `detectable: true`.
2. **Test harness** — every `violating_example` fires; every `compliant_example` does not.
3. **Dogfood gate** (ADR-011) — the rule is fired at the Style Manual's own prose, which
   is overwhelmingly compliant. A polarity-inverted rule lights up immediately.

Check 3 is the one that catches the case where the author has convinced themselves the
wrong way round, because it uses text nobody wrote for this rule.

---

## ADR-005 — Corpus eligibility is declared, not inferred

**Decision.** `corpus/eligibility.yaml` declares, per path glob, whether a page is a
source of content rules, with a reason. Extraction runs only over eligible pages. A new
page is `unclassified` and **excluded** until a human classifies it; CI reports the
backlog.

**Reason.** 108 passing Octavius rules came from the changelog, the blog, the handbook
and "how to cite the Style Manual" (F3). No per-rule heuristic reliably separates
"a rule about writing" from "a sentence about the manual"; the distinction is a
property of the *page*, and it is cheap to declare once.

**Initial classification.**

| Path | Eligible | Reason |
|---|---|---|
| `grammar-punctuation-and-conventions/**` | yes | Core normative content |
| `writing-and-designing-content/**` | yes | Core normative content |
| `structuring-content/**` | yes | Core normative content |
| `accessible-and-inclusive-content/**` | yes | Core normative content |
| `referencing-and-attribution/**` | yes | Core normative content |
| `content-types/**` | **partial** | Normative, but heavily artifact-scoped (F5). Eligible with mandatory `unit` review. |
| `about-style-manual/**` | no | Meta: changelog, foreword, citation of the manual itself |
| `style-manual-resources/**` | no | Handbook, blog and quick guides restate rules found elsewhere; including them duplicates rules under new IDs (F6) |

`style-manual-resources` is excluded as a *source* but retained as corroborating
material a reviewer can consult, since the quick guides often state a rule more crisply
than the normative page does.

---

## ADR-006 — Presence vs absence, and the scope requirement

**Decision.** Before a detection method is chosen, every rule is classified:

- **presence** — something wrong is *in* the text (`finalize`, a double space, a comma splice).
- **absence** — something required is *missing* (a comma after an introductory phrase,
  alt text on an image, a defined acronym before its second use).

An absence rule must declare a **trigger scope**: the span within which the requirement
must hold, and the precondition that makes the requirement apply. An absence rule
without a scope is `detectable: false`.

**Reason.** F2. 62% of Octavius's passing rules were positive instructions, and every one
was implemented as "match the topic and complain". "Use numerals for 2 and above" became
a matcher for spelled-out numbers and raised 8,052 findings on the manual itself.

**The shape that works.** An absence rule is expressible only as a conditional:

> *Given* a sentence that opens with an adverbial phrase (precondition, detectable),
> *assert* that a comma follows it (requirement, checkable within that span).

Both halves must be detectable. "Set column and row headings that are clear and accurate"
has no detectable precondition until it is formalised (ADR-017), which is exactly why
that rule is the worked example for disambiguation.

---

## ADR-007 — Scope and unit are mandatory

**Decision.** Every rule declares:

- `applies_to` — content types the rule governs (`policy`, `web_page`, `form`,
  `social_post`, `email`, `report`, `easy_read`, …), or `any`.
- `unit` — the span the rule evaluates: `character`, `token`, `phrase`, `sentence`,
  `paragraph`, `block`, `section`, `document`, or `artifact`.

Rules with `unit: artifact` (image contrast, video captions, file naming) are recorded
in the ledger with `detectable: false, reason: not_text` and **never loaded into the
text runtime**.

**Reason.** F5. Octavius applied "use no more than two hashtags" and "make video text
contrast at least 4.5:1" to policy documents. `page-optimisation-018` ("keep titles to
70 characters") raised 7,583 findings because it had no concept of which span is a title.

**Consequence for the UI.** `applies_to` is the natural backing for the content-type
context control (ADR-015). A user working on a policy document should never see a rule
scoped to social posts, and this is a filter over declared metadata rather than a
heuristic.

---

## ADR-008 — Human acceptance is a gate, not a review queue

**Decision.** `review_status` is one of `proposed` → `accepted` | `amended` | `rejected`
| `deferred`, plus the lifecycle states `superseded` and `orphaned`. **Only `accepted`
and `amended` rules load into the runtime.** Every transition records `decided_by`,
`decided_at` and `note`.

`validation` (do the tests pass?) is a **separate field** from `review_status` (have we
decided to ship this?). Octavius conflated them into `test_result` (Defect 4), so
"frozen" and "failing" were indistinguishable from the loader's point of view.

**Reason.** F9 — the decisive process failure. Interpretation was delegated to a batch
job before a single rule had been worked through by hand, and by review time there were
3,114 rows, which is past the point of reviewability.

**How this stays tractable.**

- The review UI (`tools/review/`) is built **before** the rule volume grows, not after.
- Review is ordered by expected value: heading-derived candidates before prose-derived,
  high-frequency rules before rare ones, unambiguous before ambiguous.
- Bulk rejection is first-class. Most triage decisions are "not applicable to text" or
  "artifact-scoped", and the UI must make disqualifying a hundred rules in a sitting
  take minutes. This is the primary near-term deliverable.
- The UI writes **git-tracked JSONL**, not a database. Every decision is a reviewable
  diff, revertable, attributable, and survives the tool being rewritten.

**Model proposals are welcome, model decisions are not.** The pipeline pre-fills every
field it can so that the human is correcting rather than authoring — which is both
faster and the stated working preference. The gate is that nothing reaches the runtime
without a human transition.

---

## ADR-009 — No generated code in the runtime

**Decision.** Rules are **data**. A rule's detector is a declarative `matcher` drawn from
a closed, versioned vocabulary of parameterised primitives, validated against
`schema/rule.schema.json`. The runtime never `exec()`s anything from the ledger.

Primitives (v1): `literal_set`, `regex`, `token_pattern` (spaCy-style POS/lemma
patterns), `length_constraint`, `structural_predicate` (a named, hand-written Python
function in `derek/detectors/`), `classifier` (a label from the Tier-1 model).

If a rule genuinely needs bespoke logic, a human writes a named function in
`derek/detectors/` with its own unit tests, and the rule references it **by name**.

**Reason.** Octavius `exec()`'d model-generated Python with full `__builtins__` for
thousands of unreviewed rules (Defect 2). Beyond the obvious risk, generated code is
unreviewable at volume, undiffable in any meaningful way, and unportable.

**What this buys.**

- Rules are safe to accept from any source, because they cannot express arbitrary behaviour.
- Rules are portable — the same ledger can drive a Python runtime, a JS client-side
  check, or a Rust service, because a matcher is a data structure.
- Rules are diffable: a review of a rule change is a review of a few fields.
- The matcher vocabulary is small enough to be exhaustively tested once, rather than
  each rule being individually trusted.

**Cost.** Some rules are awkward to express declaratively and need a
`structural_predicate`. That is the intended escape hatch, and its cost — a human writes
and tests a function — is the point.

---

## ADR-010 — Detection tiers and cheapest-viable routing

**Decision.** Three tiers. Each rule is routed to the **cheapest tier that can
correctly detect it**, decided at authoring time and recorded in the ledger.

| Tier | Mechanism | Cost | For |
|---|---|---|---|
| **0** | Literal sets, regex, POS/token patterns, length and structural predicates | microseconds, CPU | Orthography, spelling variants, punctuation, shortened forms, measurable constraints |
| **1** | ModernBERT multi-label classifier over sentences/blocks | ~ms, CPU with int8 ONNX | Rules needing semantics: tone, inclusive language, passive voice in context, noun trains, "clear and accurate" once formalised |
| **2** | Small generative model, rule-conditioned rewrite | ~100ms+ | **Deferred.** Suggestion generation only — never identification |

**Reason.** Directly the stated goal: do not use a model where a regex suffices. It is
also the only way the system fits on free-tier compute (ADR-014).

**Routing is a recorded decision, not a fallback.** `detection.tier` and
`detection.method` are ledger fields set during review. A rule does not "fall through"
to Tier 1 at runtime; if Tier 0 cannot do it, that is an explicit judgement with a
recorded reason.

**Tier 1 is multi-label over a shared encoder.** One forward pass yields scores for all
Tier-1 rules, rather than one model per rule. This is what makes neural detection
affordable, and it constrains rule design: Tier-1 rules must be expressible as labels
on a span. A rule that needs document-global reasoning is Tier 0 with a
`structural_predicate`, or it is deferred.

**Order of work:** Tier 0 first, exhaustively. Tier 1 rules accumulate as `accepted` but
`detectable_by: pending_model` until there is enough labelled data to train. The ledger
is the training specification — every Tier-1 rule is a label in the schema, and its
`violating_examples` / `compliant_examples` are its seed data.

---

## ADR-011 — The dogfood gate

**Decision.** Every accepted rule is fired at the Style Manual's own prose
(`corpus/pages/`, 213k words of professionally edited APS content) as a mandatory CI
gate, on **raw, un-suppressed output** — before budgets, dedup or document-level gating.

A rule exceeding its declared expected firing density is automatically quarantined
(`review_status: quarantined`) and cannot load until a human resolves it.

**Reason.** This is the check that would have caught every one of F1, F2, F4 and F5 on
day one, and it is nearly free. Octavius scored **1,441 findings per 1,000 words** on
this corpus and shipped anyway, because product-level suppression made the output look
merely noisy rather than meaningless (Defect 6).

**Thresholds.** Each rule declares `expected_density` (findings per 10,000 words on
compliant text). Default budget is 0 for `MUST`/`MUST_NOT` rules — the manual should not
violate its own mandatory rules. A non-zero budget is allowed with a written
justification (the manual quotes non-compliant examples under "Not this" headings, and
those spans are excluded from the corpus before the gate runs).

**The corpus is not perfect and that is fine.** The manual contains deliberate
counter-examples, quoted legislation and historical titles. The gate excludes
`Not this` blocks and quoted spans, and the remaining tolerance is absorbed by
`expected_density`. The signal being tested for is orders of magnitude, not precision:
a correct rule fires a handful of times; a broken one fires thousands.

**Second corpus.** The v1 rulebook
(`reference/octavius-v1/rules_working_draft.v1.jsonl`) is retained as a permanent
negative test set — a regression check that Derek does not re-derive the specific broken
rules catalogued in the postmortem.

---

## ADR-012 — Format-independent document model

**Decision.** The core operates on a `Document`:

```
Document
├── text: str                  # normalised plain text — the ONLY thing detectors see
├── blocks: list[Block]        # kind, char span into text, ancestors, lintable
└── anchors: list[Anchor]      # char span in text → opaque source pointer
```

An `Anchor` maps a character range in `text` back to a location in the originating
format. Detectors and the classifier never see the source format. Format adapters
(Tiptap/ProseMirror, HTML, Markdown, plain text, and later OOXML) construct the
`Document` and own the anchors.

**Invariant, enforced by property tests on every adapter:**

```
text[block.start : block.end] == block.text          # for every block
adapter.resolve(adapter.anchor_for(i)) == i          # for every char index i
```

Octavius had the equivalent zone-offset invariant and it was the part of the design that
held up (see `reference/octavius-v1/OCTAVIUS_REFACTOR_LOG.md`, "Single-pass serialiser
with guaranteed zone-offset invariant"). It is kept and generalised.

**This is the answer to the Word question.** Round-tripping with Word is deferred, but
the structural accommodation is made now and costs almost nothing:

- The model and all detectors are trained and run on `text` alone. Adding an OOXML
  adapter adds an `Anchor` implementation and **changes nothing upstream** — no
  retraining, no rule changes, no re-evaluation.
- `Anchor` is deliberately opaque to the core. For Tiptap it is a ProseMirror position;
  for OOXML it will be a `(part, w:p index, w:r index, offset)` tuple. The core never
  interprets it.
- Applying a correction is an adapter concern: the core emits *what to replace and with
  what*, in `text` coordinates; the adapter performs a minimal edit that preserves runs,
  revision marks and formatting.
- **The known hard part is recorded now:** Word splits a single logical span across
  multiple `w:r` runs for arbitrary formatting reasons, so a replacement crossing a run
  boundary must decide which run's formatting survives. That is an adapter-local
  decision and does not reach the core. See [08-open-questions.md](08-open-questions.md).

**Do not** let format details leak into `text`. The moment a detector or a training
example contains markup, the Word deferral becomes a rebuild. See ADR-019.

---

## ADR-013 — Confidence is calibrated, not raw

**Decision.** `confidence` on a finding means one thing regardless of tier:
**the estimated probability that this finding is a true violation.** It is comparable
across Tier 0 and Tier 1 because both are calibrated against held-out labelled data.

- **Tier 0** — empirical precision of that rule on the evaluation set, with a
  Wilson lower bound to penalise rules with thin evidence. A deterministic rule is
  *not* confidence 1.0; a regex that is right 80% of the time is 0.8.
- **Tier 1** — classifier probability after temperature scaling (or isotonic
  regression) fitted on a held-out split. Raw softmax output is **not** a probability
  and must never be surfaced.
- **Unvalidated** — a rule without enough evaluation data has `confidence: null` and is
  labelled "unvalidated" in the UI. It is never assigned an invented number.

**Reason.** The requirement is a confidence slider. A slider over incomparable scores is
worse than no slider: it trains users to distrust the whole output. Octavius had only a
binary severity derived from `discretionary_flag` (Defect 5), which is a statement about
the rule, not about the finding.

**Consequence.** Calibration needs a held-out labelled set from the very beginning. The
harvested `Write this` / `Not this` pairs (122 / 169 blocks) are the seed. This is
another reason the review UI comes first: review decisions *are* labelled data.

---

## ADR-014 — Core library with thin adapters

**Decision.** `derek/` is a dependency-light pure-Python library with no web framework.
Every interface is a thin adapter over the same `check(document) -> list[Finding]` call:

```
derek.core ──┬── derek.interfaces.http   (FastAPI)
             ├── derek.interfaces.mcp    (MCP server — tool-callable)
             ├── derek.interfaces.cli
             └── derek.interfaces.middleware  (LLM output filter)
```

**Reason.** MCP/API access and LLM-middleware use are stated goals. Both are trivial if
the core is a library and painful if logic lives in route handlers — which is where
Octavius put preprocessing and dispatcher selection (`routes/check.py`).

**Free-tier compute constrains this now, not later.**

- The Tier-1 model ships as **int8 ONNX**. ModernBERT-base at fp32 is ~600 MB, which does
  not fit comfortably in a 512 MiB–1 GiB free-tier container alongside a Python runtime;
  int8 is ~150 MB and runs acceptably on CPU.
- The model is loaded through an adapter interface (`derek.detect.model.Backend`) so the
  runtime is swappable — ONNX locally, a hosted endpoint if it outgrows the free tier —
  without touching rules or callers.
- The core is **stateless and synchronous**. No warm state, no background workers.
  Cold-start cost is model load; everything else is data loaded once at import.

**Middleware implications, decided now:**

- `check()` operates on a complete document. For streaming LLM output the middleware
  buffers to a **block boundary** (paragraph or list item) before checking, because
  sentence-level rules need the full sentence and block-level rules need the full block.
- The middleware path needs a latency budget and a fail-open policy: if checking exceeds
  the budget, emit the original text and log. A style filter must never be able to
  block an LLM's output.
- Correction (Tier 2) is explicitly **not** on the middleware path yet. Until then the
  middleware annotates rather than rewrites.

---

## ADR-015 — Context variables chosen by betweenness

**Decision.** The context controls exposed in the UI are chosen by computing, over the
rule↔condition bipartite graph, which context variables gate the most rules — and
exposing only the top handful.

**Mechanism.**

1. Every rule declares its applicability preconditions from a **closed context
   vocabulary** (`corpus/context-vocabulary.yaml`): `content_type`, `audience`,
   `register`, `medium`, `is_citation`, `is_legal_text`, `is_quoted`, …
2. Build a bipartite graph of rules and context variables.
3. Compute betweenness centrality over the projection. A variable with high betweenness
   is one that sits on the path between many rules and their applicability — flipping it
   changes the active rule set the most.
4. The top N (target: 4–6) become UI buttons. Everything else is inferred or defaulted.

**Reason.** Stated requirement, and it prevents the UI accumulating a control per rule
family. It also forces the context vocabulary to be **defined before rules are
authored**, so rules reference shared, comparable variables rather than inventing
per-rule conditions — which is what makes the graph meaningful.

**Sequencing.** The vocabulary must be drafted early even though the analysis runs late,
because retrofitting preconditions onto accepted rules is a re-review of every rule.

---

## ADR-016 — Deontic modality taxonomy

**Decision.** Every rule carries `modality`, one of:

| Modality | Meaning | Style Manual cues | Default severity |
|---|---|---|---|
| `MUST` | Required | "must", "always", bare imperative on a normative page | error |
| `MUST_NOT` | Prohibited | "must not", "never", "do not" | error |
| `SHOULD` | Recommended | "should", "we recommend" | warning |
| `SHOULD_NOT` | Discouraged | "should not", "avoid", "try not to" | warning |
| `MAY` | Permitted | "can", "may", "it's fine to" | info |
| `PREFER` | One option preferred over another | "prefer", "rather than", "instead of" | suggestion |

**Mechanism.** A deterministic lexical pass over the statement proposes a modality
(`derek/extract/modality.py`). The proposal is a *default in the review UI*, not a
decision — bare imperatives are genuinely ambiguous between `MUST` and `SHOULD`, and the
Style Manual is not consistent about it.

**Reason.** Stated requirement, and it drives severity, the confidence slider's defaults,
and the dogfood gate's density budget (a `MUST` rule firing on the manual's own prose is
a hard failure; a `PREFER` rule may legitimately fire).

**`PREFER` is separated from `SHOULD` deliberately.** A preference always has a named
alternative, which makes it the most tractable class for Tier 2 suggestion generation
later. Keeping it distinct now avoids re-labelling the ledger then.

---

## ADR-017 — Ambiguity is classified and formalised

**Decision.** Every rule carries `clarity`:

- `unambiguous` — directly operationalisable. *"Place a comma after adverbs and other
  introductory words."*
- `ambiguous_resolvable` — underspecified but formalisable with a recorded decision.
- `ambiguous_deferred` — requires judgement not yet resolved. Retained, not detectable.
- `not_automatable` — no operational form exists (e.g. "write for your reader").

For `ambiguous_resolvable`, the rule carries a **`specification`**: a formal restatement,
plus a `disambiguation_log` recording what was assumed, by whom, and on what basis.

**Worked example.** *"Set column and row headings that are clear and accurate."* →

> **Header placement.** Row 1 ($R_1$) must consist entirely of column headers. Column 1
> ($C_1$) must consist entirely of row headers.
> **Structural markup.** Every cell in $R_1$ and $C_1$ must be explicitly designated a
> header cell (HTML `<th>`, PDF `<TH>`). No data cells may exist within $R_1$ or $C_1$.
> **Header completeness.** Every cell in $R_1$ and $C_1$ must contain non-empty,
> non-whitespace content.
> **Grammatical uniformity.** All header text within a given row or column must match a
> single predefined POS pattern (e.g. all noun phrases, or all title case).

Four checkable assertions from one unactionable sentence — and the fourth is a genuine
addition beyond what the manual says, which is precisely why it must be logged rather
than quietly implemented.

**Reason.** Stated requirement. It also protects against the failure where a reviewer
silently narrows a rule to whatever is easy to detect: the `specification` is reviewable
*as an interpretation*, separately from the detector that implements it.

**The specification is the unit of detection, not the statement.** Detectors implement
`specification` where one exists and `statement` otherwise. This keeps the manual's
wording pristine for provenance while giving the runtime something precise.

---

## ADR-018 — Derek is a clean repository, not a git fork

**Decision.** Derek is a new repository seeded with selected Octavius material, not a
GitHub fork of it. Octavius is preserved unchanged and linked as the ancestor.

**Reason.**

- A fork inherits 18 MB of `archive/`, a dead React frontend, the compiled parquet
  rulebook and a history dominated by fifteen identical pipeline commits. None of it is
  wanted, and deleting it in the fork leaves it in the history permanently.
- The kept assets are copied with provenance recorded in
  [00-postmortem-octavius.md §4](00-postmortem-octavius.md#4-what-is-worth-keeping).
- Octavius stays readable for exactly the reasons the postmortem cites it.

**Cost.** Per-file git history for the carried-over corpus is not preserved.
`corpus/sitemap_state.legacy.json` and `corpus/content_manifest.legacy.json` carry the
substantive history (per-URL `lastmod`, per-file hashes), which is what actually matters
for change detection.

**Note.** Repository creation was not possible from the automation session that
scaffolded this (the GitHub App lacks repo-creation scope). `bootstrap_repo.sh` promotes
the `Derek/` tree to a standalone repository in one command.

---

## ADR-019 — Training inputs carry no format markup

**Decision.** The Tier-1 classifier is trained and served on **normalised plain text
only**. No HTML, no Markdown, no OOXML, no XML tags, no inline annotations. Structural
context reaches the model as a **separate categorical side channel**, not as text.

Concretely, the model input is:

```
[block_type_token] + normalised_sentence_text
```

where `block_type_token` is drawn from a small closed vocabulary (`[HEADING]`,
`[PARAGRAPH]`, `[BULLET]`, `[TABLE_CELL]`, `[QUOTE]`, …) shared by every format adapter.

**Reason.** This is the decision that keeps the Word deferral cheap (ADR-012). If format
markup enters the training distribution, then every new format is a distribution shift
requiring re-labelling and retraining. With a shared block-type vocabulary, an OOXML
adapter emits `[PARAGRAPH]` exactly as the Tiptap adapter does, and the model is unchanged.

**On concatenating POS tags into the input:** don't. ModernBERT learns its own
morphosyntactic representations, and interleaving tags corrupts the tokenisation the
pretrained weights expect — it reliably costs accuracy rather than adding information.
POS has two legitimate roles here, both outside the model: as a **Tier-0 matcher
primitive** (`token_pattern`), and as a **routing/feature signal** for deciding which
rules are candidates. If POS genuinely needs to reach Tier 1, the correct mechanism is a
parallel embedded channel summed into the input embeddings — a real architectural change,
to be justified by an ablation, not a string concatenation.

**What else is worth encoding — decided now, revisited with evidence:**

| Signal | Encode into model input? | Where it lives instead |
|---|---|---|
| Block type | **Yes**, as a control token | Closed vocabulary, shared across adapters |
| POS tags | No | Tier-0 `token_pattern` primitive |
| Character offsets | No | `Anchor`, resolved after classification |
| Format markup (HTML/OOXML) | **Never** | Adapter layer only |
| Document-level context (`content_type`, `audience`) | Probably — as control tokens | Context vocabulary (ADR-015); requires an ablation before committing |
| Surrounding sentences | Undecided — see [08-open-questions.md](08-open-questions.md) | Some rules (acronym-on-first-use) need it; costs sequence length |

---

## ADR-020 — Heading levels come from the DOM

**Decision.** The snapshot converts HTML to Markdown with
`derek/corpus/to_markdown.py`, which reads heading levels from the source
`<h1>`–`<h6>` tags. `trafilatura` is removed from the pipeline. Heading repair
([normalise.py](../derek/corpus/normalise.py)) is retained only as a regression
guard.

**Reason.** Extraction reads the rule inventory off the heading tree
([ADR-002](#adr-002-deterministic-candidate-identity)), so heading fidelity is
not cosmetic — it decides which rules exist.

`trafilatura` is a generic article extractor. It recovers prose well but does
not preserve heading hierarchy: the Octavius corpus carried 1,795 `###` against
only 53 `##` and 2 `#`, with section headings routinely demoted to bare
paragraphs. `repair_headings` was written to promote them back, and it worked —
it recovered 818 headings on the eligible pages — but it meant **390 of 546 rule
candidates (71%) existed only because a heuristic guessed they should.**

That is too much weight for a heuristic to carry, and it was avoidable: the
Style Manual's DOM already publishes a clean outline.

```
h1    page title            "Commas"
h2      section / rule      "Separate introductory words … with a comma"
h3        rule              "Place a comma after adverbs …"
h4          example block   "Write this" / "Not this" / "Example"
h5            example label "Non-essential" / "Essential"
```

Reading it is strictly better than inferring it, and it is simpler.

**Implementation.**

- Content root is `main`, falling back to `article`, `#main-content`, `body` —
  the first that actually contains a heading.
- Site chrome is removed structurally: `nav`/`footer`/`header`/`aside`/`script`
  and friends, plus everything from the first chrome heading onward
  (`Release notes`, `About this page`, `Help us improve the Style Manual`,
  `Footer`, `Secondary navigation`). Octavius carried all of these into the
  corpus as content, where they became 473 boilerplate nodes the classifier had
  to filter out per page.
- The walk is a single depth-first pass emitting block elements in document
  order. No scoring, no content-density heuristics, no randomness: the same
  HTML always produces byte-identical Markdown.
- `extract_markdown` **raises** rather than returning empty. A blocked fetch or
  a DOM change must fail loudly, not silently write an empty page into the
  corpus and register as a legitimate `altered` changeset entry.

**Why heading repair stays.** On DOM-faithful output it performs **zero**
promotions — it only fires on the exact pathology it was written for. Keeping
it costs nothing and means a future converter regression degrades rather than
silently dropping rules. Its promotion count is recorded per page
(`NormalisedPage.promotions`); a non-zero value on a fresh scrape is now a
signal that the converter has broken.

**Cost.**

- The corpus must be re-fetched in full, and every content hash changes. This is
  the `extractor_upgrade` changeset kind that
  [ADR-001](#adr-001-snapshot-integrity-over-site-metadata) exists to label, so
  it is not mistaken for 186 simultaneous editorial edits.
- Rule UIDs derived from repaired headings change, because a UID is content-
  addressed over the heading path ([ADR-002](#adr-002-deterministic-candidate-identity)).
  Reconciliation matches them by statement and records `supersedes`. Doing this
  **before** the first triage pass costs nothing; doing it after would have
  invalidated review decisions.
- `to_markdown.py` is Style-Manual-specific where `trafilatura` was generic. That
  is the right trade for a single-source pipeline, and it removes a dependency
  whose upgrades would silently rewrite the corpus.

**Note on validation.** The converter was developed against real source HTML
retrieved from the Wayback Machine, because the live site's Akamai edge returns
`403` to this environment's IP range. Archived HTML is the same document the
scraper would fetch; the transport path itself remains unexercised from here.
