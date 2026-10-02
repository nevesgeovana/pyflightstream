"""WAKE-LENGTH (0.34.0, GOAL-039 arm MW): the wake a rotor row keeps, in rotor radii.

FR-321 to FR-325. A rotor row states its wake termination as a length in rotor
radii (``wake_termination_length``), converted into the steps
``SET_WAKE_TERMINATION_TIME_STEPS`` takes, and keeps 4 radii when it states none;
one key states the termination and two are refused; near hover a thrust's
induced velocity or a revolution cap bounds the conversion; a setup key places
the solver's wake end plane (``WAKE_TERMINATION_X`` of ``INITIALIZE_SOLVER``);
and the plan always warns when a row's wake may not reach its length. Every
expected number below is worked by hand from the fixture's own figures, never
read back from the code under test.
"""

from __future__ import annotations

import difflib
import json
import math
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, FluidState, SolverSettings
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.run import CampaignErrors, PlanStatus
from pyflightstream.run.cli import main
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import InputArtifactError
from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace
from tests.tier1_offline.test_goal024_rpm import ROTOR_BLOCK
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

TERMINATION = "SET_WAKE_TERMINATION_TIME_STEPS"

# --- the hand figures of the two fixtures -----------------------------------
# rotor_case(): VELOCITY 30 m/s, RPM 1200, DELTA_TIME 1e-4 s, 720 steps; its rotor
# block's diameter_m is 3.6576, so R = 1.8288 m. One revolution is
# 60 / (1200 * 1e-4) = 500 steps, so Omega / dtheta = 1200 / 60 * 500 = 1e4 per s.
CASE_R_M = 3.6576 / 2.0
CASE_OMEGA = 1200.0 * 2.0 * math.pi / 60.0
CASE_DTHETA = 2.0 * math.pi / 500.0
# The matrix row (_rotor_row): the same speeds and clock, and the ROTOR_BLOCK of
# test_goal024_rpm on its reference: diameter_m 1.2, so R = 0.6 m, hub at x = 0.
ROW_R_M = 0.6


def _steps(length: float, radius: float, v_ax: float) -> int:
    """FR-321 R2 by hand: n = ceil(L R Omega / (V_ax dtheta))."""
    return math.ceil(round(length * radius * CASE_OMEGA / (v_ax * CASE_DTHETA), 9))


def _built(case) -> tuple[list[str], Script]:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render().splitlines(), script


def _terminations(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith(TERMINATION)]


def _air(velocity: float) -> FluidState:
    return FluidState(
        velocity_m_per_s=velocity,
        density_kg_m3=1.225,
        pressure_pa=101325.0,
        temperature_k=288.15,
        viscosity_pa_s=1.789e-5,
        sonic_velocity_m_per_s=340.29,
        source="isa",
    )


def _rotor(velocity: str = "30.0", **settings: object):
    """rotor_case() at ``velocity`` in sea-level air, with these setup keys."""
    return rotor_case(VELOCITY=velocity).model_copy(
        update={"fluid": _air(float(velocity)), "solver": SolverSettings(**settings)}
    )


# --- FR-321: a length in rotor radii, 4R by default -------------------------


def test_p0340_wake_length_a_stated_length_becomes_the_steps_it_keeps():
    """P0340-WAKE-LENGTH, FR-321 R1 and R2: L = 4.1 R converts at V_ax = V_inf.

    4.1 * 1.8288 * 1e4 / 30 = 2499.36, rounded UP to 2500, so the wake kept at
    V_ax is never shorter than L; rounding to nearest would give 2499.
    """
    requirement = "FR-321"
    lines, script = _built(_rotor(wake_termination_length=4.1))
    expected = _steps(4.1, CASE_R_M, 30.0)
    assert expected == 2500, expected
    assert _terminations(lines) == [f"{TERMINATION} {expected}"], (requirement, lines)
    assert script.solver_setup is not None
    derived = script.solver_setup.derived
    assert derived["wake_termination_length"] == "4.1 R (stated)", derived
    assert derived["wake_termination_steps"] == "2500", derived
    assert derived["wake_termination_rule"] == "free_stream", derived
    assert float(derived["wake_termination_v_ax_m_s"]) == 30.0, derived


def test_p0340_wake_length_a_row_stating_steps_is_emitted_as_stated_the_control():
    """P0340-WAKE-LENGTH, FR-321 R4 control: a stated step count is not converted."""
    requirement = "FR-321"
    lines, script = _built(_rotor(wake_termination_steps=100))
    assert _terminations(lines) == [f"{TERMINATION} 100"], (requirement, lines)
    assert script.solver_setup is not None
    assert "wake_termination_length" not in script.solver_setup.derived, requirement


