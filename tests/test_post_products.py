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
