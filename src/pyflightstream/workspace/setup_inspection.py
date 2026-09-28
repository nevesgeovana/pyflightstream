"""Present already-resolved cases without reparsing the input library."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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


def inspect_case_setup(case: SimCase, version: str) -> dict[str, Any]:
    """Return typed values, provenance, evidence and aliases from one resolved case.

    The result is a row-level configuration inspection. Point-dependent quantities
    and native effective defaults remain identified rather than guessed.
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
    """
    lines = []
    for record in records:
        settings = record["settings"]
        selected = [
            f"{key}={settings[key]['value']}"
            for key in ("solver_model", "boundary_layer", "viscous_coupling")
        ]
        aliases = ", ".join(sorted(record["aliases"])) or "none"
        strength = record.get("singularity_strength")
        surface = (
            ""
            if strength is None
            else "; Singularity_strength: carried (pproc singularity_strength = true)"
            if strength
            else "; Singularity_strength: not carried (pproc singularity_strength = false)"
        )
        lines.append(
            f"  setup {record['sim_id']} ({record['build']}): "
            + ", ".join(selected)
            + f"; aliases: {aliases}"
            + surface
        )
    return "\n".join(lines)
