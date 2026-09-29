"""Bounded workspace adapter for the existing structural driver.

No new structural model lives here. Native deformation validity remains a
separate gate; this adapter fixes configuration, ordering and callback wiring.

THE PIECES A COUPLED ROUTE CALLS (FSI-1 of 0.30.0), each usable on its own
so the rotor route and the fixed-wing route wire the same facts once:

* :func:`fsi_workflow_refusal`, which workflows accept FSI in this release;
* :func:`aeroelastic_surface_ids`, the boundary ID the solver stores, which
  the Aeroelastic toolbox matches against and which is not the tree
  position for an OBJ import;
* :func:`structural_node_layout`, the nodes placed inside the blade and
  refused when one is not;
* :func:`patch_structural_node_frame`, the node-block frame field a scripted
  import cannot set;
* :func:`aeroelastic_rbf_type`, the morphing kernel a beam line needs;
* :func:`aeroelastic_post_script`, :func:`emit_steady_aeroelastic_analysis`
  and :func:`steady_aeroelastic_finished`, when an export shows the
  deformation and how a steady coupled run is waited for.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import PurePath
from types import MappingProxyType

from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.fsi.nodes import NodeOrderingMap, generate_node_layout, render_node_file
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion

from . import CampaignConfigError, RotorBlock, SimCase

NODES_FILE = "fsi_nodes.csv"
FAMILY_FILE = "fsi_family_map.json"
POST_FILE = "fsi_post.txt"
CALLBACK_FILE = "fsi_callback.py"
LOADS_FILE = "FS_SurfaceSection_Loads.txt"

#: THE WORKFLOWS AND FSI IN THIS RELEASE (FSI-GUARD, owner decision of
#: 2026-09-28: FSI on steady, qsteady and unsteady; unsteady_rotor refused
#: while the rotor morph is in debug). Every workflow is named with the state
#: it is in; a workflow absent from the table accepts no FSI.
#:
#: ``unsteady_rotor``: refused. On 26.124 the morph of a mapped rotating
#: blade is applied to the blade at its imported azimuth and replaces the
#: rotation instead of composing with it; reported to the vendor.
#:
#: ``steady`` and ``unsteady`` (no rotor motion): the fixed-wing structural
#: route of this release (FSI-G) wires them; until it lands they are refused
#: with the interim wording below.
#:
#: ``qsteady_rotor``: THE HOOK. The workflow does not exist yet; sector FSI
#: arrives with it. Its entry is here so the day it is registered, FSI on it
#: is a decision in this table and not an accident of the lookup.
FSI_ROTOR_IN_DEBUG = (
    "FSI on unsteady_rotor is still in debug on this release (the morph is applied "
    "to the un-rotated blade, reported to the vendor)."
)
FSI_ARRIVES_WITH_FSI_G = (
    "FSI on this workflow arrives with the fixed-wing structural route of this "
    "release (FSI-G); not wired yet."
)
FSI_ARRIVES_WITH_QSTEADY_ROTOR = (
    "FSI on qsteady_rotor arrives with the qsteady_rotor workflow and its sector "
    "structural route; not wired yet."
)
FSI_WORKFLOW_STATE: Mapping[str, str] = MappingProxyType(
    {
        "unsteady_rotor": FSI_ROTOR_IN_DEBUG,
        "steady": FSI_ARRIVES_WITH_FSI_G,
        "unsteady": FSI_ARRIVES_WITH_FSI_G,
        "qsteady_rotor": FSI_ARRIVES_WITH_QSTEADY_ROTOR,
    }
)


def fsi_workflow_refusal(workflow: str) -> str | None:
    """Return why FSI is refused on a workflow in this release, or None.

    Parameters
    ----------
    workflow : str
        The workflow name :func:`pyflightstream.cases.workflows.select_workflow`
        returned.

    Returns
    -------
    str or None
        The refusal's reason, from :data:`FSI_WORKFLOW_STATE`; None when
        the workflow accepts FSI. Every workflow of this release is
        refused on this branch: none is wired yet.
    """
    if workflow in FSI_WORKFLOW_STATE:
        return FSI_WORKFLOW_STATE[workflow]
    return (
        f"FSI is wired only through the package's workflows ({', '.join(FSI_WORKFLOW_STATE)}); "
        f"{workflow!r} is not one of them."
    )


#: THE BOUNDARY ID OF A FRESH IMPORT, as the solver numbers it (FSI-1).
#: A saved simulation's ``$MESH$`` block opens each boundary record with the
#: boundary's ID, and the ID is what a motion's boundary list and the
#: Aeroelastic toolbox's surface list hold. A script cites a boundary by its
#: position in the geometry tree; ``SET_MOTION_BOUNDARIES`` is converted to
#: the ID by the solver, ``ASSIGN_AEROELASTIC_SURFACES`` is stored as written
#: and matched against the ID. Measured on 26.124 (probe evidence of
#: 2026-09-28, a census of 3825 saved simulations and a mapped-blade probe):
#: an OBJ import numbers its boundaries from 2 (``2:Blade1;3:S;4:N``), an STL
#: import from 1. The ID is the position plus this offset. A surface list
#: holding the position of an OBJ blade points at a boundary that does not
#: exist and maps 0 vertices, in silence.
IMPORT_BOUNDARY_ID_OFFSET: Mapping[str, int] = MappingProxyType({".obj": 1, ".stl": 0})


def aeroelastic_surface_ids(
    case: SimCase, script: Script, boundaries: Sequence[int | str], *, context: str
) -> list[int]:
    """Return the solver's boundary IDs of the cited boundaries (FSI-1).

    The Aeroelastic toolbox stores ``ASSIGN_AEROELASTIC_SURFACES`` as
    written and maps the surfaces whose boundary ID matches, so it must
    be handed the ID the solver gives the boundary, which is the ID the
    same boundary's motion holds (:data:`IMPORT_BOUNDARY_ID_OFFSET`).

    Parameters
    ----------
    case : SimCase
        The case; its geometry's suffix names the import route.
    script : Script
        The script the geometry was imported into, with its boundary
        inventory declared.
    boundaries : sequence of int or str
        Boundary labels or 1-based tree positions.
    context : str
        Names the citing location in error messages.

    Returns
    -------
    list of int
        One boundary ID per cited boundary, in the order given.

    Raises
    ------
    CampaignConfigError
        If the geometry is not a fresh import whose numbering was
        measured, rather than guessing the ID.
    """
    suffix = PurePath(str(case.geometry)).suffix.lower() if case.geometry is not None else ""
    offset = IMPORT_BOUNDARY_ID_OFFSET.get(suffix)
    if offset is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {context} needs the solver's boundary ID, and how the "
            f"solver numbers the boundaries of {suffix or 'this geometry'} is not measured "
            f"(measured: {', '.join(IMPORT_BOUNDARY_ID_OFFSET)} imports). A wrong ID maps "
            "no surface, in silence, so it is not guessed."
        )
    return [script.resolve_boundary(value, context=context) + offset for value in boundaries]


def structural_node_layout(cfg: FsiConfig) -> NodeOrderingMap:
    """Return the structural node layout, refused when a node is not inside the blade.

    The owner's rule of 2026-09-28: the structural nodes sit inside the
    component. With the blade's sections in the configuration
    (``BladeProperties.section_contours_m``), the nodes are placed on
    each section's camber line and a node outside its section, or
    inside it by less than max(1 mm, 10 % of the local thickness), is
    refused naming it (:func:`pyflightstream.fsi.nodes.generate_node_layout`).
    Without them, the configuration states offsets and no geometry, and
    the layout is the offset layout, unchecked: the geometry the check
    needs is the configuration's sections, and the imported mesh is not
    read here.

    Raises
    ------
    CampaignConfigError
        Naming the node, when one is not inside its section.
    """
    try:
        return generate_node_layout(cfg)
    except FsiInputError as refused:
        raise CampaignConfigError(f"FSI structural nodes: {refused}") from refused


#: THE MORPHING KERNEL OF A BEAM LINE (FSI-1). The package's structural nodes
#: are a beam line: three nodes per station along the span. On 26.124,
#: against an imposed bend of a wing driven through one beam line,
#: MULTI_QUADRATIC delivered the bend to 0.003 m at the leading edge (tip
#: 0.4007 for 0.4); WENDLAND_C2 delivered 64 % of it at the leading edge and
#: 1.4 % at the trailing edge, a nose-up shear of up to 14 deg, and the
#: coupled run diverged from its third step. Probe evidence of 2026-09-28.
BEAM_LINE_RBF_TYPE = "MULTI_QUADRATIC"


def aeroelastic_rbf_type(case: SimCase) -> str:
    """Return the morphing kernel a coupled row emits: the row's, else the beam line's.

    Parameters
    ----------
    case : SimCase
        The case; a setup stating ``aeroelastic_rbf_type`` is kept.

    Returns
    -------
    str
        The ``AEROELASTIC_RBF_TYPE`` value: the row's own, or
        :data:`BEAM_LINE_RBF_TYPE` for the package's beam-line nodes.
    """
    stated = case.solver.aeroelastic_rbf_type
    return stated if stated is not None else BEAM_LINE_RBF_TYPE


def emit_aeroelastic_rbf_type(case: SimCase, script: Script) -> None:
    """Emit the beam-line kernel unless the row's setup already emitted its own."""
    if case.solver.aeroelastic_rbf_type is None:
        script.emit("AEROELASTIC_RBF_TYPE", aeroelastic_rbf_type(case))


