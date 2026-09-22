"""Is the corpus frozen, and against what (ADR-024)?

A frozen corpus is not a frozen ledger. Freezing means ``corpus/pages/`` stops
being rewritten, so the only thing that can change ``ledger/rules.jsonl`` is a
human decision. The daily crawl keeps running and keeps reporting drift; it just
stops applying it.

The reason it exists: golden-set spans are anchored to the text they were drawn
on (ADR-023). An upstream edit while the corpus is live moves every span on that
page, and there is no point reconciling a rulebook against a moving corpus using
heuristics that are being replaced anyway.

Stdlib only, with the same small hand-written reader ``eligibility.py`` uses, so
Layer 0 stays free of a YAML dependency.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Freeze", "load_freeze", "lock_digest", "FREEZE_PATH"]

REPO = Path(__file__).resolve().parents[2]
FREEZE_PATH = REPO / "corpus" / "freeze.yaml"

_SCALAR = re.compile(r'^(?P<key>[a-z_]+):\s*(?:"(?P<q>[^"]*)"|(?P<b>true|false)|(?P<n>\d+))?\s*$')
_BLOCK_START = re.compile(r"^(?P<key>[a-z_]+):\s*[|>][-+]?\s*$")
_BLOCK_LINE = re.compile(r"^\s{2,}(?P<text>\S.*)$")


@dataclass(frozen=True)
class Freeze:
    """The declared freeze, or the absence of one."""

    frozen: bool = False
    frozen_at: str = ""
    reason: str = ""
    lock_digest: str = ""

    def __bool__(self) -> bool:
        return self.frozen

    def banner(self) -> str:
        """One line for a CI summary or a page header."""
        if not self.frozen:
            return "Corpus is live: the daily snapshot rewrites pages and rebuilds the ledger."
        return (f"Corpus is FROZEN as of {self.frozen_at}. Drift is reported, "
                f"not applied. Reason: {self.reason}")


def lock_digest(lock_path: Path) -> str:
    """A single digest over every page hash in ``snapshot.lock.json``.

    Sorted, so it is a property of the corpus content rather than of the order
    a particular run happened to write. Recorded in ``freeze.yaml`` so a frozen
    corpus can be shown to be the one the spans were drawn against, without
    reading 186 hashes to find out.
    """
    import json

    if not lock_path.exists():
        return ""
    pages = json.loads(lock_path.read_text(encoding="utf-8")).get("pages", {})
    h = hashlib.sha256()
    for path in sorted(pages):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(pages[path].get("sha256", "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def load_freeze(path: Path = FREEZE_PATH) -> Freeze:
    """Read ``corpus/freeze.yaml``. An absent file means the corpus is live."""
    if not path.exists():
        return Freeze()

    values: dict[str, str] = {}
    block_key: str | None = None
    block: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if block_key is not None:
            if (m := _BLOCK_LINE.match(line)):
                block.append(m.group("text").strip())
                continue
            values[block_key] = " ".join(block)
            block_key, block = None, []
        if (m := _BLOCK_START.match(line)):
            block_key, block = m.group("key"), []
            continue
        if (m := _SCALAR.match(line)):
            values[m.group("key")] = (
                m.group("q") if m.group("q") is not None
                else m.group("b") if m.group("b") is not None
                else m.group("n") or ""
            )
    if block_key is not None:
        values[block_key] = " ".join(block)

    return Freeze(
        frozen=values.get("frozen", "false") == "true",
        frozen_at=values.get("frozen_at", ""),
        reason=values.get("reason", ""),
        lock_digest=values.get("lock_digest", ""),
    )
