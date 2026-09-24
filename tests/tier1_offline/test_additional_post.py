"""Tier 1: the additional post over a point's saved simulation (0.27.0, G12).

A row may name a second pproc, ``ADDITIONAL_PPROC: p<id>``, and
``pyfs-matrix post --additional-pproc`` then reopens each recorded point's
final ``.fsm``, runs that pproc's extractions over it with no solve, and posts
what comes back as products marked with the pproc. What a reopened simulation
gives back was measured on 26.124 (RPT-062), and every guarantee here is held
by a test on its link:

* the builders keep the frames they created, by name, so a new distribution
  cites the frame the saved simulation holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import (
    _rotor_row,
    _saved_simulation,
    _wb_geometry,
    _with_pproc,
    steady_case,
    unsteady_case,
)

#: The one build RPT-062 measured what a reopened simulation gives back on.
BUILD = "26.124"


def a_point_of(kind: str, tmp_path: Path) -> SimCase:
    """One point of each run type, with a reference whose moment point places the MRP.

    ``steady`` and ``unsteady`` open the wing-body the workflow tests use;
    ``unsteady_rotor`` opens a pusher whose blade family is ``Blade1``, so the
    run creates a blade frame beside the MRP and the rotor's hub frame.
    """
    if kind == "unsteady_rotor":
        geometry = _saved_simulation(tmp_path / "40_PUSHER.fsm", ["Body", "Base", "Blade1"])
        return _with_pproc(_rotor_row(geometry, "Blade1"), geometry)
    make = steady_case if kind == "steady" else unsteady_case
    return _with_pproc(make(), _wb_geometry(tmp_path))


RUN_TYPES = ("steady", "unsteady", "unsteady_rotor")


def created_frames(text: str) -> dict[int, str]:
    """Every frame a rendered script names, index to name, read off its text.

    Written here rather than taken from the package, so the frame map the
    builders keep is compared with the script by a second reading of it.
    """
    lines = [line.strip() for line in text.splitlines()]
    return {
        int(lines[at + 1].split()[1]): lines[at + 2].split(" ", 1)[1]
        for at, line in enumerate(lines)
        if line == "EDIT_COORDINATE_SYSTEM"
    }


# ---------------------------------------------------------------- the seam --


@pytest.mark.parametrize("kind", RUN_TYPES)
def test_g12_frames_by_name_is_the_builders_own(kind, tmp_path):
    """Every run type keeps its frames by name, and each is a frame its script created."""
    script = Script(BUILD)
    build_script(a_point_of(kind, tmp_path), script)
    frames = script.frames_by_name
    assert frames is not None, f"{kind} kept no frames"
    created = created_frames(script.render())
    cited = [
        index
        for value in frames.values()
        for index in (value.values() if isinstance(value, dict) else [value])
        if index is not None
    ]
    assert cited, f"{kind} names no frame, so nothing was compared: {frames}"
    assert set(cited) <= set(created), (
        f"{kind}: frames {sorted(set(cited) - set(created))} are named and never created "
        f"({created})"
    )
    assert created[frames["MRP"]] == "MRP", (kind, frames, created)
