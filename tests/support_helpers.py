"""Shared offline fixture builders and record readers, with one definition each."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from pyflightstream._fsm import MESH_MARKER
from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


def no_sleep(_seconds: float) -> None:
    """The clock, injected. A suite that waited two seconds per point is a suite nobody runs."""


def script_lines(case: SimCase, build: str = "26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_mesh_fixture(path: Path, names: Sequence[str]) -> Path:
    """Write the smallest saved simulation carrying a mesh block.

    Built from the format's own shape rather than copied from a campaign
    geometry, for two reasons: those files are 1 to 9 MB, and some of
    them are derivatives that may not be distributed. What is reproduced
    here is exactly what the reader reads, including the two junk lines
    between the marker and the count and the head numbers STARTING AT 2,
    which is what seven of the eight real geometries do and what makes a
    reader that mistook the head number for the index wrong here.
    """
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    # `newline=""` because the CRLF here is DATA, not formatting. Without
    # it the platform translates each "\n" again and the file gains a
    # blank line between every record, which the reader then reports as a
    # count line that is not a number. The real geometries are CRLF, so
    # this writes the bytes they carry rather than the bytes this
    # platform would have chosen.
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


#: The cell a grouped-plan fixture row carries for CORES and WALLTIME before a test rewrites it.
_ROW_FORM = "| 8     | 1h       |"


def grouped_plan_fixture(
    tmp_path: Path, walltimes: Sequence[str] = ("BEST", "BEST", "BEST"), sweep: str = "0.0,2.0,4.0"
):
    """Return a workspace and a matrix of one unsteady rotor polar per walltime cell (NFR-42).

    The one definition of the grouped-plan workspace the plan, split, collect and parity tests
    share. The workspace library and the rotor row are built by the shared builders of the
    input-path tests, imported here at call time because they sit in test modules whose
    module-level code the support module must not run on import.
    """
    from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace

    workspace = _workspace(tmp_path)
    matrix = _rotor_row(tmp_path, sweep=sweep)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    assert _ROW_FORM in row
    rows = [
        row.replace("7001", str(7001 + index)).replace(_ROW_FORM, f"| 8     | {cell:<8} |")
        for index, cell in enumerate(walltimes)
    ]
    matrix.write_text("\n".join([header, rule, *rows]) + "\n", encoding="utf-8")
    return workspace, matrix
