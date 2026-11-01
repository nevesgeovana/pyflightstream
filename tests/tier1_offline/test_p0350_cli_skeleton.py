"""Tier 1: the 0.35.0 command-line skeleton of the grouped run modes.

Pipeline role: quality gate on the dispatch between the per-point functions and
the grouped ones. ``--polar-sweep`` and ``--batch N`` parse on ``run`` and on
``plan``, exclude each other, and leave the default per-point mode on the very
function it always called.
"""

from __future__ import annotations

import argparse
import warnings

import pytest

from pyflightstream._errors import EmptySelectionWarning, NotApplicableWarning
from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.cases.workflows._vocabulary import WALLTIME_VARIABLE
from pyflightstream.run._grouped import (
    grouped_case,
    planner_for,
    refuse_grouped_options,
    runner_for,
)
from pyflightstream.run._plan_report import (
    OUTPUT_DIR,
    design_table,
    figure_path,
    visual_inspect,
)
from pyflightstream.run.cli import main


def _default(*_args: object, **_kwargs: object) -> str:
    return "per-point"


@pytest.mark.requirement("FR-350")
@pytest.mark.requirement("FR-351")
def test_p0350_cli_fr350_fr351_the_options_parse_and_default_mode_is_unchanged(
    tmp_path, capsys
) -> None:
    """P0350-RUN-POLAR-SWEEP, P0350-RUN-BATCH: both options parse; neither leaves the default."""
    for option in (["--polar-sweep"], ["--batch", "2"]):
        # `run` parses the option and stops at its own plan gate, before any grouped code.
        assert main(["run", "none.fs", "--workspace", str(tmp_path), *option]) == 2
        assert "plan" in capsys.readouterr().err
    for command in ("run", "plan"):
        with pytest.raises(SystemExit) as stop:
            main([command, "--help"])
        assert stop.value.code == 0
        help_text = capsys.readouterr().out
        assert "--polar-sweep" in help_text and "--batch N" in help_text
    none = argparse.Namespace(polar_sweep=False, batch=None)
    assert runner_for(none, _default) is _default
    assert planner_for(none, _default) is _default


def test_p0350_cli_refusals(tmp_path, capsys) -> None:
    """P0350-RUN-POLAR-SWEEP, P0350-RUN-BATCH: the parser refuses bad combinations by name."""
    for argv, named in (
        (["--polar-sweep", "--batch", "2"], "--batch"),
        (["--batch", "0"], "--batch"),
        (["--batch", "-3"], "--batch"),
    ):
        with pytest.raises(SystemExit) as stop:
            main(["run", "none.fs", "--workspace", str(tmp_path), *argv])
        assert stop.value.code == 2
        assert named in capsys.readouterr().err
    assert refuse_grouped_options(force_rerun=None, force_rerun_all=False, sweep_csv=None) is None
    for kwargs, flag in (
        ({"force_rerun": ["2006"]}, "--force-rerun"),
        ({"force_rerun_all": True}, "--force-rerun-all"),
        ({"sweep_csv": "t.csv"}, "--sweep-csv"),
    ):
        base = {"force_rerun": None, "force_rerun_all": False, "sweep_csv": None, **kwargs}
        assert flag in (refuse_grouped_options(**base) or "")


def test_p0350_grouping_fr364_grouped_case_strips_only_the_clock() -> None:
    """P0350-RUN-BATCH: grouped_case removes WALLTIME and nothing else."""
    case = SimCase(
        sim_id="2006",
        aircraft="A",
        mach=0.2,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="m:f",
        variables={WALLTIME_VARIABLE: "4h", "OTHER": 3, "FLAG": True},
    )
    stripped = grouped_case(case)
    assert WALLTIME_VARIABLE not in stripped.variables
    assert stripped.variables == {"OTHER": 3, "FLAG": True}
    for name in SimCase.model_fields:
        if name != "variables":
            assert getattr(stripped, name) == getattr(case, name), name
    assert WALLTIME_VARIABLE in case.variables


