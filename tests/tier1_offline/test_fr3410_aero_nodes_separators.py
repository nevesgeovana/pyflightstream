"""FR-3410: the aerodynamic nodes file is read with the lines of dashes the solver writes.

Measured on 26.125 and 26.127 (the pyfs-debugging register, rows 9821 to 9833 of
2026-10-31): the solver writes a line of dashes below the column header of FSInodes.txt
and another after the last row, followed by a footer, and direct morphing failed at its
first structural call with "line 21 is not 9 finite numbers". The earlier fixture
carried no dashes and no footer.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.fsi._direct_morphing import AERO_NODES_FILE, read_aero_nodes
from pyflightstream.fsi.errors import FsiInputError

DASHES = "     " + "-" * 100

#: The header block as the solver wrote it on 26.127, its simulation path dropped.
HEADER = "\n".join(
    [
        "     Angle of attack (Deg)                       .000",
        "     Solver mode:                                Unsteady",
        "     Reference length (m)                        2.526",
        "                                                  ",
        "     Aeroelastic coordinate system:              ROTOR_RMRP1",
        "     Current aeroelastic iteration number:       1",
        "     Total elastic aerodynamic nodes:            {count}",
        DASHES,
        "     X, Y, Z, nx, ny, nz, Fx, Fy, Fz",
        DASHES,
    ]
)

POINTS = np.array([[-0.0299741, 0.1149481, 1.8257291], [0.0444637, 0.2135551, 1.8171021]])


def _row(point) -> str:
    return ",  ".join(f"{v: .16E}" for v in (*point, -0.04, -0.75, 0.66, 1.0e-3, 2.0e-3, 3.0e-3))


def _write(tmp_path, body: str):
    path = tmp_path / AERO_NODES_FILE
    path.write_text(body, encoding="utf-8")
    return path


def test_fr3410_the_dashes_around_the_header_are_separators_not_rows(tmp_path):
    """The file the solver writes reads as its declared rows, in file order."""
    body = HEADER.format(count=len(POINTS)) + "\n" + "\n".join(_row(p) for p in POINTS) + "\n"
    np.testing.assert_allclose(read_aero_nodes(_write(tmp_path, body)), POINTS)


#: What the solver writes after the last row on 26.127: dashes, then units, version, date.
FOOTER = "\n".join(
    [
        DASHES,
        "     Force Units: Coefficients",
        "     Moment Units: Coefficients",
        "     Software : solver version 2612, build #10282026",
        "     Date: 10/31/2026, Time: 0218 hours (local)",
    ]
)


def test_fr3410_the_closing_dashes_end_the_table_and_the_footer_is_not_read(tmp_path):
    rows = "\n".join(_row(p) for p in POINTS)
    body = HEADER.format(count=len(POINTS)) + "\n" + rows + "\n" + FOOTER + "\n"
    np.testing.assert_allclose(read_aero_nodes(_write(tmp_path, body)), POINTS)


def test_fr3410_a_row_that_is_not_numbers_is_still_refused(tmp_path):
    """Only a line of dashes is skipped: a broken row still stops the call, naming its line."""
    body = HEADER.format(count=len(POINTS)) + "\n" + _row(POINTS[0]) + "\n  0.1, 0.2, nan-ish\n"
    with pytest.raises(FsiInputError, match="is not 9 finite numbers"):
        read_aero_nodes(_write(tmp_path, body))


def test_fr3410_a_short_file_is_still_refused_by_its_count(tmp_path):
    body = HEADER.format(count=3) + "\n" + "\n".join(_row(p) for p in POINTS) + "\n"
    with pytest.raises(FsiInputError, match="declares 3 aerodynamic nodes but holds 2 rows"):
        read_aero_nodes(_write(tmp_path, body))
