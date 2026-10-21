"""Regression coverage grouped by subject."""

from __future__ import annotations

import inspect
import json
import warnings
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    FrameSpec,
    MeshImport,
    PprocSpec,
    RawCommand,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases import freestream as _freestream_module
from pyflightstream.cases import windows as recorded_windows
from pyflightstream.cases._farfield_spec import LatticeShape, LedgersSpec
from pyflightstream.cases.matrix import _parse_rotations
from pyflightstream.cases.workflows import (
    ExportWindow,
    WorkflowConventions,
    action_export_lines,
    build_script,
    build_steady_sweep,
    export_window,
    normal_probe_creation,
    qsteady_inflow_fft,
    reduction_plan,
    reduction_windows,
    rotor_time_stepping,
    unsteady_counter_steps,
    unsteady_export_threshold,
    unsteady_time_stepping,
    walltime_clock_program,
    walltime_stop_text,
)
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    refuse_unspliceable,
    restate_anchor,
)
from pyflightstream.cases.workflows._export_first_step import refuse_threshold_on_a_steady_run
from pyflightstream.cases.workflows._farfield import plan_record
from pyflightstream.cases.workflows._frames import _hub_basis, _keep_the_frame_this_alias_turns_from
from pyflightstream.cases.workflows._freestream import rotor_row_stepping
from pyflightstream.cases.workflows._reductions import _blade_count
from pyflightstream.cases.workflows._rows import (
    _angle,
    _require_the_averaging_window,
    _stated_rate,
    parse_restart,
    restart_iterations,
    row_ncpus,
    row_walltime_s,
)
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.post.probe_fields import write_recorded_probe_fields
from pyflightstream.run._ids import runs_as_one_job
from pyflightstream.script import CommandArgumentError, Script, helpers
from tests.support_helpers import saved_mesh_fixture as _cases_workflows_frames__saved_mesh_fixture
from tests.tier1_offline._p0400_gaps_rt_support import (
    registry_with as _gaps_rt_sixdof__registry_with,
)
from tests.tier1_offline._p0400_gaps_rt_support import (
    registry_with as _gaps_rt_streamlines__registry_with,
)
from tests.tier1_offline.test_goal024_point_name import _matrix as _cases_workflows_rates___matrix
from tests.tier1_offline.test_goal024_point_name import (
    _matrix as _cases_workflows_velocity___matrix,
)
from tests.tier1_offline.test_goal024_point_name import _plan as _cases_workflows_velocity___plan
from tests.tier1_offline.test_goal024_sweep_any_variable import AXES as _CASES_WORKFLOWS_RATES__AXES
from tests.tier1_offline.test_goal024_sweep_any_variable import (
    _resolved as _cases_workflows_rates___resolved,
)
from tests.tier1_offline.test_goal035_qsteady_rotor import RING as _CASES_WORKFLOWS_QSTEADY__RING
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    _blade_obj as _cases_workflows_qsteady___blade_obj,
)
from tests.tier1_offline.test_goal035_qsteady_rotor import _case as _cases_workflows_qsteady___case
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    _field as _cases_workflows_qsteady___field,
)
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    _lines as _cases_workflows_qsteady___lines,
)
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    _with_obj as _cases_workflows_qsteady___with_obj,
)
from tests.tier1_offline.test_p0370_s5_probe_kind import _entry as _cases_workflows_probes___entry
from tests.tier1_offline.test_p0370_s5_probe_kind import _entry as _cases_workflows_steady___entry
from tests.tier1_offline.test_p0370_s5_probe_kind import _heads as _cases_workflows_probes___heads
from tests.tier1_offline.test_p0370_s5_probe_kind import _spec as _cases_workflows_probes___spec
from tests.tier1_offline.test_p0370_s5_probe_kind import _spec as _cases_workflows_steady___spec
from tests.tier1_offline.test_raw_mesh_conditions import (
    FILE_ROUTE as _CASES_WORKFLOWS_GEOMETRY__FILE_ROUTE,
)
from tests.tier1_offline.test_raw_mesh_conditions import _case as _cases_workflows_geometry___case
from tests.tier1_offline.test_raw_mesh_conditions import (
    _library as _cases_workflows_geometry___library,
)
from tests.tier1_offline.test_reduce_by_rotor import (
    transition_case as _cases_workflows_windows__transition_case,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___case as _rfixr3_azimuths___case,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___script as _rfixr3_azimuths___script,
)
from tests.tier1_offline.test_regression_farfield_products import (
    _rfixf_layout___states as _rfixr3_azimuths___states,
)
from tests.tier1_offline.test_rotor_by_alias import PUSHER as _CASES_WORKFLOWS_MOTION__PUSHER
from tests.tier1_offline.test_rotor_by_alias import (
    two_rotor_case as _cases_workflows_motion__two_rotor_case,
)
from tests.tier1_offline.test_workflows import _case_for as _cases_workflows_probes___case_for
from tests.tier1_offline.test_workflows import _case_for as _gaps_rt_sixdof___case_for
from tests.tier1_offline.test_workflows import _case_for as _gaps_rt_streamlines___case_for
from tests.tier1_offline.test_workflows import _wb_geometry as _cases_workflows_probes___wb_geometry
from tests.tier1_offline.test_workflows import _wb_geometry as _cases_workflows_steady___wb_geometry
from tests.tier1_offline.test_workflows import _wb_geometry as _gaps_rt_sixdof___wb_geometry
from tests.tier1_offline.test_workflows import _wb_geometry as _gaps_rt_streamlines___wb_geometry
from tests.tier1_offline.test_workflows import _with_pproc as _cases_workflows_probes___with_pproc
from tests.tier1_offline.test_workflows import _with_pproc as _cases_workflows_steady___with_pproc
from tests.tier1_offline.test_workflows import _with_pproc as _gaps_rt_sixdof___with_pproc
from tests.tier1_offline.test_workflows import _with_pproc as _gaps_rt_streamlines___with_pproc
from tests.tier1_offline.test_workflows import steady_case as _cases_workflows_probes__steady_case
from tests.tier1_offline.test_workflows import steady_case as _cases_workflows_steady__steady_case
from tests.tier1_offline.test_workflows import steady_case as _gaps_rt_streamlines__steady_case

_CASES_WORKFLOWS_BATCH__HEAD = ["OPEN", "/ws/g.fsm", "", "SET_SIGNIFICANT_DIGITS 7", ""]


def _cases_workflows_batch___motion(number: int, rpm: float) -> list[str]:
    return [
        "CREATE_NEW_MOTION ROTARY",
        f"SET_MOTION_BOUNDARIES {number} 1",
        f"SET_MOTION_ROTOR_RPM {number} {rpm}",
    ]


def _cases_workflows_batch___point(folder: str, *motions: list[str]) -> JobPoint:
    text = "\n".join(
        [
            *_CASES_WORKFLOWS_BATCH__HEAD,
            *(line for motion in motions for line in motion),
            "SET_SOLVER_UNSTEADY",
            "",
        ]
    )
    return JobPoint(
        run_id=f"mtx/sim_9901/{folder}",
        sim_id="9901",
        point_name=folder,
        text=text,
        datapoint_dir=PurePosixPath(f"/ws/sim_9901/datapoints/{folder}"),
        outputs=(),
        action_exports="",
        first_export_step=None,
        stop_text="",
        time_steps=45,
    )


class TestCasesWorkflowsBatch:
    """P0400-CW-BATCH: a grouped job never creates a motion its instance still holds.

    0.40.0 item PFS-2104.037: a two-rotor point whose every speed moves was restated
    from the first rotor's SET_MOTION_ROTOR_RPM, so the second rotor's whole motion,
    CREATE_NEW_MOTION included, was created again after REMOVE_INITIALIZATION.
    """

    @staticmethod
    def test_p0400_cw_batch_a_restated_point_that_creates_a_motion_again_is_refused():
        """P0400-CW-BATCH (PFS-2104.037): both speeds move, so rotor 2 would be created twice."""
        requirement = "P0400-CW-BATCH"
        first = _cases_workflows_batch___point(
            "DP-j10",
            _cases_workflows_batch___motion(1, 1000.0),
            _cases_workflows_batch___motion(2, 2000.0),
        )
        later = _cases_workflows_batch___point(
            "DP-j12",
            _cases_workflows_batch___motion(1, 1100.0),
            _cases_workflows_batch___motion(2, 2200.0),
        )
        with pytest.raises(CampaignConfigError, match="creates a motion\\s+again") as refusal:
            refuse_unspliceable(first, later)
        assert str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_batch_one_rotor_is_still_restated_from_its_speed():
        """P0400-CW-BATCH (PFS-2104.037), control: the measured one-rotor shape is unchanged."""
        requirement = "P0400-CW-BATCH"
        first = _cases_workflows_batch___point("DP-j10", _cases_workflows_batch___motion(1, 1000.0))
        later = _cases_workflows_batch___point("DP-j12", _cases_workflows_batch___motion(1, 1100.0))
        refuse_unspliceable(first, later)
        assert restate_anchor(first, later) == "SET_MOTION_ROTOR_RPM", requirement


def _cases_workflows_clock___unsteady(
    outputs: list[str], **variables: str
) -> tuple[SimCase, WorkflowConventions]:
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=outputs,
        point={"alpha": 0.0},
        variables={
            "WORKFLOW": "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.001",
            "TIME_ITERATIONS": "100",
            "LAST_ITERS_AVG": "10",
            "WALLTIME": "4h",
            **variables,
        },
    )
    return case, WorkflowConventions(outputs=tuple(outputs))


_CASES_WORKFLOWS_CLOCK__LIFTER = RotorBlock(
    alias="LIFT_L1",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="Z",
    diameter_m=1.2,
    families_general=["LH_L1"],
    families_blades=[f"LIFT_L1_B{number}" for number in range(1, 5)],
)


_CASES_WORKFLOWS_CLOCK__PUSHER = RotorBlock(
    alias="PUSHER",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="Z",
    diameter_m=1.8,
    families_general=["PH"],
    families_blades=[f"PUSHER_B{number}" for number in range(1, 4)],
)


def _cases_workflows_clock___two_speeds(**variables: str) -> SimCase:
    return SimCase(
        sim_id="9201",
        aircraft="WORK",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        rotors={
            "LIFT_L1": _CASES_WORKFLOWS_CLOCK__LIFTER,
            "PUSHER": _CASES_WORKFLOWS_CLOCK__PUSHER,
        },
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_THETA": "10",
            "REVOLUTIONS": "2",
            "LAST_REVS_AVG": "1",
            "CLOCK_MOTION": "PUSHER",
            **variables,
        },
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
        ],
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        point={"alpha": 0.0},
    )


