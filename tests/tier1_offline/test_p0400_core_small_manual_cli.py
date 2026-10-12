"""P0400-MANUALPATH (PFS-2102.017): a missing or bad --manual path is a usage error.

``pyfs-manual coverage`` and ``draft`` caught only ManualDraftError around the
pdf read, so the FileNotFoundError or IsADirectoryError the pdf reader raises
for a mistyped path escaped as a traceback. The pdf reader is replaced by one
that opens the path as pypdf does, so the test needs no pdf extra.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from pyflightstream.utils import cli


@pytest.fixture
def opening_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in pypdf whose reader opens its path, raising what the real one raises."""

    class PdfReader:
        def __init__(self, path: str) -> None:
            with open(path, "rb"):
                pass
            self.pages: list[object] = []

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=PdfReader))


@pytest.mark.usefixtures("opening_reader")
@pytest.mark.parametrize("command", ["coverage", "draft"])
@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_p0400_manualpath_bad_manual_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str, kind: str
) -> None:
    """P0400-MANUALPATH: exit 2 with the path named, for a missing file and a folder."""
    manual = tmp_path / "absent.pdf" if kind == "missing" else tmp_path
    argv = [command, "--manual", str(manual), "--source", "SRC-741", "--chapter-pages", "1-2"]
    if command == "draft":
        argv += ["--fs-version", "26.120"]
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)
    assert stopped.value.code == 2
    assert "is not a file" in capsys.readouterr().err
