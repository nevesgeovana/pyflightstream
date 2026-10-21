"""Regression coverage grouped by subject."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.qa import _spec_0400_gap as gap
from pyflightstream.qa import _spec_0400_gapkit as kit
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    ProbeArtifacts,
    ProbeOutcome,
    ProbeSpec,
    _judge,
    generate_probe_script,
    unrecognised_commands,
)
from pyflightstream.run import ExecutionResult
from pyflightstream.script import BrokenCommandError, Script

_PROBES_DATABASE__FSI_PAIR = ("SET_MOTION_FSI_EXECUTABLE", "SET_MOTION_FSI_STRUCTURAL_NODES")


_PROBES_DATABASE__FSI_ARGS = {
    "SET_MOTION_FSI_EXECUTABLE": (1, "DISABLE", "ENABLE", "solver.exe"),
    "SET_MOTION_FSI_STRUCTURAL_NODES": (1, "nodes.txt"),
}


class TestProbesDatabase:
    """Tier 1: the command database rows the licensed runs of 2026-10-12 moved (RPT-166).

    PFS-2135.060, .061 and .066 each named rows the evidence contradicted: names the
    solver refuses still documented, so the emitter wrote them; a start time
    recorded broken from a probe artifact; a bulk separation model inherited by two
    builds whose editions no longer print it. These tests hold the rows as the runs
    and the editions left them, through the emitter a user meets.
    """

    @staticmethod
    @pytest.mark.parametrize("build", ("26.100", "26.101", "26.120", "26.124", "26.125"))
    @pytest.mark.parametrize("command", _PROBES_DATABASE__FSI_PAIR)
    def test_p0400_probes_the_fsi_motion_pair_is_refused_where_measured(build, command):
        """P0400-PROBES-FSIPAIR: PFS-2135.061, the pair the solver refuses is never written."""
        script = Script(build)
        script.emit("CREATE_NEW_MOTION", "6DOF")
        with pytest.raises(CommandNotInVersionError, match="MEASURED REMOVED 2026-10-12"):
            script.emit(command, *_PROBES_DATABASE__FSI_ARGS[command])
        row = CommandRegistry.load().commands[command].versions[build]
        assert row.report and "2026-10-12" in row.report
        assert "Candidate broken" not in (CommandRegistry.load().commands[command].notes or "")

    @staticmethod
    def test_p0400_probes_the_valarezo_erase_of_the_manual_is_refused():
        """P0400-PROBES-VALAREZO: PFS-2135.061, the 26.100 name the solver does not answer to."""
        with pytest.raises(CommandNotInVersionError, match="removed"):
            Script("26.100").emit("DELETE_VALAREZO_CRITERION_BOUNDARIES")

    @staticmethod
    @pytest.mark.parametrize("build", ("26.120", "26.124", "26.125"))
    def test_p0400_probes_the_start_time_emits_with_dated_probe_provenance(build):
        """P0400-PROBES-STARTTIME: emission and provenance, without asserting licensed validity."""
        script = Script(build)
        script.emit("CREATE_NEW_MOTION", "6DOF")
        script.emit("SET_MOTION_START_TIME", 1, 0.05)
        assert "SET_MOTION_START_TIME 1 0.05" in script.render()
        row = CommandRegistry.load().commands["SET_MOTION_START_TIME"].versions[build]
        assert "2026-10-12" in (row.report or "")

    @staticmethod
    def test_p0400_probes_the_start_time_of_26122_is_its_own_row():
        """P0400-PROBES-STARTTIME-26122: 26.122 answers from its edition, not from 26.120."""
        row = CommandRegistry.load().commands["SET_MOTION_START_TIME"].versions["26.122"]
        assert row.status == "documented" and "FSM-26.122" in (row.note or "")

    @staticmethod
    def test_p0400_probes_a_report_applies_again_after_its_removal_was_edited(tmp_path):
        """P0400-PROBES-REAPPLY: a removal edited deliberately from a report corroborates on re-apply.

        apply-compat refuses a removal over a row citing an edition page and asks for
        the row to be edited deliberately; once it was, from that same report, the
        refusal stopped the report's every other command from being promoted.
        """  # noqa: E501
        import shutil
        from pathlib import Path

        from pyflightstream.qa.compat import CORROBORATED, apply_compat

        root = Path(__file__).resolve().parents[2]
        commands = tmp_path / "src" / "pyflightstream" / "commands"
        shutil.copytree(root / "src" / "pyflightstream" / "commands", commands)
        name = "CMP-26124_2026-10-12_gap-probes.yaml"
        (tmp_path / "reports" / "compat").mkdir(parents=True)
        shutil.copy(root / "reports" / "compat" / name, tmp_path / "reports" / "compat" / name)
        report = tmp_path / "reports" / "compat" / name
        promotions = apply_compat(report, repo_root=tmp_path, commands_dir=commands)
        outcomes = {name: status for name, status, _ in promotions}
        assert outcomes["SET_MOTION_FSI_EXECUTABLE"] == CORROBORATED
        assert outcomes["SET_OFF_BODY_STREAMLINE_LENGTH"] == CORROBORATED

    @staticmethod
    def test_p0400_probes_the_bulk_separation_model():
        """P0400-PROBES-BULK: PFS-2135.060, broken where run, removed where the edition drops it."""
        with pytest.raises(BrokenCommandError, match="CREATE_CYLINDRICAL_BULK_SEPARATION"):
            Script("26.120").emit("CREATE_BULK_SEPARATION", "B", "CYLINDRICAL", -1, 0.5)
        for build in ("26.121", "26.122"):
            with pytest.raises(
                CommandNotInVersionError, match="CREATE_CYLINDRICAL_BULK_SEPARATION"
            ):
                Script(build).emit("CREATE_BULK_SEPARATION", "B", "CYLINDRICAL", -1, 0.5)


_PROBES_JUDGES__BEGIN = "PYFS_PROBE_BEGIN_SET_OFF_BODY_STREAMLINE_LENGTH"


_PROBES_JUDGES__END = "PYFS_PROBE_END_SET_OFF_BODY_STREAMLINE_LENGTH"


#: What 26.125 (build #10052026) printed for a script line it does not carry,
#: measured on 2026-10-12: the lines on stdout, no log file in the working folder.
_PROBES_JUDGES__STDOUT_REFUSAL = (
    "Running script file: probe_script.txt\n\nPYFS_A\n"
    "ERROR | Syntax | 'SET_OFF_BODY_STREAMLINE_LENGTH' | Unrecognized command in script "
    "'probe_script.txt' at line 42 | Check command spelling and syntax.\n"
    "ERROR | Scripting | N/A | Error in script 'probe_script.txt' at line 42: "
    "'SET_OFF_BODY_STREAMLINE_LENGTH' | Review command syntax and arguments.\n"
)


_PROBES_JUDGES__STDOUT_ABORT = (
    "Running script file: probe_script.txt\n\n"
    "ERROR | Scripting | N/A | Error in script 'probe_script.txt' at line 45: "
    "'CREATE_NEW_6DOF_EXTERNAL_FORCE 1 0.25 0.0 0.0 0.1 0.1 0.0 0.0 500.0' | Review command "
    "syntax and arguments.\n"
)


def _probes_judges___aborted(tmp_path: Path, stdout: str, command: str) -> ProbeArtifacts:
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


def _probes_judges___spec(command: str) -> ProbeSpec:
    return ProbeSpec(command=command, build_target=lambda s, w: None, assert_effect=lambda a: True)


def _probes_judges___artifacts(tmp_path: Path) -> ProbeArtifacts:
    return ProbeArtifacts(
        workdir=tmp_path,
        log_before="",
        log_after="",
        begin_marker=_PROBES_JUDGES__BEGIN,
        end_marker=_PROBES_JUDGES__END,
        execution=ExecutionResult(
            return_code=0, wall_time_s=1.0, timed_out=False, log_text=None, stdout="", stderr=""
        ),
    )


def _probes_judges___trajectory(path: Path, rows: list[list[float]]) -> None:
    header = "6DOF motion trajectory data\nx, y, z, u, v, w, p, q, r, phi, theta, psi\n"
    body = "".join(", ".join(f"{v:.6f}" for v in row) + "\n" for row in rows)
    path.write_text(header + body, encoding="utf-8")


#: What 26.100 (build #2122026) wrote for a name it does not carry, measured on
#: 2026-10-12: the older wording, with no table around it.
_PROBES_JUDGES__LOG_26100 = (
    "PYFS_PROBE_BEGIN_DELETE_VALAREZO_CRITERION_BOUNDARIES\n"
    "Unrecognized command in script C:/runs/probe_script.txt at line 6: "
    "DELETE_VALAREZO_CRITERION_BOUNDARIES\n"
    "Error in script C:/runs/probe_script.txt at line 6: DELETE_VALAREZO_CRITERION_BOUNDARIES\n"
)


class TestProbesJudges:
    """Tier 1: the second round of the 0.40.0 command-gap probes (the probes lane).

    The first licensed batch (2026-10-12) left 67 probe runs unprobed and 10 broken.
    Reading their logs showed instruments that could not read what the solver did,
    and one harness blind spot: 26.125 prints its script errors to its standard
    output and writes no ``FlightStreamLog.txt``, so a name it refuses was recorded
    broken instead of removed, with no line to show. These tests hold the repaired
    judges and the harness reading both channels, without the solver.
    """

    @staticmethod
    def test_p0400_probes_a_name_26125_refuses_on_stdout_is_removed(tmp_path):
        """P0400-PROBES-STDOUT: an unrecognised name printed on stdout alone records removed."""
        command = "SET_OFF_BODY_STREAMLINE_LENGTH"
        result = _judge(
            _probes_judges___spec(command),
            _probes_judges___aborted(tmp_path, _PROBES_JUDGES__STDOUT_REFUSAL, command),
            DEFAULT_ERROR_PATTERNS,
            "x",
            60,
        )
        assert result.outcome is ProbeOutcome.REMOVED, result.detail

    @staticmethod
    def test_p0400_probes_an_abort_names_the_line_the_solver_printed(tmp_path):
        """P0400-PROBES-ABORTLINE: a broken abort carries the solver's own error line."""
        command = "CREATE_NEW_6DOF_EXTERNAL_FORCE"
        result = _judge(
            _probes_judges___spec(command),
            _probes_judges___aborted(tmp_path, _PROBES_JUDGES__STDOUT_ABORT, command),
            DEFAULT_ERROR_PATTERNS,
            "x",
            60,
        )
        assert result.outcome is ProbeOutcome.BROKEN
        assert "at line 45" in result.detail
        assert any("CREATE_NEW_6DOF_EXTERNAL_FORCE 1 0.25" in line for line in result.log_errors)

    @staticmethod
    def test_p0400_probes_a_control_holds_when_the_state_stays(tmp_path, monkeypatch):
        """P0400-PROBES-CONTROL: an unmoved saved state verifies the control; a moved one fails it."""  # noqa: E501
        states = {"state_before.fsm": (("Wing",), (288, (288,))), "state_after.fsm": None}
        monkeypatch.setattr(
            kit, "_names", lambda path: states[path.name][0] if states[path.name] else None
        )
        monkeypatch.setattr(
            kit, "_faces", lambda path: states[path.name][1] if states[path.name] else None
        )
        states["state_after.fsm"] = (("Wing",), (288, (288,)))
        assert kit._state_still(_probes_judges___artifacts(tmp_path)) is True
        states["state_after.fsm"] = (("Wing", "Surface 2"), (288, (200, 88)))
        assert kit._state_still(_probes_judges___artifacts(tmp_path)) is False

    @staticmethod
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
        assert judge(_probes_judges___artifacts(tmp_path)) is True
        files["saved.fsm"] = (("Surface 3",), (408, (408,)))
        assert judge(_probes_judges___artifacts(tmp_path)) is False
        assert kit._selection_took_all(_probes_judges___artifacts(tmp_path)) is True

    @staticmethod
    def test_p0400_probes_one_surface_spanning_both_sheets_holds_the_control(tmp_path):
        """P0400-PROBES-SPAN: a surface from z 0 to 2 holds both sheets; z 0 alone does not."""
        obj = tmp_path / "surface_1.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 2\nf 1 2 3\n", encoding="utf-8")
        judge = kit._obj_spans("surface_1.obj", 2, 0.0, 2.0)
        assert judge(_probes_judges___artifacts(tmp_path)) is True
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        assert judge(_probes_judges___artifacts(tmp_path)) is None

    @staticmethod
    def test_p0400_probes_zero_surface_lines_after_a_delete_cannot_verify_it(tmp_path):
        """P0400-PROBES-SURFLINES: no line left reads unprobed; lines left break; the table verifies."""  # noqa: E501
        path = tmp_path / "surface_lines.txt"
        path.write_text(
            "     FlightStream Surface Streamlines\n     Number of Surface Streamlines:   0\n"
            "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp\n",
            encoding="utf-8",
        )
        assert (
            kit._surface_lines_deleted("surface_lines.txt")(_probes_judges___artifacts(tmp_path))
            is None
        )
        assert (
            kit._streamline_table("surface_lines.txt")(_probes_judges___artifacts(tmp_path)) is True
        )
        path.write_text("     Number of Surface Streamlines:   3\n", encoding="utf-8")
        assert (
            kit._surface_lines_deleted("surface_lines.txt")(_probes_judges___artifacts(tmp_path))
            is False
        )

    @staticmethod
    def test_p0400_probes_pitch_only_reads_theta_moving_and_z_still(tmp_path):
        """P0400-PROBES-PITCH: theta moving with z still verifies; z falling refutes."""
        first = [0.0] * 18
        still = list(first)
        still[10] = 0.07
        falling = list(still)
        falling[2] = -0.6
        path = tmp_path / kit._TRAJECTORY
        judge = kit._pitch_only(kit._TRAJECTORY)
        _probes_judges___trajectory(path, [first, still])
        assert judge(_probes_judges___artifacts(tmp_path)) is True
        _probes_judges___trajectory(path, [first, falling])
        assert judge(_probes_judges___artifacts(tmp_path)) is False

    @staticmethod
    @pytest.mark.parametrize("build", ("26.124", "26.125"))
    def test_p0400_probes_each_p4_setter_has_a_saved_state_twin(build, tmp_path):
        """P0400-PROBES-P4TWINS: the registered P4 probe is validated; its ``m`` run reads the march.

        The trajectory export written before the march held its header and no row
        on both builds (P4-04), so the trajectory is read after the march, a
        placement the phase order refuses and that is appended raw. A registered
        probe builds a validated script, so it reads the saved simulation instead,
        and the raw export stays in its ``m`` twin, after the END sentinel.
        """  # noqa: E501
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

    @staticmethod
    @pytest.mark.parametrize("build", ("26.124", "26.125"))
    def test_p0400_probes_the_declined_surface_probe_and_its_control_build(build, tmp_path):
        """P0400-PROBES-DECLINED: PFS-2085.021, the sphere on the list and off it, on both builds."""  # noqa: E501
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

    @staticmethod
    def test_p0400_probes_the_older_unrecognised_wording_is_read(tmp_path):
        """P0400-PROBES-UNTABLED: 26.100's untabled refusal records removed, not broken."""
        command = "DELETE_VALAREZO_CRITERION_BOUNDARIES"
        assert unrecognised_commands(_PROBES_JUDGES__LOG_26100) == {command}
        begin = f"PYFS_PROBE_BEGIN_{command}"
        artifacts = ProbeArtifacts(
            workdir=tmp_path,
            log_before=f"setup\n{begin}\n",
            log_after=None,
            begin_marker=begin,
            end_marker=f"PYFS_PROBE_END_{command}",
            execution=ExecutionResult(
                return_code=0,
                wall_time_s=1.0,
                timed_out=False,
                log_text=_PROBES_JUDGES__LOG_26100,
                stdout="",
                stderr="",
            ),
        )
        result = _judge(_probes_judges___spec(command), artifacts, DEFAULT_ERROR_PATTERNS, "x", 60)
        assert result.outcome is ProbeOutcome.REMOVED, result.detail


