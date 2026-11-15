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


def _setup_refusal(tmp_path: Path, text: str) -> str:
    """Read ``text`` as setup s001 the way a row's SET cell does; return the refusal."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace.inputs import resolve_setup

    (tmp_path / "setups").mkdir(exist_ok=True)
    (tmp_path / "setups" / "s001.toml").write_text(text, encoding="utf-8")
    with pytest.raises(InputArtifactError) as refused:
        resolve_setup(tmp_path, "s001")
    return str(refused.value)


def _binding_refusal(settings: dict) -> str:
    """Bind ``settings`` as a preset a matrix row names; return the refusal."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace._matrix_binding import _solver_from_setup
    from pyflightstream.workspace.inputs import SetupArtifact

    with pytest.raises(InputArtifactError) as refused:
        _solver_from_setup(SetupArtifact(settings=settings), "s001")
    return str(refused.value)


def _python_refusal(**settings) -> str:
    from pyflightstream.cases import SolverSettings

    with pytest.raises(ValueError) as refused:
        SolverSettings(**settings)
    return str(refused.value)


@pytest.mark.parametrize("key", ["physics_auto_trailing_edges", "physics_auto_wake_nodes"])
def test_p0580_pfs2250_physics_switches_are_refused_naming_the_detection(tmp_path, key):
    """PFS-2250: each PHYSICS switch is refused by name, naming the boundaries-file detection."""
    for said in (
        _setup_refusal(tmp_path, f"{key} = true\n"),
        _binding_refusal({key: True}),
        _python_refusal(**{key: False}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert '[trailing_edges] detect = "auto"' in said, said
        assert '[wake_termination] detect = "auto"' in said, said


def test_p0580_pfs2251_sonic_velocity_is_refused_naming_the_air_state(tmp_path):
    """PFS-2251: the speed of sound follows from the air state; the key is refused at read."""
    key = "sonic_velocity_m_per_s"
    for said in (
        _setup_refusal(tmp_path, f"{key} = 340.0\n"),
        _binding_refusal({key: 340.0}),
        _python_refusal(**{key: 340.0}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert "air state" in said and "flight-condition columns" in said, said


def test_p0580_pfs2255_setup_symmetry_loads_is_refused_naming_the_column(tmp_path):
    """PFS-2255: the half or full loads are the SYMMETRY_LOADS column only."""
    key = "symmetry_loads"
    for said in (
        _setup_refusal(tmp_path, f"{key} = true\n"),
        _binding_refusal({key: False}),
        _python_refusal(**{key: True}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert "SYMMETRY_LOADS column" in said, said


@pytest.mark.parametrize("build", ["26.122", "26.127"])
def test_p0580_pfs2249_bluntness_angle_is_refused_on_a_build_with_no_row(tmp_path, build):
    """PFS-2249: 26.122 removed the command and 26.127 has no row, so the build refuses it."""
    from pyflightstream.cases._geometry_emit import render_geometry_script

    instruction = _detect_instruction({"bluntness_angle_deg": 120.0})
    with pytest.raises(CommandNotInVersionError, match="SET_TRAILING_EDGE_BLUNTNESS_ANGLE"):
        render_geometry_script(
            instruction, folder=tmp_path, work=tmp_path / "partial", version=build
        )
