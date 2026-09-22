# Inbox

Drop a decision export here — the JSONL file the
[published dashboard](https://thomas-amann-ipaustralia.github.io/Derek/) downloads
when you press **Download my decisions**.

You can do it from a browser: **Add file → Upload files**, then commit. No checkout,
no Python.

`.github/workflows/apply-review.yml` then replays the file with
[`tools/review/apply_decisions.py`](../../tools/review/apply_decisions.py), which runs the
same guard rails as the local review server — a rule still cannot be kept without
`clarity`, and `uid` / `source` / `derivation` still cannot be written from a reviewer's
hands ([ADR-008](../../docs/02-decisions.md#adr-008--human-acceptance-is-a-gate-not-a-review-queue)).
If any line would break one of those, it refuses the whole file and says which line and
why, rather than landing half a session in the ledger.

What happens to your file:

| | |
|---|---|
| `ledger/rules.jsonl` | gets the decisions, with **your** timestamps, not the upload's |
| `ledger/review_ops.jsonl` | records every op applied, so re-uploading the same file does nothing the second time |
| `ledger/applied/` | your file, kept under the date it landed |

Opening a pull request with the file instead of committing to `main` validates it
without writing anything.
