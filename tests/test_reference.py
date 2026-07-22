"""Tier 1: reference rendering, HTML fallback and markdown docs pages."""

from pathlib import Path

import pyflightstream
from pyflightstream.commands import CommandRegistry
from pyflightstream.reference import (
    markdown_compatibility_matrix,
    markdown_reference_pages,
    percent_script_markdown,
    render_html,
)


def test_render_html_covers_the_whole_database():
    page = render_html()
    assert page.startswith("<!DOCTYPE html>")
    for name in ("INITIALIZE_SOLVER", "CREATE_NEW_ACTUATOR", "SONIC_VELOCITY"):
        assert f"<code>{name}</code>" in page
    assert "manual_ref" in page


def test_render_html_version_scope_keeps_removed_visible():
    page = render_html("26.12")
    assert "Scope: FlightStream 26.120" in page
    assert "<code>SONIC_VELOCITY</code>" in page
    assert "26.120: removed" in page


def test_render_html_formats_typed_arguments():
    page = render_html()
    assert "variables: enum_list in {" in page
    assert "(optional)" in page
    assert "[deg]" in page


def test_help_writes_the_page_without_opening_a_browser(tmp_path: Path):
    target = pyflightstream.help(path=tmp_path / "reference.html", open_browser=False)
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert "pyflightstream command reference" in text
    assert "113 commands" in text or "commands." in text


def test_markdown_pages_cover_every_chapter_and_command():
    registry = CommandRegistry.load()
    pages = markdown_reference_pages()
    chapters = {entry.chapter for entry in registry.commands.values()}
    assert set(pages) == {f"{chapter}.md" for chapter in chapters} | {"index.md", "SUMMARY.md"}
    joined = "\n".join(pages.values())
    for name in registry.commands:
        assert f"## {name}" in joined


def test_markdown_pages_carry_the_navigation_and_evidence():
    pages = markdown_reference_pages()
    assert pages["SUMMARY.md"].startswith("* [Overview](index.md)")
    assert "compatibility.md" in pages["index.md"]
    solver = pages["solver_settings.md"]
    assert '<span class="status-verified">verified</span>' in solver
    assert "reports/compat/" in solver
    assert "SRC-725 p.340" in solver


def test_compatibility_matrix_is_honest_about_missing_evidence():
    page = markdown_compatibility_matrix()
    registry = CommandRegistry.load()
    # Every registered version is a column; 26.000 has no evidence yet,
    # so its summary row reports the whole database as unrecorded.
    assert f"| 26.000 | 26.0 | 0 | 0 | 0 | 0 | {len(registry.commands)} | none registered |" in page
    assert "SRC-725" in page and "SRC-003" in page
    # Commands link back to their reference entry anchors.
    assert "[SET_SOLVER_STEADY](reference/solver_settings.md#set_solver_steady)" in page


def test_html_reference_carries_the_manual_coverage_section():
    page = render_html()
    assert "Manual coverage" in page
    # Chapter rows carry the page citations from the YAML headers.
    assert "SRC-003 pp.341-343" in page
    # A citation wrapped across header comment lines still reassembles.
    assert "SRC-003 pp.344-346" in page
    # The honesty notes: uncited pages are named, never guessed at.
    assert "not yet cited" in page
    assert "not absent from the manual" in page


def test_markdown_index_carries_the_manual_coverage_section():
    pages = markdown_reference_pages()
    index = pages["index.md"]
    assert "| Chapter | Manual pages | Commands drafted |" in index
    assert "SRC-003 pp.341-343" in index
    assert "## Manual coverage" in index
    assert "not yet cited" in index
    # The 26.100 edition registers no closed page range; the report says
    # so explicitly instead of computing a bogus gap list.
    assert "no gap listing can be computed" in index


def test_coverage_gap_analysis_is_derived_not_guessed():
    from pyflightstream.reference import (
        _coverage_notes,
        _coverage_rows,
        _database_cited_pages,
        _page_spans,
    )

    # Every chapter of the database appears exactly once with its count.
    registry = CommandRegistry.load()
    rows = _coverage_rows()
    assert {row[0] for row in rows} == {entry.chapter for entry in registry.commands.values()}
    assert sum(row[3] for row in rows) == len(registry.commands)

    # The cited-page scan sees both registered manual sources.
    cited = _database_cited_pages()
    assert "SRC-003" in cited and "SRC-725" in cited

    # Span collapsing is exact.
    assert _page_spans({300, 301, 302, 310}) == "300-302, 310"

    # Notes never claim knowledge the database lacks: the closing note
    # states out-of-scope areas are not tracked.
    notes = _coverage_notes()
    assert any("out of scope" in note for note in notes)


def test_percent_script_markdown_renders_the_committed_example():
    source = Path("examples/steady_polar.py").read_text(encoding="utf-8")
    page = percent_script_markdown(source)
    assert page.startswith("# Steady polar")
    assert "```python" in page
    # The module docstring is dropped, the imports survive.
    assert "Steady polar example: synthetic wing" not in page
    assert "from pyflightstream.script import Script" in page


def test_percent_script_markdown_splits_cells():
    source = (
        '# %% [markdown]\n# # Title\n# Prose line.\n# %%\n"""Docstring\nspanning lines."""\nx = 1\n'
    )
    page = percent_script_markdown(source)
    assert "# Title\nProse line." in page
    assert "```python\nx = 1\n```" in page
    assert "Docstring" not in page
