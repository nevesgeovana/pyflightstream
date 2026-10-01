"""Opening the geometry: the mesh or CAD import, the boundaries and the symmetry.

:func:`_open_geometry` is the first thing every builder emits: the import of
the staged mesh or CAD file, the import operations a row states, the
boundary conditions of a raw mesh, the base regions, the trailing edges,
the declared boundaries and the symmetry the geometry accepts. A new
geometry operation is planned in :func:`_plan_import_operations` and
emitted by :func:`_emit_import_operation`.
"""

from __future__ import annotations

from collections.abc import (
    Sequence,
)
from dataclasses import (
    dataclass,
)
from pathlib import (
    Path,
    PurePath,
)

from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import (
    MeshReadError,
    boundary_labels,
    boundary_names,
)
from pyflightstream._lengths import (
    UNIT_THAT_NAMES_NO_LENGTH,
)
from pyflightstream.cases import (
    EVERY_SURFACE,
    CampaignConfigError,
    MeshOperation,
    RawMeshConditions,
    SimCase,
    TrailingEdgeMarking,
)
from pyflightstream.cases import (
    setup_surfaces as _setup_surfaces,
)
from pyflightstream.cases._ccs import (
    CCS_FORMATS,
)
from pyflightstream.cases.ccs_wing import (
    emit_ccs_geometry,
    refuse_ccs_options_off_a_ccs_file,
)
from pyflightstream.commands import (
    CommandNotInVersionError,
    Phase,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._conventions import (
    command_accepted_on,
)
from ._names import (
    _refuse_a_pproc_the_geometry_shares_no_name_with,
    _refuse_name_absent_from_inventory,
    _refuse_name_without_inventory,
    _resolve_token,
)
from ._rows import (
    _from_metres,
    _variable,
)
from ._vocabulary import (
    _CONDITIONS_PAGE_ANCHOR,
    _IMPORT_COMMANDS,
    _IMPORT_FRAME,
    _MESH_PAGE_ANCHOR,
    _MIRROR_PLANES,
    BASE_REGIONS_VARIABLE,
    CAD_FORMATS,
    CONFIGURATION_VARIABLE,
    GEOMETRY_VARIABLE,
    RAW_MESH_FORMATS,
    SIMULATION_LENGTH_UNIT,
    SIMULATION_SUFFIX,
)

# --- PFS-2025.02.02: the case geometry, opened first --------------------------


def _configuration_comment(case: SimCase, script: Script) -> None:
    """Write the row's CONFIGURATION at the top of the script, as a comment.

    FR-94. The column LABELS and configures nothing, so the one thing it
    owes is to be VISIBLE: a label that reaches nothing a reader opens is
    a cell nobody would fill in, which is what the requirement's own last
    sentence warns against. This is one of the two places it reaches; the
    other is the custom polar file's title line.

    IT WENT NOWHERE UNTIL 2026-09-13. The requirement said it reached both
    and the constant had two occurrences in the package, its definition
    and a key list, so the release shipped a column that configured
    nothing and labelled nothing either (the V&V lens, round two).

    Emitted FIRST, before the OPEN, because a comment is not a command and
    the phase guard does not see it; a reader opening the script meets the
    configuration before anything else.
    """
    stated = str(case.variables.get(CONFIGURATION_VARIABLE) or "").strip()
    # A dash never reaches here: `_fold_columns_into_variables` drops a
    # column that says nothing rather than folding the dash in. Checked
    # anyway, because a caller building a case in Python is not the fold.
    if not stated or stated == "-":
        return
    script.comment(f"CONFIGURATION: {stated}")


def _open_geometry(case: SimCase, script: Script) -> None:
    """Open the case's geometry, before anything else is emitted.

    THE BUG THIS CLOSES, stated once because it is the whole reason for
    the 0.8.1 patch. A case carrying a geometry and the same case with
    the geometry absent rendered BYTE-IDENTICAL scripts: no ``OPEN``, no
    ``NEW_SIMULATION``, no import of any kind. The run layer had already
    staged the file and hashed it into the record, so the manifest named
    a mesh the script never opened, and the solver solved whatever it
    happened to have in memory.

    Emitted FIRST, and not merely early: ``OPEN`` replaces the whole
    simulation state, so a coordinate system, a motion or a solver
    setting written before it would be discarded by it without a word.
    The script layer's phase order agrees (``geometry`` is the first
    phase), so a later ``OPEN`` would also be refused, but the ordering
    here is the reason rather than the consequence.

    The path opened is :attr:`pyflightstream.cases.SimCase.geometry` as
    the case carries it AT BUILD TIME, which the campaign loop has
    already rewritten to the case's own staged copy
    (:func:`pyflightstream.run.run_campaign`, which owns the staging).
    That is deliberate and
    load-bearing: ``inputs_sha256`` in the run record is the hash of the
    STAGED bytes, so opening the library original instead would break
    the pairing between the digest a record publishes and the bytes the
    solver actually read, and would break it silently.

    A RAW MESH IS IMPORTED rather than opened, since 0.27.0 (G01): an
    ``.obj`` or ``.stl`` whose sidecar states its unit becomes a new
    simulation holding that file, in metres (:func:`_import_mesh`). What
    follows the open or the import is the same for both.

    Parameters
    ----------
    case : SimCase
        The case; its ``geometry`` is the simulation file to open or the
        raw mesh to import, or None for a case that names none.
    script : Script
        Script under construction, still empty. Nothing is emitted
        until the suffix and the import table have been judged, so a
        refusal leaves it exactly as it was.

    Raises
    ------
    CampaignConfigError
        If the geometry's suffix is neither :data:`SIMULATION_SUFFIX` nor
        one of :data:`RAW_MESH_FORMATS` or the CCS formats, naming the
        suffix written and the documented routes; if a saved simulation's
        sidecar states an ``[import]`` table, which nothing would read; if
        a raw mesh is refused by :func:`_import_mesh`; or if a CCS file is
        refused by :func:`pyflightstream.cases.ccs_wing.emit_ccs_geometry`.
    """
    _configuration_comment(case, script)
    if case.geometry is None:
        _geometry_simulation_controls(case, script)
        return
    suffix = PurePath(case.geometry).suffix
    sidecar = PurePath(str(case.geometry)).stem + ".boundaries.toml"
    if suffix.lower() in {".step", ".stp"}:
        raise CampaignConfigError(
            "STEP CAD import is not supported by this workflow; use the documented "
            "IGES route (.igs/.iges), or convert and inspect a supported surface mesh. "
            "Native STEP controls produced empty geometry, so no script is emitted."
        )
    refuse_ccs_options_off_a_ccs_file(case, suffix.lower())
    if suffix.lower() in CAD_FORMATS:
        _import_cad(case, script)
        _raw_mesh_boundary_conditions(case, script)
    elif suffix.lower() in CCS_FORMATS:
        # 0.32.0 PACKAGE C (FR-240 to FR-244): the solver makes the mesh from the
        # CCS file by the route its [import.ccs] table names (cases/ccs_wing.py).
        emit_ccs_geometry(script, case)
        _geometry_simulation_controls(case, script, default_unit=SIMULATION_LENGTH_UNIT)
        _declare_boundaries(case, script, stated=case.inventory)
    elif suffix.lower() in RAW_MESH_FORMATS:
        _import_mesh(case, script, RAW_MESH_FORMATS[suffix.lower()])
        # THE TRAILING EDGE RIGHT AFTER THE IMPORT (G02), on the body the
        # import operations left and against the names its renames left: the
        # points lie on that body, in the simulation's metres.
        _raw_mesh_boundary_conditions(case, script)
    elif suffix.lower() != SIMULATION_SUFFIX:
        written = suffix or "no suffix at all"
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {GEOMETRY_VARIABLE} as a file carrying "
            f"{written}, which a workflow neither opens nor imports: it opens a saved "
            f"simulation ({SIMULATION_SUFFIX}), which carries its own length units, "
            f"and imports a raw mesh written as {' or '.join(RAW_MESH_FORMATS)} in the "
            f"length units the [import] table of {sidecar} beside it states. Convert "
            "the file to one of those, or open it in the FlightStream window once and "
            f"save a {SIMULATION_SUFFIX}; docs/mesh-inputs.md carries both routes; "
            f"search that page for '{_MESH_PAGE_ANCHOR}'. A CCS file "
            f"({' or '.join(sorted(CCS_FORMATS))}) is meshed by the solver's CCS commands "
            "(docs/ccs-geometry.md). The file this resolved to is "
            f"{case.geometry!r}."
        )
    elif case.mesh_import is not None:
        # NOT IGNORED. A saved simulation carries its own units, so a table
        # stating one beside it is read by nothing, and a key that reaches
        # nothing is the silent no-op this package refuses rather than keeps.
        raise CampaignConfigError(
            f"case {case.sim_id!r} opens the saved simulation "
            f"{PurePath(str(case.geometry)).name}, and {sidecar} beside it states an "
            f"[import] table with units = {case.mesh_import.units!r}. A {SIMULATION_SUFFIX} "
            "carries its own length units and is opened, never imported, so nothing "
            "would read the table; delete it from the sidecar (docs/mesh-inputs.md, "
            f"search '{_MESH_PAGE_ANCHOR}')."
        )
    elif case.raw_mesh_conditions is not None and _declared_condition_tables(
        _applied_boundary_conditions(case)
    ):
        # NOT IGNORED EITHER, and worse than ignored if it were read: a saved
        # simulation's trailing edges, wake-termination nodes and base regions
        # were marked when it was saved, so a second pass would mark twice.
        declared = _declared_condition_tables(_applied_boundary_conditions(case))
        raise CampaignConfigError(
            f"case {case.sim_id!r} opens the saved simulation "
            f"{PurePath(str(case.geometry)).name}, and {sidecar} beside it declares "
            f"{' and '.join(declared)}, which mark a raw mesh. A {SIMULATION_SUFFIX} "
            "carries the trailing edges, wake-termination nodes and base regions it was "
            "saved with, and a second marking pass over them would mark them twice; "
            "delete the tables from the sidecar. A row marks the base regions of a saved "
            "simulation with its BASE_REGIONS key (docs/mesh-inputs.md, search "
            f"'{_CONDITIONS_PAGE_ANCHOR}')."
        )
    else:
        # THE INITIALISATION FLAG IS ALWAYS STATED (PFS-2030.03.01). A saved
        # simulation may carry an initialised solver, and loading it would start
        # the run from a state the row never declared; the reference scripts wrote
        # DISABLE on every open, and a preset that wants the stored state says so.
        load = case.solver.load_solver_initialization
        script.emit("OPEN", case.geometry, "ENABLE" if load else "DISABLE")
        _geometry_simulation_controls(case, script)
        _declare_boundaries(case, script)
    # EVERY BOUNDARY-CITING SURFACE OF THE ROW IS JUDGED HERE, at plan
    # time, against the inventory just declared (PFS-2028.00): the pproc
    # groups below, the base regions next, and the moving boundaries,
    # plots and sections where each builder resolves them.
    _setup_surfaces.emit_setup_surfaces(script, case)
    _refuse_a_pproc_the_geometry_shares_no_name_with(case, script)
    _detect_base_regions(case, script)


