"""The per-build rotor vocabulary, decided in one place (GOAL-023, RPT-049).

A rotor is written as a ``ROTARY`` motion with its axis and speed on the builds
that document those commands, and as a ``EUCLIDEAN`` motion with an angular
velocity and the rotor mark on the builds that document that vocabulary
instead. :func:`pyflightstream.script.helpers.rotary_motion` writes by
:func:`euclidean_rotor` and ``cases.workflows`` derives coverage from it, so
the decision cannot be made two ways.

It decides WHICH vocabulary a rotor is written in, never WHETHER a build runs a
rotor: 25.000 documents the whole Euclidean rotor and no ``CREATE_NEW_MOTION``,
so the predicate holds there and the workflow still refuses the build.
"""

from __future__ import annotations

from pyflightstream.commands import VersionView

__all__ = [
    "EUCLIDEAN_ROTOR_COMMANDS",
    "EUCLIDEAN_ROTOR_UNIT",
    "ROTARY_ROTOR_COMMANDS",
    "euclidean_rotor",
]

#: The commands a rotor is written with on a build whose motion type is
#: EUCLIDEAN: the angular velocity vector and the rotor mark (SRC-741 p.329,
#: SRC-747 p.306, SRC-748 p.307). No registered build documents both these
#: and SET_MOTION_ROTOR_RPM.
EUCLIDEAN_ROTOR_COMMANDS = ("SET_MOTION_ANGULAR_VELOCITY", "SET_MOTION_IS_ROTOR")

#: The commands a Euclidean rotor stands in for, on the builds where
#: :func:`euclidean_rotor` holds.
ROTARY_ROTOR_COMMANDS = ("SET_MOTION_ROTOR_AXIS", "SET_MOTION_ROTOR_RPM")


def euclidean_rotor(view: VersionView) -> bool:
    """Return whether a rotor is written as a Euclidean motion on the build ``view`` answers for.

    THE ONE PLACE THE SUBSTITUTION IS DECIDED:
    :func:`pyflightstream.script.helpers.rotary_motion` writes by it and
    ``cases.workflows`` derives coverage from it. True when the build
    documents no rotary rotor speed and documents the whole Euclidean rotor
    (:data:`EUCLIDEAN_ROTOR_COMMANDS`).
    """
    return "SET_MOTION_ROTOR_RPM" not in view and all(
        name in view for name in EUCLIDEAN_ROTOR_COMMANDS
    )


#: The unit SET_MOTION_ANGULAR_VELOCITY takes. Its scripting page states
#: none; the rotor tutorial of the same manual states rad/s for the
#: dialog field the command sets (SRC-741 p.394).
EUCLIDEAN_ROTOR_UNIT = "rad/s"
