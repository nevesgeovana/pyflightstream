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

THE ROUTES (0.30.0): :func:`wire_fixed_wing_fsi` couples a fixed wing on
``steady`` and ``unsteady`` (FSI-G), :func:`wire_quasi_steady_sector_fsi`
the blade of a ``qsteady_rotor`` periodic sector (steady, the blade held
still, the structure turning at the speed the free stream turns), and
:func:`wire_workspace_fsi` the rotor's blades on ``unsteady_rotor``, refused
in this release; all three stage and emit through one helper.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePath
from types import MappingProxyType

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.fsi.nodes import NodeOrderingMap, generate_node_layout, render_node_file
from pyflightstream.fsi.state import LOADS_FILE, QUASI_STEADY_ROTOR_FILE
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion

from . import CampaignConfigError, RotorBlock, SimCase

NODES_FILE = "fsi_nodes.csv"
FAMILY_FILE = "fsi_family_map.json"
POST_FILE = "fsi_post.txt"
CALLBACK_FILE = "fsi_callback.py"

#: THE WORKFLOWS AND FSI IN THIS RELEASE (FSI-GUARD, owner decision of
#: 2026-09-28: "vamos permitir o FSI para steady, qsteady e unsteady";
#: unsteady_rotor refused while the rotor morph is in debug). Every workflow
#: is named with the state it is in: None accepts FSI, a sentence is the
#: refusal. A workflow absent from the table accepts no FSI.
#:
#: ``steady`` and ``unsteady`` (no rotor motion): ACCEPTED, the fixed-wing
#: structural route of this release (FSI-G, :func:`wire_fixed_wing_fsi`),
#: required because fixed-wing coupling is the basic FSI case.
#:
#: ``unsteady_rotor``: refused. On 26.124 the morph of a mapped rotating
#: blade is applied to the blade at its imported azimuth and replaces the
#: rotation instead of composing with it; reported to the vendor.
#:
#: ``qsteady_rotor``: ACCEPTED on a periodic SECTOR, the route of the FSI
#: study's test 2 (the blade static, the rotation in the free stream, the
#: structure's centrifugal load at that speed): :func:`wire_quasi_steady_sector_fsi`,
#: whose structural solve applies the centrifugal loads. The WHEEL stays
#: refused by its builder: several clockings averaged are not the state of
#: one structure.
FSI_ROTOR_IN_DEBUG = (
    "FSI on unsteady_rotor is still in debug on this release (the morph is applied "
    "to the un-rotated blade, reported to the vendor)."
)
FSI_WORKFLOW_STATE: Mapping[str, str | None] = MappingProxyType(
    {
        "unsteady_rotor": FSI_ROTOR_IN_DEBUG,
        "steady": None,
        "unsteady": None,
        "qsteady_rotor": None,
    }
)

#: The workflow whose FSI is the quasi-steady sector's.
QUASI_STEADY_WORKFLOW = "qsteady_rotor"

#: The workflows whose FSI is the fixed wing's (FSI-G): nothing turns, the
#: structure is one clamped wing, and its dynamic load is its own weight.
FIXED_WING_WORKFLOWS: tuple[str, ...] = ("steady", "unsteady")


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
        the workflow accepts FSI (``steady`` and ``unsteady``, the fixed
        wing; ``qsteady_rotor``, whose builder accepts it on a sector
        only).
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

    The rule of 0.30.0: the structural nodes sit inside the
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


