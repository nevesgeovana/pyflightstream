"""Tier 1: every optional extra refuses the same way, with a remedy that works.

REV-002 finding PYFS-025, the typed half. Three code paths gated on an
optional extra raised three different exception types with three
hand-written remedy strings, so a caller who wanted to handle "an extra
is missing" had to know all three, and nothing checked that the
remedies were spelled the way the packaging spells them.

The license half of the same finding is documentary and lives in
`reports/RPT-016`, with `test_every_extra_has_a_license_card` below
holding it to the extras that actually exist.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from pyflightstream.extras import EXTRAS, MissingExtraError, require_extra

REPO = Path(__file__).resolve().parents[1]

#: Extras that gate no runtime code path, so no user can reach a
#: refusal for them. Named rather than filtered silently: `dev` is a
#: contributor's install, and a future extra that belongs here should
#: be a deliberate entry rather than an omission nobody notices.
NOT_USER_FACING = {"dev"}


def _declared_extras() -> dict[str, list[str]]:
    with open(REPO / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["optional-dependencies"]


def test_the_extras_table_matches_the_packaging():
    """`EXTRAS` and pyproject are one fact.

    An extra renamed in packaging and not here would build an install
    command that fails, which is worse than no message: it sends the
    reader away confident.
    """
    declared = set(_declared_extras()) - NOT_USER_FACING
    assert set(EXTRAS) == declared, (
        f"pyflightstream.extras.EXTRAS names {sorted(EXTRAS)} and pyproject "
        f"declares {sorted(declared)} (ignoring {sorted(NOT_USER_FACING)})"
    )


@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_each_extra_names_the_distributions_it_installs(extra):
    """The table says what arrives, so a refusal can name the right package."""
    declared = _declared_extras()[extra]
    # pyproject entries may carry a version bound; compare on the name.
    names = {re.split(r"[<>=!~\[]", spec)[0].strip().lower() for spec in declared}
    assert {package.lower() for package in EXTRAS[extra]} == names, (
        f"extra [{extra}] installs {sorted(names)} but EXTRAS records {sorted(EXTRAS[extra])}"
    )


@pytest.mark.requirement("NFR-25")
@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_the_refusal_carries_the_exact_install_command(extra):
    """One type, and a remedy composed from the extra's own name.

    This is the assertion PYFS-025 owes, parametrized per extra as it
    asks. The remedy is built rather than written, so it cannot drift
    from the name that makes it work.
    """
    error = require_extra(extra, package="somepkg", purpose="the thing")
    assert isinstance(error, MissingExtraError)
    assert isinstance(error, ImportError)
    assert error.extra == extra
    assert error.remedy == f"pip install pyflightstream[{extra}]"
    assert error.remedy in str(error)
    assert "somepkg" in str(error)
    assert "the thing" in str(error)


def test_a_refusal_cannot_name_an_extra_that_does_not_exist():
    """The failure mode the composed remedy exists to prevent."""
    with pytest.raises(ValueError, match="not an extra of this package"):
        require_extra("geometry", package="trimesh", purpose="the gate")
    # The control: the real name is accepted, so the refusal is about the
    # value and not about the check being unconditional.
    assert require_extra("geom", package="trimesh", purpose="the gate").extra == "geom"


def test_every_gated_path_raises_the_shared_type():
    """No path may go back to a bare ImportError with a typed-out remedy.

    Read from the source rather than by triggering each path, because
    triggering them needs the extras to be ABSENT and this suite runs
    with them installed. What it pins is the invariant that made the
    finding: an install remedy appears in this package only inside the
    one class that builds it.
    """
    offenders = []
    for path in sorted((REPO / "src").rglob("*.py")):
        if path.name == "extras.py":
            continue  # the one home of the string
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            # Only the literals INSIDE a raise. A module docstring or a
            # comment naming the install command is documentation and is
            # meant to stay: probes/geometry.py's own top-docstring does
            # exactly that, and an earlier version of this guard flagged
            # it, which would have taught the reader to delete the prose
            # instead of the duplication.
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    if "pip install pyflightstream[" in inner.value:
                        rel = path.relative_to(REPO).as_posix()
                        offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "these raises write an install remedy by hand instead of using "
        "MissingExtraError, which is how three paths came to print three "
        f"different strings: {sorted(set(offenders))}"
    )


def test_the_geometry_gate_is_still_its_own_catchable_name():
    """The one extra whose absence is recoverable keeps a name of its own.

    A caller can continue without culling, so singling the geometry gate
    out is a real need; it is a SUBCLASS so `except MissingExtraError`
    catches it too.
    """
    from pyflightstream.probes.geometry import GeometryEngineMissingError

    assert issubclass(GeometryEngineMissingError, MissingExtraError)
    assert issubclass(GeometryEngineMissingError, ImportError)


@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_every_extra_has_a_license_card(extra):
    """NFR-02: evidence before adoption, and the cards must cover the set.

    Measured at PYFS-025: the runtime dependencies had no card at all
    and `[plot]` had none either, while `[fsi]` and `[geom]` did. The
    cards are prose, so this checks coverage rather than content: every
    extra's distributions are named somewhere under `reports/`.
    """
    cards = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((REPO / "reports").glob("RPT-*.md"))
    ).lower()
    missing = [package for package in EXTRAS[extra] if package.lower() not in cards]
    assert not missing, (
        f"extra [{extra}] installs {missing} and no committed report under "
        "reports/ names them. NFR-02 wants a license-evidence card before "
        "adoption, not after"
    )


@pytest.mark.requirement("NFR-02")
def test_every_runtime_dependency_has_a_license_card():
    """The set that reaches every user, which is the one that had no card."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        runtime = tomllib.load(handle)["project"]["dependencies"]
    names = [re.split(r"[<>=!~\[]", spec)[0].strip() for spec in runtime]
    assert names, "the runtime dependency list is empty; the scan is broken"
    cards = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((REPO / "reports").glob("RPT-*.md"))
    ).lower()
    missing = [name for name in names if name.lower() not in cards]
    assert not missing, (
        f"runtime dependencies {missing} have no license-evidence card under "
        "reports/. These reach every user of the package"
    )