def _import_cad(case: SimCase, script: Script) -> None:
    """Convert an explicitly configured CAD file, then apply mesh operations.

    IMPORT_CAD has no units argument. FILE records that the CAD file's native
    metadata is authoritative; it never pretends to forward a raw-mesh unit.
    Subsequent translation operations are explicitly in metres.
    """
    spec = case.mesh_import
    if spec is None or spec.cad is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD geometry requires [import.cad] in its "
            'boundary sidecar, with [import] units = "FILE".'
        )
    if spec.units != "FILE":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD IMPORT_CAD has no units argument; "
            'write units = "FILE" to use the source CAD metadata. A raw-mesh '
            "unit cannot be silently ignored or used to rescale CAD."
        )
    if not case.inventory:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD conversion requires an explicit boundary "
            "inventory for the converted mesh in the sidecar."
        )
    if case.solver.load_solver_initialization:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD conversion creates a new mesh and cannot "
            "load a saved solver initialization."
        )
    marking = None if case.raw_mesh_conditions is None else case.raw_mesh_conditions.trailing_edges
    if marking is not None and marking.route == "file":
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD tessellation cannot validate source "
            "trailing-edge points offline. Declare detection, or export a mesh "
            "and validate its points before using the file route."
        )
    script.entry("IMPORT_CAD")
    script.entry("CONVERT_CAD_TO_MESH")
    steps, names = _plan_import_operations(
        case, script, PurePath(str(case.geometry)).stem + ".boundaries.toml"
    )
    cad = spec.cad
    script.emit("NEW_SIMULATION")
    script.emit(
        "IMPORT_CAD",
        cad.tessellation_density,
        "TRUE" if cad.unreferenced_patches else "FALSE",
        cad.num_curvature,
        case.geometry,
    )
    script.emit("CONVERT_CAD_TO_MESH", cad.body_index)
    for step in steps:
        if step.geometry_phase:
            _emit_import_operation(script, step, "METER")
    _geometry_simulation_controls(case, script, default_unit=SIMULATION_LENGTH_UNIT)
    for step in steps:
        if not step.geometry_phase:
            _emit_import_operation(script, step, "METER")
    _declare_boundaries(case, script, stated=names)


