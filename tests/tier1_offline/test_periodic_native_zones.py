"""A periodic row's native Tecplot holds one zone per copy, and is translated (0.30.0).

Measured on 26.124 (reports/RPT-087, 2026-09-28, a six-copy periodic
probe row): the native export of a row under ``SYMMETRY PERIODIC`` is six
complete files one after another, ``TITLE``, ``VARIABLES`` and ``ZONE`` each,
the modelled sector first, and zone k equals the k-th block of the VTK. The
0.29.0 reader refused it as "trailing data or multiple zones", and the point
that had solved was recorded FAILED_INCOMPLETE_OUTPUT. The copies share the
nodes of their seams, so the synthetic surface here puts two nodes of every
copy on the axis: one match over the whole disc is ambiguous there, and only
the copy-by-copy join translates it.
"""

import math

import numpy as np
import pytest

from pyflightstream.results import MalformedOutputError
from pyflightstream.results.surface import (
    REFERENCE_FRAME,
    VtkSurface,
    translate_surface_exports,
    translate_vtk_surface,
    write_vtk_surface,
)

COPIES = 6


def _copy_nodes(k: int) -> np.ndarray:
    """Four nodes of copy k: two on the axis (shared by every copy), two turned by k * 60 deg."""
    angle = 2.0 * math.pi * k / COPIES
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, c, s], [0.0, c, s]])


def _vtk() -> VtkSurface:
    """The whole disc as the VTK carries it: the modelled copy first, then its images."""
    points = np.vstack([_copy_nodes(k) for k in range(COPIES)])
    connectivity = np.concatenate([np.arange(4) + 4 * k for k in range(COPIES)])
    return VtkSurface(
        points=points,
        offsets=np.arange(0, 4 * COPIES + 1, 4),
        connectivity=connectivity,
        cell_data={"Cp_reference": np.array([-0.1 * (k + 1) for k in range(COPIES)])},
    )


def _strength(k: int, node: int) -> float:
    return 100.0 * (k + 1) + node


def _zone_text(k: int, at: np.ndarray | None = None) -> str:
    """One zone as the solver writes it, a file of its own, its nodes in another order.

    ``at`` places copy k's four nodes elsewhere (in their original order); by
    default they are :func:`_copy_nodes`.
    """
    order = [2, 0, 3, 1]  # native node i is original node order[i]
    nodes = (_copy_nodes(k) if at is None else at)[order]
    strength = [_strength(k, node) for node in order]
    # Faces of the one polygon 0-1-2-3 in native numbering (1-based):
    # original 0->1 is native 2->4, 1->2 is 4->1, 2->3 is 1->3, 3->0 is 3->2.
    edges = "2 4 4 1 1 3 3 2"

    def row(values) -> str:
        return " ".join(repr(float(v)) for v in values)

    return (
        'TITLE = "FlightStream solution"\n'
        'VARIABLES = "X", "Y", "Z", "Singularity_strength", "Cp"\n'
        "ZONE T=Solver, NODES=4, ELEMENTS=1, FACES=4, DATAPACKING=BLOCK, "
        "ZONETYPE=FEPolygon, NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0\n"
        f"{row(nodes[:, 0])}\n{row(nodes[:, 1])}\n{row(nodes[:, 2])}\n"
        f"{row(strength)}\n0.1 0.2 0.3 0.4\n{edges}\n1 1 1 1\n0 0 0 0\n"
    )


def _native(path, zones: int = COPIES):
    path.write_text("".join(_zone_text(k) for k in range(zones)), encoding="utf-8")
    return path


def _expected_strength() -> list[float]:
    return [_strength(k, node) for k in range(COPIES) for node in range(4)]


def test_a_six_zone_native_export_is_translated_copy_by_copy(tmp_path):
    vtk = write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="test")
    native = _native(tmp_path / "p_native_tecplot.dat")
    stated = translate_vtk_surface(
        vtk, tmp_path / "p.dat", frame=REFERENCE_FRAME, native_tecplot=native, periodic_copies=6
    )
    assert stated["node_mapping"]["periodic_copies"] == COPIES
    assert stated["node_mapping"]["matched_nodes"] == 4 * COPIES
    from pyflightstream.results.native_surface import (
        attach_native_strength_by_copy,
        read_native_tecplot_zones,
    )

    zones = read_native_tecplot_zones(native, zones=COPIES)
    joined, _ = attach_native_strength_by_copy(_vtk(), zones)
    assert joined.point_data["Singularity_strength"].tolist() == _expected_strength()
    text = (tmp_path / "p.dat").read_text(encoding="utf-8")
    assert "native values of 6 zones" in text


def test_one_match_over_the_whole_disc_would_be_ambiguous_at_the_seams(tmp_path):
    """The control: the copies share nodes, so the copy-by-copy join is what translates."""
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_zones,
    )

    zones = read_native_tecplot_zones(_native(tmp_path / "n.dat"), zones=COPIES)
    stacked = VtkSurface(
        points=np.vstack([zone.points for zone in zones]),
        offsets=np.arange(0, 4 * COPIES + 1, 4),
        connectivity=np.concatenate([zone.connectivity + 4 * k for k, zone in enumerate(zones)]),
        point_data={
            "Singularity_strength": np.concatenate(
                [zone.point_data["Singularity_strength"] for zone in zones]
            )
        },
    )
    with pytest.raises(MalformedOutputError, match="missing or ambiguous"):
        attach_native_strength(_vtk(), stacked)