#: THE NODE-BLOCK FRAME FIELD (FSI-1). ``IMPORT_AEROELASTIC_STRUCTURAL_NODES``
#: ignores its frame argument on 26.124: every scripted order, index, toggle
#: and frame stored 1 (Reference) in field 1 of the node-block line of the
#: saved ``$AEROELASTIC$`` block, the line after the working directory and
#: the execution command (``1,0,0,<nodes>,1``). A one-field patch of the
#: saved text is kept through OPEN, initialisation and the run. Probe
#: evidence of 2026-09-28.
_AEROELASTIC_START = b"$AEROELASTIC_START$"
_NODE_BLOCK_LINE = 5  # lines after the start marker: header, flags, directory, command
_NODE_BLOCK = re.compile(rb"(\d+),(\d+),(\d+),(\d+),(\d+)")


def patch_structural_node_frame(saved: bytes, frame_index: int, *, node_count: int) -> bytes:
    """Return a saved simulation with its structural nodes in another frame.

    Only field 1 of the node-block line changes; every other byte is
    kept. The route that needs a moving node frame saves the built
    simulation, patches it here and opens the patched file; a node set
    in Reference never needs it.

    Parameters
    ----------
    saved : bytes
        The saved simulation (``.fsm``) as written by ``SAVEAS``.
    frame_index : int
        The 1-based index of the frame in the simulation's frame table,
        the index the script cites it by.
    node_count : int
        The number of structural nodes imported; field 4 of the line
        must state it, so a line that is not the node block is never
        patched.

    Returns
    -------
    bytes
        The patched file.

    Raises
    ------
    CampaignConfigError
        If the file has no single ``$AEROELASTIC$`` block, or the line
        where the node block sits does not have its shape or its count.
    """
    if frame_index < 1:
        raise CampaignConfigError(f"a frame index is 1-based; got {frame_index}.")
    if saved.count(_AEROELASTIC_START) != 1:
        raise CampaignConfigError(
            f"the saved simulation holds {saved.count(_AEROELASTIC_START)} aeroelastic "
            "blocks; the node frame is patched in exactly one."
        )
    position = saved.index(_AEROELASTIC_START)
    for _ in range(_NODE_BLOCK_LINE):
        position = saved.index(b"\n", position) + 1
    end = saved.index(b"\n", position)
    line = saved[position:end].rstrip(b"\r")
    match = _NODE_BLOCK.fullmatch(line)
    if match is None or int(match.group(4)) != node_count:
        raise CampaignConfigError(
            f"the line where the aeroelastic node block sits reads {line!r}, not "
            f"'<frame>,0,0,{node_count},1'; nothing is patched in a line that is not the "
            "node block."
        )
    return saved[:position] + str(frame_index).encode("ascii") + saved[position + match.end(1) :]


