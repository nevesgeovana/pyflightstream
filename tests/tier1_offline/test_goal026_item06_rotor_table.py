"""Tier 1, v0.23.0 item 6: the standard rotor table, per rotor, `_<alias>`.

THE OWNER'S WORDS, 2026-09-17. One token is replaced by its sanctioned name
in brackets, on this estate's redaction rule for the legacy polar format:

    "Tem que ter um [rotor table] padrão toda vez que existir rotor. Tem que ter J, CT,
    CQ, CP, ETA, ETAW (eficiência no eixo do vento) para cada rotor. Se o grupo
    de malhas tiver rotor, ele tem que passar esses coeficientes somente
    integrando os rotores e colocar _<alias> para identificar. Esses coefs
    fazem sentido físico apenas para um rotor, não vários juntos."

and, on the static case:

    "Nao precisa preocupar com figura de mérito, o usuário define uma se ele
    for rodar estático."

THE DEFINITIONS, written here because a coefficient whose formula lives only in
code is a number nobody can check. ``n`` is revolutions per SECOND and ``D``
the diameter:

    J    = V / (n D)
    CT   = T / (rho n^2 D^4)
    CQ   = Q / (rho n^2 D^5)
    CP   = 2 pi CQ
    ETA  = J CT / CP
    ETAW = ETA cos(theta)

``theta`` is the angle between the rotor's SHAFT and the free stream, which is
why this item depends on item 19: until the installation vector existed the
shaft was assumed to lie on a geometry axis, so a rotor installed at pitch
reported the wind-axis efficiency as though it were not installed at pitch.

ETA AND ETAW ARE NOT WRITTEN ON A STATIC POINT. At V = 0 both are 0/0: the
rotor is doing work and producing thrust and no useful propulsive power, so any
number there is an artifact of the algebra. The cell reads `NA`. A figure of
merit is the static measure and it is the owner's to define, by her decision of
the same day.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.post.products import (
    NOT_APPLICABLE,
    ROTOR_COEFFICIENT_COLUMNS,
    rotor_coefficients,
)


def test_the_six_coefficients_she_named_in_the_order_she_named_them():
    assert ROTOR_COEFFICIENT_COLUMNS[:6] == ("J", "CT", "CQ", "CP", "ETA", "ETAW")


def test_the_coefficients_are_the_standard_definitions():
    """Checked against the formulas, computed by hand in the assertion.

    A test that recomputed them with the same code it is testing would agree
    with any implementation, including a wrong one.
    """
    rho, n, diameter, thrust, torque, speed = 1.225, 20.0, 2.0, 500.0, 40.0, 30.0
    got = rotor_coefficients(
        thrust_n=thrust,
        torque_nm=torque,
        rps=n,
        diameter_m=diameter,
        density_kg_m3=rho,
        speed_m_s=speed,
    )
    assert math.isclose(got["J"], speed / (n * diameter), rel_tol=1e-12)
    assert math.isclose(got["CT"], thrust / (rho * n**2 * diameter**4), rel_tol=1e-12)
    assert math.isclose(got["CQ"], torque / (rho * n**2 * diameter**5), rel_tol=1e-12)
    assert math.isclose(got["CP"], 2 * math.pi * got["CQ"], rel_tol=1e-12)
    assert math.isclose(got["ETA"], got["J"] * got["CT"] / got["CP"], rel_tol=1e-12)


def test_a_static_point_writes_not_applicable_for_both_efficiencies_and_keeps_the_rest():
    """At V = 0 the efficiency is 0/0, and a number there is an artifact.

    The thrust and torque coefficients are still real and still written: a
    static rotor produces thrust and absorbs torque. Only the two ratios that
    divide by the flight speed go away.
    """
    got = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=0.0,
    )
    assert got["ETA"] == NOT_APPLICABLE
    assert got["ETAW"] == NOT_APPLICABLE
    assert got["J"] == 0.0
    assert isinstance(got["CT"], float) and got["CT"] > 0
    assert isinstance(got["CQ"], float) and got["CQ"] > 0


def test_the_wind_axis_efficiency_falls_with_the_shaft_angle():
    """ETAW is ETA projected on the free stream, which is why item 19 comes first.

    A rotor installed at pitch does not put all of its thrust into the
    direction of flight, and until the installation vector existed the package
    could not know that: it assumed the shaft lay on a geometry axis and
    reported the wind-axis efficiency of an aligned rotor.
    """
    square = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=30.0,
        shaft_angle_deg=0.0,
    )
    tilted = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=30.0,
        shaft_angle_deg=30.0,
    )
    assert math.isclose(square["ETAW"], square["ETA"], rel_tol=1e-12)
    assert math.isclose(tilted["ETAW"], tilted["ETA"] * math.cos(math.radians(30.0)), rel_tol=1e-12)
    assert tilted["ETAW"] < tilted["ETA"], (tilted["ETAW"], tilted["ETA"])


def test_a_rotor_that_is_not_turning_is_refused_rather_than_dividing_by_zero():
    """Every coefficient divides by the speed squared; zero is not a rotor."""
    with pytest.raises(ZeroDivisionError):
        rotor_coefficients(
            thrust_n=500.0,
            torque_nm=40.0,
            rps=0.0,
            diameter_m=2.0,
            density_kg_m3=1.225,
            speed_m_s=30.0,
        )


def test_the_columns_carry_the_alias_so_two_rotors_are_never_summed():
    """Her constraint: these make physical sense for ONE rotor and not several."""
    from pyflightstream.post.products import rotor_coefficient_columns

    columns = rotor_coefficient_columns("PUSHER")
    assert columns[0] == "J_PUSHER", columns
    assert all(name.endswith("_PUSHER") for name in columns), columns
    assert len(set(columns)) == len(columns), columns
