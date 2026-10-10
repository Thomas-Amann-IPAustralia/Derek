# Drafting probes

Paid responses kept as records (ADR-003), outside `golden/drafts/` so that
nothing reads them as drafts.

- `2026-10-10-prepositions-medium.json`: the first smoke test of `gpt-6.1-sol`,
  at medium effort, as `draft_spans.py` wrote it. 437 reasoning tokens; one of
  the page's four labelled examples attached, with the note "Intentionally
  omitted". $0.022.
- `2026-10-10-prepositions-high.json`: the same page and prompt at high effort,
  over the streaming transport. 2,482 reasoning tokens; all four examples, each
  with the manual's polarity. $0.035. It is the draft now cached for the page.

Two earlier high-effort attempts without streaming failed with "upstream request
failed" on every retry, which is why the adapter streams. See ADR-027.
