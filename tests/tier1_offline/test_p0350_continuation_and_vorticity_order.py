"""Tier 1: a continuation continues the march; a rotor march lands its drag list before the solve.

FR-396 (RPT-134): a continuation that reopens a saved state emits no INITIALIZE_SOLVER
(R1), registers none of the unsteady actions the saved file carries (R2), and the post
warns when a continuation adds no time step to the march (R3). FR-318 R6 (RPT-133): a
row turning a rotor in time that states vorticity_drag_families emits the list right
before START_SOLVER. Each behaviour is checked on the script the package builds, with a
control that shows the check can see the other answer, and each named difference of the
parity checker is held to the real render.
"""

from __future__ import annotations

import importlib.util
import json
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    MeshImport,
    RawMeshConditions,
    ReferenceData,
    SimCase,
    SolverSettings,
    TrailingEdgeMarking,
)
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    UNSTEADY_ACTION_SCRIPT,
    UNSTEADY_COUNTER_ACTION,
    UNSTEADY_EXPORTS_ACTION,
    WALLTIME_CLOCK_ACTION,
    WALLTIME_STOP_ACTION,
    WALLTIME_STOP_SCRIPT,
    build_script,
)
from pyflightstream.script import Script
from tests.tier1_offline.test_restart_continuation import SAVED, _continuing_case
from tests.tier1_offline.test_rpt134_fr96_continuation_history import (
    PER_REV,
    _posted,
    _workspace,
)
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

REPO = Path(__file__).resolve().parents[2]
BUILD = "26.124"
ACTION = "SET_NEW_UNSTEADY_SOLVER_ACTION"
#: The four actions a row with an export threshold and a wall clock registers, in order.
FOUR = [
    UNSTEADY_COUNTER_ACTION,
    UNSTEADY_EXPORTS_ACTION,
    WALLTIME_CLOCK_ACTION,
    WALLTIME_STOP_ACTION,
]
THRESHOLD_AND_CLOCK = {"EXPORT_UNSTEADY_AFTER_ITER": "5", "WALLTIME": "2h"}
CONTINUING = {RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "12"}
NO_STEP = "adds no time step"


def _built(case: SimCase) -> Script:
    script = Script(BUILD)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script


def _lines(case: SimCase) -> list[str]:
    return _built(case).render().splitlines()


def _rotor_continuation(**variables: str) -> SimCase:
    return rotor_case(**{RESTART_VARIABLE: "{ADDITIONAL_REVS=1}", **CONTINUING, **variables})


def _with_geometry(case: SimCase, tmp_path: Path, **solver: object) -> SimCase:
    """``case`` with a raw mesh of two families and the setup ``solver`` states."""
    return case.model_copy(
        update={
            "geometry": str(tmp_path / "rotor.obj"),
            "inventory": ("Blade", "Hub"),
            "inventory_source": "sidecar",
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
            "reference": ReferenceData(area=1.0, length=0.1, span_m=1.0),
            "solver": SolverSettings(**solver),
        }
    )


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity_p0350", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- FR-396 R1: no INITIALIZE_SOLVER on a reopened state --------------------------------


@pytest.mark.parametrize("run_type", ["unsteady", "unsteady_rotor"])
def test_a_continuation_emits_no_initialize_solver_fr_396(run_type):
    """P0350-CONTINUATION-NO-REINIT (FR-396): OPEN ... ENABLE, the clock, START_SOLVER; no init.

    The control is the same row run from its mesh, whose script initialises the solver,
    so the check can see the block.
    """
    if run_type == "unsteady":
        continued = _continuing_case("{ADDITIONAL_ITERS=12}", **CONTINUING)
        control = unsteady_case()
    else:
        continued = _rotor_continuation()
        control = rotor_case()
    lines = _lines(continued)
    assert "INITIALIZE_SOLVER" not in lines, lines
    assert lines[:3] == ["OPEN", SAVED, "LOAD_SOLVER_INITIALIZATION ENABLE"], lines[:3]
    assert lines.index("SET_SOLVER_UNSTEADY") < lines.index("START_SOLVER")
    assert lines.count("START_SOLVER") == 1
    assert "INITIALIZE_SOLVER" in _lines(control)


