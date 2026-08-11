"""Tier 1: nothing this repository runs may import an extra CI lacks.

A distribution that arrives with an optional extra is present on a
maintainer's machine and absent in CI, so an unguarded import of one
passes locally forever, passes every reviewer pass, and fails on every
CI leg that lacks it. That is not hypothetical here: it is what the
v0.7.0 tag cost (INC-20260810-2140-shared). The import sat in
``tests/test_utils_manual.py`` from the release's first commit, every
reviewer pass read the diff in an environment that had pypdf, and the
first machine to disagree was CI.

THE FORBIDDEN SET IS DERIVED AND NEVER WRITTEN DOWN. It is the
distributions of the extras pyproject declares, minus everything a CI job
is guaranteed to install: the base dependencies, and the extras that
EVERY install line of THIS package names. Rename an extra, add one, or
change what a workflow installs, and this file follows with no edit.

Guaranteed means the intersection, deliberately, rather than equality
across the install lines. One leg installs everything (that is the whole
point of ``test-all-extras``) without shrinking what the other legs
prove. Requiring the lines to AGREE would make that leg impossible;
requiring the intersection makes it free.

Five companion assertions exist because the main one is negative, and a
negative assertion is the shape that passes by measuring nothing. They
fail if the derived set is empty, if no leg installs every extra, if the
guaranteed set quietly widens, if the walk stops reaching the files it
claims, or if a scanned surface is unparseable. None of them is
decoration: a guard of this shape already shipped in this workspace with
a flat ``glob`` where it needed ``rglob``, was green, and covered a
fraction of what its name claimed (INC-20260809-2230-pyflightstream).

WHAT THIS DOES NOT REACH, stated so the coverage is not overread.
``.claude/`` is outside the scan: those bodies are vendored or hook-owned
and one of them is pinned by hash, so an optional import there is
unguarded by this test. Neither are imports reached through a console
script, an entry point, a pytest plugin, or ``import_module`` with a
computed argument.
"""

from __future__ import annotations

import ast
import doctest
import importlib.metadata
import re
import textwrap
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: Every tree whose python this repository executes somewhere: shipped
#: package, test suite, published examples, maintainer scripts, and the
#: two hook and tool trees that tier 1 loads by path.
#:
#: `.claude` is named by its two leaves rather than whole, because
#: `.claude/worktrees/` holds entire checkouts of this repository that
#: reviewer agents park there; walking it would scan copies of every
#: file, including mid-mutation ones.
SCAN_ROOTS = ("src", "tests", "examples", "scripts", ".claude/hooks", ".claude/tools")

#: The partition the main assertion runs over. "root" catches the files
#: that sit at the repository root (the conftest), "markdown" the fenced
#: blocks. Every label must fall in exactly one, which is asserted.
SCAN_PARTITION = (*SCAN_ROOTS, "root", "markdown")

#: A pip install of THIS package, with or without an extras bracket.
#: Bracket-less matters: such a line installs no extras at all, and
#: counting it is what keeps the intersection honest. Lines installing
#: OTHER distributions (pip, build, twine) are deliberately not matched.
_PACKAGE_INSTALL = re.compile(
    r"pip install\s+(?:--?\S+\s+)*(?:-e\s+)?[\"']?(?:\.|dist/\S*?\.whl|dist/\S*?\}\})"
    r"(?:\[([A-Za-z0-9_,\- ]*)\])?[\"']?"
)

#: A fenced python block in a markdown page. Built from chr() so this
#: file contains no fence of its own to confuse a scan of itself.
#:
#: The leading character class matters: Sybil accepts a fence indented
#: under a list item or a blockquote, and a fence indented inside a
#: numbered step is ordinary tutorial markdown. Anchoring at column zero
#: would walk past one and report it scanned.
_BACKTICKS = chr(96) * 3
_FENCE_PREFIX = r"^[ \t>*+\-0-9.)]*"
_FENCE = re.compile(
    _FENCE_PREFIX + _BACKTICKS + r"(?:python|py)\s*$(.*?)" + _FENCE_PREFIX + _BACKTICKS + r"\s*$",
    re.MULTILINE | re.DOTALL,
)

#: Exception names whose handler makes an import optional rather than
#: required. A bare ``except:`` counts too, and is handled below.
_HANDLED = frozenset({"ImportError", "ModuleNotFoundError", "Exception"})