def test_f229_a_malformed_ccs_section_is_kept_unread_not_shifted(tmp_path):
    """F-229 a non-numeric token must not move the later triples of a section."""
    from types import SimpleNamespace

    (tmp_path / "curve.ccs").write_text(
        "CrossSection;1;2;3;4;5;6\nCrossSection;1;x;3;4;5;6\n",
        encoding="utf-8",
    )
    probe = next(p for p in gap.gap_probes() if p.probe_id == "P2-14")
    read = probe.spec.observe(SimpleNamespace(workdir=tmp_path))
    assert "curve.ccs 2 sections [2pts x 1.000..4.000" in read
    # The unread section stays empty: a shifted triple would add a one-point section.
    assert read.count("pts") == 1


def test_f802_and_x_f_0531_unreadable_is_not_empty_or_absent(tmp_path):
    """F-802, X-F-0531 the observation text keeps unreadable, empty and absent apart."""
    from types import SimpleNamespace

    from pyflightstream.qa import _spec_0400_gapbase as base

    (tmp_path / "state_before.fsm").write_bytes(b"not a simulation")
    probe = next(p for p in gap.gap_probes() if p.probe_id == "P2-01")
    read = probe.spec.observe(SimpleNamespace(workdir=tmp_path))
    assert "state_before.fsm boundary list unreadable" in read
    assert "0 boundaries" not in read
    empty = tmp_path / "empty.obj"
    empty.write_text("# nothing\n", encoding="utf-8")
    assert base.obj_summary(empty) == "empty.obj present, no vertices"
    assert base.obj_summary(tmp_path / "missing.obj") == "missing.obj absent"
    broken = tmp_path / "broken.obj"
    broken.write_text("v 1 2 x\n", encoding="utf-8")
    assert base.obj_summary(broken) == "broken.obj present, unreadable"


def test_f231_the_probe_section_has_a_closed_trailing_edge(tmp_path):
    """F-231 the x^4 term closes the NACA 0012 trailing edge the comment names."""
    probe = next(p for p in gap.gap_probes() if p.probe_id == "P2-14")
    generate_probe_script(probe.spec, "26.125", tmp_path)
    first = (tmp_path / "naca0012.txt").read_text(encoding="utf-8").splitlines()[0]
    x, z = (float(word) for word in first.split())
    assert x == pytest.approx(1.0)
    assert abs(z) < 1e-9
