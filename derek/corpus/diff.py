"""Changeset computation between corpus snapshots (ADR-001).

This is the layer that satisfies "must correctly identify new rules, rules
which have been altered and rules which have been removed". Octavius could
do none of the three: it compared the sitemap's ``lastmod`` to a stored
copy, so a page edited without a ``lastmod`` bump was invisible forever, a
page removed from the sitemap was never deleted, and no diff was ever
produced (postmortem F7).

Here the **content hash of the normalised page is the only authority**.
``lastmod`` is a scheduling hint used to decide what is worth re-fetching,
and nothing more.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["PageState", "Snapshot", "Changeset", "diff_snapshots", "load_lock", "write_lock"]

LOCK_VERSION = 1


@dataclass
class PageState:
    """What we know about one page as of a snapshot."""

    url: str
    path: str
    sha256: str
    lastmod: str | None = None
    fetched_at: str = ""
    extractor: str = ""


@dataclass
class Snapshot:
    """The full corpus state: the lock file's contents."""

    version: int = LOCK_VERSION
    generated_at: str = ""
    pages: dict[str, PageState] = field(default_factory=dict)   # keyed by path

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "pages": {k: asdict(v) for k, v in sorted(self.pages.items())},
        }


@dataclass
class Changeset:
    """What changed between two snapshots."""

    generated_at: str = ""
    added: list[str] = field(default_factory=list)
    altered: list[dict[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    kind: str = "editorial"     # editorial | extractor_upgrade | initial

    @property
    def empty(self) -> bool:
        return not (self.added or self.altered or self.removed)

    def summary(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "altered": len(self.altered),
            "removed": len(self.removed),
            "unchanged": self.unchanged,
        }

    def to_dict(self) -> dict:
        return {**asdict(self), "summary": self.summary()}


def diff_snapshots(old: Snapshot, new: Snapshot) -> Changeset:
    """Compare two snapshots by content hash.

    A page whose hash is unchanged is unchanged, whatever its ``lastmod``
    says. A page present in ``old`` and absent from ``new`` is removed — a
    case Octavius never handled at all.
    """
    cs = Changeset(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not old.pages:
        cs.kind = "initial"

    for path, state in sorted(new.pages.items()):
        prev = old.pages.get(path)
        if prev is None:
            cs.added.append(path)
        elif prev.sha256 != state.sha256:
            cs.altered.append({
                "path": path,
                "from_sha256": prev.sha256,
                "to_sha256": state.sha256,
                "lastmod_changed": str(prev.lastmod != state.lastmod),
            })
        else:
            cs.unchanged += 1

    for path in sorted(old.pages):
        if path not in new.pages:
            cs.removed.append(path)

    # A change in every page at once is an extraction-pipeline upgrade, not
    # 186 simultaneous editorial edits. Labelling it stops a dependency bump
    # being mistaken for upstream change (ADR-001).
    if old.pages and len(cs.altered) > 0.8 * len(old.pages) and not cs.added and not cs.removed:
        cs.kind = "extractor_upgrade"

    return cs


def load_lock(path: Path) -> Snapshot:
    if not path.exists():
        return Snapshot()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(
        version=raw.get("version", LOCK_VERSION),
        generated_at=raw.get("generated_at", ""),
        pages={k: PageState(**v) for k, v in raw.get("pages", {}).items()},
    )


def write_lock(path: Path, snapshot: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_changeset(directory: Path, cs: Changeset) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (cs.generated_at or datetime.now(timezone.utc).isoformat()).replace(":", "").replace("-", "")[:15]
    out = directory / f"{stamp}.json"
    out.write_text(json.dumps(cs.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
