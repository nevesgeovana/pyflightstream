"""Tier 1: reference.help opens a page at a relative path (P0400-HELP-RELPATH).

Pipeline role: quality gate on :func:`pyflightstream.reference.help`. The
page was written and then ``Path.as_uri`` raised on the relative path before
the browser was asked to open it. The browser is replaced by a recorder, so
nothing opens. Planning node PFS-2095.036.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream import reference


def test_p0400_help_relpath_opens_the_resolved_page(tmp_path, monkeypatch):
    """P0400-HELP-RELPATH: a relative path is written and opened as an absolute file URI."""
    opened: list[str] = []
    monkeypatch.setattr(reference.webbrowser, "open", opened.append)
    monkeypatch.chdir(tmp_path)

    page = reference.help("26.124", path="commands.html")

    assert page == Path("commands.html")
    assert (tmp_path / "commands.html").is_file()
    assert opened == [(tmp_path / "commands.html").resolve().as_uri()]
