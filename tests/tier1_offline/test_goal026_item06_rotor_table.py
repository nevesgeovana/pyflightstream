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
    ETAW = J CTW / CP,   CTW = Fx_W / (rho n^2 D^4)

`Fx_W` IS THE ROTOR'S FORCE ALONG THE FREE STREAM, and this line read
``ETAW = ETA cos(theta)`` until the owner corrected it on 2026-09-18. Her form:
the whole rotor-frame force vector carried to body axes by the TRANSPOSE of the
rotor-to-body rotation, then to wind axes by the AIAA rotation with alpha AND
beta, taking the X component.

A COSINE IS A SCALAR WHERE THE PHYSICS IS A VECTOR. It projects the SHAFT and
keeps only the force lying along it, discarding every component an installed
rotor produces off the shaft -- which is exactly the part her chain keeps. The
two agree only when the shaft is already aligned with the stream, which is the
case that needed no correction in the first place.

This item still depends on item 19: until the installation vector existed the
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


def test_the_wind_axis_efficiency_is_built_on_the_wind_axis_force():
    """THE EXPECTATION HERE CHANGED BECAUSE THE OWNER CHANGED THE REQUIREMENT.

    This asserted `tilted["ETAW"] == tilted["ETA"] * cos(30)` -- the formula
    written into the package until 2026-09-18, when she said it was wrong and
    gave the right one: the whole force vector through the rotor-to-body
    transpose and the AIAA alpha-and-beta rotation, taking `Fx_W`.

    It is rewritten rather than deleted, and it is not weakened: it still pins
    an exact value, and it pins MORE than it did, because a caller that states
    no wind-axis force now gets `NA` rather than a number computed the old way.
    That fallback is the point -- publishing the old formula under the corrected
    name would leave a reader unable to tell which of the two they were holding.
    """
    aligned = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=30.0,
        shaft_angle_deg=0.0,
        wind_force_n=500.0,
    )
    # A rotor putting less of its force along the stream: same thrust about the
    # shaft, a smaller component in the direction of flight.
    off_stream = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=30.0,
        shaft_angle_deg=30.0,
        wind_force_n=400.0,
    )
    assert math.isclose(aligned["ETAW"], aligned["ETA"], rel_tol=1e-12), (
        "all of the force is along the stream, so the two efficiencies coincide"
    )
    assert math.isclose(off_stream["ETAW"], off_stream["ETA"] * 400.0 / 500.0, rel_tol=1e-12), (
        "ETAW scales with the WIND-AXIS FORCE, not with the cosine of the shaft angle"
    )
    assert off_stream["ETAW"] < off_stream["ETA"], (off_stream["ETAW"], off_stream["ETA"])
    # AND THE COSINE IS NOT WHAT IT USED TO BE: cos(30) is 0.866, the ratio here
    # is 0.8, so this case would fail under the formula it replaced.
    assert not math.isclose(
        off_stream["ETAW"], off_stream["ETA"] * math.cos(math.radians(30.0)), rel_tol=1e-12
    ), "ETAW is still the cosine of the shaft angle"


def test_a_caller_that_states_no_wind_force_gets_na_and_never_the_old_formula():
    """The fallback, asserted rather than assumed.

    `wind_force_n` is optional on the signature so that every existing caller
    keeps type-checking. What such a caller must NOT get is the cosine: that
    number is the one she corrected, and publishing it under the corrected name
    is worse than publishing nothing, because the column would be right for some
    rows and wrong for others with no way to tell them apart.
    """
    silent = rotor_coefficients(
        thrust_n=500.0,
        torque_nm=40.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=30.0,
        shaft_angle_deg=30.0,
    )
    assert silent["ETAW"] == NOT_APPLICABLE, silent
    assert isinstance(silent["ETA"], float), "only ETAW depends on the wind force"


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