#: Names that make a block annotation-only. An import under one provably
#: never executes, so refusing it would be a false positive, and a false
#: positive on a guard like this is how the guard gets weakened.
_TYPE_ONLY = frozenset({"TYPE_CHECKING", "typing.TYPE_CHECKING"})

#: Call targets that import by name at run time, so a constant string
#: argument is an import the ast import nodes do not see.
_DYNAMIC = frozenset({"import_module", "__import__"})

#: The extras every job is expected to install. A ratchet, not a
#: derivation; see the test that reads it.
EXPECTED_GUARANTEED = frozenset({"dev", "fsi", "geom"})


def _distribution_of(specifier: str) -> str:
    """Return the distribution name at the head of a requirement string.

    Parameters
    ----------
    specifier : str
        A PEP 508 requirement, for example ``pypdf>=4.0; python_version<'3.13'``.

    Returns
    -------
    str
        The distribution name alone, lowercased.
    """
    return re.split(r"[<>=!~\[; ]", specifier)[0].strip().lower()


def _pyproject() -> dict:
    """Read pyproject.toml, the single home of the dependency facts."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)


def workflow_install_sets() -> dict[str, set[str]]:
    """Map ``file:line`` to the extras each install line of this package names.

    Returns
    -------
    dict of str to set of str
        One entry per line installing this package. A line with no extras
        bracket maps to the empty set, which collapses the intersection
        below; that is the fail-safe direction, because such a job runs
        with none of the optional distributions available.
    """
    found: dict[str, set[str]] = {}
    for path in sorted((REPO / ".github" / "workflows").glob("*.y*ml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            match = _PACKAGE_INSTALL.search(line)
            if match:
                raw = match.group(1) or ""
                found[f"{path.name}:{number}"] = {
                    part.strip() for part in raw.split(",") if part.strip()
                }
    return found


def guaranteed_extras() -> set[str]:
    """Extras that every install line of this package names."""
    sets = list(workflow_install_sets().values())
    if not sets:
        return set()
    return set.intersection(*sets)


def declared_extras() -> dict[str, list[str]]:
    """The optional-dependency table, distribution names only."""
    optional = _pyproject()["project"].get("optional-dependencies", {})
    return {name: [_distribution_of(spec) for spec in specs] for name, specs in optional.items()}


def unavailable_distributions() -> set[str]:
    """Distributions an extra provides that some CI job may not have.

    Subtracts the base dependencies and the distributions the guaranteed
    extras already name, because an extra whose contents arrive anyway is
    not a trap.

    Does NOT subtract transitive dependencies. matplotlib reaches CI
    today only because PyNiteFEA requires it, which is a third party's
    decision that can change in a point release without a commit here.

    Returns
    -------
    set of str
        Lowercased distribution names.
    """
    table = _pyproject()["project"]
    optional = declared_extras()
    guaranteed = guaranteed_extras()

    always = {_distribution_of(spec) for spec in table.get("dependencies", [])}
    for name in guaranteed:
        always |= set(optional.get(name, []))

    at_risk: set[str] = set()
    for name, distributions in optional.items():
        if name in guaranteed:
            continue
        at_risk |= set(distributions)
    return at_risk - always


def forbidden_import_roots() -> set[str]:
    """Top-level module names the unavailable distributions provide.

    A distribution name is not an import name. This repository already
    owns the counter-example: the ``fsi`` extra installs ``PyNiteFEA``
    and the code writes ``import Pynite``. Comparing import roots against
    distribution names works today only because pypdf and matplotlib
    happen to coincide, and would silently stop working the day another
    extra left the guaranteed set.

    Resolved from installed metadata where available, and always
    including the distribution's own name, so the answer degrades to the
    older behaviour rather than to nothing when a distribution is absent.
    """
    unavailable = unavailable_distributions()
    roots = set(unavailable)
    for module, distributions in importlib.metadata.packages_distributions().items():
        if any(name.lower() in unavailable for name in distributions):
            roots.add(module.lower())
    return roots


def _handles_import_failure(handler: ast.ExceptHandler) -> bool:
    """Whether one except clause turns an import failure into a fallback."""
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in _HANDLED
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(element, ast.Name) and element.id in _HANDLED
            for element in handler.type.elts
        )
    return False


def _is_type_checking_test(node: ast.expr) -> bool:
    """Whether an if test is the TYPE_CHECKING constant."""
    return ast.unparse(node).replace(" ", "") in _TYPE_ONLY


def _guarded_node_ids(tree: ast.AST) -> set[int]:
    """Identify every node an import failure cannot reach, or cannot break.

    Two shapes qualify. A ``try`` whose handler catches an import failure
    makes the import optional. An ``if TYPE_CHECKING:`` block never
    executes at all, so an import inside one cannot fail at run time;
    refusing it would be a false positive on an idiom this repository
    already uses in four modules, and a false positive is how a guard
    like this gets weakened rather than fixed.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for statement in node.body:
                for inner in ast.walk(statement):
                    guarded.add(id(inner))
            continue
        if not isinstance(node, ast.Try):
            continue
        if not any(_handles_import_failure(handler) for handler in node.handlers):
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                guarded.add(id(inner))
    return guarded