def _geometry_simulation_controls(
    case: SimCase,
    script: Script,
    *,
    default_unit: str | None = None,
) -> None:
    """Apply setup thresholds after geometry and before frames or edge detection.

    The merge setting is emitted in native length units. This is not a claim
    that the setter repairs an already imported mesh; that native effect needs
    separate evidence. No geometry-phase guard is bypassed.
    """
    solver = case.solver
    unit = solver.simulation_length_unit or default_unit
    if unit is not None:
        script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    if solver.vertex_merge_tolerance_m is not None:
        factor = _from_metres(case, script, "vertex_merge_tolerance_m")
        script.emit("SET_VERTEX_MERGE_TOLERANCE", solver.vertex_merge_tolerance_m * factor)
    if solver.geometric_edge_bluntness_angle_deg is not None:
        script.emit("SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE", solver.geometric_edge_bluntness_angle_deg)


def _import_mesh(case: SimCase, script: Script, file_type: str) -> None:
    """Import the case's raw mesh into a new simulation, in the unit its sidecar states (G01).

    WHAT IS EMITTED, in this order::

        NEW_SIMULATION
        IMPORT  UNITS <the sidecar's unit>  FILE_TYPE <OBJ|STL>  FILE <staged copy>  CLEAR
        <the geometry-phase import operations: scale, rename, mirror>
        SET_SIMULATION_LENGTH_UNITS METER
        <the setup-phase import operations: translate, rotate>

    and then the boundary inventory is declared, from the sidecar's
    ``boundaries`` as the operations' renames left them, since a raw mesh
    carries no mesh block to read it from and the ledger cannot relabel a
    name once declared.

    THE OPERATIONS ARE THE SIDECAR'S ``[[import.operations]]`` (G03), in
    the order written and in the reference frame. Each one's phase is read
    from the command database, so an order the script's phases cannot emit
    (a scale after a translation) is refused naming both, never reordered.
    Every cited surface is resolved by name, against the names at its own
    step, before anything is emitted (:func:`_plan_import_operations`).

    THE UNIT IS NEVER ASSUMED. The file's unit is the ``[import]`` table's
    ``units`` and goes to ``IMPORT`` alone; the simulation defaults to metres
    (:data:`SIMULATION_LENGTH_UNIT`). An explicit simulation_length_unit
    overrides that after import, before dimensional frames and detection.
    Whether ``IMPORT`` then converts the body
    from the file's unit into the simulation's was measured on 26.124 (RPT-069:
    a millimetre OBJ solved as the metre one); the page states it and what is
    not measured.

    The path imported is the STAGED copy, for the reason
    :func:`_open_geometry` gives for the open.

    Raises
    ------
    CampaignConfigError
        Before the first line is emitted: the case states no ``[import]``
        table, naming the table, the key, the sidecar and the units this
        build's ``IMPORT`` takes; the table states a unit that ``IMPORT``
        does not take on this build, or ``OTHER``, which names no length;
        the setup asks to load a stored solver state, which a new
        simulation does not have; or an import operation is refused by
        :func:`_plan_import_operations`.
    """
    geometry = PurePath(str(case.geometry))
    sidecar = geometry.stem + ".boundaries.toml"
    # READ PER BUILD, never a list written here: the units the build's
    # IMPORT documents, less the one that names no length.
    documented = next(arg for arg in script.entry("IMPORT").args if arg.name == "units").values
    accepted = [unit for unit in documented or () if unit != UNIT_THAT_NAMES_NO_LENGTH]
    route = f"docs/mesh-inputs.md carries the route; search that page for '{_MESH_PAGE_ANCHOR}'"
    spec = case.mesh_import
    if spec is not None and spec.cad is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CAD options apply only to a CAD file; "
            "the raw mesh route would not read them."
        )
    if spec is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {GEOMETRY_VARIABLE} as a raw mesh "
            f"({geometry.suffix}) and states no length unit for it: write the table "
            f'[import] with the line units = "<unit>" in {sidecar} beside it, the unit '
            f"the file is written in, one of {', '.join(accepted)}. A mesh file carries "
            "no unit and this package never assumes one, because a body imported at "
            "the wrong scale solves and reports coefficients against a body of the "
            f"wrong size without a word. A saved simulation ({SIMULATION_SUFFIX}) "
            f"carries its own units and needs no table; {route}. The file this "
            f"resolved to is {case.geometry!r}."
        )
    if spec.units not in accepted:
        why = (
            "which names no length, so the scale would be the solver's guess"
            if spec.units == UNIT_THAT_NAMES_NO_LENGTH
            else f"which IMPORT does not take on FlightStream {script.version.canonical}"
        )
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {sidecar} states units = {spec.units!r} under "
            f"[import], {why}; write the unit {geometry.name} is written in, one of "
            f"{', '.join(accepted)}; {route}."
        )
    if case.solver.load_solver_initialization:
        raise CampaignConfigError(
            f"case {case.sim_id!r} imports the raw mesh {geometry.name} into a new "
            "simulation, and its setup asks to load the solver initialization, which "
            "reads a state stored in a saved simulation; a new simulation has none. "
            f"Drop the setting, or stage a saved simulation ({SIMULATION_SUFFIX}) that "
            "carries the state."
        )
    steps, names = _plan_import_operations(case, script, sidecar)
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", spec.units, file_type, case.geometry, clear=True)
    for step in steps:
        if step.geometry_phase:
            _emit_import_operation(script, step, spec.units)
    _geometry_simulation_controls(case, script, default_unit=SIMULATION_LENGTH_UNIT)
    for step in steps:
        if not step.geometry_phase:
            _emit_import_operation(script, step, spec.units)
    # THE SIDECAR'S NAMES AS THE RENAMES LEFT THEM, declared once, after the
    # operations: the ledger cannot relabel, and the file is not read for a
    # block it cannot have.
    _declare_boundaries(case, script, stated=names)


def _applied_boundary_conditions(case: SimCase) -> RawMeshConditions:
    """Adapt published sidecar declarations, with explicit setup false meaning no redefinition."""
    conditions = case.raw_mesh_conditions or RawMeshConditions()
    updates: dict[str, None] = {}
    for field, choice in (
        ("trailing_edges", case.solver.apply_trailing_edges),
        ("wake_termination", case.solver.apply_wake_termination),
        ("base_regions", case.solver.apply_base_regions),
    ):
        if choice is False:
            updates[field] = None
        elif choice is True and getattr(conditions, field) is None:
            if field != "base_regions" or not _base_region_families(case):
                raise CampaignConfigError(
                    f"setup apply_{field}=true requires its geometry declaration"
                )
    return conditions.model_copy(update=updates)


def _declared_condition_tables(conditions: RawMeshConditions) -> list[str]:
    """Name the sidecar tables a set of raw-mesh conditions came from, as written."""
    return [
        f"[{table}]"
        for table, value in (
            ("trailing_edges", conditions.trailing_edges),
            ("wake_termination", conditions.wake_termination),
            ("base_regions", conditions.base_regions),
        )
        if value is not None
    ] + [f"[[{name}]]" for name in ("inlets", "outlets") if getattr(conditions, name)]


