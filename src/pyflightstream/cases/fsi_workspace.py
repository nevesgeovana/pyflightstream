"""Bounded workspace adapter for the existing structural driver.

No new structural model lives here. Native deformation validity remains a
separate gate; this adapter fixes configuration, ordering and callback wiring.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import PurePath

from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.fsi.nodes import generate_node_layout, render_node_file
from pyflightstream.script import Script

from . import CampaignConfigError, RotorBlock, SimCase

NODES_FILE = "fsi_nodes.csv"
FAMILY_FILE = "fsi_family_map.json"
POST_FILE = "fsi_post.txt"
CALLBACK_FILE = "fsi_callback.py"
LOADS_FILE = "FS_SurfaceSection_Loads.txt"


def validate_workspace_fsi(
    case: SimCase,
    script: Script,
    *,
    unsteady_rotor: bool,
    continuation: bool,
) -> None:
    """Refuse cases whose initial state cannot establish the coupling ordering."""
    if case.fsi is None:
        return
    if continuation:
        raise CampaignConfigError(
            "FSI continuation requires proved compatible structural state and section order; "
            "automatic recovery is not yet supported."
        )
    if not unsteady_rotor:
        raise CampaignConfigError("Workspace FSI requires the unsteady_rotor workflow.")
    if case.fsi.omega_rad_per_s <= 0:
        raise CampaignConfigError(
            "Workspace FSI requires positive omega; zero-speed coupling is unsupported."
        )
    if case.geometry is None or PurePath(str(case.geometry)).suffix.lower() not in {".obj", ".stl"}:
        raise CampaignConfigError(
            "Workspace FSI requires a fresh mesh import: inherited saved-FSM section order "
            "has no proof. Export an inspected mesh and provide its boundary sidecar."
        )
    if script.simulation_length_unit != "METER":
        raise CampaignConfigError(
            "Workspace FSI structural nodes currently require METER; other native node units "
            "have not been measured."
        )
    if case.raw_commands or case.flags or str(case.variables.get("RAW", "")).strip():
        raise CampaignConfigError(
            "Workspace FSI cannot prove section/frame order with raw commands or custom flags."
        )
    if str(case.variables.get("SYMMETRY", "NONE")).upper() != "NONE":
        raise CampaignConfigError(
            "Workspace FSI requires all blades explicitly, without symmetry copies."
        )
    if case.pproc is None or case.pproc.sections.include_symmetry:
        raise CampaignConfigError(
            "Workspace FSI requires explicit per-blade sections without symmetry copies."
        )


def wire_workspace_fsi(
    case: SimCase,
    script: Script,
    *,
    rotor: RotorBlock,
    rpm: float,
    delta_time_s: float,
    frames: Mapping[str, int | None | Mapping[str, int]],
    interpreter: str,
) -> None:
    """Stage one structural source and emit the native unsteady callback contract."""
    cfg = case.fsi
    if cfg is None:
        return
    blades = list(rotor.families_blades)
    if len(blades) != cfg.blade_count or len(set(blades)) != len(blades):
        raise CampaignConfigError("FSI blade count differs from the unique resolved rotor blades.")
    if rotor.axis != "X" or rotor.blade1.zero != "Z":
        raise CampaignConfigError(
            "FSI rotor_frame requires shaft X and blade datum Z; another node/load basis "
            "has not been established by this adapter."
        )
    if not math.isclose(abs(rpm) * math.pi / 30, cfg.omega_rad_per_s, rel_tol=1e-9):
        raise CampaignConfigError("FSI omega differs from the resolved rotor speed.")
    if cfg.time_increment_s is not None and not math.isclose(
        delta_time_s,
        cfg.time_increment_s,
        rel_tol=1e-9,
    ):
        raise CampaignConfigError("FSI time increment differs from the resolved solver clock.")
    if not math.isfinite(delta_time_s) or delta_time_s <= 0:
        raise CampaignConfigError("FSI requires a positive resolved time increment.")
    frame_indices: list[int] = []
    boundaries: list[int] = []
    for number, blade in enumerate(blades, start=1):
        frame = frames.get(f"{rotor.alias}_RMRP{number}")
        if not isinstance(frame, int) or frame <= 1:
            raise CampaignConfigError(f"FSI blade {blade!r} has no unique rotating frame.")
        frame_indices.append(frame)
        boundaries.append(script.resolve_boundary(blade, context="FSI blade"))
    if len(set(frame_indices)) != len(blades) or len(set(boundaries)) != len(blades):
        raise CampaignConfigError("FSI blade/frame/boundary mapping must be one-to-one.")
    blocks = script.section_blocks
    if len(blocks) != len(blades):
        raise CampaignConfigError("FSI needs exactly one emitted section distribution per blade.")
    families: list[SectionFamily] = []
    for block, blade, frame in zip(blocks, blades, frame_indices, strict=True):
        if (
            block.get("families") != [blade]
            or block.get("frame_index") != frame
            or block.get("plane") != "XY"
        ):
            raise CampaignConfigError(
                "FSI section order must match blade import order, each in its own "
                "rotating frame with XY cuts (span Z)."
            )
        count = block.get("count")
        if not isinstance(count, int) or count < 1:
            raise CampaignConfigError("FSI section count is not established.")
        families.append(SectionFamily(name=blade, count=count, is_blade=True))
    family_map = SectionFamilyMap(families=families)
    layout = generate_node_layout(cfg)
    reserved = {
        "config.json",
        "fsi-provenance.json",
        "state.json",
        "fsidisp.txt",
        NODES_FILE.casefold(),
        FAMILY_FILE.casefold(),
        POST_FILE.casefold(),
        CALLBACK_FILE.casefold(),
        LOADS_FILE.casefold(),
    }
    map_name = cfg.node_map_file
    if (
        PurePath(map_name).name != map_name
        or "/" in map_name
        or "\\" in map_name
        or map_name.casefold() in reserved
    ):
        raise CampaignConfigError(
            "FSI node-map path collides with a reserved file or leaves the point directory."
        )
    post = Script(script.version)
    post.emit("UPDATE_ALL_SURFACE_SECTIONS")
    post.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
    post.emit("EXPORT_SURFACE_SECTIONAL_LOADS", LOADS_FILE)
    payloads = {
        NODES_FILE: render_node_file(layout),
        map_name: layout.model_dump_json(indent=2) + "\n",
        FAMILY_FILE: family_map.model_dump_json(indent=2) + "\n",
        POST_FILE: post.render(),
        CALLBACK_FILE: (
            "from pyflightstream.fsi.cli import main\n"
            "raise SystemExit(main(['step', '--dir', '.']))\n"
        ),
    }
    existing = {name.casefold(): content for name, content in script.pending_input_files.items()}
    for name, content in payloads.items():
        if name.casefold() in existing and existing[name.casefold()] != content:
            raise CampaignConfigError(f"FSI pending input collision: {name}")
    # All identity/ordering checks precede either staging or coupling emission.
    script.emit("DELETE_AEROELASTIC_STRUCTURAL_NODES")
    script.emit("ASSIGN_AEROELASTIC_SURFACES", len(boundaries), boundaries)
    script.emit("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS", len(frame_indices), frame_indices)
    for frame in frame_indices:
        script.emit("IMPORT_AEROELASTIC_STRUCTURAL_NODES", frame, "DISABLE", NODES_FILE)
    script.emit("SET_AEROELASTIC_WORKING_DIRECTORY", ".")
    script.emit("SET_AEROELASTIC_POST_PROCESSING_SCRIPT", POST_FILE)
    script.emit(
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND", f'"{interpreter}" "{CALLBACK_FILE}"'
    )
    script.emit("SET_AEROELASTIC_ITERATIONS", 1)
    script.emit("SET_AEROELASTIC_COUPLING_IN_UNSTEADY", "ENABLE")
    script._pending_input_files.update(payloads)
