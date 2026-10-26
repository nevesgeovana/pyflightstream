"""Open saved geometry and apply the run's setup, boundary selections and symmetry.

The marking stage prepares the saved simulation before a matrix run. This
module opens its staged copy and retains the row's base-region operations.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from hashlib import sha256
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
from pyflightstream.cases import (
    BaseRegionOperation,
    CampaignConfigError,
    PortBoundary,
    SimCase,
)
from pyflightstream.cases import (
    setup_surfaces as _setup_surfaces,
)
from pyflightstream.cases._skipped_families import (
    PPROC_ARTIFACT,
    SETUP_ARTIFACT,
    skips_a_name_the_model_lacks,
)
from pyflightstream.cases.ccs_wing import (
    refuse_ccs_options_off_a_ccs_file,
)
from pyflightstream.script import (
    Script,
)

from ._conventions import (
    command_accepted_on,
)
from ._names import (
    _judge_the_group_members_the_model_lacks,
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
    BASE_REGIONS_VARIABLE,
    CONFIGURATION_VARIABLE,
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

    The column must reach both the script configuration and its label.

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
    """Open prepared geometry, or import and mark the explicit FSI raw-mesh route."""
    _configuration_comment(case, script)
    if case.geometry is None:
        refuse_ccs_options_off_a_ccs_file(case, "")
        _geometry_simulation_controls(case, script)
        return
    suffix = PurePath(case.geometry).suffix.lower()
    if suffix != SIMULATION_SUFFIX and (case.fsi is not None or case.fsi_external is not None):
        # Keep the adapter's loads/results dependencies local to the FSI branch.
        # Its injected emitter avoids a cases -> workspace -> cases dependency
        # cycle; importing workspace's marking implementation here would add it.
        from pyflightstream.cases.fsi_workspace import _import_fsi_geometry

        _import_fsi_geometry(case, script)
        _geometry_simulation_controls(case, script, default_unit="METER")
        _setup_surfaces.emit_setup_surfaces(script, case)
        _refuse_a_pproc_the_geometry_shares_no_name_with(case, script)
        _judge_the_group_members_the_model_lacks(case, script)
        _detect_base_regions(case, script)
        return
    if suffix != SIMULATION_SUFFIX:
        mesh = PurePath(case.geometry).with_suffix(".obj")
        raise CampaignConfigError(
            f"case {case.sim_id!r}: GEOMETRY {case.geometry!r} must be an .fsm. "
            f"Run pyfs-workspace geometry mark-boundaries {mesh} --apply, "
            "then run the saved simulation. Choose apply (CLI: --apply) for marking. "
            "Only FSI rows retain raw meshes. "
            "See docs/mesh-inputs.md."
        )
    refuse_ccs_options_off_a_ccs_file(case, suffix)
    load = case.solver.load_solver_initialization
    script.emit("OPEN", case.geometry, "ENABLE" if load else "DISABLE")
    _geometry_simulation_controls(case, script)
    _declare_boundaries(case, script)
    _setup_surfaces.emit_setup_surfaces(script, case)
    _refuse_a_pproc_the_geometry_shares_no_name_with(case, script)
    _judge_the_group_members_the_model_lacks(case, script)
    _detect_base_regions(case, script)


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


def _park_the_inlet_profile(
    case: SimCase, script: Script, port: PortBoundary, port_index: int, name: str
) -> str:
    """Read a port's inlet profile, verify it and park it; return the parked file name."""
    if name != "inlets":
        raise CampaignConfigError("an outlet profile has no documented native command")
    profile = Path(str(port.profile))
    try:
        payload = profile.read_bytes()
    except OSError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the inlet profile {profile} of port "
            f"{port.boundary!r} cannot be read ({error.strerror or error}); "
            "restore the file the matrix row names, or drop the profile."
        ) from error
    digest = sha256(payload).hexdigest()
    if port.profile_sha256 and digest != port.profile_sha256:
        raise CampaignConfigError(f"inlet profile changed after binding: {profile}")
    if not payload:
        raise CampaignConfigError(f"inlet profile is empty: {profile}")
    profile_name = f"pfs_inlet_{port_index}_{digest[:16]}.txt"
    script.park_input_file(profile_name, payload)
    return profile_name


