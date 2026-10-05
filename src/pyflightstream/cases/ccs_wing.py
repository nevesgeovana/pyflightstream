"""The CCS route: a row's CCS file made into a mesh by the solver's CCS commands.

Pipeline role: the cases row, where a row's solver commands are emitted. A
matrix row names a CCS file in its ``GEOMETRY`` cell and the ``[import.ccs]``
table of the file's sidecar says how it becomes a mesh
(:class:`~pyflightstream.cases._ccs.CcsImportOptions`). This module holds the
route every kind shares, :func:`emit_ccs_geometry`, which the workflows reach
through one short hook where they open a geometry, and the wing
(:func:`emit_ccs_wing`) with the control surfaces a wing declares (CCS-2). The
fuselage and the body of revolution are
:mod:`pyflightstream.cases.ccs_fuselage` and
:mod:`pyflightstream.cases.ccs_revolution`.

THE CURVE ROUTE is the one licensed round 1 accepted on 26.124 for a wing, a
fuselage and a body of revolution, each saving a simulation that lists the
new boundary (probes C1, C4, C5)::

    CAD_CREATE_INITIALIZE
    CAD_CREATE_IMPORT_CURVE_CCS <units> 1 <component>
    <the CCS file>
    CAD_CREATE_CURVE_SELECT -1
    <the kind's settings: subdivisions, control surfaces>
    CAD_CREATE_<WING|FUSELAGE|REVOLVE>_MESH_FROM_CCS <name> ...

The GUI hands the selected virtual curves to the CCS tool with a button and no
script command does that, so the loft reads the selection that
``CAD_CREATE_CURVE_SELECT -1`` leaves. Nothing else is opened, imported or
created before it: the route is the probed one, in the probed order.

THE FILE ROUTE (``kind = "file"``) is ``CCS_IMPORT``, which imported all three
components of one file on 26.124 with each boundary named after its
``Component`` line (probe C0). It is the only route that reads a component's
``Relaxed_TE`` line, whose last value is the direction of the relaxed wake's
parametric shedding line (SRC-752 p.85); the script commands
``NEW_CCS_FUSELAGE_RELAXED_TE`` and ``NEW_CCS_REVOLVE_RELAXED_TE`` take no
direction. So a row choosing that direction (``CCS_SHEDDING``, G35) is a row on
the file route, and the run imports its own copy of the file with every
``Relaxed_TE`` line restated in the row's direction. Round 1 imported the same
fuselage with the digit 0 and 1 and the two saved simulations differ in five
per-face lines, the axial file marking a set of faces 79 apart (one per ring
along the body) and the azimuth file a run of 47 consecutive faces (around it).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from pyflightstream._lengths import UNIT_THAT_NAMES_NO_LENGTH
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases._ccs import (
    CCS_FORMATS,
    CCS_LOFT_KINDS,
    CCS_SHEDDING_COPY_SUFFIX,
    CCS_SHEDDING_VARIABLE,
    CcsImportOptions,
    ccs_component_names,
    restate_relaxed_trailing_edges,
)
from pyflightstream.script import CommandArgumentError, helpers

if TYPE_CHECKING:
    from pyflightstream.cases import SimCase
    from pyflightstream.script import Script

__all__ = [
    "REFERENCE_FRAME",
    "emit_ccs_geometry",
    "emit_ccs_wing",
    "emit_curve_prelude",
    "loft_component",
    "refuse_ccs_options_off_a_ccs_file",
]

#: The page of the user documentation the route's refusals point at.
_PAGE = "docs/ccs-geometry.md"

#: The unit word of the ``[import]`` table that says the file states its own.
_FILE_UNIT = "FILE"

# The unit ``CAD_CREATE_IMPORT_CURVE_CCS`` lists that names no length,
# ``_lengths.UNIT_THAT_NAMES_NO_LENGTH``: curves read in it would be scaled by
# whatever the solver assumes, which is the assumed unit the ``[import]``
# table exists to rule out. A raw mesh import refuses it for the same reason.

#: The frame a CCS file's coordinates and a body of revolution's axis are read
#: in: the reference frame, index 1, since the route runs before any frame exists.
REFERENCE_FRAME = 1


def _options(case: SimCase) -> CcsImportOptions:
    """Return the case's ``[import.ccs]`` table, refusing a CCS file without one."""
    spec = case.mesh_import
    if spec is None or spec.ccs is None:
        geometry = PurePath(str(case.geometry))
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the CCS file {geometry.name} and its sidecar "
            "states no [import.ccs] table, so nothing says how the solver makes a mesh "
            f"of it. Write the table under [import] in {geometry.stem}.boundaries.toml, "
            f'for example kind = "wing" and component = 1 ({_PAGE}).'
        )
    return spec.ccs


