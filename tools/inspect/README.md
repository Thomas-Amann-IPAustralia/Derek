# Rule inspector

**<https://thomas-amann-ipaustralia.github.io/Derek/inspect/>**

One rule at a time. On the left, everything the repository records about it. On the
right, the page it came from, reconstructed from the frozen corpus, with the text that
states the rule highlighted where it sits. Drag the bar between them to set the ratio.

```bash
python tools/inspect/build_static.py --out site/inspect
python -m http.server -d site 8000        # → http://localhost:8000/inspect/
```

Stdlib only. No build step, no npm, nothing to install. Read-only.

---

## Why this exists

Whether a rule is fit for purpose is mostly visible only in its context. A span cut from
the middle of a qualified sentence, an example that belongs to the paragraph above, a
heading that was a label rather than an instruction ([docs/07](../../docs/07-extraction-hand-audit.md)):
none of these show on a card that holds the rule alone. The [triage app](../review/)
shows a rule without its page, and the [annotator](../annotate/) shows a page without
one rule's whole story. This shows both, side by side.

## What the left pane holds

| Card | From |
|---|---|
| **Where it came from** | The span or heading the rule is built from, who recorded it, which drafting models proposed it, the block and offsets, the extractor version, earlier uids, and links to the live page, the corpus file at that line, and the annotator |
| **What it checks** | `violation_condition`, `specification`, modality, unit, direction, clarity, `applies_to` (each explained from [`glossary.json`](../review/glossary.json)), conditions and written-down interpretations |
| **Examples** | Each compliant and violating example, and whether it is a span on the page, found in the page text, or not on the page at all |
| **Review** | Status, decider, note, and one timeline of derivation, span marking, adjudication and every status change |
| **Consensus** | Every [ADR-027](../../docs/02-decisions.md#adr-027--two-model-consensus-adjudicated-replaces-marking-by-hand) item about the rule: who found it, what the other model said, the second reading, and the adjudicator's decision and reason |
| **Detection & validation** | Method, tier, matcher, proposals in `ledger/proposals/`, validation, and confidence (`null` shown as unvalidated, D-12) |
| **Golden-set lint** | `derek.eval.golden_lint` findings for this rule, as of the build |
| **Raw records** | The ledger row, the span record and the consensus items, verbatim |

On the right, the rule's span is highlighted, and so are its examples and its "when"
conditions. The page's other rules are underlined, and clicking one opens it. Clicking an
example on the page finds it on the left.

## How a highlight is placed, and how far to trust it

Which span a rule came from is not stored on the rule. It is whichever span
`derek.extract.golden.golden_rules` turns into that rule's uid on every rebuild. So the
build asks that function, rather than letting the page guess by matching text, and
records *how* each highlight was placed:

| Placement | Meaning |
|---|---|
| **Exact (span)** | The span in `golden/spans.jsonl` that mints this uid ([ADR-023](../../docs/02-decisions.md#adr-023--the-golden-span-set-is-a-declared-extraction-input)) |
| **Exact (heading)** | The heading block at the source line, for a rule the heading walk derived ([ADR-002](../../docs/02-decisions.md#adr-002--deterministic-candidate-identity)) |
| **Located by text** | The rule's span has left the golden set (it is `orphaned`), so its statement was found at its source line |
| **Not found** | Nothing is drawn, rather than something wrong |

`tests/test_inspect_offline.py` checks the shipped placement against `golden_rules`
itself, and fails if a live rule is placed any way but exactly.

## What it does not do

**It writes nothing.** No op log, no export. A rule is changed in the annotator or the
triage app, through their single gate ([ADR-022](../../docs/02-decisions.md#adr-022--the-review-ui-is-published-the-gate-moves-to-the-apply-step)).
`localStorage` holds only the pane ratio, the filter, the last rule and the theme, and
`tests/test_inspect_offline.py` asserts it never touches the other apps' op logs, which
share the origin.

**It decides nothing in the browser.** Placement, example matching and consensus linking
are done in Python at build time. The page draws offsets it was given.

## Using it

| Key | |
|---|---|
| `J` / `K` | Next / previous rule under the filter |
| `/` | Find a rule by words, uid, heading or page |
| `S` | Scroll the page back to the span |
| `O` | Show or hide the page's other rules |
| `[` / `]` | Narrow / widen the details pane; or drag the bar, or focus it and use the arrow keys |
| `\` | Half and half |
| `C` | Copy the uid |

The URL hash is the rule's uid, so `…/inspect/#c9a7cbdd48e01002` opens that rule.
