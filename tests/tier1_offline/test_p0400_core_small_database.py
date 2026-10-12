"""P0400-REGISTERATOMIC (PFS-2102.018): register_edition replaces every chapter or none.

The final loop wrote chapter files one by one, so an OSError on the second
of two chapters (a file locked by an editor or a sync client, a full disk)
left the first rewritten, against the docstring's "nothing has been
written", and the OSError reached the command line as a traceback.
"""

from __future__ import annotations

import os

import pytest

import pyflightstream.utils.database as database
from pyflightstream.utils.errors import ManualDraftError
from tests.tier1_offline.test_utils_database import _run, tree  # noqa: F401


def _snapshot(chapters):
    return {path.name: path.read_bytes() for path in chapters.iterdir()}


def test_p0400_registeratomic_the_fixture_writes_two_chapters(tree):  # noqa: F811
    """P0400-REGISTERATOMIC: the control: an unhindered write edits both chapters."""
    result = _run(tree, write=True)
    assert len(result.chapters) == 2


def test_p0400_registeratomic_a_failed_write_replaces_nothing(tree, monkeypatch):  # noqa: F811
    """P0400-REGISTERATOMIC: the second write fails; no chapter changed, a ManualDraftError."""
    chapters = tree[0]
    before = _snapshot(chapters)
    real = database._textio.write_text
    calls = []

    def failing(path, text, **kwargs):
        calls.append(path)
        if len(calls) == 2:
            raise PermissionError(13, "locked by another program", str(path))
        return real(path, text, **kwargs)

    monkeypatch.setattr(database._textio, "write_text", failing)
    with pytest.raises(ManualDraftError, match="no chapter was replaced"):
        _run(tree, write=True)
    assert _snapshot(chapters) == before


def test_p0400_registeratomic_a_failed_replace_puts_back_the_first(tree, monkeypatch):  # noqa: F811
    """P0400-REGISTERATOMIC: the second replace fails; the first chapter is put back."""
    chapters = tree[0]
    before = _snapshot(chapters)
    real = os.replace
    calls = []

    def failing(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise PermissionError(13, "locked by another program", str(target))
        return real(source, target)

    monkeypatch.setattr(os, "replace", failing)
    with pytest.raises(ManualDraftError, match="were put back"):
        _run(tree, write=True)
    assert _snapshot(chapters) == before
