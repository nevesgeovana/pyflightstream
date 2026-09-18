"""Tier 1, v0.23.0 item 19: a rotor carries its INSTALLATION VECTOR.

THE OWNER'S WORDS, 2026-09-17:

    "Precisamos colocar no rotor o vetor de instalacao dele, imagina que ele ja
    vem com pitch e toe ja na malha. Vamos especificar via vetor ao inves de
    axis para generalizar."

WHAT WAS MEASURED BEFORE THE ITEM. `RotorBlock.axis` was validated to the
letters X, Y or Z and nothing else, and every coordinate frame the package
builds for a rotor was created with `x_axis=(1,0,0)` and `y_axis=(0,1,0)` --
seven call sites. Each one assumes the shaft lies on a geometry axis, which is
to assume the rotor is installed at zero pitch and zero toe. A mesh that
already carries its pitch and toe, which is how her hardware arrives, got
frames that do not match it.

THE LETTER KEEPS ITS EXACT MEANING, which is the property that protects every
reference she already has: `Z` IS the vector (0, 0, 1), so the old spelling is
a special case of the new one rather than something to migrate.

ITEM 6 DEPENDS ON THIS. `ETAW` is the efficiency in the WIND axis, the angle
between the thrust direction and the free stream, so while every rotor frame is
axis-aligned a rotor installed at pitch reports `ETAW` as though it were not --
a number that looks right and is wrong.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from pyflightstream.cases import RotorBlock


def _rotor(axis, zero: str = "X") -> RotorBlock:
    from pyflightstream.cases import BladeDatum

    return RotorBlock(
        alias="PUSHER",
        axis=axis,
        diameter_m=1.0,
        families_blades=["Blade1", "Blade2"],
        blade1=BladeDatum(zero=zero),
    )


@pytest.mark.parametrize(
    ("letter", "expected"),
    [("X", (1.0, 0.0, 0.0)), ("Y", (0.0, 1.0, 0.0)), ("Z", (0.0, 0.0, 1.0))],
)
def test_a_letter_is_exactly_the_vector_it_always_meant(letter, expected):
    """The property every reference she already has depends on.

    If a letter resolved to anything but its own unit vector, every existing
    reference would silently change what it asks the solver, which is the one
    thing this item may not do.
    """
    assert _rotor(letter, zero="Y" if letter != "Y" else "X").axis_vector == expected


def test_a_vector_is_accepted_and_normalised():
    """A shaft with pitch and toe, stated directly."""
    block = _rotor([0.0, 0.2, 0.98])
    vector = block.axis_vector
    assert math.isclose(sum(c * c for c in vector), 1.0, abs_tol=1e-9), vector
    # The DIRECTION is preserved; only the length is normalised.
    assert vector[1] > 0 and vector[2] > vector[1], vector
    assert math.isclose(vector[1] / vector[2], 0.2 / 0.98, rel_tol=1e-9), vector


def test_a_vector_of_no_length_is_refused():
    """A zero vector names no direction, and a rotor must turn about something."""
    with pytest.raises(ValidationError):
        _rotor([0.0, 0.0, 0.0])


def test_a_datum_parallel_to_the_shaft_is_refused_by_angle_and_not_by_spelling():
    """The check that a string comparison could never make.

    An azimuth measured from a datum parallel to the shaft locates nothing. The
    old check compared two STRINGS, so it caught `axis = Z, zero = Z` and was
    blind to a shaft at (0, 0.02, 0.9998) with a datum at Z -- which is one
    degree from parallel and reports a number rather than refusing.
    """
    with pytest.raises(ValidationError):
        _rotor([0.0, 0.02, 0.9998], zero="Z")


def test_a_datum_square_to_a_tilted_shaft_is_accepted():
    """The other half, so the refusal is not satisfied by refusing everything.

    A check that only ever refuses is the shape this estate has recorded: the
    shipping guard whose only test asked whether it could refuse had never once
    accepted anything.
    """
    block = _rotor([0.0, 0.2, 0.98], zero="X")
    assert block.axis_vector[0] == 0.0


@pytest.mark.parametrize("off_square_deg", [10.0, 30.0, 60.0, 80.0])
def test_a_datum_well_away_from_the_shaft_is_accepted_however_far_from_square(
    off_square_deg,
):
    """THE CASE THE TWO TESTS ABOVE BOTH MISS, and it hid a reversed comparison.

    The two datum tests beside this one use a datum EXACTLY square and a datum
    one degree from PARALLEL. Both verdicts are the same under the documented
    rule and under its complement, so neither could tell the two apart -- and
    the code implemented the complement: `alignment > _DATUM_ALIGNMENT_LIMIT`
    on `|cos(angle)|` refuses everything MORE than five degrees from SQUARE,
    which is the opposite of "a datum within five degrees of the SHAFT is
    refused".

    Measured before the fix, sweeping the angle off square: accepted at 0, 2
    and 4 degrees, REFUSED at 6, 15, 30, 60, 85 and 88. A datum 30 degrees off
    square is a perfectly ordinary installation and every document promises it
    is accepted; the refusal it got even told it that it "nearly lies along the
    shaft" while printing 60 degrees from that shaft in the same sentence.

    Parametrised across the whole band rather than at one angle, because a
    single case is satisfied by moving the bound rather than by fixing the
    side of it that is compared.
    """
    radians = math.radians(off_square_deg)
    shaft = [math.sin(radians), 0.0, math.cos(radians)]
    block = _rotor(shaft, zero="X")
    assert block.axis_vector[1] == 0.0


def test_the_datum_refusal_fires_on_nearness_to_the_shaft_and_nowhere_else():
    """The boundary itself, asserted from both sides of the documented five.

    Without this, the fix above is satisfied by removing the check entirely.
    """
    # Four degrees from the shaft: refused, because an azimuth measured from it
    # locates nothing.
    near = math.radians(4.0)
    with pytest.raises(ValidationError):
        _rotor([math.cos(near), 0.0, math.sin(near)], zero="X")

    # Six degrees from the shaft: accepted. The bound is a judgement, and what
    # is asserted here is that it is applied to the angle from the SHAFT.
    far = math.radians(6.0)
    _rotor([math.cos(far), 0.0, math.sin(far)], zero="X")


def test_the_shaft_basis_is_the_identity_only_when_the_datum_is_x():
    """THE CLAIM THIS TEST FIRST MADE WAS FALSE, and the suite proved it.

    It was written as "an untilted rotor produces exactly the basis the package
    hard-coded", to argue that routing every rotor through the shaft basis is
    byte-identical for the references she already has. That holds only when the
    blade datum is X. A rotor with `axis = Z` and `zero = Y` yields
    x=(0,1,0) and y=(-1,0,0) -- the same disk turned a quarter -- and 27 tier-1
    cases failed on it.

    So the basis is NOT what protects her references; a branch is. A rotor
    whose axis is a LETTER keeps the literal identity orientation, and only a
    rotor stating a VECTOR derives its frame. This test now records both halves
    rather than the half that flattered the design.
    """
    from pyflightstream.cases import frame_basis_for_shaft

    square = frame_basis_for_shaft((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    assert square == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), square

    turned = frame_basis_for_shaft((0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    assert turned != ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), (
        "if this ever equals the identity the branch below is unnecessary, and "
        "if it does not, the branch is what keeps her references identical"
    )


def test_a_rotor_stating_a_letter_keeps_the_identity_orientation():
    """The branch that actually protects every reference written before 0.23.0."""
    from pyflightstream.cases import BladeDatum
    from pyflightstream.cases.workflows import _hub_basis

    for zero in ("X", "Y"):
        block = RotorBlock(
            alias="PUSHER",
            axis="Z",
            diameter_m=1.0,
            families_blades=["Blade1", "Blade2"],
            blade1=BladeDatum(zero=zero),
        )
        assert _hub_basis(block) == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), zero


def test_a_rotor_stating_a_vector_gets_a_frame_built_on_its_shaft():
    """The other half: the branch must not refuse everything into the old path."""
    from pyflightstream.cases.workflows import _hub_basis

    block = _rotor([0.0, 0.2, 0.98], zero="X")
    x_axis, y_axis = _hub_basis(block)
    assert (x_axis, y_axis) != ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), (x_axis, y_axis)
    along = sum(a * b for a, b in zip(block.axis_vector, x_axis, strict=True))
    assert math.isclose(along, 0.0, abs_tol=1e-12), (x_axis, along)


def test_the_third_axis_of_the_basis_is_the_shaft():
    """The frame builder completes the basis with the cross product, so this is what it gets."""
    from pyflightstream.cases import frame_basis_for_shaft

    shaft = (0.0, 0.19611613513818404, 0.9805806756909202)
    x_axis, y_axis = frame_basis_for_shaft(shaft, (1.0, 0.0, 0.0))
    third = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )
    for got, want in zip(third, shaft, strict=True):
        assert math.isclose(got, want, abs_tol=1e-12), (third, shaft)


def test_the_datum_is_projected_into_the_disk_plane_of_a_tilted_rotor():
    """What makes an azimuth well defined once the shaft is not a geometry axis.

    The datum a user names is a direction in the GEOMETRY; the angle has to be
    measured in the plane the blades actually sweep. On an untilted rotor the
    projection changes nothing, which is the case above.
    """
    from pyflightstream.cases import frame_basis_for_shaft

    shaft = (0.0, 0.19611613513818404, 0.9805806756909202)
    x_axis, _ = frame_basis_for_shaft(shaft, (0.0, 1.0, 0.0))
    along = sum(a * b for a, b in zip(shaft, x_axis, strict=True))
    assert math.isclose(along, 0.0, abs_tol=1e-12), (x_axis, along)
    assert math.isclose(sum(c * c for c in x_axis), 1.0, abs_tol=1e-12), x_axis
