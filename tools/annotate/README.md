# Span annotator

**<https://thomas-amann-ipaustralia.github.io/Derek/annotate/>**

The Style Manual, reconstructed from the frozen corpus, with the text selectable.
Select the span that states a rule; it becomes a rule in the ledger.

```bash
python tools/annotate/build_static.py --out site/annotate
python -m http.server -d site 8000        # → http://localhost:8000/annotate/
python tools/annotate/apply_spans.py golden/inbox/*.jsonl
```

Stdlib only. No build step, no npm, nothing to install.

---

## Why this exists

The extractor reads rules off heading structure (ADR-002), and the hand audit in
[docs/07](../../docs/07-extraction-hand-audit.md) measured what that costs:

| | |
|---|---|
| Sampled candidates that soundly state a rule | 75% |
| **"Label, not statement"** — real rule, unusable wording | **18%** |
| Not a rule at all | 7% |
| Real rules stated as description, invisible to every branch | **~60 corpus-wide** |

The 18% and the 7% are survivable — a wrong card costs twenty seconds. The ~60 are
not: they never reach a card, so no amount of card-by-card triage finds them.
`legal-material/bills-and-explanatory-material.md` has four real rule headings and
yields zero candidates; `treaties.md` has nine headings and zero; `pronouns.md` has
seventeen and zero.

Here the manual is the document and the reviewer selects the text, so a rule
stated in prose is exactly as reachable as one stated in a heading. The result is
the **golden set** ([ADR-023](../../docs/02-decisions.md)): the authoritative rule
inventory, and the labelled data a future heuristic is fitted against *and
measured on*.

## What you mark

| | |
|---|---|
| **Rule** `R` | The text that states the rule. Carries the same tags the triage app sets. |
| **Write this** `C` | An example that complies, attached to the current rule. Optional. |
| **Not this** `V` | An example that violates. Optional. |
| **When** `P` | Text limiting when the rule applies. Optional — or type it in the rule's sheet. |

The extractor's 736 candidates are pre-seeded as dashed underlines. Confirm one
with `A`, adjust it by selecting different text and pressing `R`, or delete it
with a reason. **Text with no rule span on it is, by definition, not a rule.**

`F` marks a page swept. That is what turns absence into evidence: "I read this
page, these are all its rules" makes every unmarked heading a labelled negative,
which is what lets a heuristic be measured for precision rather than only recall.
Without it, "no span here" and "not looked at yet" are the same thing.

## Three things it deliberately does not do

**It never computes a ledger value.** No UID, no hash, no modality inference. A
span is recorded as the tuple it was drawn at — block, start, end, kind — and
Python mints its id and fills the extractor's defaults. The triage app has one JS
mirror of a Python function and documents its discomfort; a second one, a wrong
hash producing ops that point at UIDs which do not exist, would be much worse.

**It never edits the manual's wording.** A span *is* the wording
([ADR-017](../../docs/02-decisions.md#adr-017--ambiguity-is-classified-and-formalised)).
A restatement goes in `specification`, beside it, which is what detection
implements.

**It is not the record.** Spans queue in `localStorage`, export as JSONL, and are
replayed by `apply_spans.py` through the same `server._apply` the triage app uses
([ADR-022](../../docs/02-decisions.md)). The browser is a drafting surface.

## How a span stays attached to its text

Offsets index the **plain text** of one block, not the Markdown and not the page.
`derek/extract/blocks.py` is the single projection both sides use: it ships
`plain` plus inline `marks` as offsets into it, and the browser builds its DOM by
slicing `plain` at mark boundaries — so `element.textContent === block.plain` is
true by construction and a selection maps back exactly.

Block addresses are content-derived, so editing one paragraph changes that
paragraph's address and nothing else. `derek/extract/data/blocks.lock.json` pins
the whole projection and CI fails if it moves, because the dangerous failure is
not a span that fails to resolve but one that resolves to the wrong sentence.

Each span also stores its `quote` and 32 characters either side, which is what
lets it be re-found after the corpus unfreezes
([ADR-024](../../docs/02-decisions.md)).