def _turned_far_disc(tmp_path, shift, *, loads_x):
    """The disc written by a loads frame turned 45 degrees whose origin is 1e6 from
    the reference origin (as in test_native_nodal_surface): the VTK holds loads
    coordinates from X = ``loads_x`` near -1e6 at float32, the native the true reference ones,
    with copy 1 moved by ``shift`` in LOADS axes. Loads X rounds by about 0.03
    there and loads Y by about 1e-7, so the per-copy join must match in the
    loads frame, as the single-zone translation does (GOAL-034 Q8 CXQ8R7-1)."""
    from pyflightstream.results.surface import SurfaceFrame

    c = math.sqrt(0.5)
    frame = SurfaceFrame(
        origin=(1_000_000.0 * c, 1_000_000.0 * c, 0.0),
        axes=((c, c, 0.0), (-c, c, 0.0), (0.0, 0.0, 1.0)),
        index=2,
    )
    loads = _vtk().points + np.array([loads_x, 0.1, 0.0])
    surface = VtkSurface(
        points=loads.astype(np.float32).astype(float),
        offsets=_vtk().offsets,
        connectivity=_vtk().connectivity,
        cell_data=dict(_vtk().cell_data),
    )
    vtk = write_vtk_surface(tmp_path / "p.vtk", surface, title="test")
    moved = loads.copy()
    moved[4:8] += np.asarray(shift, dtype=float)
    reference = frame.to_reference(moved)
    native = tmp_path / "p_native_tecplot.dat"
    native.write_text(
        "".join(_zone_text(k, reference[4 * k : 4 * k + 4]) for k in range(COPIES)),
        encoding="utf-8",
    )
    return frame, vtk, native


def test_a_periodic_native_is_joined_copy_by_copy_in_a_turned_far_loads_frame(tmp_path):
    frame, vtk, native = _turned_far_disc(tmp_path, (0.0, 0.0, 0.0), loads_x=-999_999.9)
    record = translate_vtk_surface(
        vtk, tmp_path / "p.dat", frame=frame, native_tecplot=native, periodic_copies=COPIES
    )
    mapping = record["node_mapping"]
    assert mapping["periodic_copies"] == COPIES
    assert mapping["coordinate_tolerance_frame"] == frame.record()
    assert mapping["coordinate_tolerance_by_axis"][1] < 1e-5


def test_a_periodic_copy_moved_along_its_loads_y_is_refused(tmp_path):
    """The refusal twin: 0.02 along loads Y, where the VTK rounds by 1e-7. A join
    in the reference frame carries the loads-X rounding onto reference X and Y
    and lends copy 1 its strength anyway. The disc starts at loads X = -1e6,
    which float32 writes exactly, so no rounding offsets the shift."""
    frame, vtk, native = _turned_far_disc(tmp_path, (0.0, 0.02, 0.0), loads_x=-1_000_000.0)
    with pytest.raises(MalformedOutputError, match="missing or ambiguous"):
        translate_vtk_surface(
            vtk, tmp_path / "p.dat", frame=frame, native_tecplot=native, periodic_copies=COPIES
        )


@pytest.mark.parametrize("declared", [1, 5, 7])
def test_a_zone_count_other_than_the_declared_copies_is_refused_naming_both(tmp_path, declared):
    vtk = write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="test")
    native = _native(tmp_path / "p_native_tecplot.dat")
    with pytest.raises(MalformedOutputError) as caught:
        translate_vtk_surface(
            vtk,
            tmp_path / "p.dat",
            frame=REFERENCE_FRAME,
            native_tecplot=native,
            periodic_copies=declared,
        )
    message = str(caught.value)
    assert "holds 6 zone" in message
    assert f"{declared} w" in message  # "1 was expected", "5 were expected"
    assert not (tmp_path / "p.dat").exists()


def test_fewer_zones_than_the_declared_copies_is_refused_naming_both(tmp_path):
    from pyflightstream.results.native_surface import read_native_tecplot_zones

    with pytest.raises(MalformedOutputError, match="holds 4 zone\\(s\\) and 6 were expected"):
        read_native_tecplot_zones(_native(tmp_path / "n.dat", zones=4), zones=6)


def test_the_run_translates_by_the_copies_its_translation_records(tmp_path):
    """The batch the run calls: with the record's count it writes, without it it refuses."""
    write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="test")
    _native(tmp_path / "p_native_tecplot.dat")
    entry = {
        "vtk": "p.vtk",
        "dat": "p.dat",
        "native_tecplot": "p_native_tecplot.dat",
        "frame": {"frame": 1, "origin": [0.0, 0.0, 0.0], "axes": np.eye(3).tolist()},
    }
    refused = translate_surface_exports(tmp_path, [entry])
    assert refused[0]["written"] == []
    assert "holds 6 zones and 1 was expected" in refused[0]["problems"][0]
    written = translate_surface_exports(tmp_path, [{**entry, "periodic_copies": COPIES}])
    assert written[0]["written"] == ["p.dat"], written[0]["problems"]
    assert written[0]["artifacts"]["p.dat"]["node_mapping"]["periodic_copies"] == COPIES


def test_a_periodic_row_records_its_copy_count_on_the_translation():
    from pyflightstream.cases.workflows import build_script, with_tecplot_source
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case

    outputs = with_tecplot_source(["p.txt", "p.dat", "p.vtk"])
    periodic = steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES=6).model_copy(
        update={"outputs": outputs}
    )
    script = Script("26.124")
    build_script(periodic, script)
    assert script.periodic_copies == 6
    assert script.surface_translations[0]["periodic_copies"] == 6
    plain = steady_case().model_copy(update={"outputs": outputs})
    script = Script("26.124")
    build_script(plain, script)
    assert script.periodic_copies is None
    assert "periodic_copies" not in script.surface_translations[0]