def _setup_ports(case: SimCase, script: Script) -> None:
    """Apply resolved port conditions during setup, preserving measured creation/staging order."""
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
            profile_name = _park_the_inlet_profile(case, script, port, port_index, name)
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
            owner = "the setup" if sidecar == "setup" else sidecar
            exactly = "as the mesh does" if sidecar == "setup" else "as the sidecar does"
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {table} of {owner} names the surface {name!r}, "
                f"and the mesh's surfaces, as its boundaries and the import's renames left "
                f"them, are {known}. Name a surface exactly {exactly}; never by "
                "position."
            )
        if index not in indices:
            indices.append(index)
    return indices


def _base_region_families(case: SimCase) -> list[str]:
    """Return the boundaries that become base regions, as named: row first, then pproc."""
    declared = _variable(case, BASE_REGIONS_VARIABLE)
    if declared is not None:
        return [token.strip() for token in str(declared).split(",") if token.strip()]
    if case.pproc is not None:
        return list(case.pproc.base_regions)
    return []


def _base_region_operations(
    case: SimCase,
    script: Script,
    skipped_regions: Sequence[str] = (),
    declared: Mapping[str, int] | None = None,
) -> None:
    """Apply base indices or earlier boundary names in order, tracking deletion.

    An entry whose ``boundary`` the row's study holds and the model lacks is
    not emitted (FR-982), and a skip that renumbers the base regions an
    indexed entry counts is refused (FR-983).
    """
    actions = _the_operations_the_model_reaches(case, script, skipped_regions)
    for action in _named_base_operations(actions, dict(declared or {})):
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


def _named_base_operations(
    actions: Sequence[BaseRegionOperation], regions: dict[str, int]
) -> list[BaseRegionOperation]:
    """Resolve names against earlier declarations and creates, tracking indexed deletions."""
    count = max(regions.values(), default=0)
    resolved = []
    for action in actions:
        if action.operation == "create":
            count += 1
            if isinstance(action.boundary, str):
                if action.boundary in regions:
                    raise CampaignConfigError(
                        f"base region {action.boundary!r} is already declared"
                    )
                regions[action.boundary] = count
        elif action.operation != "mark_outflow_edges":
            action = _named_base_selection(action, regions)
            if action.operation == "delete" and isinstance(action.index, int):
                regions = {
                    name: index - int(index > action.index)
                    for name, index in regions.items()
                    if index != action.index
                }
                count = max(0, count - 1)
        resolved.append(action)
    return resolved


def _named_base_selection(
    action: BaseRegionOperation, regions: Mapping[str, int]
) -> BaseRegionOperation:
    """Resolve a follow-up boundary name without borrowing a mesh boundary's index."""
    if action.boundary is None:
        return action
    index = regions.get(str(action.boundary))
    if index is None:
        raise CampaignConfigError(
            f"base region {action.boundary!r} has no earlier create or declared region; "
            "declare it first, or use index for a region in an opened saved simulation"
        )
    return action.model_copy(update={"index": index, "boundary": None})


def _the_operations_the_model_reaches(
    case: SimCase, script: Script, skipped_regions: Sequence[str]
) -> list[BaseRegionOperation]:
    """Return the base-region operations this model reaches, refusing a renumbering skip.

    FR-982: an entry whose ``boundary`` names a surface the row's model
    lacks and its study holds is left out. FR-983: a skip in ``base_regions``
    (``skipped_regions``), or of a ``create`` entry, renumbers every base
    region after it, so it is refused where an entry addresses a region by an
    index other than ``all``. With no vocabulary every entry is kept and a
    name the model lacks is refused where it is resolved, unless
    the run asked for the refusal (FR-988). A ``boundary`` is classified against
    the model as its geometry opened it, before ``delete_surfaces``.
    """
    operations = list(case.solver.base_region_operations or ())
    renumbering = [("base_regions", name) for name in skipped_regions]
    labels = script.entities.labels("boundaries")
    if not operations or not labels:
        _refuse_a_renumbering_skip(case, renumbering)
        return operations
    ordered = _setup_surfaces.the_model_inventory(script)
    kept: list[BaseRegionOperation] = []
    for position, action in enumerate(operations, 1):
        key, boundary = f"base_region_operations[{position}]", action.boundary
        if isinstance(boundary, str) and skips_a_name_the_model_lacks(
            case, SETUP_ARTIFACT, key, boundary, ordered
        ):
            if action.operation == "create":
                renumbering.append((key, boundary))
            continue
        kept.append(action)
    _refuse_a_renumbering_skip(case, renumbering)
    return kept