def test_p0340_wake_length_a_rotor_row_stating_nothing_keeps_four_radii():
    """P0340-WAKE-LENGTH, FR-321 R4 and R5: the 4R default, and its three recorded values.

    4 * 1.8288 * 1e4 / 30 = 2438.4, so 2439 steps; the snapshot the run record
    carries says the L asked, the V_ax with its rule, and the steps.
    """
    requirement = "FR-321"
    lines, script = _built(_rotor())
    assert _terminations(lines) == [f"{TERMINATION} 2439"], (requirement, lines)
    assert script.solver_setup is not None
    record = script.solver_setup.model_dump(mode="json")
    assert record["derived"] == {
        "wake_termination_length": "4 R (the default of FR-321)",
        "wake_termination_v_ax_m_s": "30",
        "wake_termination_rule": "free_stream",
        "wake_termination_steps": "2439",
    }, record.get("derived")


def test_p0340_wake_length_the_run_record_carries_the_three_values(tmp_path):
    """P0340-WAKE-LENGTH, FR-321 R5: a rotor point run through the workflow records them.

    The row turns 1200 rev/min at TASmps 30 with a 1e-4 s step; its reference
    states rotor_diameter_m = 1.2, so R = 0.6 m and 4R is 4 * 0.6 / (30 * 1e-4) = 800
    steps. The stub solver writes nothing, so the point fails for its outputs;
    the snapshot is in the part of the record every point carries.
    """
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import (
        StubSolver,
        _rotor_matrix,
        converged,
        make_library,
    )

    requirement = "FR-321"
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(
        "rotor_diameter_m = 1.2\n" + reference.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    matrix = _rotor_matrix(tmp_path)
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("MACH:0.2, REmi:11.77,", "TASmps:30.0,"),
        encoding="utf-8",
    )
    with warnings.catch_warnings(), pytest.raises(CampaignErrors):
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver("pass"),
        )
    (record,) = workspace.read_manifest()
    assert record.solver_setup is not None, (requirement, record.error)
    derived = record.solver_setup["derived"]
    assert derived["wake_termination_length"] == "4 R (the default of FR-321)", derived
    assert derived["wake_termination_rule"] == "free_stream", derived
    assert float(derived["wake_termination_v_ax_m_s"]) == pytest.approx(30.0), derived
    assert derived["wake_termination_steps"] == "800", derived


def _parity():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_parity_wake_under_test",
        Path(__file__).resolve().parents[2] / "scripts" / "check_parity.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0340_wake_length_the_parity_entry_names_only_the_added_line_on_a_rotor_script():
    """P0340-WAKE-LENGTH, FR-321 R6: the parity script names the termination line under FR-321
    only in the direction and on the scripts the requirement states: ADDED to a script that
    turns a rotor in time and whose base wrote none. A removed line, a changed count, and
    the line added to a steady script stay unnamed."""
    requirement = "FR-321"
    goldens = Path(__file__).parent / "goldens" / "workflows"
    for build in ("26.124", "25.100"):
        rotor = (goldens / f"unsteady_rotor__bare__{build}.txt").read_text(encoding="utf-8")
        (line,) = _terminations(rotor.splitlines())
        base = rotor.replace(line + "\n", "")
        assert base != rotor and not _terminations(base.splitlines()), build

        def named(old: str, new: str) -> str | None:
            entry = _parity().name_difference("scripts", "row.txt", old, new, {requirement})
            return entry.get("requirement")

        assert named(base, rotor) == requirement, (requirement, build)
        assert named(rotor, base) is None, ("a removed line", build)
        assert named(rotor, rotor.replace(line, f"{TERMINATION} 7")) is None, build
    steady = (goldens / "steady__full__26.124.txt").read_text(encoding="utf-8")
    added = steady.replace("INITIALIZE_SOLVER", f"{TERMINATION} 100\nINITIALIZE_SOLVER", 1)
    assert added != steady
    assert (
        _parity()
        .name_difference("scripts", "row.txt", steady, added, {requirement})
        .get("requirement")
        != requirement
    ), "a line added to a steady script"


# --- FR-322: one key states the termination ----------------------------------

PAIRS = [
    (("wake_termination_length", "6"), ("wake_termination_steps", "100")),
    (("wake_termination_length", "6"), ("wake_termination_revolutions", "2")),
    (("wake_termination_steps", "100"), ("wake_termination_revolutions", "2")),
]


def _setup_and_row(tmp_path: Path, preset: list[tuple[str, str]], row: list[tuple[str, str]]):
    workspace = _workspace(tmp_path)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + ROTOR_BLOCK, encoding="utf-8")
    setup = workspace.inputs_dir / "setups" / "s002.toml"
    setup.write_text(
        setup.read_text(encoding="utf-8") + "".join(f"{key} = {value}\n" for key, value in preset),
        encoding="utf-8",
    )
    extra = "".join(f" / {key}: {value}" for key, value in row)
    return workspace, _rotor_row(tmp_path, sweep="0.0", extra=extra)


def _plan(workspace, matrix):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )


