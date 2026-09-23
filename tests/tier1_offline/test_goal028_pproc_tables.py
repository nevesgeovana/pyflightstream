"""Tier 1, 0.24.0: the three pproc tables are CONSUMED, each through the step a campaign runs.

`[phase_locked]`, `[equations]` and `[glossary]` were fields of the pproc spec
once before while nothing read them, and were withdrawn for it. What this file
holds is therefore not that the tables BIND, which the three `test_goal026_item*`
modules beside it hold, but that each one CHANGES WHAT A CAMPAIGN WRITES:

- `[phase_locked]`: `pyfs-matrix post` writes the table the definitions page
  defines, the mean AT EACH AZIMUTH across the last revolutions, one row per
  azimuthal position; a run that turned too little loses that table and nothing
  else; a pproc without the table keeps the passage series.
- `[equations]`: the derived columns are in the unsteady polar, after the plots
  and before the setup, evaluated from that row; a symbol that is no column
  refuses the block and says so, and is never a column of `NA`.
- `[glossary]` and the guides: `pyfs-workspace init`, `pyfs-matrix plan` and
  `pyfs-matrix post` write the two pages into `inputs/pproc`, idempotently.

EVERY EXPECTED VALUE is worked from the definitions page or by numpy from the
written plots table, never from the module under test. The histories are neither
constant nor linear, so a mean along the window, a last value and a median each
give another number than the mean across revolutions.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.products import read_csv_table
from tests.tier1_offline.test_matrix_cli import _workflow_plan_args, make_planned_workspace
from tests.tier1_offline.test_post_products import (
    PLOTS_HEADER,
    _products_manifest,
    _unsteady_workspace,
)

#: Twelve steps, four per revolution, two blades, blade one's datum at 30 degrees,
#: turning in the NEGATIVE sense. Neither constant nor linear.
STEPS = 12
PER_REVOLUTION = 4.0
DATUM = 30.0
RPM = -1200.0
TOTAL = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0, 5.0, 8.0]
BLADE1 = [2.0, 7.0, 1.0, 8.0, 2.0, 8.0, 1.0, 8.0, 2.0, 8.0, 4.0, 5.0]
BLADE2 = [1.0, 4.0, 1.0, 4.0, 2.0, 1.0, 3.0, 5.0, 6.0, 2.0, 3.0, 7.0]


def _history() -> str:
    table = "Time-step,FX_MRP_TOTAL,FX_LOCAL_Blade1,FX_LOCAL_Blade2\n" + "".join(
        f"{i}.0000,{TOTAL[i - 1]:.5f},{BLADE1[i - 1]:.5f},{BLADE2[i - 1]:.5f},\n"
        for i in range(1, STEPS + 1)
    )
    return PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Newtons\n"


def _plan(**phase_locked) -> dict[str, object]:
    """What a flat rotor row of this clock records, planned WITHOUT a [phase_locked] table."""
    return {
        "window_stated": True,
        "time_iterations": STEPS,
        "steps_per_revolution": PER_REVOLUTION,
        "blades": 2,
        "rpm": RPM,
        "blade1_azimuth_deg": DATUM,
        "blade_families": ["Blade1", "Blade2"],
        "time_average": {"windows": [[9, 12]], "window_from": "LAST_REVS_AVG = 1"},
        "phase_locked": phase_locked
        or {
            "windows": [[9, 10], [11, 12]],
            "period_steps": 2,
            "window_from": "the row's window, cut into blade passages of 2 steps",
        },
        "per_blade": {"windows": [[9, 12]], "period_steps": 2, "window_from": "the row's window"},
    }


def _workspace(tmp_path, pproc: str):
    workspace = _unsteady_workspace(tmp_path, reductions=_plan(), rows=STEPS)
    (workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt").write_text(
        _history(), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n' + pproc, encoding="utf-8"
    )
    return workspace


def _post(workspace) -> int:
    from pyflightstream.run.cli import main

    return main(["post", "--workspace", str(workspace.root)])


def _probes(workspace) -> Path:
    return workspace.root / "post" / "products" / "probes"


def _written_history(workspace) -> dict[str, np.ndarray]:
    """The plots table the stage WROTE, which is what every reduction is taken over."""
    columns, rows = read_csv_table(_probes(workspace) / "AL-020_plots.csv")
    return {name: np.array([float(row[name]) for row in rows]) for name in columns}


def _azimuth_of_blade(step: int, position: int) -> float:
    """The definitions page's convention, worked here: datum, sense, step, blade spacing."""
    sense = 1.0 if RPM > 0 else -1.0
    return (DATUM + position * 360.0 / 2 + sense * step * 360.0 / PER_REVOLUTION) % 360.0


