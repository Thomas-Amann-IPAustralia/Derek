# Roadmap

Derek's near-term goal is a **robust identification system**: find the text that breaks
a rule, flag it, and let the user keep or accept. Suggested corrections come later.
Word round-tripping and the MCP/middleware surfaces come later still, but the structural
accommodations for both are already made ([ADR-012](02-decisions.md#adr-012--format-independent-document-model),
[ADR-014](02-decisions.md#adr-014--core-library-with-thin-adapters)) so neither forces a rebuild.

---

## Where things stand

| | |
|---|---|
| Offline snapshot | 186 pages carried over from Octavius, re-normalised |
| Eligible rule-source pages | 128 (58 excluded, with reasons, per [ADR-005](02-decisions.md#adr-005--corpus-eligibility-is-declared-not-inferred)) |
| Deterministic candidates | **736**, unique UIDs, byte-identical across runs |
| With a *paired* compliant + violating example | **169** (170 with at least one) |
| Reviewed | 21 — nothing loads until a human accepts it |
| Corpus | **frozen** ([ADR-024](02-decisions.md#adr-024--the-corpus-is-frozen-while-the-golden-set-is-drawn)); drift is reported, not applied |

---

## How to get from the candidates to working rules

> **Option C was chosen and is now superseded by Option D.** The three options below are
> kept because the reasoning is still the reasoning — what changed is a measurement, not
> an opinion. Twenty-one decisions into Pass 1,
> [docs/07](07-extraction-hand-audit.md) had already established that the queue being
> triaged is 25% noise *and* missing roughly 60 real rules stated as description, which
> never reach a card at all. Triage can improve precision; it cannot improve recall, and
> the missing rules are the expensive half.

This is the decision the last project got wrong, so it is worth being explicit. Four
approaches, in the order they were considered.

### Option A — Author every rule by hand

You write the specification, polarity, scope and matcher for each of the 720.

- **For:** maximum fidelity. Every rule is one you understand completely.
- **Against:** roughly 10 minutes per rule is **≈120 hours**. Realistically it stalls.
- **Verdict:** not reasonable as a whole-corpus strategy — but see the hybrid below,
  where it is exactly right for a small set.

### Option B — Model fills everything, you accept or correct

The pipeline pre-fills `clarity`, `direction`, `unit`, `applies_to`,
`violation_condition` and a proposed `matcher` for all 720. You work the review queue,
correcting rather than authoring.

- **For:** matches the stated preference (correcting beats writing from scratch). All
  720 get a first pass.
- **Against:** you pay for model proposals on rules you were always going to discard,
  and a plausible-looking wrong proposal is harder to spot than a blank field. This is
  the failure mode that produced Octavius's polarity inversions — the output *looked*
  right.
- **Verdict:** right mechanism, wrong sequencing on its own.

### Option C — Triage first, then fill only the survivors

**Chosen, then superseded — see Option D.** Two passes with different economies.

**Pass 1 — disqualification.** No model. For each candidate you answer one question:
*is this detectable in text at all?* Set `unit` (is it `artifact`?), `applies_to`, and
`clarity`. Reject or defer anything that cannot work. This is the "disqualify the easy
N/A rules" UI, and it runs at roughly **15–30 seconds per rule** because it needs
judgement, not authoring.

> 720 candidates × ~20s ≈ **4–5 hours**, realistically two or three sittings.

Based on the Octavius corpus composition, expect **180–300 survivors**. Everything
scoped to images, video, social posts or page metadata drops out here — the class that
generated Octavius's worst noise ([postmortem F5](00-postmortem-octavius.md#f5--rules-about-artifacts-not-text)).

**Pass 2 — fill and correct.** Model proposals run **only on survivors**, and only for
the fields that survived triage. You correct. The `Write this` / `Not this` pairs are
already attached to 169 of them, so their polarity is grounded in editorial fact rather
than a model's guess.

> ~240 rules × ~4 min ≈ **16 hours**, and it is interruptible.

**Pass 3 — hand-author the hard ones.** The 10–20 rules that matter most and resist
formalisation (Option A, deliberately). The table-headings rule in
[ADR-017](02-decisions.md#adr-017--ambiguity-is-classified-and-formalised) is the model
for this: one unactionable sentence becomes four checkable assertions, with the
assumptions logged.

**Why this ordering.** Triage is cheap and high-leverage; filling is expensive and
error-prone. Doing the cheap pass first means you never pay to fill a rule you were
going to reject, and — more importantly — you look at every candidate **with fresh
judgement before a model has told you what to think**. That inversion is the single
process change between Derek and Octavius.

### Option D — Mark the rules on the manual  ← **current**

Reconstruct the Style Manual from the frozen corpus and select the span of text that
states each rule, wherever it sits ([ADR-023](02-decisions.md#adr-023--the-golden-span-set-is-a-declared-extraction-input),
`tools/annotate/`). The 736 candidates are pre-seeded as confirmable highlights, so
Option C's cheap pass is still there — confirming one is a keystroke — but three things
it could not do become possible:

- **A rule stated in prose is as reachable as one stated in a heading.** That is the
  ~60 rules the heading walk cannot see, on the pages where it is worst:
  `legal-material/bills-and-explanatory-material.md` has four real rule headings and
  yields zero candidates, `treaties.md` nine and zero, `pronouns.md` seventeen and zero.
- **A candidate can be corrected rather than only kept or binned.** The 18%
  "label, not statement" class is a heading at the right *place* with the wrong *words*;
  moving the span onto the sentence below it fixes the rule instead of discarding it.
- **Marking a page swept makes every unmarked heading a labelled negative.** Without
  that, "no rule here" and "not looked at yet" are the same thing, and a heuristic can
  only ever be measured for recall. `derek/eval/span_recall.py` is the instrument that
  reads it.

**Why this ordering still holds.** Everything Option C said about looking with fresh
judgement before a model tells you what to think is unchanged; what moved is the unit of
work, from a card the extractor chose to a page the manual wrote. Cost per rule is
higher and cost per page is much lower, and the rules it finds are the ones no number of
passes over the queue would have surfaced.

The golden set that results is also the labelled data a replacement heuristic is fitted
against **and measured on**, which is what makes unfreezing the corpus a decision with a
number behind it rather than a guess.

---

## Phases

### Phase 1 — Snapshot hardening *(built; unverified against the live site)*

- [x] `derek/corpus/fetch.py` — Octavius transport ported (robots.txt, XSLT sitemap, Selenium fallback)
- [x] `derek/corpus/snapshot.py` — fetch + write + `snapshot.lock.json`
- [x] `derek/corpus/diff.py` — `added` / `altered` / `removed` changesets from content hashes
- [x] Daily incremental + staggered 1/7-per-day full re-hash sweep
- [x] `.heartbeat` + 72-hour CI freshness assertion (guards the 60-day workflow-disable trap)
- [x] `snapshot.lock.json` seeded from the carried-over corpus (186 pages, hash + URL + `lastmod`)
- [ ] **Run against the live site.** The transport is carried over unchanged from
      Octavius, where it worked, but it has not been exercised from this repository.
      Expect to re-tune politeness delays and the WAF fallback.

**Done when:** a forced edit to a page is detected within 24 hours, a removed page
orphans its rules, and a re-run with no upstream change produces an empty changeset.

### Phase 2 — Review UI and triage *(tool built; the triage pass is the next work)*

- [x] `tools/review/` — local stdlib-only app over `ledger/rules.jsonl`
- [x] Swipe or keyboard: → keep · ← bin · ↓ not sure · N not-text · W keep-reworded · U undo
- [x] Shows source statement, body excerpt, gold examples, and a link to the live page
- [x] Writes git-tracked JSONL; every decision is a diff
- [x] Pipeline-owned fields (`uid`, `source`, `derivation`) rejected by the API, so a
      rebuild can never clobber a decision and review can never corrupt provenance
- [x] `tools/review/glossary.json` explains every option in plain language, and the
      server refuses to start if it has drifted from the vocabularies in
      `derek/ledger/model.py` — a reviewer is never shown an unlabelled button
- [x] Scope is mandatory, not skippable: `clarity` starts blank because the extractor
      deliberately makes no claim there, and a rule cannot be kept until it is set
- [x] Rejections carry a reason from a closed list, so "we binned 300 rules" becomes
      "we binned 80 because they govern images", which is a fix rather than a statistic
- [x] Attention checks generated from the manual's own `Write this` / `Not this` pairs
      and graded server-side, so sustained-attention decay shows up in the record
- [x] Reviewer initials on every decision, inter-reviewer agreement reported, and a
      leaderboard **derived from the ledger** rather than stored — it cannot be inflated
- [x] Decisions faster than 2.5s score nothing and are marked `(hasty)` in the note,
      so the gamification cannot buy speed at the cost of the thing it exists to produce
- [x] Example-checking mode over the harvested gold set, on the same screens the
      synthetic training data will use (`ledger/training_candidates.jsonl`)
- [x] The same app published as a static site
      (<https://thomas-amann-ipaustralia.github.io/Derek/>), so the triage pass can be
      worked from a machine that cannot run Python. Decisions queue in the browser,
      export as JSONL, and are replayed into the ledger by
      `tools/review/apply_decisions.py` — through the same `_apply`, so the gate is
      the gate wherever the decision was typed. Attention checks are not served there
      (their answers would have to ship with the page) and the leaderboard is a
      build-time snapshot; both say so on the page
      ([ADR-022](02-decisions.md#adr-022--the-review-ui-is-published-the-gate-moves-to-the-apply-step))
- [ ] Bulk operations by page, section and predicted scope

The triage app is **retained, not superseded**. Its shape — one item, a verdict, a
gesture — is exactly right for reviewing the synthetic training pairs in Phase 5, which
is thousands of small independent judgements. It is the wrong shape for identifying
rules, which is what Phase 2b is for.

### Phase 2b — Mark the golden span set *(the current work)*

- [x] `derek/extract/blocks.py` — one plain-text projection both the browser and Python
      use, pinned by `derek/extract/data/blocks.lock.json` so a renderer change cannot
      silently re-anchor a recorded span
- [x] `corpus/freeze.yaml` — the corpus stops moving under the spans; drift is still
      detected and reported to `corpus/drift.json`
      ([ADR-024](02-decisions.md#adr-024--the-corpus-is-frozen-while-the-golden-set-is-drawn))
- [x] `tools/annotate/` — the manual, reconstructed and selectable, published at
      <https://thomas-amann-ipaustralia.github.io/Derek/annotate/>. The 736 candidates
      pre-seeded as confirmable highlights; create, adjust and delete a span; `F` marks a
      page swept
- [x] `golden/spans.jsonl` read as a declared extraction input, with UID continuity so
      confirming a candidate keeps everything already decided about it
      ([ADR-023](02-decisions.md#adr-023--the-golden-span-set-is-a-declared-extraction-input))
- [x] `tools/annotate/apply_spans.py` + `apply-spans.yml` — the return leg, through the
      same `server._apply` the triage app uses
- [x] `derek/eval/span_recall.py` — the heading heuristic measured against what a human
      actually marked, on swept pages only
- [x] First three pages annotated (`commas.md`, `pronouns.md`, `treaties.md`), at about
      23 words a minute, or at least 116 hours for the whole manual at that pace
      (`python -m derek.eval.annotation_pace`).
      They surfaced the gaps below, and the annotator was changed to close them.
- [x] The span form asks for `violation_condition` (D-2: all 44 rules accepted before it
      had none) and records *how a checker would find it* as a closed choice that sets
      `detection.tier` (ADR-010). A list's lead-in and its items can be one example
      (<kbd>⇧C</kbd> / <kbd>⇧V</kbd>). Unswept pages with rules on them are named on export.
- [x] [`docs/08-rule-grain.md`](08-rule-grain.md): what counts as one rule. **Proposed**,
      pending agreement from whoever annotates.
- [x] `derek/eval/golden_lint.py`: the golden set checked against the invariants and
      that policy, shown on each page in the annotator and after each upload.
- [x] Model drafts ([ADR-025](02-decisions.md#adr-025--a-model-may-draft-spans-a-human-marks-them),
      proposed): `tools/draft/` and `draft-spans.yml`, a draft layer in the annotator,
      `golden/blind.json` (10 pages never shown a draft), and `derek/eval/draft_score.py`.
      **Built and tested; not yet run**, because it needs an API key.
- [ ] **Finish and sweep the first three pages**, working through the annotator's
      *Checks* card. They are blind, so they are the first measurement.
- [ ] **Draft the blind pages and score them** (`draft-spans.yml` with `blind`). This
      decides ADR-025: if drafts do not beat the sentence regex on recall, or they get
      example polarity wrong more often than a human, drafting stops here.
- [ ] If it passes: annotate 5 to 8 varied pages *with* drafts, and compare their pace
      (`python -m derek.eval.annotation_pace`) with the blind pages.
- [ ] Then the rest of the 128 eligible pages.

**Done when:** every eligible page is swept, so `span_recall` has a complete set to
measure against and the ledger's inventory is one a human drew rather than one a
heuristic guessed.

### Phase 3 — Tier 0 detection *(started)*

- [x] `derek/detect/matchers.py`: `regex` and `literal_set`, plus the scope keys `unless`,
      `window` and `skip_quoted`, all data ([ADR-009](02-decisions.md#adr-009--no-generated-code-in-the-runtime),
      [ADR-026](02-decisions.md#adr-026--a-matcher-is-proposed-as-data-and-adopted-by-a-named-human))
- [x] `Document` with plain-text and Style Manual page adapters, with the slice
      invariant tested. *Anchors back to a source format, and a Markdown adapter for
      user documents, are still to do.*
- [x] Example harness: violating fire, compliant do not, and at least one violating
      example to fire on
- [x] Dogfood gate wired into CI, now on plain text; `derek.detect` runs the same matchers
- [x] Nine matchers proposed in `ledger/proposals/tier0.jsonl`: **four ready** (Latin
      shortened forms, digit grouping, "and myself" as subject, opening with numbers and
      dates), four blocked for want of a violating example, and one blocked by
      [Q9](05-open-questions.md#q9--the-harvested-gold-examples-include-the-prose-that-follows-them).
      **None adopted:** that is a named human's step (`adopt-matchers.yml`).
- [ ] Violating examples for the blocked four, from a reviewed source
- [ ] Calibration on the gold set; real `confidence` values

**Done when:** Tier 0 rules run green through the dogfood gate and carry calibrated
confidence.

### Phase 4 — Identification UI

- [ ] Editor with inline highlighting, findings panel, keep-or-accept
- [ ] Confidence slider over calibrated values
- [ ] Context controls chosen by betweenness ([ADR-015](02-decisions.md#adr-015--context-variables-chosen-by-betweenness))

### Phase 5 — Tier 1 classifier

- [ ] Context vocabulary finalised (must precede large-scale labelling)
- [ ] Expand the 2,390 gold example lines into a labelled set; hold out a calibration split
- [ ] Fine-tune ModernBERT multi-label; export int8 ONNX
- [ ] Temperature-scale on held-out data; integrate behind the backend interface

### Phase 6 — Interfaces

- [ ] MCP server, HTTP API, CLI
- [ ] Middleware adapter with block buffering, latency budget and fail-open

### Deferred, by design

| Feature | Blocked on | Structural accommodation already made |
|---|---|---|
| Suggested corrections (Tier 2) | Identification being good enough to trust | Tier boundary in the ledger; `PREFER` modality separated for exactly this |
| Word round-trip | Demand | `Anchor` indirection; format-free training inputs ([ADR-019](02-decisions.md#adr-019--training-inputs-carry-no-format-markup)) |
| Live deployment | Phases 3–4 | Stateless core; int8 ONNX; swappable model backend |

---

## Sequencing traps

Three things must happen **earlier than they feel necessary**, because retrofitting them
is a re-review of every rule:

1. **The context vocabulary** ([ADR-015](02-decisions.md#adr-015--context-variables-chosen-by-betweenness))
   must be drafted before Pass 2, so rules reference shared variables rather than
   inventing per-rule preconditions. The betweenness analysis runs later, but the
   vocabulary cannot.
2. **The calibration split** must be held out before any labelling at scale, or the
   confidence numbers in Phase 3 are fitted on their own training data.
3. **The dogfood gate** must be in CI before the first rule is accepted, not after the
   first hundred. Octavius's entire failure is what happens when the quality gate arrives
   after the volume.