@pytest.mark.parametrize("where", ["setup", "preset-and-row", "row"])
@pytest.mark.parametrize("pair", PAIRS, ids=lambda pair: f"{pair[0][0]}+{pair[1][0]}")
def test_p0340_wake_one_key_two_keys_are_refused_at_plan_naming_both(tmp_path, pair, where):
    """P0340-WAKE-ONE-KEY, FR-322 R1 and R4: two of the three keys reaching one row, from
    its setup, its preset and the row, or the row alone, are refused at plan, the message
    naming each key, its value and the file or column it comes from."""
    requirement = "FR-322"
    first, second = pair
    preset, row = {
        "setup": ([first, second], []),
        "preset-and-row": ([first], [second]),
        "row": ([], [first, second]),
    }[where]
    workspace, matrix = _setup_and_row(tmp_path, preset, row)
    with pytest.raises(MatrixError) as refused:
        _plan(workspace, matrix)
    message = str(refused.value)
    for key, value in pair:
        assert (
            f"{key} = {value}" in message
            or f"{key} = {float(value)}" in message
            or (f"{key} = {int(float(value))}" in message)
        ), (requirement, key, message)
    if preset:
        assert "setup preset 's002'" in message and "inputs/setups/s002.toml" in message, message
    if row:
        assert "VAR_NAMES_VALUES" in message, message
    assert "FR-322" in message, message


def test_p0340_wake_one_key_one_key_plans_the_control(tmp_path):
    """P0340-WAKE-ONE-KEY, FR-322 control: one key, in the preset or the row, plans READY."""
    requirement = "FR-322"
    for index, (preset, row) in enumerate(
        (([("wake_termination_length", "6")], []), ([], [("wake_termination_steps", "100")]))
    ):
        workspace, matrix = _setup_and_row(tmp_path / str(index), preset, row)
        plan = _plan(workspace, matrix)
        assert [entry.status for entry in plan.points] == [PlanStatus.READY], (
            requirement,
            [entry.error for entry in plan.points],
        )


@pytest.mark.parametrize(
    "key, value", [("wake_termination_steps", "100"), ("wake_termination_revolutions", "1")]
)
def test_p0340_wake_one_key_the_same_key_in_preset_and_row_is_one_key(tmp_path, key, value):
    """P0340-WAKE-ONE-KEY, FR-322 R4 control: the SAME key in the preset and in the row is one
    key, not two. Agreeing, the row plans READY; differing, it is refused by FR-316's
    comparison of the row with its preset, never as two termination keys."""
    requirement = "FR-322"
    workspace, matrix = _setup_and_row(tmp_path / "agree", [(key, value)], [(key, value)])
    plan = _plan(workspace, matrix)
    assert [entry.status for entry in plan.points] == [PlanStatus.READY], (
        requirement,
        [entry.error for entry in plan.points],
    )
    workspace, matrix = _setup_and_row(tmp_path / "differ", [(key, value)], [(key, "3")])
    with pytest.raises(MatrixError) as refused:
        _plan(workspace, matrix)
    message = str(refused.value)
    assert "FR-316" in message and "FR-322" not in message, (requirement, message)


def test_p0340_wake_one_key_the_builder_refuses_two_keys_too():
    """P0340-WAKE-ONE-KEY, FR-322 R2: a case built in Python is refused by the builder, the
    0.33.0 reading ("can only disagree") kept and every pair of the three joined to it."""
    requirement = "FR-322"
    for (first, a), (second, b) in PAIRS:
        case = _rotor(**{first: float(a), second: float(b)})
        with pytest.raises(CampaignConfigError, match="can only disagree") as refused:
            _built(case)
        assert first in str(refused.value) and second in str(refused.value), requirement


# --- FR-323: near hover ------------------------------------------------------


def _induced(thrust: float, radius: float) -> float:
    """v_i = sqrt(T / (2 rho A)), by hand at sea level."""
    return math.sqrt(thrust / (2.0 * 1.225 * math.pi * radius**2))


def test_p0340_wake_hover_a_stated_thrust_convects_the_wake_at_zero_speed():
    """P0340-WAKE-HOVER, FR-323 R1 and R2: at V_inf = 0, V_ax is v_i of the stated thrust."""
    requirement = "FR-323"
    lines, script = _built(_rotor("0.0", wake_termination_thrust_n=1000.0))
    v_i = _induced(1000.0, CASE_R_M)
    assert _terminations(lines) == [f"{TERMINATION} {_steps(4.0, CASE_R_M, v_i)}"], lines
    assert script.solver_setup is not None
    assert script.solver_setup.derived["wake_termination_rule"] == "induced_velocity", requirement


def test_p0340_wake_hover_a_revolution_cap_sets_the_steps_at_zero_speed():
    """P0340-WAKE-HOVER, FR-323 R3: a cap of 2 revolutions is 2 * 500 = 1000 steps."""
    requirement = "FR-323"
    lines, script = _built(_rotor("0.0", wake_termination_revolutions_cap=2.0))
    assert _terminations(lines) == [f"{TERMINATION} 1000"], (requirement, lines)
    assert script.solver_setup is not None
    assert script.solver_setup.derived["wake_termination_rule"] == "revolution_cap", requirement