def _ccs_text(case: SimCase) -> str:
    """Read the CCS file the case names, as bytes decoded, so its line ends stay its own."""
    try:
        return Path(str(case.geometry)).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the CCS file {case.geometry!r} cannot be read as text, "
            f"so its components cannot be counted before any seat is spent: {error}"
        ) from error


def loft_component(case: SimCase, kind: str) -> tuple[CcsImportOptions, str, int]:
    """Check one loft of the curve route and return its table, boundary name and component.

    Parameters
    ----------
    case : SimCase
        The case naming the CCS file.
    kind : str
        ``wing``, ``fuselage`` or ``revolution``: the loft the caller emits.

    Returns
    -------
    tuple of (CcsImportOptions, str, int)
        The table, the boundary name the loft makes (the sidecar's first
        ``boundaries`` entry) and the component it lofts.

    Raises
    ------
    CampaignConfigError
        A table of another kind; the ``FILE`` unit, which is the file
        route's; the ``OTHER`` unit, which names no length; a component the
        file does not hold; a sidecar naming no
        boundary, or more than the loft and its control surfaces make; a
        boundary name carrying whitespace.
    """
    spec = _options(case)
    if spec.kind != kind:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the [import.ccs] table of its CCS file says "
            f"kind = {spec.kind!r}, and this is the {kind} loft; the route emits the kind "
            "the table names."
        )
    assert case.mesh_import is not None  # _options refused it otherwise
    if case.mesh_import.units == _FILE_UNIT:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the {kind} loft reads its curves in the unit [import] "
            f'states, and units = "{_FILE_UNIT}" is the file route\'s (kind = "file", '
            "whose file states its own Units line). Write the unit the file's coordinates "
            'are in, such as units = "METER".'
        )
    if case.mesh_import.units == UNIT_THAT_NAMES_NO_LENGTH:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the {kind} loft reads its curves in the unit [import] "
            f'states, and units = "{UNIT_THAT_NAMES_NO_LENGTH}" names no length, so the '
            "solver would choose the scale. Write the unit the file's coordinates are in, "
            'such as units = "METER".'
        )
    component = spec.component
    assert component is not None  # the table refuses a loft without one
    names = ccs_component_names(_ccs_text(case))
    if component > len(names):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the [import.ccs] table lofts component {component}, and "
            f"{PurePath(str(case.geometry)).name} declares {len(names)} component(s) "
            f"({', '.join(names) or 'no Component line at all'}); components are counted "
            "from 1 in the file's order."
        )
    boundaries = tuple(case.inventory or ())
    most = 1 + len(spec.control_surfaces)
    if not boundaries or len(boundaries) > most:
        makes = (
            "one boundary"
            if most == 1
            else f"one boundary, and at most {most - 1} more for its control surfaces"
        )
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the {kind} loft makes {makes}, named after the first "
            f"entry of the sidecar's boundaries, and the sidecar names "
            f"{len(boundaries)} ({', '.join(boundaries) or 'none'}). Write "
            'boundaries = ["<the name>"].'
        )
    name = boundaries[0]
    if any(character.isspace() for character in name):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the boundary name {name!r} carries whitespace, and the "
            "loft line reads its arguments as tokens separated by spaces; write one word."
        )
    return spec, name, component


def emit_curve_prelude(script: Script, case: SimCase, component: int) -> None:
    """Emit the curve route's prelude: initialize, import one component, select every curve.

    Parameters
    ----------
    script : Script
        The script being built for the point.
    case : SimCase
        The case naming the CCS file; its ``[import]`` unit is the one the
        curves are read in.
    component : int
        The component to import, counted from 1.
    """
    assert case.mesh_import is not None  # loft_component refused it otherwise
    script.emit("CAD_CREATE_INITIALIZE")
    script.emit(
        "CAD_CREATE_IMPORT_CURVE_CCS",
        case.mesh_import.units,
        REFERENCE_FRAME,
        component,
        str(case.geometry),
    )
    script.emit("CAD_CREATE_CURVE_SELECT", -1)