def test_etaw_is_the_wind_axis_force_and_not_the_cosine_of_the_shaft_angle():
    """THE CASE THAT TELLS THE TWO FORMULAE APART, and nothing did until now.

    Her correction, 2026-09-18: `ETAW = ETA * cos(theta)` is WRONG. The right
    form carries the whole force vector to wind axes and takes `Fx_W`.

    WHY NO TEST CAUGHT THE CHANGE. Every case in this suite used a rotor whose
    force lies ALONG ITS SHAFT, and for such a rotor the two formulae agree
    exactly -- the cosine is the projection when there is nothing off-axis to
    discard. So the suite stayed green through a change of definition, which is
    the "measure the carrier, not the mention" failure in its purest form: the
    column name was asserted, the value never was.

    THE ROTOR HERE PRODUCES FORCE OFF ITS SHAFT, which is the ordinary case for
    an installed rotor and the only one that discriminates. The shaft is on X
    and the surface also pushes on Z, so:

        cos(theta) keeps    Fx only              (the shaft projection)
        Fx_W keeps          Fx*cos(a) + Fz*sin(a)   (the stream projection)

    At alpha = 20 degrees with equal Fx and Fz those are different numbers, and
    a mutant restoring the cosine fails on this and on nothing else in the file.
    """
    import math

    from pyflightstream.post.products import ReferenceValues, rotor_coefficients, rotor_shaft_loads

    class _Rotor:
        alias = "PUSHER"
        axis_vector = (1.0, 0.0, 0.0)
        x_m = y_m = z_m = 0.0
        members = ["Blade1"]

    reference = ReferenceValues(
        sref_m2=1.0, cref_m=1.0, bref_m=1.0, xmom_m=0.0, ymom_m=0.0, zmom_m=0.0
    )
    alpha = 20.0
    # Equal push along the shaft and square to it, so the two readings diverge.
    surfaces = {"Blade1": {"Cx": 1.0, "Cy": 0.0, "Cz": 1.0}}
    loads = rotor_shaft_loads(
        surfaces,
        rotor=_Rotor(),
        reference=reference,
        density_kg_m3=1.225,
        speed_m_s=50.0,
        alpha_deg=alpha,
        beta_deg=0.0,
    )

    # THE SHAFT reading keeps Fx alone; THE STREAM reading keeps both terms.
    pressure = 0.5 * 1.225 * 50.0**2
    assert loads.thrust_n == pytest.approx(pressure), "the shaft is on X, so thrust is Fx"
    # DERIVED FROM THE CONVENTION, NOT READ OFF THE IMPLEMENTATION, and the
    # difference is the whole point of this line. It asserted `cos + sin` --
    # a number taken from the code -- and the code had the sign wrong, so the
    # case written to discriminate passed under both answers. Every other
    # assertion here holds under either sign too.
    #
    # THE DERIVATION ABOVE THIS LINE WAS WRONG, AND 0.24.0 CHANGES THE EXPECTED
    # VALUE FOR THAT REASON AND NO OTHER. It argued that with `Cz` positive up
    # the free stream at positive alpha points DOWN, `v = (cos a, 0, -sin a)`,
    # and asserted `cos a - sin a`. It points UP: the air reaches a nose-up
    # aircraft from below, so it moves aft AND up, `v = (cos a, 0, +sin a)`.
    #
    # THAT IS MEASURED, NOT ARGUED. Every recorded licensed export states its
    # own drag, and `CDi + CDo == Cx cos a + Cz sin a` to the printed precision
    # on all of them, while the minus sign misses by up to 0.05 and makes the
    # drag NEGATIVE (`test_goal028_axes_recorded_exports.py`). A derivation
    # nobody scored against the solver is how the sign shipped in 0.23.0.
    #
    # The surface pushes `(1, 0, 1) * q`, so `Fx_W = q * (cos a + sin a)`, which
    # at alpha 20 is 1.282 q. The shaft reading is 1.000 q, so the case still
    # discriminates the wind-axis force from the cosine, in the other direction.
    assert loads.wind_force_n == pytest.approx(
        pressure * (math.cos(math.radians(alpha)) + math.sin(math.radians(alpha)))
    ), "Fx_W is the force dotted with the free stream, whose Z term is POSITIVE at alpha"
    assert loads.wind_force_n != pytest.approx(loads.thrust_n), (
        "this case must discriminate; with these two equal the test proves nothing"
    )

    values = rotor_coefficients(
        thrust_n=loads.thrust_n,
        torque_nm=100.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=50.0,
        shaft_angle_deg=loads.shaft_angle_deg,
        wind_force_n=loads.wind_force_n,
    )
    # ETAW/ETA is the ratio of the two forces, which is the whole correction.
    assert values["ETAW"] / values["ETA"] == pytest.approx(loads.wind_force_n / loads.thrust_n), (
        values
    )
    # AND IT IS NOT THE COSINE. The old form would give this instead.
    cosine = values["ETA"] * math.cos(math.radians(loads.shaft_angle_deg))
    assert values["ETAW"] != pytest.approx(cosine), (
        f"ETAW is still the cosine of the shaft angle: {values['ETAW']} vs {cosine}"
    )


def test_etaw_reduces_to_eta_when_the_shaft_is_along_the_stream():
    """THE CONTROL, and it is what makes the case above mean something.

    A test that only asserts two numbers DIFFER is satisfied by any change at
    all, including a wrong one. `ETAW` must still equal `ETA` exactly when the
    shaft and the free stream are the same direction -- an aligned rotor at zero
    alpha -- because then all of the force is along the stream and there is
    nothing for the projection to remove. That property is what makes the column
    readable beside `ETA` at all.
    """
    from pyflightstream.post.products import ReferenceValues, rotor_coefficients, rotor_shaft_loads

    class _Rotor:
        alias = "PUSHER"
        axis_vector = (1.0, 0.0, 0.0)
        x_m = y_m = z_m = 0.0
        members = ["Blade1"]

    loads = rotor_shaft_loads(
        {"Blade1": {"Cx": 1.0, "Cy": 0.0, "Cz": 0.0}},
        rotor=_Rotor(),
        reference=ReferenceValues(
            sref_m2=1.0, cref_m=1.0, bref_m=1.0, xmom_m=0.0, ymom_m=0.0, zmom_m=0.0
        ),
        density_kg_m3=1.225,
        speed_m_s=50.0,
        alpha_deg=0.0,
        beta_deg=0.0,
    )
    values = rotor_coefficients(
        thrust_n=loads.thrust_n,
        torque_nm=100.0,
        rps=20.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=50.0,
        shaft_angle_deg=loads.shaft_angle_deg,
        wind_force_n=loads.wind_force_n,
    )
    assert values["ETAW"] == pytest.approx(values["ETA"]), values