def aeroelastic_post(
    version: str | FsVersion,
    *,
    surface_exports: Sequence[tuple[str, Sequence[object]]] = (),
    exports: Callable[[Script], None] | None = None,
    updates: Callable[[Script], None] | None = None,
) -> Script:
    """Build the aeroelastic post-processing script, as a script.

    :func:`aeroelastic_post_script` renders it; this is the same script
    before rendering, for a caller that needs what its exports recorded
    (the Tecplot surfaces a steady coupled run writes from its VTK).

    Parameters
    ----------
    version : str
        The FlightStream version the script is built for.
    surface_exports : sequence of (command, arguments)
        As :func:`aeroelastic_post_script` takes them.
    exports : callable, optional
        Emits the row's own exports into the script, after the loads the
        structural program reads and the surface exports: a steady coupled
        run's whole export block, which no line of the run's script may
        follow ``EXECUTE_AEROELASTIC_ANALYSIS`` to write. It exports only:
        the sections are updated and their loads computed once, here, before
        any export, and every other update those exports read is emitted by
        ``updates``.
    updates : callable, optional
        Emits the updates the row's exports read beyond the sections and
        their loads (the probe points), after those two and before the first
        export: every update is an analysis command, which the phase order
        refuses after an export (the L1 runs of 0.30.0, where a coupled row
        with the default exports updated the sections a second time after
        this script's loads export and did not build).

    Returns
    -------
    Script
        The post-processing script.
    """
    post = Script(version)
    post.emit("UPDATE_ALL_SURFACE_SECTIONS")
    post.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
    if updates is not None:
        updates(post)
    post.emit("EXPORT_SURFACE_SECTIONAL_LOADS", LOADS_FILE)
    for command, arguments in surface_exports:
        post.emit(command, *arguments)
    if exports is not None:
        exports(post)
    return post


