"""Tier 1, v0.23.0 item 6: the THRUST and TORQUE of one rotor, from what ran.

`rotor_coefficients` has taken `thrust_n` and `torque_nm` since the first commit
of this release and NOTHING computed them. A release round measured it: the
function had zero callers, its tests passed literals, and the socket was empty.

WHAT THE RUN ACTUALLY LEFT, which is what makes this derivable without a re-run
and therefore inside the owner's acceptance rule. The loads export carries, PER
SURFACE, six dimensionless coefficients in the moment-reference frame --
`Cx, Cy, Cz, CMx, CMy, CMz` -- beside the free-stream velocity, the reference
area and the reference length. The reference block carries the moment point; the
rotor block carries its hub, its diameter and, since item 19, its shaft.

THE ONE STEP THAT IS NOT ARITHMETIC IS THE MOMENT TRANSFER, and it is stated
here because a reader will ask. The export's moments are about the MOMENT
REFERENCE POINT. A rotor's torque is about ITS OWN SHAFT, through its hub. The
two differ by the moment of the force about the offset between them:

    M_hub = M_mrp + (r_mrp - r_hub) x F

That is elementary statics rather than a convention, so it is implemented rather
than asked: there is one right answer and choosing the other would report a
torque no rotor produces. What remains the owner's is the DEFINITION of `ETAW`,
which the coefficient function already flags, and physical validation, which
needs a licensed run.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.post.products import ReferenceValues, rotor_shaft_loads


def _reference(**values) -> ReferenceValues:
    """A reference whose moment point is the origin unless a test moves it."""
    base = {"SREF": 10.0, "CREF": 1.0, "BREF": 4.0, "XMOM": 0.0, "YMOM": 0.0, "ZMOM": 0.0}
    base.update(values)
    return ReferenceValues.from_mapping(base)


def _rotor(axis, *, hub=(0.0, 0.0, 0.0)):
    from pyflightstream.cases import BladeDatum, RotorBlock

    return RotorBlock(
        alias="PUSHER",
        axis=axis,
        x_m=hub[0],
        y_m=hub[1],
        z_m=hub[2],
        diameter_m=2.0,
        families_blades=["Blade1", "Blade2"],
        blade1=BladeDatum(zero="X" if axis != "X" else "Y"),
    )


def _surfaces(**rows):
    """One loads table, keyed by surface, in the export's own column names."""
    empty = {"Cx": 0.0, "Cy": 0.0, "Cz": 0.0, "CMx": 0.0, "CMy": 0.0, "CMz": 0.0}
    return {name: {**empty, **values} for name, values in rows.items()}


def test_the_thrust_is_the_force_along_the_shaft_and_nothing_else():
    """A rotor on Z, pushing along Z. Hand-checkable and the whole of the rule.

    q = 0.5 * 1.225 * 40^2 = 980.0; Sref = 10; Cz = 0.5
    => T = 0.5 * 980 * 10 = 4900 N, and the X force does not reach it.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5, "Cx": 0.3}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0), loads


def test_a_force_square_to_the_shaft_produces_no_thrust():
    """Without this the rule is satisfied by summing the magnitude."""
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.9, "Cy": 0.9}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(0.0, abs=1e-9), loads


def test_only_the_rotors_own_families_are_summed():
    """A rotor's thrust is its OWN. The airframe is in the same table."""
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}, Wing={"Cz": 99.0}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0), loads


def test_the_torque_is_taken_about_the_hub_and_not_about_the_moment_point():
    """THE MOMENT TRANSFER, which is the one step that is not arithmetic.

    The rotor sits at x = 2 and the moment point is the origin. A force of
    +Cy at the blade makes a moment about the ORIGIN that a torque about the
    HUB does not have: M_z = x * F_y, which is exactly the term the transfer
    removes.

    q = 980, Sref = 10, Cy = 0.25 => F_y = 2450 N
    the offset is 2 m in x, so the spurious M_z about the origin is 4900 N m
    and the torque about the hub is 0.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cy": 0.25, "CMz": 0.5}),
        rotor=_rotor("Z", hub=(2.0, 0.0, 0.0)),
        reference=_reference(CREF=1.0),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    # CMz = 0.5 about the origin is 0.5 * 980 * 10 * 1.0 = 4900 N m, and the
    # transfer removes exactly 4900, so the shaft torque is zero.
    assert loads.torque_nm == pytest.approx(0.0, abs=1e-6), loads


def test_a_hub_on_the_moment_point_needs_no_transfer():
    """The other half: with no offset the two are the same number.

    Without this the transfer is satisfied by subtracting the whole moment.
    """
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cy": 0.25, "CMz": 0.5}),
        rotor=_rotor("Z", hub=(0.0, 0.0, 0.0)),
        reference=_reference(CREF=1.0),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.torque_nm == pytest.approx(4900.0), loads


def test_a_tilted_shaft_takes_the_component_along_itself():
    """Item 19 is what makes this answerable for an installed rotor.

    A shaft at 30 degrees from Z in the x-z plane, with a force along Z: the
    thrust is the projection, T = F_z * cos(30).
    """
    angle = math.radians(30.0)
    shaft = [math.sin(angle), 0.0, math.cos(angle)]
    loads = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}),
        rotor=_rotor(shaft),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert loads.thrust_n == pytest.approx(4900.0 * math.cos(angle)), loads


def test_the_shaft_angle_to_the_free_stream_is_reported_for_etaw():
    """`rotor_coefficients` takes `shaft_angle_deg` and nothing produced it.

    Without a producer a wired rotor table would report the ALIGNED-rotor
    `ETAW` by omission, which is the defect the coefficient function's own
    docstring warns about. The free stream is along +X by the package's own
    convention, so a shaft on Z is 90 degrees from it and a shaft on X is 0.
    """
    on_x = rotor_shaft_loads(
        _surfaces(Blade1={"Cx": 0.5}),
        rotor=_rotor("X"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert on_x.shaft_angle_deg == pytest.approx(0.0, abs=1e-9), on_x

    on_z = rotor_shaft_loads(
        _surfaces(Blade1={"Cz": 0.5}),
        rotor=_rotor("Z"),
        reference=_reference(),
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert on_z.shaft_angle_deg == pytest.approx(90.0), on_z
