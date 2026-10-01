"""Present already-resolved cases without reparsing the input library."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pyflightstream._console import wrap
from pyflightstream.cases import (
    SOLVER_SETTING_COMMANDS,
    CampaignConfigError,
    SimCase,
    classify_outputs,
)
from pyflightstream.cases.workflows import (
    carries_singularity_strength,
    row_ncpus,
    row_symmetry_loads,
)
from pyflightstream.workspace.setup_standards import setup_entry_evidence

__all__ = [
    "inspect_case_setup",
    "setup_inspection_block",
    "setup_inspection_summary",
]


def inspect_case_setup(case: SimCase, version: str) -> dict[str, Any]:
    """Return typed values, provenance, evidence and aliases from one resolved case.

    The result is a row-level configuration inspection. Point-dependent quantities
    and native effective defaults remain identified rather than guessed.

    Parameters
    ----------
    case : SimCase
        The resolved case.
    version : str
        The build the settings are judged against.

    Returns
    -------
    dict of str to object
        The case's id, setup and build, each setting with its value, provenance and evidence, and
        the aliases.
    """
    values = case.solver.model_dump(mode="json")
    explicit = case.solver.model_fields_set
    settings: dict[str, Any] = {}
    for key, value in values.items():
        available, evidence = setup_entry_evidence(key, version)
        provenance = (
            "setup" if key in explicit else "package default" if value is not None else "unset"
        )
        error = None
        override = {"max_threads": "NCPUS", "symmetry_loads": "SYMMETRY_LOADS"}.get(key)
        has_override = override is not None and any(
            name.upper() == override for name in case.variables
        )
        try:
            if key == "max_threads":
                value = row_ncpus(case, case.solver.max_threads)
            elif key == "symmetry_loads":
                # The builder owns the conflict warning; inspect the same row value once.
                value = row_symmetry_loads(
                    case, None if has_override else case.solver.symmetry_loads
                )
            if has_override:
                provenance = "matrix row"
        except CampaignConfigError as exc:
            value = None
            provenance = "unresolved matrix override"
            error = str(exc)
        settings[key] = {
            "value": value,
            "provenance": provenance,
            "command": SOLVER_SETTING_COMMANDS.get(key),
            "available": available,
            "evidence": evidence,
            "error": error,
        }
    return {
        "sim_id": case.sim_id,
        "setup": case.variables.get("matrix_set", ""),
        "build": version,
        "settings": settings,
        "aliases": case.aliases,
        "frames": [frame.model_dump(mode="json") for frame in case.frames],
        "raw_commands": [command.model_dump(mode="json") for command in case.raw_commands],
        "flags": [flag.model_dump(mode="json") for flag in case.flags],
        "boundary_conditions": (
            case.raw_mesh_conditions.model_dump(mode="json") if case.raw_mesh_conditions else None
        ),
        # SS1 of 0.30.0: whether the row's Tecplot surface carries the nodal
        # Singularity_strength, which its pproc decides; None where the row
        # declares no Tecplot surface, so there is nothing to carry it.
        "singularity_strength": (
            carries_singularity_strength(case)
            if "tecplot" in classify_outputs(case.outputs)
            else None
        ),
        "scope": "resolved row; point-dependent values and native operation require point evidence",
    }


def setup_inspection_summary(records: Sequence[Mapping[str, Any]]) -> str:
    """Return a concise per-row view of the same records used by full inspection.

    A row declaring a Tecplot surface also says whether that surface carries
    the nodal ``Singularity_strength`` (SS1 of 0.30.0).

    Parameters
    ----------
    records : sequence of mapping
        The inspection records of :func:`inspect_case_setup`, one per case.

    Returns
    -------
    str
        One line per record.
    """
    lines = []
    for record in records:
        settings, aliases, strength = _setup_facts(record)
        lines.append(
            f"  setup {record['sim_id']} ({record['build']}): "
            + settings
            + f"; aliases: {aliases}"
            + (f"; {strength}" if strength else "")
        )
    return "\n".join(lines)


def setup_inspection_block(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the lines of the console block ``Solver setup per case`` (0.31.0).

    The facts of :func:`setup_inspection_summary`, laid out for a reader: one
    heading line per case, then its settings, its aliases and, on a row
    declaring a Tecplot surface, whether the surface carries the nodal
    ``Singularity_strength``, each on its own line indented under the heading.

    Parameters
    ----------
    records : sequence of mapping
        The inspection records of :func:`inspect_case_setup`, one per case.

    Returns
    -------
    list of str
        The block's lines.
    """
    lines: list[str] = []
    for record in records:
        settings, aliases, strength = _setup_facts(record)
        setup = f", setup {record['setup']}" if record.get("setup") else ""
        lines.append(f"  POL {record['sim_id']} (FlightStream {record['build']}{setup})")
        lines.extend(wrap(f"settings: {settings}", first="    ", rest="      "))
        lines.extend(wrap(f"aliases: {aliases}", first="    ", rest="      "))
        if strength:
            lines.extend(wrap(strength, first="    ", rest="      "))
    return lines


def _setup_facts(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return one record's selected settings, its aliases and its surface note, as words."""
    settings = record["settings"]
    selected = ", ".join(
        f"{key}={settings[key]['value']}"
        for key in ("solver_model", "boundary_layer", "viscous_coupling")
    )
    aliases = ", ".join(sorted(record["aliases"])) or "none"
    strength = record.get("singularity_strength")
    surface = (
        ""
        if strength is None
        else "Singularity_strength: carried (pproc singularity_strength = true)"
        if strength
        else "Singularity_strength: not carried (pproc singularity_strength = false)"
    )
    return selected, aliases, surface
