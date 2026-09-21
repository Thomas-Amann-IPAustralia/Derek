#!/usr/bin/env python3
"""Build the reviewer dashboard as a static site (for GitHub Pages) — ADR-022.

    python tools/review/build_static.py              # → site/
    python tools/review/build_static.py --out _site

The same `index.html` the local server serves, plus the JSON the API would
have returned, written to files. The copy published here is marked as the
static backend as it is copied (`_page`); anything unmarked asks for
`api/bootstrap` first and falls back to `data/bootstrap.json`, so the page
still works opened straight off disk. Relative paths throughout, so the site
works from a project-pages subpath (`/Derek/`) without knowing its own name.

**Why this exists.** Round 1 is 736 decisions a human has to make, and the
person making them cannot always run Python — a locked-down work machine has
a browser and nothing else. A dashboard nobody can open is a review queue
that never gets worked.

**What changes when there is no server.** Three things, each of them a real
loss rather than a thing we pretended away:

* *Decisions are queued in the browser, not written to the ledger.* They go
  into `localStorage` as an op log, are exported as JSONL, and are replayed
  into `ledger/rules.jsonl` by `tools/review/apply_decisions.py` — which runs
  the same `_apply` as the server, so the guard rails in ADR-008 hold at the
  point the decision lands in the record rather than at the point it is typed.
* *Attention checks are not served.* They are graded server-side on purpose:
  "a check whose answer is in the page is decoration" (server.py). A static
  site can only ship the answer, so the static build drops them rather than
  shipping a check that measures nothing.
* *The leaderboard is a build-time snapshot* of what is in the ledger, and
  says so on the page. It cannot see decisions still sitting on someone's
  laptop, because those are not in the record yet.

Stdlib only, and it imports `server.py` rather than reimplementing it, so the
payload the static site serves cannot drift from the payload the local server
serves. The glossary drift check runs here too (`load_glossary` raises), which
means an unexplained option fails the Pages build exactly as it fails startup.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent


def _load_server():
    """Import tools/review/server.py, which is not on a package path."""
    spec = importlib.util.spec_from_file_location(
        "derek_review_server", HERE / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _commit() -> str:
    """The commit this site was built from, for the provenance line."""
    if sha := os.environ.get("GITHUB_SHA"):
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


BACKEND_MARKER = 'window.DEREK_BACKEND = "server";'


def _page() -> str:
    """index.html with its backend marker flipped.

    The page probes for `api/bootstrap` and falls back to the published JSON,
    so the marker is only a shortcut — but it is the difference between every
    reviewer's browser logging a failed request on every load and not doing so.
    Asserting the anchor is here means the marker cannot quietly stop existing.
    """
    html = (HERE / "index.html").read_text(encoding="utf-8")
    if html.count(BACKEND_MARKER) != 1:
        raise SystemExit(
            f"tools/review/index.html no longer contains exactly one "
            f"{BACKEND_MARKER!r} — the static build cannot mark itself."
        )
    return html.replace(BACKEND_MARKER, 'window.DEREK_BACKEND = "static";')


def _write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(body, encoding="utf-8")
    return len(body.encode("utf-8"))


def build(out: Path, *, server=None) -> dict:
    """Write the site to `out` and return its manifest."""
    server = server or _load_server()

    if not server.LEDGER.exists():
        raise SystemExit(
            f"No ledger at {server.LEDGER}. Run: python -m derek.extract.build"
        )

    glossary = server.load_glossary()     # raises if it has drifted from the code
    rules = server.load_ledger(server.LEDGER)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    commit = _commit()

    build_info = {
        "generated_at": generated_at,
        "commit": commit,
        "rules": len(rules),
        "repo": os.environ.get("GITHUB_REPOSITORY", "Thomas-Amann-IPAustralia/Derek"),
    }

    bootstrap = {
        "static": True,
        "build": build_info,
        "glossary": glossary,
        "options": server.reviewer_options(glossary),
        "points": server.POINTS,
        "hasty_ms": server.HASTY_MS,
        **server._payload(rules),
    }
    examples = server.example_queue(rules)
    board = {
        "build": build_info,
        **{
            window: {
                **server.leaderboard(rules, window),
                "agreement": server.agreement(rules),
            }
            for window in ("day", "week", "all")
        },
    }

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    (out / "index.html").write_text(_page(), encoding="utf-8")
    # Pages runs Jekyll over an uploaded tree unless told not to; a `data/`
    # directory is exactly the kind of thing it would try to interpret.
    (out / ".nojekyll").write_text("", encoding="utf-8")

    sizes = {
        "index.html": (out / "index.html").stat().st_size,
        "data/bootstrap.json": _write_json(out / "data" / "bootstrap.json", bootstrap),
        "data/examples.json": _write_json(out / "data" / "examples.json", examples),
        "data/leaderboard.json": _write_json(out / "data" / "leaderboard.json", board),
    }
    manifest = {
        **build_info,
        "counts": bootstrap["counts"],
        "examples": examples["total"],
        "bytes": sizes,
    }
    sizes["data/manifest.json"] = _write_json(out / "data" / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out", type=Path, default=REPO / "site",
        help="directory to write the site into (default: site/)",
    )
    args = ap.parse_args(argv)

    manifest = build(args.out.resolve())
    total = sum(manifest["bytes"].values())
    print(f"Built {args.out} from {manifest['rules']} rules "
          f"({total / 1024:.0f} KB, commit {manifest['commit'] or 'unknown'})")
    for name, size in manifest["bytes"].items():
        print(f"  {name:<24} {size / 1024:>8.0f} KB")
    pending = manifest["counts"].get("proposed", 0)
    print(f"\n{pending} rules awaiting triage. "
          f"Decisions made on the static site are exported and replayed with:"
          f"\n  python tools/review/apply_decisions.py <export.jsonl>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