# test_p0540_visual_inspect.py merged here
# The four DoE matrices, one section per file, each led by a '#### <name>' line.
DOE_MATRICES = """#### doe-power-on.fs
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION   | DESCRIPTION                            | FLIGHT_CONDITION                                             | SWEEP_VALUES                       | GEOMETRY                              | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW       | VAR_NAMES_VALUES
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
9801 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+0p00_AOA+0p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.69, 0.73, 0.74, 0.75, 0.76, 0.80 | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9802 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+0p00_AOA+2p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:2, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9803 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+0p00_AOA+4p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:4, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9804 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+0p00_AOA+0p00_ELEV-2p50     | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9805 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+0p00_AOA+0p00_ELEV-5p00     | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9806 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+1p50_AOA+0p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9807 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+1p50_AOA+2p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:2, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9808 | 0      | 1   | TEST   | WBVHX_ELEV      | ADD_ON_INC+1p50_AOA+4p00_ELEV+0p00     | MACH:0.157, ALTFT:3600, ALPHA:4, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.74, 0.78                   | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p013  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
#### doe-power-off.fs
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION   | DESCRIPTION                            | FLIGHT_CONDITION                                                | SWEEP_VALUES      | GEOMETRY                              | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW       | VAR_NAMES_VALUES
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
9851 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+0p00_ELEV+0p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9852 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+0p00_ELEV-2p50             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9853 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+0p00_ELEV-5p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9854 | 0      | 1   | TEST   | BVH_POWEROFF    | ADD_OFF_INC+0p00_ELEV+0p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_BVH_poweroff.fsm                | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9855 | 0      | 1   | TEST   | BVH_POWEROFF    | ADD_OFF_INC+0p00_ELEV-2p50             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_BVH_poweroff.fsm                | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9856 | 0      | 1   | TEST   | BVH_POWEROFF    | ADD_OFF_INC+0p00_ELEV-5p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_BVH_poweroff.fsm                | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9857 | 0      | 1   | TEST   | B_POWEROFF      | ADD_OFF_INC+0p00_ELEVOFF               | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_B_poweroff.fsm                  | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9858 | 0      | 1   | TEST   | WB_POWEROFF     | ADD_OFF_INC+0p00_ELEVOFF               | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WB_poweroff.fsm                 | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9859 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+1p50_ELEV+0p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9860 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+1p50_ELEV-2p50             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -2.5000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
9861 | 0      | 1   | TEST   | WBVH_POWEROFF   | ADD_OFF_INC+1p50_ELEV-5p00             | MACH:0.157, ALTFT:3600, ALPHA:sweep, BETA:0 | 0, 1, 2, 3, 4     | DUMMY_WBVH_poweroff.fsm               | r012 | s016 | p012  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE: -5.0000 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 1989.46}
#### doe-rotor-a.fs
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION   | DESCRIPTION                            | FLIGHT_CONDITION                                             | SWEEP_VALUES      | GEOMETRY                              | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW       | VAR_NAMES_VALUES
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
9301 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9302 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.0000 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.0000 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.3704 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.3704 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9303 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.0370 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.0370 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.6296 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.6296 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9304 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.1481 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.1481 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.9259 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.9259 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9305 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.7407 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.7407 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.7778 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.7778 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9306 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.3333 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.3333 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0741 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0741 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9307 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.7037 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.7037 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.3333 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.3333 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9308 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.4444 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.4444 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.1852 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.1852 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9309 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.5556 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.5556 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.5556 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5556 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9310 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.2222 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.2222 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.5926 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.5926 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9311 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.4815 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.4815 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.7407 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.7407 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9312 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.7778 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.7778 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.6667 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.6667 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9313 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.9630 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.9630 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.4074 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.4074 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9314 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.8889 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.8889 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.5185 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.5185 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9315 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.6296 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.6296 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.1111 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.1111 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9316 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.4074 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.4074 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.2222 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.2222 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9317 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.1111 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.1111 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.2593 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.2593 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9318 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.2963 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.2963 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.9630 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.9630 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9319 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.8148 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.8148 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.4815 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.4815 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9320 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.5185 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.5185 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.8148 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.8148 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9321 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.3704 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.3704 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.0370 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.0370 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9322 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.5926 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.5926 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.7037 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.7037 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9323 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.2593 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.2593 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.8889 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.8889 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9324 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.8519 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.8519 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.4444 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.4444 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9325 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.0741 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.0741 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.8519 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.8519 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9326 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.9259 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.9259 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.0000 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.0000 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9327 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.1852 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.1852 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.1481 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.1481 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9328 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_PARAMETRIC_01                | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.6667 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.6667 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.2963 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.2963 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER}/ DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
#### doe-rotor-b.fs
POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION   | DESCRIPTION                            | FLIGHT_CONDITION                                             | SWEEP_VALUES      | GEOMETRY                              | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW       | VAR_NAMES_VALUES
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
9401 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.4250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.4250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.2500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.2500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9402 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  4.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.6250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.6250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.5500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.5500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9403 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -4.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -4.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.9250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.9250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.0500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.0500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9404 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -4.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -2.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.3250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.3250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.8500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.8500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9405 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -0.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.3750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.3750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.5500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.5500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9406 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  4.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  1.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.0250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.0250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.1500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.1500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9407 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  3.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -1.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.6250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.6250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.6500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.6500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9408 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -2.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.1750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.1750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.6500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.6500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9409 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  4.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -2.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.1250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.1250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.4500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.4500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9410 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -3.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -3.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.7750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.7750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.3500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.3500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9411 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  3.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -3.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.8250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.8250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.1500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.1500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9412 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  4.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.3250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.3250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.3500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.3500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9413 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.1250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.1250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.4500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.4500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9414 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  0.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  4.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.0250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.7500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.7500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9415 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -4.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  3.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.9750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.9750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.7500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.7500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9416 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -0.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -0.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.2250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.2250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.7500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.7500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9417 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -3.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -3.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.8750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.8750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.2500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.2500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9418 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -2.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  3.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.4750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.4750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.0500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.0500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9419 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  2.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  4.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.9750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.9750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.0500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.0500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9420 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  2.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  2.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.7250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.7250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.5500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.5500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9421 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  3.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -4.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.5250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.5250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.6500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.6500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9422 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -1.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  2.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.2750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.2750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.9500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.9500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9423 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -3.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.7750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.7750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.9500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.9500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9424 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -0.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  2.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.2750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.2750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.8500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.8500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9425 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -1.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  1.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.3750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.3750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.2500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.2500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9426 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -4.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -0.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.8750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.8750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.4500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.4500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9427 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -1.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  2.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.5250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.5250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.1500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.1500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9428 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -2.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  1.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.6750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.6750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.3500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.3500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9429 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  3.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  0.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.5750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.5750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.8500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.8500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9430 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -2.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -1.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.4250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.4250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.9500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.9500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9431 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -3.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  1.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.1750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.1750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.4500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.4500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9432 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -0.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -4.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.7250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.7250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.5500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.5500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9433 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  4.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -1.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.2250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.2250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.6500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.6500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9434 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  1.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -4.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.0750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.0750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.3500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.3500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9435 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -0.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -0.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.6750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.6750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.1500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.1500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9436 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  4.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  3.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.8250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.8250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.8500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.8500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9437 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  2.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -3.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.9250 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.9250 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  0.0500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  0.0500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9438 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  2.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -1.3750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  1.5750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  1.5750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  3.2500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  3.2500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9439 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -1.8750 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  -2.1250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.0750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.0750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  2.9500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  2.9500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
9440 | 0      | 1   | TEST   | WBVHX_ELEV      | PITCH_TOE_ELEV_PARAMETRIC_01           | MACH:0.157, ALTFT:3600, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.71, 0.78        | 45_WBVH_elev_mid_poweron_assym.fsm    | r012 | s011 | p010  | None     | false          |  10   | -        | 26.127   | unsteady_rotor | ROTATE: {ANGLE:  -2.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_LH},{ANGLE:  3.6250 / AXIS: HINGE_ELEV-Y / ALIAS: elev_RH},{ANGLE:  0.4750 / AXIS: ENGTOE_RH-Z / ALIAS: morph_push}, {ANGLE:  0.4750 / AXIS: ENGTOE_RH-Z / ALIAS: PUSHER},{ANGLE:  1.7500 / AXIS: ENGTILT_DN-Y / ALIAS: morph_push},{ANGLE:  1.7500 / AXIS: ENGTILT_DN-Y / ALIAS: PUSHER} / DELTA_THETA: 10.0 / REVOLUTIONS: 4.0 / LAST_REVS_AVG: 1.0 / CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER} / EXPORT_UNSTEADY_LAST_ITER: 9
"""  # noqa: E501


