"""Tier 1: the worked examples run, and each declares the extras it needs.

REV-002 finding PYFS-026, the examples half. The four ``examples/*.py``
were in no CI step at all, so an example could break with the API it
demonstrates and stay broken until a reader tried it. They are the
first code a new user runs.

Each runs in about a second and a half without a solver (the ones that
would execute FlightStream take its path as an argument and build the
script when given none), so they run here rather than only in CI: a
tier 1 test runs on both platforms and on both Python bounds, which is
more coverage than a single CI job.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.extras import EXTRAS

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

#: The extras each example needs, declared rather than inferred, so a
#: new import that reaches into an extra has to be a deliberate edit
#: here as well. ``test_each_example_needs_only_the_extras_it_declares``
#: holds the declaration to the imports.
EXAMPLE_EXTRAS: dict[str, frozenset[str]] = {
    "campaign_matrix.py": frozenset(),
    "fsi_campbell_diagram.py": frozenset({"fsi"}),
    "steady_polar.py": frozenset(),
    "wing_static_deflection.py": frozenset({"fsi"}),
}

#: Subpackages an extra gates. Used to check an example's imports
#: against its declaration; a subpackage absent here is core.
GATED_SUBPACKAGES = {"pyflightstream.fsi": "fsi", "pyflightstream.probes.geometry": "geom"}


def _example_paths() -> list[Path]:
    return sorted(EXAMPLES.glob("*.py"))


def test_the_declaration_covers_every_example():
    """A new example joins the table, or nothing runs it.

    Guard the guard: the parametrized tests below key on
    EXAMPLE_EXTRAS, so an example missing from it would simply not be
    tested, which is the state this finding is about.
    """
    on_disk = {path.name for path in _example_paths()}
    assert on_disk == set(EXAMPLE_EXTRAS), (
        f"examples/ holds {sorted(on_disk)} and EXAMPLE_EXTRAS declares "
        f"{sorted(EXAMPLE_EXTRAS)}; an example nothing declares is an example "
        "nothing runs"
    )
    assert on_disk, "no examples found at all; the glob is wrong"


@pytest.mark.parametrize("name", sorted(EXAMPLE_EXTRAS))
def test_each_example_runs(name):
    """The examples execute, which nothing checked before.

    Run as a subprocess rather than imported, because that is how a
    reader runs them: a module-level guard that only holds under
    ``__main__`` would pass an import and fail the user.
    """
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"examples/{name} exited {result.returncode}. It is the first code a new "
        f"user runs.\nstdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-2000:]}"
    )


@pytest.mark.parametrize("name", sorted(EXAMPLE_EXTRAS))
def test_each_example_needs_only_the_extras_it_declares(name):
    """An example that reaches into an ungated extra is a broken promise.

    A user installs the base package, opens the example the README
    points at, and gets an ImportError. Checked statically, from the
    import statements, because the alternative is four CI jobs with four
    different installs to observe the same fact.
    """
    tree = ast.parse((EXAMPLES / name).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    needed = {
        extra
        for module in imported
        for gated, extra in GATED_SUBPACKAGES.items()
        if module == gated or module.startswith(f"{gated}.")
    }
    declared = EXAMPLE_EXTRAS[name]
    assert needed <= declared, (
        f"examples/{name} imports from {sorted(needed - declared)}, which the "
        f"[{', '.join(sorted(needed - declared))}] extra gates, and declares "
        f"{sorted(declared)}. A reader on a base install would get an ImportError"
    )
    assert declared <= set(EXTRAS), (
        f"examples/{name} declares extras {sorted(declared - set(EXTRAS))} that "
        "this package does not have"
    )


def test_at_least_one_example_needs_no_extra():
    """The control on the declaration table.

    If every example needed an extra, the base install would demonstrate
    nothing, and the import check above would be satisfied by declaring
    every extra everywhere.
    """
    assert any(not extras for extras in EXAMPLE_EXTRAS.values()), (
        "no example runs on a base install; the package's first impression "
        "would require an optional dependency"
    )