def _raw_mesh_boundary_conditions(case: SimCase, script: Script) -> None:
    """Mark a raw mesh's trailing edges, and the options its sidecar writes (G02).

    A raw mesh carries no trailing edge, and without one the solver makes
    no wake and still runs and answers, so its sidecar declares one, in a
    ``[trailing_edges]`` table, and a raw mesh without the table is refused.

    WHAT IS EMITTED, right after the import, in this order:

    * the file route, the default: ``IMPORT_WAKE_EDGES_FROM_FILE <TYPE>
      <TOLERANCE> METER`` with the node file on the next line, named in the
      folder the script runs in
      (:attr:`pyflightstream.script.Script.working_dir`), which the run
      writes it into, and never beside the staged geometry, a link into the
      shared input library
      (:func:`pyflightstream.script.helpers.mark_wake_edges`).
      The points were read and checked against the mesh when the row was
      bound, and are in the simulation's metres. The file marks exactly the
      edges it names, since initialisation adds none (RPT-065), and the run
      compares the count the solver logs as imported with the points
      written. Measured on 26.124 only (RPT-061): 26.122 and 26.123 are
      refused by the helper, and an earlier build by the absent command.
    * or detection, only when written: ``SET_TRAILING_EDGE_SWEEP_ANGLE``
      when an angle is stated, then ``AUTO_DETECT_TRAILING_EDGES`` over
      every surface or ``DETECT_TRAILING_EDGES_BY_SURFACE`` on the surfaces
      named.
    * ``[wake_termination]``: ``AUTO_DETECT_WAKE_TERMINATION_NODES``, or one
      ``DETECT_WAKE_TERMINATION_NODES_BY_SURFACE`` per surface named, on the
      detection route only. On the file route the detection waits for the
      solver to initialise and is emitted by :func:`_script_init` between two
      initialisations (:func:`_wake_termination_after_initialization`), since
      right after a file import it marks nothing (RPT-069, T07). Its surfaces
      are resolved here on both routes, so a name the sidecar does not carry
      is refused before anything else is emitted.
    * ``[base_regions]``: ``AUTO_DETECT_BASE_REGIONS``, which marked the
      base of a body with a flat base on 26.124 (RPT-066).

    Surfaces are cited by the sidecar's names as the import's renames left
    them, exactly as written, never by position.

    Raises
    ------
    CampaignConfigError
        No ``[trailing_edges]`` table; a file route beside an import
        operation that moves, scales or copies the body, since the points
        name edges of the file as written; a file route whose points were
        never read (a case built in Python stating none); a surface the
        sidecar does not name; or ``[base_regions]`` beside a row or pproc
        naming base regions of its own.
    CommandNotInVersionError
        The file route on a build other than 26.124, from the helper.
    """
    geometry = PurePath(str(case.geometry))
    sidecar = geometry.stem + ".boundaries.toml"
    page = f"docs/mesh-inputs.md, search that page for '{_CONDITIONS_PAGE_ANCHOR}'"
    conditions = _applied_boundary_conditions(case)
    marking = None if conditions is None else conditions.trailing_edges
    if marking is None and case.solver.apply_trailing_edges is not False:
        raise CampaignConfigError(
            f"case {case.sim_id!r} imports the raw mesh {geometry.name}, and {sidecar} "
            "beside it declares no [trailing_edges] table. Without a marked trailing edge "
            "there is no wake, and the solver runs and answers anyway. Write the table "
            'with file = "<points file>", the default route: the mid-point of every '
            "trailing-edge mesh edge under a line naming their length unit, checked "
            'against the mesh before the run; or with detect = "auto", the solver\'s '
            f"detection, which applies only when written ({page})."
        )
    if marking is None:
        pass
    elif marking.route == "none":
        if conditions.wake_termination is not None:
            raise CampaignConfigError(
                "a no-trailing-edge body cannot request wake termination nodes"
            )
        warn(
            f"case {case.sim_id!r}: explicit no trailing edge; this body generates no wake",
            PyflightstreamWarning,
            stacklevel=2,
        )
    elif marking.route == "file":
        _mark_trailing_edges_from_file(case, script, marking, sidecar, page)
    else:
        if marking.sweep_angle_deg is not None:
            script.emit("SET_TRAILING_EDGE_SWEEP_ANGLE", marking.sweep_angle_deg)
        if not marking.detect_surfaces:
            script.emit("AUTO_DETECT_TRAILING_EDGES")
        else:
            indices = _sidecar_surfaces(
                case, script, sidecar, "[trailing_edges]", marking.detect_surfaces
            )
            script.emit("DETECT_TRAILING_EDGES_BY_SURFACE", len(indices), indices)
    # RESOLVED ON BOTH ROUTES, so a surface the sidecar does not name is refused
    # here; EMITTED here on the detection route only (the file route's waits for
    # an initialisation, :func:`_script_init`).
    detection = _wake_termination_detection(case, script, sidecar)
    if marking is None or marking.route != "file":
        for command, arguments in detection:
            script.emit(command, *arguments)
    if conditions.base_regions is not None:
        named = _base_region_families(case)
        if named:
            raise CampaignConfigError(
                f'case {case.sim_id!r}: {sidecar} declares [base_regions] detect = "auto", '
                "which detects every base region of the mesh, and the row (or its pproc) "
                f"also names base regions, {', '.join(named)}. Declare them once: the "
                "sidecar's detection over the whole mesh, or the row's BASE_REGIONS on the "
                f"boundaries that become the base ({page})."
            )
        _base_region_detection_angle(case, script)
        script.emit("AUTO_DETECT_BASE_REGIONS")