# --- FR-396 R2: the actions the saved state carries are not registered again ----------


@pytest.mark.parametrize("run_type", ["unsteady", "unsteady_rotor"])
def test_a_continuation_registers_none_of_the_saved_actions_fr_396(run_type):
    """P0350-CONTINUATION-ACTIONS-ONCE (FR-396): no registration line, the same uses recorded.

    The saved simulation runs the actions its run registered, and a second registration
    under the same name ran beside it, twice a step (RPT-134). The uses stay on the
    script, in the order a run from the mesh records them, so the run stages the files
    the saved actions run; the control is that run from the mesh, which emits the four
    registrations.
    """
    if run_type == "unsteady":
        continued = _continuing_case("{ADDITIONAL_ITERS=12}", **THRESHOLD_AND_CLOCK, **CONTINUING)
        control = unsteady_case(**THRESHOLD_AND_CLOCK)
    else:
        continued = _rotor_continuation(**THRESHOLD_AND_CLOCK)
        control = rotor_case(**THRESHOLD_AND_CLOCK)
    script = _built(continued)
    assert not [line for line in script.render().splitlines() if line.startswith(ACTION)]
    assert [use.name for use in script.unsteady_actions] == FOUR
    assert sorted(script.pending_action_scripts) == sorted(
        [UNSTEADY_ACTION_SCRIPT, WALLTIME_STOP_SCRIPT]
    )
    assert set(script.pending_action_scripts.values()) == {""}
    full = _built(control)
    registered = [line for line in full.render().splitlines() if line.startswith(ACTION)]
    assert [line.split()[-1] for line in registered] == FOUR
    assert [use.name for use in full.unsteady_actions] == FOUR


def test_a_continuation_without_a_threshold_records_the_counter_alone_fr_396():
    """P0350-CONTINUATION-ACTIONS-ONCE (FR-396): a row asking no per-step export keeps its counter.

    The counter counts only on such a row (FR-314), and the march label the build checks
    against the recorded uses still holds: a single march with its counter.
    """
    script = _built(_continuing_case("{ADDITIONAL_ITERS=12}", **CONTINUING))
    assert ACTION not in script.render()
    assert [use.name for use in script.unsteady_actions] == [UNSTEADY_COUNTER_ACTION]
    assert script.pending_action_scripts == {}


# --- FR-396 R3: the post warns on a continuation that adds no step ---------------------


def test_the_post_warns_when_a_continuation_adds_no_time_step_fr_396(tmp_path):
    """P0350-CONTINUATION-WARN (FR-396): the 0.34.0 continuation re-marched; the post says so.

    RPT-134's recorded exports: the continuation 0.34.0 emitted restates the point's 12
    steps and ends at step 12, where the point ended. The warning names the continuation
    and the run it continues, and the table is still posted. The post log line is the one
    the parity checker names FR-396.
    """
    workspace = _workspace(tmp_path, continuation="continuation_plots.txt")
    (original, continuation) = workspace.read_manifest()
    _, series, said = _posted(workspace)
    idle = [message for message in said if NO_STEP in message]
    assert len(idle) == 1, said
    assert f"point={continuation.run_id} " in idle[0]
    assert f"this continuation of {original.run_id!r}" in idle[0]
    assert f"had reached step {PER_REV}" in idle[0]
    assert list(series.steps) == list(range(1, PER_REV + 1))
    out = workspace.root / "post" / "products"
    parity = _parity()
    log = (out / "post.log").read_text(encoding="utf-8").splitlines()
    (line,) = [entry for entry in log if NO_STEP in entry]
    base = "\n".join(entry for entry in log if NO_STEP not in entry) + "\n"
    release = "\n".join(log) + "\n"
    named = parity.name_difference("post", "w/post.log", base, release, {"FR-396"})
    assert named.get("requirement") == "FR-396", (line, named)
    document = json.loads((out / "post.log.json").read_text(encoding="utf-8"))
    (record,) = [entry for entry in document["records"] if NO_STEP in entry["message"]]
    assert (record["point"], record["product"]) == (continuation.run_id, "plots")
    kept = [entry for entry in document["records"] if entry is not record]
    old = json.dumps({**document, "records": kept}, indent=1) + "\n"
    new = json.dumps(document, indent=1) + "\n"
    named = parity.name_difference("post", "w/post.log.json", old, new, {"FR-396"})
    assert named.get("requirement") == "FR-396", named