def test_etaw_is_na_when_the_export_is_not_in_the_geometry_frame():
    """THE PREMISE OF THE ROTATION, CHECKED AGAINST A WITNESS THE EXPORT CARRIES.

    `ETAW` carries the rotor's force into wind axes by alpha and beta. That
    rotation is only valid from the GEOMETRY frame, and the implementation
    collapses the owner's rotor-frame round trip on exactly that ground: the
    export already states the force in body axes, so resolving into the rotor
    frame and back is the identity.

    A CAMPAIGN CAN MAKE THAT FALSE. `script.helpers.analysis_setup(loads_frame=)`
    points the analysis at a created coordinate system, and the export then
    prints that frame's label under "Coordinate frame for analysis:". Rotating a
    force stated in some other frame by alpha and beta produces a plausible
    efficiency of nothing -- no error, no `NA`, just a wrong number.

    THE FIELD WAS PARSED, CARRIED ON `LoadsReport`, AND READ BY NOBODY, while a
    comment asserted the geometry frame as a property of the EXPORT. It is a
    property of the campaign's setup. The V&V lens of the release round found
    it; every fixture in this suite prints `Reference`, so no case here could
    have failed on it.
    """
    from pyflightstream.post.products import (
        NOT_APPLICABLE,
        ReferenceValues,
        rotor_coefficients,
        rotor_shaft_loads,
    )

    class _Rotor:
        alias = "PUSHER"
        axis_vector = (1.0, 0.0, 0.0)
        x_m = y_m = z_m = 0.0
        members = ["Blade1"]

    reference = ReferenceValues(
        sref_m2=1.0, cref_m=1.0, bref_m=1.0, xmom_m=0.0, ymom_m=0.0, zmom_m=0.0
    )

    def _loads(frame):
        return rotor_shaft_loads(
            {"Blade1": {"Cx": 1.0, "Cy": 0.0, "Cz": 1.0}},
            rotor=_Rotor(),
            reference=reference,
            density_kg_m3=1.225,
            speed_m_s=50.0,
            alpha_deg=20.0,
            beta_deg=0.0,
            analysis_frame=frame,
        )

    def _etaw(loads):
        return rotor_coefficients(
            thrust_n=loads.thrust_n,
            torque_nm=100.0,
            rps=20.0,
            diameter_m=2.0,
            density_kg_m3=1.225,
            speed_m_s=50.0,
            shaft_angle_deg=loads.shaft_angle_deg,
            wind_force_n=loads.wind_force_n,
        )["ETAW"]

    # THE FRAME EVERY RECORDED EXPORT PRINTS, and an export that states none.
    assert isinstance(_etaw(_loads("Reference")), float)
    assert isinstance(_etaw(_loads(None)), float)

    # `MRP` IS ADMITTED AND WAS NOT. This package points the analysis at MRP
    # itself whenever the reference states a moment point, and builds it as a
    # pure TRANSLATION -- origin moved, axes identity -- so every force
    # direction is unchanged and the rotation is valid. Denying it would have
    # written NA on exactly the campaign item 6 exists for, and the unsteady
    # loads fixture prints `MRP` on line 21.
    assert isinstance(_etaw(_loads("MRP")), float)

    # A ROTOR'S OWN FRAME IS GENUINELY TURNED, so the premise fails.
    assert _etaw(_loads("PUSHER_SMRP")) == NOT_APPLICABLE
    # AND THE WHOLE ROW GOES WITH IT. This asserted the opposite for one commit
    # -- that the thrust was unaffected "because it is a projection on the
    # shaft, which needs no wind axes". That sentence is wrong: `shaft` is a
    # vector in GEOMETRY axes, so the dot product rests on the same premise the
    # wind rotation rests on. Guarding one column meant CT, CQ, CP and ETA
    # published silently wrong numbers while only ETAW went visibly absent.
    # One premise, one verdict.
    refused = _loads("PUSHER_SMRP")
    assert refused.thrust_n != refused.thrust_n, "thrust must be NaN, not a number"
    assert refused.torque_nm != refused.torque_nm, "torque must be NaN, not a number"