class TestCasesWorkflowsClock:
    """P0400-CW-CLOCK: the clock of an unsteady row, as its threshold, counter and rescue read it.

    0.40.0 items PFS-2089.006 (the renderers take the case's build, never a
    literal), PFS-2104.031 and PFS-2104.039 (the wall-clock rescue asks the
    end-of-run block's two questions about the log) and PFS-2104.003 (the
    threshold and the counter take the clock CLOCK_MOTION names) and PFS-2095.041
    (a threshold on any steady run type is refused as one).
    """

    @staticmethod
    @pytest.mark.parametrize(
        "renderer",
        [
            action_export_lines,
            unsteady_export_threshold,
            walltime_clock_program,
            walltime_stop_text,
        ],
    )
    def test_p0400_cw_clock_the_renderers_take_the_build_and_never_default_it(renderer):
        """P0400-CW-CLOCK (PFS-2089.006): `version` is required; 26.120 documents no action."""
        requirement = "P0400-CW-CLOCK"
        version = inspect.signature(renderer).parameters["version"]
        assert version.default is inspect.Parameter.empty, requirement
        assert version.kind is inspect.Parameter.KEYWORD_ONLY

    @staticmethod
    def test_p0400_cw_clock_the_rescue_writes_no_log_where_the_machine_turns_it_off():
        """P0400-CW-CLOCK (PFS-2104.031, PFS-2104.039): EXPORT_LOG false reaches the rescue too.

        The run layer sets EXPORT_LOG false on the point case of a machine that
        aborts at the command, and the rescue still wrote it there.
        """
        requirement = "P0400-CW-CLOCK"
        outputs = ["loads_a.txt", "loads_a_log.txt"]
        case, conventions = _cases_workflows_clock___unsteady(outputs, EXPORT_LOG="false")
        text = walltime_stop_text(case, conventions, version="26.124")
        assert "EXPORT_LOG" not in text, (requirement, text)
        assert "loads_a.txt" in text
        on, conventions = _cases_workflows_clock___unsteady(outputs)
        assert "EXPORT_LOG\nloads_a_log.txt" in walltime_stop_text(
            on, conventions, version="26.124"
        )

    @staticmethod
    def test_p0400_cw_clock_the_rescue_writes_a_log_output_log_by_position():
        """P0400-CW-CLOCK (PFS-2104.031): a LOG_OUTPUT log not named *_log.txt was left out."""
        requirement = "P0400-CW-CLOCK"
        outputs = ["loads_a.txt", "solver_run.out"]
        case, conventions = _cases_workflows_clock___unsteady(outputs, LOG_OUTPUT="2")
        lines = walltime_stop_text(case, conventions, version="26.124").splitlines()
        assert lines[lines.index("EXPORT_LOG") + 1] == "solver_run.out", (requirement, lines)
        off, conventions = _cases_workflows_clock___unsteady(
            outputs, LOG_OUTPUT="2", EXPORT_LOG="false"
        )
        assert "EXPORT_LOG" not in walltime_stop_text(off, conventions, version="26.124")

    @staticmethod
    def test_p0400_cw_clock_the_threshold_and_counter_take_the_clock_motion():
        """P0400-CW-CLOCK (PFS-2104.003): CLOCK_MOTION names the slower rotor, and it owns the clock.

        The threshold took the fastest rotor's clock, so its delta_time_s was the
        lifter's ten degrees while the script's SET_SOLVER_UNSTEADY was the pusher's.
        """  # noqa: E501
        requirement = "P0400-CW-CLOCK"
        case = _cases_workflows_clock___two_speeds(EXPORT_UNSTEADY_AFTER_ITER="1")
        builder = rotor_row_stepping(case)
        assert builder.delta_time_s == pytest.approx(10.0 / (6.0 * 900.0)), requirement
        threshold = unsteady_export_threshold(case, version="26.124")
        assert threshold is not None
        assert threshold.delta_time_s == builder.delta_time_s
        assert threshold.step_deg == pytest.approx(10.0)
        assert threshold.time_iterations == builder.time_iterations == 72
        assert unsteady_counter_steps(case) == builder.time_iterations

    @staticmethod
    @pytest.mark.parametrize(
        "key",
        ["EXPORT_UNSTEADY_AFTER_ITER", "EXPORT_UNSTEADY_LAST_ITER", "EXPORT_UNSTEADY_AFTER_REV"],
    )
    def test_p0400_cw_clock_a_threshold_on_the_quasi_steady_rotor_is_refused_as_steady(key):
        """P0400-CW-CLOCK (PFS-2095.041): qsteady_rotor has no time loop, and the refusal says so.

        It fell through to refusals about an unsteady clock, or about a run type
        that "turns nothing", which a quasi-steady rotor does not.
        """
        requirement = "P0400-CW-CLOCK"
        case, _ = _cases_workflows_clock___unsteady(["loads_a.txt"], **{key: "1"})
        with pytest.raises(
            CampaignConfigError, match="names the qsteady_rotor run type, which has no"
        ) as refusal:
            refuse_threshold_on_a_steady_run(case, key, "qsteady_rotor")
        assert str(refusal.value), requirement


_CASES_WORKFLOWS_EXPORTS__OUTPUTS = ["loads_a.txt", "surf_a.vtk", "loads_a_log.txt"]


def _cases_workflows_exports___steady(log_output: str) -> SimCase:
    return SimCase(
        sim_id="7002",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=_CASES_WORKFLOWS_EXPORTS__OUTPUTS,
        variables={"WORKFLOW": "steady", "VELOCITY": "30.0", "LOG_OUTPUT": log_output},
        point={"alpha": 0.0},
    )


class TestCasesWorkflowsExports:
    """P0400-CW-EXPORTS: the end-of-run export block and the solver log it may write.

    0.40.0 item PFS-2096.003: LOG_OUTPUT's overwrite guard knew only the loads
    table's position, so a log pointed at the VTK was written over it.
    """

    @staticmethod
    def test_p0400_cw_exports_a_log_pointed_at_the_vtk_is_refused():
        """P0400-CW-EXPORTS (PFS-2096.003): position 2 is the VTK this block already exports."""
        requirement = "P0400-CW-EXPORTS"
        with pytest.raises(
            CampaignConfigError, match="already exports 'surf_a.vtk' there"
        ) as refusal:
            build_script(_cases_workflows_exports___steady("2"), Script("26.124"))
        assert str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_exports_a_log_pointed_at_its_own_entry_is_exported():
        """P0400-CW-EXPORTS (PFS-2096.003), control: position 3 is the log's own entry."""
        requirement = "P0400-CW-EXPORTS"
        script = Script("26.124")
        build_script(_cases_workflows_exports___steady("3"), script)
        lines = script.render().splitlines()
        assert "EXPORT_LOG" in lines, requirement
        assert lines[lines.index("EXPORT_LOG") + 1] == "loads_a_log.txt"


_CASES_WORKFLOWS_FRAMES__SHAFT = (1.0, 0.0, 0.1)


_CASES_WORKFLOWS_FRAMES__PUSHER = RotorBlock(
    alias="PUSHER",
    axis=_CASES_WORKFLOWS_FRAMES__SHAFT,
    rpm_sign=1,
    diameter_m=1.8,
    x_m=7.2,
    families_general=["Spinner"],
    families_blades=["Blade1", "Blade2", "Blade3"],
    blade1=BladeDatum(azimuth_deg=30.0, zero="Y"),
)


def _cases_workflows_frames___flat_row(tmp_path, **variables: str) -> SimCase:
    mesh = ["Spinner", "Blade1", "Blade2", "Blade3", "W"]
    case = SimCase(
        sim_id="9301",
        aircraft="WORK",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "RPM": "1200",
            "ROTOR_AXIS": "Z",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            "LAST_REVS_AVG": "1",
            **variables,
        },
        point={"alpha": 0.0},
        geometry=str(_cases_workflows_frames__saved_mesh_fixture(tmp_path / "w.fsm", mesh)),
        rotors={"PUSHER": _CASES_WORKFLOWS_FRAMES__PUSHER},
        aliases={"PUSHER": mesh[:4]},
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
    )
    case.rotations = _parse_rotations(
        {"ROTATE": "{ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}"}, case.sim_id
    )
    return case


def _cases_workflows_frames___frames(
    case: SimCase,
) -> tuple[dict[str, dict[str, float]], list[list[str]]]:
    """Each frame's EDIT_COORDINATE_SYSTEM fields by name, and every ROTATE block."""
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    edits: dict[str, dict[str, float]] = {}
    rotations: list[list[str]] = []
    for at, line in enumerate(lines):
        if line == "EDIT_COORDINATE_SYSTEM":
            name = lines[at + 2].split(" ", 1)[1]
            fields = dict(each.split(" ", 1) for each in lines[at + 3 : at + 15])
            edits[name] = {key: float(value) for key, value in fields.items()}
            edits[name]["FRAME"] = float(lines[at + 1].split()[1])
        elif line == "ROTATE_COORDINATE_SYSTEM":
            rotations.append(lines[at + 1 : at + 5])
    return edits, rotations


def _cases_workflows_frames___placement(edit: dict[str, float]) -> list[float]:
    keys = ("ORIGIN", "VECTOR_X", "VECTOR_Y", "VECTOR_Z")
    return [value for key, value in edit.items() if key.startswith(keys)]


class TestCasesWorkflowsFrames:
    """P0400-CW-FRAMES: a flat rotor row's frames are placed from its hub as the script placed it.

    0.40.0 items PFS-2104.004 (the ``<ALIAS>_SMRP_ORIGINAL`` copy is the hub as
    placed), PFS-2104.005 (the flat row's blade frames sit at the hub, on its
    basis, from the blade1 datum) and PFS-2104.034 (the hub basis keeps the sign of
    ``blade1.zero``).
    """

    @staticmethod
    def test_p0400_cw_frames_the_original_copy_is_the_hub_as_placed(tmp_path):
        """P0400-CW-FRAMES (PFS-2104.004): ROTOR_ORIGIN and the shaft basis reach the copy.

        It was rebuilt from the block's origin on identity axes, a frame the hub
        never was on this row.
        """
        requirement = "P0400-CW-FRAMES"
        edits, _ = _cases_workflows_frames___frames(
            _cases_workflows_frames___flat_row(tmp_path, ROTOR_ORIGIN="1.0,2.0,3.0")
        )
        hub, copy = edits["PUSHER_SMRP"], edits["PUSHER_SMRP_ORIGINAL"]
        assert (hub["ORIGIN_X"], hub["ORIGIN_Y"], hub["ORIGIN_Z"]) == (1.0, 2.0, 3.0), requirement
        assert _cases_workflows_frames___placement(copy) == _cases_workflows_frames___placement(hub)

    @staticmethod
    def test_p0400_cw_frames_a_flat_rows_blade_frames_sit_at_the_hub_from_the_datum(tmp_path):
        """P0400-CW-FRAMES (PFS-2104.005): the blades turn about the hub they are named under.

        They sat at `rotor_position_m` or the origin, on identity axes, from azimuth
        zero, while being registered as the hub's `<ALIAS>_RMRP<k>`.
        """
        requirement = "P0400-CW-FRAMES"
        edits, rotations = _cases_workflows_frames___frames(
            _cases_workflows_frames___flat_row(tmp_path, ROTOR_ORIGIN="1.0,2.0,3.0")
        )
        hub = edits["PUSHER_SMRP"]
        blades = [edits[f"BladeAxis{number}"] for number in (1, 2, 3)]
        for blade in blades:
            assert _cases_workflows_frames___placement(
                blade
            ) == _cases_workflows_frames___placement(hub), requirement
        turns = {
            int(rotation[0].split()[1]): rotation[1:]
            for rotation in rotations
            if rotation[1] == f"ROTATION_FRAME {int(hub['FRAME'])}"
            and rotation[2] != "ROTATION_AXIS Y"
        }
        assert [turns[int(blade["FRAME"])] for blade in blades] == [
            [f"ROTATION_FRAME {int(hub['FRAME'])}", "ROTATION_AXIS Z", f"ANGLE {angle}"]
            for angle in (30.0, 150.0, 270.0)
        ]

    @staticmethod
    def test_p0400_cw_frames_the_hub_basis_keeps_the_sign_of_the_datum():
        """P0400-CW-FRAMES (PFS-2104.034): '-Y' measures the azimuth from the opposite side."""
        requirement = "P0400-CW-FRAMES"
        plus = _hub_basis(_CASES_WORKFLOWS_FRAMES__PUSHER)
        minus = _hub_basis(
            _CASES_WORKFLOWS_FRAMES__PUSHER.model_copy(
                update={"blade1": BladeDatum(azimuth_deg=30.0, zero="-Y")}
            )
        )
        assert minus[0] == pytest.approx(tuple(-each for each in plus[0])), requirement
        assert minus[1] == pytest.approx(tuple(-each for each in plus[1]))

    @staticmethod
    def test_p0400_cw_frames_an_unplaced_hub_cannot_be_copied(tmp_path):
        """P0400-CW-FRAMES (PFS-2104.004): a copy cannot guess an opened or turned hub."""
        requirement = "P0400-CW-FRAMES"
        with pytest.raises(CampaignConfigError, match="cannot state where PUSHER_SMRP") as refusal:
            _keep_the_frame_this_alias_turns_from(
                _cases_workflows_frames___flat_row(tmp_path),
                {"ALIAS": "PUSHER"},
                Script("26.124"),
                {"PUSHER_SMRP": 2},
                set(),
            )
        assert str(refusal.value), requirement


def _cases_workflows_geometry___rendered(tmp_path, unit: str | None) -> tuple[list[str], Script]:
    case = _cases_workflows_geometry___case(
        tmp_path,
        _cases_workflows_geometry___library(tmp_path, _CASES_WORKFLOWS_GEOMETRY__FILE_ROUTE),
    )
    if unit is not None:
        solver = case.solver.model_copy(update={"simulation_length_unit": unit})
        case = case.model_copy(update={"solver": solver})
    script = Script("26.124")
    build_script(case, script)
    return script.render().splitlines(), script


class TestCasesWorkflowsGeometry:
    """P0400-CW-GEOMETRY: a raw mesh's trailing-edge points are written in the simulation's unit.

    0.40.0 item PFS-2104.007: the setup may set the simulation to MILLIMETER after
    the import, and the node file was still written and declared in metres, so the
    import matched no edge and marked nothing.
    """

    @staticmethod
    def test_p0400_cw_geometry_the_node_file_follows_a_millimetre_simulation(tmp_path):
        """P0400-CW-GEOMETRY (PFS-2104.007): points and tolerance in MILLIMETER, declared so."""
        requirement = "P0400-CW-GEOMETRY"
        lines, script = _cases_workflows_geometry___rendered(tmp_path, "MILLIMETER")
        assert "SET_SIMULATION_LENGTH_UNITS MILLIMETER" in lines, requirement
        at = lines.index("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.1 MILLIMETER")
        parked = script.pending_input_files[lines[at + 1]].splitlines()
        assert parked[:3] == ["16", "0,0,0", "1000.0,-3750.0,0.0"], parked

    @staticmethod
    def test_p0400_cw_geometry_a_metre_simulation_writes_what_it_always_did(tmp_path):
        """P0400-CW-GEOMETRY (PFS-2104.007), control: the metre route is byte for byte the same."""
        requirement = "P0400-CW-GEOMETRY"
        lines, script = _cases_workflows_geometry___rendered(tmp_path, None)
        at = lines.index("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER")
        parked = script.pending_input_files[lines[at + 1]].splitlines()
        assert parked[:3] == ["16", "0,0,0", "1.0,-3.75,0.0"], (requirement, parked)


