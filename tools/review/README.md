# Review tool

Round 1 of rule review: deciding which of the 720 extracted candidates a computer
could realistically check in a piece of writing. See
[docs/04-roadmap.md](../../docs/04-roadmap.md) for where this sits.

```bash
python tools/review/server.py          # http://localhost:8765
DEREK_REVIEW_PORT=9000 python tools/review/server.py
DEREK_REVIEWER=TA python tools/review/server.py    # or set initials in the app
```

Stdlib only. No build step, no npm, nothing to install. It opens a browser at a
phone-shaped layout that works equally well on a desktop.

---

## What it writes

Everything lands in `ledger/`, in git, as plain JSONL — so every decision is a
reviewable diff with a name and a timestamp on it, and nothing is trapped in a
database ([ADR-008](../../docs/02-decisions.md#adr-008-human-acceptance-is-a-gate-not-a-review-queue)).

| File | What it holds |
|---|---|
| `rules.jsonl` | The decisions themselves. Status, scope, and the full `review.history` of every transition, including undos. |
| `review_activity.jsonl` | Attention-check outcomes per reviewer. Created on first use. |
| `example_reviews.jsonl` | Verdicts on individual example sentences. Created on first use. |

Nothing the pipeline owns (`uid`, `source`, `derivation`) can be written from the UI;
the API rejects it. So a rebuild can never clobber a human decision, and a human can
never corrupt a rule's provenance.

---

## Four things that look like friction and are not

**Clarity starts blank and a rule cannot be kept until it is set.** The extractor
deliberately makes no claim about how clear a rule is — asserting one would be a
judgement nobody made. Pre-filling a default would quietly manufacture that judgement
720 times.

**Rejections need a reason from a closed list.** "We binned 300 rules" is a statistic.
"We binned 80 because they govern images rather than text" is a fix to the extractor.
The reason is the useful output of this round, not the count.

**Decisions faster than 2.5 seconds score nothing and are marked `(hasty)`.** The
gamification exists to make a tedious job bearable; the moment it can buy speed at
the cost of attention it is working against the thing it was added to support. The
mark also makes a rushed batch findable afterwards.

**The leaderboard is computed from `review.history`, never stored.** There is no score
field anyone can write to, so it cannot be inflated, and clearing browser storage
loses your local streak but not a single decision.

---

## The field guide

`glossary.json` is the plain-language meaning of every option a reviewer can pick:
what it means, what it does to the data, and when to choose it. It is written for
someone who has never seen this repository.

It is not optional documentation. `server.py` checks it against the vocabularies in
`derek/ledger/model.py` at startup and **refuses to start** if a value exists in code
without an explanation, or an explanation survives a value that no longer exists.
Adding a `Unit` or a `Clarity` level without explaining it is a startup failure, not
a silent unlabelled button.

`tests/test_review_tool.py` asserts the same thing, plus the guard rails above.

---

## Example checking

The second mode checks example *sentences* rather than rules. Today it serves the
gold examples harvested from the manual's own `Write this` / `Not this` blocks —
which the dogfood gate and confidence calibration will be measured against
([ADR-011](../../docs/02-decisions.md#adr-011-the-dogfood-gate),
[ADR-013](../../docs/02-decisions.md#adr-013-confidence-is-calibrated-not-raw))
and which nobody has read end to end. Harvesting artefacts do exist in there; finding
them is the point.

When `ledger/training_candidates.jsonl` exists, the same screens serve that instead:

```json
{"id": "syn-0001", "rule_uid": "f8f3ddac1581e5c6", "rule": "Use numerals with the percentage sign",
 "text": "About fifteen per cent of respondents agreed.", "polarity": "violating"}
```

Same shape, same decisions, no second tool to learn — which is the point of building
it this way now rather than later.

---

## Keyboard

| Key | Rules | Examples |
|---|---|---|
| `→` / `K` | Keep (opens the scope sheet) | Good example |
| `←` / `B` | Bin (opens the reason sheet) | Bad example |
| `↓` / `D` | Not sure | Not sure |
| `N` | Not text at all — one keystroke, every field it implies is determined | — |
| `W` | Keep, reworded | — |
| `U` | Undo the last decision | — |
| `?` | Field guide | — |

Cards can also be dragged.