def unguarded_imports(source: str, forbidden: set[str]) -> list[tuple[int, str]]:
    """Find every unguarded import of a forbidden module root.

    Takes source TEXT rather than a path, so the scanner can be driven
    with synthetic input. A negative assertion that can only be run over
    the real tree cannot be told apart from one that scans nothing.

    Parameters
    ----------
    source : str
        Python source to parse.
    forbidden : set of str
        Lowercased top-level module names that must not be imported bare.

    Returns
    -------
    list of tuple of (int, str)
        Sorted ``(line number, module root)`` pairs, empty when clean.

    Raises
    ------
    SyntaxError
        When the source does not parse. Deliberately propagated rather
        than swallowed: a surface that silently counts as clean is a
        third way for a negative assertion to measure nothing.
    """
    tree = ast.parse(source)
    guarded = _guarded_node_ids(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0].lower()
                if root in forbidden:
                    found.append((node.lineno, root))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0].lower()
            if root in forbidden:
                found.append((node.lineno, root))
        elif isinstance(node, ast.Call):
            if ast.unparse(node.func).split(".")[-1] not in _DYNAMIC:
                continue
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    root = argument.value.split(".")[0].lower()
                    if root in forbidden:
                        found.append((node.lineno, root))
    return sorted(set(found))


def doctest_source(text: str) -> str:
    """Join the statements of every doctest example found in a text.

    An AST scanner cannot see an import inside a docstring, because there
    it is a string constant rather than an Import node. Sybil executes
    those doctests on every platform leg, so they are as real a surface
    as the module around them. This lifts them out so the same scan
    applies.
    """
    try:
        examples = doctest.DocTestParser().get_examples(text)
    except ValueError:
        return ""
    return "".join(example.source for example in examples)


