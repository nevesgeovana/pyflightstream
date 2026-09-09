"""PFS-2029.15.01 and .15.02: the campaign's CSV products round-trip and carry her numbers.

The synthetic case here is one loads table with two surfaces at alpha -2,
the numbers of the author's recorded wing-body point at Mach 0.20 (her
loads table of 2026-08-03), so the polar row this module writes is measured
against a row she wrote, column by column, at her five decimals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.post.products import (
    COEFFICIENT_COLUMNS,
    POLAR_COLUMNS,
    SECTION_COLUMNS,
    ProductError,
    ReferenceValues,
    group_coefficients,
    polar_file_name,
    polar_row,
    read_csv_table,
    write_plots_table,
    write_polar_table,
    write_recorded_polar,
    write_sections_table,
)
from pyflightstream.results import parse_loads

FIXTURES = Path(__file__).parent / "fixtures"

LOADS = """\




                              Aerodynamic loads


     Simulation file:                            c:/campaign/POLAR-3207_M20AL-020BE+000.fsm
     Angle of attack (Deg)                       -2.000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   68.058
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        1.000
     Solver model:                               Subsonic (Prandtl-Glauert)
     Solver mode:                                Steady
     Reference velocity (m/s)                    68.058
     Reference length (m)                        2.526
     Reference area (m^2)                        50.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             11771675.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            198
     ----------------------------------------------------------------------------------------------------
     Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
     ----------------------------------------------------------------------------------------------------
     W,+0.0193288,+0.0000000,+0.1620516,+0.1631176,+0.0012085,+0.0124530,+0.0000000,-0.0077298,+0.0000000
     B,+0.0081038,+0.0000000,+0.0251063,+0.0251653,+0.0000333,+0.0071894,-0.0000000,-0.0892137,+0.0000000
     Total,+0.0274326,+0.0000000,+0.1871579,+0.1882829,+0.0012418,+0.0196424,-0.0000000,-0.0969435,+0.0000000
     ----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #7012026
     Company  : Altair
     Date: 8/3/2026, Time: 2305 hours (local)
"""

#: Her recorded row for the whole configuration at alpha -2 (group 1 of her
#: polar 3207 at Mach 0.20), the twenty-four coefficients at five decimals.
HER_ROW = (
    "-2.00000 0.00000 0.20000 11.77168 0.02744 0.00000 0.18744 0.00000 -0.09694 0.00000 "
    "0.02088 0.00000 0.18828 0.00000 -0.09694 0.00000 0.02088 0.00000 0.18828 0.00000 "
    "-0.09694 0.00000 0.01964 0.00124"
).split()

REFERENCE = ReferenceValues(sref_m2=50.0, cref_m=2.526, bref_m=20.0, xmom_m=9.152)


def _loads():
    return parse_loads(LOADS)


def test_a_polar_row_carries_her_numbers():
    """Body, stability and wind axes from the loads table, at five decimals, equal her row."""
    loads = _loads()
    coefficients = group_coefficients(loads, ["Blade1", "S", "N", "W", "B"], bref_m=20.0)
    assert coefficients.families_used == ("W", "B"), "families the table lacks are left out"
    row = polar_row(
        loads.angle_of_attack_deg,
        0.2,
        loads.reynolds / 1e6,
        coefficients,
        cref_m=2.526,
        bref_m=20.0,
    )
    assert [f"{v:.5f}" for v in row] == HER_ROW


def test_a_group_the_table_carries_none_of_sums_to_zero():
    coefficients = group_coefficients(_loads(), ["Blade1", "S"], bref_m=20.0)
    assert coefficients.families_used == ()
    assert coefficients.drag == coefficients.lift == coefficients.pitch == 0.0


def test_polar_table_round_trips(tmp_path):
    """The CSV a reader takes apart is the one written: columns, rows, values."""
    loads = _loads()
    coefficients = group_coefficients(loads, ["W", "B"], bref_m=20.0)
    row = polar_row(-2.0, 0.2, loads.reynolds / 1e6, coefficients, cref_m=2.526, bref_m=20.0)
    target = write_polar_table(
        tmp_path / polar_file_name("3207", 0.2, "1"),
        polar="3207",
        description="STEADY_WB",
        group="1",
        reference=REFERENCE,
        rows=[row],
    )
    assert target.name == "3207_M20_g01.csv"
    columns, rows = read_csv_table(target)
    assert columns == POLAR_COLUMNS
    assert len(rows) == 1
    assert (
        rows[0]["POLAR"] == "3207"
        and rows[0]["DESCRIPTION"] == "STEADY_WB"
        and rows[0]["GROUP"] == "1"
    )
    assert rows[0]["SREF"] == "50.00000" and rows[0]["XMOM"] == "9.15200"
    assert [rows[0][c] for c in COEFFICIENT_COLUMNS] == HER_ROW
    # A row of the wrong width is refused, and so is a file whose rows do not fit its header.
    with pytest.raises(ProductError, match="values"):
        write_polar_table(
            tmp_path / "bad.csv",
            polar="1",
            description="x",
            group="1",
            reference=REFERENCE,
            rows=[row[:3]],
        )
    (tmp_path / "torn.csv").write_text("A,B\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ProductError, match="line 2"):
        read_csv_table(tmp_path / "torn.csv")


SLOADS = """\




                              FlightStream Surface Sectional Loads


     Simulation file:                            c:/campaign/P.fsm
     Angle of attack (Deg)                       .000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   68.058
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        .004
     Solver model:                               Subsonic (Prandtl-Glauert)
     Solver mode:                                Unsteady
     Reference velocity (m/s)                    68.058
     Reference length (m)                        2.526
     Reference area (m^2)                        50.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             11771700.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            3134
     ----------------------------------------------------------------------------------------------------
     Number of Surface Sections:                 2
     ----------------------------------------------------------------------------------------------------
     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment
     ----------------------------------------------------------------------------------------------------
     -0.9909E+01, 0.2065E+01,-0.1073E+00, 0.5604E-01, 0.1157E+03, 0.6680E+03, 0.7589E+02,
     -0.9728E+01, 0.2082E+01,-0.1033E+00, 0.5585E-01, 0.1038E+03, 0.9663E+03, 0.1364E+03,
     ----------------------------------------------------------------------------------------------------
     Force Units: Newtons
     Moment Units: Newton-Meter
     Software : Flightstream
     Company  : Research In Flight (RIF)
     Date: 8/3/2026, Time: 2305 hours (local)
