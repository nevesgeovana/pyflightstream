"""The per-build rotor vocabulary, decided in one place (GOAL-023, RPT-049, RPT-051).

A rotor is written as a ``ROTARY`` motion with its axis and speed on the builds
that document those commands, as a ``EUCLIDEAN`` motion with an angular
velocity and the rotor mark on the builds that document that vocabulary
instead, and as a ``EUCLIDEAN`` motion with an angular velocity and NO rotor
mark on the build that documents the angular velocity and has no scripted
rotor mark (26.100). :func:`pyflightstream.script.helpers.rotary_motion`
writes by :func:`euclidean_rotor` and :func:`unmarked_euclidean_rotor`, and
``cases.workflows`` derives coverage from the same two, so the decision cannot
be made two ways.

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
    "UNMARKED_EUCLIDEAN_ROTOR_COMMANDS",
    "UNMARKED_EUCLIDEAN_ROTOR_UNIT",
    "euclidean_rotor",
    "unmarked_euclidean_rotor",
]

#: The commands a rotor is written with on a build whose motion type is
#: EUCLIDEAN: the angular velocity vector and the rotor mark (SRC-741 p.329,
#: SRC-747 p.306, SRC-748 p.307). No registered build documents both these
#: and SET_MOTION_ROTOR_RPM.
EUCLIDEAN_ROTOR_COMMANDS = ("SET_MOTION_ANGULAR_VELOCITY", "SET_MOTION_IS_ROTOR")

#: The commands a Euclidean rotor stands in for, on the builds where
#: :func:`euclidean_rotor` or :func:`unmarked_euclidean_rotor` holds.
ROTARY_ROTOR_COMMANDS = ("SET_MOTION_ROTOR_AXIS", "SET_MOTION_ROTOR_RPM")

#: The command a rotor is written with on a build that documents the angular
#: velocity and has no rotor mark: the angular velocity vector alone.
UNMARKED_EUCLIDEAN_ROTOR_COMMANDS = ("SET_MOTION_ANGULAR_VELOCITY",)


def euclidean_rotor(view: VersionView) -> bool:
    """Return whether a rotor is written as a marked Euclidean motion on ``view``'s build.

    THE ONE PLACE THE SUBSTITUTION IS DECIDED, with
    :func:`unmarked_euclidean_rotor`:
    :func:`pyflightstream.script.helpers.rotary_motion` writes by it and
    ``cases.workflows`` derives coverage from it. True when the build
    documents no rotary rotor speed and documents the whole Euclidean rotor
    (:data:`EUCLIDEAN_ROTOR_COMMANDS`).
    """
    return "SET_MOTION_ROTOR_RPM" not in view and all(
        name in view for name in EUCLIDEAN_ROTOR_COMMANDS
    )


def unmarked_euclidean_rotor(view: VersionView) -> bool:
    """Return whether a rotor is written as a Euclidean motion WITHOUT the rotor mark.

    True when the build documents no rotary rotor speed, documents the
    angular velocity, and does not carry ``SET_MOTION_IS_ROTOR``. 26.100 is
    that build: its solver does not recognize the rotor mark its manual
    prints (RPT-049). The motion is written with no mark, so the solver is
    never told the motion is a rotor (RPT-051). :func:`euclidean_rotor` and
    this function never both hold on one build.
    """
    return (
        "SET_MOTION_ROTOR_RPM" not in view
        and all(name in view for name in UNMARKED_EUCLIDEAN_ROTOR_COMMANDS)
        and "SET_MOTION_IS_ROTOR" not in view
    )


#: The unit SET_MOTION_ANGULAR_VELOCITY takes on a build where
#: :func:`euclidean_rotor` holds. Its scripting page states none; the rotor
#: tutorial of the same manual states rad/s for the dialog field the command
#: sets (SRC-741 p.394), and RPT-049 measured it on 26.000.
EUCLIDEAN_ROTOR_UNIT = "rad/s"

#: The unit SET_MOTION_ANGULAR_VELOCITY is written in on a build where
#: :func:`unmarked_euclidean_rotor` holds. A maintainer decision, NOT a
#: measurement: no run in this repository settles the unit on 26.100, and
#: that build's manual tutorial gives rad/s for the dialog field (RPT-051).
UNMARKED_EUCLIDEAN_ROTOR_UNIT = "rev/min"
