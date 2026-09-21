# Open questions

Questions that are genuinely undecided, each with a recommendation and what would settle
it. Decisions that *have* been made live in [02-decisions.md](02-decisions.md) — if a
question is not here, it has an ADR, and changing it means writing a superseding one.

The point of this file is that an open question stays visibly open. Octavius's failures
were not mostly wrong decisions; they were decisions nobody noticed they were making.

---

## Q1 — Which model should generate suggested corrections?

**Status:** open, deferred to Phase 5+. Does not block identification.

Candidates named so far: a fine-tuned Llama 3.2 1B/3B, Qwen 2.5 1.5B/3B, or a seq2seq
model (T5 / BART).

**Recommendation: start with a small encoder–decoder — BART-base (~140M) or
flan-t5-base (~250M) — not a decoder-only instruct model.** The reasoning:

- The task is **constrained span rewriting conditioned on a rule label**, not open-ended
  generation. That is precisely what encoder–decoder models are built for, and they
  fine-tune well on a few thousand pairs — which is roughly the data that is realistically
  available.
- It fits the free-tier compute constraint. A 1.5B decoder at int4 is ~1 GB and slow on
  CPU; BART-base at int8 is tens of megabytes and fast.
- Small seq2seq models are much less prone to the failure that matters here — rewriting
  more of the sentence than the rule asked for. Fidelity to the untouched span is the
  metric, and a constrained model is easier to hold to it.
- A decoder-only instruct model is the better choice if you want **one model handling
  many rules zero-shot** rather than a fine-tune per mutation class. That is a real
  trade-off, and it becomes attractive the moment the rule count is high and the
  per-rule data is thin.

**What would settle it:** ~200 hand-written `(violating text, rule, corrected text)`
triples per mutation class, then a head-to-head on exact-match plus a "did it change
anything it shouldn't have" span-fidelity metric. Do not choose before that data exists.