"""


def test_sections_table_round_trips(tmp_path):
    target = write_sections_table(
        tmp_path / "sections" / "P_sections.csv", SLOADS, point="P", mach=0.2
    )
    assert target is not None
    columns, rows = read_csv_table(target)
    assert columns == SECTION_COLUMNS
    assert len(rows) == 2
    assert rows[0]["POINT"] == "P" and rows[0]["VINF"] == "68.05800" and rows[0]["RE"] == "11.77170"
    assert (
        rows[0]["Offset"] == "-9.90900"
        and rows[0]["Fx"] == "115.70000"
        and rows[1]["Moment"] == "136.40000"
    )
    # An export declaring no section, which a run without a distribution
    # leaves, is no product at all.
    none = SLOADS.replace(
        "Number of Surface Sections:                 2",
        "Number of Surface Sections:                 0",
    )
    none = (
        "\n".join(line for line in none.splitlines() if not line.strip().startswith("-0.9")) + "\n"
    )
    assert (
        write_sections_table(tmp_path / "sections" / "Q_sections.csv", none, point="Q", mach=0.2)
        is None
    )


PLOTS = """\




                              FlightStream Unsteady Solver Plots


     Simulation file:                            c:/campaign/P.fsm
     Angle of attack (Deg)                       .000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   50.000
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        .004
     Solver model:                               Subsonic (Prandtl-Glauert)
     Solver mode:                                Unsteady
     Reference velocity (m/s)                    100.000
     Reference length (m)                        2.526
     Reference area (m^2)                        50.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             11771700.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            2
----------------------------------------------------------------------------------------------------
Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL,FX_MRP_TOTAL,MACH1
----------------------------------------------------------------------------------------------------
1.0000,.22538,.0000,1411.9,.20000,
2.0000,.22600,.0010,1412.0,.20100,
----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #7012026
     Company  : Altair
     Date: 8/3/2026, Time: 2305 hours (local)