#: THE COMPLETION LINE OF A STEADY COUPLED RUN (FSI-1). In a script
#: ``EXECUTE_AEROELASTIC_ANALYSIS`` returns at once: a line after it runs at
#: solver iteration 0 while the analysis goes on, a ``CLOSE_FLIGHTSTREAM``
#: after it ends the analysis, and with neither the process never exits by
#: itself. The analysis prints this line when it ends (26.124, probe evidence
#: of 2026-09-28; the recorded steady replay of GOAL-033 ends the same way).
STEADY_AEROELASTIC_COMPLETION = "Aeroelastic solver run time"


def aeroelastic_post_script(
    version: str | FsVersion, *, surface_exports: Sequence[tuple[str, Sequence[object]]] = ()
) -> str:
    """Render the aeroelastic post-processing script.

    The solver runs it after every aerodynamic solve of a coupled run:
    in unsteady twice per step, before the structural call and after
    the morph that call returns; in steady after every coupling
    iteration, the last one included. So it is where an export that
    must show the deformation belongs, and the only place a steady
    coupled run can be observed: each pass writes the same file names,
    so the file left on disk after a step (unsteady) or after the
    analysis (steady) is the one written after the structural call.

    The sectional loads the structural program reads come first, so the
    call reads the loads of the solve that preceded it.

    Parameters
    ----------
    version : str
        The FlightStream version the script is built for.
    surface_exports : sequence of (command, arguments)
        The surface exports that must show the deformation, emitted in
        the order given after the loads (a Tecplot or VTK surface
        export: those write the solver's morphed vertices, where a
        triangulation export and ``SAVEAS`` keep the reference ones).

    Returns
    -------
    str
        The script text.
    """
    post = Script(version)
    post.emit("UPDATE_ALL_SURFACE_SECTIONS")
    post.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
    post.emit("EXPORT_SURFACE_SECTIONAL_LOADS", LOADS_FILE)
    for command, arguments in surface_exports:
        post.emit(command, *arguments)
    return post.render()


