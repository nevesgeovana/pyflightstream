"""The coupling block of an external structural program (FR-462, 0.40.0).

Route B of the use case, the one the evidence supports on 26.124 and 26.125:
the aeroelastic toolbox the beam routes already drive, with its execution
command pointed at the archiving step ``pyfs-fsi external`` in place of the
beam's step, and the user's node file imported in place of the package's
layout. The motion pair ``SET_MOTION_FSI_EXECUTABLE`` and
``SET_MOTION_FSI_STRUCTURAL_NODES`` (route A) is never emitted here: it was
rejected as unrecognised on 26.120 and no build records it verified.

The structure is a fixed wing's, on ``steady`` or ``unsteady``: one coupled
family, fed by one section distribution of the row's pproc cut in a frame the
run created, whose index links the surface. The user's nodes are stored in the
reference frame, as the scripted import stores every node set (FSI-1).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path, PurePath

from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.cases.fsi_workspace import (
    CALLBACK_FILE,
    FIXED_WING_WORKFLOWS,
    POST_FILE,
    STEADY_AEROELASTIC_ITERATIONS,
    aeroelastic_post,
    aeroelastic_surface_ids,
    emit_aeroelastic_rbf_type,
)
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.fsi.external import EXTERNAL_MANIFEST
from pyflightstream.script import Script

__all__ = [
    "EXTERNAL_NODES_FILE",
    "validate_external_fsi",
    "wire_external_fsi",
]

#: The user's node file, as the point folder holds it.
EXTERNAL_NODES_FILE = "fsi_external_nodes.csv"


def validate_external_fsi(
    case: SimCase, script: Script, *, workflow: str, continuation: bool
) -> None:
    """Refuse a row the external route cannot couple (FR-462 R4), before any coupling line.

    Parameters
    ----------
    case : SimCase
        The case; ``case.fsi_external`` names the program.
    script : Script
        The script built so far.
    workflow : str
        The row's run type.
    continuation : bool
        Whether the point continues a stopped run.

    Raises
    ------
    CampaignConfigError
        A run type other than ``steady`` or ``unsteady``, a continuation, a geometry
        that is not a fresh mesh import, a simulation not in metres, raw commands,
        symmetry copies, or no pproc.
    """
    if case.fsi_external is None:
        return
    if case.fsi is not None:
        raise CampaignConfigError(f"case {case.sim_id!r} states two structures; state one.")
    if workflow not in FIXED_WING_WORKFLOWS:
        raise CampaignConfigError(
            f'case {case.sim_id!r}: FSI mode "external" couples a fixed wing on '
            f"{' or '.join(FIXED_WING_WORKFLOWS)}, and this row runs {workflow}."
        )
    if continuation:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: an external FSI point cannot be continued: the program's "
            "own state between calls is not the package's to restore."
        )
    suffix = PurePath(str(case.geometry)).suffix.lower() if case.geometry is not None else ""
    if suffix not in {".obj", ".stl"}:
        raise CampaignConfigError(
            f'case {case.sim_id!r}: FSI mode "external" needs a fresh mesh import (OBJ or '
            "STL), whose boundary IDs the toolbox maps are measured."
        )
    if script.simulation_length_unit != "METER":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the external program's nodes and displacements are in "
            "metres, and a node set in another unit is not measured; mesh the row in METER."
        )
    if case.raw_commands or case.flags or str(case.variables.get("RAW", "")).strip():
        raise CampaignConfigError(
            f"case {case.sim_id!r}: an external FSI row cannot prove its section and frame "
            "order with raw commands or custom flags."
        )
    if str(case.variables.get("SYMMETRY", "NONE")).upper() != "NONE":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: an external FSI row couples the whole wing, without "
            "symmetry copies."
        )
    if case.pproc is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: an external FSI row needs a pproc whose one section "
            "distribution feeds the loads the program reads."
        )


def wire_external_fsi(
    case: SimCase,
    script: Script,
    *,
    workflow: str,
    interpreter: str,
    exports: Callable[[Script], None] | None,
    updates: Callable[[Script], None] | None = None,
) -> list[dict[str, object]]:
    """Stage the external program's files and emit its coupling block (FR-462 R5).

    Parameters
    ----------
    case : SimCase
        The case; ``case.fsi_external`` names the program.
    script : Script
        The script, after the section distributions were emitted.
    workflow : str
        ``steady`` or ``unsteady``.
    interpreter : str
        The Python the archiving step runs under.
    exports : callable or None
        Emits the exports the post-processing script carries.
    updates : callable, optional
        Emits the updates those exports read.

    Returns
    -------
    list of dict
        The Tecplot surfaces the post-processing script's exports recorded.

    Raises
    ------
    CampaignConfigError
        The sections do not identify the coupled family in a frame the run created,
        a staged name collides, or a convergence threshold on a build without the
        command.
    """
    structure = case.fsi_external
    if structure is None:
        return []
    family = structure.families[0]
    blocks = [block for block in script.section_blocks if block.get("families") == [family]]
    if len(script.section_blocks) != 1 or len(blocks) != 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the external program's loads come from one section "
            f"distribution over {family!r}; the pproc emits {len(script.section_blocks)}, "
            f"{len(blocks)} of them over that family alone. The loads file concatenates every "
            "distribution, so a second one would reach the program unannounced."
        )
    frame = blocks[0].get("frame_index")
    if not isinstance(frame, int) or frame <= 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the coupled family's section distribution is in frame "
            f"{frame!r}; the surface is linked to the frame its sections are cut in, which "
            "must be a frame the run created (the manual refuses the reference frame there)."
        )
    boundaries = aeroelastic_surface_ids(case, script, [family], context="external FSI family")
    post = aeroelastic_post(script.version, exports=exports, updates=updates)
    manifest = structure.model_dump_json(indent=2) + "\n"
    payloads: dict[str, str | bytes] = {
        EXTERNAL_NODES_FILE: Path(structure.structural_nodes).read_bytes(),
        EXTERNAL_MANIFEST: manifest,
        POST_FILE: post.render(),
        CALLBACK_FILE: (
            "from pyflightstream.fsi.cli import main\n"
            "raise SystemExit(main(['external', '--dir', '.']))\n"
        ),
        "fsi-provenance.json": json.dumps(structure.provenance(), indent=2) + "\n",
        # FR-462 R6: the input itself, under the digest the record states for it
        # (the run refuses a source changed after the plan).
        Path(structure.source).name: Path(structure.source).read_bytes(),
    }
    for name, source in structure.inputs.items():
        payloads[name] = Path(source).read_bytes()
    existing = {name.casefold(): content for name, content in script.pending_input_files.items()}
    for name, content in payloads.items():
        if name.casefold() in existing and existing[name.casefold()] != content:
            raise CampaignConfigError(f"case {case.sim_id!r}: FSI pending input collision: {name}")
    emit_aeroelastic_rbf_type(case, script)
    script.emit("DELETE_AEROELASTIC_STRUCTURAL_NODES")
    script.emit("ASSIGN_AEROELASTIC_SURFACES", len(boundaries), list(boundaries))
    script.emit("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS", 1, [frame])
    script.emit("IMPORT_AEROELASTIC_STRUCTURAL_NODES", frame, "DISABLE", EXTERNAL_NODES_FILE)
    script.emit("SET_AEROELASTIC_WORKING_DIRECTORY", ".")
    script.emit("SET_AEROELASTIC_POST_PROCESSING_SCRIPT", POST_FILE)
    script.emit(
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND", f'"{interpreter}" "{CALLBACK_FILE}"'
    )
    if workflow == "steady":
        script.emit(
            "SET_AEROELASTIC_ITERATIONS", structure.max_iterations or STEADY_AEROELASTIC_ITERATIONS
        )
    else:
        script.emit("SET_AEROELASTIC_ITERATIONS", 1)
        script.emit("SET_AEROELASTIC_COUPLING_IN_UNSTEADY", "ENABLE")
    if structure.convergence_threshold is not None:
        try:
            script.emit("SET_AEROELASTIC_CONVERGENCE_THRESHOLD", structure.convergence_threshold)
        except CommandNotInVersionError as error:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: [coupling] convergence_threshold needs "
                f"SET_AEROELASTIC_CONVERGENCE_THRESHOLD, which FlightStream "
                f"{script.version.canonical} does not carry ({error}); remove the key on this "
                "build."
            ) from error
    script._pending_input_files.update(payloads)
    return [dict(translation) for translation in post.surface_translations]
