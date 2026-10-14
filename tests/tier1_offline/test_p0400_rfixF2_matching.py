"""P0400-RFIXF2-MATCHING: each far-field set is matched in its own frame, to the export's precision.

PFS-2081.102 (REL2-001): a declared lattice recorded in a translated frame (MRP)
is matched among that frame's points only, in its local coordinates, so a later
reference-frame entry whose positions coincide with the lattice's reference
positions never lends it its velocities.

PFS-2081.103 (REL2-002): the matching tolerance is the export's printed
precision of each coordinate, never a fraction of the distance from the origin;
a plane of another grid at large coordinates, or a legacy export holding a
distant unrelated point, is refused rather than integrated with the wrong area.
Every fixture is synthetic: a uniform stream, a uniform crossflow.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF2.

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.farfield import mass_closure
from pyflightstream.post.farfield_fields import (
    FarLayout,
    ProbeSamples,
    far_samples,
    lattice_samples,
    plane_values,
    recorded_layout,
    steady_samples,
    unsteady_samples,
)
from pyflightstream.probes.layouts import farfield_plane, lattice_points
from tests.tier1_offline.test_p0400_rfixF_layout import _export

pytestmark = pytest.mark.requirement("FR-455")

_LATTICE = LatticeShape.model_validate(
    {"frame": "MRP", "tip_radius_m": 0.5, "stations": [2.0], "n_r": 2, "n_psi": 8}
).build(1.0)
_ORIGIN = np.array([0.25, 0.0, 0.0])
_LOCAL = lattice_points(_LATTICE, axis="X")
_SHAPE = {
    "kind": "lattice",
    "source": "declared",
    "entry": 1,
    "count": len(_LOCAL),
    "lattice": _LATTICE.model_dump(mode="json"),
    "axis": "X",
    "origin_m": [float(v) for v in _ORIGIN],
    "positions_frame": "MRP",
}


def _unsteady(entries: list[tuple[np.ndarray, str, float]]) -> ProbeSamples:
    """One step of fluid plots: each entry's points (native = m), frame label and axial speed."""
    positions: dict[int, tuple[float, float, float, str]] = {}
    series: dict[str, np.ndarray] = {}
    vertex = 0
    for points, frame, speed in entries:
        for point in points:
            vertex += 1
            positions[vertex] = (*(float(v) for v in point), frame)  # type: ignore[assignment]
            series[f"VX{vertex}"] = np.array([speed])
            series[f"VY{vertex}"] = np.array([0.0])
            series[f"VZ{vertex}"] = np.array([0.0])
            series[f"CP_REF{vertex}"] = np.array([0.0])
    return unsteady_samples(series, positions, 0)


def _mdot(samples: ProbeSamples, block: slice | np.ndarray) -> float:
    fields = lattice_samples(samples, block, _LATTICE, "X", q=0.5 * 1.225 * 20.0**2)
    return float(mass_closure(fields, 1.225).mdot[0])


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_translated_frame_lattice_reads_its_own_samples():
    """P0400-RFIXF2-MATCHING (FR-455 R2, PFS-2081.102): MRP lattice before a REFERENCE entry.

    The lattice's 24 points are recorded in MRP at their local positions with
    20 m/s; the next entry, in REFERENCE, stands at the lattice's reference
    positions (local plus the frame origin) with 50 m/s. Post must read the
    20 m/s, and the balance must be the lattice's own mass flow.
    """
    samples = _unsteady([(_LOCAL, "MRP", 20.0), (_LOCAL + _ORIGIN, "REFERENCE", 50.0)])
    lattice, plane, why = far_samples(samples, recorded_layout([_SHAPE]), per_m=1.0)
    assert why == "" and plane is None
    assert np.allclose(samples.velocity[lattice], [20.0, 0.0, 0.0])
    alone = _unsteady([(_LOCAL, "MRP", 20.0)])
    assert _mdot(samples, lattice) == pytest.approx(_mdot(alone, slice(0, len(_LOCAL))))


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_frame_lattice_found_twice_in_its_frame_is_refused():
    """P0400-RFIXF2-MATCHING (FR-455 R2): two MRP entries at the same points are refused."""
    samples = _unsteady([(_LOCAL, "MRP", 20.0), (_LOCAL, "MRP", 50.0)])
    lattice, _, why = far_samples(samples, recorded_layout([_SHAPE]), per_m=1.0)
    assert lattice is None and "2 times" in why


