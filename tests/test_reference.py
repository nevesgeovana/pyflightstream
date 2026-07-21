"""Tier 1: HTML reference rendering."""

from pathlib import Path

import pyflightstream
from pyflightstream.reference import render_html


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