def emit_ccs_wing(script: Script, case: SimCase) -> None:
    """Emit the CCS wing of one point: prelude, subdivisions, control surfaces, loft.

    Parameters
    ----------
    script : Script
        The script being built for the point.
    case : SimCase
        The point's case, whose ``[import.ccs]`` table says ``kind = "wing"``.

    Raises
    ------
    CampaignConfigError
        As :func:`loft_component` refuses.
    """
    spec, name, component = loft_component(case, "wing")
    emit_curve_prelude(script, case, component)
    if spec.te_blend_length_pct is not None:
        script.emit("SET_CCS_TE_BLEND_LENGTH", spec.te_blend_length_pct)
    if spec.subdivisions is not None:
        for direction, count in (
            ("CHORD", spec.subdivisions.chord),
            ("SPAN", spec.subdivisions.span),
        ):
            if count is not None:
                script.emit("CCS_WING_MESH_SUBDIVISIONS", direction, count)
    # 26.125 asks for the curves to be assigned to the component before its
    # control surfaces (SRC-753 p.307); no earlier build carries the command.
    helpers.assign_selected_ccs_curves(script, "wing")
    for surface in spec.control_surfaces:
        # ALL TEN, SPACE and AXIS included: round 1 on 26.124 refused the
        # eight-token line the manual's sample prints (probe C3).
        script.emit(
            "NEW_CCS_WING_CONTROL_SURFACE",
            surface.name,
            surface.v0,
            surface.v1,
            surface.u0,
            surface.u1,
            surface.hinge_height,
            surface.angle_deg,
            surface.slot_gap_pct,
            surface.space,
            surface.axis,
        )
    loft_u, loft_v = spec.lofts
    script.emit(
        "CAD_CREATE_WING_MESH_FROM_CCS",
        name,
        "TRUE" if spec.mark_trailing_edges else "FALSE",
        spec.trailing_edge,
        spec.close_ends,
        loft_u,
        loft_v,
    )


def _shedding(case: SimCase) -> str | None:
    """Return the row's ``CCS_SHEDDING`` direction, or None where the row states none."""
    value = case.variables.get(CCS_SHEDDING_VARIABLE)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return helpers.resolve_shedding_direction(
            value if isinstance(value, (str, int)) else str(value),
            context=f"case {case.sim_id!r}",
        )
    except CommandArgumentError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {CCS_SHEDDING_VARIABLE} as {value!r}, and the "
            "shedding line of a Relaxed_TE component runs AXIAL (0), the default, or "
            f"AZIMUTH (1) (SRC-752 p.85). The library says: {error}"
        ) from error


def _emit_file_route(script: Script, case: SimCase, names: Sequence[str]) -> None:
    """Emit ``CCS_IMPORT`` of the whole file, or of the run's copy in the row's direction."""
    assert case.mesh_import is not None  # _options refused it otherwise
    geometry = PurePath(str(case.geometry))
    if case.mesh_import.units != _FILE_UNIT:
        raise CampaignConfigError(
            f'case {case.sim_id!r}: kind = "file" imports {geometry.name} by CCS_IMPORT, '
            "which takes no unit because the file states its own Units line, and [import] "
            f'says units = "{case.mesh_import.units}". Write units = "{_FILE_UNIT}".'
        )
    declared = tuple(case.inventory or ())
    if declared != tuple(names):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: CCS_IMPORT names each boundary after its component, in "
            f"the file's order, so {geometry.name} makes {', '.join(names) or 'nothing'}, "
            f"and the sidecar's boundaries say {', '.join(declared) or 'nothing'}. Write "
            f"boundaries = [{', '.join(repr(name) for name in names)}]."
        )
    path = str(geometry)
    direction = _shedding(case)
    if direction is not None:
        try:
            restated, count = restate_relaxed_trailing_edges(_ccs_text(case), direction)
        except CommandArgumentError as error:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {CCS_SHEDDING_VARIABLE}, and a Relaxed_TE "
                f"line of {geometry.name} cannot be read. The library says: {error}"
            ) from error
        if count == 0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {CCS_SHEDDING_VARIABLE}: {direction}, and "
                f"{geometry.name} carries no Relaxed_TE line for the direction to apply to; "
                f"remove the key, or declare the relaxed trailing edge in the file ({_PAGE})."
            )
        name = f"{geometry.stem}{CCS_SHEDDING_COPY_SUFFIX}{geometry.suffix}"
        path = name if script.working_dir is None else str(PurePath(script.working_dir) / name)
        # THE RUN'S OWN COPY, written where the point runs and hashed into the
        # record like every parked input; the user's file is never edited.
        script._pending_input_files[path] = restated.encode("utf-8")
    script.emit(
        "CCS_IMPORT",
        close_component_ends="DISABLE",
        update_properties="DISABLE",
        clear_existing="ENABLE",
        file=path,
    )