**Structural note:** Tier 2 sits behind an interface
([ADR-010](02-decisions.md#adr-010-detection-tiers-and-cheapest-viable-routing)), so this
choice is reversible. It is not a foundation decision — do not treat it as one.

---

## Q2 — How does Word round-tripping actually work?

**Status:** design settled, implementation open.
[ADR-012](02-decisions.md#adr-012-format-independent-document-model) fixes the shape:
an OOXML `Anchor` implementation, and nothing upstream changes.

What remains genuinely open is **run-boundary reconciliation**.

Word splits a logical span across multiple `w:r` runs for arbitrary reasons — a spell-check
artifact, a stray formatting toggle, tracked-changes history. A single sentence is
routinely five runs. When a correction replaces a span that crosses a run boundary,
something must decide which run's formatting the replacement inherits.

Options:

| Approach | Behaviour | Risk |
|---|---|---|
| Inherit from the first run in the span | Simple, predictable | Loses mid-span emphasis |
| Split the replacement proportionally across runs | Preserves formatting | Ill-defined when lengths differ |
| Refuse to auto-apply across run boundaries; offer manual | Never corrupts | Blocks many real corrections |

**Recommendation:** inherit from the first run, but **detect** when the span carries
mixed formatting and downgrade that finding from auto-apply to manual. Most spans are
formatting-uniform; the ones that are not are exactly the ones worth a human glance.

**Also open:** whether corrections should be emitted as tracked changes
(`w:ins`/`w:del`) rather than direct edits. For APS review workflows this is probably
the expected behaviour and is worth deciding before the adapter is written, because it
changes the edit model rather than just the output.

**What would settle it:** a corpus of ~20 real APS `.docx` files, measuring what
fraction of candidate spans cross a run boundary and how many carry mixed formatting.

---

## Q3 — What should be encoded in the classifier's training input?

**Status:** partly decided. [ADR-019](02-decisions.md#adr-019-training-inputs-carry-no-format-markup)
settles the load-bearing parts:

- **Format markup: never.** It is what makes the Word deferral cheap.
- **Block type: yes**, as a control token from a vocabulary shared by every adapter.
- **POS tags concatenated into the text: no.** ModernBERT learns its own morphosyntax,
  and interleaving tags corrupts the tokenisation the pretrained weights expect. POS
  belongs in Tier 0 matchers and in rule routing.

Two things remain open:

**Q3a — Document-level context as control tokens.** Should `content_type` and `audience`
be prepended (`[FORM] [PUBLIC] …`)? Probably yes — several rules are
applicability-gated on exactly these. But it costs sequence length and risks the model
learning the context token as a shortcut rather than the linguistic signal.
*Settled by:* an ablation once there is a labelled set. Hold the tokens in the data
format from the start so the ablation is cheap to run.

**Q3b — Surrounding context window.** Some rules are inherently cross-sentence
("define an acronym before its second use", "vary sentence length"). A single sentence
cannot express them. Options: (a) sentence only, cross-sentence rules stay Tier 0 with a
`structural_predicate`; (b) sentence plus a fixed window of neighbours; (c) whole block.
*Recommendation:* start with (a). It keeps sequences short, keeps the free-tier budget
intact, and cross-sentence rules are a small minority that Tier 0 handles well. Revisit
only if a specific rule set demands it.

---

## Q4 — What is the context vocabulary, exactly?

**Status:** open and **on the critical path**.
[ADR-015](02-decisions.md#adr-015-context-variables-chosen-by-betweenness) fixes the
*method* for choosing UI controls; it does not fix the vocabulary those controls draw on.

This must be drafted **before Pass 2 of the review**
([04-roadmap.md](04-roadmap.md#option-c--triage-first-then-fill-only-the-survivors)),
because rules authored against ad-hoc preconditions cannot be compared, and retrofitting
a vocabulary is a re-review of every rule.

Starting proposal, to be argued with:

| Variable | Values |
|---|---|
| `content_type` | policy · web_page · form · report · email · social_post · easy_read · transcript |
| `audience` | general_public · specialist · internal · cald · low_literacy |
| `register` | formal · neutral · conversational |
| `medium` | screen · print · both |
| `is_citation` | true · false |
| `is_legal_text` | true · false |
| `is_quoted` | true · false |

**What would settle it:** tagging preconditions on the first ~50 triaged rules and
seeing which variables actually get used, then pruning. The vocabulary should be derived
from rules that exist, not imagined in advance — but it must be *stable* before the bulk
pass.

---

## Q5 — How are Tier-0 rules calibrated with thin evidence?

**Status:** open. [ADR-013](02-decisions.md#adr-013-confidence-is-calibrated-not-raw)
requires calibrated confidence; it does not say what to do with a rule that has three
gold examples.

A Wilson lower bound handles small samples honestly but yields confidences so low that
good rules get filtered out by any reasonable slider position.

Options: show `null` / "unvalidated" until N examples exist (currently favoured);
hierarchical shrinkage toward a per-method prior; or a hand-assigned prior per modality.

**Recommendation:** `null` until N≥10, and let the UI treat unvalidated separately from
low-confidence rather than conflating them. A user filtering by confidence is asking
"how sure are you?", and "we haven't measured" is a different answer from "not very".

**What would settle it:** how many rules actually reach N≥10 after Phase 3. If most do
not, shrinkage becomes necessary.

---

## Q6 — Should prose-derived candidates be extracted at all?

**Status:** open. The extractor currently reads rules from headings only
([ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity)), yielding 661
candidates. Rules stated only in body prose are missed.

**Recommendation:** defer. Finish triage and Tier 0 on the 661 first, then measure
recall against `reference/octavius-v1/` — the v1 rulebook is retained precisely as a
recall checklist. If a material set of real rules exists only in prose, add the
`imperative_sentence` derivation pass (it is already a declared `derivation.method`, so
the ledger does not change).

The risk of doing it early is exactly the Octavius failure mode: inflating the candidate
count past reviewability before anything has been reviewed.

---

## Q7 — What is the deployment target?

**Status:** open. The constraint is stated — free-tier Google compute — which
[ADR-014](02-decisions.md#adr-014-core-library-with-thin-adapters) treats as binding
(stateless core, int8 ONNX, swappable backend).

Undecided: Cloud Run vs Cloud Functions vs a Colab-hosted prototype; whether the MCP
server is co-hosted or separate; and whether the model is bundled in the container or
fetched at cold start.

**Recommendation:** Cloud Run with the model baked into the image. Cold-start cost is
paid once per instance rather than per request, and a bundled model makes the container
reproducible — which matters more than image size here.

**What would settle it:** the measured p95 latency of Tier 0 + Tier 1 on a
representative 1,000-word document on one free-tier vCPU. Until that number exists, the
architecture keeps its options open and no more.

---

## Q8 — Should imperative detection use a POS tagger?

**Status:** open, and the largest known source of missed rules.

Rule candidates are identified by checking whether a heading opens with a verb from
`derek/extract/data/imperative_verbs.txt`, a hand-curated list.
[ADR-002](02-decisions.md#adr-002-deterministic-candidate-identity) chose a lexicon over
a POS tagger because tagger output varies across model versions and would make candidate
identity unstable.

The [2026-09-21 audit](06-extraction-audit.md#3-a-10-recall-gap-in-imperative-detection)
showed what that costs: **65 imperative headings filed as sections**, 50 of them purely
because the verb was absent from the list. Real rules were missing — *"Join nouns with
an en dash"*, *"Get permissions and licences for copyright material"*, *"Meet WCAG level
AA"*. The list has been extended with all 47 verbs the audit found, but that fixes this
snapshot, not the mechanism: the next Style Manual edit using an unlisted verb will
silently drop a rule, and only another audit will reveal it.

**Recommendation: replace the lexicon with a version-pinned POS tagger.** The
determinism objection is weaker than it looked. It is really an objection to
*uncontrolled* variation, and pinning solves that here exactly as it solves it for the
HTML converter ([ADR-020](02-decisions.md#adr-020-heading-levels-come-from-the-dom),
where `trafilatura`'s version was pinned for the same reason). A pinned spaCy model is a
pure function: same version, same input, same tag. A model upgrade becomes a deliberate,
reviewed event that produces an `extractor_upgrade`-style changeset — which the
reconciler now handles as a *rehoming* rather than 500 fictional upstream edits.

**Costs, which are real:**

- `derek/extract/` is currently stdlib-only, deliberately, so the snapshot workflow does
  not need the pipeline dependencies. spaCy plus a model is ~50 MB and breaks that.
  Mitigation: run tagging in a separate authoring step that writes `statement_form` into
  the ledger, keeping the runtime dependency-free.
- The tagger has its own false positives. On this corpus it wrongly flags 9 noun
  headings (`Summary`, `Comparative`, `Viewpoint`, `accept/except`) as imperatives.
  Those would become candidates that triage rejects — cheap, and the opposite failure
  (a silently dropped rule) is not.

**What would settle it:** tag the whole corpus with a pinned model, diff the candidate
set against the lexicon's, and count real gains against false positives. The audit
tooling already does most of this. Until then the lexicon stands, with its limitation
recorded in the file itself.