COUNTS = {"doe-power-on": 27, "doe-power-off": 55, "doe-rotor-a": 56, "doe-rotor-b": 80}


@pytest.fixture
def workspace(tmp_path):
    for section in DOE_MATRICES.split("#### ")[1:]:
        name, _, body = section.partition("\n")
        (tmp_path / name).write_text(body, encoding="utf-8", newline="\n")
    return tmp_path


def _table(workspace, names=tuple(COUNTS)):
    return design_table({n: read_matrix(workspace / f"{n}.fs") for n in names})


def test_p0540_each_matrix_expands_into_its_points(workspace):
    table = _table(workspace)
    assert {name: len(points) for name, points in table.items()} == COUNTS


def test_p0540_the_rotate_alias_turned_about_two_axes_is_named_with_its_axis(workspace):
    table = _table(workspace)
    names = {key for points in table.values() for p in points for key in p}
    assert "morph_push:ENGTILT_DN-Y" in names
    assert "morph_push:ENGTOE_RH-Z" in names
    assert "morph_push" not in names
    # an alias turned about one axis keeps its plain name
    assert "elev_RH" in names


def test_p0540_an_unstated_alias_is_not_turned_so_its_angle_is_zero(workspace):
    off = _table(workspace)["doe-power-off"]
    # the power-off matrix never states the toe axis the other matrices turn: 0, not left out
    assert all(p["morph_push:ENGTOE_RH-Z"] == 0.0 for p in off)
    assert {p["elev_RH"] for p in off} >= {0.0, -2.5, -5.0}


