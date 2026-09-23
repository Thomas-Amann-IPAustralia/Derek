#!/usr/bin/env python3
"""Replay a span export into the golden set and the ledger — ADR-022, ADR-023.

    python tools/annotate/apply_spans.py golden/inbox/*.jsonl
    python tools/annotate/apply_spans.py export.jsonl --dry-run
    python tools/annotate/apply_spans.py export.jsonl --skip-invalid

The return leg of the annotator. Spans are marked in a browser, queued in
``localStorage`` and downloaded as JSONL; nothing is a decision until it lands
here, which is the same boundary the triage app draws (ADR-022) and the same
reason: everything a static page asserts about its own data is unverifiable.

Three stages, in this order and only this order:

1. **Validate and write ``golden/spans.jsonl``.** Every span is re-resolved
   against the corpus, so a quote that no longer matches its offsets is a
   refusal rather than a silent re-anchoring.
2. **Rebuild the ledger.** This is what mints each rule's uid — the browser
   never computes one, so the mapping from span to rule exists only after this
   step.
3. **Replay the reviewer's tags through ``server._apply``.** The same chokepoint
   the triage app uses, with the same refusals, recording the same history at the
   reviewer's own timestamp. The build never writes a review status.

One bad op refuses the whole file rather than landing half a session, and the
whole run is idempotent: op ids are recorded in ``golden/span_ops.jsonl``, so
re-uploading the same export does nothing the second time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
REVIEW = REPO / "tools" / "review"

sys.path.insert(0, str(REPO))

from derek.corpus.eligibility import load_eligibility              # noqa: E402
from derek.corpus.normalise import NormalisedPage                  # noqa: E402
from derek.extract.blocks import RENDER_VERSION, parse_blocks      # noqa: E402
from derek.extract.golden import (                                 # noqa: E402
    RULE, SPAN_KINDS, GoldenError, GoldenSet, Span, load_golden, resolve_span,
    span_id, write_golden,
)

PAGES = REPO / "corpus" / "pages"
ELIGIBILITY = REPO / "corpus" / "eligibility.yaml"
GOLDEN_SPANS = REPO / "golden" / "spans.jsonl"
GOLDEN_PAGES = REPO / "golden" / "pages.jsonl"
SPAN_OPS = REPO / "golden" / "span_ops.jsonl"
LEDGER = REPO / "ledger" / "rules.jsonl"

KNOWN_OPS = frozenset({"span", "span_del", "page", "decide", "meta"})


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SpanOpError(ValueError):
    """An op that cannot be trusted. Names the op and why."""


# ---------------------------------------------------------------------------
# The chokepoint
# ---------------------------------------------------------------------------

def apply_op(gs: GoldenSet, op: dict, *, eligibility, page_text) -> str | None:
    """Fold one op into the golden set. The analogue of ``server._apply``.

    Returns a short description of what it did, or ``None`` for an op that is
    provenance rather than a change.
    """
    kind = op.get("op")
    if kind not in KNOWN_OPS:
        raise SpanOpError(f"unknown op {kind!r}")
    if kind == "meta":
        return None
    if not op.get("op_id"):
        raise SpanOpError("op has no op_id, so it cannot be de-duplicated")
    by = (op.get("by") or "").strip()
    if not by:
        raise SpanOpError("op has no reviewer initials")

    if kind == "decide":
        return None            # handled in stage 3, through server._apply

    # A `span` op carries its page inside the span record; `page` and `span_del`
    # carry it at the top level, because they are about the page rather than
    # about a span.
    page = op.get("page_path") or (op.get("span") or {}).get("page_path")
    if not page:
        raise SpanOpError("op names no page")
    if not eligibility.decide(page)[0]:
        raise SpanOpError(
            f"{page} is not a rule source — corpus/eligibility.yaml excludes it, "
            f"and eligibility is a property of the page, not a per-rule judgement "
            f"(ADR-005)")
    text = page_text(page)
    if text is None:
        raise SpanOpError(f"{page} is not in the corpus")

    if kind == "page":
        status = op.get("status")
        if status not in ("in_progress", "complete"):
            raise SpanOpError(f"unknown page status {status!r}")
        gs.swept[page] = {
            "schema_version": 1, "page_path": page,
            "page_sha256": op.get("page_sha256", ""),
            "status": status, "by": by, "at": op.get("at", ""),
            "note": op.get("note", ""),
            "dropped": op.get("dropped", []),
        }
        return f"page {page} marked {status}"

    if kind == "span_del":
        key = op.get("key") or ""
        before = len(gs.spans.get(page, []))
        gs.spans[page] = [s for s in gs.spans.get(page, [])
                          if _key(s) != key]
        # A rule going away takes its examples with it: an orphaned example has
        # nothing to illustrate, and `golden_candidates` would refuse the set.
        alive = {s.span_id for s in gs.spans[page] if s.kind == RULE}
        gs.spans[page] = [s for s in gs.spans[page] if not s.of or s.of in alive]
        removed = before - len(gs.spans[page])
        return f"removed {removed} span(s) from {page}" if removed else None

    # kind == "span"
    raw = op.get("span") or {}
    span = _span_from_op(raw, page, by, op.get("at", ""), text)
    gs.spans.setdefault(page, [])
    gs.spans[page] = [s for s in gs.spans[page] if s.span_id != span.span_id]
    gs.spans[page].append(span)
    return f"{span.kind} span on {page}: {span.quote[:48]!r}"


def _key(span: Span) -> str:
    """The browser's local identity for a span: the tuple it was drawn at."""
    return f"{span.block_id}|{span.start}|{span.end}|{span.kind}"