def emit_steady_aeroelastic_analysis(script: Script) -> None:
    """Emit ``EXECUTE_AEROELASTIC_ANALYSIS`` as the script's last line.

    Nothing may follow it: an export after it runs before the analysis
    has iterated and a ``CLOSE_FLIGHTSTREAM`` after it ends the
    analysis (:data:`STEADY_AEROELASTIC_COMPLETION`). The exports belong
    in :func:`aeroelastic_post_script`, and the process that ran the
    script is stopped by its runner once
    :func:`steady_aeroelastic_finished` reads the completion line.
    :func:`refuse_lines_after_steady_analysis` holds the order on the
    finished script.
    """
    script.emit("EXECUTE_AEROELASTIC_ANALYSIS")


def refuse_lines_after_steady_analysis(rendered: str) -> None:
    """Refuse a steady coupled script with any command after its analysis.

    Raises
    ------
    CampaignConfigError
        If ``EXECUTE_AEROELASTIC_ANALYSIS`` is absent, or any command
        follows it, naming the first.
    """
    lines = [line.strip() for line in rendered.splitlines() if line.strip()]
    if "EXECUTE_AEROELASTIC_ANALYSIS" not in lines:
        raise CampaignConfigError("a steady coupled script must run EXECUTE_AEROELASTIC_ANALYSIS.")
    after = lines[lines.index("EXECUTE_AEROELASTIC_ANALYSIS") + 1 :]
    if after:
        raise CampaignConfigError(
            f"{after[0]!r} follows EXECUTE_AEROELASTIC_ANALYSIS. The analysis returns at "
            "once, so that line would run before it iterates (an export of the rigid "
            "surface) or end it (CLOSE_FLIGHTSTREAM); exports belong in the aeroelastic "
            "post-processing script."
        )


def steady_aeroelastic_finished(native_output: str) -> bool:
    """Whether a steady coupled run's output shows its analysis finished."""
    return STEADY_AEROELASTIC_COMPLETION in native_output


def validate_workspace_fsi(
    case: SimCase,
    script: Script,
    *,
    workflow: str,
    continuation: bool,
) -> None:
    """Refuse cases whose initial state cannot establish the coupling ordering.

    The workflow is judged first (:func:`fsi_workflow_refusal`), so a row
    FSI is refused on in this release hears why before any other check.
    """
    if case.fsi is None:
        return
    refusal = fsi_workflow_refusal(workflow)
    if refusal is not None:
        raise CampaignConfigError(f"case {case.sim_id!r}: {refusal}")
    if continuation:
        raise CampaignConfigError(
            "FSI continuation requires proved compatible structural state and section order; "
            "automatic recovery is not yet supported."
        )
    if workflow == "unsteady_rotor" and case.fsi.omega_rad_per_s <= 0:
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
    for number, blade in enumerate(blades, start=1):
        frame = frames.get(f"{rotor.alias}_RMRP{number}")
        if not isinstance(frame, int) or frame <= 1:
            raise CampaignConfigError(f"FSI blade {blade!r} has no unique rotating frame.")
        frame_indices.append(frame)
    # FSI-1: THE SOLVER'S BOUNDARY IDS, not the tree positions. The motion's
    # boundary list holds the ID the solver converted SET_MOTION_BOUNDARIES to;
    # the Aeroelastic toolbox stores this list as written and maps the IDs it
    # holds, so an OBJ blade cited by position mapped 0 vertices.
    boundaries = aeroelastic_surface_ids(case, script, blades, context="FSI blade")
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
    layout = structural_node_layout(cfg)
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
    payloads = {
        NODES_FILE: render_node_file(layout),
        map_name: layout.model_dump_json(indent=2) + "\n",
        FAMILY_FILE: family_map.model_dump_json(indent=2) + "\n",
        POST_FILE: aeroelastic_post_script(script.version),
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
    emit_aeroelastic_rbf_type(case, script)
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
