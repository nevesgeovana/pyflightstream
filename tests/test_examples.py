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
import builtins
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.extras import EXTRAS

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
PACKAGE = REPO / "src" / "pyflightstream"

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
        env=os.environ.copy(),
    ).stdout.split("\0")
    known = {name.split("/", 1)[0] for name in tracked if name}

    found = []
    for path in sorted(REPO.iterdir()):
        if path.name in known or path.name == ".git":
            continue
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", path.name],
            cwd=REPO,
            capture_output=True,
            env=os.environ.copy(),
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

    AND IT MAY NOT WARN IN THIS PACKAGE'S OWN VOICE (OPS-2006.02.02).
    The run checked the exit status only, so an example that started
    warning kept exiting 0 and the reader met the warning before anyone
    here did. Read off stderr rather than promoted with a ``-W`` flag,
    and that is a measurement rather than a preference: a ``-W`` naming
    a class outside the standard library is processed while the
    interpreter starts, before ``site`` has put this package on the
    path, so ``python -W error::pyflightstream...`` prints "Invalid -W
    option ignored" and promotes NOTHING. ``pytest``'s own ``-W`` parses
    later and does work, which is why the six homes can carry the
    narrowed filter and this subprocess cannot. Stderr needs no flag at
    all: :class:`PyflightstreamWarning` is a ``UserWarning``, which the
    default filters print.
    """
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, (
        f"examples/{name} exited {result.returncode}. It is the first code a new "
        f"user runs.\nstdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-2000:]}"
    )
    assert PACKAGE_WARNING_NAME not in result.stderr, (
        f"examples/{name} raised a {PACKAGE_WARNING_NAME} while running. The example "
        "is what a reader copies, so a warning it provokes is either a defect in the "
        f"example or a warning that should not fire here.\nstderr:\n{result.stderr[-2000:]}"
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

    THERE IS A THIRD WAY TO GET ONE and the message used to send its
    reader to the wrong file for it. `runs/` is also the sanctioned local
    scratch root of the qa CLI: `pyfs-qa probe` writes `runs/probes/` by
    default, which is the author's own tidy-up decision. So on a licensed
    machine this guard fires after every probe run and told the operator
    a docs code block had run in the wrong directory.

    The guard is right to fire and the assertion is unchanged: the tree
    IS dirty and a licensed session clears its scratch root when it is
    done with it. What changed on 2026-08-17 is that the message names
    both causes, after an attempt to excuse a pre-existing `runs/` was
    shown to break the guard outright: the docs blocks run in a SEPARATE
    pytest invocation from this module, so a tree they left behind is
    always pre-existing by the time this guard is imported, and the
    exception would have swallowed the case it was written for.
    """
    assert _root_artifacts() == [], (
        f"the repository root holds {_root_artifacts()}. Two causes, and they need "
        "different fixes. A licensed run leaves `runs/`, which is the qa CLI's "
        "sanctioned scratch root: delete it, or point --workroot elsewhere. Anything "
        "else means an example or a docs code block ran with the repository as its "
        "working directory: mark such a block `<!-- skip: next -->`, or pass a "
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
    # THE WITNESS DIRECTORY IS `runs/` ITSELF AND THAT WAS WRONG TWICE
    # OVER, on a machine that has actually run the solver. `mkdir(
    # exist_ok=True)` followed by an unconditional `rmdir` DELETES a
    # pre-existing `runs/` this test did not create, and where that
    # directory holds a licensed run's raw output the `rmdir` raises
    # `OSError: directory not empty` and names nothing useful. This
    # session destroyed licensed probe and physics workdirs four times
    # before noticing.
    #
    # So the witness is a name that cannot collide, and it is removed
    # only if this test made it. `runs` stays in the detector's scope,
    # which is what the assertion below actually checks.
    witness_dir = REPO / "_guard_witness_runs"
    assert not witness_dir.exists(), (
        f"{witness_dir.name} exists before the test made it, so removing it would "
        "delete something this test does not own"
    )
    made = []
    try:
        (REPO / "_guard_witness.png").write_bytes(b"")
        made.append(REPO / "_guard_witness.png")
        witness_dir.mkdir()
        made.append(witness_dir)
        found = _root_artifacts()
        assert "_guard_witness.png" in found, found
        assert witness_dir.name in found, found
    finally:
        for path in made:
            if path.is_dir():
                path.rmdir()
            elif path.exists():
                path.unlink()
    assert witness_dir.name not in _root_artifacts()


# ---------------------------------------------------------------------------
# OPS-2006.02.02: the examples build goes red only on warnings THIS package
# raised.
#
# The run promoted every warning to an error, so an unrelated upstream
# release turned the documentation build red for a reason nobody here could
# fix, and the usual answer to a red build nobody can fix is to stop
# believing it. Narrowing to a category of our own is the mechanism; the
# thing that makes a warnings filter dangerous is that it stops matching
# silently, so the narrowing is not shipped on its own. Three questions are
# asked mechanically here: WHERE the promotion is spelled, WHAT it does to a
# warning of each kind, and WHETHER the categories this package actually
# raises are inside the promoted hierarchy at all.
# ---------------------------------------------------------------------------

#: The dotted path of the category the examples runs promote to an error.
#:
#: A PYTEST filter and not an interpreter one, which is measured rather than
#: assumed: ``-W error::a.b.C`` is parsed by IMPORTING ``a.b``, and the
#: interpreter parses its own ``-W`` while it starts, before ``site`` puts
#: this package on the path, so ``python -W error::pyflightstream...`` prints
#: "Invalid -W option ignored" and promotes nothing at all. Every one of the
#: six homes is a ``pytest`` command line, and pytest parses its ``-W`` after
#: the run has begun, where the import succeeds.
#:
#: ``pyflightstream._errors`` rather than ``pyflightstream.exceptions`` for
#: now, only because the catalogue re-export is owed (OPS-2006.02.02);
#: both routes were driven under pytest and both work, so this constant is
#: the one line that moves when the catalogue line lands.
PACKAGE_WARNING_PATH = "pyflightstream._errors.PyflightstreamWarning"
PACKAGE_WARNING_FILTER = f"error::{PACKAGE_WARNING_PATH}"
PACKAGE_WARNING_HOME, PACKAGE_WARNING_NAME = PACKAGE_WARNING_PATH.rsplit(".", 1)

#: The tracked files that spell a ``pytest ... -W ...`` command. DERIVED by
#: the scan below and pinned here, so a seventh home cannot appear unwatched
#: and a home cannot quietly stop carrying its command.
PROMOTION_HOMES = frozenset(
    {
        ".claude/skills/release/SKILL.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "CONTRIBUTING.md",
        "conftest.py",
        "docs/srs/standards.md",
    }
)

#: How many such commands those six files hold. SEVEN and not six:
#: ``docs/srs/standards.md`` is a table row that prints the command twice,
#: once inside the prose cell and once in the cell that names the check, so
#: that row is one edit and two commands. The count is asserted because the
#: population of anything walked is asserted before it is compared.
PROMOTION_COMMANDS = 7

#: What ``warnings.warn`` means when it is given no category at all.
DEFAULT_CATEGORY = "*default*"

#: Warning categories this package raises that are NOT yet inside the
#: promoted hierarchy, as ``(module path under src/pyflightstream, category
#: as written)`` pairs. THIS IS A RATCHET AND IT IS EXPECTED TO EMPTY.
#:
#: While it holds anything, narrowing the six commands above would stop
#: catching exactly these warnings, which is the half of this item that must
#: not be split from the other half. Retagging them is one atomic edit and it
#: is written out in the item's handover: every entry here becomes
#: ``PyflightstreamWarning`` (or ``PyflightstreamDeprecationWarning`` for the
#: two deprecation sites), and ``VersionMismatchWarning`` is re-parented onto
#: ``PyflightstreamWarning`` with ``UserWarning`` kept in its MRO.
#:
#: Pairs rather than counts, deliberately: a second warning of a category a
#: file already raises is not new information, and three sessions share this
#: tree. A new FILE or a new CATEGORY is new information and reds.
#: EMPTIED 2026-08-19, in the commit that retagged every site, which is
#: the order the paragraph above insists on: narrowing first would have
#: stopped catching ours. Nine pairs became none. `VersionMismatchWarning`
#: settled four of the eleven call sites at once by being re-parented onto
#: `PyflightstreamWarning`, which keeps `UserWarning` in its MRO, so every
#: existing `pytest.warns(UserWarning)` and `-W error::UserWarning`
#: catches exactly what it caught.
#:
#: It stays as an EMPTY frozenset rather than being deleted, because the
#: walk below compares against it and a deleted name would take the
#: comparison with it. Empty is the state that says "nothing is owed",
#: which is a different claim from "nobody is checking".
UNPROMOTED_WARNING_CATEGORIES: frozenset[tuple[str, str]] = frozenset()

#: Floors on the two walks, so neither can report green having found
#: nothing. Both are floors and never equalities: another session adding a
#: warning site must not red this file, while a session REMOVING the last
#: site of a category must.
WARN_SITE_FLOOR = 11
WARN_FILE_FLOOR = 6

_PYTEST_COMMAND = re.compile(r"pytest\b[^`|\n]*")
_WARNING_FLAG = re.compile(r"-W\s+(\S+)")


def _warning_filters_in(text: str) -> list[tuple[int, tuple[str, ...]]]:
    """``(line number, filter tokens)`` per ``pytest`` command in ``text``.

    One entry per COMMAND and not per line: the standards table prints
    two on one line, and reading the line as a single command would
    report a two-filter command that nobody wrote.
    """
    found: list[tuple[int, tuple[str, ...]]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for command in _PYTEST_COMMAND.finditer(line):
            flags = tuple(match.group(1) for match in _WARNING_FLAG.finditer(command.group(0)))
            if flags:
                found.append((number, flags))
    return found


def _promotion_commands() -> dict[str, list[tuple[int, tuple[str, ...]]]]:
    """Every tracked ``pytest ... -W ...`` command, by repository-relative path.

    Derived from ``git ls-files`` rather than enumerated, for the reason
    ``_root_artifacts`` gives above: a list of the homes somebody has
    already met can only ever catch a home somebody has already met.
    ``tests/`` is skipped because this module quotes the filter it is
    checking, and ``CHANGELOG.md`` because release history states what a
    command USED to be and is not a home to keep current.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    ).stdout.split("\0")
    found: dict[str, list[tuple[int, tuple[str, ...]]]] = {}
    for name in tracked:
        if not name or name.startswith("tests/") or name == "CHANGELOG.md":
            continue
        try:
            text = (REPO / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # a binary or absent tracked file
            continue
        commands = _warning_filters_in(text)
        if commands:
            found[name] = commands
    return found


def _warn_categories_in(source: str) -> list[tuple[int, str]]:
    """``(line, category as written)`` per ``warnings.warn`` call in ``source``.

    Static, because the alternative is importing every module and
    triggering every branch that warns. ``DEFAULT_CATEGORY`` stands for a
    call that passes none, which the warnings machinery reads as
    ``UserWarning``: an untagged site is the one a reader is most likely
    to believe is already covered.

    ONE SHAPE IS READ AS UNTAGGED THAT IS NOT: ``warnings.warn(Cls(msg))``
    takes its category from the instance and passes no second argument,
    so this walk calls it a default. No site in the package uses it
    today; if one arrives it reds the ratchet, which is the safe
    direction, and this note is why the message will look wrong.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        is_warn = (isinstance(function, ast.Attribute) and function.attr == "warn") or (
            isinstance(function, ast.Name) and function.id == "warn"
        )
        if not is_warn:
            continue
        category = node.args[1] if len(node.args) >= 2 else None
        for keyword in node.keywords:
            if keyword.arg == "category":
                category = keyword.value
        found.append((node.lineno, DEFAULT_CATEGORY if category is None else ast.unparse(category)))
    return found


def _warn_sites() -> list[tuple[str, int, str]]:
    """``(module path under src/pyflightstream, line, category)`` for the package."""
    sites: list[tuple[str, int, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        for line, category in _warn_categories_in(path.read_text(encoding="utf-8")):
            sites.append((relative, line, category))
    return sites


def _module_name(relative: str) -> str:
    """``results/__init__.py`` to ``pyflightstream.results``."""
    parts = relative.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(["pyflightstream", *parts])


def _resolve_category(relative: str, category: str) -> type:
    """The class a written category name denotes, from the module that wrote it."""
    if category == DEFAULT_CATEGORY:
        return UserWarning
    builtin = getattr(builtins, category, None)
    if isinstance(builtin, type):
        return builtin
    module = importlib.import_module(_module_name(relative))
    resolved = getattr(module, category, None)
    assert isinstance(resolved, type), (
        f"{relative} warns with {category!r} and {_module_name(relative)} exports no "
        "such class, so this walk cannot say whether the examples run promotes it; "
        "the resolver has to learn the new shape before the guard means anything"
    )
    return resolved


def _run_pytest_with(filters: tuple[str, ...], module: Path) -> subprocess.CompletedProcess[str]:
    """Run one throwaway test module under exactly ``filters``.

    Through ``pytest`` and from the repository, rather than through a
    bare interpreter from a temporary directory: the six homes are
    ``pytest`` command lines, pytest installs its own default filters
    before the ones it is given, and the repository's own ini file is
    part of what a reader would be running. Measuring the mechanism
    somewhere easier would be measuring a different mechanism.
    """
    flags = [token for spec in filters for token in ("-W", spec)]
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(module), "-q", "-p", "no:cacheprovider", *flags],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=300,
        env=os.environ.copy(),
    )


def _warning_module(tmp_path: Path, name: str, body: str) -> Path:
    module = tmp_path / f"test_ops200602_{name}.py"
    module.write_text(body, encoding="utf-8")
    return module


UPSTREAM_WARNING_MODULE = """
import warnings


def test_a_dependency_deprecates_something_of_its_own():
    warnings.warn("an upstream release deprecated something", DeprecationWarning, stacklevel=1)
"""

PACKAGE_WARNING_MODULE = f"""
import warnings

from {PACKAGE_WARNING_HOME} import {PACKAGE_WARNING_NAME}


def test_this_package_warns_about_something_of_its_own():
    warnings.warn("this package warned", {PACKAGE_WARNING_NAME}, stacklevel=1)
"""


def _distinct_filters() -> list[tuple[str, ...]]:
    seen = {flags for commands in _promotion_commands().values() for _, flags in commands}
    return sorted(seen)


def test_the_promotion_homes_are_the_six_the_item_names():
    """A seventh home, or a home that lost its command, is a finding.

    The scan is derived and this is where its population is asserted,
    before anything compares one home against another. A guard whose
    walk quietly matches nothing passes every per-item assertion it
    makes about the nothing it found.
    """
    commands = _promotion_commands()
    assert set(commands) == PROMOTION_HOMES, (
        f"the tracked tree spells a `pytest ... -W` command in {sorted(commands)} and "
        f"this file watches {sorted(PROMOTION_HOMES)}. A home nobody watches drifts "
        "from the other five"
    )
    total = sum(len(found) for found in commands.values())
    assert total == PROMOTION_COMMANDS, (
        f"{total} commands across the six homes, and {PROMOTION_COMMANDS} are watched. "
        "The standards row prints its command twice, which is where the seventh comes "
        f"from; the commands found are {commands}"
    )


def test_every_promotion_home_spells_the_same_filter():
    """Six homes, one filter. Anything else is a narrowing that half landed.

    This is the assertion that makes the narrowing ATOMIC: the moment one
    home is narrowed and another is not, a contributor following
    CONTRIBUTING.md runs a different promotion from the one CI runs, and
    a warning caught in one place and not the other is the worst of the
    two states rather than a half-way point between them.
    """
    distinct = _distinct_filters()
    assert len(distinct) == 1, (
        f"the six homes spell {len(distinct)} different filters: {distinct}. Narrow "
        "all of them or none of them"
    )


def test_the_promotion_leaves_an_upstream_deprecation_alone(tmp_path):
    """An upstream deprecation is not this package's defect and must not read as one.

    Driven through the real filter rather than argued: the spec comes
    from the six homes as they are written today, and a real pytest runs
    a real warning under it.
    """
    (filters,) = _distinct_filters()
    module = _warning_module(tmp_path, "upstream", UPSTREAM_WARNING_MODULE)
    result = _run_pytest_with(filters, module)
    assert result.returncode == 0, (
        f"under {list(filters)} a dependency's DeprecationWarning fails the examples "
        f"run. Nobody here can fix an upstream deprecation, and a build that goes red "
        f"for a reason nobody can fix stops being believed.\n{result.stdout[-2000:]}"
    )


def test_the_promotion_still_catches_a_warning_this_package_raised(tmp_path):
    """The other kind, and the half a narrowing silently loses.

    The control on the test above. Both are driven through the same
    filter taken from the same six homes, so a narrowing that bought
    quiet by promoting nothing at all fails here rather than passing
    both.
    """
    (filters,) = _distinct_filters()
    module = _warning_module(tmp_path, "ours", PACKAGE_WARNING_MODULE)
    result = _run_pytest_with(filters, module)
    output = result.stdout + result.stderr
    assert "PyflightstreamWarning" in output, (
        f"under {list(filters)} a warning this package raised produced no mention of "
        f"its own category; the run failed for some other reason.\n{output[-2000:]}"
    )
    excuses = [
        token
        for token in ("ModuleNotFoundError", "ImportError", "error during collection")
        if token in output
    ]
    assert not excuses, (
        f"the run failed on {excuses} rather than on the warning, so a nonzero status "
        f"here proves nothing about the filter.\n{output[-2000:]}"
    )
    assert result.returncode != 0, (
        f"under {list(filters)} a warning this package raised did NOT fail the run. "
        "The narrowing has stopped catching ours, which is the failure mode a "
        f"warnings filter has.\n{output[-2000:]}"
    )


def test_the_filter_the_narrowing_will_use_answers_both_kinds(tmp_path):
    """The target spec, driven on a warning of each kind. Green today.

    The two tests above measure the filter the six homes CARRY; this one
    measures the filter they will carry, so the narrowing is a known
    quantity before it is written into a shipped command line rather
    than after. It is the whole of the item's promise in one assertion
    pair: an upstream deprecation survives, and one of ours does not.

    It cannot go stale quietly. If the category stops existing, or stops
    being promotable through a ``-W`` spec, or the spec's spelling
    changes, this reds; and on the day the homes are narrowed the spec
    under test and the spec they carry become the same string.
    """
    target = (PACKAGE_WARNING_FILTER,)

    upstream = _run_pytest_with(
        target, _warning_module(tmp_path, "target_up", UPSTREAM_WARNING_MODULE)
    )
    assert upstream.returncode == 0, (
        f"under {PACKAGE_WARNING_FILTER} a dependency's DeprecationWarning still fails "
        f"the run, so the narrowing buys nothing.\n{upstream.stdout[-2000:]}"
    )

    ours = _run_pytest_with(
        target, _warning_module(tmp_path, "target_ours", PACKAGE_WARNING_MODULE)
    )
    assert ours.returncode != 0 and PACKAGE_WARNING_NAME in ours.stdout + ours.stderr, (
        f"under {PACKAGE_WARNING_FILTER} a warning THIS package raised does not fail "
        "the run. A narrowing that stops catching ours is worse than the blanket it "
        f"replaced.\n{(ours.stdout + ours.stderr)[-2000:]}"
    )


def test_an_example_that_warns_in_our_voice_is_visible_on_stderr(tmp_path):
    """The witness for the stderr half of ``test_each_example_runs``.

    That assertion is negative and passes on every example today, so it
    would look identical if the warning stopped being printed at all.
    Driven here against a script written to warn, run the same way an
    example is run: no ``-W`` flag, because the interpreter cannot parse
    one naming this package's class, and none is needed.
    """
    script = tmp_path / "ops200602_warns.py"
    script.write_text(
        "import warnings\n"
        f"from {PACKAGE_WARNING_HOME} import {PACKAGE_WARNING_NAME}\n"
        f"warnings.warn('an example provoked one', {PACKAGE_WARNING_NAME})\n"
        "print('the example finished anyway')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=300,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "the example finished anyway" in result.stdout
    assert PACKAGE_WARNING_NAME in result.stderr, (
        "a warning this package raised left no trace on stderr, so the assertion in "
        "test_each_example_runs is watching a channel nothing arrives on"
    )


def test_every_warning_this_package_raises_is_promoted_or_ratcheted():
    """The categories in ``src`` and the promoted hierarchy, held equal.

    This is what allows the narrowing to be safe rather than hoped for.
    A category outside :class:`PyflightstreamWarning` is a warning the
    narrowed filter will NOT catch, so every one is named here with the
    retag it is waiting for, and a new one reds.
    """
    sites = _warn_sites()
    assert len(sites) >= WARN_SITE_FLOOR, (
        f"the walk found {len(sites)} `warnings.warn` calls under {PACKAGE}, below the "
        f"floor of {WARN_SITE_FLOOR}. A walk that finds nothing reports green, so the "
        "floor is checked before the categories are"
    )
    assert len({relative for relative, _, _ in sites}) >= WARN_FILE_FLOOR, (
        "the walk reached fewer files than it did when this floor was measured; it is "
        "matching a shape the package no longer uses"
    )

    outside = {
        (relative, category)
        for relative, _, category in sites
        if not issubclass(_resolve_category(relative, category), PyflightstreamWarning)
    }
    unwatched = outside - UNPROMOTED_WARNING_CATEGORIES
    assert not unwatched, (
        f"{sorted(unwatched)} raise a warning category the examples run's narrowed "
        f"filter would not catch. Tag them {PyflightstreamWarning.__name__} (or "
        "PyflightstreamDeprecationWarning where the site is a deprecation), or add "
        "them here with the reason they cannot be"
    )
    settled = UNPROMOTED_WARNING_CATEGORIES - outside
    assert not settled, (
        f"{sorted(settled)} are inside the promoted hierarchy now and this ratchet "
        "still holds them, so it is overstating what is owed; delete each entry in "
        "the commit that retags it"
    )

    # THE TWO HALVES, BOUND. Everything above is true whatever the six
    # homes say, so on its own it would let the narrowing land while the
    # ratchet is still full, which is the one ordering this item exists
    # to prevent. A filter naming a category is a narrowed filter, and a
    # narrowed filter catches only what the ratchet says is already
    # inside the hierarchy.
    narrowed = sorted({spec for filters in _distinct_filters() for spec in filters if "::" in spec})
    assert not (narrowed and outside), (
        f"the promotion homes narrowed to {narrowed} while {sorted(outside)} still "
        "raise a category it does not catch, so the examples run now promotes nothing "
        "this package actually raises. Retag those sites in this commit or widen the "
        "filter back"
    )


def test_the_walks_can_see_what_they_are_looking_for():
    """The mutation companion of both scans above.

    Neither scan can be proved by the tree passing: the filter scan
    would pass having matched nothing, and the category walk would pass
    having found no site outside the hierarchy. Both are driven here
    against sources written for the purpose.
    """
    assert _warning_filters_in("run: pytest src README.md docs -W error") == [(1, ("error",))]
    assert _warning_filters_in("| `pytest a -W one` and `pytest b -W two` |") == [
        (1, ("one",)),
        (1, ("two",)),
    ]
    assert _warning_filters_in("run: pytest src README.md docs") == []
    assert _warning_filters_in("ruff check . -W error") == []

    walked = _warn_categories_in(
        "import warnings\n"
        "warnings.warn('a')\n"
        "warnings.warn('b', DeprecationWarning)\n"
        "warnings.warn('c', category=FutureWarning)\n"
        "print('not a warning at all')\n"
    )
    assert walked == [(2, DEFAULT_CATEGORY), (3, "DeprecationWarning"), (4, "FutureWarning")]

    # The resolver's three routes, each driven: the default, a builtin
    # category, and a class the warning site's own module exports. The
    # last is the one that decides whether a re-parented
    # VersionMismatchWarning moves out of the ratchet by itself.
    assert _resolve_category("cases/matrix.py", DEFAULT_CATEGORY) is UserWarning
    assert not issubclass(
        _resolve_category("cases/matrix.py", "UserWarning"), PyflightstreamWarning
    )
    assert issubclass(
        _resolve_category("results/__init__.py", "VersionMismatchWarning"), UserWarning
    )
    assert issubclass(
        _resolve_category("_errors.py", PyflightstreamWarning.__name__), PyflightstreamWarning
    )


def test_the_category_walk_reaches_every_file_the_ratchet_names():
    """The ratchet's own population, asserted before it is subtracted.

    The failure this prevents was measured twice this week: a guard
    whose collection was rewritten stopped matching anything while
    passing every per-item assertion, and a fixture builder staged files
    no identifier could reach. Every path named in the ratchet must be a
    path the walk actually visits.
    """
    walked = {relative for relative, _, _ in _warn_sites()}
    named = {relative for relative, _ in UNPROMOTED_WARNING_CATEGORIES}
    # THE POPULATION ASSERTED IS THE WALK'S, not the ratchet's, since
    # 2026-08-19. It used to be the ratchet's, with the message "the
    # ratchet is empty; if that is true the narrowing is owed, not this
    # test", which was right while the ratchet held nine pairs and
    # became a false alarm the moment the retag emptied it. Emptying it
    # is the goal, so a guard that reds on the goal is a guard that will
    # be deleted rather than read. What must never be empty is the WALK:
    # a walk finding no warn site at all would make every subtraction
    # below vacuous, which is the failure this test exists for.
    assert walked, (
        "the warn-site walk found nothing, so every assertion over it is vacuous. "
        "Either the package raises no warning at all, which the floors below deny, "
        "or the walk stopped matching"
    )
    missing = named - walked
    assert not missing, (
        f"the ratchet names {sorted(missing)}, which the walk does not reach. Either "
        "the file moved and the entry is now unreachable, or the walk stopped seeing "
        "it; both make this guard smaller than it reads"
    )