def _plane(center: tuple[float, float, float], grid: float) -> np.ndarray:
    return farfield_plane(
        center,
        direction=(1.0, 0.0, 0.0),
        distance=0.0,
        half_width=grid,
        half_height=grid,
        spacing=grid,
    ).points


def _plane_shape(center: tuple[float, float, float], grid: float) -> dict:
    return {
        "kind": "plane",
        "source": "added",
        "entry": None,
        "count": 9,
        "center_m": list(center),
        "direction": [1.0, 0.0, 0.0],
        "half_width_m": grid,
        "half_height_m": grid,
        "spacing_m": grid,
    }


def _crossflow(points: np.ndarray) -> ProbeSamples:
    """A steady export of ``points`` in a 10 m/s stream with a 1 m/s crossflow."""
    velocity = np.tile([10.0, 1.0, 0.0], (len(points), 1))
    return steady_samples(_export(points, velocity))


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_distant_plane_of_another_grid_is_refused():
    """P0400-RFIXF2-MATCHING (FR-455 R2, PFS-2081.103): 4 m2 laid, 16 m2 recorded, at x = 30 km.

    The control is the recorded 4 m2 plane at the same place: matched, and its
    induced drag is the crossflow's 0.5 rho v^2 S = 2 N.
    """
    center = (30000.0, 0.0, 0.0)
    samples = _crossflow(_plane(center, 1.0))
    _, plane, why = far_samples(samples, recorded_layout([_plane_shape(center, 2.0)]), per_m=1.0)
    assert plane is None and "no point set" in why
    _, plane, why = far_samples(samples, recorded_layout([_plane_shape(center, 1.0)]), per_m=1.0)
    assert why == "" and plane == slice(0, 9)
    flow = (1.0, 10.0, 0.0, 0.0)
    values = plane_values(samples, plane, flow=flow, grid=(1.0, 1.0, 1.0), per_m=1.0, q_ref=50.0)
    assert values["D"] == pytest.approx(2.0, rel=1e-6)


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_legacy_export_with_a_distant_point_keeps_a_tight_tolerance():
    """P0400-RFIXF2-MATCHING (FR-455 R2, PFS-2081.103): one far point does not loosen matching.

    A record without a layout matches the plane by shape. A distant unrelated
    point before a 1 m grid must not make a 2 m grid's shape match it.
    """
    points = np.vstack([[[1.0e6, 0.0, 0.0]], _plane((5.0, 0.0, 0.0), 1.0)])
    samples = _crossflow(points)
    wider = FarLayout(
        plane_m=_plane((0.0, 0.0, 0.0), 2.0), plane_grid=(2.0, 2.0, 2.0), plane_placed=False
    )
    _, plane, why = far_samples(samples, wider, per_m=1.0)
    assert plane is None and "no point set" in why
    same = FarLayout(
        plane_m=_plane((0.0, 0.0, 0.0), 1.0), plane_grid=(1.0, 1.0, 1.0), plane_placed=False
    )
    _, plane, why = far_samples(samples, same, per_m=1.0)
    assert why == "" and plane == slice(1, 10)


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_layout_finer_than_the_printed_digits_is_refused():
    """P0400-RFIXF2-MATCHING (FR-455 R2, PFS-2081.103): seven digits cannot place 1 m at 3e7 m."""
    center = (3.0e7, 0.0, 0.0)
    samples = _crossflow(_plane(center, 1.0))
    _, plane, why = far_samples(samples, recorded_layout([_plane_shape(center, 1.0)]), per_m=1.0)
    assert plane is None and "printed precision" in why
