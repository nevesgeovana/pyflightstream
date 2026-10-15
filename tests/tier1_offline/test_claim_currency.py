"""Retained runtime, privacy and link checks, with shared test support."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


README = REPO / "README.md"


def test_the_removed_files_shim_refuses_import() -> None:
    """The retired import remains unavailable."""
    with pytest.raises(ImportError):
        __import__("pyflightstream.files")


def _readme_named_examples() -> set[str]:
    """Example file names the README points a reader at."""
    return set(
        re.findall(
            r"(?:docs/)?examples/(?:_sources/)?[\w.]+\.py",
            README.read_text(encoding="utf-8"),
        )
    )


def test_every_example_the_readme_names_exists() -> None:
    """REV010-017. The README promised `examples/` reached "coupled
    aeroelastic runs" and no such example exists: the two FSI-adjacent
    ones are a static deflection and a modal Campbell diagram."""
    named = _readme_named_examples()
    assert named, "the README names no example files; this guard would pass vacuously"
    missing = sorted(name for name in named if not (REPO / name).is_file())
    assert not missing, (
        f"the README points at examples that do not exist: {missing}. Either add "
        "the example or stop claiming it."
    )
