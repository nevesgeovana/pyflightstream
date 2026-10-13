"""The 6DOF motion a row's ``SIXDOF`` key frees (FR-461, 0.40.0).

:func:`_sixdof_motion` emits one 6DOF motion of the input's families about its
body frame, in the setup phase, after the frames and before the solver is
initialised. The trajectory export is NOT emitted with it: exported before the
march the file holds its header and no row (RPT-166 probe P4-04), so the export
block writes it after the march, with the other exports (FR-461 R6).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.cases.sixdof import (
    SixDofCustomForce,
    SixDofExternalForce,
    SixDofSpec,
    SixDofSpringForce,
)
from pyflightstream.script import Script

from ._gap_evidence import refuse_unprobed_commands
from ._rows import _from_metres
from ._vocabulary import Frames

__all__ = [
    "SIXDOF_PROVENANCE_FILE",
    "sixdof_commands",
]

#: The record of the input a point staged (FR-461 R5).
SIXDOF_PROVENANCE_FILE = "sixdof-provenance.json"

_FORCE_COMMANDS = {
    "external": "CREATE_NEW_6DOF_EXTERNAL_FORCE",
    "spring": "CREATE_NEW_6DOF_SPRING_FORCE",
    "custom": "CREATE_NEW_6DOF_CUSTOM_FORCE",
}


def sixdof_commands(spec: SixDofSpec) -> list[str]:
    """Return the commands a 6DOF input emits, in order of first use.

    Parameters
    ----------
    spec : SixDofSpec
        The input.

    Returns
    -------
    list of str
        The command names.
    """
    commands = [
        "CREATE_NEW_MOTION",
        "SET_MOTION_BOUNDARIES",
        "SET_MOTION_COORDINATE_SYSTEM",
        "SET_MOTION_MASS_PROPERTIES",
        "SET_MOTION_GRAVITY",
        "SET_MOTION_6DOF_INITIAL_VELOCITY",
        "SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY",
        "SET_MOTION_6DOF_ACTIVE_VARIABLES",
    ]
    for force in spec.forces:
        command = _FORCE_COMMANDS[force.kind]
        if command not in commands:
            commands.append(command)
    commands.append("SET_6DOF_MOTION_SYMMETRY_LOADS")
    if spec.export.trajectory:
        commands.append("EXPORT_6DOF_TRAJECTORY")  # emitted after the march (R6)
    return commands


def _refuse_what_the_motion_cannot_place(case: SimCase, script: Script) -> None:
    """Refuse a simulation in another length unit than the metre (FR-461 R4).

    The lengths are written as stated, in metres, where the simulation is in
    metres or states no unit (the rule :func:`_from_metres` keeps for every
    length a row states).
    """
    if _from_metres(case, script, "the SIXDOF points and lengths") != 1.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: SIXDOF states its points and lengths in metres and the "
            f"simulation's length unit is {script.simulation_length_unit}; the unit the solver "
            "reads a 6DOF point and spring in is a probe question, so only a simulation in "
            "metres is accepted until a probe settles it."
        )


def _sixdof_motion(
    case: SimCase, script: Script, frames: Frames, *, trajectory_file: str | None
) -> None:
    """Emit the row's 6DOF motion in the setup phase (FR-461 R2).

    Parameters
    ----------
    case : SimCase
        The case; ``case.sixdof`` states the body.
    script : Script
        The script, after the frames, before the solver is initialised.
    frames : mapping
        The frames the run created, by name.
    trajectory_file : str or None
        The name the trajectory is exported to, from the row's outputs.

    Raises
    ------
    CampaignConfigError
        A gated command not verified on the build, a frame the run does not create,
        a family the geometry does not carry, a simulation not in metres, or a
        trajectory asked with no declared output.
    """
    spec = case.sixdof
    if spec is None:
        return
    refuse_unprobed_commands(case, script, sixdof_commands(spec), capability="SIXDOF")
    _refuse_what_the_motion_cannot_place(case, script)
    frame = frames.get(spec.frame)
    if not isinstance(frame, int) or frame <= 1:
        created = sorted(name for name, value in frames.items() if isinstance(value, int))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the SIXDOF input's frame {spec.frame!r} is not a frame this "
            f"run creates (created: {', '.join(created) or 'none'}); the body frame at the "
            "pivot is declared in the reference's or the setup's [[frames]]."
        )
    boundaries = [
        script.resolve_boundary(family, context="the SIXDOF families") for family in spec.families
    ]
    if spec.export.trajectory and trajectory_file is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the SIXDOF input exports the trajectory and the row's "
            "outputs declare no <point>_trajectory_6dof.txt; build the row through the workspace."
        )
    script.emit("CREATE_NEW_MOTION", "6DOF", label="SIXDOF")
    motion = script.num_motions
    script.emit("SET_MOTION_BOUNDARIES", motion, len(boundaries), boundaries)
    script.emit("SET_MOTION_COORDINATE_SYSTEM", motion, frame)
    script.emit("SET_MOTION_MASS_PROPERTIES", motion, spec.mass.mass_kg, *spec.mass.inertia_kg_m2)
    script.emit("SET_MOTION_GRAVITY", motion, *spec.gravity.vector_reference_m_per_s2)
    script.emit("SET_MOTION_6DOF_INITIAL_VELOCITY", motion, *spec.initial.velocity_body_m_per_s)
    # Written in rad/s, the unit RPT-049 measured for the motion family's
    # angular velocity (SET_MOTION_ANGULAR_VELOCITY); this command's own unit
    # is unstated and is the probe question P4-2.
    script.emit(
        "SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY",
        motion,
        *(math.radians(value) for value in spec.initial.angular_velocity_body_deg_per_s),
    )
    script.emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", motion, spec.active_lines())
    for force in spec.forces:
        _emit_force(case, script, motion, force)
    script.emit(
        "SET_6DOF_MOTION_SYMMETRY_LOADS", motion, "ENABLE" if spec.symmetry_loads else "DISABLE"
    )
    script.sixdof_motion = motion
    if case.sixdof_provenance:
        _stage(
            case,
            script,
            SIXDOF_PROVENANCE_FILE,
            json.dumps(case.sixdof_provenance, indent=2) + "\n",
        )


def _emit_force(
    case: SimCase,
    script: Script,
    motion: int,
    force: SixDofExternalForce | SixDofSpringForce | SixDofCustomForce,
) -> None:
    """Emit one ``[[forces]]`` entry; a custom force's file is staged beside the script."""
    if isinstance(force, SixDofExternalForce):
        script.emit(
            "CREATE_NEW_6DOF_EXTERNAL_FORCE",
            motion,
            *force.point_body_m,
            force.start_s,
            force.duration_s,
            *force.force_body_n,
        )
    elif isinstance(force, SixDofSpringForce):
        script.emit(
            "CREATE_NEW_6DOF_SPRING_FORCE",
            motion,
            *force.point_body_m,
            *force.axis_body,
            force.free_length_m,
            force.solid_length_m,
            force.initial_length_m,
            force.rate_n_per_m,
        )
    else:
        source = Path(force.resolved_file or "")
        if not source.is_file():
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the SIXDOF custom force file {force.file!r} was not "
                "resolved to a file of inputs/sixdof/; build the row through the workspace."
            )
        _stage(case, script, source.name, source.read_bytes())
        script.emit("CREATE_NEW_6DOF_CUSTOM_FORCE", motion, force.type, source.name)


def _stage(case: SimCase, script: Script, name: str, content: str | bytes) -> None:
    """Stage one point input beside the script, refusing a collision of names."""
    script.park_input_file(name, content)
