"""The rule ledger: Derek's single source of truth about rules.

One ledger entry per rule. The entry carries three provenance tags, which
are the project's non-negotiable requirement:

1. **derivation** — how we arrived at this rule.
2. **detection**  — the method through which the rule should be implemented.
3. **source**     — the original Style Manual rule the implementation came from.

Every other field exists to prevent a specific, documented Octavius failure.
Cross-references to ``docs/00-postmortem-octavius.md`` are given inline so
that nobody removes a field without first reading why it is there.

The ledger is JSONL in git. It is not a database: every decision is a
reviewable diff, attributable and revertable (ADR-008).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "Rule",
    "Source",
    "Derivation",
    "Detection",
    "Validation",
    "Review",
    "ReviewStatus",
    "Clarity",
    "Direction",
    "Unit",
    "DetectionMethod",
]


class ReviewStatus:
    """Lifecycle of a rule. Only ACCEPTED and AMENDED reach the runtime (ADR-008)."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    AMENDED = "amended"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    QUARANTINED = "quarantined"   # failed the dogfood gate (ADR-011)
    SUPERSEDED = "superseded"     # statement reworded upstream (ADR-002)
    ORPHANED = "orphaned"         # source page removed upstream (ADR-001)

    LOADABLE = frozenset({ACCEPTED, AMENDED})
    ALL = frozenset({
        PROPOSED, ACCEPTED, AMENDED, REJECTED, DEFERRED,
        QUARANTINED, SUPERSEDED, ORPHANED,
    })


class Clarity:
    """Is the rule operationalisable as written? (ADR-017)

    ``UNREVIEWED`` is the initial value. The extractor deliberately makes no
    claim: asserting ``unambiguous`` would be a judgement nobody made, and
    asserting ``ambiguous_resolvable`` would claim a resolution that does not
    yet exist. Clarity is a review-owned field.
    """

    UNREVIEWED = "unreviewed"
    UNAMBIGUOUS = "unambiguous"
    AMBIGUOUS_RESOLVABLE = "ambiguous_resolvable"
    AMBIGUOUS_DEFERRED = "ambiguous_deferred"
    NOT_AUTOMATABLE = "not_automatable"

    ALL = frozenset({
        UNREVIEWED, UNAMBIGUOUS, AMBIGUOUS_RESOLVABLE,
        AMBIGUOUS_DEFERRED, NOT_AUTOMATABLE,
    })


class Direction:
    """Does the rule detect something present, or something missing? (ADR-006)"""

    PRESENCE = "presence"
    ABSENCE = "absence"

    ALL = frozenset({PRESENCE, ABSENCE})


class Unit:
    """The span a rule evaluates (ADR-007). ARTIFACT rules never load."""

    CHARACTER = "character"
    TOKEN = "token"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    BLOCK = "block"
    SECTION = "section"
    DOCUMENT = "document"
    ARTIFACT = "artifact"

    ALL = frozenset({
        CHARACTER, TOKEN, PHRASE, SENTENCE, PARAGRAPH,
        BLOCK, SECTION, DOCUMENT, ARTIFACT,
    })


class DetectionMethod:
    """Closed vocabulary of matcher primitives (ADR-009). No generated code."""

    LITERAL_SET = "literal_set"
    REGEX = "regex"
    TOKEN_PATTERN = "token_pattern"
    LENGTH_CONSTRAINT = "length_constraint"
    STRUCTURAL_PREDICATE = "structural_predicate"
    CLASSIFIER = "classifier"
    NONE = "none"

    ALL = frozenset({
        LITERAL_SET, REGEX, TOKEN_PATTERN, LENGTH_CONSTRAINT,
        STRUCTURAL_PREDICATE, CLASSIFIER, NONE,
    })


@dataclass
class Source:
    """Provenance tag 3 — the original Style Manual rule.

    ``statement`` is the manual's wording verbatim. It is never edited; an
    interpretation goes in ``Rule.specification`` instead (ADR-017), so the
    manual's text stays citable.
    """

    page_path: str
    heading_path: list[str]
    statement: str
    url: str = ""
    body_excerpt: str = ""
    snapshot_sha256: str = ""
    line_start: int = 0