def test_the_post_is_silent_when_the_continuation_marched_on_fr_396(tmp_path):
    """P0350-CONTINUATION-WARN (FR-396), the control: the resume arm adds 12 steps, no warning.

    RPT-134's resume arm kept the reopened state and its export holds the whole march,
    steps 1 to 24: the continuation added steps 13 to 24, so nothing is said about it.
    """
    _, series, said = _posted(_workspace(tmp_path, continuation="resume_plots.txt"))
    assert list(series.steps) == list(range(1, 2 * PER_REV + 1))
    assert not [message for message in said if NO_STEP in message], said


# --- FR-318 R6: the vorticity drag list before START_SOLVER on a rotor march ------------


@pytest.mark.parametrize(
    ("families", "payload"),
    [
        (["Blade"], ["SET_VORTICITY_DRAG_BOUNDARIES 1", "1"]),
        (["Blade", "Hub"], ["SET_VORTICITY_DRAG_BOUNDARIES 2", "1,2"]),
    ],
)
def test_a_rotor_march_lands_its_drag_list_before_start_solver_fr_318(tmp_path, families, payload):
    """P0350-VORTICITY-BEFORE-SOLVE (FR-318): the moments model, the list, START_SOLVER.

    The list's lines are RPT-133's arm B: right before START_SOLVER, once, and never
    after it. The rotor row stating no list emits none, and its script is otherwise the
    same: the move is the list's lines and nothing else.
    """
    case = _with_geometry(
        rotor_case(), tmp_path, vorticity_drag_families=families, moments_model="VORTICITY"
    )
    lines = _lines(case)
    start = lines.index("START_SOLVER")
    assert lines[start - len(payload) - 2 : start + 1] == [
        "SET_ANALYSIS_MOMENTS_MODEL VORTICITY",
        *payload,
        "",
        "START_SOLVER",
    ], lines[start - 5 : start + 2]
    assert sum(line.startswith("SET_VORTICITY_DRAG_BOUNDARIES") for line in lines) == 1
    bare = _built(_with_geometry(rotor_case(), tmp_path, moments_model="VORTICITY")).render()
    listed = "\n".join(payload) + "\n\nSTART_SOLVER\n"
    assert "\n".join(lines).replace(listed, "START_SOLVER\n") + "\n" == bare


@pytest.mark.parametrize("run_type", ["steady", "unsteady"])
def test_a_row_turning_no_rotor_in_time_keeps_its_list_after_the_solve_fr_318(tmp_path, run_type):
    """P0350-VORTICITY-BEFORE-SOLVE (FR-318), the control: R6 moves the list of a rotor march only.

    A steady row exports after the solve, and a march turning no rotor is outside the
    requirement and RPT-133's measurement: both keep the list right after START_SOLVER,
    as 0.34.0 emitted it.
    """
    make = steady_case if run_type == "steady" else unsteady_case
    lines = _lines(_with_geometry(make(), tmp_path, vorticity_drag_families=["Blade"]))
    start = lines.index("START_SOLVER")
    assert lines[start + 1 : start + 3] == ["SET_VORTICITY_DRAG_BOUNDARIES 1", "1"]


