"""Tier 1: P0400-EASIGN (PFS-2104.013), the pitch-axis to elastic-axis moment transfer's sign.

The aerodynamic forces act at the pitch axis and the configuration's
``elastic_axis_offset_*`` runs from the pitch axis to the elastic axis, so
the moment about the elastic axis is M_PA + (r_PA - r_EA) x F = M_PA - e x F.
Both tests failed on the code before the fix, which added e x F.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.fsi.config import BladeProperties, FsiConfig
from pyflightstream.fsi.loads import SectionBlock, to_elastic_axis

STATIONS = [0.2, 0.6, 1.0]
SECTIONS = np.linspace(0.2, 1.0, 9)


def _config(ea_chordwise_m: float, ea_normal_m: float = 0.0) -> FsiConfig:
    """A section-frame blade (Omega zero): the export columns are the section axes."""
    n = len(STATIONS)
    blade = BladeProperties(
        station_radii_m=STATIONS,
        chord_m=[0.2] * n,
        mass_per_length_kg_per_m=[2.0] * n,
        inertia_major_kg_m=[1.0e-3] * n,
        inertia_minor_kg_m=[1.0e-4] * n,
        bending_stiffness_n_m2=[1.0e4] * n,
        torsion_stiffness_n_m2=[1.0e3] * n,
        elastic_axis_offset_chordwise_m=[ea_chordwise_m] * n,
        elastic_axis_offset_normal_m=[ea_normal_m] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    )
    return FsiConfig(blade_count=1, omega_rad_per_s=0.0, blade=blade)


def _block(chordwise: float, normal: float, moment: float) -> SectionBlock:
    k = len(SECTIONS)
    return SectionBlock(
        family="blade_1",
        offset_m=SECTIONS,
        chord_m=np.full(k, 0.2),
        x_qc_m=np.zeros(k),
        z_qc_m=np.zeros(k),
        fx_n_per_m=np.full(k, chordwise),
        fz_n_per_m=np.full(k, normal),
        moment_qc_nm_per_m=np.full(k, moment),
    )


def test_p0400_easign_lift_ahead_of_the_elastic_axis_twists_nose_up():
    """P0400-EASIGN: the physical oracle.

    Lift at the pitch axis with the elastic axis 5 cm aft of it acts ahead of
    the elastic axis and twists the section nose up: +10 N/m x 0.05 m. With
    the elastic axis ahead, the same lift twists it nose down.
    """
    lift = 10.0
    aft = to_elastic_axis(_block(0.0, lift, 0.0), _config(ea_chordwise_m=-0.05))
    assert aft.moment_ea_nm_per_m == pytest.approx(np.full(len(SECTIONS), +0.5))
    ahead = to_elastic_axis(_block(0.0, lift, 0.0), _config(ea_chordwise_m=+0.05))
    assert ahead.moment_ea_nm_per_m == pytest.approx(np.full(len(SECTIONS), -0.5))


def test_p0400_easign_the_transfer_is_the_cross_product_of_the_lever_from_the_elastic_axis():
    """P0400-EASIGN: an independent check with numpy's cross product.

    In the right-handed triad (chordwise, normal, spanwise) the moment about
    the elastic axis of a force F at the pitch axis is M_PA plus the spanwise
    component of (r_PA - r_EA) x F, with r_PA - r_EA = -e.
    """
    e = np.array([0.031, -0.012, 0.0])
    force = np.array([7.0, -23.0, 0.0])
    moment_pa = 1.7
    loads = to_elastic_axis(_block(force[0], force[1], moment_pa), _config(e[0], e[1]))
    expected = moment_pa + np.cross(-e, force)[2]
    assert loads.moment_ea_nm_per_m == pytest.approx(np.full(len(SECTIONS), expected), rel=1e-12)