def _setup_ports(case: SimCase, script: Script) -> None:
    """Apply resolved port conditions during setup, preserving measured creation/staging order."""
    if case.raw_mesh_conditions and (
        case.raw_mesh_conditions.inlets or case.raw_mesh_conditions.outlets
    ):
        raise CampaignConfigError("inlet/outlet conditions belong to setup ports and MATRIX")
    if not case.solver.ports:
        return
    if case.geometry is None or PurePath(case.geometry).suffix.lower() == SIMULATION_SUFFIX:
        raise CampaignConfigError(
            "saved or unknown geometry port indices are not proven empty; setup ports require "
            "a fresh imported mesh until the saved port inventory is established"
        )
    if case.solver.delete_inlets or case.solver.delete_outlets:
        raise CampaignConfigError("new setup ports cannot share a run with explicit port deletions")
    seen: set[str] = set()
    for port in case.solver.ports:
        if port.kind is None:
            raise CampaignConfigError("setup ports require an explicit inlet or outlet kind")
        if port.boundary in seen:
            raise CampaignConfigError("a boundary is assigned more than once to setup ports")
        if port.boundary is not None:
            seen.add(port.boundary)
    # Native 26.124 uses one created-port sequence for both families.
    # An outlet on mesh boundary 2 is port 1 alone, or port 2 after an inlet.
    # RPT-081 preserves the negative controls and target-only remesh evidence.
    port_index = 0
    for port in case.solver.ports:
        name = "inlets" if port.kind == "inlet" else "outlets"
        command = "CREATE_NEW_INLET" if port.kind == "inlet" else "CREATE_NEW_OUTLET"
        if port.boundary is None or port.velocity is None:
            raise CampaignConfigError("setup ports must bind geometry identities and MATRIX values")
        port_index += 1
        profile_name = None
        if port.profile is not None:
            if name != "inlets":
                raise CampaignConfigError("an outlet profile has no documented native command")
            from hashlib import sha256

            profile = Path(port.profile)
            payload = profile.read_bytes()
            digest = sha256(payload).hexdigest()
            if port.profile_sha256 and digest != port.profile_sha256:
                raise CampaignConfigError(f"inlet profile changed after binding: {profile}")
            if not payload:
                raise CampaignConfigError(f"inlet profile is empty: {profile}")
            profile_name = f"pfs_inlet_{port_index}_{digest[:16]}.txt"
            parked = script.pending_input_files.get(profile_name)
            if parked is not None and parked != payload:
                raise CampaignConfigError(f"inlet profile staging collision: {profile_name}")
            script._pending_input_files[profile_name] = payload
        indices = _sidecar_surfaces(case, script, "setup", "[[ports]]", (port.boundary,))
        script.emit(command, indices[0], port.velocity)
        if port.remesh is not None:
            mesh = port.remesh
            unit_scale = _from_metres(case, script, f"{name} remesh radius")
            script.emit(
                "REMESH_INLET" if name == "inlets" else "REMESH_OUTLET",
                port_index,
                inner_radius=mesh.inner_radius_m * unit_scale,
                elements=mesh.radial_faces,
                growth_scheme="1" if mesh.growth_scheme == "successive" else "2",
                growth_rate=mesh.growth_rate,
            )
        if profile_name is not None:
            script.emit("SET_INLET_CUSTOM_PROFILE", port_index, profile_name)


def _wake_termination_detection(
    case: SimCase, script: Script, sidecar: str
) -> list[tuple[str, tuple[int, ...]]]:
    """Return the ``[wake_termination]`` detection a raw mesh's sidecar writes (G02).

    ``AUTO_DETECT_WAKE_TERMINATION_NODES`` for ``detect = "auto"``, or one
    ``DETECT_WAKE_TERMINATION_NODES_BY_SURFACE`` per surface named, cited
    by the sidecar's names exactly; nothing when the table is not written.
    Each command comes with its arguments. WHERE it is emitted is the
    route's: with the detected edges on the detection route
    (:func:`_raw_mesh_boundary_conditions`), between two initialisations
    on the file route (:func:`_wake_termination_after_initialization`).
    """
    conditions = _applied_boundary_conditions(case)
    wake = None if conditions is None else conditions.wake_termination
    if wake is None:
        return []
    if wake == "auto":
        return [("AUTO_DETECT_WAKE_TERMINATION_NODES", ())]
    return [
        ("DETECT_WAKE_TERMINATION_NODES_BY_SURFACE", (index,))
        for index in _sidecar_surfaces(case, script, sidecar, "[wake_termination]", wake)
    ]


def _wake_termination_after_initialization(
    case: SimCase, script: Script
) -> list[tuple[str, tuple[int, ...]]]:
    """Return the wake-termination detection that waits for an initialisation (G02, T07).

    MEASURED ON 26.124 (RPT-069, T07), on a twisted blade whose root end is
    its one wake-termination node. Right after ``IMPORT_WAKE_EDGES_FROM_FILE``
    the detection, automatic or by surface, marks nothing. Run after
    ``INITIALIZE_SOLVER`` it marks the node, and the loads do not move,
    because the solver was initialised without it. Initialised again, which
    clears the first initialisation, the run equals the saved simulation and
    the detection route to the printed digit; without the node its induced
    drag was 1.8 % lower. The log reports the trailing-edge groups only
    during an initialisation, which is the inferred reason: the detection
    finds the ends of groups the file route has not created yet.

    So this is non-empty exactly for a script that imported its trailing
    edges from a file (:attr:`~pyflightstream.script.Script.wake_edge_points`
    is set) of a raw mesh whose sidecar writes ``[wake_termination]``, and
    :func:`_script_init` emits it between two initialisations with the same
    settings. A continuation reopens a saved simulation that carries the
    node and imports nothing, so it gets nothing here.
    """
    conditions = _applied_boundary_conditions(case)
    if script.wake_edge_points is None or conditions is None:
        return []
    marking = conditions.trailing_edges
    if marking is None or marking.route != "file":
        return []
    sidecar = PurePath(str(case.geometry)).stem + ".boundaries.toml"
    return _wake_termination_detection(case, script, sidecar)


def _mark_trailing_edges_from_file(
    case: SimCase, script: Script, marking: TrailingEdgeMarking, sidecar: str, page: str
) -> None:
    """Emit the file route of ``[trailing_edges]``, its points already checked (G02)."""
    geometry = PurePath(str(case.geometry))
    named = PurePath(marking.points_file).name if marking.points_file else "the points file"
    spec = case.mesh_import
    moving = (
        []
        if spec is None
        else [
            f"operation {position} ({operation.op})"
            for position, operation in enumerate(spec.operations, start=1)
            if operation in spec.moving_operations
        ]
    )
    if moving:
        listed = ", ".join(moving)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {sidecar} marks the trailing edges of {geometry.name} "
            f"by the points file {named}, and its [import] table also moves, scales or "
            f"copies the body: {listed}. The points name edges of the mesh as the file "
            "holds it and are checked against that file, so those operations would carry "
            "the edges away from them and the import would mark nothing, in silence. "
            "Apply the operations to the mesh file itself, or mark the edges by detection, "
            f'detect = "auto" ({page}).'
        )
    if not marking.points_m:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the [trailing_edges] file route of {sidecar} carries "
            f"no points. A case bound from a matrix row reads them from {named} and checks "
            "them against the mesh; a case built in Python states them, in metres, as "
            f"TrailingEdgeMarking.points_m ({page})."
        )
    # IN THE FOLDER THE SCRIPT RUNS IN, never beside the staged geometry. A
    # staged geometry is a link into the input library, one folder every
    # simulation on the same mesh shares, so a node file named beside it was one
    # file for all of them: a case submitted while another on the mesh was still
    # queued replaced that job's points before it read them, with the same count,
    # and a points file its author had named like the node file was written
    # over. The run gives the script its working folder (a point's datapoint
    # folder, a steady job's simulation folder), writes the file there before
    # the solver starts, and hashes those bytes into the record.
    name = f"{geometry.stem}.wake_nodes.txt"
    node_file = name if script.working_dir is None else str(PurePath(script.working_dir) / name)
    helpers.mark_wake_edges(
        script,
        edge_type=marking.edge_type,
        tolerance=marking.tolerance,
        units=SIMULATION_LENGTH_UNIT,
        node_file=node_file,
        midpoints=marking.points_m,
    )


