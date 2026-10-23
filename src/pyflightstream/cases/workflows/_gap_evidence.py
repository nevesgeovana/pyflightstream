"""The evidence gate for command capabilities (FR-460 R-GATE, FR-461 R-GATE).

Every command a workflow emits needs evidence in the command database. The
streamline and 6DOF commands the command gap reaches were recorded
``documented`` on 26.124 and 26.125, read from the manual and run by no probe,
when their routes were written. A row reaching one of them is refused at plan
on a build where it is not ``verified``, naming the command and the licensed
probe that settles it; the probe's evidence enters the database through the
add-command route, and the same row then plans with no change to this module.

The commands the existing workflows already emit (``CREATE_NEW_MOTION``,
``SET_MOTION_BOUNDARIES``, the aeroelastic toolbox) are not gated here: they
are reached today on the same evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.commands import Status
from pyflightstream.script import Script

__all__ = [
    "PROBE_GATED_COMMANDS",
    "command_verified",
    "evidence_state",
    "refuse_unprobed_commands",
]

_STREAMLINE_PROBE = "the streamline probes of the command-gap batch (P3)"
_SIXDOF_PROBE = "the 6DOF probes of the command-gap batch (P4)"

#: The gated commands, each with the licensed probe that settles it.
PROBE_GATED_COMMANDS: Mapping[str, str] = MappingProxyType(
    {
        "MARK_WAKE_TERMINATION_NODES": "PFS-2149.01, the wake-termination probe",
        "NEW_OFF_BODY_STREAMTUBE": _STREAMLINE_PROBE,
        "SET_OFF_BODY_STREAMLINE_LENGTH": _STREAMLINE_PROBE,
        "SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM": _STREAMLINE_PROBE,
        "SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM": _STREAMLINE_PROBE,
        "DELETE_ALL_OFF_BODY_STREAMLINES": _STREAMLINE_PROBE,
        "GENERATE_ALL_SURFACE_STREAMLINES": _STREAMLINE_PROBE,
        "DELETE_ALL_SURFACE_STREAMLINES": _STREAMLINE_PROBE,
        "EXPORT_ALL_SURFACE_STREAMLINES": _STREAMLINE_PROBE,
        "NEW_STREAMLINE_DISTRIBUTION": _STREAMLINE_PROBE,
        "GENERATE_ALL_OFF_BODY_STREAMLINES": _STREAMLINE_PROBE,
        "EXPORT_ALL_OFF_BODY_STREAMLINES": _STREAMLINE_PROBE,
        "SET_MOTION_MASS_PROPERTIES": _SIXDOF_PROBE,
        "SET_MOTION_GRAVITY": _SIXDOF_PROBE,
        "SET_MOTION_6DOF_INITIAL_VELOCITY": _SIXDOF_PROBE,
        "SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY": _SIXDOF_PROBE,
        "SET_MOTION_6DOF_ACTIVE_VARIABLES": _SIXDOF_PROBE,
        "CREATE_NEW_6DOF_EXTERNAL_FORCE": _SIXDOF_PROBE,
        "CREATE_NEW_6DOF_CUSTOM_FORCE": _SIXDOF_PROBE,
        "CREATE_NEW_6DOF_SPRING_FORCE": _SIXDOF_PROBE,
        "SET_6DOF_MOTION_SYMMETRY_LOADS": _SIXDOF_PROBE,
        "EXPORT_6DOF_TRAJECTORY": _SIXDOF_PROBE,
    }
)


def refuse_unprobed_wake_termination(case: SimCase, script: Script) -> None:
    """Check the selected explicit termination route before geometry emission."""
    from pyflightstream.cases.mesh import WakeTerminationMarking

    conditions = case.raw_mesh_conditions
    if (
        conditions is not None
        and case.solver.apply_wake_termination is not False
        and isinstance(conditions.wake_termination, WakeTerminationMarking)
    ):
        refuse_unprobed_commands(
            case, script, ["MARK_WAKE_TERMINATION_NODES"], capability="[wake_termination] file"
        )


def command_verified(script: Script, command: str) -> bool:
    """Say whether a probe recorded ``command`` verified on the script's build.

    Parameters
    ----------
    script : Script
        The script whose build and registry are read (hotfix builds inherit).
    command : str
        The command name.

    Returns
    -------
    bool
        True where the build's record of the command is ``verified``.
    """
    entry = script.registry.commands.get(command)
    if entry is None:
        return False
    record = entry.status_in(script.version)
    return record is not None and record.status is Status.VERIFIED


def refuse_unprobed_commands(
    case: SimCase, script: Script, commands: Iterable[str], *, capability: str
) -> None:
    """Refuse, before any emission, a gated command no probe verified on the build.

    Parameters
    ----------
    case : SimCase
        The case, named in the refusal.
    script : Script
        The script being built; its build is judged.
    commands : iterable of str
        The commands the capability is about to emit.
    capability : str
        What the row asked for, named in the refusal (``[streamlines]``, ``SIXDOF``).

    Raises
    ------
    CampaignConfigError
        Naming every gated command not verified on the build and the probe of each.
    """
    missing = sorted(
        {
            command
            for command in commands
            if command in PROBE_GATED_COMMANDS and not command_verified(script, command)
        }
    )
    if not missing:
        return
    probes = sorted({PROBE_GATED_COMMANDS[command] for command in missing})
    states = "; ".join(f"{command} is {evidence_state(script, command)}" for command in missing)
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {capability} emits {', '.join(missing)}, and on FlightStream "
        f"{script.version.canonical} no probe has recorded it verified ({states}), so the "
        "script would not rest on a run. It is refused until "
        f"{' and '.join(probes)} records the command verified on this build in the command "
        "database; nothing was run."
    )


def evidence_state(script: Script, command: str) -> str:
    """Say in words what the command database records for ``command`` on the script's build.

    Parameters
    ----------
    script : Script
        The script whose build and registry are read.
    command : str
        The command name.

    Returns
    -------
    str
        One phrase: recorded from the manual and run by no probe (``documented``),
        recorded broken by a probe, recorded removed from the build, or absent
        from the command database for the build.
    """
    entry = script.registry.commands.get(command)
    record = None if entry is None else entry.status_in(script.version)
    if record is None:
        return "absent from the command database for this build"
    if record.status is Status.DOCUMENTED:
        return "recorded from the manual and run by no probe"
    if record.status is Status.BROKEN:
        return "recorded broken by a probe"
    if record.status is Status.REMOVED:
        return "recorded removed from this build"
    return f"recorded {record.status.value}"