def _refuse_a_renumbering_skip(case: SimCase, skipped: Sequence[tuple[str, str]]) -> None:
    """Refuse a skip that renumbers the base regions an indexed entry counts (FR-983)."""
    indexed = next(
        (
            (position, action.index)
            for position, action in enumerate(case.solver.base_region_operations or (), 1)
            if action.index is not None and action.index != "all"
        ),
        None,
    )
    if not skipped or indexed is None:
        return
    key, name = skipped[0]
    position, index = indexed
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {key} cites {name!r}, which the geometry "
        f"{PurePath(str(case.geometry)).name} does not carry and the row's study skips, and "
        f"the setup's base_region_operations[{position}] addresses a base region by index "
        f"{index}. A skipped base region renumbers every region after it, so that entry "
        "would act on another region than the one it was written for. Address the entry "
        "with index = 'all', or give this model a setup of its own (FR-435)."
    )


def _a_base_region_the_study_skips(case: SimCase, script: Script, name: str) -> bool:
    """Whether a pproc ``base_regions`` name the model lacks is skipped (FR-982).

    A row's own ``BASE_REGIONS`` refuses an absent name (FR-979), and so does a
    reference declaring no vocabulary at the default flag (FR-981); the study
    refuses a name it does not hold, and a run that asked for the refusal
    refuses every one under the pproc key, with or without a vocabulary (FR-984,
    FR-988). The words that name no set and a surface the setup removed are not
    judged (FR-982).
    """
    if _variable(case, BASE_REGIONS_VARIABLE) is not None:
        return False
    return skips_a_name_the_model_lacks(
        case, PPROC_ARTIFACT, "base_regions", name, _setup_surfaces.the_model_inventory(script)
    )


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
    _base_region_detection_angle(case, script)
    labels = script.entities.labels("boundaries")
    indices: list[int] = []
    skipped: list[str] = []
    for family in families:
        if not labels:
            _refuse_name_without_inventory(case, BASE_REGIONS_VARIABLE, family)
        found = _resolve_token(case, family, labels)
        if not found and _a_base_region_the_study_skips(case, script, family):
            skipped.append(family)
            continue
        if not found:
            _refuse_name_absent_from_inventory(case, BASE_REGIONS_VARIABLE, family, labels)
        indices.extend(index for index in found if index not in indices)
    for index in sorted(indices):
        script.emit("DETECT_BASE_REGIONS_BY_SURFACE", boundary_index=index)
    declared = {
        name: position
        for position, index in enumerate(sorted(indices), 1)
        for name, boundary in labels.items()
        if boundary == index
    }
    _base_region_operations(case, script, skipped, declared)


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
    geometry into receives no inventory declaration here.

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
            "read by those positions.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return
    if stated is None and case.inventory is not None:
        # PFS-2029.06.03: a sidecar states the order; the file's own block
        # is the authority, and the two disagreeing means one of them was
        # edited since the sidecar was written, which no run may guess at.
        sidecar_name = (
            case.boundaries_file or PurePath(str(case.geometry)).name + ".boundaries.toml"
        )
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

    The tail of :func:`_declare_boundaries` (G12), shared so the
    additional post declares the inventory a saved simulation holds by the
    same rule the run declared it by, and every label resolves as it did in
    the run.
    """
    # R03: the run record carries these names, so the post reads a
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
        with its own token set (FSM-25.000 p.298). ``None`` is what sends a
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