def _refuse_the_real_control_surface_form(case: SimCase, spec: CcsImportOptions) -> None:
    """Refuse a control surface written with REAL spanwise limits (RPT-097, POL 3205, RPT-126).

    Licensed round 2 on FlightStream 26.124 ran the same aileron in the two
    forms through the package route: the PARAMETRIC form completed and saved a
    simulation that differs from the wing without it (POL 3204), and the REAL
    form ended ``FAILED_EXECUTION`` with no saved simulation (POL 3205). No
    other build measured the REAL form, so it is refused on every build.
    RPT-126 then separated the cause (FR-336 R4, ``refusal_stays``): the limits
    2.0 and 3.6 end the solver process in both spaces, the REAL token does not,
    and the message states it.
    """
    for surface in spec.control_surfaces:
        if surface.space != "REAL":
            continue
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the control surface {surface.name!r} is written with REAL "
            "spanwise limits, and the plan refuses that form. On FlightStream 26.124 the REAL "
            "form ended FAILED_EXECUTION with no saved simulation, where the same surface in "
            "the PARAMETRIC form completed (licensed round 2, RPT-097). RPT-126 measured the "
            "cause: the limits 2.0 and 3.6 end the solver process (0xC0000005) in both spaces, "
            "so the REAL token is not the cause; the refusal stays because that row neither "
            "solved nor saved, and no other build measured the form. Write the limits as "
            'fractions of the span between 0 and 1 and space = "PARAMETRIC" (the default) in '
            "the sidecar's [[import.ccs.control_surfaces]]."
        )


def emit_ccs_geometry(script: Script, case: SimCase) -> None:
    """Make the case's CCS file a mesh: the loft its table names, or the whole file.

    The workflows call this where they open a geometry, for a ``GEOMETRY``
    whose suffix is a CCS file's; the length unit and the boundary inventory
    are stated by the caller right after, as after every import.

    Parameters
    ----------
    script : Script
        Script under construction, still empty.
    case : SimCase
        The case naming the CCS file.

    Raises
    ------
    CampaignConfigError
        A CCS file with no ``[import.ccs]`` table; a table beside import
        operations or a CAD table, which this route does not apply; a case
        loading a saved solver initialization into a mesh it creates; a
        sidecar declaring the raw-mesh boundary-condition tables;
        ``CCS_SHEDDING`` on a loft; and every refusal of the kind's own
        emitter.
    """
    spec = _options(case)
    assert case.mesh_import is not None  # _options refused it otherwise
    if case.mesh_import.operations or case.mesh_import.cad is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the [import] table of its CCS file also states "
            "mesh operations or an [import.cad] table, which the CCS route does not apply; "
            "delete them from the sidecar."
        )
    if case.solver.load_solver_initialization:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the CCS route creates a new mesh and cannot load a "
            "saved solver initialization."
        )
    conditions = case.raw_mesh_conditions
    declared = [
        table
        for table in ("trailing_edges", "wake_termination", "base_regions")
        if conditions is not None and getattr(conditions, table) is not None
    ]
    if declared:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the sidecar of its CCS file declares "
            f"{' and '.join(f'[{table}]' for table in declared)}, which mark a raw mesh; "
            "a CCS wing loft marks its own trailing edges (mark_trailing_edges) and a file "
            "states Mark_trailing_edges itself, so a second marking pass would mark twice. "
            "Delete the tables."
        )
    if spec.kind in CCS_LOFT_KINDS and _shedding(case) is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {CCS_SHEDDING_VARIABLE} on a {spec.kind} loft, "
            "and the direction of a Relaxed_TE shedding line exists only in the CCS file's "
            "own Relaxed_TE line: the loft route's relaxed trailing-edge commands take no "
            'direction (SRC-752 pp.306, 309). Use kind = "file" in [import.ccs], which '
            "imports the file with its Relaxed_TE lines in the row's direction."
        )
    if spec.kind == "wing":
        _refuse_the_real_control_surface_form(case, spec)
        emit_ccs_wing(script, case)
    elif spec.kind == "fuselage":
        from pyflightstream.cases.ccs_fuselage import emit_ccs_fuselage

        emit_ccs_fuselage(script, case)
    elif spec.kind == "revolution":
        from pyflightstream.cases.ccs_revolution import emit_ccs_revolution

        emit_ccs_revolution(script, case)
    else:
        _emit_file_route(script, case, ccs_component_names(_ccs_text(case)))


def refuse_ccs_options_off_a_ccs_file(case: SimCase, suffix: str) -> None:
    """Refuse an ``[import.ccs]`` table beside a geometry that is not a CCS file.

    Parameters
    ----------
    case : SimCase
        The case whose geometry is opened or imported.
    suffix : str
        The geometry's suffix, lower case.

    Raises
    ------
    CampaignConfigError
        Where the table would be read by nothing: beside a raw mesh, a CAD
        file or a saved simulation.
    """
    spec = case.mesh_import
    if spec is None or spec.ccs is None or suffix in CCS_FORMATS:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r}: the sidecar of {PurePath(str(case.geometry)).name} states "
        f"an [import.ccs] table, and the CCS route reads a CCS file "
        f"({' or '.join(sorted(CCS_FORMATS))}); nothing would read the table beside a "
        f"{suffix or 'suffixless'} file. Delete it, or name the CCS file ({_PAGE})."
    )
