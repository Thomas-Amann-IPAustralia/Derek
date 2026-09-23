"""The golden span set: rules a human marked on the manual itself (ADR-023).

``golden/spans.jsonl`` is a **declared input to Layer 1**, exactly as
``corpus/eligibility.yaml`` and ``derek/extract/data/imperative_headings.json``
already are. ``derek.extract.build`` reads it alongside the corpus, so
extraction stays a pure function of the corpus plus its declared inputs and
``build --check`` stays byte-reproducible (D-7). No model runs here and no model
decides a rule exists — a human does, which is ADR-008's posture moved one layer
earlier.

Why it exists: the heading walk misses roughly 60 real rules corpus-wide because
the Style Manual states them as description rather than instruction, and those
never reach a reviewer at all (docs/07). Reviewing a queue can improve precision;
it cannot improve recall. Reading the document can do both.

**UID continuity is the point.** A span that exactly covers a heading block takes
that heading's title verbatim as its statement, so ``candidate_uid`` returns the
*same* uid and the reconciler files it ``unchanged`` with every review decision
intact. A span covering different text mints a different uid and the reconciler
links the lineage. Confirming the extractor's guess is therefore free, and
correcting it is handled by machinery that already existed.

Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from derek.extract.blocks import Block, parse_blocks
from derek.extract.candidates import Candidate, candidate_uid, classify_heading, normalise_statement
from derek.extract.segment import iter_nodes, parse_page

__all__ = [
    "SPAN_KINDS", "RULE", "EXAMPLE_KINDS", "GoldenError", "Span", "GoldenSet",
    "load_golden", "write_golden", "span_id", "resolve_span", "golden_candidates",
    "golden_rules",
]

REPO = Path(__file__).resolve().parents[2]
SPANS_PATH = REPO / "golden" / "spans.jsonl"
PAGES_PATH = REPO / "golden" / "pages.jsonl"

RULE = "rule"
EXAMPLE_KINDS = ("compliant", "violating")
SPAN_KINDS = frozenset({RULE, "compliant", "violating", "precondition"})
SCHEMA_VERSION = 1

# The example keys golden spans contribute. Deliberately not a label the manual
# itself uses, so they can never collide with a harvested `Write this` block —
# `_polarity_seed` reads both and the two must stay distinguishable.
GOLD_COMPLIANT = "golden compliant"
GOLD_VIOLATING = "golden violating"


class GoldenError(ValueError):
    """A span that cannot be trusted. Always names the span and why."""


@dataclass(frozen=True)
class Span:
    span_id: str
    kind: str
    page_path: str
    page_sha256: str
    block_id: str
    start: int
    end: int
    quote: str
    prefix: str = ""
    suffix: str = ""
    of: str = ""                       # the rule span this supports
    # Example spans sharing a group are ONE example that crosses blocks — a
    # list's lead-in and its items, which the block projection splits apart.
    # Without it "for example:" + "green" + "orange" + "red" became four
    # examples, three of them a single word that illustrates nothing.
    group: str = ""
    tags: dict = field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    disambiguator: str = ""
    seed_uid: str = ""
    by: str = ""
    at: str = ""

    def to_dict(self) -> dict:
        out = {
            "schema_version": SCHEMA_VERSION,
            "span_id": self.span_id,
            "kind": self.kind,
            "page_path": self.page_path,
            "page_sha256": self.page_sha256,
            "anchor": {
                "block_id": self.block_id, "start": self.start, "end": self.end,
                "quote": self.quote, "prefix": self.prefix, "suffix": self.suffix,
            },
            "of": self.of,
            "by": self.by,
            "at": self.at,
        }
        if self.group:
            out["group"] = self.group
        if self.kind == RULE:
            out["tags"] = dict(self.tags)
            out["preconditions"] = list(self.preconditions)
            if self.disambiguator:
                out["disambiguator"] = self.disambiguator
            if self.seed_uid:
                out["seed_uid"] = self.seed_uid
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "Span":
        anchor = raw.get("anchor") or {}
        kind = raw.get("kind", "")
        if kind not in SPAN_KINDS:
            raise GoldenError(f"unknown span kind {kind!r}")
        return cls(
            span_id=raw.get("span_id", ""),
            kind=kind,
            page_path=raw["page_path"],
            page_sha256=raw.get("page_sha256", ""),
            block_id=anchor.get("block_id", ""),
            start=int(anchor.get("start", 0)),
            end=int(anchor.get("end", 0)),
            quote=anchor.get("quote", ""),
            prefix=anchor.get("prefix", ""),
            suffix=anchor.get("suffix", ""),
            of=raw.get("of", ""),
            group=raw.get("group", ""),
            tags=dict(raw.get("tags") or {}),
            preconditions=tuple(raw.get("preconditions") or ()),
            disambiguator=raw.get("disambiguator", ""),
            seed_uid=raw.get("seed_uid", ""),
            by=raw.get("by", ""),
            at=raw.get("at", ""),
        )


@dataclass
class GoldenSet:
    spans: dict[str, list[Span]] = field(default_factory=dict)   # page_path -> spans
    swept: dict[str, dict] = field(default_factory=dict)         # page_path -> marker

    @property
    def authoritative(self) -> set[str]:
        """Pages a human has swept, where absence of a span means 'not a rule'."""
        return {p for p, m in self.swept.items() if m.get("status") == "complete"}

    def all_spans(self) -> list[Span]:
        return [s for page in sorted(self.spans) for s in self.spans[page]]


def span_id(page_path: str, block_id: str, start: int, end: int, kind: str) -> str:
    """Content-derived identity for a span.

    Hashed from the tuple the span was drawn at, so re-marking the same extent
    is idempotent and ``golden/spans.jsonl`` is a set rather than a log. SHA-256
    rather than blake2s only because the browser could compute the same value if
    it ever needed to — it does not, and deliberately does not try.
    """
    import hashlib

    h = hashlib.sha256()
    h.update(f"{page_path}\x00{block_id}\x00{start}\x00{end}\x00{kind}".encode("utf-8"))
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Reading and writing
# ---------------------------------------------------------------------------

def load_golden(spans_path: Path = SPANS_PATH, pages_path: Path = PAGES_PATH,
                eligibility=None) -> GoldenSet:
    """Read the golden set, refusing anything the ledger could not honour."""
    gs = GoldenSet()

    for lineno, raw in _rows(spans_path):
        try:
            span = Span.from_dict(raw)
        except (KeyError, GoldenError) as exc:
            raise GoldenError(f"{spans_path}:{lineno}: {exc}") from exc

        if eligibility is not None and not eligibility.decide(span.page_path)[0]:
            # D-4 / ADR-005: eligibility is a property of the page, declared once,
            # never a per-rule judgement. A span here would put a rule in the
            # ledger from a page the extractor is not allowed to read.
            raise GoldenError(
                f"{spans_path}:{lineno}: span on {span.page_path}, which "
                f"corpus/eligibility.yaml excludes (ADR-005)"
            )
        gs.spans.setdefault(span.page_path, []).append(span)

    for lineno, raw in _rows(pages_path):
        if "page_path" not in raw:
            raise GoldenError(f"{pages_path}:{lineno}: no page_path")
        gs.swept[raw["page_path"]] = raw

    for page in gs.spans:
        gs.spans[page].sort(key=lambda s: (s.block_id, s.start, s.end, s.kind))
    return gs


def _rows(path: Path):
    if not path.exists():
        return
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            yield lineno, json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldenError(f"{path}:{lineno}: {exc}") from exc


def write_golden(gs: GoldenSet, spans_path: Path = SPANS_PATH,
                 pages_path: Path = PAGES_PATH) -> tuple[int, int]:
    """Canonical form, so a re-run with no semantic change produces no diff.

    Same discipline as ``derek.ledger.store.write_ledger``, for the same reason:
    it is what makes "this changed nothing" observable rather than asserted.
    """
    spans = sorted(gs.all_spans(),
                   key=lambda s: (s.page_path, s.block_id, s.start, s.end, s.kind))
    _write(spans_path, [s.to_dict() for s in spans])
    _write(pages_path, [gs.swept[p] for p in sorted(gs.swept)])
    return len(spans), len(gs.swept)


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
            fh.write("\n")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Resolving a span against the text it was drawn on
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolved:
    span: Span
    block: Block
    text: str
    rebased: bool = False


def resolve_span(span: Span, blocks: list[Block]) -> Resolved:
    """Find the text a span points at. Never guesses.

    Three routes, tried in order — the same posture ``derek.ledger.reconcile``
    takes on lineage, and for the same reason: a wrong resolution silently moves
    a human's judgement onto text they never read.

    1. The block id, with the quote verifying. This is every span while the
       corpus is frozen (ADR-024).
    2. The quote, within the blocks under the same heading, disambiguated by the
       32 characters either side. This is the unfreeze path.
    3. The quote, uniquely, anywhere on the page.

    Anything that does not resolve uniquely raises.
    """
    by_id = {b.id: b for b in blocks}

    block = by_id.get(span.block_id)
    if block is not None and block.plain[span.start:span.end] == span.quote:
        return Resolved(span, block, span.quote)

    def _find(candidates: list[Block]) -> list[tuple[Block, int]]:
        hits: list[tuple[Block, int]] = []
        for b in candidates:
            at = b.plain.find(span.quote)
            while at != -1:
                before = b.plain[max(0, at - len(span.prefix)):at]
                after = b.plain[at + len(span.quote):at + len(span.quote) + len(span.suffix)]
                if (not span.prefix or before == span.prefix) and \
                   (not span.suffix or after == span.suffix):
                    hits.append((b, at))
                at = b.plain.find(span.quote, at + 1)
        return hits

    if not span.quote:
        raise GoldenError(
            f"span {span.span_id} on {span.page_path} has no quote and its block "
            f"{span.block_id} is gone — nothing to re-anchor to"
        )

    scope = [b for b in blocks
             if block is not None and b.heading_path == block.heading_path] or blocks
    hits = _find(scope) or _find(blocks)

    if len(hits) == 1:
        found, at = hits[0]
        moved = replace(span, block_id=found.id, start=at, end=at + len(span.quote))
        return Resolved(moved, found, span.quote, rebased=True)
    raise GoldenError(
        f"span {span.span_id} on {span.page_path} cannot be placed: "
        f"block {span.block_id} does not hold {span.quote[:60]!r} at "
        f"[{span.start}:{span.end}], and the quote "
        + (f"appears {len(hits)} times elsewhere on the page"
           if hits else "is not on the page at all")
        + ". Re-anchor it in the annotator, or fix the export."
    )


# ---------------------------------------------------------------------------
# Spans -> candidates
# ---------------------------------------------------------------------------

def golden_candidates(page_path: str, text: str, spans: list[Span]) -> list[Candidate]:
    """Turn one page's spans into rule candidates."""
    return [c for _, c in golden_rules(page_path, text, spans)]


