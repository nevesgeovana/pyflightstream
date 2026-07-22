"""Tier 1: package front door (version, docstring) and the architecture overview."""

from importlib import metadata
from pathlib import Path

import pyflightstream
from pyflightstream.overview import (
    _SECTIONS,
    markdown_overview,
    render_overview_html,
)


def test_version_comes_from_the_installed_metadata():
    # B1 (PLN-021): the published package must never report the stale
    # hardcoded skeleton version again.
    assert pyflightstream.__version__ != "0.0.1.dev0"
    try:
        installed = metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        assert pyflightstream.__version__ == "0.0.0+uninstalled"
    else:
        assert pyflightstream.__version__ == installed


def test_package_docstring_is_the_didactic_front_door():
    # B2 (PLN-021): no milestone references; the docstring names the
    # pipeline layers and the two offline entry points.
    doc = pyflightstream.__doc__
    assert "ilestone" not in doc
    for layer in ("versions", "commands", "script", "results", "cases", "run", "files"):
        assert f"``{layer}``" in doc
    assert "help" in doc and "overview" in doc


def test_overview_is_exported_next_to_help():
    assert set(pyflightstream.__all__) == {"__version__", "help", "overview"}
    assert callable(pyflightstream.overview)


def test_render_overview_html_covers_every_subpackage():
    page = render_overview_html()
    assert page.startswith("<!DOCTYPE html>")
    assert "Layer diagram" in page
    for name in _SECTIONS:
        assert f"<code>pyflightstream.{name}</code>" in page
    # Content is the live docstrings, not prose of its own: spot-check
    # one distinctive phrase per end of the pipeline.
    assert "the lowest layer" in page  # versions
    assert "conservation ledgers" in page  # farfield


def test_overview_sections_match_the_deliverable_list():
    assert _SECTIONS == (
        "versions",
        "commands",
        "script",
        "results",
        "cases",
        "run",
        "files",
        "post",
        "qa",
        "fsi",
        "probes",
        "farfield",
        "reference",
    )


def test_overview_writes_the_page_without_opening_a_browser(tmp_path: Path):
    target = pyflightstream.overview(path=tmp_path / "overview.html", open_browser=False)
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "pyflightstream architecture overview" in text
    assert "downward" in text


def test_markdown_overview_carries_the_diagram_and_sections():
    page = markdown_overview()
    assert page.startswith("# Architecture overview")
    assert "```text" in page
    for name in _SECTIONS:
        assert f"## `pyflightstream.{name}`" in page
    # Sphinx roles are rewritten to plain markdown code spans.
    assert ":mod:" not in page
    assert ":func:" not in page
    assert "`pyflightstream.script.helpers`" in page
