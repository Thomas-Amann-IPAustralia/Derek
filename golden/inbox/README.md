# Span inbox

Drop a `derek-spans-*.jsonl` export from the annotator
(<https://thomas-amann-ipaustralia.github.io/Derek/annotate/>) in this directory
and commit it. You can do that through github.com with no checkout and no Python.

`.github/workflows/apply-spans.yml` then replays it:

```bash
python tools/annotate/apply_spans.py golden/inbox/*.jsonl            # writes
python tools/annotate/apply_spans.py golden/inbox/*.jsonl --dry-run  # validates only
```

The replay writes `golden/spans.jsonl`, rebuilds `ledger/rules.jsonl` from it, and
moves the export to `golden/applied/` under the date it landed.

**Export early and often.** Until a file gets here, the spans exist in exactly one
browser profile. Every export carries everything you have marked and every op
carries an id that `golden/span_ops.jsonl` records, so uploading the same file
twice does nothing the second time.

**One bad op refuses the whole file.** A span whose quote no longer matches the
text at its offsets, an example that overlaps the rule it illustrates (D-5), a
span on a page `corpus/eligibility.yaml` excludes (D-4), or an export built
against a different renderer — any of these stops the file rather than landing
half of it. The message names the span.
