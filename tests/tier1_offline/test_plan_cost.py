"""Tier 1: the plan's cost table, and what each of its columns is a reading OF (FR-82).

Her design of 2026-09-11: "no plan, eu quero uma flag que ao ser ativada, volta
tambem um resumo de tempo de execucao esperado para cada polar tabelando o
tamanho da malha, numero total de trailing edges marcadas, configuracao do
farfield layers e acoplamento viscoso, se e steady ou unsteady, numero de
iteracoes temporais e tempo estimado", then "inclua tambem o numero de
processadores setados", then, when asked what the estimate could rest on, "eu
quero uma estimativa do tempo da rodada. Eu vou depois fazer um estudo de
escalabilidade mais completo e te passar os dados para calibrar melhhor o
modelo, por enquanto use o que voce tem."

The reproduction, as an operator types it::

    pyfs-matrix plan matriz.fs --workspace . --fs-version 26.123 --cost

WHAT THIS MODULE IS REALLY GUARDING is not that the table renders. Every column
of the first two writings of this feature rendered perfectly and three of them
were readings of the wrong thing:

* `panels` was the BOUNDARY COUNT, so a wing-body read 2 where its mesh holds
  14266, and a rotor sector read 3;
* `procs` and `TEs` each read a variable key NO ROW WRITES, so both printed the
  same value for every row in the table -- a dash and a zero -- and neither
  could ever have printed anything else;
* the expected time read the sample's step count off a manifest field that is
  null whenever the run's reductions were skipped, counting a 36 step run as
  ONE SOLVE and tabling her rotor point at 7013.5s against a recorded run of
  194.8s of that same point.

A column that cannot be wrong is a column nobody is measuring. So every
assertion below is built to DISCRIMINATE: the geometry's element count differs
from its boundary count, the marked families include one the geometry does not
carry, the two run types are fitted from different samples, and the expected
time is computed here from the arithmetic rather than by restating the
implementation's expression.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from pyflightstream._fsm import MESH_MARKER
from pyflightstream.cases import ReferenceData, RotorBlock, SimCase, SolverSettings, SweepAxis
from pyflightstream.run import estimate_point_cost, format_cost_table

#: The element count the fixture geometry states, deliberately unlike any
#: count of anything else in the file. A reader that returned the boundary
#: count, which is what the first writing did, returns 3 here.
ELEMENTS = 4321


def saved_simulation(path: Path, names: Sequence[str], elements: int = ELEMENTS) -> Path:
    """The smallest saved simulation carrying a mesh block, with a stated size.

    Built from the format's own shape rather than copied from a campaign
    geometry: those run to 9 MB and some are derivatives that may not be
    distributed. Reproduced exactly, including the element count on the
    first line after the marker, the second junk line the name reader
    skips, and head numbers STARTING AT 2, which is what seven of the
    eight real geometries do.
    """
    body = [MESH_MARKER, str(elements), "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    # `newline=""` because the CRLF is DATA and not formatting; the real
    # geometries are CRLF and this writes the bytes they carry.
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


PUSHER = RotorBlock(
    alias="PUSHER",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="X",
    diameter_m=3.6576,
    families_general=["S"],
    families_blades=[f"Blade{number}" for number in range(1, 7)],
    # The datum a blade's azimuth is measured from may not be the axis the
    # rotor turns about, so a rotor turning about X takes Z, exactly as her
    # r002 does.
    blade1={"azimuth_deg": 0.0, "zero": "Z"},
)


def steady_case(geometry: Path, **solver) -> SimCase:
    """A steady wing-body row."""
    return SimCase(
        sim_id="6001",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"WORKFLOW": "steady", "VELOCITY": "68.0"},
        geometry=str(geometry),
        solver=SolverSettings(**solver),
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        point={"alpha": 0.0, "beta": 0.0},
    )


def rotor_case(geometry: Path, revolutions: str = "1.5", **solver) -> SimCase:
    """An unsteady rotor row whose clock is an angle and a number of turns."""
    return SimCase(
        sim_id="6002",
        aircraft="NXROTOR",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="advance_ratio", values=[1.7]),
        rotors={"PUSHER": PUSHER},
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "49.0",
            "DELTA_THETA": "15",
            "REVOLUTIONS": revolutions,
            "CLOCK_MOTION": "PUSHER",
        },
        motions=[{"MOVING_BC_ALIAS": "PUSHER"}],
        geometry=str(geometry),
        solver=SolverSettings(**solver),
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        point={"alpha": 0.0, "beta": 0.0, "advance_ratio": 1.7},
    )


def recorded(
    run_id: str, seconds: float, recipe: str = "steady", reductions: object = None
) -> dict:
    """One manifest record as `_recorded_costs` hands it to the fit.

    The RECIPE is stated, because that is the fact the fit reads to decide
    whether a recorded run is comparable. The first writing inferred it from
    whether the record carried a reduction block, and every unsteady fixture
    here -- which states none -- was classified steady.
    """
    return {
        "run_id": run_id,
        "wall_time_s": seconds,
        "recipe": recipe,
        "reductions": reductions,
    }


# --------------------------------------------------------------------------
# The columns that are READINGS
# --------------------------------------------------------------------------


def test_the_mesh_column_is_the_size_the_file_states_and_not_its_boundary_count(tmp_path):
    """The first writing read `len(boundary_names(...))` and called it panels.

    It rendered a number for every row, so nothing looked wrong until the
    column was held against a real geometry: a wing-body read 2 where its
    mesh block states 14266. The fixture here carries THREE boundaries and
    states 4321 elements, so the two readings cannot be confused.
    """
    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    cost = estimate_point_cost(steady_case(geometry), run_id="run/a", recorded=[])
    assert cost.panels == ELEMENTS
    assert cost.panels != 3, "the column is reading the boundary count again"


def test_a_geometry_with_no_mesh_block_leaves_the_column_blank(tmp_path):
    """A wrong mesh size is compared against other rows; a blank is not."""
    empty = tmp_path / "not-a-simulation.fsm"
    empty.write_text("nothing here\n", encoding="utf-8")
    cost = estimate_point_cost(steady_case(empty), run_id="run/a", recorded=[])
    assert cost.panels is None
    # THE MESH FIELD, not "a dash somewhere in the row". The row already
    # carries dashes in `layers`, `steps` and `procs`, so `"-" in line` held
    # whatever the mesh cell printed, and a mutant rendering `0` there
    # survived (the QA lens scoring M26, 2026-09-11).
    table = format_cost_table([cost]).splitlines()
    header, row = table[0].split(), table[2].split()
    assert row[header.index("mesh")] == "-"


def test_the_marked_trailing_edges_are_the_families_the_geometry_actually_carries(tmp_path):
    """Two readings of this column printed 0 for every row in the table.

    Both read a key nobody writes: `VORTICITY_DRAG_BOUNDARIES` off the
    row's variables, then `solver.vorticity_drag_boundaries`, which is not
    a field. The selection is `vorticity_drag_families`, family NAMES, and
    the builder leaves out the families the opened geometry does not carry.

    THE FIXTURE NAMES THREE AND THE GEOMETRY CARRIES TWO OF THEM, so a
    reader that counts the statement answers 3, one that counts the
    geometry answers 3 as well, and only one that does what the builder
    does answers 2.
    """
    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    case = steady_case(geometry, vorticity_drag_families=["W", "B", "GHOST"])
    cost = estimate_point_cost(case, run_id="run/a", recorded=[])
    assert cost.trailing_edges == 2


def test_a_row_marking_no_trailing_edges_reports_a_measured_zero(tmp_path):
    geometry = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    cost = estimate_point_cost(rotor_case(geometry), run_id="run/b", recorded=[])
    assert cost.trailing_edges == 0


def test_the_setup_columns_are_read_from_the_settings_the_script_is_built_from(tmp_path):
    """`procs` read a variable key no row writes and dashed for every row.

    Asserted against values that are not defaults, so a reader returning
    the model's own default cannot pass.
    """
    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    case = steady_case(geometry, max_threads=8, farfield_layers=5, viscous_coupling=True)
    cost = estimate_point_cost(case, run_id="run/a", recorded=[])
    assert cost.processors == 8
    assert cost.farfield_layers == 5
    assert cost.viscous_coupling is True


def test_a_rotor_row_states_its_steps_as_an_angle_and_a_number_of_turns(tmp_path):
    """The rotor row is the row whose cost anyone wants, and it read a dash.

    The first writing asked `unsteady_time_stepping`, which answers for the
    `unsteady` recipe and not for `unsteady_rotor`, and then fell back to a
    `TIME_ITERATIONS` variable a rotor row does not state.

    1.5 turns at 15 degrees a step is 24 steps to the revolution and 36 in
    all, computed here from the angles rather than by calling the same
    resolver the implementation calls.
    """
    geometry = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    cost = estimate_point_cost(rotor_case(geometry), run_id="run/b", recorded=[])
    assert cost.unsteady is True
    assert cost.time_iterations == 36


def test_a_steady_row_states_no_step_count_at_all(tmp_path):
    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    cost = estimate_point_cost(steady_case(geometry), run_id="run/a", recorded=[])
    assert cost.unsteady is False
    assert cost.time_iterations is None


# --------------------------------------------------------------------------
# The one column that is an EXTRAPOLATION
# --------------------------------------------------------------------------


def test_the_expected_time_is_fitted_from_the_recorded_runs_of_the_same_run_type(tmp_path):
    """Steady and unsteady differ by more than any other term, so they do not mix.

    Two recorded steady runs at 10s and 20s average 15s a solve. One
    recorded unsteady run of 36 steps in 180s is 5s a step, so a point
    asking 36 steps is 180s. The two samples are deliberately far apart:
    a fit that pooled them would give neither number.
    """
    wb = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    history = [
        recorded("run/s1", 10.0),
        recorded("run/s2", 20.0),
        recorded("run/u1", 180.0, "unsteady_rotor"),
    ]
    steps = {"run/u1": 36}

    steady = estimate_point_cost(
        steady_case(wb),
        run_id="run/a",
        recorded=history,
        steps_by_run=steps,
    )
    assert steady.samples == 2
    assert steady.seconds == pytest.approx(15.0)

    unsteady = estimate_point_cost(
        rotor_case(rotor),
        run_id="run/b",
        recorded=history,
        steps_by_run=steps,
    )
    assert unsteady.samples == 1
    assert unsteady.seconds == pytest.approx(180.0)


def test_the_fit_is_linear_in_the_steps_the_point_asks_for(tmp_path):
    """Half the revolutions is half the time, at the same rate.

    0.5 turns at 15 degrees is 12 steps, so at 5s a step the point is 60s
    where the 36 step point is 180s. This is what makes the model a model
    rather than the mean of the history.
    """
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    history = [recorded("run/u1", 180.0, "unsteady_rotor")]
    steps = {"run/u1": 36}
    short = estimate_point_cost(
        rotor_case(rotor, revolutions="0.5"),
        run_id="run/b",
        recorded=history,
        steps_by_run=steps,
    )
    assert short.time_iterations == 12
    assert short.seconds == pytest.approx(60.0)


def test_a_recorded_run_whose_step_count_is_unknown_is_left_out_of_the_fit(tmp_path):
    """The defect measured on her workspace on 2026-09-11.

    Her recorded rotor run carries `reductions.time_iterations = null`,
    because every reduction of that point was skipped, and the fit read
    the null as ONE SOLVE. The rate came out 36 times too large and the
    point was tabled at 7013.5s against its own recorded 194.8s.

    A sample whose work is unknown cannot calibrate a per-step rate. Here
    the good sample says 5s a step; a fit that counted the unknown one as
    one solve would land between that and 180s a step, so the assertion
    discriminates rather than merely passing.
    """
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    history = [
        recorded("run/u1", 180.0, "unsteady_rotor"),
        recorded("run/u2", 180.0, "unsteady_rotor", reductions={"time_iterations": None}),
    ]
    cost = estimate_point_cost(
        rotor_case(rotor),
        run_id="run/b",
        recorded=history,
        steps_by_run={"run/u1": 36},
    )
    assert cost.samples == 1, "the sample with no step count entered the fit"
    assert cost.seconds == pytest.approx(180.0)
    assert "1 further recorded run(s) state no step count" in cost.basis


def test_a_point_with_no_comparable_recorded_run_gets_no_number_at_all(tmp_path):
    """A figure that looks like a measurement and is not is worse than a blank."""
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    cost = estimate_point_cost(
        rotor_case(rotor),
        run_id="run/b",
        recorded=[
            recorded(
                "run/s1",
                10.0,
            )
        ],
    )
    assert cost.seconds is None
    assert cost.samples == 0
    assert "no recorded run of this run type" in cost.basis
    assert "unknown" in format_cost_table([cost])


def test_every_comparable_run_lacking_a_step_count_offers_no_estimate(tmp_path):
    """Not the same state as having no history, and it does not say it is."""
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    history = [
        recorded("run/u1", 180.0, "unsteady_rotor"),
        recorded("run/u2", 200.0, "unsteady_rotor"),
    ]
    cost = estimate_point_cost(rotor_case(rotor), run_id="run/b", recorded=history, steps_by_run={})
    assert cost.seconds is None
    assert cost.samples == 0
    assert "state no step count" in cost.basis


# --------------------------------------------------------------------------
# What the table SAYS about its own number
# --------------------------------------------------------------------------


def test_the_basis_under_the_table_is_each_run_types_own(tmp_path):
    """It was the FIRST ROW'S, printed under the whole table.

    A table holding a steady row and an unsteady one carried "fitted from
    2 recorded steady run(s)" under both, which is a false sentence about
    the unsteady row and one that reads as a measurement.
    """
    wb = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    history = [
        recorded("run/s1", 10.0),
        recorded("run/s2", 20.0),
        recorded("run/u1", 180.0, "unsteady_rotor"),
    ]
    steps = {"run/u1": 36}
    table = format_cost_table(
        [
            estimate_point_cost(
                steady_case(wb), run_id="run/a", recorded=history, steps_by_run=steps
            ),
            estimate_point_cost(
                rotor_case(rotor), run_id="run/b", recorded=history, steps_by_run=steps
            ),
        ]
    )
    lines = [line for line in table.splitlines() if line.startswith("  ")]
    assert len(lines) == 2, table
    steady_line = next(line for line in lines if line.startswith("  steady rows:"))
    unsteady_line = next(line for line in lines if line.startswith("  unsteady rows:"))
    assert "2 recorded steady run(s)" in steady_line
    assert "1 recorded unsteady run(s)" in unsteady_line
    assert "steady run(s)" not in unsteady_line.replace("unsteady run(s)", "")


def test_the_table_says_the_time_is_an_extrapolation_before_it_says_anything_else(tmp_path):
    """Her instruction was to estimate with what there is, so the row says so.

    Until her scalability study lands, a reader must not be able to take
    this number for a measurement of the point in front of them.
    """
    wb = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    cost = estimate_point_cost(steady_case(wb), run_id="run/a", recorded=[recorded("run/s1", 10.0)])
    table = format_cost_table([cost])
    assert "EXPECTED TIME IS AN EXTRAPOLATION AND NOT A MEASUREMENT" in table
    assert "crude model" in cost.basis
    assert "is not a measurement of this point" in cost.basis


def test_every_column_her_design_named_has_a_heading(tmp_path):
    """Her list, read back off the rendered header rather than off the model."""
    wb = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    header = format_cost_table(
        [
            estimate_point_cost(
                steady_case(wb),
                run_id="run/a",
                recorded=[],
            )
        ]
    ).splitlines()[0]
    for column in ("mesh", "TEs", "layers", "visc", "type", "steps", "procs", "expected"):
        assert column in header, column


# --------------------------------------------------------------------------
# The one mutant that survives, and the measurement that explains it
# --------------------------------------------------------------------------


def test_the_two_steppers_agree_on_a_rotor_rows_step_count(tmp_path):
    """Why `time_steps_of`'s rotor branch cannot be killed by a mutant.

    Mutating `if case.recipe == "unsteady_rotor"` so a rotor row falls
    through to `unsteady_time_stepping` leaves every assertion in this
    module green. That is not a hole in the guard: the two resolvers were
    measured against five shapes of rotor row -- angular with a speed,
    angular with none, an explicit clock, half an explicit clock, and
    revolutions that are not a whole number of steps -- and they agree on
    the count in all five, because `unsteady_time_stepping` DELEGATES the
    angular form to `rotor_time_stepping`.

    THE BRANCH STAYS ANYWAY, and this test is the reason it can. That
    delegation is documented as a deliberate choice of one release that
    "should be revisited", so a reader that relied on it would break
    silently on the day it is. The branch routes a rotor row to the rotor
    resolver because that is what it is; this test pins the equivalence
    that makes the two interchangeable TODAY, so if it ever stops holding,
    it stops loudly here rather than quietly in a cost column.
    """
    from pyflightstream.cases.workflows import (
        _optional_rotor_speed,
        rotor_time_stepping,
        unsteady_time_stepping,
    )

    geometry = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    case = rotor_case(geometry)
    through_the_rotor = rotor_time_stepping(case, speed=_optional_rotor_speed(case))
    through_the_general = unsteady_time_stepping(case)
    assert through_the_rotor.time_iterations == through_the_general.time_iterations == 36


# --------------------------------------------------------------------------
# The requirement's own two demands on the model
# --------------------------------------------------------------------------


def test_the_fit_is_scored_against_a_point_it_was_not_fitted_on(tmp_path):
    """FR-82: "a model measured on its own training set measures nothing".

    Two recorded unsteady runs of DIFFERENT lengths train the model, and a
    third of a length neither of them has is held out. The prediction must
    land on the held-out run's actual time.

    THE HOLD-OUT DISCRIMINATES BECAUSE THE LENGTHS DIFFER. A model that
    ignored the steps and predicted the mean of the training wall times
    would answer 90s where the truth is 180s, so this cannot be satisfied
    by averaging, which is the whole failure the requirement names.
    """
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    training = [
        recorded("run/short", 60.0, "unsteady_rotor"),
        recorded("run/medium", 120.0, "unsteady_rotor"),
    ]
    steps = {"run/short": 12, "run/medium": 24}

    # HELD OUT: 36 steps, and it really took 180s at the same rate.
    held_out_actual = 180.0
    predicted = estimate_point_cost(
        rotor_case(rotor),
        run_id="run/held-out",
        recorded=training,
        steps_by_run=steps,
    ).seconds

    assert predicted == pytest.approx(held_out_actual, rel=0.1)
    mean_of_training = (60.0 + 120.0) / 2
    assert predicted != pytest.approx(mean_of_training), (
        "the model answered the mean of its training wall times, which is a model "
        "that has not read the steps"
    )


def test_the_fit_never_reads_a_recorded_iteration_count(tmp_path):
    """FR-82 records that 89 of 95 recorded iteration counts are untrustworthy.

    They were read off the first page of the solver log, so any run that
    outlasted its first page recorded that page's last row. The requirement
    asked for them to be re-derived or excluded with the calibration-set
    size said beside the estimate.

    THIS FIT DOES NEITHER, BECAUSE IT NEVER READS THEM. The work of a
    recorded run is the step count its own ROW asks for, resolved from
    `DELTA_THETA` and `REVOLUTIONS` by the same function that resolves it
    for a point about to be planned. So a record carrying a wrong
    `iterations` moves no estimate, which this asserts by handing the fit a
    record whose `iterations` is the classic wrong 100.
    """
    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    poisoned = recorded("run/u1", 180.0, "unsteady_rotor")
    poisoned["iterations"] = 100  # the first page's last row, not the run's length
    cost = estimate_point_cost(
        rotor_case(rotor),
        run_id="run/b",
        recorded=[poisoned],
        steps_by_run={"run/u1": 36},
    )
    # 180s over the 36 steps the ROW states, not over the 100 the record claims.
    assert cost.seconds == pytest.approx(180.0)
    assert cost.seconds != pytest.approx(180.0 / 100 * 36)


# --------------------------------------------------------------------------
# The assembler, which nothing reached
# --------------------------------------------------------------------------


def test_point_costs_fills_the_sweep_point_before_it_costs_it(tmp_path):
    """The defect `point_costs`' own docstring records, with no case until now.

    A swept row states `ADVANCE_RATIO: sweep` and the VALUE is the POINT's, so
    a rotor row costed from the un-filled row names no rotor speed and reports
    no step count at all. A mutant that stopped filling the point survived
    every case in the two new modules, because both of them call
    `estimate_point_cost` directly and nothing called the assembler above it
    (the QA lens scoring M27, 2026-09-11).

    36 steps is what 1.5 revolutions at 15 degrees works out to, and it is
    reachable ONLY through the filled point: the row alone cannot resolve the
    rotor speed its clock is measured against.
    """
    from pyflightstream.run import CampaignPlan, PlanStatus, PointPlan, point_costs

    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    case = rotor_case(rotor).model_copy(update={"point": {}})
    plan = CampaignPlan(
        campaign="camp",
        fs_version="26.123",
        points=[
            PointPlan(
                run_id="camp/sim_6002/a+00.0_b+00.0_j+01.7",
                sim_id="6002",
                point={"alpha": 0.0, "beta": 0.0, "advance_ratio": 1.7},
                script_name=None,
                status=PlanStatus.READY,
            )
        ],
    )

    class _NoRuns:
        """A workspace that has recorded nothing, so only the columns are read."""

        manifest_path = tmp_path / "runs.json"

    rows = point_costs(plan, cases_by_sim_id={"6002": case}, workspace=_NoRuns())
    assert len(rows) == 1
    assert rows[0].run_id == "camp/sim_6002/a+00.0_b+00.0_j+01.7"
    assert rows[0].time_iterations == 36


def test_point_costs_gives_no_row_to_a_point_whose_simulation_it_was_not_given(tmp_path):
    """A row of blanks would read as a measurement of a point nobody planned."""
    from pyflightstream.run import CampaignPlan, PlanStatus, PointPlan, point_costs

    plan = CampaignPlan(
        campaign="camp",
        fs_version="26.123",
        points=[
            PointPlan(
                run_id="camp/sim_9999/a+00.0",
                sim_id="9999",
                point={"alpha": 0.0},
                script_name=None,
                status=PlanStatus.READY,
            )
        ],
    )

    class _NoRuns:
        manifest_path = tmp_path / "runs.json"

    assert point_costs(plan, cases_by_sim_id={}, workspace=_NoRuns()) == []
