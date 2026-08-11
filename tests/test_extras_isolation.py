"""Tier 1: nothing this repository runs may import an extra CI lacks.

A distribution that arrives with an optional extra is present on a
maintainer's machine and absent in CI, so an unguarded import of one
passes locally forever, passes every reviewer pass, and fails on every
CI leg. That is not hypothetical here: it is what the v0.7.0 tag cost
(INC-20260810-2140-shared). The import sat at
``tests/test_utils_manual.py`` from the release's first commit, fifteen
reviewer passes read the diff in an environment that had pypdf, and the
first machine to disagree was the one running the release.

THE FORBIDDEN SET IS DERIVED AND NEVER WRITTEN DOWN. It is the
distributions of the extras pyproject declares, minus everything a CI
job is guaranteed to install: the base dependencies, and the extras that
EVERY install line in EVERY workflow names. Rename an extra, add one, or
change what a workflow installs, and this file follows with no edit.

Guaranteed means the intersection, deliberately, rather than equality
across the install lines. One leg may install more (there is such a leg,
so the assertions gated behind ``manual`` execute somewhere) without
shrinking what the other legs prove. Requiring the lines to AGREE would
make that leg impossible; requiring the intersection makes it free.

Two companion assertions exist because the main one is negative, and a
negative assertion is the shape that passes by measuring nothing: one
fails if the derived set is empty, one fails if the walk stops reaching
the files it claims to cover. The second is not decoration. A guard of
this shape already shipped in this workspace with a flat ``glob`` where
it needed ``rglob``, was green, and covered a fraction of what its name
claimed (INC-20260809-2230-pyflightstream).
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: Every tree whose python this repository executes somewhere: shipped
#: package, test suite, published examples, maintainer scripts.
SCAN_ROOTS = ("src", "tests", "examples", "scripts")

#: An extras bracket on a pip install line, in any workflow.
_INSTALL = re.compile(r"pip install[^\n]*?\[([A-Za-z0-9_,\- ]+)\]")

#: A fenced python block in a markdown page. Built from chr() so this
#: file contains no fence of its own to confuse the scan of itself.
_BACKTICKS = chr(96) * 3
_FENCE = re.compile(
    "^" + _BACKTICKS + r"(?:python|py)\s*$(.*?)^" + _BACKTICKS + r"\s*$",
    re.MULTILINE | re.DOTALL,
)

#: Exception names whose handler makes an import optional rather than
#: required. A bare ``except:`` counts too, and is handled below.
_HANDLED = frozenset({"ImportError", "ModuleNotFoundError", "Exception"})

#: Call targets that import by name at run time, so a string argument is
#: an import the ast import nodes do not see.
_DYNAMIC = frozenset({"import_module", "__import__"})


def _distribution_of(specifier: str) -> str:
    """Return the distribution name at the head of a requirement string.

    Parameters
    ----------
    specifier : str
        A PEP 508 requirement, for example ``pypdf>=4.0``.

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
    """Map ``file:line`` to the extras that install line names.

    Returns
    -------
    dict of str to set of str
        One entry per pip install line carrying an extras bracket.
    """
    found: dict[str, set[str]] = {}
    for path in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            match = _INSTALL.search(line)
            if match:
                found[f"{path.name}:{number}"] = {
                    part.strip() for part in match.group(1).split(",") if part.strip()
                }
    return found


def guaranteed_extras() -> set[str]:
    """Extras that every workflow install line names, so CI always has them."""
    sets = list(workflow_install_sets().values())
    if not sets:
        return set()
    return set.intersection(*sets)


def unavailable_distributions() -> set[str]:
    """Distributions an extra provides that a CI job may not have.

    Subtracts the base dependencies and the distributions the guaranteed
    extras already name, because an extra whose contents arrive anyway is
    not a trap. Does NOT subtract transitive dependencies: matplotlib
    reaches CI today only because a third party requires it, and that is
    a decision this repository does not control.

    Returns
    -------
    set of str
        Lowercased distribution names, empty only if something is wrong.
    """
    table = _pyproject()["project"]
    optional = table.get("optional-dependencies", {})
    guaranteed = guaranteed_extras()

    always = {_distribution_of(spec) for spec in table.get("dependencies", [])}
    for name in guaranteed:
        always |= {_distribution_of(spec) for spec in optional.get(name, [])}

    at_risk: set[str] = set()
    for name, specs in optional.items():
        if name in guaranteed:
            continue
        at_risk |= {_distribution_of(spec) for spec in specs}
    return at_risk - always


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


