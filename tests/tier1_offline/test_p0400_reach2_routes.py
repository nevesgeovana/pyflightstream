"""P0400-REACH2: the workspace route runs the public probe and far-field functions (PFS-2140.011).

The owner's rule of 2026-10-12: every public capability is reached from the
workspace. Where the route did the job with a duplicate of a public function,
the route now calls the function, and each test pins both halves: the public
function is what the route runs (a spy that the duplicate never called), and
what the route produces is unchanged (the value or the text the duplicate
produced, computed beside it).
"""

from __future__ import annotations

import numpy as np
import pytest

import pyflightstream.post.farfield_fields as farfield_fields
from pyflightstream.cases._farfield_spec import LedgersSpec
from pyflightstream.farfield import sample_coverage, transverse_flux, transverse_force

_REQUIREMENT = "P0400-REACH2"


class _Rotor:
    axis = "X"
    diameter_m = 2.0
    x_m, y_m, z_m = 0.5, 0.0, 0.0


def _spy(monkeypatch, module, name: str, function) -> list:
    """Replace ``module.name`` by a wrapper of ``function`` that records each call."""
    calls: list = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper, raising=False)
    return calls


def _sheared_fields():
    """A lattice sampled with a sheared, crossflowing stream and one missing sample."""
    spec = LedgersSpec(rotor="R", stations=(-1.0, 0.5, 1.5), n_r=6, n_psi=16, m_max=2)
    lattice, points_m, axis = farfield_fields.rotor_lattice(spec, _Rotor())
    y, z = points_m[:, 1], points_m[:, 2]
    velocity = np.column_stack([12.0 + 0.4 * y, 0.3 * z - 0.2, 0.5 + 0.25 * y * y])
    velocity[len(points_m) // 2 + 3] = np.nan
    samples = farfield_fields.ProbeSamples(points_m, velocity, 0.01 * y)
    fields = farfield_fields.lattice_samples(samples, slice(0, len(points_m)), lattice, axis, q=0.0)
    return spec, fields


@pytest.mark.requirement("FR-38")
def test_p0400_reach2_the_ledger_runs_transverse_force_and_sample_coverage(monkeypatch):
    """P0400-REACH2 (PFS-2139.008): FY and FZ are transverse_force's plane term, COVERAGE
    is sample_coverage, and each value is the one the ledger wrote before."""
    spec, fields = _sheared_fields()
    forces = _spy(monkeypatch, farfield_fields, "transverse_force", transverse_force)
    coverages = _spy(monkeypatch, farfield_fields, "sample_coverage", sample_coverage)
    rows = farfield_fields.ledger_values(fields, spec, rho=1.2, speed=12.0, near=(3.0, 1.0))
    assert forces and coverages, (_REQUIREMENT, "the ledger runs the public balances")
    fy = transverse_flux(fields, 1.2, component="v")
    fz = transverse_flux(fields, 1.2, component="w")
    finite = np.isfinite(fields["u"]).mean(axis=(-2, -1))
    assert finite.min() < 1.0, "the fixture misses a sample"
    for index, row in enumerate(rows):
        assert row["COVERAGE"] == float(finite[index])
        if index:
            # The duplicate's arithmetic, bit for bit (NaN where a sample is missing).
            np.testing.assert_array_equal(
                [row["FY_PLANE_N"], row["FZ_PLANE_N"]],
                [float(fy[index] - fy[0]), float(fz[index] - fz[0])],
            )
    assert any(np.isfinite(row.get("FZ_PLANE_N", np.nan)) for row in rows[1:])