# --- [phase_locked] -----------------------------------------------------------


def test_the_table_is_one_row_per_azimuth_and_each_value_the_mean_across_revolutions(tmp_path):
    workspace = _workspace(
        tmp_path, "\n[phase_locked]\nmin_revolutions = 3.0\nlast_revolutions_avg = 2.0\n"
    )
    assert _post(workspace) == 0
    columns, rows = read_csv_table(_probes(workspace) / "AL-020_phase_locked.csv")
    assert "AZIMUTH" in columns and "WINDOW" not in columns, columns

    # ONE ROW PER AZIMUTHAL POSITION OF THE REVOLUTION, from 0 towards 360. The
    # last revolution is steps 9 to 12, and blade one is at 30 - 90 * step.
    expected_azimuths = sorted(_azimuth_of_blade(step, 0) for step in (9, 10, 11, 12))
    assert expected_azimuths == [30.0, 120.0, 210.0, 300.0]
    assert [float(row["AZIMUTH"]) for row in rows] == expected_azimuths
    assert {row["REVOLUTIONS"] for row in rows} == {"2"}, rows
    assert {(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows} == {("5", "12")}

    # THE ORACLE, by search and not by arithmetic on offsets: for each row's
    # azimuth, every step of the last two revolutions (5 to 12) at which THAT
    # blade is at THAT azimuth, averaged with numpy.
    history = _written_history(workspace)
    window = range(5, STEPS + 1)
    for row in rows:
        azimuth = float(row["AZIMUTH"])
        for name, position in (
            ("FX_MRP_TOTAL", 0),
            ("FX_LOCAL_Blade1", 0),
            ("FX_LOCAL_Blade2", 1),
        ):
            at = [s for s in window if abs(_azimuth_of_blade(s, position) - azimuth) < 1e-9]
            assert len(at) == 2, (name, azimuth, at)
            expected = float(np.mean([history[name][s - 1] for s in at]))
            assert float(row[name]) == pytest.approx(expected, abs=1e-5), (name, azimuth, at)

    # AND IT IS NONE OF THE NUMBERS A WRONG REDUCTION GIVES: at 30 degrees blade
    # one is at steps 8 and 12, so the total is (6 + 8) / 2.
    first = rows[0]
    assert float(first["FX_MRP_TOTAL"]) == pytest.approx(7.0, abs=1e-5)
    assert float(first["FX_MRP_TOTAL"]) != pytest.approx(float(np.mean(TOTAL[4:])), abs=1e-3)
    assert float(first["FX_MRP_TOTAL"]) != pytest.approx(TOTAL[-1], abs=1e-3)
    # Blade two is at 30 degrees when blade one is at 210: steps 6 and 10.
    assert float(first["FX_LOCAL_Blade2"]) == pytest.approx((1.0 + 2.0) / 2, abs=1e-5)

    entry = _products_manifest(workspace)["products"]["probes/AL-020_phase_locked.csv"]
    assert entry["shape"] == "azimuthal" and entry["revolutions"] == 2.0, entry
    assert entry["windows"] == [[5, 12]], entry


def test_a_run_that_turned_too_little_loses_this_table_and_nothing_else(tmp_path):
    """Three revolutions against a minimum of five: a named skip, and every neighbour written."""
    workspace = _workspace(
        tmp_path, "\n[phase_locked]\nmin_revolutions = 5.0\nlast_revolutions_avg = 2.0\n"
    )
    assert _post(workspace) == 0
    names = {path.name for path in _probes(workspace).iterdir()}
    assert "AL-020_phase_locked.csv" not in names, names
    assert {"AL-020_per_blade.csv", "AL-020_time_average.csv", "AL-020_plots.csv"} <= names
    manifest = _products_manifest(workspace)
    reason = manifest["skipped"]["probes/AL-020_phase_locked.csv"]
    assert "3.0" in reason and "5.0" in reason and "phase-locked" in reason, reason
    assert any(key.endswith("_uns_avg.csv") for key in manifest["products"]), manifest["products"]


def test_the_minimum_met_exactly_generates_it(tmp_path):
    workspace = _workspace(
        tmp_path, "\n[phase_locked]\nmin_revolutions = 3.0\nlast_revolutions_avg = 3.0\n"
    )
    assert _post(workspace) == 0
    _columns, rows = read_csv_table(_probes(workspace) / "AL-020_phase_locked.csv")
    assert {row["REVOLUTIONS"] for row in rows} == {"3"}, rows
    assert float(rows[0]["FX_MRP_TOTAL"]) == pytest.approx((1.0 + 6.0 + 8.0) / 3, abs=1e-5)


def test_a_pproc_without_the_table_keeps_the_passage_series(tmp_path):
    """Absent is not zero: the file is what it was, one row per blade passage."""
    workspace = _workspace(tmp_path, "")
    assert _post(workspace) == 0
    columns, rows = read_csv_table(_probes(workspace) / "AL-020_phase_locked.csv")
    assert "WINDOW" in columns and "AZIMUTH" not in columns, columns
    assert [(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows] == [("9", "10"), ("11", "12")]
    assert float(rows[0]["FX_MRP_TOTAL"]) == pytest.approx((5.0 + 3.0) / 2, abs=1e-5)


def test_removing_the_table_after_the_run_brings_the_passages_back(tmp_path):
    """A record planned UNDER a table, posted with a pproc that no longer has one."""
    from tests.tier1_offline.test_goal028_explained_products import _give

    workspace = _workspace(tmp_path, "")
    _give(
        workspace,
        reductions=_plan(
            windows=[[5, 12]], shape="azimuthal", revolutions=2.0, steps_per_revolution=4.0
        ),
    )
    assert _post(workspace) == 0
    columns, rows = read_csv_table(_probes(workspace) / "AL-020_phase_locked.csv")
    assert "WINDOW" in columns, columns
    assert [(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows] == [("9", "10"), ("11", "12")]


def test_a_revolution_that_is_not_a_whole_number_of_steps_is_read_between_them():
    """2.5 steps per revolution, the history `step ** 2`, two revolutions ending at step 10.

    Worked by hand. The last revolution holds steps 8, 9 and 10; one revolution
    earlier is 5.5, 6.5 and 7.5, read linearly: 30.5, 42.5 and 56.5. So the means
    are (64 + 30.5) / 2, (81 + 42.5) / 2 and (100 + 56.5) / 2.
    """
    from pyflightstream.post.unsteady import TimestepSeries, phase_locked_rows

    steps = np.arange(1, 11)
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"Q": (steps.astype(float) ** 2)[:, None]},
        sources=(),
    )
    rows = phase_locked_rows(
        series,
        ["Q"],
        last_step=10,
        revolutions=2.0,
        steps_per_revolution=2.5,
        blade1_azimuth_deg=0.0,
    )
    by_step = {row["STEP"]: row for row in rows}
    assert sorted(by_step) == [8, 9, 10]
    assert by_step[8]["Q"] == pytest.approx(47.25)
    assert by_step[9]["Q"] == pytest.approx(61.75)
    assert by_step[10]["Q"] == pytest.approx(78.25)
    # Step 10 is 10 * 144 = 1440 = 0 degrees, step 8 is 72, step 9 is 216.
    assert [row["STEP"] for row in rows] == [10, 8, 9]
    assert [row["AZIMUTH"] for row in rows] == pytest.approx([0.0, 72.0, 216.0])


@pytest.mark.parametrize("sense", [1.0, -1.0])
def test_three_blades_are_each_tabulated_by_their_own_azimuth_in_either_sense(sense):
    """Two blades cannot tell the sign of a blade's offset: half a turn either way is
    the same place. Three can. The oracle is a SEARCH: every step of the window at
    which that blade, by the page's formula, is at the row's azimuth."""
    from pyflightstream.post.unsteady import TimestepSeries, phase_locked_rows

    per_revolution, datum, last = 6.0, 20.0, 18
    steps = np.arange(1, last + 1)
    rng = np.random.default_rng(7)
    fields = {f"FX_LOCAL_B{k}": rng.uniform(-5, 5, size=last)[:, None] for k in (1, 2, 3)}
    series = TimestepSeries(
        steps=steps, times_s=None, points=np.zeros((1, 3)), fields=fields, sources=()
    )
    rows = phase_locked_rows(
        series,
        list(fields),
        last_step=last,
        revolutions=2.0,
        steps_per_revolution=per_revolution,
        blade1_azimuth_deg=datum,
        sense=sense,
        blades=3,
        blade_families=["B1", "B2", "B3"],
    )
    assert len(rows) == 6

    def azimuth(step: int, position: int) -> float:
        return (datum + position * 120.0 + sense * step * 360.0 / per_revolution) % 360.0

    for row in rows:
        for position in range(3):
            at = [
                s
                for s in range(7, last + 1)
                if abs((azimuth(s, position) - float(row["AZIMUTH"]) + 180.0) % 360.0 - 180.0)
                < 1e-9
            ]
            assert len(at) == 2, (position, row["AZIMUTH"], at)
            name = f"FX_LOCAL_B{position + 1}"
            expected = float(np.mean([fields[name][s - 1, 0] for s in at]))
            assert row[name] == pytest.approx(expected), (name, row["AZIMUTH"], at)


def test_a_history_that_does_not_hold_the_revolutions_is_a_named_skip(tmp_path):
    """The exported history starts at step 9; two revolutions need 5 to 12."""
    workspace = _workspace(
        tmp_path, "\n[phase_locked]\nmin_revolutions = 3.0\nlast_revolutions_avg = 2.0\n"
    )
    lines = _history().splitlines(keepends=True)
    dropped = {f"{i}." for i in range(1, 9)}
    kept = [line for line in lines if line[:2] not in dropped]
    (workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt").write_text(
        "".join(kept), encoding="utf-8"
    )
    assert _post(workspace) == 0
    reason = _products_manifest(workspace)["skipped"]["probes/AL-020_phase_locked.csv"]
    assert "steps 5 to 12" in reason and "steps 9 to 12" in reason, reason


def test_each_rotor_is_gated_and_windowed_on_its_own_revolution():
    """Twelve steps are three turns of a rotor at four steps a turn and one and a half of
    one at eight. A minimum of two generates the first and skips the second; a depth of
    one and a half turns of the first is its last six steps."""
    from pyflightstream.cases import PhaseLockedSpec
    from pyflightstream.cases.windows import regate

    passages = {"windows": [[9, 10], [11, 12]], "period_steps": 2}
    plan = {
        "time_iterations": 12,
        "steps_per_revolution": 4.0,
        "time_average": {"windows": [[9, 12]]},
        "rotors": {
            "LIFT": {"steps_per_revolution": 4.0, "period_steps": 2, "phase_locked": passages},
            "PUSHER": {
                "steps_per_revolution": 8.0,
                "period_steps": 4,
                "phase_locked": {"windows": [[9, 12]], "period_steps": 4},
            },
            # A clock and no blade count: a skip no table cures, and it stands.
            "LOST": {
                "steps_per_revolution": 4.0,
                "blades": None,
                "phase_locked": {"skipped": "no blade count"},
            },
        },
    }
    fresh = regate(plan, PhaseLockedSpec(min_revolutions=2.0, last_revolutions_avg=1.5))
    assert fresh is not None
    lift = fresh["rotors"]["LIFT"]["phase_locked"]
    assert lift["windows"] == [[7, 12]] and lift["shape"] == "azimuthal", lift
    assert (lift["revolutions"], lift["steps_per_revolution"]) == (1.5, 4.0), lift
    pusher = fresh["rotors"]["PUSHER"]["phase_locked"]
    assert "1.5" in pusher["skipped"] and "2.0" in pusher["skipped"], pusher
    assert fresh["rotors"]["LOST"]["phase_locked"] == {"skipped": "no blade count"}
    # THE RECORD IS NEVER REWRITTEN.
    assert plan["rotors"]["LIFT"]["phase_locked"] is passages
    assert regate(plan, None) is None, "no table and nothing planned under one: nothing moves"


def test_the_plan_of_a_row_whose_pproc_declares_the_table_is_azimuthal():
    """RPM 1200 at 1e-4 s is 500 steps a turn; 720 steps turn 1.44. One turn is 221 to 720."""
    from pyflightstream.cases import PhaseLockedSpec, PprocSpec, SimCase, SweepAxis
    from pyflightstream.cases.workflows import reduction_windows

    def plan_with(pproc):
        case = SimCase(
            sim_id="7001",
            aircraft="RotorRig",
            recipe="unsteady_rotor",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={
                "VELOCITY": "30.0",
                "RPM": "1200",
                "BLADES": "4",
                "DELTA_TIME": "0.0001",
                "TIME_ITERATIONS": "720",
                "LAST_REVS_AVG": "0.25",
            },
            pproc=pproc,
        )
        return reduction_windows(case)

    table = PprocSpec(phase_locked=PhaseLockedSpec(min_revolutions=1.0, last_revolutions_avg=1.0))
    entry = plan_with(table)["phase_locked"]
    assert entry["windows"] == [[221, 720]] and entry["shape"] == "azimuthal", entry
    # WITHOUT THE TABLE the plan is the passages of the row's window, as it was.
    legacy = plan_with(PprocSpec())["phase_locked"]
    assert legacy["windows"] == [[596, 720]] and "shape" not in legacy, legacy
    assert plan_with(table)["per_blade"] == plan_with(PprocSpec())["per_blade"]


# --- [equations] --------------------------------------------------------------

EQUATIONS = """
[equations.RATIO]
expression = "THRUST / sqrt(FX_LOCAL_Blade1**2 + 1)"
meshes_alias = "TOTAL"

[equations.THRUST]
expression = "-FX * 2"
meshes_alias = "TOTAL"
frame = "MRP"
"""


def _polar(workspace) -> tuple[list[str], dict[str, str]]:
    (path,) = (workspace.root / "post" / "products" / "polars").glob("*_uns_avg.csv")
    columns, rows = read_csv_table(path)
    return list(columns), rows[0]


def test_the_derived_columns_are_in_the_unsteady_polar_evaluated_from_that_row(tmp_path):
    workspace = _workspace(tmp_path, EQUATIONS)
    assert _post(workspace) == 0
    columns, row = _polar(workspace)

    # NAMED <NAME>_<alias>, in the order the chain needs and not the file's.
    assert "THRUST_TOTAL" in columns and "RATIO_TOTAL" in columns, columns
    assert columns.index("THRUST_TOTAL") < columns.index("RATIO_TOTAL")
    # AFTER THE PLOTS, BEFORE THE SETUP of the row.
    assert columns.index("FX_LOCAL_Blade2") < columns.index("THRUST_TOTAL")
    setup = [name for name in ("run_id", "sim_id", "status") if name in columns]
    assert len(setup) == 3, columns
    assert all(columns.index("RATIO_TOTAL") < columns.index(name) for name in setup)

    # THE ORACLE: the window is steps 9 to 12, and `FX` with frame MRP and alias
    # TOTAL is the column FX_MRP_TOTAL.
    history = _written_history(workspace)
    thrust = -float(np.mean(history["FX_MRP_TOTAL"][8:12])) * 2
    blade = float(np.mean(history["FX_LOCAL_Blade1"][8:12]))
    assert float(row["THRUST_TOTAL"]) == pytest.approx(thrust, abs=1e-5)
    assert float(row["RATIO_TOTAL"]) == pytest.approx(thrust / np.sqrt(blade**2 + 1), abs=1e-5)
    assert thrust == pytest.approx(-10.5)  # (5 + 3 + 5 + 8) / 4 = 5.25, by hand
    assert not [k for k in _products_manifest(workspace)["skipped"] if k.endswith("#equations")]


def test_a_symbol_that_is_no_column_refuses_the_block_and_is_never_a_column_of_na(tmp_path):
    workspace = _workspace(
        tmp_path,
        '\n[equations.GOOD]\nexpression = "FX_MRP_TOTAL * 2"\nmeshes_alias = "TOTAL"\n'
        '\n[equations.CTX]\nexpression = "CT * 2"\nmeshes_alias = "PUSHER"\nframe = "SMRP"\n',
    )
    with pytest.warns(PyflightstreamWarning, match="CTX"):
        assert _post(workspace) == 0
    columns, _row = _polar(workspace)
    # WHOLE OR ABSENT: not the good one without the bad one, and no NA column.
    assert "CTX_PUSHER" not in columns and "GOOD_TOTAL" not in columns, columns
    skipped = _products_manifest(workspace)["skipped"]
    (key,) = [name for name in skipped if name.endswith("#equations")]
    reason = skipped[key]
    assert "[equations.CTX]" in reason and "'CT'" in reason, reason
    for tried in ("CT_PUSHER_SMRP", "CT_SMRP_PUSHER", "CT_PUSHER"):
        assert tried in reason, reason
    assert "FX_MRP_TOTAL" in reason, "the refusal lists the columns there are"


def test_a_symbol_is_about_the_alias_before_it_is_an_exact_name():
    """The setup of a row carries the native export's own `CL`, one instant of the last
    step; `CL` of an equation about WING is the plotted `CL_WING`, averaged."""
    from pyflightstream.post.equations import resolve_symbol

    held = ["RHO", "CL", "CL_WING", "CL_WING_MRP", "CL_MRP_WING"]
    assert resolve_symbol("CL", alias="WING", frame=None, columns=held) == "CL_WING"
    assert resolve_symbol("CL", alias="WING", frame="MRP", columns=held) == "CL_WING_MRP"
    assert resolve_symbol("CL", alias="WING", frame="MRP", columns=held[:3]) == "CL_WING"
    assert resolve_symbol("CL", alias="TAIL", frame=None, columns=held) == "CL"
    assert resolve_symbol("RHO", alias="WING", frame="MRP", columns=held) == "RHO"
    assert resolve_symbol("CQ", alias="WING", frame="MRP", columns=held) is None


def test_an_expression_is_parsed_and_never_executed():
    from pydantic import ValidationError

    from pyflightstream.cases import PprocSpec

    for hostile in (
        "__import__('os').system('echo x')",
        "FX.real",
        "FX[0]",
        "open('x')",
        "FX if FX else 1",
        "lambda: 1",
        "'a' * 3",
        "FX // 2",
        "sqrt(x=4)",
    ):
        with pytest.raises(ValidationError) as caught:
            PprocSpec(equations={"E": {"expression": hostile, "meshes_alias": "A"}})
        assert "arithmetic" in str(caught.value), hostile

    spec = PprocSpec(
        equations={
            "E": {
                "expression": "-abs(min(FX, 2)) ** 2 + max(1, 3) / sqrt(4) + degrees(radians(90))",
                "meshes_alias": "A",
            }
        }
    )
    assert spec.equations["E"].symbols() == ["FX"]


def test_the_arithmetic_is_the_arithmetic():
    """Worked by hand: -|min(3, 2)|**2 + max(1, 3) / sqrt(4) + 90 = -4 + 1.5 + 90."""
    from pyflightstream._expressions import evaluate_expression

    value = evaluate_expression(
        "-abs(min(FX, 2)) ** 2 + max(1, 3) / sqrt(4) + degrees(radians(90))", {"FX": 3.0}.get
    )
    assert value == pytest.approx(87.5)
    assert evaluate_expression("2 ** 3 ** 2 - (1 - 4) * 2", {}.get) == pytest.approx(518.0)
    assert evaluate_expression("cos(0) + sin(0) + tan(0)", {}.get) == pytest.approx(1.0)


def test_a_cell_the_row_does_not_hold_is_na_in_that_cell_and_the_rest_is_evaluated():
    from types import SimpleNamespace

    from pyflightstream.post.equations import apply_equations

    notes: list[str] = []
    added, values = apply_equations(
        [{"J": None, "FX_P": 4.0}, {"J": 0.5, "FX_P": 4.0}, {"J": 0.0, "FX_P": 4.0}],
        {"E": SimpleNamespace(expression="FX / J", meshes_alias="P", frame=None)},
        ["E"],
        columns=["J", "FX_P"],
        where="polars/x.csv",
        notes=notes,
    )
    assert added == ["E_P"]
    assert values == [{"E_P": None}, {"E_P": 8.0}, {"E_P": None}]
    assert len(notes) == 1 and "row 1" in notes[0] and "row 3" in notes[0], notes


# --- the guides and [glossary] ------------------------------------------------


def _guides(workspace) -> list[Path]:
    return [workspace.inputs_dir / "pproc" / name for name in GUIDES]


GUIDES = ("VARIABLES.md", "WRITING-EQUATIONS.md")


def test_pyfs_workspace_init_writes_the_guides_where_a_pproc_is_written(tmp_path, capsys):
    from pyflightstream.workspace.cli import main

    assert main(["init", str(tmp_path / "camp")]) == 0
    for name in GUIDES:
        assert (tmp_path / "camp" / "inputs" / "pproc" / name).is_file(), name
    assert "VARIABLES.md" in capsys.readouterr().out


def test_pyfs_matrix_plan_writes_them_with_the_glossary_and_only_when_they_differ(tmp_path, capsys):
    from pyflightstream.run.cli import main

    workspace = make_planned_workspace(tmp_path)
    for guide in _guides(workspace):
        guide.unlink(missing_ok=True)  # a workspace made before the guides existed
    folder = workspace.inputs_dir / "pproc"
    with open(folder / "p001.toml", "a", encoding="utf-8") as handle:
        handle.write('\n[glossary]\nCTX = "my own coefficient"\n')
    (folder / "NOTES.md").write_text("mine\n", encoding="utf-8")

    assert main(_workflow_plan_args(workspace)) == 0
    out = capsys.readouterr().out
    variables, equations = _guides(workspace)
    assert variables.is_file() and equations.is_file()
    assert out.count("guide written:") == 2, out
    text = variables.read_text(encoding="utf-8")
    assert "Your own definitions" in text
    assert "`CTX`: my own coefficient (from p001.toml)" in text

    # IDEMPOTENT: a second plan touches neither page and says nothing.
    before = [(guide.stat().st_mtime_ns, guide.read_bytes()) for guide in _guides(workspace)]
    assert main(_workflow_plan_args(workspace)) == 0
    assert "guide written:" not in capsys.readouterr().out
    assert before == [
        (guide.stat().st_mtime_ns, guide.read_bytes()) for guide in _guides(workspace)
    ]
    assert (folder / "NOTES.md").read_text(encoding="utf-8") == "mine\n"

    # A GLOSSARY THAT MOVED moves the variables page, and only that page.
    with open(folder / "p001.toml", "a", encoding="utf-8") as handle:
        handle.write('CTY = "another"\n')
    assert main(_workflow_plan_args(workspace)) == 0
    assert capsys.readouterr().out.count("guide written:") == 1
    assert "`CTY`: another" in variables.read_text(encoding="utf-8")


def test_pyfs_matrix_post_writes_them_too_and_counts_no_guide_as_a_product(tmp_path, capsys):
    workspace = _workspace(tmp_path, "")
    for guide in _guides(workspace):
        guide.unlink(missing_ok=True)
    assert _post(workspace) == 0
    assert all(guide.is_file() for guide in _guides(workspace))
    assert "VARIABLES.md" not in capsys.readouterr().out
    assert not [k for k in _products_manifest(workspace)["products"] if k.endswith(".md")]


def test_every_toml_example_of_the_generated_guide_is_one_the_spec_accepts(tmp_path):
    """A page that says it is generated is trusted, so its examples are run."""
    import tomllib

    from pyflightstream.cases import PprocSpec
    from pyflightstream.post.guides import write_pproc_guides

    _variables, guide = write_pproc_guides(tmp_path)
    text = guide.read_text(encoding="utf-8")
    blocks = [block.split("```")[0] for block in text.split("```toml\n")[1:]]
    assert len(blocks) >= 4, blocks
    for block in blocks:
        PprocSpec(**tomllib.loads(block))
    chained = PprocSpec(**tomllib.loads(blocks[1]))
    assert chained.equation_order() == ["T", "CT_FLIGHT"]


def test_every_column_the_variables_page_lists_has_a_definition(tmp_path):
    from pyflightstream.post._tables import CONTEXT_COLUMNS
    from pyflightstream.post.guides import VARIABLE_DEFINITIONS, write_pproc_guides
    from pyflightstream.post.products import (
        PHASE_LOCKED_COLUMNS,
        ROTOR_COEFFICIENT_COLUMNS,
        UNSTEADY_AXIS_COLUMNS,
    )

    listed = {
        *CONTEXT_COLUMNS,
        *PHASE_LOCKED_COLUMNS,
        *ROTOR_COEFFICIENT_COLUMNS,
        *UNSTEADY_AXIS_COLUMNS,
    }
    assert not sorted(listed - set(VARIABLE_DEFINITIONS))
    variables, _guide = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    assert "`RHO`: kg/m3." in text and "`CT_<alias>`: -. Thrust coefficient" in text
