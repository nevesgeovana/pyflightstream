"""PFS-2029.15.01 and .15.02: the campaign's CSV products round-trip and carry her numbers.

The synthetic case here is one loads table with two surfaces at alpha -2,
the numbers of the author's recorded wing-body point at Mach 0.20 (her
loads table of 2026-08-03), so the polar row this module writes is measured
against a row she wrote, column by column, at her five decimals.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamDeprecationWarning
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
    write_campaign_products,
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


def test_an_empty_group_sums_every_family_the_table_carries():
    """Her decision of 2026-09-09 (PFS-2005.02): a group written empty is every
    family, so its row is the sum over every surface row of the loads table,
    here W and B, and equals the group that names them; the Total row is not
    a surface and is not summed twice. The reading is the ARTIFACT's, so the
    products stage asks for it by name (the interface lens of 2026-09-09); the
    other half is pinned by
    test_an_empty_member_list_sums_to_zero_unless_the_caller_asks_for_every_family."""
    loads = _loads()
    everything = group_coefficients(loads, [], bref_m=20.0, empty_is_every=True)
    assert everything.families_used == tuple(loads.surfaces), "every surface, in table order"
    assert everything.families_used == ("W", "B")
    assert everything == group_coefficients(loads, ["W", "B"], bref_m=20.0)


def test_an_empty_member_list_sums_to_zero_unless_the_caller_asks_for_every_family():
    """The interface lens of 2026-09-09: her decision that an empty [groups] entry
    is every family is about the ARTIFACT, and it had flipped this public function
    in silence, where an empty list summed to zero and its docstring said so. A
    caller that filtered its families down to none still gets zero; the products
    stage, which reads the artifact, asks for every family by name."""
    loads = _loads()
    zero = group_coefficients(loads, [], bref_m=20.0)
    assert zero.families_used == () and zero.lift == 0.0
    every = group_coefficients(loads, [], bref_m=20.0, empty_is_every=True)
    assert every.families_used == ("W", "B")
    assert every == group_coefficients(loads, ["W", "B"], bref_m=20.0)


def test_a_group_member_may_be_a_family_or_an_alias_of_the_setup():
    """Her decisions of 2026-09-09: a member is an exact surface name first, then
    an ALIAS the row's setup defines (its members resolved the same way, a
    member the table lacks ignored), then a family, the label without its
    trailing number. Nothing is hardcoded: ``airframe`` and ``blades`` are
    whatever the setup says they are, and without an alias those words are
    families the table does not carry. Until 0.14.0 a family name in a group
    summed nothing at products time."""
    from dataclasses import replace

    loads = _loads()
    wing, body = loads.surfaces["W"], loads.surfaces["B"]
    with_blades = replace(loads, surfaces={"Blade1": body, "Blade2": wing, "W": wing, "B": body})
    aliases = {"airframe": ["W", "B", "Nothing"], "rotor": ["Blade"], "one": ["Blade2"]}
    by_family = group_coefficients(with_blades, ["Blade"], bref_m=20.0)
    assert by_family.families_used == ("Blade1", "Blade2")
    assert by_family.lift == pytest.approx(wing["CL"] + body["CL"])
    assert group_coefficients(with_blades, ["rotor"], bref_m=20.0, aliases=aliases) == by_family
    airframe = group_coefficients(with_blades, ["airframe"], bref_m=20.0, aliases=aliases)
    assert airframe.families_used == ("W", "B"), "the member the table lacks is ignored"
    assert group_coefficients(with_blades, ["airframe"], bref_m=20.0).families_used == (), (
        "without the setup's alias the word is a family the table does not carry"
    )
    assert group_coefficients(with_blades, ["blades"], bref_m=20.0).families_used == ()
    mixed = group_coefficients(with_blades, ["one", "airframe"], bref_m=20.0, aliases=aliases)
    assert mixed.families_used == ("Blade2", "W", "B"), "alias by alias, each name once"
    assert group_coefficients(with_blades, [], bref_m=20.0, empty_is_every=True).families_used == (
        "Blade1",
        "Blade2",
        "W",
        "B",
    )


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


#: A TRANSITION row's plan (FR-68): two rotors, two blade counts, two
#: passages. The flat keys carry the skip that says where the reductions
#: went, exactly as `reduction_windows` writes them for such a row.
TWO_ROTOR_PLAN = {
    "time_iterations": 8,
    "steps_per_revolution": 4.0,
    "blades": None,
    "time_average": {"windows": [[3, 8]], "window_from": "the export window: 6 steps"},
    "rotors": {
        "LIFT_L1": {
            "blades": 2,
            "rpm": 2200.0,
            "steps_per_revolution": 4.0,
            "period_steps": 2,
            "phase_locked": {
                "windows": [[3, 4], [5, 6], [7, 8]],
                "period_steps": 2,
                "window_from": "blade passages of LIFT_L1, 2 steps each",
            },
            "per_blade": {
                "windows": [[5, 6], [7, 8]],
                "period_steps": 2,
                "window_from": "the last revolution of LIFT_L1",
            },
        },
        "PUSHER": {
            "blades": 2,
            "rpm": 900.0,
            "steps_per_revolution": 8.0,
            "period_steps": 4,
            "phase_locked": {
                "windows": [[3, 6]],
                "period_steps": 4,
                "window_from": "blade passages of PUSHER, 4 steps each",
            },
            "per_blade": {
                "windows": [[1, 4], [5, 8]],
                "period_steps": 4,
                "window_from": "the last revolution of PUSHER",
            },
        },
    },
    "phase_locked": {
        "skipped": "case '7001' turns 2 rotors, so one blade passage of the ROW has no "
        "length: each rotor reduces over its own, and the windows are under 'rotors' "
        "(LIFT_L1, PUSHER)."
    },
    "per_blade": {
        "skipped": "case '7001' turns 2 rotors, so one blade passage of the ROW has no "
        "length: each rotor reduces over its own, and the windows are under 'rotors' "
        "(LIFT_L1, PUSHER)."
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


def test_a_transition_row_writes_one_passage_reduction_per_rotor(tmp_path):
    """FR-68: the reduction files NAME the rotor, and each carries its own windows.

    A transition row turns the lifters and the pusher in ONE run, and one
    file per reduction cannot hold two blade passages. The time average is
    still one file, because it is one window of the whole run whatever
    turns in it.
    """
    from pyflightstream.post.products import write_campaign_products

    workspace = _unsteady_workspace(tmp_path, reductions=TWO_ROTOR_PLAN)
    write_campaign_products(workspace)
    plots = workspace.root / "post" / "products" / "plots"
    names = sorted(p.name for p in plots.iterdir())
    assert names == [
        "a-02.0_per_blade_LIFT_L1.csv",
        "a-02.0_per_blade_PUSHER.csv",
        "a-02.0_phase_locked_LIFT_L1.csv",
        "a-02.0_phase_locked_PUSHER.csv",
        "a-02.0_plots.csv",
        "a-02.0_time_average.csv",
    ], f"the plots folder holds {names}"

    _, lifter = read_csv_table(plots / "a-02.0_per_blade_LIFT_L1.csv")
    _, pusher = read_csv_table(plots / "a-02.0_per_blade_PUSHER.csv")
    assert [(r["FIRST_STEP"], r["LAST_STEP"]) for r in lifter] == [("5", "6"), ("7", "8")]
    assert [(r["FIRST_STEP"], r["LAST_STEP"]) for r in pusher] == [("1", "4"), ("5", "8")]
    assert lifter[0]["CL_MRP_TOTAL"] != pusher[0]["CL_MRP_TOTAL"], (
        "both rotors were averaged over one window, so one of them is not its own"
    )

    manifest = _products_manifest(workspace)
    entry = manifest["products"]["plots/a-02.0_per_blade_PUSHER.csv"]
    assert entry["reduction"] == "per_blade" and entry["period_steps"] == 4
    assert "PUSHER" in entry["window_from"], "the record does not say whose window it is"
    skipped = manifest["skipped"]
    assert "rotors" in skipped["plots/a-02.0_per_blade.csv"], (
        "the flat file's skip does not say where the row's reductions went"
    )


def test_a_row_turning_one_rotor_keeps_the_file_names_it_has_always_had(tmp_path):
    """The rotor's name enters a file name only where there are several to tell apart.

    A one-rotor row's record carries a `rotors` block too, and its files
    are still `<point>_per_blade.csv`: every workspace written before
    0.15.0 keeps its names, and so does every golden.
    """
    from pyflightstream.post.products import write_campaign_products

    plan = {**ROTOR_PLAN, "rotors": {"LIFT_L1": TWO_ROTOR_PLAN["rotors"]["LIFT_L1"]}}
    workspace = _unsteady_workspace(tmp_path, reductions=plan)
    write_campaign_products(workspace)
    plots = workspace.root / "post" / "products" / "plots"
    names = sorted(p.name for p in plots.iterdir())
    assert names == [
        "a-02.0_per_blade.csv",
        "a-02.0_phase_locked.csv",
        "a-02.0_plots.csv",
        "a-02.0_time_average.csv",
    ], f"a one-rotor row's file names moved: {names}"


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


# --- PFS-2012.08.01: a PROV-JSON document per recorded run --------------------------
#
# The run record carries every fact a provenance document needs; what it
# lacked was a shape another tool reads without reading this package's docs.
# W3C PROV, serialized as PROV-JSON, one document per recorded run, written by
# the products stage (her decision of 2026-09-08, design 68).


def _steady_workspace_with_provenance(tmp_path):
    """One converged steady record with the provenance fields filled, and one failed."""
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "raw"
    raw.mkdir(parents=True)
    (raw / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
    common: dict[str, object] = dict(
        sim_id="3207",
        fs_version_requested="26.120",
        fs_version_reported="26.1",
        fs_build="7012026",
        fs_exe="C:/builds/26120/FlightStream.exe",
        fs_exe_sha256="e" * 64,
        package_version="0.13.0.dev0",
        package_commit="8f7740f",
        package_dirty=False,
        script_path="scripts/POLAR-3207_M20AL-020BE+000.fs",
        script_sha256="c" * 64,
        inputs_sha256={"10_WING.fsm": "a" * 64, "10_WING.boundaries.json": "b" * 64},
        raw_flag=False,
        pproc="p001",
        description="STEADY_WB",
        mach=0.2,
        reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 9.152},
        executor={
            "class_name": "LocalExecutor",
            "argv": ["C:/builds/26120/FlightStream.exe", "-hidden", "-script", "run.fs"],
        },
        wall_time_s=12.5,
    )
    # Guarded so the RED measurement lands on the assertion rather than on
    # the record refusing a field it does not have yet (extra="forbid").
    if "started_at" in RunRecord.model_fields:
        common["started_at"] = "2026-09-08T21:41:07+00:00"
        common["finished_at"] = "2026-09-08T21:41:19+00:00"
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/a-02.0",
            point={"alpha": -2.0},
            status=RunStatus.CONVERGED,
            outputs=["raw/POLAR-3207_M20AL-020BE+000.txt"],
            **common,
        )
    )
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/a+02.0",
            point={"alpha": 2.0},
            status=RunStatus.FAILED_EXECUTION,
            outputs=[],
            error="the solver returned 3",
            **common,
        )
    )
    return workspace


def _read_prov_json(path):
    """A small PROV-JSON reader: the structure, and that every relation resolves.

    Every ``used`` names an activity and an entity the document declares,
    every ``wasGeneratedBy`` an entity and the activity, every
    ``wasAssociatedWith`` an agent, every ``wasAttributedTo`` an entity and
    an agent. Returns the parsed document once it holds.
    """
    import json

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("prefix", "entity", "activity", "agent"):
        assert key in document, f"{path} carries no {key!r}"
    assert "prov" in document["prefix"] and "pyfs" in document["prefix"]
    entities, activities, agents = document["entity"], document["activity"], document["agent"]
    relations = {
        "used": ("prov:activity", activities, "prov:entity", entities),
        "wasGeneratedBy": ("prov:entity", entities, "prov:activity", activities),
        "wasAssociatedWith": ("prov:activity", activities, "prov:agent", agents),
        "wasAttributedTo": ("prov:entity", entities, "prov:agent", agents),
    }
    for relation, (left, left_in, right, right_in) in relations.items():
        for name, entry in document.get(relation, {}).items():
            assert entry[left] in left_in, f"{relation} {name} names {entry[left]!r}, not declared"
            assert entry[right] in right_in, (
                f"{relation} {name} names {entry[right]!r}, not declared"
            )
    return document


def test_pyfs_matrix_post_writes_a_prov_json_document_per_recorded_run(tmp_path):
    """PFS-2012.08.01. One PROV-JSON document per recorded run, failed runs
    included, under post/<stem>/provenance/, named in products.json under
    ``provenance`` keyed by run id: entities for every staged input, the script
    and every collected output with their sha256, one activity for the solver
    run with its start, end and argv, agents for the package and the solver."""
    import hashlib
    import json

    from pyflightstream.post.products import write_campaign_products

    workspace = _steady_workspace_with_provenance(tmp_path)
    write_campaign_products(workspace)
    out = workspace.root / "post" / "products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert "provenance" in manifest, f"products.json carries {sorted(manifest)} and no provenance"
    assert manifest["provenance"] == {
        "camp/sim_3207/a-02.0": "provenance/camp_sim_3207_a-02.0.prov.json",
        "camp/sim_3207/a+02.0": "provenance/camp_sim_3207_a+02.0.prov.json",
    }
    for relative in manifest["provenance"].values():
        assert (out / relative).is_file(), f"{relative} was named and not written"

    document = _read_prov_json(out / "provenance" / "camp_sim_3207_a-02.0.prov.json")
    entities = document["entity"]
    by_sha = {entry.get("pyfs:sha256"): name for name, entry in entities.items()}
    assert "a" * 64 in by_sha and "b" * 64 in by_sha, "every staged input is an entity"
    assert "c" * 64 in by_sha, "the script is an entity carrying its sha256"
    # Of the file's BYTES, which on Windows carry the line endings write_text
    # gave them, not of the text the test holds.
    loads_file = workspace.sim_dir("3207") / "raw" / "POLAR-3207_M20AL-020BE+000.txt"
    loads_sha = hashlib.sha256(loads_file.read_bytes()).hexdigest()
    assert loads_sha in by_sha, "the collected output carries the sha256 of the file itself"
    assert entities[by_sha[loads_sha]]["pyfs:sha256_from"] == "file"
    assert by_sha[loads_sha].endswith("POLAR-3207_M20AL-020BE+000.txt")

    (activity_name, activity), *rest = document["activity"].items()
    assert not rest, "one activity, the solver run"
    assert activity["pyfs:argv"] == [
        "C:/builds/26120/FlightStream.exe",
        "-hidden",
        "-script",
        "run.fs",
    ]
    assert activity["prov:startTime"] == "2026-09-08T21:41:07+00:00"
    assert activity["prov:endTime"] == "2026-09-08T21:41:19+00:00"
    assert activity["pyfs:wall_time_s"] == 12.5

    agents = document["agent"]
    versions = {entry.get("pyfs:version") for entry in agents.values()}
    assert "0.13.0.dev0" in versions, "the package at its version is an agent"
    assert {entry.get("pyfs:commit") for entry in agents.values()} >= {"8f7740f"}
    builds = {entry.get("pyfs:build") for entry in agents.values()}
    assert "7012026" in builds, "the solver build is an agent"
    assert {entry.get("pyfs:executable_sha256") for entry in agents.values()} >= {"e" * 64}
    assert {entry.get("pyfs:version_reported") for entry in agents.values()} >= {"26.1"}

    used = {entry["prov:entity"] for entry in document["used"].values()}
    assert used == {by_sha["a" * 64], by_sha["b" * 64], by_sha["c" * 64]}, (
        "the activity used every staged input and the script, and nothing else"
    )
    generated = {entry["prov:entity"] for entry in document["wasGeneratedBy"].values()}
    assert generated == {by_sha[loads_sha]}
    assert {e["prov:activity"] for e in document["wasGeneratedBy"].values()} == {activity_name}
    associated = {entry["prov:agent"] for entry in document["wasAssociatedWith"].values()}
    assert associated == set(agents), "the run is associated with both agents"
    assert document["wasAttributedTo"], "the outputs are attributed"

    # The failed run has no output and no generation, and still its document.
    failed = _read_prov_json(out / "provenance" / "camp_sim_3207_a+02.0.prov.json")
    assert "wasGeneratedBy" not in failed or failed["wasGeneratedBy"] == {}
    assert len(failed["used"]) == 3

    # The docs name the folder and the format.
    page = (Path(__file__).parents[2] / "docs" / "workspace-and-workflows.md").read_text(
        encoding="utf-8"
    )
    assert "PROV-JSON" in page and ".prov.json" in page


# --- PFS-2014.01.02 and .01.01: her plot format ------------------------------------
#
# Her existing tooling opens a fixed-width text polar file. The committed
# fixture has that file's SHAPE, read off a file of hers; every value in it is
# synthetic, invented for the tier-3 wing of the tour's row 1001.

HER_FORMAT_SAMPLE = FIXTURES / "custom_polar_format_sample.dat"

#: ``Tue Sep 08 23:41:07  2026``: weekday, month, zero-padded day, clock, two
#: spaces, year. Her sample carries the two spaces.
DATE_LINE = r"^[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2}  \d{4}$"


def _her_format_functions():
    from pyflightstream.post import products as module

    writer = getattr(module, "write_custom_polar_format", None)
    reader = getattr(module, "read_custom_polar_format", None)
    assert writer is not None and reader is not None, (
        "post.products has no writer and reader of the custom polar format (PFS-2014.01)"
    )
    return writer, reader


def test_her_plot_format_sample_against_the_stage_product(tmp_path):
    """PFS-2014.01.02. The fixture is the specification: its rows fed through the
    writer come back byte for byte, except line 3, the write time, which is
    masked and matched against the date pattern. The fixture's shape was read
    off a file of hers; every value in it is synthetic."""
    import re

    write_custom_polar_format, read_custom_polar_format = _her_format_functions()
    expected = HER_FORMAT_SAMPLE.read_bytes()
    assert b"\r" not in expected, "the fixture is pinned LF (.gitattributes)"
    table = read_custom_polar_format(HER_FORMAT_SAMPLE)
    assert table.polar == "1001" and table.mach == 0.1 and table.group == 1
    assert table.description == "STEADY_polar_AL_sweep_MACH_REmi_pins_from_the_setup"
    assert table.reference.sref_m2 == 8.0 and table.reference.xmom_m == 0.25
    assert len(table.rows) == 13 and [row["ALPHA"] for row in table.rows][:3] == [-2.0, -1.0, 0.0]

    written = write_custom_polar_format(
        tmp_path / "1001_M10_g01.dat",
        polar=table.polar,
        description=table.description,
        group=table.group,
        mach=table.mach,
        reference=table.reference,
        rows=[tuple(row[name] for name in COEFFICIENT_COLUMNS) for row in table.rows],
    )
    actual = written.read_bytes()
    actual_lines = actual.split(b"\n")
    expected_lines = expected.split(b"\n")
    assert re.match(DATE_LINE, actual_lines[2].decode("ascii")), actual_lines[2]
    assert re.match(DATE_LINE, expected_lines[2].decode("ascii")), expected_lines[2]
    actual_lines[2] = expected_lines[2] = b"<date>"
    assert actual_lines == expected_lines, "the writer's bytes differ from the fixture's"

    # The writer's docstring is the specification: every line of the format named.
    specification = write_custom_polar_format.__doc__ or ""
    for line in range(1, 10):
        assert f"line {line}" in specification, f"the docstring names no line {line}"
    assert "%10.5f" in specification


def test_pyfs_matrix_post_writes_her_format_beside_the_polar_tables_when_asked(tmp_path):
    """PFS-2014.01.01. ``[products] custom_polar_format = true`` on the pproc artifact
    writes ``<polar>_M<code>_g<group>.dat`` beside every polar table the stage
    writes, products.json names it, the reader opens it, and write, read, write
    again is byte equal. Without the key nothing is written."""
    import json

    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    write_custom_polar_format, read_custom_polar_format = _her_format_functions()

    def _workspace(root, pproc_text):
        workspace = CampaignWorkspace.init(root)
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc_text, encoding="utf-8")
        raw = workspace.sim_dir("3207") / "raw"
        raw.mkdir(parents=True)
        (raw / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id="camp/sim_3207/a-02.0",
                sim_id="3207",
                point={"alpha": -2.0},
                fs_version_requested="26.120",
                package_version="0.13.0.dev0",
                script_sha256="",
                raw_flag=False,
                status=RunStatus.CONVERGED,
                outputs=["raw/POLAR-3207_M20AL-020BE+000.txt"],
                pproc="p001",
                description="STEADY_WB",
                mach=0.2,
                reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 9.152},
            )
        )
        return workspace

    asked = _workspace(
        tmp_path / "asked",
        '[groups]\n"1" = ["W", "B"]\n"3" = ["W"]\n[products]\ncustom_polar_format = true\n',
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamDeprecationWarning)
        assert asked.resolve_pproc("p001").products.custom_polar_format is True
    written = write_campaign_products(asked)
    out = asked.root / "post" / "products"
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "3207_M20_g01.csv",
        "3207_M20_g01.dat",
        "3207_M20_g03.csv",
        "3207_M20_g03.dat",
        "products.json",
        "provenance",
    ], names
    assert {p.name for p in written} >= {"3207_M20_g01.dat", "3207_M20_g03.dat"}
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert manifest["products"]["3207_M20_g01.dat"]["runs"] == ["camp/sim_3207/a-02.0"]

    # The two serializations carry the same rows: the custom format at %10.5f, the
    # CSV at five decimals.
    table = read_custom_polar_format(out / "3207_M20_g01.dat")
    assert table.polar == "3207" and table.group == 1 and table.mach == 0.2
    assert table.description == "STEADY_WB"
    _, csv_rows = read_csv_table(out / "3207_M20_g01.csv")
    assert [f"{table.rows[0][c]:.5f}" for c in COEFFICIENT_COLUMNS] == [
        csv_rows[0][c] for c in COEFFICIENT_COLUMNS
    ]
    assert [f"{table.rows[0][c]:.5f}" for c in COEFFICIENT_COLUMNS] == HER_ROW
    text = (out / "3207_M20_g01.dat").read_text(encoding="ascii")
    assert text.splitlines()[:2] == ["FlightStream - STEADY_WB", "320720"]
    assert text.splitlines()[6:8] == ["001", "024"]

    # Write, read, write again: byte equal, the date carried through.
    first = (out / "3207_M20_g01.dat").read_bytes()
    again = write_custom_polar_format(
        tmp_path / "again.dat",
        polar=table.polar,
        description=table.description,
        group=table.group,
        mach=table.mach,
        reference=table.reference,
        rows=[tuple(row[name] for name in COEFFICIENT_COLUMNS) for row in table.rows],
        date=table.date,
    )
    assert again.read_bytes() == first

    silent = _workspace(tmp_path / "silent", '[groups]\n"1" = ["W", "B"]\n')
    write_campaign_products(silent)
    assert sorted(p.name for p in (silent.root / "post" / "products").iterdir()) == [
        "3207_M20_g01.csv",
        "products.json",
        "provenance",
    ], "without the key the custom format is not written"

    # The docs name the key and what the format is for.
    page = (Path(__file__).parents[2] / "docs" / "workspace-and-workflows.md").read_text(
        encoding="utf-8"
    )
    assert "custom_polar_format" in page and "existing tooling" in page


# --- PFS-2031.18.01: the per-step exports of a windowed point as a series ------------

PROBES = (Path(__file__).parent / "fixtures" / "probe_points_26.120.txt").read_text(
    encoding="utf-8"
)


def _windowed_workspace(tmp_path, *, window, reductions=None, kinds=("", "_sloads", "_probes")):
    """One converged unsteady record whose simulation folder holds stamped exports.

    The loads, sectional loads and probe fixtures of this module stand in
    for what the solver stamps on every step of the window, ``_cp`` and
    ``.dat`` files beside them; the whole-run exports sit under ``raw/``.
    """
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    sim = workspace.sim_dir("7001")
    raw = sim / "raw"
    raw.mkdir(parents=True)
    (raw / "a-02.0.txt").write_text(LOADS, encoding="utf-8")
    texts = {"": LOADS, "_sloads": SLOADS, "_probes": PROBES}
    for step in range(int(window["first_step"]), int(window["time_iterations"]) + 1):
        for kind in kinds:
            (sim / f"a-02.0{kind}_iteration={step}.txt").write_text(texts[kind], encoding="utf-8")
        (sim / f"a-02.0_cp_iteration={step}.txt").write_text("cp", encoding="utf-8")
        (sim / f"a-02.0_iteration={step}.dat").write_text("tecplot", encoding="utf-8")
    fields: dict[str, object] = dict(
        run_id="camp/sim_7001/a-02.0",
        sim_id="7001",
        point={"alpha": -2.0},
        fs_version_requested="26.123",
        package_version="0.14.0.dev0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=["raw/a-02.0.txt"],
        pproc="p001",
        recipe="unsteady_rotor",
        description="ROTOR_UNSTEADY",
        mach=0.2,
        reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
        export_window=window,
        action_count=int(window["time_iterations"]),
    )
    if reductions is not None:
        fields["reductions"] = reductions
    workspace.append_record(RunRecord(**fields))
    return workspace


def _series(workspace, name):
    import csv

    path = workspace.root / "post" / "products" / "series" / name
    assert path.is_file(), (
        sorted(p.name for p in path.parent.iterdir())
        if path.parent.is_dir()
        else "no series folder"
    )
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def test_a_windowed_point_gets_one_series_table_per_export_kind(tmp_path):
    """PFS-2031.18.01: the stamped exports of the window, one table per kind under
    series/, a row per step (and per section or probe), the step's time and azimuth
    from the record's clock, which is the counter program's own arithmetic. RED on
    d908092: no series folder."""
    window = {
        "stated_form": "iterations",
        "stated_value": 3.0,
        "first_step": 3,
        "time_iterations": 5,
        "delta_time_s": 0.01,
        "step_deg": 30.0,
    }
    workspace = _windowed_workspace(tmp_path, window=window)
    write_campaign_products(workspace)
    columns, rows = _series(workspace, "a-02.0_loads_series.csv")
    assert columns[:3] == ["step", "time_s", "azimuth_deg"], columns
    assert [int(r["step"]) for r in rows] == [3, 4, 5]
    assert [float(r["time_s"]) for r in rows] == pytest.approx([0.03, 0.04, 0.05])
    assert [float(r["azimuth_deg"]) for r in rows] == pytest.approx([90.0, 120.0, 150.0])
    assert "W_CL" in columns and "Total_CL" in columns and "B_CMy" in columns, columns
    assert float(rows[0]["Total_CL"]) == pytest.approx(0.1882829, abs=1e-5), "five decimals"
    columns, rows = _series(workspace, "a-02.0_sections_series.csv")
    assert columns[:3] == ["step", "time_s", "azimuth_deg"] and "Chord" in columns, columns
    assert [int(r["step"]) for r in rows] == [3, 3, 4, 4, 5, 5], "two sections per step"
    columns, rows = _series(workspace, "a-02.0_probes_series.csv")
    assert columns[:3] == ["step", "time_s", "azimuth_deg"] and "Cp" in columns, columns
    assert len(rows) == 3 * 12 and {int(r["step"]) for r in rows} == {3, 4, 5}
    index = _products_manifest(workspace)["products"]
    entry = index["series/a-02.0_loads_series.csv"]
    assert entry["steps"] == [3, 5] and entry["steps_tabled"] == [3, 4, 5], entry
    assert len(entry["sections_files"]) == 3 and len(entry["tecplot_files"]) == 3, entry
    assert all(name.endswith(".dat") for name in entry["tecplot_files"]), entry["tecplot_files"]
    assert "series/a-02.0_probes_series.csv" in index


def test_a_record_without_the_clock_leaves_the_time_blank_and_reads_the_azimuth_off_the_reductions(
    tmp_path,
):
    """A record written before 0.14.0 carries no clock: its time column stays blank
    rather than guessed, and its azimuth comes from the steps per revolution the
    reductions plan already carries."""
    window = {
        "stated_form": "iterations",
        "stated_value": 4.0,
        "first_step": 4,
        "time_iterations": 5,
    }
    workspace = _windowed_workspace(
        tmp_path, window=window, reductions={**ROTOR_PLAN, "steps_per_revolution": 12.0}
    )
    write_campaign_products(workspace)
    _, rows = _series(workspace, "a-02.0_loads_series.csv")
    assert [r["time_s"] for r in rows] == ["", ""], rows
    assert [float(r["azimuth_deg"]) for r in rows] == pytest.approx([120.0, 150.0])


def test_a_stamped_file_the_parser_cannot_read_skips_that_series_and_not_the_stage(tmp_path):
    """The V&V lens of REL-0140: a truncated stamped file is the ordinary outcome of
    a run stopped mid-window, and it must cost that point its series and nothing
    else, as a refused polar costs its simulation and not the stage (PFS-2031.16).
    RED on 5a770de: the stage raised ProductError and wrote no products.json."""
    import warnings

    from pyflightstream._errors import PyflightstreamWarning

    window = {
        "stated_form": "iterations",
        "stated_value": 3.0,
        "first_step": 3,
        "time_iterations": 4,
        "delta_time_s": 0.01,
    }
    workspace = _windowed_workspace(tmp_path, window=window, kinds=("",))
    torn = workspace.sim_dir("7001") / "a-02.0_iteration=4.txt"
    torn.write_text(LOADS[: LOADS.index("Surface, Cx")], encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PyflightstreamWarning)
        write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "series/camp/sim_7001/a-02.0" in manifest["skipped"], manifest["skipped"]
    assert "iteration=4" in manifest["skipped"]["series/camp/sim_7001/a-02.0"]
    assert any("series of camp/sim_7001/a-02.0 not written" in str(w.message) for w in caught)
    assert not (workspace.root / "post" / "products" / "series").exists() or not list(
        (workspace.root / "post" / "products" / "series").glob("a-02.0_loads_series.csv")
    ), "the torn point's loads series was written anyway"
    assert any(name.endswith("_g01.csv") for name in manifest["products"]), "the polar still wrote"


def test_a_step_the_solver_never_stamped_is_absent_from_the_series_and_named_in_the_index(tmp_path):
    """The record says which steps exist; a step without a file is not invented."""
    window = {
        "stated_form": "iterations",
        "stated_value": 2.0,
        "first_step": 2,
        "time_iterations": 4,
        "delta_time_s": 0.5,
    }
    workspace = _windowed_workspace(tmp_path, window=window, kinds=("",))
    (workspace.sim_dir("7001") / "a-02.0_iteration=3.txt").unlink()
    write_campaign_products(workspace)
    _, rows = _series(workspace, "a-02.0_loads_series.csv")
    assert [int(r["step"]) for r in rows] == [2, 4]
    assert [r["azimuth_deg"] for r in rows] == ["", ""], "no rotor, no azimuth"
    entry = _products_manifest(workspace)["products"]["series/a-02.0_loads_series.csv"]
    assert entry["steps_tabled"] == [2, 4] and entry["steps"] == [2, 4]
    columns, rows = _series(workspace, "a-02.0_probes_series.csv")
    assert columns == ["step", "time_s", "azimuth_deg"] and rows == [], (
        "no probe export, a header alone"
    )


def test_a_step_whose_surfaces_differ_from_the_first_refuses_the_loads_series_naming_both(tmp_path):
    """QA-7 of REL-0140: the wide loads table fixed its columns from the first
    stamped step and dropped, silently, a surface a later step added. One column
    set over every step, or the point's series is a recorded skip naming the step
    and the surfaces."""
    window = {
        "stated_form": "iterations",
        "stated_value": 3.0,
        "first_step": 3,
        "time_iterations": 4,
        "delta_time_s": 0.01,
    }
    workspace = _windowed_workspace(tmp_path, window=window, kinds=("",))
    later = workspace.sim_dir("7001") / "a-02.0_iteration=4.txt"
    later.write_text(
        LOADS.replace(
            "     B,+0.0081038",
            "     Nacelle" + ",+0.0000000" * 9 + "\n     B,+0.0081038",
        ),
        encoding="utf-8",
    )
    write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    reason = skipped.get("series/camp/sim_7001/a-02.0", "")
    assert "iteration=4" in reason and "'Nacelle'" in reason and "'W', 'B', 'Total'" in reason, (
        skipped
    )


def test_the_former_key_of_the_polar_format_reaches_the_stage_and_warns(tmp_path):
    """The old key ``her_polar_format = true`` on a real artifact file warns from
    the ledger and writes the same files the new key writes (the QA lens of the
    rename round: the supported spelling carries the stage test above, and the
    deprecated one has this case, deleted whole at 0.16.0)."""
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "old")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n[products]\nher_polar_format = true\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "raw"
    raw.mkdir(parents=True)
    (raw / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/a-02.0",
            sim_id="3207",
            point={"alpha": -2.0},
            fs_version_requested="26.120",
            package_version="0.14.0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["raw/POLAR-3207_M20AL-020BE+000.txt"],
            pproc="p001",
            description="STEADY_WB",
            mach=0.2,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0, "XMOM": 9.152},
        )
    )
    with pytest.warns(PyflightstreamDeprecationWarning, match="her_polar_format.*0.16.0"):
        written = write_campaign_products(workspace)
    assert {p.name for p in written} >= {"3207_M20_g01.csv", "3207_M20_g01.dat"}


def test_the_former_her_names_of_the_polar_format_forward_and_warn(tmp_path):
    """Her decision of 2026-09-09: custom_ names the thing. The old key on a pproc
    artifact is read as the new one, and the old Python names forward, each
    warning from the ledger with its removal version; both keys at once are
    refused."""
    import warnings

    import pyflightstream.post as post
    from pyflightstream._errors import PyflightstreamDeprecationWarning
    from pyflightstream.cases import ProductsSpec
    from pyflightstream.post import products as products_module

    with pytest.warns(PyflightstreamDeprecationWarning, match="her_polar_format.*0.16.0"):
        spec = ProductsSpec.model_validate({"her_polar_format": True})
    assert spec.custom_polar_format is True
    with pytest.raises(ValueError, match="one key"):
        ProductsSpec.model_validate({"her_polar_format": True, "custom_polar_format": True})
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamDeprecationWarning)
        assert ProductsSpec.model_validate({"custom_polar_format": True}).custom_polar_format
    for old, new in (
        ("HerPolarTable", post.CustomPolarTable),
        ("write_her_polar_format", post.write_custom_polar_format),
        ("read_her_polar_format", post.read_custom_polar_format),
    ):
        with pytest.warns(PyflightstreamDeprecationWarning, match=f"{old}.*0.16.0") as caught:
            assert getattr(post, old) is new
        assert len(caught) == 1, "the package warns once, not once per lookup (QA-5)"
    with pytest.warns(PyflightstreamDeprecationWarning, match="her_polar_file_name.*0.16.0"):
        assert products_module.her_polar_file_name is products_module.custom_polar_file_name
    missing = "no_such_name"
    with pytest.raises(AttributeError):
        getattr(post, missing)