class TestCasesWorkflowsMotion:
    """P0400-CW-MOTION: a MOTIONS row never turns a vector shaft about global Z.

    0.40.0 item PFS-2104.008: the MOTIONS builder creates the hub on the
    geometry's axes while the view hands the motion the letter Z. Both the hub
    and moving frame must put their third axis on the declared shaft.
    """

    @staticmethod
    def test_p0400_cw_motion_a_vector_shaft_on_a_motions_row_uses_its_shaft(tmp_path):
        """P0400-CW-MOTION (PFS-2104.008): local Z follows the declared vector shaft."""
        requirement = "P0400-CW-MOTION"
        case = _cases_workflows_motion__two_rotor_case(tmp_path)
        tilted = type(_CASES_WORKFLOWS_MOTION__PUSHER).model_validate(
            {**_CASES_WORKFLOWS_MOTION__PUSHER.model_dump(), "axis": (1.0, 0.0, 0.1)}
        )
        case = case.model_copy(update={"rotors": {**case.rotors, "PUSHER": tilted}})
        script = Script("26.124")
        build_script(case, script)
        lines = script.render().splitlines()
        placements = {}
        for at, line in enumerate(lines):
            if line == "EDIT_COORDINATE_SYSTEM":
                name = lines[at + 2].split(" ", 1)[1]
                fields = dict(each.split(" ", 1) for each in lines[at + 3 : at + 15])
                placements[name] = tuple(float(fields[f"VECTOR_Z_{axis}"]) for axis in "XYZ")
        for name in ("PUSHER_SMRP", "PUSHER_RMRP"):
            assert placements[name] == pytest.approx(tilted.axis_vector), requirement

    @staticmethod
    def test_p0400_cw_motion_a_letter_shaft_on_a_motions_row_still_builds(tmp_path):
        """P0400-CW-MOTION (PFS-2104.008), control: the letter path is untouched."""
        requirement = "P0400-CW-MOTION"
        script = Script("26.124")
        build_script(_cases_workflows_motion__two_rotor_case(tmp_path), script)
        assert "SET_MOTION_ROTOR_RPM" in script.render(), requirement


def _cases_workflows_probes___averaged(tmp_path):
    spec = _cases_workflows_probes___spec(
        _cases_workflows_probes___entry("normal", frame="MRP"), time_averaging={"last_iters": 3}
    )
    case = _cases_workflows_probes___with_pproc(
        _cases_workflows_probes___case_for("unsteady"),
        _cases_workflows_probes___wb_geometry(tmp_path),
        pproc=spec,
    )
    case = case.model_copy(
        update={"outputs": [name.replace("{name}", "P") for name in spec.outputs(True)]}
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return case, script


def _cases_workflows_probes___steady_with(tmp_path, *entries, frames=()):
    spec = PprocSpec.model_validate({"groups": {"1": "all"}, "probes": list(entries)})
    case = _cases_workflows_probes___with_pproc(
        _cases_workflows_probes__steady_case(),
        _cases_workflows_probes___wb_geometry(tmp_path),
        pproc=spec,
    )
    return case.model_copy(
        update={
            "outputs": ["point.txt", "point_probes.txt", "point_plots.txt"],
            "frames": list(frames),
        }
    )


def _cases_workflows_probes___rendered(case) -> tuple[list[str], Script]:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script.render().splitlines(), script


_CASES_WORKFLOWS_PROBES__TILTED = FrameSpec(
    name="PROBE_F", origin=(1.0, 0.0, 0.0), x_axis=(2.0, 0.0, 0.0)
)


class TestCasesWorkflowsProbes:
    """P0400-CW-PROBES: the probe points a script creates, where and how often.

    0.40.0 items PFS-2104.033 (normal probes on a row whose per-step window comes
    from ``[time_averaging]`` alone were never created during the march),
    PFS-2104.009 (a steady cited survey in rotor radii is scaled), PFS-2104.038 (a
    steady probe in a named frame is placed with unit axes) and PFS-2105.027 (a
    steady probe field records the reference-frame points it declares).
    """

    @staticmethod
    def test_p0400_cw_probes_a_time_averaging_window_creates_its_normal_probes(tmp_path):
        """P0400-CW-PROBES (PFS-2104.033): the averaging-only window creates what it exports."""
        requirement = "P0400-CW-PROBES"
        case, script = _cases_workflows_probes___averaged(tmp_path)
        creation = normal_probe_creation(case, "26.124")
        assert creation.startswith("DELETE_PROBE_POINTS\nNEW_PROBE_LINE"), (requirement, creation)
        heads = _cases_workflows_probes___heads(script)
        assert heads[heads.index("START_SOLVER") + 1] == "DELETE_PROBE_POINTS", heads

    @staticmethod
    def test_p0400_cw_probes_a_survey_in_rotor_radii_is_scaled_on_a_steady_row(tmp_path):
        """P0400-CW-PROBES (PFS-2104.009): the import took the file's numbers as metres."""
        requirement = "P0400-CW-PROBES"
        survey = tmp_path / "survey.txt"
        survey.write_text("1\n2,3,4,1\n", encoding="utf-8", newline="\n")
        entry = {
            "frame": "REFERENCE",
            "parameters": ["MACH"],
            "points_file": "survey.txt",
            "scale": "rotor_radius",
        }
        case = _cases_workflows_probes___steady_with(tmp_path, entry)
        case.pproc.probes[0] = case.pproc.probes[0].model_copy(
            update={"resolved_points_file": str(survey)}
        )
        lines, _ = _cases_workflows_probes___rendered(case)
        assert "PROBE_POINTS_IMPORT" not in lines, requirement
        radius = 3.6576 / 2.0
        expected = " ".join(str(round(value * radius, 5)) for value in (2, 3, 4))
        created = [line for line in lines if line.startswith("NEW_PROBE_POINT")]
        assert created == [f"NEW_PROBE_POINT VOLUME {expected}"], created

    @staticmethod
    def test_p0400_cw_probes_a_cited_survey_in_a_named_frame_is_placed(tmp_path):
        """P0400-CW-PROBES (PFS-2104.009): the import has no named-frame argument."""
        requirement = "P0400-CW-PROBES"
        survey = tmp_path / "survey.txt"
        survey.write_text("1" + chr(10) + "2,3,4,1" + chr(10), encoding="utf-8")
        entry = {"frame": "PROBE_F", "parameters": ["MACH"], "points_file": "survey.txt"}
        case = _cases_workflows_probes___steady_with(
            tmp_path, entry, frames=[_CASES_WORKFLOWS_PROBES__TILTED]
        )
        case.pproc.probes[0] = case.pproc.probes[0].model_copy(
            update={"resolved_points_file": str(survey)}
        )
        lines, _ = _cases_workflows_probes___rendered(case)
        assert "PROBE_POINTS_IMPORT" not in lines, requirement
        assert "NEW_PROBE_POINT VOLUME 3.0 3.0 4.0" in lines

    @staticmethod
    def test_p0400_cw_probes_a_transformed_surface_survey_is_refused(tmp_path):
        """P0400-CW-PROBES (PFS-2104.009): transforming TYPE 0 cannot invent a volume sample."""
        requirement = "P0400-CW-PROBES"
        survey = tmp_path / "survey.txt"
        survey.write_text("1" + chr(10) + "2,3,4,0" + chr(10), encoding="utf-8")
        entry = {"frame": "PROBE_F", "parameters": ["MACH"], "points_file": "survey.txt"}
        case = _cases_workflows_probes___steady_with(
            tmp_path, entry, frames=[_CASES_WORKFLOWS_PROBES__TILTED]
        )
        case.pproc.probes[0] = case.pproc.probes[0].model_copy(
            update={"resolved_points_file": str(survey)}
        )
        with pytest.raises(
            CampaignConfigError, match="surface TYPE 0.*transforms a survey"
        ) as refusal:
            _cases_workflows_probes___rendered(case)
        assert "REFERENCE frame" in str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_probes_a_steady_line_in_a_frame_uses_its_unit_axes(tmp_path):
        """P0400-CW-PROBES (PFS-2104.038): an x_axis of length 2 doubled the line's reach."""
        requirement = "P0400-CW-PROBES"
        entry = {
            "frame": "PROBE_F",
            "parameters": ["MACH"],
            "points": 2,
            "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
        }
        lines, _ = _cases_workflows_probes___rendered(
            _cases_workflows_probes___steady_with(
                tmp_path, entry, frames=[_CASES_WORKFLOWS_PROBES__TILTED]
            )
        )
        created = [line for line in lines if line.startswith("NEW_PROBE_LINE")]
        assert created == ["NEW_PROBE_LINE 2 1.0 0.0 0.0 2.0 0.0 0.0"], (requirement, created)

    @staticmethod
    def test_p0400_cw_probes_a_steady_probe_field_records_the_reference_points(tmp_path):
        """P0400-CW-PROBES (PFS-2105.027): the layout says REFERENCE and carries those points."""
        requirement = "P0400-CW-PROBES"
        square = FrameSpec(name="PROBE_F", origin=(1.0, 0.0, 0.0))
        entry = {
            "frame": "PROBE_F",
            "parameters": ["VX", "VY", "VZ"],
            "points": 2,
            "field_formats": ["vtk"],
            "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
        }
        _, script = _cases_workflows_probes___rendered(
            _cases_workflows_probes___steady_with(tmp_path, entry, frames=[square])
        )
        (layout,) = [item for item in script.probe_field_layout if item["kind"] == "probe-field"]
        assert layout["frame"] == "REFERENCE" and layout["declared_frame"] == "PROBE_F", requirement
        assert layout["points_native"] == [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
        assert [point[4] for point in script.probe_points] == ["REFERENCE", "REFERENCE"]


class TestCasesWorkflowsProvenance:
    """Reference coordinates keep the field's originally declared frame in provenance."""

    @staticmethod
    def test_p0400_cw_provenance_a_reference_field_keeps_its_declared_frame(tmp_path):
        """P0400-CW-PROBES (PFS-2105.027): writing metadata preserves the separate declaration."""
        requirement = "P0400-CW-PROBES"
        script = Script("26.124")
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
        source = tmp_path / "probes.csv"
        source.write_text(
            "PROBE,STEP,X,Y,Z,FRAME,VX,VY,VZ" + chr(10) + "1,NA,1,2,3,REFERENCE,11,3,5" + chr(10),
            encoding="utf-8",
        )
        layout = dict(
            entry=1,
            probe_ids=[1],
            frame="REFERENCE",
            declared_frame="PROBE_F",
            frame_index=1,
            coordinate_frame_index=1,
            coordinate_source="native-export-reference",
            export_kind="steady-probe",
            native_to_m=1.0,
            formats=["vtk"],
            reusable_inflow=False,
            points_native=[[1, 2, 3]],
        )
        record = SimpleNamespace(
            run_id="steady",
            campaign=None,
            probe_field_layout=[layout],
            frame_motions=script.frame_motions,
            fs_exe_sha256="9" * 64,
            fs_build="8172026",
            solver_setup=helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                mode="json"
            ),
        )
        paths = write_recorded_probe_fields(source, record, tmp_path / "out", "P")
        vtk = next(path for path in paths if path.suffix == ".vtk")
        metadata = json.loads(vtk.with_suffix(".vtk.provenance.json").read_text())["sampling"]
        assert metadata["declared_frame"] == "PROBE_F", requirement
        assert metadata["frame"] == "REFERENCE"


class TestCasesWorkflowsQsteady:
    """P0400-CW-QSTEADY: the quasi-steady rotor reads its inflow and its raw lines as one.

    0.40.0 item PFS-2104.010: ``qsteady_inflow_fft`` read a NATIVE or undeclared
    custom inflow in the raw mesh file's import unit, while the builder reads it in
    the simulation's unit, which is metres for a raw mesh. PFS-2104.042: the
    clockings before the last skipped the row's raw exec, analysis and export lines.
    """

    @staticmethod
    @pytest.mark.parametrize("declared", ["NATIVE", None])
    def test_p0400_cw_qsteady_the_plan_reads_the_inflow_in_the_simulations_unit(
        tmp_path, monkeypatch, declared
    ):
        """P0400-CW-QSTEADY (PFS-2104.010): a millimetre OBJ is a metre simulation."""
        requirement = "P0400-CW-QSTEADY"
        obj = _cases_workflows_qsteady___blade_obj(tmp_path / "prop.obj")
        case = _cases_workflows_qsteady___with_obj(
            _cases_workflows_qsteady___case(tmp_path), obj, ("Blade1", "Blade2", "Blade3")
        )
        case = case.model_copy(update={"mesh_import": MeshImport(units="MILLIMETER")})
        path = _cases_workflows_qsteady___field(
            tmp_path, [(*p, 30.0, 0.0, 0.0) for p in _CASES_WORKFLOWS_QSTEADY__RING]
        )
        variables = {**case.variables, "FREESTREAM": path.stem}
        if declared is not None:
            variables["FREESTREAM_UNITS"] = declared
        case = case.model_copy(update={"variables": variables, "freestream_profile": str(path)})
        seen: list[object] = []

        def recording(*args, **kwargs):
            seen.append(kwargs.get("native_unit"))
            raise CampaignConfigError("stopped by the test")

        monkeypatch.setattr(_freestream_module, "field_rows_in_metres", recording)
        record = qsteady_inflow_fft(case)
        assert record is not None and "stopped by the test" in str(record.get("note")), requirement
        assert seen == ["METER"], seen

    @staticmethod
    def test_p0400_cw_qsteady_every_clocking_gets_the_rows_raw_phase_lines():
        """P0400-CW-QSTEADY (PFS-2104.042): a raw exec or analysis line reached the last solve alone.

        Three clockings on three blades: each solve carries the init-phase setting
        the row declares before exec, and the analysis line it declares after.
        """  # noqa: E501
        requirement = "P0400-CW-QSTEADY"
        case = _cases_workflows_qsteady___case(PASSAGE_POSITIONS="3", ALPHA_POINT=5.0).model_copy(
            update={
                "raw_commands": [
                    RawCommand(command="SOLVER_SET_ITERATIONS 321", before="exec"),
                    RawCommand(command="DELETE_VORTICITY_DRAG_BOUNDARIES", before="analysis"),
                ]
            }
        )
        lines, _ = _cases_workflows_qsteady___lines(case)
        assert lines.count("START_SOLVER") == 3, requirement
        assert lines.count("SOLVER_SET_ITERATIONS 321") == 3, lines
        assert lines.count("DELETE_VORTICITY_DRAG_BOUNDARIES") == 3, lines
        starts = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
        settings = [at for at, line in enumerate(lines) if line == "SOLVER_SET_ITERATIONS 321"]
        assert all(setting < start for setting, start in zip(settings, starts, strict=True))


class TestCasesWorkflowsRates:
    """A matrix body-rate sweep builds a fresh free stream at every point."""

    @staticmethod
    def test_p0400_cw_rates_a_matrix_sweep_runs_each_rate_as_its_own_job(tmp_path):
        """P0400-CW-RATES (PFS-2104.043): the job router cannot group different body rates."""
        requirement = "P0400-CW-RATES"
        workspace, matrix = _cases_workflows_rates___matrix(
            tmp_path,
            condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
            values="2.0,4.0",
        )
        reference = workspace.inputs_dir / "references" / "r003.toml"
        reference.write_text(
            reference.read_text(encoding="utf-8") + _CASES_WORKFLOWS_RATES__AXES, encoding="utf-8"
        )
        resolved = _cases_workflows_rates___resolved(workspace, matrix)
        case = resolved.campaign.sims[0]
        assert not runs_as_one_job(resolved.campaign, case), requirement
        texts = []
        for point in case.sweep.points():
            script = Script("26.120")
            build_script(case.model_copy(update={"point": point}), script)
            texts.append(script.render())
        assert all(text.count("SET_FREESTREAM ROTATION") == 1 for text in texts)
        assert texts[0] != texts[1]


_CASES_WORKFLOWS_REDUCTIONS__FOUR = RotorBlock(
    alias="ROTOR",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="X",
    diameter_m=1.0,
    families_general=[],
    families_blades=["Blade1", "Blade2", "Blade3", "Blade4"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _cases_workflows_reductions___row(
    workflow: str = "unsteady_rotor", **variables: str
) -> SimCase:
    stated: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_THETA": "5",
        "REVOLUTIONS": "4",
        "LAST_REVS_AVG": "1",
        "RPM": "1200",
        "ROTOR_AXIS": "X",
    }
    if workflow == "unsteady":
        stated = {
            "WORKFLOW": workflow,
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.001",
            "TIME_ITERATIONS": "720",
        }
    stated.update(variables)
    return SimCase(
        sim_id="7101",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        variables=stated,
        point={"alpha": 0.0},
        rotors={"ROTOR": _CASES_WORKFLOWS_REDUCTIONS__FOUR} if workflow == "unsteady_rotor" else {},
    )


_CASES_WORKFLOWS_REDUCTIONS__LIFTER = _CASES_WORKFLOWS_REDUCTIONS__FOUR.model_copy(
    update={"alias": "LIFTER", "axis": "Z"}
)


_CASES_WORKFLOWS_REDUCTIONS__PUSHER = _CASES_WORKFLOWS_REDUCTIONS__FOUR.model_copy(
    update={"alias": "PUSHER", "families_blades": ["P1", "P2", "P3"], "diameter_m": 1.8}
)


class TestCasesWorkflowsReductions:
    """P0400-CW-REDUCTIONS: the windows a point record carries for its reductions.

    0.40.0 items PFS-2104.011 (the block is the blade count, never the periodic
    copies), PFS-2095.007 and PFS-2081.33 (an averaging window the clock cannot
    resolve is a recorded skip, as the docstring says, not an exception),
    PFS-2100.022 (a window cut to the run says so), PFS-2095.006 (a left-handed
    rotor spins) and PFS-2081.20 (a rotor's revolution comes from the azimuthal
    step where the clock states one).
    """

    @staticmethod
    def test_p0400_cw_reductions_a_two_of_four_sector_has_four_blades():
        """P0400-CW-REDUCTIONS (PFS-2104.011): PERIODIC_COPIES 2 is what the file is, not the rotor."""  # noqa: E501
        requirement = "P0400-CW-REDUCTIONS"
        case = _cases_workflows_reductions___row(SYMMETRY="PERIODIC", PERIODIC_COPIES="2")
        assert _blade_count(case) == 4, requirement
        plan = reduction_windows(case)
        assert plan is not None
        assert plan["blades"] == 4
        assert plan["per_blade"]["period_steps"] == 72 // 4

    @staticmethod
    def test_p0400_cw_reductions_a_row_blade_count_against_the_block_is_refused():
        """P0400-CW-REDUCTIONS (PFS-2104.011): BLADES 3 beside a block of four names both."""
        requirement = "P0400-CW-REDUCTIONS"
        with pytest.raises(CampaignConfigError, match="BLADES: 3 .* 4 blade"):
            _blade_count(_cases_workflows_reductions___row(BLADES="3"))
        assert _blade_count(_cases_workflows_reductions___row(BLADES="4")) == 4, requirement

    @staticmethod
    def test_p0400_cw_reductions_revolutions_without_a_clock_are_a_recorded_skip():
        """P0400-CW-REDUCTIONS (PFS-2095.007, PFS-2081.33): the refusal is recorded, not raised.

        The averaging window was read outside the try, so the run's point record
        raised where the docstring promised a skipped reduction with its reason.
        """
        requirement = "P0400-CW-REDUCTIONS"
        plan = reduction_windows(_cases_workflows_reductions___row("unsteady", LAST_REVS_AVG="1"))
        assert plan is not None, requirement
        assert "no rotor speed" in plan["time_average"]["skipped"]

    @staticmethod
    def test_p0400_cw_reductions_a_window_longer_than_the_run_says_it_was_cut():
        """P0400-CW-REDUCTIONS (PFS-2100.022): the record no longer calls a cut window the row's."""
        requirement = "P0400-CW-REDUCTIONS"
        plan = reduction_windows(
            _cases_workflows_reductions___row("unsteady", LAST_ITERS_AVG="1000")
        )
        assert plan is not None, requirement
        average = plan["time_average"]
        assert average["windows"] == [[1, 720]]
        assert "cut to the whole run" in average["window_from"], average
        stated = reduction_windows(
            _cases_workflows_reductions___row("unsteady", LAST_ITERS_AVG="100")
        )
        assert stated is not None
        assert "cut" not in stated["time_average"]["window_from"]

    @staticmethod
    def test_p0400_cw_reductions_a_left_handed_rotor_spins():
        """P0400-CW-REDUCTIONS (PFS-2095.006): a signed speed is a speed of that magnitude."""
        requirement = "P0400-CW-REDUCTIONS"
        window = export_window(
            revolutions=1.0, rpm=-1200.0, delta_time_s=0.0001, time_iterations=720
        )
        assert window.steps == 500, requirement
        assert window.steps_per_revolution == pytest.approx(500.0)

    @staticmethod
    def test_p0400_cw_reductions_a_stationary_public_window_has_no_revolution():
        """P0400-CW-REDUCTIONS (PFS-2095.006): a step window at rest has no angular clock."""
        requirement = "P0400-CW-REDUCTIONS"
        window = export_window(steps=10, rpm=0.0, delta_time_s=0.001, time_iterations=20)
        assert window.steps_per_revolution is None, requirement

    @staticmethod
    def test_p0400_cw_reductions_a_rotors_revolution_is_counted_from_the_azimuthal_step():
        """P0400-CW-REDUCTIONS (PFS-2081.20): 1.5 degrees a step is 240 steps a turn, exactly.

        From the seconds derived from that step, 60 / (rpm dt) read
        240.00000000000003 for the clock rotor.
        """
        requirement = "P0400-CW-REDUCTIONS"
        case = SimCase(
            sim_id="9201",
            aircraft="WORK",
            recipe="unsteady_rotor",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            rotors={
                "LIFTER": _CASES_WORKFLOWS_REDUCTIONS__LIFTER,
                "PUSHER": _CASES_WORKFLOWS_REDUCTIONS__PUSHER,
            },
            variables={
                "WORKFLOW": "unsteady_rotor",
                "VELOCITY": "30.0",
                "DELTA_THETA": "1.5",
                "REVOLUTIONS": "8",
                "LAST_REVS_AVG": "1",
                "CLOCK_MOTION": "LIFTER",
            },
            motions=[
                {"MOVING_BC_ALIAS": "LIFTER", "RPM": "473.1723"},
                {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
            ],
            reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
            point={"alpha": 0.0},
        )
        plan = reduction_windows(case)
        assert plan is not None, requirement
        rotors = plan["rotors"]
        assert rotors["LIFTER"]["steps_per_revolution"] == 240.0
        assert rotors["PUSHER"]["steps_per_revolution"] == pytest.approx(240.0 * 473.1723 / 900.0)


_CASES_WORKFLOWS_ROWS__ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _cases_workflows_rows___case(
    workflow: str = "unsteady", *, point: dict | None = None, **overrides
) -> SimCase:
    variables: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "LAST_ITERS_AVG": "10",
    }
    if workflow == "unsteady_rotor":
        variables.update({"RPM": "1200", "ROTOR_AXIS": "X", "BLADES": "1"})
        variables.pop("LAST_ITERS_AVG")
        variables["LAST_REVS_AVG"] = "0.5"
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0} if point is None else point,
        rotors={_CASES_WORKFLOWS_ROWS__ROTOR.alias: _CASES_WORKFLOWS_ROWS__ROTOR}
        if workflow == "unsteady_rotor"
        else {},
    )


