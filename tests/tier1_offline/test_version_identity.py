"""Retained runtime, privacy and link checks, with shared test support."""

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
