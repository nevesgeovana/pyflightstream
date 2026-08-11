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


#: Scratch trees a run creates at whatever its working directory is.
#: Gitignored, so the closure below cannot see them, and still a
#: finding at the ROOT: one here means a test ran in the wrong place.
SCRATCH_ROOTS = ("runs", "site_check")


def _root_artifacts() -> list[str]:
    """Names of everything at the repository root that nothing accounts for.

    DERIVED, not enumerated. The first version listed the artifact kinds
    it knew about (``*.png``, then two directory names), so it could
    only ever catch a leftover somebody had already met. On 2026-08-09 a
    solver run left a file called ``CLOSE_FLIGHTSTREAM`` at the root,
    named after the command it had eaten as an export filename, and this
    guard did not see it: it was committed, and the artifact of the
    defect this release fixes nearly shipped inside the release that
    fixes it.

    So the question is closed instead of sampled. A path at the root is
    accounted for when git tracks it or when git ignores it; anything
    else is something a run left behind, whatever it is called. That
    also means a genuinely new file must be added or ignored
    deliberately, which is the same discipline applied to the tree.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", ":(top)*"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    known = {name.split("/", 1)[0] for name in tracked if name}

    found = []
    for path in sorted(REPO.iterdir()):
        if path.name in known or path.name == ".git":
            continue
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", path.name], cwd=REPO, capture_output=True
        )
        if ignored.returncode != 0:
            found.append(path.name)

    # And the scratch roots, which ARE ignored and are still findings
    # HERE. Being ignored answers "may this be committed"; this guard
    # asks the different question of whether a test ran with the
    # repository as its working directory, and a scratch tree at the
    # root is the evidence that one did. Dropping these when the closure
    # above arrived would have traded a specific catch for a general
    # one, so both questions are asked.
    found += [name for name in SCRATCH_ROOTS if (REPO / name).exists()]
    return sorted(found)


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


@pytest.mark.requirement("NFR-01d")
@pytest.mark.parametrize("name", sorted(EXAMPLE_EXTRAS))
def test_each_example_runs(name, tmp_path):
    """The examples execute, which nothing checked before.

    Run as a subprocess rather than imported, because that is how a
    reader runs them: a module-level guard that only holds under
    ``__main__`` would pass an import and fail the user.

    In a temporary working directory, not the repository. Two of them
    write a PNG beside the caller, and the first version of this test
    ran them at the repository root, so every suite run left two
    untracked artifacts there. A test that dirties the tree it is
    testing is a test somebody eventually deletes.
    """
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
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


def test_nothing_leaves_an_artifact_in_the_repository_root():
    """The tree is as clean after the suite as before it.

    Guards two fixes rather than the examples themselves. `cwd=tmp_path`
    above is one keyword and reverting it would be invisible, while the
    artifacts it prevents are two PNGs nobody would connect to a test.
    And a docs page whose code block builds a workspace writes a `runs/`
    tree at the root, which is the same class arriving from the other
    direction: the docs examples run under Sybil, with the repository as
    their working directory.
    """
    assert _root_artifacts() == [], (
        f"the repository root holds {_root_artifacts()}; something ran an "
        "example or a docs code block with the repository as its working "
        "directory. Mark such a block `<!-- skip: next -->`, or pass a "
        "temporary cwd"
    )


def test_the_cleanliness_detector_can_actually_see_an_artifact():
    """The guard above is a negative assertion, so it needs a witness.

    In CI both of its halves are green by construction: the docs blocks
    that would write `runs/` are executed in a later step than the tier 1
    run, and the two examples that write a PNG are run by
    `test_each_example_runs` with `cwd=tmp_path`, so the file lands
    beside the temporary directory and never at the root. A detector that
    quietly stopped detecting would look exactly like a clean tree. This
    drives it.

    An earlier version of this docstring gave a different reason for the
    PNG half: that matplotlib is not in the CI install. Measured on
    2026-08-10, that is false. PyNiteFEA requires matplotlib
    unconditionally, so the `fsi` extra drags it in and every leg has
    always had it; those examples run and do write their PNGs. The
    working directory is what keeps the tree clean, which is the reason
    the test above already states and this one contradicted.
    """
    made = []
    try:
        for name in ("_guard_witness.png",):
            (REPO / name).write_bytes(b"")
            made.append(REPO / name)
        (REPO / "runs").mkdir(exist_ok=True)
        made.append(REPO / "runs")
        found = _root_artifacts()
        assert "_guard_witness.png" in found, found
        assert "runs" in found, found
    finally:
        for path in made:
            if path.is_dir():
                path.rmdir()
            elif path.exists():
                path.unlink()
    assert _root_artifacts() == []