class TestCasesWorkflowsRows:
    """P0400-CW-ROWS: the row readers refuse what they cannot read, naming the case and the key.

    0.40.0 items PFS-2097.003, PFS-2097.014, PFS-2093.010, PFS-2095.042,
    PFS-2097.004, PFS-2097.015 and PFS-2093.009: every numeric cell goes through
    the one reader that refuses NaN and infinity, counts are counts, a wall clock's
    unit is all of its trailing letters, and the averaging window is read for its
    value at build rather than only for its presence.
    """

    @staticmethod
    @pytest.mark.parametrize("text", ["nan", "inf", "abc"])
    def test_p0400_cw_rows_a_row_angle_is_read_through_the_finite_reader(text):
        """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): an ALPHA cell off the point is refused by key."""  # noqa: E501
        requirement = "P0400-CW-ROWS"
        case = _cases_workflows_rows___case("steady", point={}, ALPHA=text)
        with pytest.raises(CampaignConfigError, match="'7001' declares ALPHA as") as refusal:
            _angle(case, "alpha")
        assert str(refusal.value), requirement

    @staticmethod
    @pytest.mark.parametrize("text", ["nan", "inf"])
    def test_p0400_cw_rows_a_non_finite_body_rate_is_refused(text):
        """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): a NaN rate compared unequal to 0."""
        requirement = "P0400-CW-ROWS"
        case = _cases_workflows_rows___case("steady", ROLL_RATE=text)
        with pytest.raises(CampaignConfigError, match="not a finite number") as refusal:
            _stated_rate(case, "ROLL_RATE")
        assert str(refusal.value), requirement

    @staticmethod
    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_p0400_cw_rows_a_resolved_angle_is_finite_too(value):
        """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): resolved angles use the same reader."""
        requirement = "P0400-CW-ROWS"
        with pytest.raises(CampaignConfigError, match="ALPHA.*not a finite number") as refusal:
            _angle(_cases_workflows_rows___case("steady", point={"alpha": value}), "alpha")
        assert str(refusal.value), requirement

    @staticmethod
    @pytest.mark.parametrize("text", ["nanh", "infm", "nan h"])
    def test_p0400_cw_rows_a_non_finite_wall_clock_is_refused(text):
        """P0400-CW-ROWS (PFS-2097.014): WALLTIME 'nanh' read as NaN and turned the watchdog on."""
        requirement = "P0400-CW-ROWS"
        with pytest.raises(CampaignConfigError, match="not a finite number") as refusal:
            row_walltime_s(_cases_workflows_rows___case(WALLTIME=text))
        assert str(refusal.value), requirement

    @staticmethod
    @pytest.mark.parametrize(("text", "unit"), [("30min", "min"), ("2hrs", "hrs")])
    def test_p0400_cw_rows_a_wall_clock_unit_is_every_trailing_letter(text, unit):
        """P0400-CW-ROWS (PFS-2093.010): `30min` was told it carries no unit."""
        requirement = "P0400-CW-ROWS"
        with pytest.raises(CampaignConfigError) as raised:
            row_walltime_s(_cases_workflows_rows___case(WALLTIME=text))
        message = str(raised.value)
        assert f"the unit {unit!r} is not one of" in message, (requirement, message)
        assert "no unit" not in message

    @staticmethod
    def test_p0400_cw_rows_a_wall_clock_still_reads_its_four_units():
        """P0400-CW-ROWS (PFS-2093.010), control: the four units and the bare-number refusal hold."""  # noqa: E501
        requirement = "P0400-CW-ROWS"
        assert row_walltime_s(_cases_workflows_rows___case(WALLTIME="4h")) == 4 * 3600.0, (
            requirement
        )
        assert row_walltime_s(_cases_workflows_rows___case(WALLTIME=" 240 m ")) == 240 * 60.0
        assert row_walltime_s(_cases_workflows_rows___case(WALLTIME="1.5d")) == 1.5 * 86400.0
        with pytest.raises(CampaignConfigError, match="no unit"):
            row_walltime_s(_cases_workflows_rows___case(WALLTIME="240"))

    @staticmethod
    def test_p0400_cw_rows_ncpus_is_read_as_every_count_is():
        """P0400-CW-ROWS (PFS-2095.042): NCPUS 4.0 is four processors; 4.5 is refused by key."""
        requirement = "P0400-CW-ROWS"
        assert row_ncpus(_cases_workflows_rows___case(NCPUS="4.0"), None) == 4, requirement
        with pytest.raises(CampaignConfigError, match="NCPUS"):
            row_ncpus(_cases_workflows_rows___case(NCPUS="4.5"), None)

    @staticmethod
    @pytest.mark.parametrize(
        "text",
        [
            "{ADDITIONAL_ITERS=0.5}",
            "{ADDITIONAL_ITERS=2.7}",
            "{ADDITIONAL_ITERS=nan}",
            "{ADDITIONAL_REVS=inf}",
            "{ADDITIONAL_REVS=nan}",
        ],
    )
    def test_p0400_cw_rows_a_restart_count_is_finite_and_a_step_count_whole(text):
        """P0400-CW-ROWS (PFS-2097.004, PFS-2097.015): 0.5 became a 0-step continuation."""
        requirement = "P0400-CW-ROWS"
        with pytest.raises(CampaignConfigError, match="'7001' declares RESTART as") as refusal:
            parse_restart(_cases_workflows_rows___case(RESTART=text))
        assert str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_rows_a_whole_restart_count_still_reads():
        """P0400-CW-ROWS (PFS-2097.004), control: 2.0 more steps are two more steps."""
        requirement = "P0400-CW-ROWS"
        request = parse_restart(_cases_workflows_rows___case(RESTART="{ADDITIONAL_ITERS=2.0}"))
        assert request is not None, requirement
        assert restart_iterations(request, {}) == 2

    @staticmethod
    def test_p0400_cw_rows_additional_revolutions_round_before_the_ceiling():
        """P0400-CW-ROWS (PFS-2097.015): one turn at the recorded step of 11 per turn is 11 steps.

        The record keeps the step as round(360 / 11, 9), a hair under the true
        step, so the unrounded quotient is 11.00000000009 and its ceiling 12.
        """
        requirement = "P0400-CW-ROWS"
        request = parse_restart(_cases_workflows_rows___case(RESTART="{ADDITIONAL_REVS=1}"))
        assert request is not None, requirement
        record = {"export_window": {"step_deg": round(360.0 / 11, 9)}}
        assert restart_iterations(request, record) == 11

    @staticmethod
    @pytest.mark.parametrize(
        ("workflow", "overrides", "named"),
        [
            ("unsteady", {"LAST_ITERS_AVG": "0"}, "LAST_ITERS_AVG"),
            ("unsteady", {"LAST_ITERS_AVG": "abc"}, "LAST_ITERS_AVG"),
            ("unsteady", {"LAST_ITERS_AVG": "-"}, "LAST_ITERS_AVG"),
            ("unsteady", {"LAST_ITERS_AVG": "100.5"}, "LAST_ITERS_AVG"),
            ("unsteady", {"LAST_REVS_AVG": "0.5"}, "both"),
            ("unsteady_rotor", {"LAST_REVS_AVG": "0"}, "LAST_REVS_AVG"),
            ("unsteady_rotor", {"LAST_REVS_AVG": "nan"}, "LAST_REVS_AVG"),
        ],
    )
    def test_p0400_cw_rows_the_averaging_window_is_read_for_its_value_at_build(
        workflow, overrides, named
    ):
        """P0400-CW-ROWS (PFS-2093.009): a zero, unreadable or doubled window planned READY."""
        requirement = "P0400-CW-ROWS"
        case = _cases_workflows_rows___case(workflow, **overrides)
        with pytest.raises(CampaignConfigError, match=named) as refusal:
            _require_the_averaging_window(case, workflow)
        with pytest.raises(CampaignConfigError, match=named):
            build_script(case, Script("26.124"))
        assert str(refusal.value), requirement


