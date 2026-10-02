"""FR-318 R5: what the place of the vorticity drag list does to a rotor march's exports (RPT-133).

The fixtures are the loads spreadsheets the three arms of RPT-133 exported on FlightStream
26.124 (build 8172026), far field 5: the final export and the step-1 and step-12 exports of
arm A (the list after START_SOLVER, as the package emits it), arm B (the same three lines
moved before START_SOLVER) and arm C (no list, the control). Only the Total row is read.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    MeshImport,
    RawMeshConditions,
    ReferenceData,
    SolverSettings,
    TrailingEdgeMarking,
)
from pyflightstream.cases.workflows import build_script
from pyflightstream.results.loads import parse_loads
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import rotor_case

FIX = Path(__file__).resolve().parent / "fixtures" / "rpt133"
#: The build every recorded export names in its header, and the exports recorded.
BUILD = "8172026"
EXPORTS = tuple(f"{arm}_{when}" for arm in "ABC" for when in ("final", "step01", "step12"))
SOFTWARE = re.compile(r"Software : Flightstream version 26\.1, build #(\d+)")

#: RPT-133's answer to Q2: True when, with the list before START_SOLVER, every step export
#: carries it; False when none does. Measured True (12 of 12 step exports).
Q2_CARRIED: bool | None = True
#: RPT-133's reading of the released order: False when no step export of arm A carries the
#: list (what FR-318 R5 states), True when they do. Measured False (0 of 12 differ from C).
RELEASED_STEPS_CARRY: bool | None = False


def _total(name: str) -> dict[str, float]:
    return parse_loads((FIX / f"{name}.txt").read_text(encoding="latin-1")).total


def test_every_recorded_export_names_build_8172026_in_its_header_fr_318():
    """The fixtures are exports of 26.124 build 8172026, read from each file's own header."""
    # Verifies FR-318.
    assert sorted(p.stem for p in FIX.glob("*.txt")) == sorted(EXPORTS)
    builds = {
        name: SOFTWARE.findall((FIX / f"{name}.txt").read_text(encoding="latin-1"))
        for name in EXPORTS
    }
    assert all(found == [BUILD] for found in builds.values()), builds


def test_the_drag_list_moves_the_final_loads_the_control_fr_318():
    """The control's power: without the list the final induced drag differs, so a step can."""
    # Verifies FR-318.
    assert _total("A_final")["CDi"] != _total("C_final")["CDi"]


def test_after_start_solver_the_list_reaches_the_final_export_and_no_step_export_fr_318():
    """The released order (arm A): every step as the control's, the final export not (RPT-133)."""
    # Verifies FR-318.
    if RELEASED_STEPS_CARRY is None:
        pytest.fail("RELEASED_STEPS_CARRY is not filled from RPT-133")
    for step in ("step01", "step12"):
        assert (_total(f"A_{step}") != _total(f"C_{step}")) is RELEASED_STEPS_CARRY, step
    if not RELEASED_STEPS_CARRY:
        assert _total("A_step12") != _total("A_final")


def test_before_start_solver_the_step_exports_answer_r5_as_rpt_133_recorded_fr_318():
    """The probe (arm B): the list moved before the solve, read at step 1 and step 12."""
    # Verifies FR-318.
    if Q2_CARRIED is None:
        pytest.fail("Q2_CARRIED is not filled from RPT-133")
    if Q2_CARRIED:
        for step in ("step01", "step12"):
            assert _total(f"B_{step}") != _total(f"C_{step}"), step
        assert _total("B_step12") == _total("A_final")
    else:
        for step in ("step01", "step12"):
            assert _total(f"B_{step}") == _total(f"C_{step}"), step


def test_the_package_still_emits_the_order_rpt_133_measured_as_arm_a_fr_318(tmp_path):
    """Arm A is the package's order: the list after START_SOLVER, the moments model before it.

    If 0.35.0 moves the list, this test moves with it and RPT-133's arm B is its
    evidence; until then a change of order is a change RPT-133 did not measure.
    """
    # Verifies FR-318.
    case = rotor_case().model_copy(
        update={
            "geometry": str(tmp_path / "rotor.obj"),
            "inventory": ("Blade", "Hub"),
            "inventory_source": "sidecar",
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
            "reference": ReferenceData(area=1.0, length=0.1, span_m=1.0),
            "solver": SolverSettings(vorticity_drag_families=["Blade"], moments_model="VORTICITY"),
        }
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    lines = script.render().splitlines()
    start = lines.index("START_SOLVER")
    drag = next(
        i for i, line in enumerate(lines) if line.startswith("SET_VORTICITY_DRAG_BOUNDARIES")
    )
    assert lines.index("SET_ANALYSIS_MOMENTS_MODEL VORTICITY") < start < drag