def golden_rules(page_path: str, text: str,
                 spans: list[Span]) -> list[tuple[Span, Candidate]]:
    """Each rule span paired with the candidate it produces.

    The pairing is the primitive rather than a lookup afterwards, because the
    span-to-uid mapping is what ``tools/annotate/apply_spans.py`` needs to route
    a reviewer's tags to the right rule, and re-deriving it by matching statement
    text would be guessing at something that was computed exactly here.

    Reuses ``segment.parse_page``, ``blocks.parse_blocks``, ``candidate_uid`` and
    ``classify_heading`` rather than restating any of them: the whole point of
    UID continuity is that a golden rule and the heading candidate it confirms
    are computed by the same function.
    """
    if not spans:
        return []

    blocks = parse_blocks(page_path, text)
    root = parse_page(text)
    nodes = sorted(iter_nodes(root), key=lambda n: n.line_start)
    heading_block_ids = {b.id for b in blocks if b.kind == "heading"}
    node_by_line = {n.line_start: n for n in nodes}

    position = {b.id: i for i, b in enumerate(blocks)}
    resolved = {s.span_id: resolve_span(s, blocks) for s in spans}
    rules = [r for r in resolved.values() if r.span.kind == RULE]
    kids = [r for r in resolved.values() if r.span.kind != RULE]

    _refuse_orphans(page_path, rules, kids)
    _refuse_overlapping_examples(page_path, resolved, kids)

    out: list[tuple[Span, Candidate]] = []
    seen: dict[str, Span] = {}

    for r in sorted(rules, key=lambda r: (r.block.line, r.block.id, r.span.start)):
        span, block = r.span, r.block

        if block.kind == "heading" and span.start == 0 and span.end == len(block.plain):
            node = node_by_line.get(block.line)
            if node is None:
                raise GoldenError(
                    f"{page_path}: span {span.span_id} covers heading block "
                    f"{block.id} but no heading node sits at line {block.line}")
            if node.level <= 1:
                # ADR-002: a page title is the document, not a rule in it. The
                # extractor refuses this and so must a human's span, or the
                # ledger gains a rule whose statement is a page name.
                raise GoldenError(
                    f"{page_path}: span {span.span_id} covers the page title "
                    f"{node.title!r}, which is not a rule")
            # Verbatim from the node, not from `plain`. They differ in exactly one
            # heading in the corpus — the only one carrying emphasis — and taking
            # `plain` there would mint a second uid for a rule that already exists.
            statement = node.title
            heading_path = node.path
            level = node.level
            line_start = node.line_start
            body = node.body.strip()
            positional = True
        else:
            if not block.heading_path:
                raise GoldenError(
                    f"{page_path}: span {span.span_id} sits above the first heading, "
                    f"so it has no address in the page")
            statement = normalise_statement(r.text)
            heading_path = block.heading_path
            node = _enclosing(nodes, block)
            level = node.level if node else len(heading_path)
            line_start = block.line
            body = node.body.strip() if node else ""
            positional = False

        basis = heading_path + (f"#{span.disambiguator}",) if span.disambiguator \
            else heading_path
        uid = candidate_uid(page_path, basis, statement)

        if uid in seen:
            other = seen[uid]
            raise GoldenError(
                f"{page_path}: two rule spans resolve to the same rule id {uid}.\n"
                f"  {other.quote[:70]!r} at [{other.start}:{other.end}] in {other.block_id}\n"
                f"  {span.quote[:70]!r} at [{span.start}:{span.end}] in {span.block_id}\n"
                f"They state the same thing under the same heading. Widen one so "
                f"they differ, or set `disambiguator` on one to say they are "
                f"genuinely two rules."
            )
        seen[uid] = span

        # The classifier's verdict is recorded, not consulted: it is the
        # prediction a future heuristic has to beat, and comparing it against the
        # human's spans is the measurement ADR-023 exists to make possible.
        form = classify_heading(statement)[1] or "descriptive"

        examples = _examples_of(page_path, span, kids, position)

        preconditions = list(span.preconditions) + [
            k.text for k in kids
            if k.span.of == span.span_id and k.span.kind == "precondition"
        ]

        # A span carrying `seed_uid` confirms or corrects a heading candidate. If
        # it produced the same uid it IS that candidate and there is nothing to
        # supersede; if it produced a different one the human moved the rule, and
        # saying so beats letting the reconciler infer it from position.
        supersedes = span.seed_uid if span.seed_uid and span.seed_uid != uid else ""

        out.append((span, Candidate(
            uid=uid,
            page_path=page_path,
            heading_path=heading_path,
            statement=statement,
            statement_form=form,
            level=level,
            body=body,
            line_start=line_start,
            examples=examples,
            origin="golden",
            preconditions=tuple(dict.fromkeys(p for p in preconditions if p.strip())),
            supersedes=supersedes,
            positional=positional,
        )))

    out.sort(key=lambda pair: (pair[1].line_start, pair[1].uid))
    return out


