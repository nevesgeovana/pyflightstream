"""Tier 1: the second round of the 0.40.0 command-gap probes (the probes lane).

The first licensed batch (2026-10-12) left 67 probe runs unprobed and 10 broken.
Reading their logs showed instruments that could not read what the solver did,
and one harness blind spot: 26.125 prints its script errors to its standard
output and writes no ``FlightStreamLog.txt``, so a name it refuses was recorded
broken instead of removed, with no line to show. These tests hold the repaired
judges and the harness reading both channels, without the solver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.qa import _spec_0400_gap as gap
from pyflightstream.qa import _spec_0400_gapkit as kit
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    ProbeArtifacts,
    ProbeOutcome,
    ProbeSpec,
    _judge,
    generate_probe_script,
)
from pyflightstream.run import ExecutionResult

BEGIN = "PYFS_PROBE_BEGIN_SET_OFF_BODY_STREAMLINE_LENGTH"
END = "PYFS_PROBE_END_SET_OFF_BODY_STREAMLINE_LENGTH"

#: What 26.125 (build #10052026) printed for a script line it does not carry,
#: measured on 2026-10-12: the lines on stdout, no log file in the working folder.
STDOUT_REFUSAL = (
    "Running script file: probe_script.txt\n\nPYFS_A\n"
    "ERROR | Syntax | 'SET_OFF_BODY_STREAMLINE_LENGTH' | Unrecognized command in script "
    "'probe_script.txt' at line 42 | Check command spelling and syntax.\n"
    "ERROR | Scripting | N/A | Error in script 'probe_script.txt' at line 42: "
    "'SET_OFF_BODY_STREAMLINE_LENGTH' | Review command syntax and arguments.\n"
)

STDOUT_ABORT = (
    "Running script file: probe_script.txt\n\n"
    "ERROR | Scripting | N/A | Error in script 'probe_script.txt' at line 45: "
    "'CREATE_NEW_6DOF_EXTERNAL_FORCE 1 0.25 0.0 0.0 0.1 0.1 0.0 0.0 500.0' | Review command "
    "syntax and arguments.\n"
)


def _aborted(tmp_path: Path, stdout: str, command: str) -> ProbeArtifacts:
    """Artifacts of a script that stopped at the target: log before, none after."""
    begin = f"PYFS_PROBE_BEGIN_{command}"
    return ProbeArtifacts(
        workdir=tmp_path,
        log_before=f"setup\n{begin}\n",
        log_after=None,
        begin_marker=begin,
        end_marker=f"PYFS_PROBE_END_{command}",
        execution=ExecutionResult(
            return_code=0,
            wall_time_s=1.0,
            timed_out=False,
            log_text=None,
            stdout=stdout,
            stderr="",
        ),
    )


def _spec(command: str) -> ProbeSpec:
    return ProbeSpec(command=command, build_target=lambda s, w: None, assert_effect=lambda a: True)


def test_p0400_probes_a_name_26125_refuses_on_stdout_is_removed(tmp_path):
    """P0400-PROBES-STDOUT: an unrecognised name printed on stdout alone records removed."""
    command = "SET_OFF_BODY_STREAMLINE_LENGTH"
    result = _judge(
        _spec(command), _aborted(tmp_path, STDOUT_REFUSAL, command), DEFAULT_ERROR_PATTERNS, "x", 60
    )
    assert result.outcome is ProbeOutcome.REMOVED, result.detail


def test_p0400_probes_an_abort_names_the_line_the_solver_printed(tmp_path):
    """P0400-PROBES-ABORTLINE: a broken abort carries the solver's own error line."""
    command = "CREATE_NEW_6DOF_EXTERNAL_FORCE"
    result = _judge(
        _spec(command), _aborted(tmp_path, STDOUT_ABORT, command), DEFAULT_ERROR_PATTERNS, "x", 60
    )
    assert result.outcome is ProbeOutcome.BROKEN
    assert "at line 45" in result.detail
    assert any("CREATE_NEW_6DOF_EXTERNAL_FORCE 1 0.25" in line for line in result.log_errors)


def _artifacts(tmp_path: Path) -> ProbeArtifacts:
    return ProbeArtifacts(
        workdir=tmp_path,
        log_before="",
        log_after="",
        begin_marker=BEGIN,
        end_marker=END,
        execution=ExecutionResult(
            return_code=0, wall_time_s=1.0, timed_out=False, log_text=None, stdout="", stderr=""
        ),
    )


def test_p0400_probes_a_control_holds_when_the_state_stays(tmp_path, monkeypatch):
    """P0400-PROBES-CONTROL: an unmoved saved state verifies the control; a moved one fails it."""
    states = {"state_before.fsm": (("Wing",), (288, (288,))), "state_after.fsm": None}
    monkeypatch.setattr(
        kit, "_names", lambda path: states[path.name][0] if states[path.name] else None
    )
    monkeypatch.setattr(
        kit, "_faces", lambda path: states[path.name][1] if states[path.name] else None
    )
    states["state_after.fsm"] = (("Wing",), (288, (288,)))
    assert kit._state_still(_artifacts(tmp_path)) is True
    states["state_after.fsm"] = (("Wing", "Surface 2"), (288, (200, 88)))
    assert kit._state_still(_artifacts(tmp_path)) is False