"""


def test_plots_table_round_trips(tmp_path):
    """Coefficient columns come to the free stream, (vref / vinf)^2 = 4 here; loads do not."""
    target = write_plots_table(tmp_path / "plots" / "P_plots.csv", PLOTS)
    assert target is not None
    columns, rows = read_csv_table(target)
    assert columns == ("Time-step", "CL_MRP_TOTAL", "CDI_MRP_TOTAL", "FX_MRP_TOTAL", "MACH1")
    assert rows[0]["CL_MRP_TOTAL"] == "0.90152", "0.22538 times four"
    assert rows[1]["CDI_MRP_TOTAL"] == "0.00400"
    assert rows[0]["FX_MRP_TOTAL"] == "1411.90000" and rows[1]["MACH1"] == "0.20100"


def test_an_unreadable_plots_export_is_refused_naming_it(tmp_path):
    with pytest.raises(ProductError, match="P_plots.csv"):
        write_plots_table(tmp_path / "plots" / "P_plots.csv", "not an export at all\n")


def test_write_recorded_polar_writes_one_table_per_group_and_the_sections(tmp_path):
    """The whole polar: a point folder with its loads table and its sectional export."""
    polar = tmp_path / "POLAR-3207"
    point = polar / "POLAR-3207_M20AL-020BE+000"
    point.mkdir(parents=True)
    (point / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
    (point / "POLAR-3207_M20AL-020BE+000_sloads.txt").write_text(SLOADS, encoding="utf-8")
    written = write_recorded_polar(
        polar,
        tmp_path / "out",
        groups={"1": ["W", "B"], "3": ["W"], "5": ["Blade1"]},
        reference={
            "SREF": 50.0,
            "CREF": 2.526,
            "BREF": 20.0,
            "XMOM": 9.152,
            "YMOM": 0.0,
            "ZMOM": 0.0,
        },
        description="STEADY_WB",
        mach=0.2,
    )
    names = [p.relative_to(tmp_path / "out").as_posix() for p in written]
    assert names == [
        "3207_M20_g01.csv",
        "3207_M20_g03.csv",
        "3207_M20_g05.csv",
        "sections/POLAR-3207_M20AL-020BE+000_sections.csv",
    ]
    _, rows = read_csv_table(tmp_path / "out" / "3207_M20_g01.csv")
    assert [rows[0][c] for c in COEFFICIENT_COLUMNS] == HER_ROW
    _, empty = read_csv_table(tmp_path / "out" / "3207_M20_g05.csv")
    assert empty[0]["CLB"] == "0.00000", "a group of absent families sums to zero"


def test_a_point_under_sideslip_is_refused_naming_it(tmp_path):
    """The wind-axis turn through sideslip is checked against nothing, so it is refused."""
    from pyflightstream.post.products import PolarPoint, ProductError
    from pyflightstream.post.products import _polar_rows as polar_rows

    text = LOADS.replace(
        "Side-slip angle (Deg)                       .000",
        "Side-slip angle (Deg)                      2.000",
    )
    assert text != LOADS, "the fixture's sideslip line moved"
    path = tmp_path / "a+02.0.txt"
    path.write_text(text, encoding="utf-8")
    point = PolarPoint(name="a+02.0", loads=parse_loads(text), loads_path=path)
    with pytest.raises(ProductError) as caught:
        polar_rows([point], ["W"], mach=0.2, reference=REFERENCE)
    message = str(caught.value)
    assert "a+02.0.txt" in message and "2.0" in message and "sideslip" in message


def test_the_mach_code_rounds_rather_than_truncates():
    from pyflightstream.post.products import _mach_code

    assert _mach_code(0.1465) == 15 and _mach_code(0.1441) == 14 and _mach_code(0.2) == 20


# --- PFS-2015.04: the reductions reach the products through the stage --------------
#
# The four reductions existed as library functions since 0.8.0 and nothing on
# the campaign path called them (measured 2026-09-08). Her rule of the same
# day: every capability enters through the workflow. So the products stage
# writes them, one file per reduction beside the plots table, over the window
# the row states, which the run record carries as `reductions`.

#: The header of the plots export above, everything before its table, so a
#: synthetic history carries the free-stream and reference velocities the
#: plots table scales by: (100 / 50) squared, four.
PLOTS_HEADER = PLOTS.split("Time-step")[0]


def _plots_export(rows: int) -> str:
    """A synthetic plots export of ``rows`` time steps whose CL is 0.1 times the step.

    The step is the value, so the mean over any window is the mean step
    times 0.1 and, after the free-stream scaling, times 0.4.
    """
    table = "Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL\n" + "".join(
        f"{i}.0000,{0.1 * i:.5f},{0.01 * i:.5f},\n" for i in range(1, rows + 1)
    )
    return PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Coefficients\n"


#: The windows a rotor row of eight steps states: four steps per revolution,
#: two blades, an export window of six steps. The per-blade split is the last
#: revolution (5 to 8) cut in two; the phase-locked passages cut the export
#: window (3 to 8) into three passages of one blade passage each.
ROTOR_PLAN = {
    "time_iterations": 8,
    "steps_per_revolution": 4.0,
    "blades": 2,
    "time_average": {"windows": [[3, 8]], "window_from": "the export window: 6 steps"},
    "phase_locked": {
        "windows": [[3, 4], [5, 6], [7, 8]],
        "period_steps": 2,
        "window_from": "the export window: 6 steps, cut into blade passages",
    },
    "per_blade": {
        "windows": [[5, 6], [7, 8]],
        "period_steps": 2,
        "window_from": "the last revolution, one window per blade",
    },
}


def _unsteady_workspace(tmp_path, *, reductions, recipe="unsteady_rotor", rows=8):
    """One converged unsteady record with a loads table and a plots export under raw/."""
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("7001") / "raw"
    raw.mkdir(parents=True)
    (raw / "a-02.0.txt").write_text(LOADS, encoding="utf-8")
    (raw / "a-02.0_plots.txt").write_text(_plots_export(rows), encoding="utf-8")
    fields: dict[str, object] = dict(
        run_id="camp/sim_7001/a-02.0",
        sim_id="7001",
        point={"alpha": -2.0},
        fs_version_requested="26.120",
        package_version="0.13.0.dev0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=["raw/a-02.0.txt", "raw/a-02.0_plots.txt"],
        pproc="p001",
        recipe=recipe,
        description="ROTOR_UNSTEADY",
        mach=0.2,
        reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
    )
    # Guarded so the RED measurement lands on the assertion rather than on
    # the record refusing a field it does not have yet (extra="forbid").
    if reductions is not None and "reductions" in RunRecord.model_fields:
        fields["reductions"] = reductions
    workspace.append_record(RunRecord(**fields))
    return workspace


def _products_manifest(workspace):
    import json

    return json.loads(
        (workspace.root / "post" / "products" / "products.json").read_text(encoding="utf-8")
    )


def test_pyfs_matrix_post_writes_every_reduction_beside_the_plots_table(tmp_path):
    """PFS-2015.04. One file per applicable reduction beside the plots table, each
    named in products.json with the reduction and the window it used; raw is the
    plots table itself and is written once."""
    from pyflightstream.post.products import write_campaign_products

    workspace = _unsteady_workspace(tmp_path, reductions=ROTOR_PLAN)
    written = write_campaign_products(workspace)
    plots = workspace.root / "post" / "products" / "plots"
    names = sorted(p.name for p in plots.iterdir())
    assert names == [
        "a-02.0_per_blade.csv",
        "a-02.0_phase_locked.csv",
        "a-02.0_plots.csv",
        "a-02.0_time_average.csv",
    ], f"the plots folder holds {names}"
    assert {p.name for p in written} >= set(names), "every reduction is a product returned"

    columns, rows = read_csv_table(plots / "a-02.0_time_average.csv")
    assert columns == (
        "REDUCTION",
        "WINDOW",
        "FIRST_STEP",
        "LAST_STEP",
        "STEPS",
        "Time-step",
        "CL_MRP_TOTAL",
        "CDI_MRP_TOTAL",
    ), "the reduction carries the window block and then the plots table's own columns"
    assert len(rows) == 1
    assert rows[0]["REDUCTION"] == "time_average" and rows[0]["WINDOW"] == "1"
    assert (rows[0]["FIRST_STEP"], rows[0]["LAST_STEP"], rows[0]["STEPS"]) == ("3", "8", "6")
    assert rows[0]["CL_MRP_TOTAL"] == "2.20000", "mean step 5.5 times 0.1, scaled by four"

    _, blades = read_csv_table(plots / "a-02.0_per_blade.csv")
    assert [(r["WINDOW"], r["FIRST_STEP"], r["LAST_STEP"]) for r in blades] == [
        ("1", "5", "6"),
        ("2", "7", "8"),
    ]
    assert [r["CL_MRP_TOTAL"] for r in blades] == ["2.20000", "3.00000"]

    _, passages = read_csv_table(plots / "a-02.0_phase_locked.csv")
    assert [(r["FIRST_STEP"], r["LAST_STEP"]) for r in passages] == [
        ("3", "4"),
        ("5", "6"),
        ("7", "8"),
    ]
    assert passages[0]["CL_MRP_TOTAL"] == "1.40000"

    manifest = _products_manifest(workspace)
    entry = manifest["products"]["plots/a-02.0_per_blade.csv"]
    assert entry["runs"] == ["camp/sim_7001/a-02.0"] and entry["sim_id"] == "7001"
    assert entry["reduction"] == "per_blade"
    assert entry["windows"] == [[5, 6], [7, 8]] and entry["period_steps"] == 2
    assert "last revolution" in entry["window_from"]
    average = manifest["products"]["plots/a-02.0_time_average.csv"]
    assert average["reduction"] == "time_average" and average["windows"] == [[3, 8]]
    assert "reduction" not in manifest["products"]["plots/a-02.0_plots.csv"], (
        "raw is the plots table itself, not a reduction"
    )
    assert manifest["skipped"] == {}

    # The docs name the files a user meets beside the plots table.
    page = (Path(__file__).parents[2] / "docs" / "workspace-and-workflows.md").read_text(
        encoding="utf-8"
    )
    for name in ("<point>_time_average.csv", "<point>_phase_locked.csv", "<point>_per_blade.csv"):
        assert name in page, f"docs/workspace-and-workflows.md does not name {name}"


def test_a_rotorless_unsteady_point_gets_the_time_average_alone(tmp_path):
    """Without a rotor the row states DELTA_TIME and TIME_ITERATIONS: only the time
    average and raw apply; a blade passage has no length, so the other two are
    neither written nor recorded as skipped."""
    from pyflightstream.post.products import write_campaign_products

    plan = {
        "time_iterations": 8,
        "steps_per_revolution": None,
        "blades": None,
        "time_average": {
            "windows": [[1, 8]],
            "window_from": "the whole run: DELTA_TIME and TIME_ITERATIONS",
        },
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan, recipe="unsteady")
    write_campaign_products(workspace)
    plots = workspace.root / "post" / "products" / "plots"
    assert sorted(p.name for p in plots.iterdir()) == [
        "a-02.0_plots.csv",
        "a-02.0_time_average.csv",
    ]
    _, rows = read_csv_table(plots / "a-02.0_time_average.csv")
    assert rows[0]["CL_MRP_TOTAL"] == "1.80000", "mean step 4.5 times 0.1, scaled by four"
    manifest = _products_manifest(workspace)
    assert manifest["skipped"] == {}, "not applicable is not skipped"


def test_a_reduction_the_row_cannot_window_is_recorded_as_skipped(tmp_path):
    """Three ways a window is missing, each a skip naming its reason under the
    file that was not written, the way a refused polar is recorded."""
    from pyflightstream.post.products import write_campaign_products

    # A rotor row with no BLADES: the run stage records the reason on the plan.
    plan = dict(ROTOR_PLAN)
    plan["per_blade"] = {"skipped": "the row states no BLADES, so one blade passage has no length"}
    plan["phase_locked"] = {
        "skipped": "the row states no BLADES, so one blade passage has no length"
    }
    workspace = _unsteady_workspace(tmp_path / "blades", reductions=plan)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "plots/a-02.0_per_blade.csv" in manifest["skipped"], manifest["skipped"]
    assert "BLADES" in manifest["skipped"]["plots/a-02.0_per_blade.csv"]
    assert "BLADES" in manifest["skipped"]["plots/a-02.0_phase_locked.csv"]
    assert "plots/a-02.0_time_average.csv" in manifest["products"]
    assert not (workspace.root / "post" / "products" / "plots" / "a-02.0_per_blade.csv").exists()

    # A plots table shorter than the window: a shorter history averaged as a
    # whole one is the shape every reader here refuses.
    workspace = _unsteady_workspace(tmp_path / "short", reductions=ROTOR_PLAN, rows=6)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    reason = manifest["skipped"]["plots/a-02.0_per_blade.csv"]
    assert "6" in reason and "8" in reason, reason
    assert "plots/a-02.0_phase_locked.csv" in manifest["skipped"]
    assert "plots/a-02.0_time_average.csv" in manifest["skipped"]
    assert (workspace.root / "post" / "products" / "plots" / "a-02.0_plots.csv").is_file()

    # A record carrying no windows at all, written before this release or by
    # hand: the time average is skipped naming the record, and nothing guesses.
    workspace = _unsteady_workspace(tmp_path / "none", reductions=None)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "record" in manifest["skipped"]["plots/a-02.0_time_average.csv"]
    assert "plots/a-02.0_plots.csv" in manifest["products"]


def test_the_reductions_sit_beside_the_plots_table_and_never_replace_it(tmp_path):
    """PFS-2015.03, closed on 2026-09-08 with nothing behind it; this is its proof.
    After the reductions are written the plots table is present and byte-identical
    to what the stage wrote before them."""
    from pyflightstream.post.products import write_campaign_products

    before = _unsteady_workspace(tmp_path / "before", reductions=None)
    write_campaign_products(before)
    table_before = before.root / "post" / "products" / "plots" / "a-02.0_plots.csv"
    assert table_before.is_file()
    assert not (table_before.parent / "a-02.0_time_average.csv").exists(), (
        "the control wrote no reduction; it is the plots table alone"
    )

    after = _unsteady_workspace(tmp_path / "after", reductions=ROTOR_PLAN)
    write_campaign_products(after)
    table_after = after.root / "post" / "products" / "plots" / "a-02.0_plots.csv"
    assert table_after.is_file(), "the plots table is present after the reductions"
    assert (table_after.parent / "a-02.0_per_blade.csv").is_file(), "the reductions were written"
    assert table_after.read_bytes() == table_before.read_bytes(), (
        "the plots table changed under the reductions; a reduction ships beside the "
        "history and never in its place (her rule of 2026-08-16)"
    )


# --- OPS-2008.01: the seventh propagation test ---------------------------------------


def test_a_missing_sample_poisons_the_harmonic_in_plane_moment_product():
    """OPS-2008.01. Six of the seven far-field reductions hold ``skipna=False`` behind
    a test that turns red when it is reverted; the harmonic branch of the in-plane
    moment was the seventh and had none. One sample of the axial velocity missing
    on the outlet plane must arrive as NaN in the harmonic loading term rather than
    as a number one sample short.

    Written at the reduction's own seam, and that is said here rather than left
    to be found: on 2026-09-08 the campaign products stage carries no far-field
    product (nothing outside ``pyflightstream.farfield`` calls the ledger, and no
    reader turns a probe export into its lattice dataset), so the acceptance's
    phrase "runs the campaign products stage" has no stage to run through yet.
    When a far-field product enters the stage, this test moves onto it.
    """
    import numpy as np

    from pyflightstream.farfield import cylindrical_components, in_plane_moment, lattice_dataset
    from pyflightstream.probes import build_lattice

    lattice = build_lattice(tip_radius=1.0, stations=(-2.0, 2.0), lateral_radius=None)
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)
    # A pure 1P cosine loading on the axial velocity at the OUTLET alone, so
    # the harmonic loading term, outlet minus inlet, is finite and non-zero on
    # the complete field.
    fields = {
        "u": np.full(shape, 30.0),
        "v": np.zeros(shape),
        "w": np.zeros(shape),
        "p_prime": np.zeros(shape),
    }
    fields["u"][1] += 2.0 * np.cos(lattice.psi)[None, :]
    complete = cylindrical_components(lattice_dataset(lattice, fields))
    whole = in_plane_moment(complete, 1.2, 30.0, inlet=-2.0, outlet=2.0, method="harmonic")
    assert np.isfinite(float(whole["loading_term"])) and float(whole["loading_term"]) != 0.0

    holed = {name: value.copy() for name, value in fields.items()}
    holed["u"][1, 0, 0] = np.nan
    poisoned = cylindrical_components(lattice_dataset(lattice, holed))
    product = in_plane_moment(poisoned, 1.2, 30.0, inlet=-2.0, outlet=2.0, method="harmonic")
    loading = float(product["loading_term"])
    assert np.isnan(loading), (
        f"one missing sample produced the finite harmonic loading term {loading!r} "
        f"instead of NaN; the complete field gives {float(whole['loading_term'])!r}"
    )
    assert np.isnan(float(product["total"])), "the poison reaches the total"
