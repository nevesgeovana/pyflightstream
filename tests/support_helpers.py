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