def _cases_workflows_steady___points(case, alphas, **point):
    names = [name.replace("{name}", "P") for name in case.pproc.outputs(False)]
    return [
        case.model_copy(
            update={
                "point": {"alpha": alpha, **point},
                "outputs": [name.replace("P", f"P{index}", 1) for name in names],
            }
        )
        for index, alpha in enumerate(alphas)
    ]


def _cases_workflows_steady___built(points) -> Script:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_steady_sweep(points, script)
    return script


class TestCasesWorkflowsSteady:
    """P0400-CW-STEADY: a steady sweep built as one script is built as its points would be.

    0.40.0 items PFS-2104.012 and PFS-2104.041 (the sweep runs build_script's pre-
    and post-build steps, the loads frame of every section block included),
    PFS-2104.043 (a later point whose free stream turns otherwise is refused) and
    PFS-2104.036 with PFS-2104.040 (each point's probes replace the previous
    point's).
    """

    @staticmethod
    def test_p0400_cw_steady_a_sweep_stamps_the_loads_frame_on_every_section_block(tmp_path):
        """P0400-CW-STEADY (PFS-2104.012, PFS-2104.041): the BL product reads it on every block."""
        requirement = "P0400-CW-STEADY"
        case = _cases_workflows_steady___with_pproc(
            _cases_workflows_steady__steady_case(), _cases_workflows_steady___wb_geometry(tmp_path)
        )
        case.pproc.products.boundary_layer_integrals = True
        script = _cases_workflows_steady___built(_cases_workflows_steady___points(case, (0.0, 5.0)))
        assert script.section_blocks, requirement
        for block in script.section_blocks:
            assert block.get("loads_frame_index") == script.loads_frame, block

    @staticmethod
    def test_p0400_cw_steady_a_sweep_refuses_what_build_script_refuses(tmp_path):
        """P0400-CW-STEADY (PFS-2104.012), the pre-build half: the BL dependency check runs."""
        requirement = "P0400-CW-STEADY"
        case = _cases_workflows_steady___with_pproc(
            _cases_workflows_steady__steady_case(), _cases_workflows_steady___wb_geometry(tmp_path)
        )
        case.pproc.products.boundary_layer_integrals = True
        points = [
            point.model_copy(update={"outputs": ["P.txt"]})
            for point in _cases_workflows_steady___points(case, (0, 5))
        ]
        with pytest.raises(
            CampaignConfigError, match="boundary_layer_integrals requires"
        ) as refusal:
            _cases_workflows_steady___built(points)
        assert str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_steady_a_swept_body_rate_is_refused_in_one_script(tmp_path):
        """P0400-CW-STEADY (PFS-2104.043): every point was solved at the first point's rate."""
        requirement = "P0400-CW-STEADY"
        axes = {"roll": "X", "pitch": "Y", "yaw": "Z"}
        reference = ReferenceData(
            area=50.0, length=2.526, moment_point_m=(9.152, 0.0, 0.0), body_axes=axes
        )
        case = _cases_workflows_steady___with_pproc(
            _cases_workflows_steady__steady_case(), _cases_workflows_steady___wb_geometry(tmp_path)
        ).model_copy(update={"reference": reference})
        points = _cases_workflows_steady___points(case, (0.0, 0.0), pitch_rate=2.0)
        points[1] = points[1].model_copy(update={"point": {"alpha": 0.0, "pitch_rate": 4.0}})
        with pytest.raises(CampaignConfigError, match="free stream differently") as refusal:
            _cases_workflows_steady___built(points)
        _cases_workflows_steady___built(
            _cases_workflows_steady___points(case, (0.0, 5.0), pitch_rate=2.0)
        )  # one rate: one free stream, builds
        assert str(refusal.value), requirement

    @staticmethod
    def test_p0400_cw_steady_each_points_probes_replace_the_last_points(tmp_path):
        """P0400-CW-STEADY (PFS-2104.036, PFS-2104.040): one creation per point, one ledger."""
        requirement = "P0400-CW-STEADY"
        spec = _cases_workflows_steady___spec(_cases_workflows_steady___entry(None))
        case = _cases_workflows_steady___with_pproc(
            _cases_workflows_steady__steady_case(),
            _cases_workflows_steady___wb_geometry(tmp_path),
            pproc=spec,
        )
        script = _cases_workflows_steady___built(
            _cases_workflows_steady___points(case, (0.0, 2.0, 4.0))
        )
        lines = script.render().splitlines()
        starts = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
        assert len(starts) == 3, requirement
        bounds = [*starts, len(lines)]
        for here, there in zip(bounds, bounds[1:], strict=False):
            chunk = lines[here:there]
            heads = [line.split()[0] for line in chunk if line[:1].isalpha()]
            assert heads.count("NEW_PROBE_LINE") == 1, heads
            assert heads.count("DELETE_PROBE_POINTS") == 1, heads
            assert heads.index("DELETE_PROBE_POINTS") < heads.index("NEW_PROBE_LINE")
        # One line of three and a 2 by 2 rectangle: seven points, once.
        assert len(script.probe_points) == 7, script.probe_points


_CASES_WORKFLOWS_TIMING__ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _cases_workflows_timing___case(workflow: str, **overrides: str | None) -> SimCase:
    variables: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "LAST_ITERS_AVG": "10",
    }
    if workflow == "unsteady_rotor":
        variables.update({"RPM": "1200", "ROTOR_AXIS": "X", "BLADES": "1"})
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        rotors={_CASES_WORKFLOWS_TIMING__ROTOR.alias: _CASES_WORKFLOWS_TIMING__ROTOR}
        if workflow == "unsteady_rotor"
        else {},
    )


class TestCasesWorkflowsTiming:
    """P0400-CW-TIMING: the explicit clock of a rotor row, at rest and out of bounds.

    PFS-2095.008 and PFS-2097.005 of the 0.40.0 release: a stationary rotor
    stated with the explicit clock divided by zero, and a zero or negative
    explicit step or count was emitted to the solver.
    """

    @staticmethod
    def test_p0400_cw_timing_a_rotor_at_rest_on_the_explicit_clock_has_no_revolution():
        """P0400-CW-TIMING (PFS-2095.008): RPM 0 with DELTA_TIME and TIME_ITERATIONS builds.

        The stationary-rotor refusal tells the user to write exactly this clock,
        and before the fix it raised a bare ZeroDivisionError from the property.
        """
        requirement = "P0400-CW-TIMING"
        case = _cases_workflows_timing___case("unsteady_rotor", RPM="0")
        stepping = rotor_time_stepping(case)
        assert stepping.rpm == 0.0, requirement
        assert stepping.steps_per_revolution is None
        windows = reduction_windows(case)
        assert windows["steps_per_revolution"] is None
        assert windows["time_iterations"] == 720
        script = Script("26.124")
        build_script(case, script)
        assert "SET_SOLVER_UNSTEADY" in script.render()

    @staticmethod
    @pytest.mark.parametrize("workflow", ["unsteady_rotor", "unsteady"])
    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("DELTA_TIME", "0"),
            ("DELTA_TIME", "-0.01"),
            ("TIME_ITERATIONS", "0"),
            ("TIME_ITERATIONS", "-3"),
        ],
    )
    def test_p0400_cw_timing_a_non_positive_explicit_clock_is_refused_by_name(workflow, key, value):
        """P0400-CW-TIMING (PFS-2097.005): both explicit branches bound the pair, naming the key."""
        requirement = "P0400-CW-TIMING"
        case = _cases_workflows_timing___case(workflow, **{key: value})
        stepping = rotor_time_stepping if workflow == "unsteady_rotor" else unsteady_time_stepping
        with pytest.raises(CampaignConfigError, match=f"'7001' declares {key} as") as refusal:
            stepping(case)
        with pytest.raises(CampaignConfigError, match=key):
            build_script(case, Script("26.124"))
        assert str(refusal.value), requirement