# --- the parity checker names each difference, and only it -----------------------------


def test_the_parity_checker_names_the_moved_list_fr_318_and_nothing_wider(tmp_path):
    """P0350-VORTICITY-BEFORE-SOLVE (FR-318): the named difference is held to the move.

    The 0.34.0 side is the release render with the list's lines moved back after
    START_SOLVER. A list that stays after START_SOLVER, another changed line, a march
    turning no rotor and an SRS without FR-318 are not named.
    """
    case = _with_geometry(
        rotor_case(), tmp_path, vorticity_drag_families=["Blade"], moments_model="VORTICITY"
    )
    release = _built(case).render()
    moved = "SET_VORTICITY_DRAG_BOUNDARIES 1\n1\n\n"
    base = release.replace(moved + "START_SOLVER\n", "START_SOLVER\n" + moved, 1)
    assert base != release
    parity = _parity()

    def name(old: str, new: str, defined: frozenset[str] = frozenset({"FR-318"})) -> dict:
        return parity.name_difference("scripts", "row.txt", old, new, set(defined))

    assert name(base, release).get("requirement") == "FR-318"
    assert "requirement" not in name(release, base)
    assert "requirement" not in name(
        base, release.replace("CLOSE_FLIGHTSTREAM", "EXTRA\nCLOSE_FLIGHTSTREAM")
    )
    unsteady = release.replace("CREATE_NEW_MOTION ROTARY", "CREATE_NEW_MOTION NONE")
    assert "requirement" not in name(
        base.replace("CREATE_NEW_MOTION ROTARY", "CREATE_NEW_MOTION NONE"), unsteady
    )
    assert "FR-318" in name(base, release, frozenset()).get("unnamed_because", "")


def test_the_parity_checker_names_the_continuation_fr_396_and_nothing_wider():
    """P0350-CONTINUATION-NO-REINIT (FR-396), P0350-CONTINUATION-ACTIONS-ONCE (FR-396): removal.

    The 0.34.0 side is the release render with the four registrations and the
    initialization put back where 0.34.0 emitted them. The opposite direction, a removal
    from a script that reopens no saved state, and another changed line are not named.
    """
    script = _built(_continuing_case("{ADDITIONAL_ITERS=12}", **THRESHOLD_AND_CLOCK, **CONTINUING))
    release = script.render()
    registrations = "".join(
        f"{ACTION} {use.kind} {use.name}\n{use.filename}\n\n" for use in script.unsteady_actions
    )
    initialization = (
        "INITIALIZE_SOLVER\nSOLVER_MODEL INCOMPRESSIBLE\nSURFACES -1\n"
        "WAKE_TERMINATION_X DEFAULT\nSYMMETRY NONE\n\n"
    )
    base = release.replace(
        "\nSTART_SOLVER\n", f"\n{registrations}{initialization}START_SOLVER\n", 1
    )
    assert base.count(ACTION) == 4 and "INITIALIZE_SOLVER" in base
    parity = _parity()

    def name(old: str, new: str) -> dict:
        return parity.name_difference("scripts", "row.txt", old, new, {"FR-396"})

    assert name(base, release).get("requirement") == "FR-396"
    assert "requirement" not in name(release, base)
    fresh = re.sub(
        r"(?m)^LOAD_SOLVER_INITIALIZATION ENABLE$", "LOAD_SOLVER_INITIALIZATION DISABLE", release
    )
    stale = re.sub(
        r"(?m)^LOAD_SOLVER_INITIALIZATION ENABLE$", "LOAD_SOLVER_INITIALIZATION DISABLE", base
    )
    assert "requirement" not in name(stale, fresh)
    assert "requirement" not in name(
        base, release.replace("CLOSE_FLIGHTSTREAM", "EXTRA\nCLOSE_FLIGHTSTREAM")
    )