def _examples_of(page_path: str, rule: Span, kids, position) -> dict[str, list[str]]:
    """The example strings one rule span contributes, keyed by polarity.

    Ungrouped examples keep the order they always had, so a golden set with no
    groups builds the same ledger it did before groups existed. A group becomes
    one string, its members joined by newlines in document order, emitted where
    its first member would have been. Newline rather than any list marker: a
    training input carries no format markup (D-13, ADR-019).
    """
    mine = [k for k in kids if k.span.of == rule.span_id]
    groups: dict[str, list] = {}
    for kid in mine:
        if kid.span.group:
            groups.setdefault(kid.span.group, []).append(kid)
    for gid, members in groups.items():
        kinds = {m.span.kind for m in members}
        if len(kinds) > 1:
            raise GoldenError(
                f"{page_path}: example group {gid} mixes {sorted(kinds)} — one "
                f"example cannot both comply and violate")

    examples: dict[str, list[str]] = {}
    emitted: set[str] = set()
    for kid in mine:
        key = {"compliant": GOLD_COMPLIANT, "violating": GOLD_VIOLATING}.get(kid.span.kind)
        if not key:
            continue
        gid = kid.span.group
        if not gid:
            examples.setdefault(key, []).append(kid.text)
            continue
        if gid in emitted:
            continue
        emitted.add(gid)
        members = sorted(groups[gid], key=lambda m: (position.get(m.block.id, 0), m.span.start))
        examples.setdefault(key, []).append("\n".join(m.text for m in members))
    return examples