class TestCasesWorkflowsVelocity:
    """A resolved flight condition cannot silently ignore a VELOCITY cell."""

    @staticmethod
    def test_p0400_cw_velocity_a_matrix_row_warns_about_its_ignored_cell(tmp_path):
        """P0400-CW-VELOCITY (PFS-2093.001): TASmps/MACH supplies the planned velocity."""
        requirement = "P0400-CW-VELOCITY"
        workspace, matrix = _cases_workflows_velocity___matrix(
            tmp_path,
            condition="TASmps:50.0, REmi:2.3, ALPHA:sweep",
            values="0.0",
            cell="VELOCITY: 30.0",
        )
        with pytest.warns(UserWarning, match="VELOCITY.*TASmps/MACH"):
            plan = _cases_workflows_velocity___plan(workspace, matrix)
        assert not plan.blocked, (requirement, plan.summary())


def _cases_workflows_windows___fractional_row():
    from tests.tier1_offline.test_regression_workflow_emission import (
        _cases_workflows_reductions___row as _row,
    )

    case = _row(DELTA_THETA="10", REVOLUTIONS="4", LAST_REVS_AVG="4")
    block = case.rotors["ROTOR"].model_copy(
        update={"families_blades": [f"Blade{number}" for number in range(1, 8)]}
    )
    return case.model_copy(update={"rotors": {"ROTOR": block}})


class TestCasesWorkflowsWindows:
    """Regression evidence for public and per-rotor averaging windows."""

    @staticmethod
    def test_p0400_cw_windows_each_rotors_passages_use_its_own_span():
        """P0400-CW-WINDOWS (PFS-2088.011): both passage products use that rotor's turns."""
        requirement = "P0400-CW-WINDOWS"
        case = _cases_workflows_windows__transition_case()
        case.variables["LAST_REVS_AVG"] = "1"
        plan = reduction_windows(case)
        assert plan is not None, requirement
        pusher = plan["rotors"]["PUSHER"]
        span = pusher["per_blade"]["windows"][0]
        windows = pusher["phase_locked"]["windows"]
        assert windows[0][0] == span[0], requirement
        assert windows[-1][1] <= span[1]
        assert span == [54, 720]

    @staticmethod
    def test_p0400_cw_windows_public_window_clamps_like_the_live_window():
        """P0400-CW-WINDOWS (PFS-2098.002): the public window agrees with recorded reductions."""
        requirement = "P0400-CW-WINDOWS"
        window = export_window(steps=1000, time_iterations=720)
        assert window.window_steps() == (1, 720), requirement
        assert window.steps == 720
        assert window.stated_value == 1000.0

    @staticmethod
    def test_p0400_cw_windows_each_rotors_legacy_fallback_is_its_own_turn():
        """P0400-CW-WINDOWS (PFS-2088.011): an absent averaging key keeps one physical turn."""
        requirement = "P0400-CW-WINDOWS"
        plan = reduction_windows(_cases_workflows_windows__transition_case())
        pusher = plan["rotors"]["PUSHER"]
        assert pusher["per_blade"]["windows"] == [[54, 720]], requirement
        assert pusher["phase_locked"]["windows"][0][0] == 54

    @staticmethod
    def test_p0400_cw_windows_the_public_reduction_plan_clamps_too():
        """P0400-CW-WINDOWS (PFS-2098.002): the public plan accepts the live path's window."""
        requirement = "P0400-CW-WINDOWS"
        from tests.tier1_offline.test_regression_workflow_emission import (
            _cases_workflows_reductions___row as _row,
        )

        case = _row(LAST_REVS_AVG="100")
        assert reduction_plan(case).window.window_steps() == (1, 288), requirement

    @staticmethod
    def test_p0400_cw_windows_a_public_window_uses_the_case_clock():
        """P0400-CW-WINDOWS (PFS-2098.002): a non-clock rotor cannot supply the row's clock."""
        requirement = "P0400-CW-WINDOWS"
        case = _cases_workflows_windows__transition_case()
        case.variables.update({"LAST_REVS_AVG": "2"})
        public = ExportWindow.from_case(case)
        live = reduction_windows(case)
        assert public.window_steps() == tuple(live["time_average"]["windows"][0]), requirement
        assert public.steps_per_revolution == pytest.approx(live["steps_per_revolution"])

    @staticmethod
    def test_p0400_cw_windows_fractional_passages_do_not_accumulate_rounding():
        """P0400-CW-WINDOWS (PFS-2081.19): passage boundaries follow physical turns."""
        requirement = "P0400-CW-WINDOWS"
        case = _cases_workflows_windows___fractional_row()
        # Seven passages complete one 36-step turn, without rounding each to five.
        plan = reduction_windows(case)
        cut = plan["phase_locked"]["windows"]
        assert cut[:4] == [[1, 5], [6, 10], [11, 15], [16, 20]], requirement
        assert cut[6][1] == 36
        assert cut[13][1] == 72
        assert cut[20][1] == 108

    @staticmethod
    def test_p0400_cw_windows_post_replanning_keeps_the_rotors_own_span():
        """P0400-CW-WINDOWS (PFS-2088.011): post must not overwrite the rotor's span."""
        requirement = "P0400-CW-WINDOWS"
        case = _cases_workflows_windows__transition_case()
        case.variables["LAST_REVS_AVG"] = "1"
        plan = reduction_windows(case)
        fresh = recorded_windows.replan(plan, case.variables)
        pusher = fresh["rotors"]["PUSHER"]
        assert pusher["phase_locked"]["windows"][0][0] == 54, requirement
        assert pusher["per_blade"]["windows"] == [[54, 720]]

    @staticmethod
    def test_p0400_cw_windows_post_replanning_preserves_fractional_passages():
        """P0400-CW-WINDOWS (PFS-2081.19): replanning cannot round the passage period."""
        requirement = "P0400-CW-WINDOWS"
        case = _cases_workflows_windows___fractional_row()
        fresh = recorded_windows.replan(reduction_windows(case), case.variables)
        assert fresh["phase_locked"]["windows"][6][1] == 36, requirement
        assert fresh["phase_locked"]["windows"][13][1] == 72


if TYPE_CHECKING:
    from pyflightstream.cases.sixdof import SixDofSpec


_GAPS_RT_SIXDOF__GOLDENS = Path(__file__).parent / "goldens"


_GAPS_RT_SIXDOF__BUILD = "26.124"


_GAPS_RT_SIXDOF__FREE_TO_PITCH = """
families = ["W", "B"]
frame = "MRP"

[mass]
mass_kg = 4.2
inertia_kg_m2 = [0.05, 0.31, 0.33, 0.0, 0.0, 0.0]

[gravity]
vector_reference_m_per_s2 = [0.0, 0.0, -9.80665]

[initial]
velocity_body_m_per_s = [0.0, 0.0, 0.0]
angular_velocity_body_deg_per_s = [0.0, 0.0, 0.0]

[free]
q = true

[[forces]]
kind = "external"
point_body_m = [0.25, 0.0, 0.0]
force_body_n = [0.0, 0.0, -40.0]
start_s = 0.0
duration_s = 0.01

[[forces]]
kind = "spring"
point_body_m = [0.0, 0.0, 0.0]
axis_body = [0.0, 0.0, 1.0]
free_length_m = 0.40
solid_length_m = 0.05
initial_length_m = 0.30
rate_n_per_m = 800.0

[[forces]]
kind = "custom"
type = "FORCE_VS_TIME"
file = "pulse_force.txt"
"""


_GAPS_RT_SIXDOF__PULSE = "0.000 0.0\n0.010 0.0\n0.015 -20.0\n0.020 0.0\n1.000 0.0\n"


def _gaps_rt_sixdof___inputs(
    tmp_path: Path, text: str = _GAPS_RT_SIXDOF__FREE_TO_PITCH, *, code: str = "d001"
) -> Path:
    inputs = tmp_path / "inputs"
    folder = inputs / "sixdof"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{code}.toml").write_text(text, encoding="utf-8")
    (folder / "pulse_force.txt").write_text(_GAPS_RT_SIXDOF__PULSE, encoding="utf-8")
    return inputs


def _gaps_rt_sixdof___resolved(
    tmp_path: Path, text: str = _GAPS_RT_SIXDOF__FREE_TO_PITCH, **variables: str
):
    from pyflightstream.workspace.sixdof_setup import resolve_row_sixdof

    cell = {"SIXDOF": "d001", **variables}
    return resolve_row_sixdof(
        _gaps_rt_sixdof___inputs(tmp_path, text), cell, workflow="unsteady", pol="9401"
    )


def _gaps_rt_sixdof___verified(spec: SixDofSpec) -> CommandRegistry:
    """The committed database with every command of ``spec`` recorded verified on BUILD."""
    from pyflightstream.cases.workflows import sixdof_commands

    return _gaps_rt_sixdof__registry_with(
        sixdof_commands(spec), _GAPS_RT_SIXDOF__BUILD, Status.VERIFIED
    )