def _span_from_op(raw: dict, page: str, by: str, at: str, text: str) -> Span:
    anchor = raw.get("anchor") or {}
    kind = raw.get("kind")
    if kind not in SPAN_KINDS:
        raise SpanOpError(f"unknown span kind {kind!r}")

    block_id = anchor.get("block_id") or ""
    start, end = int(anchor.get("start", 0)), int(anchor.get("end", 0))
    quote = anchor.get("quote", "")

    blocks = parse_blocks(page, text)
    block = next((b for b in blocks if b.id == block_id), None)
    if block is None:
        raise SpanOpError(
            f"{page}: block {block_id} is not in this page. The export was built "
            f"against a different corpus or a different renderer.")
    if not (0 <= start < end <= len(block.plain)):
        raise SpanOpError(
            f"{page}: span [{start}:{end}] is outside block {block_id}, "
            f"which is {len(block.plain)} characters")
    actual = block.plain[start:end]
    if actual != quote:
        raise SpanOpError(
            f"{page}: span [{start}:{end}] in block {block_id} holds {actual[:60]!r}, "
            f"but the export recorded {quote[:60]!r}. The text moved under the span.")

    # The browser references a parent rule by the tuple it was drawn at, because
    # it cannot mint a span_id. Resolve it here.
    of = raw.get("of") or ""
    if of and "|" in of:
        parts = of.split("|")
        of = span_id(page, parts[0], int(parts[1]), int(parts[2]), parts[3])

    return Span(
        span_id=span_id(page, block_id, start, end, kind),
        kind=kind, page_path=page,
        page_sha256=raw.get("page_sha256", ""),
        block_id=block_id, start=start, end=end, quote=quote,
        prefix=anchor.get("prefix", ""), suffix=anchor.get("suffix", ""),
        of=of,
        tags=dict(raw.get("tags") or {}),
        preconditions=tuple(raw.get("preconditions") or ()),
        disambiguator=raw.get("disambiguator", ""),
        seed_uid=raw.get("seed_uid", ""),
        by=by, at=at,
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _page_reader():
    cache: dict[str, str | None] = {}

    def read(rel: str) -> str | None:
        if rel not in cache:
            src = PAGES / rel
            cache[rel] = (
                NormalisedPage(rel, src.read_text(encoding="utf-8")).text
                if src.exists() else None
            )
        return cache[rel]

    return read


def _check_provenance(ops: list[dict]) -> None:
    """A span's offsets mean nothing without the renderer that produced them.

    The triage export needs no equivalent check: a decision is about a uid, and a
    uid is stable. A span is about a position, and a position is only meaningful
    against one projection of the text (ADR-023).
    """
    for op in ops:
        if op.get("op") != "meta":
            continue
        got = op.get("render_version")
        if got and got != RENDER_VERSION:
            raise SystemExit(
                f"{op.get('_source', '?')}: exported against renderer {got}, but "
                f"this checkout is {RENDER_VERSION}. Every offset in the file is "
                f"anchored to the old projection.\n"
                f"Rebuild the site, re-export, or run with --rebase once that "
                f"exists (ADR-024).")


def plan(ops, *, eligibility, already: set[str], skip_invalid: bool) -> dict:
    """Fold every op into a fresh copy of the golden set. Writes nothing."""
    gs = load_golden(GOLDEN_SPANS, GOLDEN_PAGES, eligibility)
    read = _page_reader()
    applied, skipped, errors, decides = [], [], [], []

    for op in ops:
        oid = op.get("op_id") or ""
        if oid and oid in already:
            skipped.append((op, "already applied"))
            continue
        try:
            what = apply_op(gs, op, eligibility=eligibility, page_text=read)
        except (SpanOpError, GoldenError, ValueError) as exc:
            errors.append((op, str(exc)))
            if not skip_invalid:
                break
            continue
        if op.get("op") == "decide":
            decides.append(op)
        if what:
            applied.append((op, what))
        elif op.get("op") not in ("meta",):
            applied.append((op, f"{op.get('op')} (no change)"))

    # Checked after every op is folded, not per op: a sweep is a statement about
    # the page as a whole, and whether it destroys something depends on the spans
    # in the same export.
    if not errors or skip_invalid:
        errors.extend(_check_sweeps(gs, read))
        if errors and not skip_invalid:
            applied = []

    return {"golden": gs, "applied": applied, "skipped": skipped,
            "errors": errors, "decides": decides}


def _check_sweeps(gs, page_text) -> list[tuple[dict, str]]:
    """Refuse a sweep that would quietly discard something load-bearing.

    Marking a page swept makes every heading no span covers into a labelled
    negative, and the reconciler orphans the candidates behind them. That is the
    point — it is how absence becomes evidence (ADR-023) — but it is also the one
    place authority mode can destroy a judgement nobody revisited.

    Two classes are held back until the reviewer names them in `dropped`:

    * A candidate carrying **both** a compliant and a violating example. That
      pairing is the Style Manual's own editors saying "here is the right way and
      here is the wrong way", which is independent of anything Derek inferred and
      is the seed evaluation set ADR-011 rests on. Dropping one should cost a
      sentence of explanation.
    * A candidate already **accepted or amended**. Someone read it and said yes.
      A sweep disagreeing with that is fine, but it should be deliberate.

    A `rejected` or `deferred` candidate needs no listing: rejection agrees with
    the sweep, and deferral is the absence of a judgement rather than one.
    """
    from derek.extract.golden import golden_rules
    from derek.ledger.store import load_ledger

    if not gs.authoritative or not LEDGER.exists():
        return []

    rules = load_ledger(LEDGER)
    problems: list[tuple[dict, str]] = []

    for page in sorted(gs.authoritative):
        text = page_text(page)
        if text is None:
            continue
        marker = gs.swept.get(page, {})
        listed = {d.get("uid") for d in marker.get("dropped", []) if d.get("uid")}
        kept = {cand.uid for _, cand in golden_rules(page, text, gs.spans.get(page, []))}

        at_risk = []
        for rule in rules.values():
            if rule.source.page_path != page or rule.uid in kept or rule.uid in listed:
                continue
            if rule.review.status in ("accepted", "amended"):
                at_risk.append((rule, f"already {rule.review.status}"))
            elif rule.review.status in ("rejected", "deferred"):
                # The docstring's promise, which the code did not keep: a
                # rejected candidate with the manual's pair was listed anyway,
                # so the first sweep of commas.md would have been refused over
                # two headings its reviewer had already binned.
                continue
            elif rule.compliant_examples and rule.violating_examples:
                at_risk.append((rule, "carries the manual's own paired examples"))

        for rule, why in at_risk:
            problems.append((
                {"op": "page", "op_id": marker.get("op_id", ""),
                 "_source": marker.get("_source", page)},
                f"sweeping {page} would drop {rule.uid} ({why}): "
                f"{rule.source.statement[:60]!r}. Mark it as a rule, or list it in "
                f"the page's `dropped` with a reason for letting it go."))
    return problems


def rebase(dry_run: bool = False) -> int:
    """Re-anchor every recorded span onto the corpus as it now stands.

    ADR-024's unfreeze step. While the corpus is frozen every span resolves by
    `block_id` and this does nothing; after an unfreeze the text has moved, and
    each span is re-found by its quote within the same heading, disambiguated by
    the 32 characters either side that were stored for exactly this.

    Anything that does not resolve **uniquely** is reported for a human rather
    than guessed at — the same posture `derek.ledger.reconcile` takes on lineage,
    and for the same reason: a wrong re-anchoring silently moves somebody's
    judgement onto text they never read, and it does not announce itself, because
    a wrong offset still resolves to *some* text.
    """
    from dataclasses import replace

    from derek.extract.golden import Span, resolve_span

    eligibility = load_eligibility(ELIGIBILITY)
    gs = load_golden(GOLDEN_SPANS, GOLDEN_PAGES, eligibility)
    read = _page_reader()
    moved, steady, lost = 0, 0, []

    for page in sorted(gs.spans):
        text = read(page)
        if text is None:
            lost.append((page, "", "the page is no longer in the corpus"))
            continue
        blocks = parse_blocks(page, text)
        fresh: list[Span] = []
        for span in gs.spans[page]:
            try:
                r = resolve_span(span, blocks)
            except GoldenError as exc:
                lost.append((page, span.span_id, str(exc)))
                fresh.append(span)          # keep it; a human decides
                continue
            if r.rebased:
                moved += 1
                fresh.append(replace(
                    r.span,
                    span_id=span_id(page, r.span.block_id, r.span.start,
                                    r.span.end, r.span.kind),
                    page_sha256="",
                    prefix=r.block.plain[max(0, r.span.start - 32):r.span.start],
                    suffix=r.block.plain[r.span.end:r.span.end + 32],
                ))
            else:
                steady += 1
                fresh.append(span)
        gs.spans[page] = fresh

    print(f"{steady} span(s) still resolve by block id; {moved} re-anchored by quote.")
    if lost:
        print(f"\n{len(lost)} span(s) could not be placed:", file=sys.stderr)
        for page, sid, why in lost:
            print(f"  {page} {sid}: {why}", file=sys.stderr)
        print("\nThey are left in golden/spans.jsonl unchanged. Open the page in the "
              "annotator and re-mark them, or delete them.", file=sys.stderr)

    if dry_run:
        print("\n--dry-run: nothing written.")
        return 1 if lost else 0
    if moved:
        # A re-anchored span changes its id, because the id is the tuple it sits
        # at. Old ids in golden/span_ops.jsonl stay as history; they are an
        # idempotency record of what was applied, not a reference to a live span.
        spans, pages = write_golden(gs, GOLDEN_SPANS, GOLDEN_PAGES)
        print(f"\nRewrote {spans} span(s). Rebuild with: python -m derek.extract.build")
    return 1 if lost else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and report; write nothing")
    ap.add_argument("--skip-invalid", action="store_true",
                    help="apply what is valid instead of refusing the whole file")
    ap.add_argument("--rebase", action="store_true",
                    help="re-anchor the recorded spans onto the current corpus "
                         "(ADR-024's unfreeze step); takes no files")
    args = ap.parse_args(argv)

    if args.rebase:
        if args.files:
            ap.error("--rebase re-anchors what is already recorded; it takes no files")
        return rebase(dry_run=args.dry_run)
    if not args.files:
        ap.error("no export given (or use --rebase)")

    apply_decisions = _load("derek_apply_decisions", REVIEW / "apply_decisions.py")
    server = apply_decisions._load_server()
    server.load_glossary()          # the same startup drift check as everywhere else

    eligibility = load_eligibility(ELIGIBILITY)
    ops = apply_decisions.read_ops(args.files)
    _check_provenance(ops)

    already = apply_decisions.applied_ids(SPAN_OPS)
    report = plan(ops, eligibility=eligibility, already=already,
                  skip_invalid=args.skip_invalid)

    for op, what in report["applied"]:
        print(f"  {what}")
    if report["skipped"]:
        print(f"  ({len(report['skipped'])} op(s) already applied)")

    if report["errors"]:
        print(f"\n{len(report['errors'])} op(s) refused:", file=sys.stderr)
        for op, why in report["errors"]:
            print(f"  {op.get('_source', '?')} {op.get('op_id', '')[:8]}: {why}",
                  file=sys.stderr)
        if not args.skip_invalid:
            print("\nNothing was written. One bad op holds back the whole file, so "
                  "a session lands complete or not at all. Use --skip-invalid to "
                  "apply the rest.", file=sys.stderr)
            return 1

    if args.dry_run:
        print(f"\n--dry-run: {len(report['applied'])} op(s) would apply. "
              f"Nothing written.")
        return 0
    if not report["applied"] and not report["decides"]:
        print("\nNothing to do.")
        return 0

    # Stage 1 — the golden set.
    spans, pages = write_golden(report["golden"], GOLDEN_SPANS, GOLDEN_PAGES)

    # Stage 2 — the ledger, which is what mints each rule's uid.
    from derek.extract.build import build as build_ledger
    build_ledger(LEDGER, check=False)

    # Stage 3 — the reviewer's decisions, through the gate.
    tagged, decided = _apply_decisions(report, server, apply_decisions)

    _record(report, apply_decisions)

    print(f"\nWrote {spans} span(s) and {pages} page marker(s) to golden/.")
    print(f"Rebuilt the ledger; {tagged} rule(s) tagged and {decided} "
          f"candidate(s) rejected through server._apply.")
    return 0


def _apply_decisions(report, server, apply_decisions) -> tuple[int, int]:
    """Replay the reviewer's judgements as ordinary review decisions.

    The span record carries `tags` as provenance and training data; the ledger's
    `review` block is the runtime record, and only `server._apply` may write it.
    One writes the other, once — so every refusal in that function still applies
    and `review.history` still says who decided and when.
    """
    from derek.extract.golden import golden_rules

    rules = server.load_ledger(LEDGER)
    read = _page_reader()
    gs = report["golden"]
    n, missing = 0, []

    for page in sorted(gs.spans):
        text = read(page)
        if text is None:
            continue
        for span, cand in golden_rules(page, text, gs.spans[page]):
            if not span.tags:
                continue
            rule = rules.get(cand.uid)
            if rule is None:
                missing.append((page, cand.uid))
                continue
            patch = {k: v for k, v in span.tags.items()
                     if k in server.EDITABLE and v not in ("", [], None)}
            if not patch.get("review_status"):
                continue
            with apply_decisions._at(server, span.at):
                server._apply(rule, patch, span.by or "ANON")
            n += 1

    if missing:
        # The build just ran from this exact golden set, so every rule span must
        # have produced a ledger entry. If one did not, the two disagree and
        # writing the rest would hide that.
        raise SystemExit(
            "the rebuilt ledger is missing rules the golden set produced:\n  "
            + "\n  ".join(f"{p} {u}" for p, u in missing))

    # The explicit rejections: "delete this candidate" in the annotator, which
    # the ledger records rather than deletes. Replayed after the build so the
    # reviewer's reason sits on top of whatever the sweep derived — a reason from
    # the closed list is a fix to the extractor, where "not marked in the golden
    # set" only restates the input.
    decided = 0
    for op in report["decides"]:
        rule = rules.get(op.get("uid"))
        if rule is None:
            continue
        with apply_decisions._at(server, op.get("at", "")):
            server._apply(rule, dict(op.get("patch") or {}), op.get("by") or "ANON")
        decided += 1

    if n or decided:
        server.write_ledger(LEDGER, rules.values())
    return n, decided


def _record(report, apply_decisions) -> None:
    """Append applied op ids, so re-uploading the same export is a no-op."""
    SPAN_OPS.parent.mkdir(parents=True, exist_ok=True)
    with SPAN_OPS.open("a", encoding="utf-8") as fh:
        for op, what in report["applied"]:
            row = {k: v for k, v in op.items() if not k.startswith("_")}
            row["applied_from"] = op.get("_source", "")
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