def _enclosing(nodes, block: Block):
    """The heading node a body block sits under."""
    found = None
    for node in nodes:
        if node.line_start <= block.line:
            found = node
        else:
            break
    return found


def _refuse_orphans(page_path: str, rules, kids) -> None:
    ids = {r.span.span_id for r in rules}
    for kid in kids:
        if kid.span.of not in ids:
            raise GoldenError(
                f"{page_path}: {kid.span.kind} span {kid.span.span_id} "
                f"({kid.text[:50]!r}) points at rule {kid.span.of or '<nothing>'}, "
                f"which is not a rule span on this page")


def _refuse_overlapping_examples(page_path: str, resolved, kids) -> None:
    """D-5, and the only way a reviewer could reintroduce the Octavius failure.

    A rule tested against the sentence that states it always passes and proves
    nothing — postmortem F4. The schema cannot catch it because both strings are
    legitimate on their own; only their provenance makes it wrong, and provenance
    is exactly what a span records.
    """
    for kid in kids:
        parent = resolved.get(kid.span.of)
        if parent is None or kid.span.kind == "precondition":
            continue
        if kid.block.id != parent.block.id:
            continue
        if kid.span.start < parent.span.end and kid.span.end > parent.span.start:
            raise GoldenError(
                f"{page_path}: {kid.span.kind} example {kid.text[:50]!r} overlaps the "
                f"rule statement it illustrates ({parent.text[:50]!r}). A rule's "
                f"examples are never drawn from the sentence that states the rule "
                f"(D-5, postmortem F4)."
            )
