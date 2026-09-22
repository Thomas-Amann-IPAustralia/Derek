# Review tool

Card-by-card triage: one rule, one verdict, one gesture. Deciding which extracted
candidates a computer could realistically check in a piece of writing.

> **Identifying rules has moved to [`tools/annotate/`](../annotate/)**
> ([ADR-023](../../docs/02-decisions.md#adr-023--the-golden-span-set-is-a-declared-extraction-input)).
> The heading walk this queue is built from misses roughly 60 rules the manual states as
> description, and those never reach a card, so no number of passes over the queue finds
> them. Marking spans on the manual itself does.
>
> This app is **retained, not superseded**. Its shape is exactly right for the thousands
> of small independent judgements in Phase 5 — reviewing the synthetic training pairs —
> and it remains the fastest way to work a queue of candidates that already exists.

Two ways to run it. Same app, same screens, same decisions.

```bash
python tools/review/server.py          # http://localhost:8765
DEREK_REVIEW_PORT=9000 python tools/review/server.py
DEREK_REVIEWER=TA python tools/review/server.py    # or set initials in the app
```

**<https://thomas-amann-ipaustralia.github.io/Derek/>** — the same app, published as
files, for a machine that cannot run Python. Built by `build_static.py` and deployed by
`.github/workflows/pages.yml` on every push that changes the ledger.

Stdlib only. No build step, no npm, nothing to install. It opens a browser at a
phone-shaped layout that works equally well on a desktop.

---

## The published copy

A locked-down work machine has a browser and nothing else, and 736 decisions do not
get made on a laptop the reviewer only has in the evenings. So the app is also
published as a static site
([ADR-022](../../docs/02-decisions.md#adr-022--the-review-ui-is-published-the-gate-moves-to-the-apply-step)).
Nothing about deciding changes. Three things do.

**Decisions queue in the browser and come back as a file.** There is no server to
write to, so each decision is appended to an op log in `localStorage`, exported as
JSONL, and replayed into the ledger by `apply_decisions.py`. The op log is the same
shape as what the API would have received; the browser is a drafting surface, and
`ledger/rules.jsonl` is still the record.

```bash
python tools/review/build_static.py --out site      # → site/, ~1.1 MB
python tools/review/apply_decisions.py export.jsonl # → ledger/, as a git diff
python tools/review/apply_decisions.py export.jsonl --dry-run
```

Or, with no checkout at all: upload the file to [`ledger/inbox/`](../../ledger/inbox)
through github.com and `.github/workflows/apply-review.yml` does it for you, then moves
the file to `ledger/applied/`.

**The guard rails apply when the file lands, not when the button is pressed.**
`apply_decisions.py` runs the same `_apply` the server runs, so a rule still cannot be
kept without `clarity`, an `ambiguous_resolvable` reading still has to be written down,
and `uid` / `source` / `derivation` are still refused. One bad op refuses the whole
file rather than landing half a session. The page checks the same things while you
work, so you hear about it with the card still in front of you — but it is a courtesy,
not the gate. `tests/test_review_offline.py` asserts the distinction.

Every op carries an id, and applied ids are recorded in `ledger/review_ops.jsonl`, so
uploading the same export twice does nothing the second time. Export early and often:
a decision that exists only in a browser's local storage is one cleared cache from gone.

**Attention checks are not served there, and the leaderboard is a snapshot.** Checks
are graded server-side because a check whose answer is in the page is decoration; a
static site can only ship the answer, so it does not ask. The leaderboard is computed
from the ledger at build time, so it shows work that has been applied rather than work
still sitting in someone's browser. Both are said on the page rather than papered over.

---

## What it writes

Everything lands in `ledger/`, in git, as plain JSONL — so every decision is a
reviewable diff with a name and a timestamp on it, and nothing is trapped in a
database ([ADR-008](../../docs/02-decisions.md#adr-008--human-acceptance-is-a-gate-not-a-review-queue)).

| File | What it holds |
|---|---|
| `rules.jsonl` | The decisions themselves. Status, scope, and the full `review.history` of every transition, including undos. |
| `review_activity.jsonl` | Attention-check outcomes per reviewer. Created on first use. |
| `example_reviews.jsonl` | Verdicts on individual example sentences. Created on first use. |
| `review_ops.jsonl` | Every op replayed from a published-dashboard export, so a re-upload is a no-op. Created on first use. |
| `inbox/` · `applied/` | Exports waiting to be applied, and the ones that have been, under the date they landed. |

Nothing the pipeline owns (`uid`, `source`, `derivation`) can be written from the UI;
the API rejects it. So a rebuild can never clobber a human decision, and a human can
never corrupt a rule's provenance.

---

## Four things that look like friction and are not

**Clarity starts blank and a rule cannot be kept until it is set.** The extractor
deliberately makes no claim about how clear a rule is — asserting one would be a
judgement nobody made. Pre-filling a default would quietly manufacture that judgement
once per candidate, at the scale of the whole ledger.

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
([ADR-011](../../docs/02-decisions.md#adr-011--the-dogfood-gate),
[ADR-013](../../docs/02-decisions.md#adr-013--confidence-is-calibrated-not-raw))
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