def _sidecar_surfaces(
    case: SimCase, script: Script, sidecar: str, table: str, names: Sequence[str]
) -> list[int]:
    """Resolve the surfaces a raw mesh's sidecar table names, exactly, to their indices."""
    labels = script.entities.labels("boundaries")
    indices: list[int] = []
    for name in names:
        index = labels.get(name)
        if index is None:
            known = ", ".join(repr(label) for label in labels) or "none"
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {table} of {sidecar} names the surface {name!r}, "
                f"and the mesh's surfaces, as its boundaries and the import's renames left "
                f"them, are {known}. Name a surface exactly as the sidecar does; never by "
                "position."
            )
        if index not in indices:
            indices.append(index)
    return indices


@dataclass(frozen=True)
class _ImportStep:
    """One mesh operation of an import, resolved before anything is emitted (G03)."""

    position: int
    operation: MeshOperation
    command: str
    geometry_phase: bool
    #: The 1-based position of the surface it acts on, at its own step; None
    #: for every surface.
    surface: int | None


def _import_operation_command(script: Script, op: str) -> str:
    """Return the command one import operation emits on this script's build."""
    if op != "rotate":
        return _IMPORT_COMMANDS[op]
    for name in helpers.ROTATION_COMMANDS:
        try:
            script.entry(name)
        except CommandNotInVersionError:
            continue
        return name
    # No registered build documents neither; the lookup of the phase below
    # then refuses naming the build, still before anything is emitted.
    return helpers.ROTATION_COMMANDS[0]


def _plan_import_operations(
    case: SimCase, script: Script, sidecar: str
) -> tuple[list[_ImportStep], tuple[str, ...]]:
    """Resolve the import operations the sidecar declares, refusing before any emission (G03).

    Returns the steps in the order written and the boundary names as the
    renames leave them. Walked once, in order, on a LOCAL copy of the names,
    because the script's own ledger cannot relabel a name once declared and
    the solver renames only when the script runs.

    Raises
    ------
    CampaignConfigError
        A geometry-phase operation written after a setup-phase one, naming
        both by position and kind; a surface name absent at its step,
        listing the names at that step; a name two surfaces carry at its
        step; or a rename onto a name another surface carries.
    """
    spec = case.mesh_import
    if spec is None:
        return [], tuple(case.inventory or ())
    names = list(case.inventory or ())
    steps: list[_ImportStep] = []
    first_setup: _ImportStep | None = None
    for position, operation in enumerate(spec.operations, start=1):
        command = _import_operation_command(script, operation.op)
        # THE PHASE IS THE DATABASE'S, per build, never a list written here.
        geometry_phase = script.entry(command).phase is Phase.GEOMETRY
        if geometry_phase and first_setup is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {sidecar} declares operation {position} "
                f"({operation.op}) after operation {first_setup.position} "
                f"({first_setup.operation.op}); {operation.op} is a geometry command "
                f"({command}) and {first_setup.operation.op} a setup command "
                f"({first_setup.command}), and a script cannot return to the geometry "
                "phase once it has reached the setup phase, so the two cannot be emitted "
                "in the order written, and they are never reordered. Write every scale, "
                "rename and mirror before the first translate or rotate, restating a "
                "translation in the scaled size if the scale was meant to act on it "
                "(docs/mesh-inputs.md)."
            )
        surface = None
        if operation.surface != EVERY_SURFACE:
            surface = _import_surface(case, sidecar, names, position, operation)
        if operation.op == "rename" and surface is not None and operation.to is not None:
            taken = [
                index
                for index, name in enumerate(names, start=1)
                if name == operation.to and index != surface
            ]
            if taken:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: operation {position} (rename) of {sidecar} "
                    f"renames {operation.surface!r} to {operation.to!r}, which surface "
                    f"{taken[0]} already carries at that step, and two surfaces of one "
                    "name cannot be cited apart. Choose a name no other surface carries."
                )
            names[surface - 1] = operation.to
        step = _ImportStep(position, operation, command, geometry_phase, surface)
        if not geometry_phase and first_setup is None:
            first_setup = step
        steps.append(step)
    return steps, tuple(names)


def _import_surface(
    case: SimCase, sidecar: str, names: Sequence[str], position: int, operation: MeshOperation
) -> int:
    """Return the 1-based position of the surface one import operation names, at its step."""
    found = [index for index, name in enumerate(names, start=1) if name == operation.surface]
    where = (
        f"case {case.sim_id!r}: operation {position} ({operation.op}) of {sidecar} names "
        f"the surface {operation.surface!r}"
    )
    if not found:
        known = ", ".join(repr(name) for name in names) or (
            "none, since the sidecar states no boundaries"
        )
        raise CampaignConfigError(
            f"{where}, and the surfaces at that step are {known}. Cite a surface by the "
            "name the file gives it, or by the name an earlier rename gave it, exactly as "
            "written; never by position (docs/mesh-inputs.md)."
        )
    if len(found) > 1:
        raise CampaignConfigError(
            f"{where}, which {len(found)} surfaces carry at that step (positions "
            f"{', '.join(str(index) for index in found)}), so it selects none of them. "
            "Give those surfaces distinct names in the mesh file."
        )
    return found[0]


def _emit_import_operation(script: Script, step: _ImportStep, units: str) -> None:
    """Emit one resolved import operation, in the reference frame (G03)."""
    operation = step.operation
    if operation.op == "rotate":
        # MeshOperation's own check states both for a rotation; this narrows the type.
        assert operation.axis is not None and operation.angle_deg is not None
        helpers.rotate_surfaces(
            script,
            frame=_IMPORT_FRAME,
            axis=operation.axis,
            angle_deg=operation.angle_deg,
            boundaries="all" if step.surface is None else [step.surface],
        )
        return
    if operation.op == "rename":
        script.emit(step.command, index=step.surface, name=operation.to)
        return
    if operation.op == "mirror":
        # JOINED TO ITS SOURCE, which survives: the surface count is unchanged,
        # and the other three outcomes add or replace a surface whose name and
        # position are unmeasured.
        assert operation.plane is not None
        script.emit(
            step.command,
            surface=step.surface,
            coordinate_system=_IMPORT_FRAME,
            mirror_plane=_MIRROR_PLANES[operation.plane],
            combine_flag="TRUE",
            delete_source_flag="FALSE",
        )
        return
    # EVERY SURFACE IS EACH COMMAND'S OWN SENTINEL, read from the database:
    # -1 on SURFACE_SCALE and 0 on TRANSLATE_SURFACE_IN_FRAME.
    surface = step.surface
    if surface is None:
        argument = next(arg for arg in script.entry(step.command).args if arg.name == "surface")
        surface = argument.all_sentinel
    if operation.op == "scale":
        assert operation.factors is not None
        scale_x, scale_y, scale_z = operation.factors
        script.emit(
            step.command,
            frame=_IMPORT_FRAME,
            scale_x=scale_x,
            scale_y=scale_y,
            scale_z=scale_z,
            surface=surface,
        )
        return
    assert operation.vector is not None
    x, y, z = operation.vector
    # IN THE FILE'S UNIT, which the command states on its own line. A named
    # surface splits its vertices from its neighbours, as the row's own
    # translation does (RPT-048); every surface together has none to split from.
    script.emit(
        step.command,
        frame=_IMPORT_FRAME,
        x=x,
        y=y,
        z=z,
        units=units,
        surface=surface,
        split_vertices="DISABLE" if step.surface is None else "ENABLE",
    )