def aeroelastic_post_script(
    version: str | FsVersion,
    *,
    surface_exports: Sequence[tuple[str, Sequence[object]]] = (),
    exports: Callable[[Script], None] | None = None,
    updates: Callable[[Script], None] | None = None,
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
    exports : callable, optional
        The row's own exports, as :func:`aeroelastic_post` takes them.
    updates : callable, optional
        The updates those exports read, as :func:`aeroelastic_post` takes them.

    Returns
    -------
    str
        The script text.
    """
    return aeroelastic_post(
        version, surface_exports=surface_exports, exports=exports, updates=updates
    ).render()


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


def is_steady_aeroelastic_script(rendered: str) -> bool:
    """Whether a rendered script is a steady coupled run's: its last command is the analysis.

    The run layer asks it of the script it launches: such a process never
    exits by itself (:data:`STEADY_AEROELASTIC_COMPLETION`), so it is waited
    on until the solver prints the completion line and then stopped.
    Comment lines and blank lines are not commands.
    """
    lines = [
        line.strip()
        for line in rendered.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return bool(lines) and lines[-1] == "EXECUTE_AEROELASTIC_ANALYSIS"


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
    if workflow in FIXED_WING_WORKFLOWS and case.fsi.wing is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: FSI on the {workflow} workflow is a fixed wing's (FSI-G), "
            "and the FSI input this row names states no [config.wing] table, so it describes "
            "a rotor blade and no wing. State [config.wing] (self_weight, gravity_m_per_s2, "
            "span_axis, origin_m) with omega_rad_per_s = 0 and blade_count = 1."
        )
    if workflow not in FIXED_WING_WORKFLOWS and case.fsi.wing is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the FSI input states a fixed wing ([config.wing]) and the "
            f"row runs {workflow}; a fixed wing couples on {' or '.join(FIXED_WING_WORKFLOWS)}."
        )
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
    # A QUASI-STEADY SECTOR IS PERIODIC BY DEFINITION: one blade meshed, the
    # others its images. Its structure is the meshed blade alone, so the copies
    # are refused where they would reach the structure, in the sections below.
    if (
        workflow != QUASI_STEADY_WORKFLOW
        and str(case.variables.get("SYMMETRY", "NONE")).upper() != "NONE"
    ):
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
    _stage_and_emit(
        case,
        script,
        layout=layout,
        family_map=family_map,
        post=aeroelastic_post_script(script.version),
        boundaries=boundaries,
        frames=frame_indices,
        interpreter=interpreter,
        steady=False,
    )


#: The cap on a steady coupled run's coupling iterations (FSI-G). The solver
#: stops the loop itself once its displacement residual falls below the
#: convergence it was given (26.124: 2 of 20 for a fixed displacement, probe
#: evidence of 2026-09-28); a relaxed update closes (1 - lambda) of the
#: remaining gap per call at the configured relaxation, so the cap leaves
#: room for the default 0.4 to settle.
STEADY_AEROELASTIC_ITERATIONS = 50

#: The deformed surface an unsteady coupled wing writes after every call:
#: exported in the post-processing script, so the file left after a step is
#: the morphed one (a VTK surface carries the solver's morphed vertices).
DEFORMED_SURFACE_FILE = "fsi_surface.vtk"


def _stage_and_emit(
    case: SimCase,
    script: Script,
    *,
    layout: NodeOrderingMap,
    family_map: SectionFamilyMap,
    post: str,
    boundaries: Sequence[int],
    frames: Sequence[int],
    interpreter: str,
    steady: bool,
    extra: Mapping[str, str] | None = None,
) -> None:
    """Stage the structural files and emit the coupling block: one home for every route.

    Every identity and ordering check of the calling route precedes this,
    so a refusal leaves the script without an aeroelastic line and without
    a staged file. A steady run takes :data:`STEADY_AEROELASTIC_ITERATIONS`
    coupling iterations at most and is analysed by
    :func:`emit_steady_aeroelastic_analysis`; an unsteady one couples once
    per time step inside the solver's march.
    """
    cfg = case.fsi
    assert cfg is not None
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
        DEFORMED_SURFACE_FILE.casefold(),
        QUASI_STEADY_ROTOR_FILE.casefold(),
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
        POST_FILE: post,
        CALLBACK_FILE: (
            "from pyflightstream.fsi.cli import main\n"
            "raise SystemExit(main(['step', '--dir', '.']))\n"
        ),
        **(extra or {}),
    }
    existing = {name.casefold(): content for name, content in script.pending_input_files.items()}
    for name, content in payloads.items():
        if name.casefold() in existing and existing[name.casefold()] != content:
            raise CampaignConfigError(f"FSI pending input collision: {name}")
    # All identity/ordering checks precede either staging or coupling emission.
    emit_aeroelastic_rbf_type(case, script)
    script.emit("DELETE_AEROELASTIC_STRUCTURAL_NODES")
    script.emit("ASSIGN_AEROELASTIC_SURFACES", len(boundaries), list(boundaries))
    script.emit("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS", len(frames), list(frames))
    for frame in frames:
        script.emit("IMPORT_AEROELASTIC_STRUCTURAL_NODES", frame, "DISABLE", NODES_FILE)
    script.emit("SET_AEROELASTIC_WORKING_DIRECTORY", ".")
    script.emit("SET_AEROELASTIC_POST_PROCESSING_SCRIPT", POST_FILE)
    script.emit(
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND", f'"{interpreter}" "{CALLBACK_FILE}"'
    )
    if steady:
        script.emit("SET_AEROELASTIC_ITERATIONS", STEADY_AEROELASTIC_ITERATIONS)
    else:
        script.emit("SET_AEROELASTIC_ITERATIONS", 1)
        script.emit("SET_AEROELASTIC_COUPLING_IN_UNSTEADY", "ENABLE")
    script._pending_input_files.update(payloads)


def quasi_steady_fsi_config(case: SimCase, *, rpm: float, quiet: bool = False) -> FsiConfig:
    """Return the structure of a quasi-steady sector turning at the row's speed.

    On ``qsteady_rotor`` the structural solve applies the centrifugal loads
    at the speed the free stream turns (0.30.0). So the
    configuration's ``omega_rad_per_s`` is TAKEN FROM THE ROW, ``|RPM| pi / 30``,
    the speed its ``SET_FREESTREAM ROTATION`` (or its rotating custom field)
    states, whatever the FSI input wrote; an input that states another non-zero
    speed is warned, naming both, and the row's wins. The run stages this
    configuration as the point's ``config.json``, so an RPM sweep couples each
    point at its own speed. ``quiet`` leaves the warning to the builder, which
    says it once at plan and once at run; the run's staging asks it quietly.

    Raises
    ------
    CampaignConfigError
        A row that does not turn: the route exists to apply the centrifugal
        loads, and a blade at rest is a fixed structure.
    """
    cfg = case.fsi
    if cfg is None:
        raise CampaignConfigError(f"case {case.sim_id!r} states no FSI input.")
    omega = abs(float(rpm)) * math.pi / 30.0
    if omega <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} couples a quasi-steady sector at 0 rev/min. The structural "
            "solve of this route applies the centrifugal loads at the speed the free stream "
            "turns, and a sector that does not turn has none; state the rotor's RPM."
        )
    stated = cfg.omega_rad_per_s
    if not quiet and stated > 0.0 and not math.isclose(stated, omega, rel_tol=1e-9):
        warn(
            f"case {case.sim_id!r}: the FSI input states omega_rad_per_s = {stated} rad/s and "
            f"the row turns the free stream at {abs(float(rpm))} rev/min ({omega} rad/s). The "
            "structure of a quasi-steady sector turns at the row's speed, so the row's is used.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    return cfg.model_copy(update={"omega_rad_per_s": omega})


#: How far a cut frame's axes may stray from the reference's and still be read
#: as the reference's, and how far its origin may sit off the wing's origin
#: along the span (FSI-G). Both are round-off, never a tolerance of geometry.
_AXES_TOLERANCE = 1.0e-12
_ORIGIN_TOLERANCE_M = 1.0e-9


def _refuse_a_frame_other_than_the_reference(
    case: SimCase, script: Script, frame: int, *, what: str, origin: Sequence[float]
) -> None:
    """Refuse a cut frame whose axes are not the reference's or whose origin is not ``origin``."""
    placement = script.frame_placements.get(frame)
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    if (
        placement is None
        or placement.origin is None
        or placement.axes is None
        or any(
            abs(float(a) - b) > _AXES_TOLERANCE
            for axis, unit in zip(placement.axes, identity, strict=True)
            for a, b in zip(axis, unit, strict=True)
        )
        or any(
            abs(float(a) - float(b)) > _ORIGIN_TOLERANCE_M
            for a, b in zip(placement.origin, origin, strict=True)
        )
    ):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} are cut in frame {frame}, which is not known to be "
            f"placed with the reference axes at {tuple(origin)} m. The scripted import stores "
            "the structural nodes in the reference frame (FSI-1), so the frame the blade is "
            "linked to must coincide with it for the nodes and the loads to describe one blade."
        )


