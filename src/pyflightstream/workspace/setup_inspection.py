# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.1
# artifact_id: resolved-setup-inspection
# last_modified_at: 2026-09-28T00:24:53.112Z
# last_modified_by: OpenAI / Codex / unknown / architect-reviewer-correction
# dependencies: [pyflightstream.cases, pyflightstream.workspace.setup_standards]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Restore shared interfaces and factual contract declarations for the release.
# revision_source: git
# GEOVERSE_HEADER_END
"""Present already-resolved cases without reparsing the input library."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pyflightstream.cases import SOLVER_SETTING_COMMANDS, CampaignConfigError, SimCase
from pyflightstream.cases.workflows import row_ncpus, row_symmetry_loads
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
        "scope": "resolved row; point-dependent values and native operation require point evidence",
    }


def setup_inspection_summary(records: Sequence[Mapping[str, Any]]) -> str:
    """Return a concise per-row view of the same records used by full inspection."""
    lines = []
    for record in records:
        settings = record["settings"]
        selected = [
            f"{key}={settings[key]['value']}"
            for key in ("solver_model", "boundary_layer", "viscous_coupling")
        ]
        aliases = ", ".join(sorted(record["aliases"])) or "none"
        lines.append(
            f"  setup {record['sim_id']} ({record['build']}): "
            + ", ".join(selected)
            + f"; aliases: {aliases}"
        )
    return "\n".join(lines)
