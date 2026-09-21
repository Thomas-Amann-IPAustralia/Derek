# Roadmap

Derek's near-term goal is a **robust identification system**: find the text that breaks
a rule, flag it, and let the user keep or accept. Suggested corrections come later.
Word round-tripping and the MCP/middleware surfaces come later still, but the structural
accommodations for both are already made ([ADR-012](02-decisions.md#adr-012-format-independent-document-model),
[ADR-014](02-decisions.md#adr-014-core-library-with-thin-adapters)) so neither forces a rebuild.

---

## Where things stand

| | |
|---|---|
| Offline snapshot | 186 pages carried over from Octavius, re-normalised |
| Eligible rule-source pages | 128 (58 excluded, with reasons, per [ADR-005](02-decisions.md#adr-005-corpus-eligibility-is-declared-not-inferred)) |
| Deterministic candidates | **661**, unique UIDs, byte-identical across runs |
| With gold examples | 366 (55%); 83 with *paired* compliant + violating |
| Reviewed | **0** — nothing loads until a human accepts it |

---

## How to get from 661 candidates to working rules

This is the decision the last project got wrong, so it is worth being explicit. Three
approaches are viable.

### Option A — Author every rule by hand

You write the specification, polarity, scope and matcher for each of the 661.

- **For:** maximum fidelity. Every rule is one you understand completely.
- **Against:** roughly 10 minutes per rule is **≈90 hours**. Realistically it stalls.
- **Verdict:** not reasonable as a whole-corpus strategy — but see the hybrid below,
  where it is exactly right for a small set.

### Option B — Model fills everything, you accept or correct

The pipeline pre-fills `clarity`, `direction`, `unit`, `applies_to`,
`violation_condition` and a proposed `matcher` for all 661. You work the review queue,
correcting rather than authoring.

- **For:** matches the stated preference (correcting beats writing from scratch). All
  661 get a first pass.
- **Against:** you pay for model proposals on rules you were always going to discard,
  and a plausible-looking wrong proposal is harder to spot than a blank field. This is
  the failure mode that produced Octavius's polarity inversions — the output *looked*
  right.
- **Verdict:** right mechanism, wrong sequencing on its own.

### Option C — Triage first, then fill only the survivors  ← **recommended**

Two passes with different economies.

**Pass 1 — disqualification.** No model. For each candidate you answer one question:
*is this detectable in text at all?* Set `unit` (is it `artifact`?), `applies_to`, and
`clarity`. Reject or defer anything that cannot work. This is the "disqualify the easy
N/A rules" UI, and it runs at roughly **15–30 seconds per rule** because it needs
judgement, not authoring.

> 661 candidates × ~20s ≈ **3.5–4.5 hours**, realistically two or three sittings.

Based on the Octavius corpus composition, expect **180–300 survivors**. Everything
scoped to images, video, social posts or page metadata drops out here — the class that
generated Octavius's worst noise ([postmortem F5](00-postmortem-octavius.md#f5--rules-about-artifacts-not-text)).

**Pass 2 — fill and correct.** Model proposals run **only on survivors**, and only for
the fields that survived triage. You correct. The `Write this` / `Not this` pairs are
already attached to 77 of them, so their polarity is grounded in editorial fact rather
than a model's guess.

> ~240 rules × ~4 min ≈ **16 hours**, and it is interruptible.

**Pass 3 — hand-author the hard ones.** The 10–20 rules that matter most and resist
formalisation (Option A, deliberately). The table-headings rule in
[ADR-017](02-decisions.md#adr-017-ambiguity-is-classified-and-formalised) is the model
for this: one unactionable sentence becomes four checkable assertions, with the
assumptions logged.

**Why this ordering.** Triage is cheap and high-leverage; filling is expensive and
error-prone. Doing the cheap pass first means you never pay to fill a rule you were
going to reject, and — more importantly — you look at every candidate **with fresh
judgement before a model has told you what to think**. That inversion is the single
process change between Derek and Octavius.

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
- [x] Keyboard-first triage: A accept · R reject · D defer · N not-text · S skip
- [x] Shows source statement, body excerpt, gold examples, and a link to the live page
- [x] Writes git-tracked JSONL; every decision is a diff
- [x] Pipeline-owned fields (`uid`, `source`, `derivation`) rejected by the API, so a
      rebuild can never clobber a decision and review can never corrupt provenance
- [ ] Bulk operations by page, section and predicted scope
- [ ] **Run Pass 1 over all 661** ← the actual next task

**Done when:** the reviewed count is 661 and the survivor set is known.

### Phase 3 — Tier 0 detection

- [ ] `derek/detect/` — matcher primitives ([ADR-009](02-decisions.md#adr-009-no-generated-code-in-the-runtime))
- [ ] `Document` + `Anchor` + plain-text and Markdown adapters, with property tests
- [ ] Example harness: violating fire, compliant do not
- [ ] Dogfood gate wired into CI
- [ ] Calibration on the gold set; real `confidence` values

**Done when:** Tier 0 rules run green through the dogfood gate and carry calibrated
confidence.

### Phase 4 — Identification UI

- [ ] Editor with inline highlighting, findings panel, keep-or-accept
- [ ] Confidence slider over calibrated values
- [ ] Context controls chosen by betweenness ([ADR-015](02-decisions.md#adr-015-context-variables-chosen-by-betweenness))

### Phase 5 — Tier 1 classifier

- [ ] Context vocabulary finalised (must precede large-scale labelling)
- [ ] Expand the 489 gold sentences into a labelled set; hold out a calibration split
- [ ] Fine-tune ModernBERT multi-label; export int8 ONNX
- [ ] Temperature-scale on held-out data; integrate behind the backend interface

### Phase 6 — Interfaces

- [ ] MCP server, HTTP API, CLI
- [ ] Middleware adapter with block buffering, latency budget and fail-open

### Deferred, by design

| Feature | Blocked on | Structural accommodation already made |
|---|---|---|
| Suggested corrections (Tier 2) | Identification being good enough to trust | Tier boundary in the ledger; `PREFER` modality separated for exactly this |
| Word round-trip | Demand | `Anchor` indirection; format-free training inputs ([ADR-019](02-decisions.md#adr-019-training-inputs-carry-no-format-markup)) |
| Live deployment | Phases 3–4 | Stateless core; int8 ONNX; swappable model backend |

---

## Sequencing traps

Three things must happen **earlier than they feel necessary**, because retrofitting them
is a re-review of every rule:

1. **The context vocabulary** ([ADR-015](02-decisions.md#adr-015-context-variables-chosen-by-betweenness))
   must be drafted before Pass 2, so rules reference shared variables rather than
   inventing per-rule preconditions. The betweenness analysis runs later, but the
   vocabulary cannot.
2. **The calibration split** must be held out before any labelling at scale, or the
   confidence numbers in Phase 3 are fitted on their own training data.
3. **The dogfood gate** must be in CI before the first rule is accepted, not after the
   first hundred. Octavius's entire failure is what happens when the quality gate arrives
   after the volume.
