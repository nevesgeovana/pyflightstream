"""P0400-CHMEMPTY (PFS-2135.044): chm_to_pdf.py fails when the package reader finds no command.

The tool printed "the package reader finds NO command; the page numbers are
not citable" and exited 0. The archive reading, the Chrome render and the pdf
reader are replaced, so the test reaches that branch without Chrome or pypdf.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

import pyflightstream.utils.manual as manual

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "chm_to_pdf_p0400", REPO / "scripts" / "chm_to_pdf.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("found", "code"), [({}, 1), ({"X": types.SimpleNamespace(page=3)}, 0)])
def test_p0400_chmempty_no_command_found_is_a_failure(tmp_path, monkeypatch, found, code) -> None:
    """P0400-CHMEMPTY: no command found exits 1; the control, one found, exits 0."""
    module = _load()
    out = tmp_path / "out.pdf"
    monkeypatch.setattr(sys, "argv", ["chm_to_pdf.py", str(tmp_path), str(out), "chrome.exe"])
    reader = types.SimpleNamespace(PdfReader=lambda path: types.SimpleNamespace(pages=[1]))
    monkeypatch.setattr(module, "_pypdf", lambda: reader)
    monkeypatch.setattr(module, "combine", lambda root: (root / "c.html", 0, 0))
    monkeypatch.setattr(module, "render", lambda combined, target, chrome: target.write_bytes(b"x"))
    monkeypatch.setattr(manual, "read_pdf_pages", lambda path, *, first, last: {})
    monkeypatch.setattr(manual, "parse_signatures", lambda pages: found)
    assert module.main() == code
