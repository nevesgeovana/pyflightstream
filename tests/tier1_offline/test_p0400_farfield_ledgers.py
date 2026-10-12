"""P0400-LEDGERS: the balances from a point's probes, instant and average (FR-38 R1 to R7).

Synthetic lattices sampled with analytic fields: a uniform stream, a stream
read in a frame turning with a rotor, and per-step rows averaged. Each test
goes through the public functions the post step calls.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.cases._farfield_spec import LedgersSpec
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    ProbeSamples,
    average_rows,
    far_samples,
    lattice_samples,
    ledger_values,
    rotor_lattice,
    unsteady_samples,
)


class _Rotor:
    axis = "X"
    diameter_m = 2.0
    x_m, y_m, z_m = 0.5, 0.0, 0.0


_SPEC = LedgersSpec(rotor="R", stations=(-1.0, 0.5, 1.5), n_r=6, n_psi=16, m_max=2)


def _uniform(points: np.ndarray, speed: float) -> ProbeSamples:
    velocity = np.tile([speed, 0.0, 0.0], (len(points), 1))
    return ProbeSamples(points, velocity, np.zeros(len(points)))


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_the_lattice_is_found_by_its_positions():
    """P0400-LEDGERS (FR-455 R2): a lattice behind other probes, in millimetres, and the plane."""
    lattice, points_m, _axis = rotor_lattice(_SPEC, _Rotor())
    other = np.zeros((7, 3)) + 99.0
    positions = np.vstack([other, points_m * 1000.0])
    samples = _uniform(positions, 10.0)
    at, plane, why = far_samples(samples, lattice_m=points_m, plane_count=4, per_m=1000.0)
    assert not why and at == slice(7, 7 + lattice.point_count)
    assert plane == slice(3, 7), "the plane is the points just before an added lattice"
    _, _, why = far_samples(samples, lattice_m=points_m + 0.5, plane_count=0, per_m=1000.0)
    assert "no point set" in why


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_a_uniform_stream_closes_every_balance():
    """P0400-LEDGERS (FR-38 R2): constant mass flow, zero forces, the inlet row NA."""
    lattice, points_m, axis = rotor_lattice(_SPEC, _Rotor())
    samples = _uniform(points_m, 12.0)
    fields = lattice_samples(samples, slice(0, len(points_m)), lattice, axis, q=0.0)
    rows = ledger_values(fields, _SPEC, rho=1.2, speed=12.0, near=(0.0, 1.0))
    assert [row["STATION_X_R"] for row in rows] == [-1.0, 0.5, 1.5]
    assert "FX_N" not in rows[0] and "FY_PLANE_N" not in rows[0], "the inlet row is NA"
    mdot = [row["MDOT_KG_S"] for row in rows]
    assert mdot[0] == pytest.approx(mdot[-1]) and rows[0]["MASS_SPREAD"] == pytest.approx(0.0)
    for row in rows[1:]:
        assert row["FX_N"] == pytest.approx(0.0, abs=1e-9)
        assert row["FZ_PLANE_N"] == pytest.approx(0.0, abs=1e-9)
        assert row["FZ_PLANE_HARMONIC_N"] == pytest.approx(0.0, abs=1e-9)
        assert row["TORQUE_NM"] == pytest.approx(0.0, abs=1e-9)
    assert set(rows[1]) <= set(LEDGER_COLUMNS)


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_an_unselected_balance_stays_out():
    """P0400-LEDGERS (FR-38 R2): a balance the table does not select is not written."""
    spec = LedgersSpec(rotor="R", stations=(-1.0, 1.0), n_r=4, n_psi=16, m_max=2, balances=["mass"])
    lattice, points_m, axis = rotor_lattice(spec, _Rotor())
    fields = lattice_samples(_uniform(points_m, 5.0), slice(0, len(points_m)), lattice, axis, q=0.0)
    rows = ledger_values(fields, spec, rho=1.0, speed=5.0, near=(0.0, 1.0))
    assert "MDOT_KG_S" in rows[1] and "FX_N" not in rows[1] and "TORQUE_NM" not in rows[1]


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_the_turning_frame_is_converted_to_the_hub():
    """P0400-LEDGERS (FR-453 R8): a still stream read in the rotor's frame has no swirl after."""
    lattice, points_m, axis = rotor_lattice(_SPEC, _Rotor())
    omega, shaft, origin = 30.0, np.array([1.0, 0.0, 0.0]), np.array([0.5, 0.0, 0.0])
    relative = np.cross(shaft * omega, points_m - origin)
    turning = ProbeSamples(
        points_m, np.tile([8.0, 0.0, 0.0], (len(points_m), 1)) - relative, np.zeros(len(points_m))
    )
    raw = lattice_samples(turning, slice(0, len(points_m)), lattice, axis, q=0.0)
    hub = lattice_samples(
        turning, slice(0, len(points_m)), lattice, axis, q=0.0, hub=(omega, shaft, origin)
    )
    assert np.abs(raw["v_theta"]).max() > 1.0, "the turning frame carries the rotation"
    assert np.abs(hub["v_theta"]).max() == pytest.approx(0.0, abs=1e-9)


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_unsteady_samples_read_each_vertex():
    """P0400-LEDGERS (FR-455 R9): fluid plots by vertex; a missing plot is NaN, never zero."""
    series = {
        "VX1": np.array([1.0, 2.0]),
        "VY1": np.array([0.0, 0.0]),
        "VZ1": np.array([0.0, 0.0]),
        "CP_REF1": np.array([0.1, 0.2]),
    }
    positions = {1: (0.0, 0.0, 0.0, "REFERENCE"), 2: (1.0, 0.0, 0.0, "REFERENCE")}
    samples = unsteady_samples(series, positions, 1)
    assert samples.velocity[0].tolist() == [2.0, 0.0, 0.0] and samples.cp[0] == 0.2
    assert math.isnan(samples.velocity[1, 0]) and math.isnan(samples.cp[1])


@pytest.mark.requirement("FR-38")
def test_p0400_ledgers_the_average_is_of_each_steps_balance():
    """P0400-LEDGERS (FR-38 R7): per-step rows averaged cell by cell; a NaN step stays NaN."""
    steps = [
        [("P", 1, "R", 1.0, 4.0), ("P", 1, "R", 2.0, 1.0)],
        [("P", 2, "R", 3.0, float("nan")), ("P", 2, "R", 4.0, 3.0)],
    ]
    averaged = average_rows(steps, 3)
    assert averaged[0][:4] == ("P", "AVERAGE", "R", 2.0) and math.isnan(averaged[0][4])
    assert averaged[1][3:] == (3.0, 2.0)