def test_p0540_a_parameter_a_row_does_not_state_leaves_the_point_out(workspace):
    table = _table(workspace)
    assert all("MACH" in p and "ALTFT" in p for points in table.values() for p in points)
    # SYMMETRY_LOADS and the other columns are no design parameters
    assert all("NCPUS" not in p for points in table.values() for p in points)


def test_p0540_a_row_that_declares_no_advance_ratio_has_no_advance_ratio_point(workspace):
    table = _table(workspace)
    assert all("ADVANCE_RATIO" not in p for p in table["doe-power-off"])
    assert all("ADVANCE_RATIO" in p for p in table["doe-power-on"])
    assert all("ALPHA" in p for p in table["doe-power-off"])


def test_p0540_the_command_writes_the_pdf_and_prints_its_path(workspace, capsys):
    code = main(
        [
            "visual-inspect",
            "--workspace",
            str(workspace),
            "--name",
            "design",
            "--matrices",
            "doe-rotor-a.fs",
            "doe-power-on",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    # The file is named by --name, in the fixed place.
    expected = figure_path(workspace, "design")
    assert expected == workspace / "post" / "visual-inspect" / "design.pdf"
    assert str(expected) in out
    assert "'doe-rotor-a': 56" in out
    assert expected.read_bytes().startswith(b"%PDF")
    assert expected.parent == workspace / "post" / "visual-inspect"
    assert OUTPUT_DIR == "post/visual-inspect"


def test_p0540_without_params_every_varying_parameter_is_drawn_and_reported(workspace, capsys):
    out = visual_inspect(workspace, ["doe-power-on", "doe-power-off"], name="fig")
    assert out is not None and out.is_file()
    printed = capsys.readouterr().out
    varying_line = next(
        line for line in printed.splitlines() if line.startswith("varying parameters:")
    )
    assert "ADVANCE_RATIO" in varying_line
    assert "ALPHA" in varying_line
    assert "MACH" not in varying_line


def test_p0540_all_takes_every_matrix_of_the_workspace(workspace, capsys):
    out = visual_inspect(workspace, ["all"], ["ALPHA"], name="fig")
    assert out == workspace / "post" / "visual-inspect" / "fig.pdf"
    printed = capsys.readouterr().out
    for name, count in COUNTS.items():
        assert f"'{name}': {count}" in printed


def test_p0540_an_unknown_parameter_is_warned_and_skipped_naming_what_is_stated(workspace):
    with pytest.warns(NotApplicableWarning) as caught:
        out = visual_inspect(
            workspace, ["doe-rotor-a"], ["ALPHA", "NOT_A_PARAMETER", "ADVANCE_RATIO"], name="fig"
        )
    assert out is not None and out.is_file()
    text = " ".join(str(w.message) for w in caught)
    assert "NOT_A_PARAMETER" in text
    assert "ADVANCE_RATIO" in text and "morph_push:ENGTILT_DN-Y" in text


def test_p0540_with_no_parameter_left_nothing_is_written(workspace):
    with pytest.warns(EmptySelectionWarning):
        with pytest.warns(NotApplicableWarning):
            assert (
                visual_inspect(workspace, ["doe-rotor-a"], ["NOT_A_PARAMETER"], name="fig") is None
            )
    assert not (workspace / "post").exists()


def test_p0540_a_matrix_the_workspace_does_not_hold_is_warned_and_skipped(workspace):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = visual_inspect(workspace, ["doe-rotor-a", "nothing-here"], ["ALPHA"], name="fig")
    assert out is not None
    assert any(
        issubclass(w.category, NotApplicableWarning) and "nothing-here" in str(w.message)
        for w in caught
    )


def test_p0540_an_rpm_inside_a_motions_record_is_no_parameter(workspace):
    table = _table(workspace)
    names = {key for points in table.values() for p in points for key in p}
    assert "RPM" not in names and not any("1989" in key for key in names)


# --- finished / not finished markers (0.53.0, FR-3440) ---

_OFF = "doe-power-off"  # POL 9851 to 9857, ALPHA 0 to 4 each: 55 points
_NAME = "M157ALT03600AL{a:+04d}BE+000"


def _captured_figure(monkeypatch):
    from matplotlib.backends.backend_pdf import PdfPages

    held = []
    real = PdfPages.savefig

    def keep(self, figure=None, **kwargs):
        held.append(figure)
        return real(self, figure, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", keep)
    return held


def _marker_counts(figure):
    """Return (filled, open) point counts of the first scatter panel, read from its artists."""
    from matplotlib.colors import to_rgba

    filled = open_ = 0
    panel = figure.axes[1]
    for collection in panel.collections:
        count = collection.get_offsets().shape[0]
        if tuple(collection.get_facecolor()[0]) == to_rgba("white"):
            assert collection.get_sizes()[0] >= 1.7 * 14 and collection.get_zorder() >= 3
            open_ += count
        else:
            filled += count
    return filled, open_


def _polar_table(workspace, pol, alphas):
    folder = workspace / "post" / _OFF / "polars"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["POL,ALPHA,BETA,MACH"] + [f"{pol},{a},0,0.157" for a in alphas]
    (folder / f"P{pol}-M157AL+sweep_g01.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _runs_json(workspace, rows):
    import json

    from pyflightstream.workspace import RunRecord, RunStatus
    from pyflightstream.workspace.record_document import encode_rows

    records = []
    for sim, alpha, status in rows:
        record = RunRecord(
            run_id=f"camp/sim_{sim}/{_NAME.format(a=alpha * 10)}",
            sim_id=sim,
            matrix_stem=_OFF,
            fs_version_requested="26.124",
            package_version="0.53.0",
            script_sha256="c" * 64,
            recipe="steady",
            raw_flag=False,
            status=RunStatus(status),
            outputs=[],
            script_path=None,
            inputs_sha256={},
            point={"alpha": float(alpha)},
        )
        records.append(record.model_dump(mode="json"))
    (workspace / "runs.json").write_text(json.dumps(encode_rows(records)), encoding="utf-8")


def test_p0530_vi_products_marks_a_point_with_a_polar_row_finished(workspace, monkeypatch, capsys):
    held = _captured_figure(monkeypatch)
    _polar_table(workspace, "9851", [0, 1])  # two rows present
    _polar_table(workspace, "9853", [3])  # a table, but no row for the other points
    # POL 9852 has no table at all
    assert visual_inspect(workspace, [_OFF], ["ALPHA", "MACH"], name="fig") is not None
    assert "'doe-power-off': '3/55'" in capsys.readouterr().out
    assert _marker_counts(held[0]) == (3, 52)
    labels = [t.get_text() for t in held[0].legends[0].get_texts()]
    assert "finished" in labels and "not finished" in labels


def test_p0530_vi_products_without_a_polars_folder_every_point_is_not_finished(
    workspace, monkeypatch, capsys
):
    held = _captured_figure(monkeypatch)
    assert visual_inspect(workspace, [_OFF], ["ALPHA", "MACH"], name="fig") is not None
    assert "'doe-power-off': '0/55'" in capsys.readouterr().out
    assert _marker_counts(held[0]) == (0, 55)


def test_p0530_vi_sims_marks_a_converged_record_finished_and_a_failed_one_not(
    workspace, monkeypatch, capsys
):
    held = _captured_figure(monkeypatch)
    _runs_json(
        workspace,
        [("9851", 0, "CONVERGED"), ("9851", 1, "FAILED_DIVERGED"), ("9852", 0, "CONVERGED")],
    )
    out = visual_inspect(workspace, [_OFF], ["ALPHA", "MACH"], finished_by="sims", name="fig")
    assert out is not None
    assert "'doe-power-off': '2/55'" in capsys.readouterr().out
    assert _marker_counts(held[0]) == (2, 53)


def test_p0530_vi_sims_without_runs_json_every_point_is_not_finished(workspace, capsys):
    assert (
        visual_inspect(workspace, [_OFF], ["ALPHA", "MACH"], finished_by="sims", name="fig")
        is not None
    )
    assert "'doe-power-off': '0/55'" in capsys.readouterr().out


def test_p0530_vi_the_option_takes_products_or_sims_only(workspace):
    from pyflightstream.run._plan_report import FINISHED_BY_CHOICES, FINISHED_BY_OPTION

    assert FINISHED_BY_CHOICES == ("products", "sims") and FINISHED_BY_OPTION == "--finished-by"
    with pytest.raises(ValueError, match="finished_by"):
        visual_inspect(workspace, [_OFF], finished_by="polars", name="fig")


def test_p0530_vi_name_is_required_takes_pdf_once_and_refuses_a_folder(workspace, capsys):
    base = [
        "visual-inspect",
        "--workspace",
        str(workspace),
        "--matrices",
        _OFF,
        "--params",
        "ALPHA",
    ]
    with pytest.raises(SystemExit):
        main(base)  # no --name
    assert "--name" in capsys.readouterr().err
    assert main([*base, "--name", "mine.pdf"]) == 0
    assert (workspace / "post" / "visual-inspect" / "mine.pdf").is_file()
    assert not (workspace / "post" / "visual-inspect" / "mine.pdf.pdf").exists()
    for bad in ("sub/mine", "sub\\mine"):
        with pytest.raises(SystemExit):
            main([*base, "--name", bad])
        assert "--name" in capsys.readouterr().err


def test_p0530_vi_an_existing_figure_is_kept_with_a_warning_unless_overwrite(workspace):
    target = workspace / "post" / "visual-inspect" / "keep.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    with pytest.warns(NotApplicableWarning, match="--overwrite") as caught:
        assert visual_inspect(workspace, [_OFF], ["ALPHA"], name="keep") is None
    assert str(target) in str(caught[0].message)
    assert target.read_bytes() == b"old"
    assert visual_inspect(workspace, [_OFF], ["ALPHA"], name="keep", overwrite=True) == target
    assert target.read_bytes().startswith(b"%PDF")
    target.write_bytes(b"old")
    base = ["visual-inspect", "--workspace", str(workspace), "--matrices", _OFF, "--name", "keep"]
    with pytest.warns(NotApplicableWarning):
        assert main(base) == 0
    assert target.read_bytes() == b"old"
    assert main([*base, "--overwrite"]) == 0
    assert target.read_bytes().startswith(b"%PDF")
