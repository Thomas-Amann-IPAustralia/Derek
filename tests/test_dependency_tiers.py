"""The dependency tiering is an invariant, so it is asserted rather than trusted.

Two separate things are checked here, both of which have already broken once.

1. **``derek/extract/`` and ``derek/ledger/`` are stdlib-only.** Extraction is a
   pure function of the corpus (ADR-002); a third-party import there is a
   reproducibility hazard, because a silent dependency bump would change the
   rulebook without the Style Manual changing a word.

2. **Everything CI runs is installable from ``requirements.txt`` plus
   ``requirements-dev.txt``.** CI installs exactly those two files. When
   ADR-020 replaced the converter, ``derek/corpus/to_markdown.py`` gained an
   HTML parser dependency that was only ever declared in
   ``requirements-pipeline.txt``, which CI does not install — so
   ``tests/test_to_markdown.py`` failed at *collection* and took the entire
   suite down with it, including every invariant test in this directory.
   A missing dependency that disables the invariant tests is the worst shape
   this failure can take, so the closure is now checked statically.

Static analysis, deliberately: importing every module to find out what it needs
is exactly what fails when a dependency is missing.
"""

from __future__ import annotations

import ast
import re
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Tiers that must never acquire a third-party import. ``derek/corpus/`` is
# absent on purpose: to_markdown.py needs an HTML parser and fetch.py needs a
# transport, both documented in CLAUDE.md.
STDLIB_ONLY_TIERS = ("derek/extract", "derek/ledger")

# CI installs these and only these.
CI_REQUIREMENTS = ("requirements.txt", "requirements-dev.txt")

# What CI actually executes, beyond the test suite itself (.github/workflows/ci.yml).
# What CI actually executes, beyond the test suite itself. The two static
# builders are here because pages.yml runs them with NO `pip install` step, so a
# third-party import in either aborts the Pages deploy rather than failing a test.
CI_ENTRY_POINTS = (
    "derek/extract/build.py",
    "derek/extract/blocks.py",
    "derek/eval/dogfood.py",
    "tools/review/build_static.py",
    "tools/annotate/build_static.py",
    # Loaded by path from tools/annotate/build_static.py, so an import chain
    # would not reach it: the annotator ships its drafts (ADR-025).
    "tools/draft/drafting.py",
    "derek/eval/golden_lint.py",
    # adopt-matchers.yml runs these with no install step either.
    "derek/detect/proposals.py",
    "derek/detect/__main__.py",
)

_PIN = re.compile(r"[=<>!~\[;]")


def _canon(name: str) -> str:
    """PEP 503 name normalisation, so ``beautifulsoup4`` == ``BeautifulSoup4``."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _declared(path: Path, seen: set[Path] | None = None) -> set[str]:
    """Distribution names a requirements file declares, following ``-r`` includes."""
    seen = seen if seen is not None else set()
    path = path.resolve()
    if path in seen or not path.exists():
        return set()
    seen.add(path)

    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-r", "--requirement")):
            out |= _declared(path.parent / line.split(maxsplit=1)[1], seen)
            continue
        if line.startswith("-"):
            continue
        out.add(_canon(_PIN.split(line)[0]))
    return out


def _imported_modules(source: Path) -> set[str]:
    """Fully-qualified module names a file imports. Relative imports resolve."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    package = source.relative_to(REPO).with_suffix("").parts
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: -node.level]
                out.add(".".join((*base, node.module)) if node.module else ".".join(base))
            elif node.module:
                out.add(node.module)
    return out


def _resolve(dotted: str) -> list[Path]:
    """First-party module name -> the file(s) implementing it, if any."""
    parts = dotted.split(".")
    candidates = [REPO.joinpath(*parts).with_suffix(".py"), REPO.joinpath(*parts, "__init__.py")]
    return [p for p in candidates if p.is_file()]


def _third_party_closure(seeds: list[Path]) -> dict[str, set[str]]:
    """Third-party top-level module -> the first-party files that import it.

    Walks ``derek.*`` imports transitively, so a dependency three modules deep
    behind a test import is still found.
    """
    stack = list(seeds)
    visited: set[Path] = set()
    found: dict[str, set[str]] = {}

    while stack:
        current = stack.pop()
        if current in visited or not current.is_file():
            continue
        visited.add(current)
        where = str(current.relative_to(REPO))

        for dotted in _imported_modules(current):
            root = dotted.split(".")[0]
            if root == "derek":
                stack.extend(_resolve(dotted))
            elif root in sys.stdlib_module_names or root in ("tests", "conftest"):
                continue
            else:
                found.setdefault(root, set()).add(where)
    return found


# ---------------------------------------------------------------------------
# D-7 — extraction is deterministic, so its tier carries no dependencies
# ---------------------------------------------------------------------------

def test_extraction_and_ledger_tiers_are_stdlib_only():
    offenders: list[str] = []
    for tier in STDLIB_ONLY_TIERS:
        for source in sorted((REPO / tier).rglob("*.py")):
            for dotted in sorted(_imported_modules(source)):
                root = dotted.split(".")[0]
                if root != "derek" and root not in sys.stdlib_module_names:
                    offenders.append(f"{source.relative_to(REPO)} imports {dotted}")
    assert not offenders, (
        "a stdlib-only tier grew a third-party import — extraction would no "
        "longer be reproducible from the corpus alone (ADR-002):\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# CI must be able to install what CI runs
# ---------------------------------------------------------------------------

def test_ci_requirements_cover_everything_ci_imports():
    seeds = sorted((REPO / "tests").glob("*.py"))
    seeds += [REPO / p for p in CI_ENTRY_POINTS]

    declared = set()
    for name in CI_REQUIREMENTS:
        declared |= _declared(REPO / name)

    # module -> distributions, for what is installed in this interpreter.
    provides = {mod: {_canon(d) for d in dists}
                for mod, dists in packages_distributions().items()}

    undeclared: list[str] = []
    for module, importers in sorted(_third_party_closure(seeds).items()):
        dists = provides.get(module, set())
        if not dists:
            undeclared.append(
                f"{module} (imported by {', '.join(sorted(importers))}) is not "
                f"installed, so no requirements file can be providing it"
            )
        elif not dists & declared:
            undeclared.append(
                f"{module} (imported by {', '.join(sorted(importers))}) comes from "
                f"{sorted(dists)}, which {' / '.join(CI_REQUIREMENTS)} do not declare"
            )

    assert not undeclared, (
        "CI installs only " + " and ".join(CI_REQUIREMENTS) + ", so a dependency "
        "missing from them aborts pytest at collection and silently disables every "
        "invariant test:\n  " + "\n  ".join(undeclared)
    )


def test_pipeline_requirements_do_not_restate_the_core_pins():
    """One pin, one place. Two copies drift, and a converter bump must be deliberate (ADR-001)."""
    core = _declared(REPO / "requirements.txt")
    pipeline_text = (REPO / "requirements-pipeline.txt").read_text(encoding="utf-8")
    restated = sorted(
        name for name in core
        if any(
            _canon(_PIN.split(line.split("#", 1)[0].strip())[0]) == name
            for line in pipeline_text.splitlines()
            if line.split("#", 1)[0].strip() and not line.strip().startswith("-")
        )
    )
    assert not restated, (
        "requirements-pipeline.txt restates pins that requirements.txt already "
        f"owns: {restated}. Include it with '-r requirements.txt' instead."
    )
