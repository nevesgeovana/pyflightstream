"""P0400-RESTATELABEL (PFS-2135.055): restate_26123_notes refuses the two manifest-label defects.

A manifest without 26.123 raised a bare ValueError from ``labels.index``, and
26.123 as the FIRST row made ``editions[position - 1]`` the last row, so the
newest edition was compared against the oldest. Both are refused before a
manual is read, as prove_edition_comparison already refuses them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "restate_26123_notes_p0400", REPO / "scripts" / "restate_26123_notes.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("labels", "words"),
    [(["26.120", "26.122"], "no row labelled '26.123'"), (["26.123", "26.124"], "first row")],
    ids=["absent", "first"],
)
def test_p0400_restatelabel_bad_manifest_is_refused_before_reading(
    monkeypatch, labels, words
) -> None:
    """P0400-RESTATELABEL: an absent or first-row 26.123 stops with a SystemExit naming it."""
    module = _load()
    editions = [SimpleNamespace(label=label) for label in labels]
    monkeypatch.setattr(module, "read_edition_manifest", lambda path: editions)

    def never(edition):
        raise AssertionError("a manual was read before the manifest was judged")

    monkeypatch.setattr(module, "read_edition", never)
    with pytest.raises(SystemExit, match=words):
        module.main(["--editions", "manifest.yaml"])