def test_p0340_wake_hover_neither_key_at_zero_speed_is_refused_naming_both():
    """P0340-WAKE-HOVER, FR-323 R4: a length at V_inf = 0 with neither bound is refused."""
    requirement = "FR-323"
    with pytest.raises(CampaignConfigError) as refused:
        _built(_rotor("0.0"))
    message = str(refused.value)
    assert "wake_termination_thrust_n" in message, (requirement, message)
    assert "wake_termination_revolutions_cap" in message, (requirement, message)


def test_p0340_wake_hover_a_slow_rotor_whose_induced_velocity_exceeds_v_inf():
    """P0340-WAKE-HOVER, FR-323 R2: at 1 m/s the 1000 N thrust's v_i (6.23 m/s) wins."""
    requirement = "FR-323"
    v_i = _induced(1000.0, CASE_R_M)
    assert v_i > 1.0, v_i
    lines, script = _built(_rotor("1.0", wake_termination_thrust_n=1000.0))
    assert _terminations(lines) == [f"{TERMINATION} {_steps(4.0, CASE_R_M, v_i)}"], lines
    assert script.solver_setup is not None
    assert script.solver_setup.derived["wake_termination_rule"] == "induced_velocity", requirement


def test_p0340_wake_hover_forward_flight_keeps_the_free_stream_the_control():
    """P0340-WAKE-HOVER, FR-323 R2 control: at 30 m/s the same thrust's v_i is slower, so
    V_ax stays V_inf and the steps are the 4R default's 2439; a cap above them changes
    nothing."""
    requirement = "FR-323"
    lines, script = _built(
        _rotor("30.0", wake_termination_thrust_n=1000.0, wake_termination_revolutions_cap=10.0)
    )
    assert _terminations(lines) == [f"{TERMINATION} 2439"], (requirement, lines)
    assert script.solver_setup is not None
    assert script.solver_setup.derived["wake_termination_rule"] == "free_stream", requirement


@pytest.mark.parametrize("bound", ["wake_termination_thrust_n", "wake_termination_revolutions_cap"])
@pytest.mark.parametrize("count", ["wake_termination_steps", "wake_termination_revolutions"])
def test_p0340_wake_hover_a_bound_beside_a_count_is_refused(bound, count):
    """P0340-WAKE-HOVER, FR-323 R6: the two keys bound a length only."""
    requirement = "FR-323"
    with pytest.raises(CampaignConfigError) as refused:
        _built(_rotor(**{bound: 500.0, count: 2}))
    assert bound in str(refused.value) and count in str(refused.value), requirement


def test_p0340_wake_hover_a_cap_cuts_a_length_in_forward_flight_too():
    """P0340-WAKE-HOVER, FR-323 R3: the converted steps never exceed the cap, at any speed.

    At 30 m/s, 6 R is 6 * 1.8288 * 1e4 / 30 = 3657.6, so 3658 steps uncapped; a cap of
    one revolution is 500 steps, which win, and the rule recorded is the cap's.
    """
    requirement = "FR-323"
    assert _steps(6.0, CASE_R_M, 30.0) == 3658
    lines, script = _built(
        _rotor("30.0", wake_termination_length=6.0, wake_termination_revolutions_cap=1.0)
    )
    assert _terminations(lines) == [f"{TERMINATION} 500"], (requirement, lines)
    assert script.solver_setup is not None
    derived = script.solver_setup.derived
    assert derived["wake_termination_rule"] == "revolution_cap", (requirement, derived)
    assert float(derived["wake_termination_v_ax_m_s"]) == 30.0, derived


@pytest.mark.parametrize(
    "key, value",
    [
        ("wake_termination_length", 6.0),
        ("wake_termination_thrust_n", 1000.0),
        ("wake_termination_revolutions_cap", 2.0),
    ],
)
@pytest.mark.parametrize("factory", [steady_case, unsteady_case], ids=["steady", "rotorless"])
def test_p0340_wake_hover_a_length_or_bound_on_a_run_turning_no_rotor_is_refused(
    factory, key, value
):
    """P0340-WAKE-HOVER, FR-323 and FR-321 R4: a length, a thrust or a cap on a steady run or
    on an unsteady run that turns no rotor reaches no line, so it is refused, naming the key,
    rather than silently dropped."""
    requirement = "FR-323"
    case = factory().model_copy(update={"solver": SolverSettings(**{key: value})})
    with pytest.raises(CampaignConfigError) as refused:
        _built(case)
    message = str(refused.value)
    assert f"{key} = {value}" in message and "FR-321" in message, (requirement, message)


# --- FR-324: the wake end plane ----------------------------------------------


