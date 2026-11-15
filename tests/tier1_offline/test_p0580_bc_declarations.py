"""P0580-BC (PFS-2176 review, PFS-2249 to PFS-2257): each boundary condition has one home.

The owner's review of 2026-11-15 gave every FlightStream boundary condition one declaration.
A condition that moved is refused by name at its old home, the refusal naming the new one;
a condition with no route gained one. Each test runs the reader or the builder a user meets
and asserts what the node's acceptance sentence states.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError


def _detect_instruction(detect: dict):
    from pyflightstream.cases._geometry_instruction import GeometryInstruction, MeshSource
    from pyflightstream.cases.mesh import TrailingEdgeMarking

    return GeometryInstruction(
        name="wing",
        outputs=("fsm",),
        boundaries=("Wing",),
        kind="mesh",
        mesh=MeshSource(file="wing.obj", units="METER"),
        trailing_edges=TrailingEdgeMarking(route="detect", **detect),
    )


def test_p0580_pfs2249_bluntness_angle_is_read_beside_the_sweep_angle(tmp_path: Path):
    """PFS-2249: ``detect = { ..., bluntness_angle = ... }`` reaches the marking in degrees."""
    from pyflightstream.workspace.sidecars import read_trailing_edges

    marking = read_trailing_edges(
        tmp_path / "wing.obj.boundaries.toml",
        {"detect": {"surfaces": ["Wing"], "sweep_angle": 30, "bluntness_angle": 120}},
    )
    assert (marking.sweep_angle_deg, marking.bluntness_angle_deg) == (30.0, 120.0)


def test_p0580_pfs2249_bluntness_angle_emits_its_command_where_the_build_has_a_row(tmp_path):
    """PFS-2249: the angle is set before the detection on a build whose row allows it."""
    from pyflightstream.cases._geometry_emit import render_geometry_script

    instruction = _detect_instruction({"detect_surfaces": ("Wing",), "bluntness_angle_deg": 120.0})
    text = render_geometry_script(
        instruction, folder=tmp_path, work=tmp_path / "partial", version="26.121"
    ).text
    lines = text.splitlines()
    blunt = next(i for i, line in enumerate(lines) if "SET_TRAILING_EDGE_BLUNTNESS_ANGLE" in line)
    detect = next(i for i, line in enumerate(lines) if "DETECT_TRAILING_EDGES_BY_SURFACE" in line)
    assert blunt < detect
    assert lines[blunt].split()[-1].startswith("120")


@pytest.mark.parametrize("build", ["26.122", "26.127"])
def test_p0580_pfs2249_bluntness_angle_is_refused_on_a_build_with_no_row(tmp_path, build):
    """PFS-2249: 26.122 removed the command and 26.127 has no row, so the build refuses it."""
    from pyflightstream.cases._geometry_emit import render_geometry_script

    instruction = _detect_instruction({"bluntness_angle_deg": 120.0})
    with pytest.raises(CommandNotInVersionError, match="SET_TRAILING_EDGE_BLUNTNESS_ANGLE"):
        render_geometry_script(
            instruction, folder=tmp_path, work=tmp_path / "partial", version=build
        )
