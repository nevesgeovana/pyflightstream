"""Retained runtime, privacy and link checks, with shared test support."""

import re
import tomllib
from pathlib import Path

from packaging.version import parse as parse_version

REPO = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    with (REPO / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_the_version_is_a_valid_pep440_string():
    """A version nothing can parse is its own identity problem."""
    parse_version(_pyproject_version())


def test_p0440_guide_version_matches_the_package():
    """The guide identifies the same release as its source package."""
    text = (REPO / "guide/latex-sources/shared/info.tex").read_text(encoding="utf-8")
    versions = re.findall(r"\\newcommand\{\\pkgversion\}\{([^}]+)\}", text)
    assert versions == [_pyproject_version()]


def test_p0440_unsteady_super_content_change_is_named():
    notes = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split("## [0.43.0]", 1)[0]
    assert "SET_SOLVER_UNSTEADY" in notes
    assert "time_iterations" in notes and "delta_time" in notes and "NA" in notes


def test_p0440_refinement_identity_migration_is_named():
    notes = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split("## [0.43.0]", 1)[0]
    assert "canonical_selection" in notes
    assert all(term in notes for term in ("body axis and origin", "level folder", "migration:"))


def test_p0440_cheatsheet_names_the_solved_probe_timeout_exception():
    text = (REPO / "guide/latex-sources/04-cheatsheet/text/01-matrix-and-tools.tex").read_text(
        encoding="utf-8"
    )
    line = next(line for line in text.splitlines() if r"\fl{--timeout S}" in line)
    assert "solved probes keep their own limits" in line
    assert all(value in line for value in ("180", "240", "60"))