def test_p0340_wake_trefftz_a_stated_plane_writes_wake_termination_x_and_nothing_else():
    """P0340-WAKE-TREFFTZ, FR-324 R1: the plane is the one changed line, in INITIALIZE_SOLVER."""
    requirement = "FR-324"
    before, _ = _built(steady_case())
    after, _ = _built(
        steady_case().model_copy(update={"solver": SolverSettings(wake_termination_x=2.75)})
    )
    changed = [
        line
        for line in difflib.unified_diff(before, after, lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert changed == ["-WAKE_TERMINATION_X DEFAULT", "+WAKE_TERMINATION_X 2.75"], (
        requirement,
        changed,
    )
    head = after.index("INITIALIZE_SOLVER")
    assert "WAKE_TERMINATION_X 2.75" in after[head : head + 6], (requirement, after[head:])


def test_p0340_wake_trefftz_an_unstated_plane_writes_default_as_0330_did():
    """P0340-WAKE-TREFFTZ, FR-324 R2: unstated and DEFAULT render the same bytes, and the
    committed steady golden, unchanged by 0.34.0, carries WAKE_TERMINATION_X DEFAULT."""
    requirement = "FR-324"
    unstated, _ = _built(steady_case())
    default, _ = _built(
        steady_case().model_copy(update={"solver": SolverSettings(wake_termination_x="DEFAULT")})
    )
    assert unstated == default, requirement
    assert "WAKE_TERMINATION_X DEFAULT" in unstated, requirement
    golden = Path(__file__).parent / "goldens" / "workflows" / "steady__full__26.124.txt"
    assert "WAKE_TERMINATION_X DEFAULT" in golden.read_text(encoding="utf-8"), requirement


@pytest.mark.parametrize(
    "value",
    ["3 m", "4R", "4 R", "nan", "inf", float("nan"), float("inf"), "", "default", "TREFFTZ", True],
    ids=lambda value: repr(value),
)
def test_p0340_wake_trefftz_any_other_value_is_refused_naming_the_key_and_the_forms(value):
    """P0340-WAKE-TREFFTZ, FR-324 R3 and R4: a number with a unit, a distance in radii, a
    non-finite number, an empty value and any word other than DEFAULT are refused, so no
    such value reaches WAKE_TERMINATION_X."""
    requirement = "FR-324"
    with pytest.raises(ValidationError) as refused:
        SolverSettings(wake_termination_x=value)
    message = str(refused.value)
    assert "wake_termination_x" in message and "DEFAULT" in message, (requirement, message)
    assert "metres" in message, (requirement, message)


@pytest.mark.parametrize("value", ["2.75", "-1.5", "3"])
def test_p0340_wake_trefftz_a_bare_number_in_a_cell_or_a_preset_is_taken(value):
    """P0340-WAKE-TREFFTZ, FR-324 R1: the text a row cell carries is the number that
    WAKE_TERMINATION_X writes."""
    requirement = "FR-324"
    assert SolverSettings(wake_termination_x=value).wake_termination_x == float(value), requirement


def test_p0340_wake_trefftz_a_refused_value_stops_the_plan(tmp_path):
    """P0340-WAKE-TREFFTZ, FR-324 R3: refused at plan, from the preset, naming the key,
    before any script writes WAKE_TERMINATION_X."""
    requirement = "FR-324"
    workspace, matrix = _setup_and_row(tmp_path, [("wake_termination_x", '"4R"')], [])
    with pytest.raises((InputArtifactError, MatrixError)) as refused:
        _plan(workspace, matrix)
    message = str(refused.value)
    assert "setup preset 's002'" in message, (requirement, message)
    for words in ("wake_termination_x", "DEFAULT", "metres", "rotor radii", "FR-324"):
        assert words in message, (requirement, words, message)


# --- FR-325: the plan always warns -------------------------------------------

#: The two measured placements of the solver's default plane (FR-324), as plan
#: fixtures: the rotor case's at 5.5 R and the blades-only wheel's at 2.1 R
#: downstream of the hub, here the row's rotor at x = 0 with R = 0.6 m.
PLANES = {"rotor case": 5.5 * ROW_R_M, "blades-only wheel": 2.1 * ROW_R_M}


def _planned_wake(
    tmp_path: Path, *, iterations: int = 720, row: str = "", plane=None, hover: bool = False
):
    """Plan the one rotor row; return its wake warnings, statuses and written plan.

    ``hover`` sets the row's free stream to zero (TASmps and VELOCITY 0, sea-level
    air), so a stated thrust's induced velocity convects the wake.
    """
    workspace = _workspace(tmp_path)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + ROTOR_BLOCK, encoding="utf-8")
    extra = row + ("" if plane is None else f" / wake_termination_x: {plane}")
    matrix = _rotor_row(tmp_path, sweep="0.0", extra=extra)
    text = matrix.read_text(encoding="utf-8").replace(
        "TIME_ITERATIONS: 720", f"TIME_ITERATIONS: {iterations}"
    )
    if hover:
        text = text.replace("TASmps:30.0, REmi:1.20,", "TASmps:0.0,").replace(
            "VELOCITY: 30.0", "VELOCITY: 0.0"
        )
    matrix.write_text(text, encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    said = [
        str(item.message)
        for item in caught
        if issubclass(item.category, PyflightstreamWarning) and "FR-325" in str(item.message)
    ]
    assert plan.plan_file is not None
    points = json.loads(plan.plan_file.read_text(encoding="utf-8"))["points"]
    return said, [entry.status for entry in plan.points], points, (workspace, matrix)


def _rule(said: list[str], rule: str) -> list[str]:
    return [text for text in said if f"FR-325 {rule})" in text]


@pytest.mark.parametrize("length", [None, 6.0], ids=["4R-default", "6R-stated"])
def test_p0340_wake_plan_warn_too_few_revolutions_warns_and_enough_does_not(tmp_path, length):
    """P0340-WAKE-PLAN-WARN, FR-325 R1: the plan warns at the 4R default and at a larger L.

    The row's L R / (V dt) is 200 L steps (R = 0.6 m, V = 30 m/s, dt = 1e-4 s): 800
    at 4R, 1200 at 6R, against a revolution of 500 steps. 720 steps (1.44
    revolutions) are too few for either; 1500 are enough for both.
    """
    requirement = "FR-325"
    row = "" if length is None else f" / wake_termination_length: {length:g}"
    needed = (200.0 * (length or 4.0)) / 500.0
    few, statuses, _, _ = _planned_wake(tmp_path / "few", iterations=720, row=row)
    warned = _rule(few, "R1")
    assert len(warned) == 1, (requirement, few)
    assert f"L = {length or 4.0:g} R" in warned[0] and "'7001'" in warned[0], warned
    assert f"{needed:.3g} revolution(s)" in warned[0] and "1.44 revolution(s)" in warned[0], warned
    assert statuses == [PlanStatus.READY], requirement
    enough, statuses, _, _ = _planned_wake(tmp_path / "enough", iterations=1500, row=row)
    assert _rule(enough, "R1") == [], (requirement, enough)
    assert statuses == [PlanStatus.READY], requirement


def test_p0340_wake_plan_warn_a_step_count_states_its_length_against_four_radii(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R2: 100 steps keep 100 * 30 * 1e-4 / 0.6 = 0.5 R, below
    the 4R recommendation, and the plan warns; 1000 steps of a 1500-step run keep 5 R."""
    requirement = "FR-325"
    short, _, _, _ = _planned_wake(tmp_path / "short", row=" / wake_termination_steps: 100")
    warned = _rule(short, "R2")
    assert len(warned) == 1 and "0.5 R" in warned[0], (requirement, short)
    assert _rule(short, "R1") == [], short
    long, _, _, _ = _planned_wake(
        tmp_path / "long", iterations=1500, row=" / wake_termination_steps: 1000"
    )
    assert _rule(long, "R2") == [], (requirement, long)


@pytest.mark.parametrize("fixture", sorted(PLANES))
def test_p0340_wake_plan_warn_a_plane_before_the_length_warns_and_after_it_does_not(
    tmp_path, fixture
):
    """P0340-WAKE-PLAN-WARN, FR-325 R3 and R5: the two measured placements as fixtures, on a
    rotor row and a blades-only wheel alike. At 4R (2.4 m) the rotor case's plane (3.3 m)
    is after L and the wheel's (1.26 m) is before it; at 6R (3.6 m) both are before it."""
    requirement = "FR-325"
    plane = PLANES[fixture]
    at_4r, _, _, _ = _planned_wake(tmp_path / "4r", iterations=1500, plane=f"{plane:.4g}")
    before = plane < 4.0 * ROW_R_M
    assert len(_rule(at_4r, "R3")) == (1 if before else 0), (requirement, fixture, at_4r)
    at_6r, _, _, _ = _planned_wake(
        tmp_path / "6r",
        iterations=1500,
        row=" / wake_termination_length: 6",
        plane=f"{plane:.4g}",
    )
    warned = _rule(at_6r, "R3")
    assert len(warned) == 1 and "wake_termination_x" in warned[0], (requirement, at_6r)
    assert f"{plane / ROW_R_M:.3g} R downstream" in warned[0], warned
    # A stated plane is never the DEFAULT warning.
    assert _rule(at_4r, "R4") == [] and _rule(at_6r, "R4") == [], requirement


def test_p0340_wake_plan_warn_the_default_plane_always_warns_citing_both_placements(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R4: the plan cannot know where DEFAULT is, and says so."""
    requirement = "FR-325"
    said, statuses, _, _ = _planned_wake(tmp_path, iterations=1500)
    warned = _rule(said, "R4")
    assert len(warned) == 1, (requirement, said)
    for words in ("DEFAULT", "5.5 R", "RPT-130", "2.1 R", "RPT-137", "wake_termination_x"):
        assert words in warned[0], (requirement, words, warned[0])
    assert statuses == [PlanStatus.READY], requirement


def test_p0340_wake_plan_warn_the_warnings_change_neither_the_exit_nor_the_plan(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R6: the plan warns, and a row it warns about exits 0,
    plans READY and writes the plan an unwarned row writes, but for the plane it states."""
    requirement = "FR-325"
    warned, statuses, points, (workspace, matrix) = _planned_wake(tmp_path / "warned")
    assert _rule(warned, "R1") and _rule(warned, "R4"), (requirement, warned)
    quiet, quiet_statuses, quiet_points, _ = _planned_wake(
        tmp_path / "quiet", iterations=720, plane="100"
    )
    assert not _rule(quiet, "R4") and not _rule(quiet, "R3"), (requirement, quiet)
    assert statuses == quiet_statuses == [PlanStatus.READY], requirement
    for entry in (*points, *quiet_points):
        entry["wake_termination"].pop("plane")
    assert json.dumps(points).replace(str(tmp_path / "warned"), "<T>") == json.dumps(
        quiet_points
    ).replace(str(tmp_path / "quiet"), "<T>"), requirement
    assert main(["plan", str(matrix), "--workspace", str(workspace.root)]) == 0, requirement


def test_p0340_wake_plan_warn_the_plan_states_the_three_values(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 beside FR-321 R5: whether or not it warns, the plan
    states L, V_ax with its rule, and the steps."""
    requirement = "FR-325"
    workspace = _workspace(tmp_path)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + ROTOR_BLOCK, encoding="utf-8")
    plan = _plan(workspace, _rotor_row(tmp_path, sweep="0.0"))
    (entry,) = plan.points
    assert entry.wake_termination["steps"] == 800, (requirement, entry.wake_termination)
    assert "wake termination L = 4 R (default), V_ax 30 m/s (free_stream), 800 steps" in (
        plan.summary()
    ), plan.summary()


def test_p0340_wake_plan_warn_a_count_states_the_length_it_keeps_warned_or_not(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R2: the plan STATES the length a count keeps, whether or
    not it warns. 1000 steps of a 1500-step run keep 1000 * 30 * 1e-4 / 0.6 = 5 R, above
    4R and unwarned; 100 steps keep 0.5 R, stated and warned."""
    requirement = "FR-325"
    for name, iterations, steps, kept, warns in (
        ("long", 1500, 1000, "5", False),
        ("short", 720, 100, "0.5", True),
    ):
        said, _, _, (workspace, matrix) = _planned_wake(
            tmp_path / name, iterations=iterations, row=f" / wake_termination_steps: {steps}"
        )
        assert bool(_rule(said, "R2")) is warns, (requirement, name, said)
        summary = _plan(workspace, matrix).summary()
        assert (
            f"wake termination wake_termination_steps: {steps} steps, keeping about {kept} R "
            "of wake"
        ) in summary, (requirement, summary)


def test_p0340_wake_plan_warn_a_cap_that_cuts_the_length_is_named(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R1 with FR-323 R3: a cap that cuts L in forward flight.

    6 R is 200 * 6 = 1200 steps, which a 1500-step run reaches; a cap of one revolution
    keeps 500 steps, 500 * 30 * 1e-4 / 0.6 = 2.5 R, and the warning names the cap.
    """
    requirement = "FR-325"
    said, statuses, points, _ = _planned_wake(
        tmp_path,
        iterations=1500,
        row=" / wake_termination_length: 6 / wake_termination_revolutions_cap: 1",
    )
    warned = _rule(said, "R1")
    assert len(warned) == 1, (requirement, said)
    assert "the revolution cap keeps 500 steps" in warned[0], warned
    assert "about 2.5 R" in warned[0] and "L = 6 R" in warned[0], warned
    assert points[0]["wake_termination"]["steps"] == 500, points[0]["wake_termination"]
    assert statuses == [PlanStatus.READY], requirement


def test_p0340_wake_plan_warn_a_plane_on_either_side_of_a_hovering_rotor(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R3 at zero speed: with no free-stream sense the wake may
    leave either way, so a plane within L on EITHER side of the hub cuts it. The hub is at
    x = 0 and L is the 4R default, 2.4 m: a plane 1 R upstream (-0.6 m) or downstream
    (0.6 m) warns at 1 R; one 5 R upstream (-3.0 m) does not."""
    requirement = "FR-325"
    thrust = " / wake_termination_thrust_n: 1000"
    for name, plane, warns in (("up", "-0.6", True), ("down", "0.6", True), ("far", "-3.0", False)):
        said, statuses, points, _ = _planned_wake(
            tmp_path / name, iterations=1500, row=thrust, plane=plane, hover=True
        )
        assert points[0]["wake_termination"]["rule"] == "induced_velocity", points
        warned = _rule(said, "R3")
        assert len(warned) == (1 if warns else 0), (requirement, name, said)
        if warns:
            assert "lies 1 R downstream" in warned[0], (requirement, warned)
        assert statuses == [PlanStatus.READY], requirement


def test_p0340_wake_plan_warn_a_plane_the_plan_cannot_place_still_warns(tmp_path):
    """P0340-WAKE-PLAN-WARN, FR-325 R3: a stated plane on a rotor whose hub X is unknown (the
    reference states rotor_diameter_m and no rotor block) cannot be placed against L, and
    the plan says so rather than passing it in silence (the author's 'always warn')."""
    from tests.tier1_offline.test_matrix_run import _rotor_matrix, make_library

    requirement = "FR-325"
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(
        "rotor_diameter_m = 1.2\n" + reference.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    matrix = _rotor_matrix(tmp_path)
    matrix.write_text(
        matrix.read_text(encoding="utf-8")
        .replace("MACH:0.2, REmi:11.77,", "TASmps:30.0,")
        .replace("LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25 / wake_termination_x: 1.0"),
        encoding="utf-8",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    said = [str(item.message) for item in caught if "FR-325 R3)" in str(item.message)]
    assert len(said) == 1, (requirement, [str(item.message) for item in caught])
    for words in ("wake_termination_x = 1 m", "hub X is unknown", "cannot be placed"):
        assert words in said[0], (requirement, words, said[0])
    assert [entry.status for entry in plan.points] == [PlanStatus.READY], requirement


# --- the licensed confirmation LQ5 (RPT-130), checked before the seat is spent ------


def test_p0340_wake_length_the_lq5_kit_plans_ready_offline(tmp_path):
    """P0340-WAKE-LENGTH, FR-321 and FR-324: the LQ5 kit's two rows plan READY with no
    solver, keep 4R as 180 steps (L / (2 J) = 2.5 revolutions of 72 steps at J = 0.8), run
    288 steps, so the run reaches L; the control keeps WAKE_TERMINATION_X DEFAULT and is
    the one the plan warns about, the other row moves the plane to 8 R."""
    from tests.tier3_licensed import wake_lq5

    requirement = "FR-321"
    workspace_root = tmp_path / "lq5"
    wake_lq5.build(workspace_root, str(tmp_path / "FlightStream.exe"))
    from pyflightstream.workspace import CampaignWorkspace

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            workspace_root / wake_lq5.MATRIX,
            CampaignWorkspace(workspace_root),
            name="lq5_wake",
            recipes={},
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
    assert [entry.status for entry in plan.points] == [PlanStatus.READY] * 2, (
        requirement,
        [entry.error for entry in plan.points],
    )
    control, moved = (entry.wake_termination for entry in plan.points)
    assert control["steps"] == moved["steps"] == 180, (control, moved)
    assert control["run_steps"] == 288 and control["plane"] == "DEFAULT", control
    assert moved["plane"] == pytest.approx(8.0 * wake_lq5.R_M), moved
    said = [str(item.message) for item in caught if "FR-325" in str(item.message)]
    assert len(said) == 1 and "'9501'" in said[0] and "R4" in said[0], said


def test_p0340_wake_length_the_lq5_analysis_recovers_a_known_convection_speed(tmp_path):
    """P0340-WAKE-LENGTH, FR-321 R3: the analysis RPT-130 reads, on a synthetic tip vortex
    convecting at 1.15 V_inf and ending at 4.5 R, returns that speed and that end, and the
    slipstream line's induced velocity; the momentum ratio of CT = 0.1 is worked by hand."""
    from tests.tier3_licensed import wake_lq5 as kit

    requirement = "FR-321"
    v_ax = 1.15 * kit.V_INF
    n = kit.V_INF / (kit.J * 2.0 * kit.R_M)
    omega_b = kit.BLADES * 2.0 * math.pi * n
    dt = (kit.DELTA_THETA_DEG / 360.0) / n
    table = tmp_path / "P9502-LQ5_probes.csv"
    rows = ["POL,PROBE,X,Y,Z,FRAME,STEP,VX,VZ"]
    for index in range(kit.TIP_POINTS):
        x_r = kit.X_START_R + index * 0.1
        level = 1.0 if 0.0 <= x_r <= 4.55 else 0.01
        for step in range(1, 289):
            wave = level * math.cos(omega_b * (step * dt - x_r * kit.R_M / v_ax))
            rows.append(f"9502,{index + 1},{x_r * kit.R_M},0,1.6,PROP_SMRP,{step},49.0,{wave}")
    for index in range(kit.SLIP_POINTS):
        x_r = kit.X_START_R + index * 0.5
        for step in range(1, 289):
            axial = kit.V_INF * (1.1 if x_r > 0.0 else 1.0)
            rows.append(f"9502,{kit.TIP_POINTS + index + 1},{x_r},0,0.9,PROP_SMRP,{step},{axial},0")
    table.write_text("\n".join(rows) + "\n", encoding="utf-8")
    vz, vx = kit.probe_histories(table, "VZ"), kit.probe_histories(table, "VX")
    ratio, end = kit.convection_speed(kit.tip_line(vz, min(vz)))
    assert ratio == pytest.approx(1.15, rel=1e-6) and end == pytest.approx(4.5), (ratio, end)
    induced = dict(kit.slipstream(vx, min(vz) + kit.TIP_POINTS))
    assert induced[1.0] == pytest.approx(0.1) and induced[-1.0] == pytest.approx(0.0), induced
    thrust = 0.1 * kit.RHO * n**2 * (2.0 * kit.R_M) ** 4
    v_i = -kit.V_INF + math.sqrt(kit.V_INF**2 + 2.0 * thrust / (kit.RHO * math.pi * kit.R_M**2))
    assert kit.momentum_ratio(0.1) == pytest.approx(1.0 + v_i / 2.0 / kit.V_INF), requirement