@dataclass
class Derivation:
    """Provenance tag 1 — how we arrived at this rule."""

    method: str = "heading_structure"   # heading_structure | imperative_sentence | manual
    extractor_version: str = "1.0.0"
    statement_form: str = ""            # imperative | negative_imperative | modal | descriptive
    derived_at: str = ""
    supersedes: str | None = None       # uid of the rule this replaces (ADR-002)
    uid_history: list[str] = field(default_factory=list)
    # ^ prior UIDs of *this same rule*, when a re-derivation changed the
    #   content-addressed identity without the Style Manual changing a word
    #   — e.g. a converter upgrade that corrected the heading path (ADR-020).
    #   Distinct from ``supersedes``, which means the upstream text changed.
    model_decisions: dict[str, str] = field(default_factory=dict)
    # ^ maps field name -> "<prompt_version>/<model_id>" for any field a model
    #   proposed, so a model-proposed value is never mistaken for a human one
    #   and a prompt-version bump invalidates exactly the right entries (ADR-003).


@dataclass
class Detection:
    """Provenance tag 2 — the method through which the rule is implemented.

    ``matcher`` is declarative data drawn from the closed vocabulary in
    ``DetectionMethod``. The runtime never executes code from the ledger
    (ADR-009 / postmortem Defect 2).
    """

    tier: int | None = None             # 0 deterministic | 1 classifier | 2 generative
    method: str = DetectionMethod.NONE
    matcher: dict[str, Any] = field(default_factory=dict)
    detectable: bool = False
    not_detectable_reason: str = ""


@dataclass
class Validation:
    """Test outcomes. Deliberately SEPARATE from review status (Defect 4).

    Octavius conflated "the tests passed" with "we decided to ship this" in
    a single ``test_result`` field, so a frozen rule and a failing rule were
    indistinguishable to the loader.
    """

    status: str = "untested"            # untested | pass | fail
    examples_pass: bool | None = None   # violating fire, compliant do not (ADR-004)
    dogfood_density: float | None = None   # findings per 10k words on the manual itself
    expected_density: float = 0.0          # budget; >0 needs written justification
    last_run: str = ""
    notes: str = ""


@dataclass
class Review:
    """The human gate (ADR-008)."""

    status: str = ReviewStatus.PROPOSED
    decided_by: str = ""
    decided_at: str = ""
    note: str = ""
    history: list[dict[str, str]] = field(default_factory=list)

    def transition(self, status: str, by: str, at: str, note: str = "") -> None:
        if status not in ReviewStatus.ALL:
            raise ValueError(f"unknown review status: {status!r}")
        self.history.append(
            {"from": self.status, "to": status, "by": by, "at": at, "note": note}
        )
        self.status, self.decided_by, self.decided_at, self.note = status, by, at, note


@dataclass
class Rule:
    """One rule in the ledger."""

    uid: str
    source: Source
    derivation: Derivation

    # --- interpretation -------------------------------------------------
    modality: str = "MUST"
    modality_basis: str = ""
    clarity: str = Clarity.UNREVIEWED
    specification: str = ""                     # formal restatement (ADR-017)
    disambiguation_log: list[dict[str, str]] = field(default_factory=list)

    # --- scope (ADR-007) ------------------------------------------------
    applies_to: list[str] = field(default_factory=lambda: ["any"])
    unit: str = Unit.SENTENCE
    context_preconditions: list[str] = field(default_factory=list)

    # --- polarity (ADR-004) — the field set that killed Octavius --------
    direction: str = Direction.PRESENCE
    violation_condition: str = ""
    compliant_examples: list[str] = field(default_factory=list)
    violating_examples: list[str] = field(default_factory=list)

    # --- implementation and outcome -------------------------------------
    detection: Detection = field(default_factory=Detection)
    validation: Validation = field(default_factory=Validation)
    confidence: float | None = None             # calibrated; null = unvalidated (ADR-013)
    confidence_basis: str = ""
    review: Review = field(default_factory=Review)

    schema_version: int = SCHEMA_VERSION

    # ------------------------------------------------------------------
    @property
    def loadable(self) -> bool:
        """May this rule enter the runtime?"""
        return (
            self.review.status in ReviewStatus.LOADABLE
            and self.detection.detectable
            and self.unit != Unit.ARTIFACT
            and self.detection.method != DetectionMethod.NONE
        )

    @property
    def effective_statement(self) -> str:
        """What detectors implement: the specification if one exists (ADR-017)."""
        return self.specification or self.source.statement

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        return cls(
            uid=d["uid"],
            source=Source(**d["source"]),
            derivation=Derivation(**d["derivation"]),
            detection=Detection(**d.get("detection", {})),
            validation=Validation(**d.get("validation", {})),
            review=Review(**d.get("review", {})),
            **{
                k: v for k, v in d.items()
                if k not in {"uid", "source", "derivation", "detection", "validation", "review"}
            },
        )