def test_p0400_probes_the_selection_judge_reads_the_surface_that_replaced_the_source(
    tmp_path, monkeypatch
):
    """P0400-PROBES-SELECT: 120 faces moved into a new surface verify; all 408 refute."""
    files = {
        "state_after.fsm": (("Wing", "Small"), (408, (288, 120))),
        "saved.fsm": (("Wing", "Surface 3"), (408, (288, 120))),
    }
    monkeypatch.setattr(kit, "_names", lambda path: files[path.name][0])
    monkeypatch.setattr(kit, "_faces", lambda path: files[path.name][1])
    judge = kit._selection_took(2)
    assert judge(_artifacts(tmp_path)) is True
    files["saved.fsm"] = (("Surface 3",), (408, (408,)))
    assert judge(_artifacts(tmp_path)) is False
    assert kit._selection_took_all(_artifacts(tmp_path)) is True


def test_p0400_probes_one_surface_spanning_both_sheets_holds_the_control(tmp_path):
    """P0400-PROBES-SPAN: a surface from z 0 to 2 holds both sheets; z 0 alone does not."""
    obj = tmp_path / "surface_1.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 2\nf 1 2 3\n", encoding="utf-8")
    judge = kit._obj_spans("surface_1.obj", 2, 0.0, 2.0)
    assert judge(_artifacts(tmp_path)) is True
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    assert judge(_artifacts(tmp_path)) is None


def test_p0400_probes_zero_surface_lines_after_a_delete_cannot_verify_it(tmp_path):
    """P0400-PROBES-SURFLINES: no line left reads unprobed; lines left break; the table verifies."""
    path = tmp_path / "surface_lines.txt"
    path.write_text(
        "     FlightStream Surface Streamlines\n     Number of Surface Streamlines:   0\n"
        "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp\n",
        encoding="utf-8",
    )
    assert kit._surface_lines_deleted("surface_lines.txt")(_artifacts(tmp_path)) is None
    assert kit._streamline_table("surface_lines.txt")(_artifacts(tmp_path)) is True
    path.write_text("     Number of Surface Streamlines:   3\n", encoding="utf-8")
    assert kit._surface_lines_deleted("surface_lines.txt")(_artifacts(tmp_path)) is False


def _trajectory(path: Path, rows: list[list[float]]) -> None:
    header = "6DOF motion trajectory data\nx, y, z, u, v, w, p, q, r, phi, theta, psi\n"
    body = "".join(", ".join(f"{v:.6f}" for v in row) + "\n" for row in rows)
    path.write_text(header + body, encoding="utf-8")


def test_p0400_probes_pitch_only_reads_theta_moving_and_z_still(tmp_path):
    """P0400-PROBES-PITCH: theta moving with z still verifies; z falling refutes."""
    first = [0.0] * 18
    still = list(first)
    still[10] = 0.07
    falling = list(still)
    falling[2] = -0.6
    path = tmp_path / kit._TRAJECTORY
    judge = kit._pitch_only(kit._TRAJECTORY)
    _trajectory(path, [first, still])
    assert judge(_artifacts(tmp_path)) is True
    _trajectory(path, [first, falling])
    assert judge(_artifacts(tmp_path)) is False


@pytest.mark.parametrize("build", ("26.124", "26.125"))
def test_p0400_probes_each_p4_setter_has_a_saved_state_twin(build, tmp_path):
    """P0400-PROBES-P4TWINS: the registered P4 probe is validated; its ``m`` run reads the march.

    The trajectory export written before the march held its header and no row
    on both builds (P4-04), so the trajectory is read after the march, a
    placement the phase order refuses and that is appended raw. A registered
    probe builds a validated script, so it reads the saved simulation instead,
    and the raw export stays in its ``m`` twin, after the END sentinel.
    """
    probes = {p.probe_id: p for p in gap.gap_probes()}
    for probe_id in gap._SAVED_STATE_TWINS:
        registered, run = probes[probe_id], probes[f"{probe_id}m"]
        assert registered.primary and not run.primary
        assert registered.spec.command == run.spec.command
        assert registered.spec.save_state and registered.spec.epilogue is None
        workdir = tmp_path / build / probe_id
        workdir.mkdir(parents=True)
        assert not generate_probe_script(registered.spec, build, workdir).raw_flag
        (workdir / "m").mkdir()
        script = generate_probe_script(run.spec, build, workdir / "m")
        tail = script.render().split(f"PYFS_PROBE_END_{run.spec.command}", 1)[1]
        assert script.raw_flag and "EXPORT_6DOF_TRAJECTORY" in tail, probe_id


@pytest.mark.parametrize("build", ("26.124", "26.125"))
def test_p0400_probes_the_declined_surface_probe_and_its_control_build(build, tmp_path):
    """P0400-PROBES-DECLINED: PFS-2085.021, the sphere on the list and off it, on both builds."""
    pair = {p.probe_id: p for p in gap.declined_surface_probes()}
    assert set(pair) == {"D-01", "D-01c"}
    lines = {}
    for probe_id, probe in pair.items():
        assert not probe.primary and probe.node == "PFS-2085.021"
        workdir = tmp_path / probe_id
        workdir.mkdir()
        text = generate_probe_script(probe.spec, build, workdir).render()
        target = text.split(f"PYFS_PROBE_BEGIN_{probe.spec.command}", 1)[1]
        lines[probe_id] = target.split("PYFS_PROBE_END_", 1)[0]
        assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET" in text.split("PYFS_PROBE_END_", 1)[1]
    assert lines["D-01"] != lines["D-01c"]


def test_p0400_probes_the_sphere_is_closed():
    """P0400-PROBES-SPHERE: every edge of the probe sphere is shared by two faces, none open."""
    edges: dict[tuple, int] = {}
    for triangle in kit.sphere_triangles():
        corners = [tuple(round(float(c), 9) for c in corner) for corner in triangle]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            key = tuple(sorted((corners[a], corners[b])))
            edges[key] = edges.get(key, 0) + 1
    assert edges and set(edges.values()) == {2}