def python_surfaces() -> list[tuple[str, str]]:
    """Return ``(label, source)`` for every python surface this repository runs.

    Three kinds. The python files of the scanned trees; the doctests
    inside them, which Sybil runs as a separate step; and the fenced
    python blocks of the README and the docs pages, which Sybil also
    runs. A fenced block written as a doctest session is not valid
    python, so it is recovered through the doctest parser rather than
    dropped: one such block exists today, and before this it was counted
    as scanned and silently discarded.
    """
    out: list[tuple[str, str]] = []
    for root in SCAN_ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            label = path.relative_to(REPO).as_posix()
            text = path.read_text(encoding="utf-8")
            out.append((label, text))
            examples = doctest_source(text)
            if examples.strip():
                out.append((f"{label}#doctests", examples))
    out.append(("conftest.py", (REPO / "conftest.py").read_text(encoding="utf-8")))
    for path in [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        for index, match in enumerate(_FENCE.finditer(text), 1):
            label = f"{path.relative_to(REPO).as_posix()}#block{index}"
            block = textwrap.dedent(match.group(1))
            try:
                ast.parse(block)
            except SyntaxError:
                block = doctest_source(block)
            out.append((label, block))
    return out


def partition_of(label: str) -> str:
    """Which member of SCAN_PARTITION a surface label belongs to."""
    if "#block" in label:
        return "markdown"
    for root in SCAN_ROOTS:
        if label.startswith(f"{root}/"):
            return root
    return "root"


def test_the_workflows_name_at_least_one_install_of_this_package():
    """No install line found means the derivation below read nothing."""
    assert workflow_install_sets(), (
        "no pip install of this package was found in .github/workflows, so what CI "
        "installs could not be derived and the scan below would forbid nothing. The "
        "regex or the workflow layout moved."
    )


def test_one_job_installs_every_declared_extra():
    """Something must run the assertions the other legs skip.

    Guarding an optional import correctly, and stopping there, converts a
    red test into a permanently silent skip. That is what the first fix
    for INC-20260810-2140-shared did, and it is why the all-extras leg is
    half of this guard rather than a convenience. Delete that leg and
    this fails; before this assertion existed, deleting it was silent.
    """
    installed = workflow_install_sets()
    declared = set(declared_extras())
    fullest = max(installed.values(), key=len, default=set())
    assert any(extras >= declared for extras in installed.values()), (
        f"no CI job installs every declared extra {sorted(declared)}; the fullest "
        f"install line names {sorted(fullest)}. An assertion gated behind an extra "
        "nothing installs executes nowhere, which is not weaker evidence than a red "
        "test, it is none."
    )


def test_the_unavailable_set_is_not_empty():
    """A negative assertion over an empty set is vacuously true.

    If every declared extra becomes guaranteed, this file stops proving
    anything and must be deleted deliberately rather than kept as a green
    test that measures nothing.
    """
    assert unavailable_distributions(), (
        "every declared extra is now installed by every job, so the scan below can "
        "never fail. Either the derivation broke, or the extras are genuinely all "
        "guaranteed and this file should be deleted on purpose."
    )


def test_the_guaranteed_set_has_not_quietly_widened():
    """A ratchet, because the derivation follows drift and not strength.

    Deriving what CI installs is right for a rename or a new extra, and
    wrong for severity: adding an extra to every install line silently
    removes its distributions from the forbidden set and nothing else
    here would notice. The four platform legs are deliberately lean, and
    that intent is prose in ci.yml until this assertion holds it.
    """
    assert guaranteed_extras() == set(EXPECTED_GUARANTEED), (
        f"the extras every job installs are now {sorted(guaranteed_extras())}, not "
        f"{sorted(EXPECTED_GUARANTEED)}. Widening this WEAKENS every assertion below, "
        "because a guaranteed extra's distributions leave the forbidden set. If the "
        "change is deliberate, move EXPECTED_GUARANTEED in the same commit and say "
        "why; if it was made to silence skips, add a job that installs more instead "
        "of widening the lean legs, which are the probe that the package works "
        "without optional extras."
    )


def test_the_scanner_finds_what_it_is_looking_for():
    """The positive control: drive the scanner with synthetic source.

    Without this, a wrong root path or a broken parse makes every
    assertion below pass by scanning nothing.
    """
    forbidden = {"pypdf"}
    assert unguarded_imports("import pypdf\n", forbidden) == [(1, "pypdf")]
    assert unguarded_imports("from pypdf import PdfReader\n", forbidden) == [(1, "pypdf")]
    assert unguarded_imports("import pypdf as reader\n", forbidden) == [(1, "pypdf")]
    assert unguarded_imports("import pypdf.generic\n", forbidden) == [(1, "pypdf")]
    assert unguarded_imports("def render():\n    import pypdf\n", forbidden) == [(2, "pypdf")]
    assert unguarded_imports("import importlib\nimportlib.import_module('pypdf')\n", forbidden) == [
        (2, "pypdf")
    ]

    # And the forms that are genuinely optional, which must NOT be found.
    assert (
        unguarded_imports(
            "try:\n    import pypdf\nexcept ImportError:\n    pypdf = None\n", forbidden
        )
        == []
    )
    assert (
        unguarded_imports(
            "try:\n    import pypdf\nexcept ModuleNotFoundError:\n    pypdf = None\n", forbidden
        )
        == []
    )
    assert (
        unguarded_imports("import pytest\npypdf = pytest.importorskip('pypdf')\n", forbidden) == []
    )
    assert unguarded_imports("import numpy\n", forbidden) == []


def test_the_import_root_mapping_can_see_a_renamed_distribution():
    """A distribution name is not an import name, and one here is not.

    The ``fsi`` extra installs PyNiteFEA and the code writes
    ``import Pynite``. Comparing import roots against distribution names
    works today only because pypdf and matplotlib coincide. This asserts
    the mapping that makes the guard survive an extra leaving the
    guaranteed set, against real installed metadata rather than a
    synthetic fixture.
    """
    mapping = importlib.metadata.packages_distributions()
    assert mapping, "importlib.metadata reported no installed distributions at all"
    renamed = [
        (module, names)
        for module, names in mapping.items()
        if all(module.lower() != name.lower() for name in names)
    ]
    assert renamed, (
        "no installed distribution has an import name different from its distribution "
        "name, so this environment cannot demonstrate the mapping the guard depends "
        "on. Check that the dev and fsi extras are installed."
    )


def test_the_walk_reaches_nested_files_and_markdown_blocks():
    """The walk covers what its name claims, measured rather than assumed.

    A flat glob where a recursive one was meant is green and covers a
    fraction of the tree (INC-20260809-2230-pyflightstream). These
    anchors fail the moment the walk stops descending.
    """
    labels = {label for label, _ in python_surfaces()}

    assert "conftest.py" in labels, "the root conftest is not being scanned"

    nested = [name for name in labels if name.startswith("src/pyflightstream/utils/")]
    assert nested, (
        "no file under src/pyflightstream/utils/ was scanned, so the walk is not "
        "descending into subpackages"
    )

    blocks = [name for name in labels if "#block" in name]
    assert blocks, (
        "no fenced python block was scanned, so an unguarded import in the README or "
        "in a docs page would not be seen even though Sybil executes it"
    )
    assert any(name.startswith("docs/") for name in blocks), (
        "no fenced block under docs/ was scanned; only the README was reached"
    )


def test_every_scanned_surface_is_claimed_by_exactly_one_partition():
    """The walk reaching a file is not the same as an assertion testing it.

    The first version of this file scanned the root conftest and then
    tested only labels starting with a scan root, so the one file whose
    bad import fails every CI leg at collection time was walked and never
    asserted. That is the INC-20260809-2230 defect moved one level: the
    coverage claim was about the walk, not about the assertion. This ties
    the two together, so a surface added to the walk cannot fall out of
    the assertion silently.
    """
    labels = [label for label, _ in python_surfaces()]
    assert labels, "no surfaces at all"
    for label in labels:
        assert partition_of(label) in SCAN_PARTITION, label
    missing = set(SCAN_PARTITION) - {partition_of(label) for label in labels}
    assert not missing, (
        f"the partition {sorted(SCAN_PARTITION)} claims members that match no scanned "
        f"surface: {sorted(missing)}. A parameter that selects nothing is a green case "
        "measuring an empty set."
    )


def test_every_scanned_surface_parses():
    """An unparseable surface must be a decision, not a silent exemption.

    ``unguarded_imports`` raises rather than returning an empty list, and
    this is where that surfaces. A fenced block with an elision in it is
    the likely first offender, and the right answer is to mark the block
    rather than to let the scanner skip it.
    """
    broken: list[str] = []
    for label, source in python_surfaces():
        try:
            ast.parse(source)
        except SyntaxError as error:
            broken.append(f"{label}: {error}")
    assert not broken, (
        "these scanned surfaces do not parse, so the import scan cannot see them:\n  "
        + "\n  ".join(broken)
        + "\nA surface the scanner cannot read is a surface it reports clean."
    )


@pytest.mark.parametrize("part", SCAN_PARTITION)
def test_no_unguarded_import_of_a_distribution_ci_may_lack(part):
    """The assertion the v0.7.0 tag paid for.

    Parametrized by partition rather than by file so the suite gains six
    cases instead of a few hundred; the message names every offending
    file and line, so the failure is no less precise.
    """
    forbidden = forbidden_import_roots()
    offenders: list[str] = []
    for label, source in python_surfaces():
        if partition_of(label) != part:
            continue
        for line, module in unguarded_imports(source, forbidden):
            offenders.append(f"{label}:{line} imports {module}")

    assert not offenders, (
        "these imports are not guarded, and the modules they name come from an extra "
        "that at least one CI job does not install:\n  "
        + "\n  ".join(sorted(offenders))
        + f"\n\nDerived as unavailable: {sorted(unavailable_distributions())} "
        f"(import roots {sorted(forbidden)}). Guaranteed extras: "
        f"{sorted(guaranteed_extras())}.\n"
        "An import like this passes on a maintainer machine, which carries every "
        "extra, and fails on the CI legs that do not. Use the form that fits the "
        "tree:\n"
        "  tests/     pypdf = pytest.importorskip('pypdf')\n"
        "  src/       try:\n"
        "                 import pypdf\n"
        "             except ImportError as error:\n"
        "                 raise missing_extra('manual', package='pypdf',\n"
        "                                     purpose='what you were doing') from error\n"
        "             RAISE it. missing_extra RETURNS the exception; written as a\n"
        "             bare statement it builds one, discards it and continues, which\n"
        "             is the silence pyflightstream.extras was renamed to prevent.\n"
        "  examples/  try/except ModuleNotFoundError with a printed skip line and an\n"
        "             else: body, as in examples/wing_static_deflection.py, so the\n"
        "             script degrades instead of aborting."
    )
