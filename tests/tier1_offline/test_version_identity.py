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