def _base_region_families(case: SimCase) -> list[str]:
    """Return the boundaries that become base regions, as named: row first, then pproc."""
    declared = _variable(case, BASE_REGIONS_VARIABLE)
    if declared is not None:
        return [token.strip() for token in str(declared).split(",") if token.strip()]
    if case.pproc is not None:
        return list(case.pproc.base_regions)
    return []


def _base_region_operations(case: SimCase, script: Script) -> None:
    """Apply explicit base indices in order; deletion may renumber later selections."""
    settings = case.solver
    for action in settings.base_region_operations or ():
        if action.operation == "create":
            assert action.boundary is not None and action.model is not None
            boundary = script.resolve_boundary(action.boundary, context="base-region create")
            script.emit("CREATE_NEW_BASE_REGION", boundary, action.model, action.cp)
            continue
        if action.operation == "mark_outflow_edges":
            commands = ("SET_OUTLET_TRAILING_EDGES", "SET_OUTFLOW_TRAILING_EDGES")
            command = next(
                (
                    name
                    for name in commands
                    if command_accepted_on(script.registry.commands[name], script.version)
                ),
                None,
            )
            if command is None:
                raise CampaignConfigError(
                    f"base-region outflow-edge marking has no documented route on {script.version}"
                )
            assert action.boundary is not None
            boundary = (
                -1
                if action.boundary == "all"
                else script.resolve_boundary(action.boundary, context="base-region outflow edges")
            )
            script.emit(command, boundary)
            continue
        index = -1 if action.index == "all" else action.index
        assert index is not None
        if action.operation == "set_pressure":
            args = (index, action.model) if action.cp is None else (index, action.model, action.cp)
            script.emit("SET_BASE_REGION_CP", *args)
        elif action.operation == "remesh":
            mesh = action.mesh
            assert mesh is not None
            unit_scale = _from_metres(case, script, "base-region remesh radius")
            script.emit(
                "REMESH_BASE_REGION",
                index,
                inner_radius=mesh.inner_radius_m * unit_scale,
                elements=mesh.radial_faces,
                growth_scheme="1" if mesh.growth_scheme == "successive" else "2",
                growth_rate=mesh.growth_rate,
            )

        else:
            command = {
                "delete": "DELETE_BASE_REGION",
                "mark_trailing_edges": "SET_BASE_REGION_TRAILING_EDGES",
                "select_faces": "SELECT_BASE_REGION_FACES",
            }[action.operation]
            script.emit(command, index)


def _base_region_detection_angle(case: SimCase, script: Script) -> None:
    angle = case.solver.base_region_bending_angle_deg
    if angle is not None:
        script.emit("SET_BASE_REGION_BENDING_ANGLE", angle)


def _detect_base_regions(case: SimCase, script: Script) -> None:
    """Emit one DETECT_BASE_REGIONS_BY_SURFACE per boundary of the named families.

    PFS-2029.10, the third sentence of item #6: base region is an
    optional input naming mesh families, so the autodetect runs on those
    surfaces only. Naming none emits nothing, which is every golden and
    every recorded script; AUTO_DETECT_BASE_REGIONS, the whole-geometry
    form, is what a raw mesh's sidecar asks for when it writes
    ``[base_regions] detect = "auto"``, or a recipe of your own calls, and
    this package never decides on its own which surfaces have a base.

    THE NAMED BOUNDARY IS THE ONE THAT BECOMES THE BASE (RPT-066, 26.124).
    The command takes the index of the base region's own boundary: given
    20_BODY's ``Base`` it marks the 24 faces the automatic detection marks,
    and given its ``Body`` it marks nothing and says nothing. Nothing here
    can tell a base from a body offline, so the key's page says which to
    name, and the tier-3 rows name ``Base``.
    """
    if case.solver.apply_base_regions is False:
        if case.solver.base_region_operations:
            raise CampaignConfigError(
                "apply_base_regions=false conflicts with base_region_operations"
            )
        return
    families = _base_region_families(case)
    if not (case.raw_mesh_conditions and case.raw_mesh_conditions.base_regions):
        _base_region_detection_angle(case, script)
    labels = script.entities.labels("boundaries")
    indices: list[int] = []
    for family in families:
        if not labels:
            _refuse_name_without_inventory(case, BASE_REGIONS_VARIABLE, family)
        found = _resolve_token(case, family, labels)
        if not found:
            _refuse_name_absent_from_inventory(case, BASE_REGIONS_VARIABLE, family, labels)
        indices.extend(index for index in found if index not in indices)
    for index in sorted(indices):
        script.emit("DETECT_BASE_REGIONS_BY_SURFACE", boundary_index=index)
    _base_region_operations(case, script)


