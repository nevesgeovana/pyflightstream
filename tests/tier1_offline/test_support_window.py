"""Tier 1: the declared Python and dependency window follows SPEC 0.

PFS-2024.07. Until 0.13.0 the window in ``pyproject.toml`` was chosen
(``>=3.11`` since the first release, and no floor on the numerical
dependencies at all), and a user reading it to learn whether their
environment is supported had no way to know how it would move. The
window now follows the scientific-python community schedule, SPEC 0
(https://scientific-python.org/specs/spec-0000/): a Python version is
supported for THREE years after its initial release and a core package
version for TWO, and the floor is the oldest version still inside that
window on the date the window was computed.

The test re-derives the floor from the release dates and a stated date
rather than holding a constant, so the day the schedule moves past the
declared floor this file says so, and the commit that moves the floor
states the new date beside it. The release dates below were read from
PyPI (``upload_time`` of the first file of each release) and from the
Python release schedule on 2026-09-09.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest
from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]

#: The date the window in pyproject.toml was computed for. Moving the
#: floor is a deliberate commit that moves this date with it.
WINDOW_COMPUTED_ON = dt.date(2026, 9, 9)

#: Initial release dates, from the Python release schedule (PEP 664,
#: PEP 693, PEP 719, PEP 745) and PyPI.
PYTHON_RELEASES = {
    "3.11": dt.date(2022, 10, 24),
    "3.12": dt.date(2023, 10, 2),
    "3.13": dt.date(2024, 10, 7),
    "3.14": dt.date(2025, 10, 7),
}
PACKAGE_RELEASES = {
    "numpy": {
        "2.0": dt.date(2024, 6, 16),
        "2.1": dt.date(2024, 8, 18),
        "2.2": dt.date(2024, 12, 8),
        "2.3": dt.date(2025, 6, 7),
        "2.4": dt.date(2025, 12, 20),
        "2.5": dt.date(2026, 6, 21),
    },
    "pandas": {
        "2.2": dt.date(2024, 1, 20),
        "2.3": dt.date(2025, 6, 5),
        "3.0": dt.date(2026, 1, 21),
    },
}

PYTHON_SUPPORT_YEARS = 3
PACKAGE_SUPPORT_YEARS = 2


def _years_after(released: dt.date, years: int) -> dt.date:
    return released.replace(year=released.year + years)


def spec0_floor(releases: dict[str, dt.date], years: int, on: dt.date) -> str:
    """The oldest release still supported on ``on`` under SPEC 0's rule."""
    supported = [v for v, released in releases.items() if _years_after(released, years) > on]
    assert supported, f"no release of {list(releases)} is supported on {on}; extend the table"
    return min(supported, key=Version)


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_floor(specifier: str, name: str) -> Version:
    match = re.search(r">=\s*([0-9][0-9.]*)", specifier)
    assert match, f"{name} declares {specifier!r}, which names no floor"
    return Version(match.group(1))


def test_the_python_floor_is_no_older_than_spec0_allows_on_the_stated_date():
    """RED on the base tree: ``>=3.11`` against a SPEC 0 floor of 3.12."""
    expected = spec0_floor(PYTHON_RELEASES, PYTHON_SUPPORT_YEARS, WINDOW_COMPUTED_ON)
    declared = _declared_floor(_pyproject()["project"]["requires-python"], "requires-python")
    assert declared >= Version(expected), (
        f"requires-python names {declared} and SPEC 0 supports Python {expected} and later on "
        f"{WINDOW_COMPUTED_ON}; move the floor and the date in the same commit"
    )


def test_the_python_floor_is_stated_beside_its_schedule_and_date():
    """A reader of pyproject.toml learns WHY the floor is where it is."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    head = text[: text.index("requires-python")]
    assert "SPEC 0" in text and WINDOW_COMPUTED_ON.isoformat() in text, (
        "pyproject.toml names neither SPEC 0 nor the date the window was computed"
    )
    assert head.count("\n") < 40, "the floor moved away from the top of the project table"


@pytest.mark.parametrize("package", sorted(PACKAGE_RELEASES))
def test_a_core_package_floor_follows_spec0_and_is_not_above_the_tree(package):
    """SPEC 0 for numpy and pandas; the floor never exceeds what runs here."""
    expected = spec0_floor(PACKAGE_RELEASES[package], PACKAGE_SUPPORT_YEARS, WINDOW_COMPUTED_ON)
    declared = next(
        dep for dep in _pyproject()["project"]["dependencies"] if dep.split(">")[0] == package
    )
    floor = _declared_floor(declared, package)
    assert floor >= Version(expected), (
        f"{package} declares {declared!r}; SPEC 0 supports {expected} and later on "
        f"{WINDOW_COMPUTED_ON}"
    )
    assert floor <= Version(installed_version(package)), (
        f"{package} declares a floor of {floor} above the {installed_version(package)} this tree "
        "runs with; the floor is a measurement, not a hope"
    )


def test_the_continuous_integration_legs_start_at_the_declared_floor():
    """The matrix follows pyproject, not the other way round."""
    floor = _declared_floor(_pyproject()["project"]["requires-python"], "requires-python")
    for workflow in ("ci.yml", "release.yml"):
        text = (REPO / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        matrices = re.findall(r"python-version:\s*\[([^\]]+)\]", text)
        assert matrices, f"{workflow} declares no python-version matrix"
        for matrix in matrices:
            legs = [Version(leg.strip().strip('"')) for leg in matrix.split(",")]
            assert min(legs) == floor, (
                f"{workflow} runs Python {min(legs)} and the declared floor is {floor}"
            )


def test_the_linter_targets_the_declared_floor():
    """ruff's target-version and the floor say one thing (mypy is deliberately unpinned)."""
    data = _pyproject()
    floor = _declared_floor(data["project"]["requires-python"], "requires-python")
    target = data["tool"]["ruff"]["target-version"]
    assert target == f"py{floor.major}{floor.minor}", (
        f"ruff targets {target} and the floor is {floor}"
    )
    classifiers = [
        c.rsplit(" ", 1)[1]
        for c in data["project"]["classifiers"]
        if c.startswith("Programming Language :: Python :: 3.")
    ]
    assert classifiers and min(map(Version, classifiers)) == floor, (
        f"the classifiers list {classifiers} and the floor is {floor}"
    )