def wire_quasi_steady_sector_fsi(
    case: SimCase,
    script: Script,
    *,
    config: FsiConfig,
    rotor: RotorBlock,
    interpreter: str,
    exports: Callable[[Script], None] | None,
    updates: Callable[[Script], None] | None = None,
) -> list[dict[str, object]]:
    """Stage a quasi-steady sector's rotating blade and emit its coupling (0.30.0).

    THE ROUTE of the FSI study's test 2: the blade is held still, the free
    stream turns about the shaft at the rotor's speed, and the structure is
    the ROTATING blade at that speed (``config``, from
    :func:`quasi_steady_fsi_config`): the structural program solves it with the
    centrifugal tension and its stiffening, the propeller moment and the
    in-plane centrifugal softening (the run folder is marked with
    :data:`~pyflightstream.fsi.state.QUASI_STEADY_ROTOR_FILE`, which routes
    each call to that solve). The run is steady: at most
    :data:`STEADY_AEROELASTIC_ITERATIONS` coupling iterations, the row's whole
    export block in the post-processing script (``exports``), and the builder
    ends the script with :func:`emit_steady_aeroelastic_analysis`; the runner
    stops the process after :data:`STEADY_AEROELASTIC_COMPLETION`.

    THE BLADE IS FIXED, so its frame is the one it was meshed in, and no frame
    patch is needed where that frame is the reference: blade one, at azimuth
    0 with its datum on Z, on a shaft along X through the origin, is the
    blade frame of the rotor route (x the shaft, z the span) and the reference
    frame at once. The structure is that ONE blade (``blade_count = 1``), fed
    by one section distribution over it, cut on XY (normal to the span) in a
    frame the run created that coincides with the reference. Anything else is
    refused rather than converted: the scripted import stores the nodes in the
    reference frame (FSI-1), so a blade elsewhere would be described twice.
    The surface list holds the blade's boundary ID
    (:func:`aeroelastic_surface_ids`), the nodes are placed inside its sections
    (:func:`structural_node_layout`) and the kernel is the beam line's
    (:data:`BEAM_LINE_RBF_TYPE`).

    Returns
    -------
    list of dict
        The Tecplot surfaces the post-processing script's exports recorded,
        for the caller to state in the run's script once its loads frame is
        placed.

    Raises
    ------
    CampaignConfigError
        A structure of more than one blade, a blade other than blade one at
        azimuth 0 on Z, a shaft other than X through the origin, or sections
        that do not identify the blade in the reference frame.
    """
    if config.wing is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the FSI input states a fixed wing ([config.wing]) and the "
            "row is a quasi-steady rotor sector, whose structure is a turning blade."
        )
    if config.blade_count != 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the FSI input of a quasi-steady sector states "
            f"blade_count = {config.blade_count}; the sector's structure is its one meshed "
            "blade, blade one, and the others are its periodic images."
        )
    if (
        rotor.axis != "X"
        or rotor.blade1.zero != "Z"
        or abs(rotor.blade1.azimuth_deg) > 1e-12
        or any(abs(value) > _ORIGIN_TOLERANCE_M for value in rotor.origin)
    ):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: FSI on a quasi-steady sector couples blade one at azimuth 0 "
            "with its datum on Z, on a shaft along X through the origin, where the blade frame "
            "of the rotor route (x the shaft, z the span) is the reference frame the scripted "
            "import stores the nodes in. Rotor "
            f"{rotor.alias} turns about {rotor.axis!r} from {rotor.origin} with blade one at "
            f"{rotor.blade1.azimuth_deg} deg from {rotor.blade1.zero}; mesh the sector there."
        )
    blocks = script.section_blocks
    blade = rotor.families_blades[0] if rotor.families_blades else None
    if len(blocks) != 1 or blade is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a quasi-steady sector's blade is fed by exactly one section "
            f"distribution, over blade one on the XY plane; the pproc emits {len(blocks)}."
        )
    block = blocks[0]
    if block.get("families") != [blade] or block.get("plane") != "XY":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the sector's section distribution covers "
            f"{block.get('families')!r} on the {block.get('plane')!r} plane; the structure is "
            f"blade one ({blade}), cut on XY so each section is normal to its span."
        )
    frame = block.get("frame_index")
    if not isinstance(frame, int) or frame <= 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the blade's section distribution is in frame {frame!r}; the "
            "blade is linked to the frame its sections are cut in, which must be a frame the "
            "run created (the manual refuses the reference frame there)."
        )
    _refuse_a_frame_other_than_the_reference(
        case, script, frame, what="the blade's sections", origin=(0.0, 0.0, 0.0)
    )
    count = block.get("count")
    if not isinstance(count, int) or count < 1:
        raise CampaignConfigError("FSI section count is not established.")
    boundaries = aeroelastic_surface_ids(case, script, [blade], context="FSI blade")
    family_map = SectionFamilyMap(families=[SectionFamily(name=blade, count=count, is_blade=True)])
    layout = structural_node_layout(config)
    post = aeroelastic_post(script.version, exports=exports, updates=updates)
    _stage_and_emit(
        case,
        script,
        layout=layout,
        family_map=family_map,
        post=post.render(),
        boundaries=boundaries,
        frames=[frame],
        interpreter=interpreter,
        steady=True,
        extra={
            QUASI_STEADY_ROTOR_FILE: (
                "quasi-steady rotor sector: steady coupling of a blade held still, the "
                f"structure turning at {config.omega_rad_per_s!r} rad/s\n"
            )
        },
    )
    return [dict(translation) for translation in post.surface_translations]


