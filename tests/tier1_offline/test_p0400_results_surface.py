"""P0400-RESULTS: the VTK surface reader and the surface translations of 0.40.0 (lane results)."""

from __future__ import annotations

import pytest

from pyflightstream.results import (
    read_vtk_surface,
)
from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.native_surface import read_native_tecplot_surface
from tests.tier1_offline.test_native_nodal_surface import _native

pytestmark = pytest.mark.requirement("P0400-RESULTS-SURFACE")

#: A two-triangle solver surface: the layout of the reader's own example.
VTK = (
    "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
    "POINTS 4 float\n0 0 0\n1 0 0\n0 1 0\n1 1 0\nPOLYGONS 2 8\n3 0 1 2\n3 1 3 2\n"
    "CELL_DATA 2\nSCALARS Cp_reference FLOAT\nLOOKUP_TABLE default\n-0.5\n0.25\n"
)

#: One translation, placed in the reference frame itself.
TRANSLATIONS = [
    {
        "vtk": "surface.vtk",
        "dat": "surface.dat",
        "frame": {"origin": [0, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    }
]


# --- PFS-2095.023: truncated or malformed VTK header lines raise catalogued errors ---


@pytest.mark.parametrize(
    ("text", "error", "message"),
    [
        (
            VTK.split("POINTS")[0] + "POINTS\n",
            IncompleteOutputError,
            "POINTS.*states no count.*truncated",
        ),
        (
            VTK.split("POLYGONS")[0] + "POLYGONS 2\n",
            IncompleteOutputError,
            "POLYGONS.*states no count.*truncated",
        ),
        (
            VTK.split("CELL_DATA")[0] + "CELL_DATA\n",
            IncompleteOutputError,
            "CELL_DATA.*states no count.*truncated",
        ),
        (
            VTK.replace("POINTS 4 float", "POINTS four float"),
            MalformedOutputError,
            "POINTS.*'four'.*whole count",
        ),
        (
            VTK.replace("POINTS 4 float", "POINTS -4 float"),
            MalformedOutputError,
            "POINTS.*negative count -4.*nonnegative",
        ),
        (
            VTK.replace("POLYGONS 2 8", "POLYGONS 2"),
            MalformedOutputError,
            "POLYGONS.*states no count",
        ),
        (
            VTK.replace("POLYGONS 2 8", "POLYGONS 2 8.5"),
            MalformedOutputError,
            "POLYGONS.*'8.5'.*whole count",
        ),
        (
            VTK.replace("CELL_DATA 2", "CELL_DATA two"),
            MalformedOutputError,
            "CELL_DATA.*'two'.*whole count",
        ),
        (
            VTK.replace("Cp_reference FLOAT", "Cp_reference FLOAT one"),
            MalformedOutputError,
            "SCALARS.*Cp_reference.*'one'.*component count",
        ),
    ],
    ids=[
        "cut-after-POINTS",
        "cut-inside-POLYGONS",
        "cut-after-CELL_DATA",
        "mangled-POINTS",
        "negative-POINTS",
        "short-POLYGONS",
        "fractional-POLYGONS",
        "mangled-CELL_DATA",
        "mangled-SCALARS-components",
    ],
)
def test_p0400_results_a_cut_or_mangled_vtk_header_is_a_catalogued_refusal(
    tmp_path, text, error, message
):
    """P0400-RESULTS (PFS-2095.023): no bare IndexError or ValueError escapes the reader."""
    path = tmp_path / "surface.vtk"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(error, match=message):
        read_vtk_surface(path)


def test_p0400_results_the_vtk_fixture_reads(tmp_path):
    """P0400-RESULTS (PFS-2095.023): control, the unmangled surface reads."""
    path = tmp_path / "surface.vtk"
    path.write_text(VTK, encoding="utf-8")
    surface = read_vtk_surface(path)
    assert (surface.n_points, surface.n_cells) == (4, 2)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("variables", "VARIABLES needs an equals sign.*quoted variable names"),
        ("location", "variable location.*invalid index.*whole index"),
        ("encoding", "Singularity_strength contains invalid values"),
        ("count", "NODES count cannot be read as a whole number"),
    ],
)
def test_p0400_results_malformed_native_headers_raise_catalogued_errors(tmp_path, change, message):
    """P0400-RESULTS-SURFACE (PFS-2095.023): native text cannot raise a raw parser error."""
    path = _native(tmp_path / "native.dat")
    content = path.read_bytes()
    if change == "variables":
        content = content.replace(b"VARIABLES=", b"VARIABLES ")
    elif change == "location":
        content = content.replace(b"FACES=4,", b"FACES=4, VARLOCATION=([-1]=CELLCENTERED),")
    elif change == "count":
        content = content.replace(b"NODES=4", b"NODES=" + b"9" * 4500)
    else:
        content = content.replace(b"30 10 40 20", b"30 10 40 " + bytes([255]))
    path.write_bytes(content)
    with pytest.raises(MalformedOutputError, match=message):
        read_native_tecplot_surface(path)