def _declare_boundaries(
    case: SimCase, script: Script, *, stated: Sequence[str] | None = None
) -> None:
    """Declare the opened geometry's boundary names onto the script.

    BOUND TO THE ``OPEN`` AND NOT TO THE SCRIPT'S CONSTRUCTION, which
    is the whole of why this call sits here (PFS-2028.00). Declaring
    when the script is built would assert a name-to-index map for a
    file that only the recipe decides whether to open, and would hand
    a pre-declared script to arbitrary user code: a recipe calling
    :meth:`~pyflightstream.script.Script.declare_existing` itself, which
    ``docs/mesh-inputs.md`` documents as the supported route, would then
    ADD to a total this package had already set, because the count form
    accumulates. Declared here, the inventory and the opened file are the
    same file by construction, and a script this package did not open a
    geometry into is left exactly as it was before this release.

    Parameters
    ----------
    case : SimCase
        The case whose geometry was just opened. The path read is the
        one ``OPEN`` received, which the campaign loop has already
        rewritten to the STAGED copy, so the names come from the same
        bytes the run record hashes and the solver reads.
    script : Script
        Script under construction, with ``OPEN`` already emitted.
    stated : sequence of str, optional
        The names to declare when the file carries no mesh block to read
        them from: a raw mesh, whose names its sidecar states (G01). The
        file is then not read, since an ``.obj`` or ``.stl`` has no block
        and reading one whole to learn that costs the file's size.

    Notes
    -----
    NOTHING HERE REFUSES A RUN THAT WORKS TODAY. A geometry carrying no
    mesh block leaves the inventory undeclared, which is exactly the
    state FR-30c licenses and the state every run was in before this
    release. A block that opens and then does not hold its shape warns
    and leaves it undeclared too, because a patch may not stop a
    campaign that ran yesterday; what the warning buys is that the user
    learns why a name in a row is not resolving, instead of being told
    that no labels are registered as though it were their mistake.
    """
    if case.geometry is None:
        return
    names: Sequence[str] | None
    try:
        names = tuple(stated) if stated is not None else boundary_names(case.geometry)
    except MeshReadError as unreadable:
        warn(
            f"case {case.sim_id!r}: {unreadable} No boundary names are declared for "
            "this run, so a row naming one is refused and a row citing positions is "
            "read exactly as it was before this release.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return
    if stated is None and case.inventory is not None:
        # PFS-2029.06.03: a sidecar states the order; the file's own block
        # is the authority, and the two disagreeing means one of them was
        # edited since the sidecar was written, which no run may guess at.
        sidecar_name = PurePath(str(case.geometry)).stem + ".boundaries.toml"
        if names and tuple(names) != tuple(case.inventory):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the mesh block of "
                f"{PurePath(str(case.geometry)).name} lists {', '.join(names)} and the "
                f"sidecar {sidecar_name} lists {', '.join(case.inventory)}; the two "
                "disagree, so no boundary index this run would cite can be trusted. "
                "Rewrite the sidecar from the file with `pyfs-matrix inventory "
                "<geometry>`, overwrite (CLI: --overwrite), if the file is current, or "
                "restage the file "
                "the sidecar describes."
            )
        names = tuple(case.inventory)
    if not names:
        return
    _declare_inventory(case, script, names)


def _declare_inventory(case: SimCase, script: Script, names: Sequence[str]) -> None:
    """Declare boundary names onto the script, the name at position i being boundary i.

    The tail of :func:`_declare_boundaries`, split out at 0.27.0 (G12) so the
    additional post declares the inventory a saved simulation holds by the
    same rule the run declared it by, and every label resolves as it did in
    the run.
    """
    # R03 of 0.27.0: the run record carries these names, so the post reads a
    # selection over the geometry the script was built over rather than over
    # the cuts alone. Every name, duplicates included: position i is boundary i.
    script.boundary_inventory = tuple(names)
    labels, ambiguous = boundary_labels(names)
    if ambiguous:
        warn(
            f"case {case.sim_id!r}: {PurePath(str(case.geometry)).name} carries "
            f"{len(ambiguous)} boundary name(s) used more than once "
            f"({', '.join(sorted(ambiguous))}), and a name that means two surfaces "
            "cannot select either one. Those boundaries are citable by position only; "
            "every other name in the file resolves.",
            PyflightstreamWarning,
            # One frame deeper than before the split, so the warning still
            # points at the caller of `_declare_boundaries`.
            stacklevel=3,
        )
    if labels:
        script.declare_existing(boundaries=labels)
    # TOP THE TOTAL UP TO THE FILE'S TRUE COUNT. The mapping form sets
    # the total to the highest index it names, so a file whose LAST
    # boundary has a duplicated name would declare an inventory smaller
    # than the file and turn a correct position into a refusal. The
    # count form adds, which is a pinned contract, so the difference is
    # exactly what restores the true total.
    highest = max(labels.values(), default=0)
    if len(names) > highest:
        script.declare_existing(boundaries=len(names) - highest)


# --- PFS-2025.02.03: the solver initialization, off the same row --------------


def accepted_symmetry(script: Script) -> tuple[str, ...] | None:
    """Return the symmetry modes one build's INITIALIZE_SOLVER accepts.

    READ FROM THE COMMAND DATABASE, per build, and never a literal list
    kept here. The modes are a per-version fact of the command's own
    grammar, so a list in this module would be a second declaration of
    a vocabulary this package already stores with its evidence, free to
    drift the moment a build states a different set.

    The database is reached through :attr:`Script.registry`, which is
    public for exactly this reason: everything recording a per-version
    fact ABOUT a script has to ask the same database the script itself
    validates against.

    Parameters
    ----------
    script : Script
        The script under construction, bound to one build.

    Returns
    -------
    tuple of str or None
        The accepted tokens, in the order the database declares them.
        ``None`` where that build's ``INITIALIZE_SOLVER`` declares no
        argument called ``symmetry`` at all, which is a real case and
        not a failure: FlightStream 25.000 spells it ``SYMMETRY_TYPE``
        with its own token set (SRC-749 p.298). ``None`` is what sends a
        row on to
        :func:`pyflightstream.script.helpers.initialize_solver`, whose
        refusal already names that edition and its remedy.

        An EMPTY TUPLE where the build declares a ``symmetry`` argument
        that is NOT an enumeration. A non-enum argument carries no
        ``values`` in the command database and reads back as ``()``. No
        registered build is that shape today: 25.000 spells the argument
        ``symmetry_type`` and every other build declares the three-token
        enum.

        BOTH FALSY ANSWERS MEAN "THIS BUILD CANNOT JUDGE A MODE", so a
        caller tests truthiness::

            if accepted and mode not in accepted:
                ...

        That is what the built-in workflows do, and they deliberately do
        NOT tell the two apart. Tell them apart only when REPORTING to a
        user which fact holds: ``None`` means the build declares no
        argument of that name, ``()`` means it declares one that is not
        an enumeration. An earlier draft of this paragraph pointed at the
        workflow builders as the precedent for distinguishing them, which
        is the opposite of what they do, and a reader following that
        citation found a truthiness test and could reasonably conclude
        ``is not None`` was sanctioned. It is not.

        AN ENUMERATION DECLARING NO TOKENS IS NOT ONE OF THESE CASES,
        and the distinction is worth a line because the obvious reading
        gets it backwards. That state cannot exist:
        :class:`pyflightstream.commands.ArgSpec` refuses to validate an
        enum with no values, so a database containing one fails to load.
        An earlier draft of this section offered it as the meaning of
        ``()`` and called the real producer impossible, which is exactly
        the reading under which ``if accepted is not None`` looks
        correct at the call site. It is not, and that regression was
        written and reverted once already.

    Raises
    ------
    pyflightstream.commands.CommandNotInVersionError
        When the build's command view carries no ``INITIALIZE_SOLVER``
        at all. Unreachable from the builders, which call
        :func:`require_coverage` first, and reachable by a caller
        passing a :class:`~pyflightstream.script.Script` bound to a
        build that only the registry knows.
    """
    entry = script.registry.for_version(script.version)["INITIALIZE_SOLVER"]
    for argument in entry.args:
        if argument.name == "symmetry":
            return tuple(argument.values or ())
    return None
