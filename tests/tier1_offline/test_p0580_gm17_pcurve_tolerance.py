"""P0580 G17: the written-pcurve check holds curved junction edges to the sewing tolerance.

The owner's decision: a curved junction edge (a blade-root cut of the spinner, a hole in a hub
face) is checked at the 0.01 mm sewing tolerance of the assembly junctions, and an iso trim keeps
1e-4 mm. Which edge is which is read from the trims' declared origin, never from a measured value.
"""

import tomllib
from pathlib import Path

import numpy as np

from pyflightstream.geometry import Propeller
from pyflightstream.geometry._generation import propeller_faces
from pyflightstream.workspace import _geom_propeller as gp

FIXTURES = Path(__file__).parent / "fixtures" / "propeller"


def spinner_component():
    data = tomllib.loads((FIXTURES / "simple_naca.toml").read_text(encoding="utf-8"))
    data["spinner"] = {
        "radius": 160.0,
        "nose_length": 180.0,
        "cylinder_length": 200.0,
        "nose_x": -250.0,
    }
    return Propeller(data).component()


def rows(iso_mm, junction_mm, junction_pieces=3):
    return 0, [
        {
            "boundary": 1,
            "iso_pieces": 4,
            "junction_pieces": junction_pieces,
            "iso_mm": iso_mm,
            "junction_mm": junction_mm,
        }
    ]


def run(report):
    return {c["id"]: c for c in gp.pcurve_checks(*report)}


def test_p0580_gm17_pcurve_junction_edge_at_5_micrometres_passes():
    """P0580-G17-PCURVE-JUNCTION: a junction edge 0.005 mm from its spatial trim passes."""
    checks = run(rows(iso_mm=0.0, junction_mm=0.005))
    assert checks["propeller.pcurve_3d_junction"]["status"] == "passed"
    assert checks["propeller.pcurve_3d_junction"]["limit"] == gp.SEW_MM == 0.01
    assert checks["propeller.pcurve_3d"]["status"] == "passed"


def test_p0580_gm17_pcurve_iso_trim_at_5_micrometres_fails():
    """P0580-G17-PCURVE-ISO: an iso trim 0.005 mm from its spatial trim still fails 1e-4 mm."""
    checks = run(rows(iso_mm=0.005, junction_mm=0.0))
    assert checks["propeller.pcurve_3d"]["status"] == "failed"
    assert checks["propeller.pcurve_3d"]["limit"] == 1e-4
    assert checks["propeller.pcurve_3d_junction"]["status"] == "passed"


def test_p0580_gm17_pcurve_junction_beyond_sewing_tolerance_fails():
    """P0580-G17-PCURVE-JUNCTION: a junction edge past 0.01 mm fails."""
    checks = run(rows(iso_mm=0.0, junction_mm=0.02))
    assert checks["propeller.pcurve_3d_junction"]["status"] == "failed"


def test_p0580_gm17_pcurve_without_junction_trims_is_skipped():
    """P0580-G17-PCURVE-JUNCTION: no declared junction leaves the check skipped, iso unchanged."""
    checks = run(rows(iso_mm=0.0, junction_mm=0.0, junction_pieces=0))
    assert checks["propeller.pcurve_3d_junction"]["status"] == "skipped"


def test_p0580_gm17_trims_declare_their_junction_edges():
    """P0580-G17-PCURVE-ORIGIN: the spinner's cut and hole trims carry their junction origin."""
    _, trims = propeller_faces(spinner_component())
    cut = [t for t in trims if t.junction]
    holed = [t for t in trims if t.inner]
    assert cut and holed
    for trim in cut:
        assert set(trim.junction) < set(trim.loop)
        assert any(piece not in trim.junction for piece in trim.loop)
        assert all(a[0] != b[0] or a[1] != b[1] for a, b in trim.junction)
    for trim in trims:
        if not trim.junction and not trim.inner:
            assert trim.to_dict().get("junction") is None


def test_p0580_gm17_written_piece_is_classified_from_declared_origin():
    """P0580-G17-PCURVE-ORIGIN: a piece on a declared iso side is iso, one on the cut is not."""
    _, trims = propeller_faces(spinner_component())
    blade = next(t for t in trims if t.junction)
    segments = gp.trim_segments([t.to_dict() for t in trims])
    junction = blade.junction[len(blade.junction) // 2]
    middle = (np.asarray(junction[0]) + np.asarray(junction[1])) / 2
    assert gp.written_junction(middle, segments)
    iso = next(p for p in blade.loop if p not in blade.junction)
    assert not gp.written_junction((np.asarray(iso[0]) + np.asarray(iso[1])) / 2, segments)
    assert not gp.written_junction(np.array([0.5, 0.5]), (segments[0][:0], segments[1]))