def wire_fixed_wing_fsi(
    case: SimCase,
    script: Script,
    *,
    workflow: str,
    interpreter: str,
    exports: Callable[[Script], None] | None,
    updates: Callable[[Script], None] | None = None,
) -> list[dict[str, object]]:
    """Stage the fixed wing's structure and emit its coupling (FSI-G of 0.30.0).

    The wing is one clamped beam fed by ONE section distribution of the
    row's pproc: over the wing's one family, on the XZ plane (sections
    normal to the span), in a frame with the reference axes whose origin
    sits on the wing's own origin along the span, so the export's offset
    is the station's distance (a frame with other axes, or elsewhere, is
    refused rather than converted). The surface list holds that family's
    boundary ID (:func:`aeroelastic_surface_ids`), the linked frame is that
    frame (the manual forbids the reference itself there), and the nodes
    are the configuration's, placed inside the wing's sections and stored
    in the reference frame (:func:`structural_node_layout`); a fixed wing
    needs no node-frame patch. The kernel is the beam line's
    (:data:`BEAM_LINE_RBF_TYPE`).

    Steady: at most :data:`STEADY_AEROELASTIC_ITERATIONS` coupling
    iterations, and the row's whole export block runs in the
    post-processing script (``exports``); the builder ends the script with
    :func:`emit_steady_aeroelastic_analysis`. Unsteady: one coupling
    iteration per time step inside the march
    (``SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE``), and ``exports``
    writes the deformed surface after every call.

    Parameters
    ----------
    case : SimCase
        The case; ``case.fsi`` states a fixed wing.
    script : Script
        The script, after the section distributions were emitted.
    workflow : str
        ``steady`` or ``unsteady``.
    interpreter : str
        The Python the structural callback runs under.
    exports : callable or None
        Emits the exports the post-processing script carries.
    updates : callable, optional
        Emits the updates those exports read, as :func:`aeroelastic_post`
        takes them.

    Returns
    -------
    list of dict
        The Tecplot surfaces the post-processing script's exports recorded,
        for the caller to state in the run's script once its loads frame is
        placed; empty when the exports write none.

    Raises
    ------
    CampaignConfigError
        If the configuration is not a wing, the sections do not identify
        one wing, or a node is not inside its section.
    """
    cfg = case.fsi
    if cfg is None:
        return []
    wing = cfg.wing
    if wing is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the fixed-wing route needs [config.wing] in the FSI input."
        )
    blocks = script.section_blocks
    if len(blocks) != 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a fixed wing is fed by exactly one section distribution, "
            f"over the wing's one family on the XZ plane; the pproc emits {len(blocks)}. The "
            "flat loads export concatenates every distribution, so a second one would be "
            "attributed to the wing or guessed."
        )
    block = blocks[0]
    families = block.get("families")
    if not isinstance(families, list) or len(families) != 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wing's section distribution covers {families!r}; it "
            "names the wing's one family, whose boundary the solver morphs."
        )
    if block.get("plane") != "XZ":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wing's sections are cut on the {block.get('plane')!r} "
            "plane; a wing along the y axis is cut on XZ, so each section is normal to its span."
        )
    frame = block.get("frame_index")
    if not isinstance(frame, int) or frame <= 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wing's section distribution is in frame {frame!r}; the "
            "wing is linked to the frame its sections are cut in, which must be a frame the "
            "run created (the manual refuses the reference frame there)."
        )
    placement = script.frame_placements.get(frame)
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    if (
        placement is None
        or placement.origin is None
        or placement.axes is None
        or any(
            abs(float(a) - b) > _AXES_TOLERANCE
            for axis, unit in zip(placement.axes, identity, strict=True)
            for a, b in zip(axis, unit, strict=True)
        )
    ):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wing's sections are cut in frame {frame}, whose axes "
            "are not known to be the reference's; the export's forces are read as x and z "
            "of the reference frame, so the frame must be placed with the reference axes."
        )
    if abs(float(placement.origin[1]) - wing.origin_m[1]) > _ORIGIN_TOLERANCE_M:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wing's sections are cut in frame {frame}, whose origin "
            f"is at y = {float(placement.origin[1])} m, and the wing's stations are measured "
            f"from y = {wing.origin_m[1]} m ([config.wing] origin_m). The export's offsets are "
            "read as station distances, so the two must agree: state the frame's y in origin_m "
            "and measure the stations from it."
        )
    count = block.get("count")
    if not isinstance(count, int) or count < 1:
        raise CampaignConfigError("FSI section count is not established.")
    name = str(families[0])
    boundaries = aeroelastic_surface_ids(case, script, [name], context="FSI wing")
    family_map = SectionFamilyMap(families=[SectionFamily(name=name, count=count, is_blade=True)])
    layout = structural_node_layout(cfg)
    post = aeroelastic_post(script.version, exports=exports, updates=updates)
    _stage_and_emit(
        case,
        script,
        layout=layout,
        family_map=family_map,
        post=post.render(),
        boundaries=boundaries,
        frames=[frame],
        interpreter=interpreter,
        steady=workflow == "steady",
    )
    return [dict(translation) for translation in post.surface_translations]
