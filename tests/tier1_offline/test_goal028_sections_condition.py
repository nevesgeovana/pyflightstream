"""The sections table states the POINT's condition, like every other family (CC-02).

THE DEFECT. `ALT` came from three sources in one folder. The sections table read
the export's `Altitude (ft)` line, which the campaign never sets, so it printed
0.00000 with confidence on a row whose matrix cell says `ALTFT:10000`; the polar
read the cell and printed 10000; the rotor table printed NA. The sections table
was the one family that assembled its condition by hand instead of through
`point_condition`.
"""

from __future__ import annotations

from pyflightstream.post.products import (
    NOT_APPLICABLE,
    read_csv_table,
    write_sections_table,
)
from tests.tier1_offline.test_post_products import SLOADS as EXPORT


def test_the_altitude_is_the_rows_and_not_the_exports_unset_zero(tmp_path):
    condition = {"ALPHA": 4.0, "BETA": 0.0, "MACH": 0.2, "ALTFT": 10000.0, "RHO": 0.9046}
    written = write_sections_table(
        tmp_path / "p_sections.csv", EXPORT, mach=0.2, condition=condition
    )
    assert written is not None
    _columns, rows = read_csv_table(written)
    assert {row["ALT"] for row in rows} == {"10000.00000"}, {row["ALT"] for row in rows}
    assert {row["RHO"] for row in rows} == {"0.90460"}


def test_a_row_that_states_no_altitude_reads_not_applicable_and_never_zero(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", EXPORT, mach=0.2, condition={"ALPHA": 4.0, "MACH": 0.2}
    )
    assert written is not None
    _columns, rows = read_csv_table(written)
    assert {row["ALT"] for row in rows} == {NOT_APPLICABLE}