def _guarded_node_ids(tree: ast.AST) -> set[int]:
    """Identify every node lexically inside a try that catches an import failure."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_handles_import_failure(handler) for handler in node.handlers):
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                guarded.add(id(inner))
    return guarded


def unguarded_imports(source: str, forbidden: set[str]) -> list[tuple[int, str]]:
    """Find every unguarded import of a forbidden distribution.

    Takes source TEXT rather than a path, so the scanner can be driven
    with synthetic input. A negative assertion that can only be run over
    the real tree cannot be told apart from one that scans nothing.

    Parameters
    ----------
    source : str
        Python source to parse.
    forbidden : set of str
        Lowercased distribution names that must not be imported bare.

    Returns
    -------
    list of tuple of (int, str)
        Sorted ``(line number, distribution)`` pairs, empty when clean.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
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


def python_surfaces() -> list[tuple[str, str]]:
    """Return ``(label, source)`` for every python surface this repository runs.

    Includes the fenced python blocks of the README and the docs pages,
    because Sybil executes them and an unguarded import there fails in
    exactly the same job.
    """
    out: list[tuple[str, str]] = []
    for root in SCAN_ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            out.append((path.relative_to(REPO).as_posix(), path.read_text(encoding="utf-8")))
    out.append(("conftest.py", (REPO / "conftest.py").read_text(encoding="utf-8")))
    for path in [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        for index, match in enumerate(_FENCE.finditer(text), 1):
            label = f"{path.relative_to(REPO).as_posix()}#block{index}"
            out.append((label, match.group(1)))
    return out


def test_the_workflows_name_at_least_one_extras_set():
    """No install line found means the derivation below read nothing."""
    sets = workflow_install_sets()
    assert sets, (
        "no pip install line with an extras bracket was found in "
        ".github/workflows, so what CI installs could not be derived and the "
        "scan below would forbid nothing. The regex or the workflow layout moved."
    )


def test_the_unavailable_set_is_not_empty():
    """A negative assertion over an empty set is vacuously true.

    If every declared extra becomes guaranteed, this file stops proving
    anything and must be deleted deliberately rather than kept as a green
    test that measures nothing.
    """
    assert unavailable_distributions(), (
        "every declared extra is now installed by every workflow, so the scan "
        "below can never fail. Either the derivation broke, or the extras are "
        "genuinely all guaranteed and this file should be deleted on purpose."
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


def test_the_walk_reaches_nested_files_and_markdown_blocks():
    """The walk covers what its name claims, measured rather than assumed.

    A flat glob where a recursive one was meant is green and covers a
    fraction of the tree (INC-20260809-2230-pyflightstream). These three
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
        "no fenced python block was scanned, so an unguarded import in the README "
        "or in a docs page would not be seen even though Sybil executes it"
    )
    assert any(name.startswith("docs/") for name in blocks), (
        "no fenced block under docs/ was scanned; only the README was reached"
    )


@pytest.mark.parametrize("root", [*SCAN_ROOTS, "markdown"])
def test_no_unguarded_import_of_a_distribution_ci_may_lack(root):
    """The assertion the v0.7.0 tag paid for.

    Parametrized by tree rather than by file so the suite gains five
    cases instead of a few hundred; the message names every offending
    file and line, so the failure is no less precise.
    """
    forbidden = unavailable_distributions()
    offenders: list[str] = []
    for label, source in python_surfaces():
        in_this_root = "#block" in label if root == "markdown" else label.startswith(f"{root}/")
        if not in_this_root:
            continue
        for line, distribution in unguarded_imports(source, forbidden):
            offenders.append(f"{label}:{line} imports {distribution}")

    assert not offenders, (
        "these imports are not guarded, and the distributions they name belong to "
        "an extra that at least one CI job does not install:\n  "
        + "\n  ".join(sorted(offenders))
        + f"\n\nDerived as unavailable: {sorted(forbidden)}. Guaranteed extras: "
        f"{sorted(guaranteed_extras())}.\n"
        "An import like this passes on a maintainer machine, which carries every "
        "extra, and fails on the CI legs that do not. In a test use "
        "pytest.importorskip(...); in shipped code use try/except ImportError with "
        "pyflightstream.extras.missing_extra(...), so the refusal names the extra "
        "and the install command."
    )