def _gaps_rt_sixdof___script(
    tmp_path: Path, resolved, registry: CommandRegistry | None = None
) -> Script:
    from pyflightstream.cases.workflows import build_script

    case = _gaps_rt_sixdof___with_pproc(
        _gaps_rt_sixdof___case_for("unsteady"), _gaps_rt_sixdof___wb_geometry(tmp_path), pproc=None
    )
    case = case.model_copy(
        update={"sixdof": resolved.spec, "sixdof_provenance": resolved.provenance()}
    )
    from pyflightstream.cases.workflows._pproc import row_outputs

    names = [name.replace("{name}", "P") for name in row_outputs(case, "unsteady")]
    case = case.model_copy(update={"outputs": names})
    script = Script(
        _GAPS_RT_SIXDOF__BUILD,
        registry if registry is not None else _gaps_rt_sixdof___verified(resolved.spec),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script


def _gaps_rt_sixdof___block(script: Script) -> str:
    lines = script.render().splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_MOTION 6DOF"))
    last = next(i for i, line in enumerate(lines) if line.startswith("SET_6DOF_MOTION_SYMMETRY"))
    return "\n".join(lines[first : last + 1]) + "\n"


def _gaps_rt_sixdof___replace(old: str, new: str) -> str:
    assert old in _GAPS_RT_SIXDOF__FREE_TO_PITCH
    return _GAPS_RT_SIXDOF__FREE_TO_PITCH.replace(old, new)


class TestGapsRtSixdof:
    """P0400-SIXDOF (FR-461): the SIXDOF row key frees a body to move under its loads.

    The free-to-pitch input is resolved and its motion block is held to a golden
    (FR-1084, FR-1085), built against the committed database with the 6DOF commands recorded
    verified on the build; the evidence gate refuses a build recording one of them
    documented (R-GATE); every
    refusal of FR-1086 and FR-1087 is asserted by its message; the provenance and the custom
    force file are staged with the script (FR-1088).
    """

    @staticmethod
    def test_p0400_sixdof_free_to_pitch_golden(tmp_path):
        """P0400-SIXDOF (FR-1084, FR-1085): the motion block, before the solver is initialised."""
        resolved = _gaps_rt_sixdof___resolved(tmp_path)
        assert resolved is not None
        script = _gaps_rt_sixdof___script(tmp_path, resolved)
        text = script.render()
        assert text.index("CREATE_NEW_MOTION 6DOF") < text.index("INITIALIZE_SOLVER")
        assert _gaps_rt_sixdof___block(script) == (
            _GAPS_RT_SIXDOF__GOLDENS / "p0400_sixdof_free_to_pitch.txt"
        ).read_text(encoding="utf-8")

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-6DOFEXPORT")])
    def test_p0400_6dofexport_the_trajectory_is_exported_after_the_march(tmp_path):
        """P0400-6DOFEXPORT (FR-1089): the export follows the march, never the motion's setup."""
        resolved = _gaps_rt_sixdof___resolved(tmp_path)
        assert resolved is not None
        lines = _gaps_rt_sixdof___script(tmp_path, resolved).render().splitlines()
        (export,) = [i for i, line in enumerate(lines) if line.startswith("EXPORT_6DOF_TRAJECTORY")]
        march = next(i for i, line in enumerate(lines) if line.startswith("START_SOLVER"))
        initialise = next(i for i, line in enumerate(lines) if line.startswith("INITIALIZE_SOLVER"))
        assert initialise < march < export
        assert lines[export] == "EXPORT_6DOF_TRAJECTORY 1"
        assert lines[export + 1] == "P_trajectory_6dof.txt"

    @staticmethod
    def test_p0400_sixdof_stages_its_provenance_and_force_file(tmp_path):
        """P0400-SIXDOF (FR-1088): the provenance and the custom force file go with the script."""
        from pyflightstream.cases.workflows._sixdof import SIXDOF_PROVENANCE_FILE

        resolved = _gaps_rt_sixdof___resolved(tmp_path)
        assert resolved is not None
        staged = _gaps_rt_sixdof___script(tmp_path, resolved).pending_input_files
        source = tmp_path / "inputs" / "sixdof" / "pulse_force.txt"
        assert staged["pulse_force.txt"] == source.read_bytes()
        record = json.loads(staged[SIXDOF_PROVENANCE_FILE])
        assert record["source_sha256"] == resolved.source_sha256
        assert set(record["files_sha256"]) == {"pulse_force.txt"}

    @staticmethod
    def test_p0400_sixdof_gate_refuses_an_unprobed_build(tmp_path):
        """P0400-SIXDOF (FR-461 R-GATE): an unverified 6DOF command is refused by name."""
        resolved = _gaps_rt_sixdof___resolved(tmp_path)
        assert resolved is not None
        documented = _gaps_rt_sixdof__registry_with(
            ["SET_MOTION_MASS_PROPERTIES"],
            _GAPS_RT_SIXDOF__BUILD,
            Status.DOCUMENTED,
            base=_gaps_rt_sixdof___verified(resolved.spec),
        )
        with pytest.raises(CampaignConfigError, match="SET_MOTION_MASS_PROPERTIES.*6DOF probes"):
            _gaps_rt_sixdof___script(tmp_path, resolved, documented)

    @staticmethod
    @pytest.mark.parametrize(
        ("text", "words"),
        [
            (_gaps_rt_sixdof___replace("mass_kg = 4.2", "mass_kg = 0.0"), "above zero"),
            (
                _gaps_rt_sixdof___replace(
                    "[0.05, 0.31, 0.33, 0.0, 0.0, 0.0]", "[0.05, 0.31, 0.33, 0.2, 0.0, 0.0]"
                ),
                "positive definite",
            ),
            (_gaps_rt_sixdof___replace("q = true", "q = false"), "locks every freedom"),
            (_gaps_rt_sixdof___replace("duration_s = 0.01", "duration_s = 0.0"), "duration"),
            (_gaps_rt_sixdof___replace("solid_length_m = 0.05", "solid_length_m = 0.5"), "exceeds"),
            (
                _gaps_rt_sixdof___replace('file = "pulse_force.txt"', 'file = "missing.txt"'),
                "missing.txt",
            ),
            (
                _gaps_rt_sixdof___replace("[gravity]", "[gravity]\ng = 9.8"),
                "Extra inputs are not permitted",
            ),
        ],
    )
    def test_p0400_sixdof_input_refusals(tmp_path, text, words):
        """P0400-SIXDOF (FR-1086): each refusal names its key."""
        from pyflightstream.workspace.sixdof_setup import SixDofSetupError

        with pytest.raises(SixDofSetupError, match=words):
            _gaps_rt_sixdof___resolved(tmp_path, text)

    @staticmethod
    def test_p0400_sixdof_mirror_refuses_a_lateral_freedom(tmp_path):
        """P0400-SIXDOF (FR-1086): a mirrored half model frees no lateral freedom."""
        from pyflightstream.workspace.sixdof_setup import SixDofSetupError

        text = _gaps_rt_sixdof___replace("q = true", "q = true\nv = true")
        with pytest.raises(SixDofSetupError, match="MIRROR"):
            _gaps_rt_sixdof___resolved(tmp_path, text, SYMMETRY="MIRROR")
        assert (
            _gaps_rt_sixdof___resolved(tmp_path, _GAPS_RT_SIXDOF__FREE_TO_PITCH, SYMMETRY="MIRROR")
            is not None
        )

    @staticmethod
    @pytest.mark.parametrize("workflow", ["steady", "qsteady_rotor", "unsteady_rotor"])
    def test_p0400_sixdof_refused_off_the_unsteady_run_type(tmp_path, workflow):
        """P0400-SIXDOF (FR-1087): a free body needs the march, and no rotor turning."""
        from pyflightstream.workspace.sixdof_setup import SixDofSetupError, resolve_row_sixdof

        with pytest.raises(SixDofSetupError, match="time march"):
            resolve_row_sixdof(
                _gaps_rt_sixdof___inputs(tmp_path), {"SIXDOF": "d001"}, workflow=workflow
            )

    @staticmethod
    def test_p0400_sixdof_refused_with_fsi_and_a_bad_code(tmp_path):
        """P0400-SIXDOF (FR-1086, FR-1087): SIXDOF with FSI, and a code that is not d-prefixed."""
        from pyflightstream.workspace.sixdof_setup import SixDofSetupError, resolve_row_sixdof

        with pytest.raises(SixDofSetupError, match="FSI"):
            resolve_row_sixdof(
                _gaps_rt_sixdof___inputs(tmp_path),
                {"SIXDOF": "d001", "FSI": "f001"},
                workflow="unsteady",
            )
        with pytest.raises(SixDofSetupError, match="d-prefixed"):
            resolve_row_sixdof(
                _gaps_rt_sixdof___inputs(tmp_path), {"SIXDOF": "x001"}, workflow="unsteady"
            )
        assert (
            resolve_row_sixdof(_gaps_rt_sixdof___inputs(tmp_path), {}, workflow="unsteady") is None
        )

    @staticmethod
    def test_p0400_sixdof_frame_the_run_does_not_create(tmp_path):
        """P0400-SIXDOF (FR-1087): a body frame the run does not create is refused."""
        resolved = _gaps_rt_sixdof___resolved(
            tmp_path, _gaps_rt_sixdof___replace('frame = "MRP"', 'frame = "PIVOT"')
        )
        assert resolved is not None
        with pytest.raises(CampaignConfigError, match="PIVOT"):
            _gaps_rt_sixdof___script(tmp_path, resolved)

    @staticmethod
    def test_p0400_sixdof_rotor_run_type_does_not_register_the_key():
        """P0400-SIXDOF (FR-1087): the key is the unsteady run type's alone."""
        from pyflightstream.cases.workflows import WORKFLOWS

        assert "SIXDOF" in WORKFLOWS["unsteady"].keys
        for name in ("steady", "unsteady_rotor", "qsteady_rotor"):
            assert "SIXDOF" not in WORKFLOWS[name].keys

    @staticmethod
    def test_p0400_sixdof_active_lines_in_solver_order():
        """P0400-SIXDOF (FR-1085): six lines, U V W P Q R, each named once."""
        from pyflightstream.cases.sixdof import SixDofSpec

        spec = SixDofSpec.model_validate(
            {
                "families": ["W"],
                "frame": "MRP",
                "mass": {"mass_kg": 1.0, "inertia_kg_m2": [1, 1, 1, 0, 0, 0]},
                "free": {"q": True, "w": True},
            }
        )
        assert spec.active_lines() == [
            "U DISABLE",
            "V DISABLE",
            "W ENABLE",
            "P DISABLE",
            "Q ENABLE",
            "R DISABLE",
        ]


_GAPS_RT_STREAMLINES__GOLDENS = Path(__file__).parent / "goldens"


_GAPS_RT_STREAMLINES__FIXTURES = Path(__file__).parent / "fixtures"


_GAPS_RT_STREAMLINES__BUILD = "26.124"


_GAPS_RT_STREAMLINES___TABLE: dict[str, object] = {
    "surface": True,
    "direction": "downstream",
    "length_m": 6.0,
    "lines": [
        {"frame": "REFERENCE", "start": [-0.5, 1.9, -0.1], "end": [-0.5, 1.9, 0.1], "count": 20}
    ],
    "tubes": [
        {
            "frame": "MRP",
            "axis": "X",
            "origin": [-0.3, 0.0, 0.0],
            "radius": 0.9,
            "radial": 4,
            "circular": 12,
        }
    ],
}


def _gaps_rt_streamlines___spec(**table: object) -> PprocSpec:
    return PprocSpec.model_validate(
        {"groups": {"1": "all"}, "streamlines": table or _GAPS_RT_STREAMLINES___TABLE}
    )


def _gaps_rt_streamlines___verified(spec: PprocSpec) -> CommandRegistry:
    """The committed database with every command of ``spec`` recorded verified on BUILD."""
    from pyflightstream.cases.workflows import streamline_commands

    assert spec.streamlines is not None
    commands = streamline_commands(spec.streamlines, reopened=True)
    return _gaps_rt_streamlines__registry_with(
        commands, _GAPS_RT_STREAMLINES__BUILD, Status.VERIFIED
    )


def _gaps_rt_streamlines___script(
    tmp_path: Path, run_type: str, spec: PprocSpec, registry: CommandRegistry | None = None
) -> Script:
    """Build one row of ``run_type`` naming ``spec``, its outputs as the pproc declares them."""
    from pyflightstream.cases.workflows import build_script

    base = (
        _gaps_rt_streamlines__steady_case()
        if run_type == "steady"
        else _gaps_rt_streamlines___case_for(run_type)
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _gaps_rt_streamlines___with_pproc(
        base, _gaps_rt_streamlines___wb_geometry(tmp_path), pproc=spec
    )
    names = [name.replace("{name}", "P") for name in spec.outputs(run_type != "steady")]
    case = case.model_copy(update={"outputs": names})
    script = Script(
        _GAPS_RT_STREAMLINES__BUILD,
        registry if registry is not None else _gaps_rt_streamlines___verified(spec),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script


def _gaps_rt_streamlines___tail(script: Script) -> str:
    """The lines from the first streamline command to the end of the script."""
    lines = script.render().splitlines()
    first = next(i for i, line in enumerate(lines) if "STREAMLINE" in line or "STREAMTUBE" in line)
    return "\n".join(lines[first:]) + "\n"


class TestGapsRtStreamlines:
    """P0400-STREAMLINES (FR-460): a pproc's [streamlines] table traces streamlines on every point.

    The table is read and refused at reading (FR-1080); a steady and an unsteady row
    emit the trace after the solve and before the exports, against goldens (FR-1077,
    FR-1078), with the evidence gate exercised both ways (R-GATE); the plan states the
    count (FR-1079); the rows FR-1081 names are refused; the additional extraction deletes
    first (FR-1082); and the post writes the VTK polylines of the observed 26.123
    export (FR-1083).

    THE GATE. The streamline commands were recorded ``documented`` and unprobed on
    26.124 when the route was written, so a row reaching them is refused at plan
    (R-GATE). The emission tests build against the committed database with the
    streamline commands recorded verified on the build (:func:`_verified`), so they
    run the real emission path before and after the licensed probes, and the
    refusal test against one with a command recorded documented.
    """

    @staticmethod
    # --------------------------------------------------------------------------- FR-1080, reading
    @pytest.mark.parametrize(
        ("table", "words"),
        [
            ({"surface": True, "length_m": 1.0, "unrestricted": True}, "alternatives"),
            ({"surface": False}, "traces nothing"),
            ({"surface": True, "direction": "upstream"}, "apply to off-body"),
            (
                {"lines": [{"start": [0, 0, 0], "end": [1, 0, 0], "count": 1}]},
                "NEW_OFF_BODY_STREAMLINE",
            ),
            ({"lines": [{"start": [0, 0, 0], "end": [0, 0, 0], "count": 3}]}, "two distinct"),
            ({"surface": True, "colour": "red"}, "colour"),
        ],
    )
    def test_p0400_streamlines_reading_refuses_by_key(table, words):
        """P0400-STREAMLINES (FR-1080): each refusal names its key or the broken single seed."""
        with pytest.raises(ValidationError, match=words):
            PprocSpec.model_validate({"streamlines": table})

    @staticmethod
    def test_p0400_streamlines_outputs_and_count():
        """P0400-STREAMLINES (FR-1078, FR-1079): the two export names and the count of 20 + 4 *
        12.
        """
        spec = _gaps_rt_streamlines___spec()
        names = spec.outputs(False)
        assert "{name}_sls.txt" in names and "{name}_slo.txt" in names
        assert spec.streamlines is not None and spec.streamlines.off_body_count() == 68
        surface_only = _gaps_rt_streamlines___spec(surface=True)
        assert "{name}_slo.txt" not in surface_only.outputs(False)
        assert "{name}_sls.txt" not in PprocSpec().outputs(False)

    @staticmethod
    def test_p0400_streamlines_exports_cannot_name_them():
        """P0400-STREAMLINES (FR-1078): [exports] cannot switch a trace on or off."""
        with pytest.raises(ValidationError, match=r"\[streamlines\] table"):
            PprocSpec.model_validate({"exports": {"streamlines_off_body": True}})

    @staticmethod
    # --------------------------------------------------------------------------- FR-1077,
    # FR-1078, R-GATE
    @pytest.mark.parametrize("run_type", ["steady", "unsteady"])
    def test_p0400_streamlines_golden(tmp_path, run_type):
        """P0400-STREAMLINES (FR-1077, FR-1078): the trace after the solve, before the exports."""
        spec = _gaps_rt_streamlines___spec()
        script = _gaps_rt_streamlines___script(tmp_path, run_type, spec)
        heads = [line.split()[0] for line in script.render().splitlines() if line[:1].isalpha()]
        assert heads.index("START_SOLVER") < heads.index("GENERATE_ALL_SURFACE_STREAMLINES")
        assert heads.index("GENERATE_ALL_OFF_BODY_STREAMLINES") < heads.index(
            "EXPORT_ALL_OFF_BODY_STREAMLINES"
        )
        assert "DELETE_ALL_SURFACE_STREAMLINES" not in heads, "a fresh script has nothing to delete"
        golden = _GAPS_RT_STREAMLINES__GOLDENS / f"p0400_streamlines_{run_type}.txt"
        assert _gaps_rt_streamlines___tail(script) == golden.read_text(encoding="utf-8")

    @staticmethod
    def test_p0400_streamlines_gate_refuses_an_unprobed_build(tmp_path):
        """P0400-STREAMLINES (FR-460 R-GATE): an unverified command is refused by name at plan."""
        spec = _gaps_rt_streamlines___spec()
        documented = _gaps_rt_streamlines__registry_with(
            ["NEW_OFF_BODY_STREAMTUBE"],
            _GAPS_RT_STREAMLINES__BUILD,
            Status.DOCUMENTED,
            base=_gaps_rt_streamlines___verified(spec),
        )
        with pytest.raises(CampaignConfigError, match="NEW_OFF_BODY_STREAMTUBE.*probe"):
            _gaps_rt_streamlines___script(tmp_path, "steady", spec, documented)

    @staticmethod
    def test_p0400_streamlines_gate_reads_the_database(tmp_path):
        """P0400-STREAMLINES (FR-460 R-GATE): the predicate reads the build's recorded status."""
        from pyflightstream.cases.workflows import _gap_evidence

        script = Script(_GAPS_RT_STREAMLINES__BUILD)
        assert _gap_evidence.command_verified(script, "NEW_STREAMLINE_DISTRIBUTION")
        assert not _gap_evidence.command_verified(script, "NEW_OFF_BODY_STREAMLINE")
        assert not _gap_evidence.command_verified(script, "NO_SUCH_COMMAND")

    @staticmethod
    def test_p0400_streamlines_plan_count(tmp_path):
        """P0400-STREAMLINES (FR-1079): the plan's count is the pproc's off-body count."""
        from pyflightstream.cases.workflows import streamline_count

        case = _gaps_rt_streamlines___with_pproc(
            _gaps_rt_streamlines__steady_case(),
            _gaps_rt_streamlines___wb_geometry(tmp_path),
            pproc=_gaps_rt_streamlines___spec(),
        )
        assert streamline_count(case) == 68
        assert streamline_count(_gaps_rt_streamlines__steady_case()) == 0

    @staticmethod
    # --------------------------------------------------------------------------- FR-1081
    def test_p0400_streamlines_qsteady_rotor_refuses_off_body_names_the_frame():
        """P0400-STREAMLINES (FR-1081): off-body lines on qsteady_rotor name the rotor-fixed frame."""  # noqa: E501
        from pyflightstream.cases.workflows._streamlines import (
            refuse_streamlines_where_they_cannot_run,
        )

        spec = _gaps_rt_streamlines___spec()
        assert spec.streamlines is not None
        case = _gaps_rt_streamlines___case_for("qsteady_rotor").model_copy(
            update={"pproc": spec, "pproc_id": "p9"}
        )
        with pytest.raises(CampaignConfigError, match="rotor-fixed frame"):
            refuse_streamlines_where_they_cannot_run(case, spec.streamlines)
        surface = _gaps_rt_streamlines___spec(surface=True)
        assert surface.streamlines is not None
        refuse_streamlines_where_they_cannot_run(case, surface.streamlines)

    @staticmethod
    def test_p0400_streamlines_frame_the_run_does_not_create(tmp_path):
        """P0400-STREAMLINES (FR-1081): a frame the run does not create is refused."""
        table = {
            "lines": [{"frame": "NOWHERE", "start": [0, 0, 0], "end": [1, 0, 0], "count": 2}],
        }
        spec = _gaps_rt_streamlines___spec(**table)
        with pytest.raises(CampaignConfigError, match="NOWHERE"):
            _gaps_rt_streamlines___script(tmp_path, "steady", spec)

    @staticmethod
    # --------------------------------------------------------------------------- FR-1082
    def test_p0400_streamlines_reopened_deletes_first():
        """P0400-STREAMLINES (FR-1082): an extraction deletes what the saved simulation carries."""  # noqa: E501
        from pyflightstream.cases.workflows import streamline_commands

        spec = _gaps_rt_streamlines___spec()
        assert spec.streamlines is not None
        commands = streamline_commands(spec.streamlines, reopened=True)
        assert commands[:2] == ["DELETE_ALL_SURFACE_STREAMLINES", "DELETE_ALL_OFF_BODY_STREAMLINES"]
        assert "DELETE_ALL_SURFACE_STREAMLINES" not in streamline_commands(spec.streamlines)

    @staticmethod
    def test_p0400_streamlines_additional_outputs():
        """P0400-STREAMLINES (FR-1082): an additional pproc's extraction declares the traces."""
        from pyflightstream.cases.workflows._additional import (
            additional_outputs,
            refuse_what_a_saved_point_cannot_give,
        )

        spec = _gaps_rt_streamlines___spec()
        refuse_what_a_saved_point_cannot_give(spec, pproc_id="p9", where="row")
        names = additional_outputs(spec, stem="P", unsteady=False)
        assert "P_sls.txt" in names and "P_slo.txt" in names

    @staticmethod
    # --------------------------------------------------------------------------- FR-1083
    def test_p0400_streamlines_vtk_of_the_observed_export(tmp_path):
        """P0400-STREAMLINES (FR-1083): three polylines of thirty points, with the variables."""
        from pyflightstream.post.streamlines import (
            render_streamlines_vtk,
            write_streamline_products,
        )
        from pyflightstream.results import parse_off_body_streamlines

        source = tmp_path / "P_slo.txt"
        source.write_bytes(
            (_GAPS_RT_STREAMLINES__FIXTURES / "off_body_streamlines_26.123.txt").read_bytes()
        )
        outcomes = write_streamline_products(
            {"streamlines_off_body": source, "streamlines_surface": tmp_path / "P_sls.txt"},
            tmp_path / "post",
            "P",
        )
        written = outcomes["P_off_body.vtk"]
        assert isinstance(written, Path)
        text = written.read_text(encoding="utf-8")
        report = parse_off_body_streamlines(source.read_text(encoding="utf-8"))
        total = sum(line.points for line in report.streamlines)
        assert f"POINTS {total} double" in text
        assert f"LINES {report.count} {total + report.count}" in text
        for name in (
            "SCALARS Mach",
            "SCALARS Cp_ref",
            "SCALARS vtot",
            "SCALARS Cp",
            "VECTORS velocity",
        ):
            assert name in text
        assert "not yet measured" in str(outcomes["P_surface.vtk"])
        first = report.streamlines[0].values[0]
        assert f"{float(first[0])!r} {float(first[1])!r} {float(first[2])!r}" in text
        assert render_streamlines_vtk(report, title="t").startswith("# vtk DataFile Version 3.0")

    @staticmethod
    def test_p0400_streamlines_vtk_off_writes_nothing(tmp_path):
        """P0400-STREAMLINES (FR-1083): vtk = false writes no product."""
        from pyflightstream.post.streamlines import write_streamline_products

        assert write_streamline_products({}, tmp_path, "P", vtk=False) == {}


_INTEGFIX_BLADES___ONE_FAMILY = RotorBlock(
    alias="ROTOR",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="X",
    diameter_m=1.0,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _integfix_blades___row(**stated: str) -> SimCase:
    variables = {"WORKFLOW": "unsteady_rotor", "ROTOR_AXIS": "X", "RPM": "600", **stated}
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        variables=variables,
        point={"alpha": 0.0},
        rotors={"ROTOR": _INTEGFIX_BLADES___ONE_FAMILY},
    )


class TestIntegfixBlades:
    """P0400-INTEGFIX-BLADES: a one-blade sector stated as periodic copies stays a valid row.

    PFS-2104.011 made the rotor block the blade count and refused a ``BLADES`` that
    disagrees with it. A mesh that carries ONE blade family, with the row's
    ``PERIODIC_COPIES`` supplying the wheel (the committed study reference says so
    in its own words), states ``BLADES: 6`` beside ``PERIODIC_COPIES: 6``: that is
    the same rotor counted two ways, and it was refused.
    """

    @staticmethod
    def test_p0400_integfix_blades_one_family_times_the_copies_is_the_stated_count():
        """P0400-INTEGFIX-BLADES (PFS-2104.011): families x copies equal to BLADES agrees."""
        row = _integfix_blades___row(SYMMETRY="PERIODIC", PERIODIC_COPIES="6", BLADES="6")
        assert _blade_count(row) == 6

    @staticmethod
    def test_p0400_integfix_blades_a_count_that_the_copies_do_not_explain_is_still_refused():
        """P0400-INTEGFIX-BLADES (PFS-2104.011): BLADES 5 beside one family and six copies."""
        with pytest.raises(CampaignConfigError, match=r"BLADES: 5 .* 1 blade"):
            _blade_count(
                _integfix_blades___row(SYMMETRY="PERIODIC", PERIODIC_COPIES="6", BLADES="5")
            )
        with pytest.raises(CampaignConfigError, match=r"BLADES: 6 .* 1 blade"):
            _blade_count(_integfix_blades___row(BLADES="6"))


class TestLast6Script:
    """Public parking and observation of accepted Script emissions."""

    pytestmark = pytest.mark.requirement("P0400-LAST6-SCRIPT")

    @staticmethod
    def test_p0400_last6_input_collision_is_case_insensitive():
        script = Script("26.124")
        park = getattr(script, "park_input_file", None)
        assert callable(park), "P0400-LAST6-INPUT: cases need a public parking operation"
        park("Field.dat", b"first")
        park("field.dat", b"first")
        assert script.pending_input_files == {"Field.dat": b"first"}
        with pytest.raises(CommandArgumentError, match="collid"):
            park("FIELD.dat", b"different")
        assert script.pending_input_files == {"Field.dat": b"first"}

    @staticmethod
    def test_p0400_last6_observer_sees_only_accepted_commands():
        script = Script("26.124")
        observe = getattr(script, "observe_commands", None)
        assert callable(observe), "P0400-LAST6-RECORD: recording must not subclass Script"
        calls = []
        with observe(lambda *call: calls.append(call)):
            script.emit("SOLVER_SET_AOA", 2)
            with pytest.raises(CommandArgumentError):
                script.emit("SOLVER_SET_AOA", "bad")
            script.emit_line("SOLVER_SET_AOA 3")
        script.emit("SOLVER_SET_AOA", 4)
        assert len(calls) == 2
        assert calls[0] == ("SOLVER_SET_AOA", (2,), {}, "SOLVER_SET_AOA 2\n", False)
        assert calls[1][-1] is True


class TestRfixr3Azimuths:
    """Release review round three, REL3-001 (FR-1040, FR-1045): an odd azimuth count.

    The aliasing rule refuses a harmonic order at or above half the azimuth count,
    2 m_max >= n_psi. Integer division (m_max >= n_psi // 2) refused order 6 on
    13 azimuths, which the numerical core resolves, and so kept a qualifying
    declared lattice from being reused.
    """

    @staticmethod
    @pytest.mark.requirement("FR-454")
    def test_p0400_rfixr3_an_order_below_half_an_odd_azimuth_count_is_accepted():
        """P0420: order 7 on 15 azimuths is below 7.5; on 14 azimuths it is refused."""
        LedgersSpec(rotor="R", stations=(1.0,), n_r=2, n_psi=15, m_max=7)
        with pytest.raises(ValueError, match="n_psi = 14"):
            LedgersSpec(rotor="R", stations=(1.0,), n_r=2, n_psi=14, m_max=7)

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_rfixr3_the_sole_odd_azimuth_lattice_is_reused(tmp_path):
        """P0420: a sole declared 15-azimuth lattice qualifies for order 7 and is reused."""
        declared = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 15}
        case = _rfixr3_azimuths___case(
            tmp_path,
            {"families": "all", "ledgers": {"rotor": "ROTOR", "m_max": 7}},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [declared]}],
        )
        script = _rfixr3_azimuths___script(case)
        count = LatticeShape.model_validate(declared).build(1.0).point_count
        assert len(script.probe_points) == count, "laid once, the declared entry"
        (shape,) = script.farfield_layout[-1]["shapes"]
        assert (shape["kind"], shape["source"], shape["entry"]) == ("lattice", "declared", 1)
        assert _rfixr3_azimuths___states(plan_record(case, "26.124", script), "ledgers") == {
            "reused"
        }


class TestSixdofRefusesNonMetreUnits:
    """FR-1087: a simulation in another length unit than the metre is refused at plan."""

    @staticmethod
    def test_fr1087_a_millimetre_simulation_is_refused_and_a_metre_one_is_not():
        from pyflightstream.cases.workflows._sixdof import _refuse_what_the_motion_cannot_place

        case = _gaps_rt_sixdof___case_for("unsteady")
        metres = Script(_GAPS_RT_SIXDOF__BUILD)
        metres.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
        _refuse_what_the_motion_cannot_place(case, metres)
        millimetres = Script(_GAPS_RT_SIXDOF__BUILD)
        millimetres.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
        with pytest.raises(CampaignConfigError, match="metres"):
            _refuse_what_the_motion_cannot_place(case, millimetres)
