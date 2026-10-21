"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_floor(specifier: str, name: str) -> Version:
    match = re.search(r">=\s*([0-9][0-9.]*)", specifier)
    assert match, f"{name} declares {specifier!r}, which names no floor"
    return Version(match.group(1))


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


def test_the_installed_version_of_each_declared_dependency_is_inside_its_range():
    """F-797, X-F-0001: the declared envelope of every dependency is measured on this tree.

    A floor above the installed version, or a ceiling at or below it, is a declaration the
    tree itself contradicts. (No CI leg installs the floors, so this is evidence about the
    tree's own versions only.)
    """
    from importlib import metadata

    from packaging.requirements import Requirement

    for text in _pyproject()["project"]["dependencies"]:
        requirement = Requirement(text)
        installed = Version(metadata.version(requirement.name))
        assert requirement.specifier.contains(installed, prereleases=True), (
            f"{requirement.name} {installed} is outside the declared {requirement.specifier}"
        )
