"""Direct morphing must preserve the solver's vertex count and row order."""

import numpy as np
import pytest

from pyflightstream._textio import write_text
from pyflightstream.fsi._direct_morphing import read_aero_nodes
from pyflightstream.fsi.errors import FsiInputError


def _nodes(tmp_path, second, count=2):
    path = tmp_path / "FSInodes.txt"
    write_text(
        path,
        "Aeroelastic coordinate system: ROTOR_SMRP\n"
        f"Total elastic aerodynamic nodes: {count}\n"
        "X, Y, Z, nx, ny, nz, Fx, Fy, Fz\n"
        "1, 2, 3, 0, 0, 1, 0, 0, 0\n" + second,
    )
    return path


@pytest.mark.parametrize(
    "second",
    [
        "4, 5, 6, 0, 0, 1, 0, 0\n",
        "bad, 5, 6, 0, 0, 1, 0, 0, 0\n",
        "nan, 5, 6, 0, 0, 1, 0, 0, 0\n",
        "4, 5, 6, 0, 0, 1, inf, 0, 0\n",
        "",
    ],
)
def test_a_damaged_aerodynamic_row_is_refused_instead_of_dropped(tmp_path, second):
    """P0370-S6-DIRECT-MORPHING (FR-341): every declared vertex must yield one finite row."""
    with pytest.raises(FsiInputError, match="FSInodes.txt"):
        read_aero_nodes(_nodes(tmp_path, second))


def test_a_complete_aerodynamic_list_keeps_its_order(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): positions preserve the solver's row identities."""
    path = _nodes(tmp_path, "4, 5, 6, 0, 0, 1, 0, 0, 0\n")
    np.testing.assert_array_equal(read_aero_nodes(path), [[1, 2, 3], [4, 5, 6]])
