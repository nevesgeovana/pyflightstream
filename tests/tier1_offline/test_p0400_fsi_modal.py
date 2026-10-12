"""Tier 1: the modal and rotating-solve items of the FSI lane of 0.40.0.

P0400-MODALMASS (PFS-2095.010), P0400-FLAPSOFTEN (PFS-2085.002),
P0400-CAMPBELLCONV (PFS-2088.003), P0400-TORSIONARRAY (PFS-2095.011),
P0400-CGOFFSET (PFS-2085.013), P0400-FAMILYTRACK (PFS-2095.012) and
P0400-SOUTHWELL (PFS-2095.013). Each test failed on the code before its fix.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.fsi import beam, centrifugal
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.sections import blade_properties_from_sections
from pyflightstream.fsi.state import TwistIterationError

PLATE = [(0.02, 0.002), (-0.02, 0.002), (-0.02, -0.002), (0.02, -0.002)]


def plate_config(pitch_deg: float = 10.0, omega: float = 0.0, **blade_updates) -> FsiConfig:
    """A flat titanium plate blade on three stations, uniform in every distribution."""
    blade = blade_properties_from_sections(
        [0.1, 0.3, 0.5],
        [PLATE] * 3,
        [0.04] * 3,
        [pitch_deg] * 3,
        "ti-6al-4v-grade5-annealed",
        geometry_source="a flat 40 x 4 mm plate",
    )
    data = {**blade.model_dump(), **blade_updates}
    return FsiConfig.model_validate({"blade_count": 2, "omega_rad_per_s": omega, "blade": data})


def test_p0400_modalmass_a_station_without_twist_inertia_is_refused_by_name():
    """P0400-MODALMASS: a free station lumping no twist inertia is refused, naming it."""
    cfg = plate_config()
    i1 = list(cfg.blade.inertia_major_kg_m)
    i2 = list(cfg.blade.inertia_minor_kg_m)
    i1[1] = i2[1] = 0.0
    bare = plate_config(inertia_major_kg_m=i1, inertia_minor_kg_m=i2)
    model = beam.build_beam_model(bare)
    beam.solve_static(model)
    with pytest.raises(FsiInputError, match=r"station 1 .*twist inertia"):
        beam.modal_frequencies(model, bare, n_modes=4)


def _first_flap(result: beam.ModalResult) -> float:
    return next(
        f for f, k in zip(result.frequencies_rad_per_s, result.kinds, strict=True) if k == "flap"
    )


def test_p0400_flapsoften_the_modal_problem_carries_the_in_plane_softening():
    """P0400-FLAPSOFTEN: omega_flap^2(beta) = omega_flap^2(0) - Omega^2 sin^2(beta).

    The oracle, by hand: with mu uniform, the softening the static solve
    applies, mu Omega^2 sin^2(beta) per unit span lumped over the tributary
    lengths, is Omega^2 sin^2(beta) times the lumped flap mass matrix. A
    stiffness term proportional to the mass matrix shifts every flap
    eigenvalue by exactly that factor, and flap and torsion do not couple in
    this beam, so the pitched blade's flap frequencies are the flat blade's
    lowered by Omega^2 sin^2(beta) in the squares. The geometric stiffness of
    the tension does not depend on the pitch.
    """
    omega = 150.0
    beta = 25.0
    flat = centrifugal.rotating_frequencies(plate_config(0.0, omega), n_modes=4)
    pitched = centrifugal.rotating_frequencies(plate_config(beta, omega), n_modes=4)
    expected = math.sqrt(_first_flap(flat) ** 2 - omega**2 * math.sin(math.radians(beta)) ** 2)
    assert _first_flap(pitched) == pytest.approx(expected, rel=1e-9)
    assert _first_flap(pitched) < _first_flap(flat)


def test_p0400_flapsoften_a_flap_stiffness_entry_count_is_held_to_the_stations():
    """P0400-FLAPSOFTEN: the new modal term is sampled at the configuration stations."""
    cfg = plate_config()
    model = beam.build_beam_model(cfg)
    beam.solve_static(model)
    with pytest.raises(FsiInputError, match="flap_stiffness_n_per_m has 2 entries"):
        beam.modal_frequencies(model, cfg, flap_stiffness_n_per_m=[0.0, 0.0])


def test_p0400_campbellconv_an_unsettled_static_solve_is_refused():
    """P0400-CAMPBELLCONV: no modes are linearized about an unconverged twist.

    A plate at a tenth of its torsional stiffness, 30 deg of pitch and
    1000 rad/s: the propeller moment outweighs the stiffness and the inner
    iteration exhausts its solves (measured, residual about 1.6 rad).
    """
    base = plate_config(30.0, 1000.0)
    soft = [0.1 * g for g in base.blade.torsion_stiffness_n_m2]
    cfg = plate_config(30.0, 1000.0, torsion_stiffness_n_m2=soft)
    assert not centrifugal.solve_rotating_static(cfg).converged
    with pytest.raises(TwistIterationError, match="did not converge"):
        centrifugal.rotating_frequencies(cfg, n_modes=2)


def test_p0400_torsionarray_a_numpy_torsion_distribution_is_accepted():
    """P0400-TORSIONARRAY: an array solves as the same list does."""
    cfg = plate_config(10.0, 100.0)
    torsion = np.array([0.5, 0.3, 0.1])
    from_array = centrifugal.solve_rotating_static(cfg, torsion_moment_n_m_per_m=torsion)
    from_list = centrifugal.solve_rotating_static(cfg, torsion_moment_n_m_per_m=list(torsion))
    assert from_array.solution == from_list.solution


def test_p0400_torsionarray_an_empty_torsion_distribution_is_refused():
    """P0400-TORSIONARRAY: empty is a wrong length, not 'no torsion'."""
    with pytest.raises(FsiInputError, match="torsion_moment_n_m_per_m has 0 entries"):
        centrifugal.solve_rotating_static(plate_config(), torsion_moment_n_m_per_m=[])


def test_p0400_cgoffset_the_twist_inertia_carries_the_parallel_axis_term():
    """P0400-CGOFFSET: (I1 + I2 + mu d^2) l, computed by hand."""
    cfg = plate_config(cg_offset_chordwise_m=[0.003] * 3, cg_offset_normal_m=[0.004] * 3)
    _, twist = beam.lumped_station_masses(cfg)
    blade = cfg.blade
    tributary = [0.1, 0.2, 0.1]
    expected = [
        (blade.inertia_major_kg_m[i] + blade.inertia_minor_kg_m[i])
        + blade.mass_per_length_kg_per_m[i] * 0.005**2
        for i in range(3)
    ]
    assert twist == pytest.approx(
        [e * t for e, t in zip(expected, tributary, strict=True)], rel=1e-12
    )


def test_p0400_cgoffset_a_rotating_blade_with_a_cg_offset_is_warned():
    """P0400-CGOFFSET: the rotating model says it does not carry the offset."""
    cfg = plate_config(10.0, 100.0, cg_offset_chordwise_m=[0.003] * 3)
    with pytest.warns(PyflightstreamWarning, match="nonzero cg_offset on a rotating blade"):
        centrifugal.solve_rotating_static(cfg)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        centrifugal.solve_rotating_static(plate_config(10.0, 100.0))


def test_p0400_familytrack_a_family_absent_from_the_sweep_is_refused():
    """P0400-FAMILYTRACK: a didactic refusal, not a bare StopIteration."""
    data = centrifugal.campbell_sweep(plate_config(), [0.0, 10.0], n_modes=2)
    assert data.modal_results[0].kinds == ("flap", "flap")
    with pytest.raises(FsiInputError, match="larger n_modes"):
        data.family_track("torsion")


@pytest.mark.parametrize("omegas", [[10.0, 10.0, 10.0], [10.0, -10.0, 10.0]])
def test_p0400_southwell_one_omega_squared_is_refused(omegas):
    """P0400-SOUTHWELL: one distinct Omega^2 leaves the slope undefined."""
    with pytest.raises(FsiInputError, match="two distinct values of Omega"):
        centrifugal.southwell_fit(omegas, [1.0, 2.0, 3.0])
