"""Additional post-processing of a saved simulation: the extraction script.

:func:`build_additional_script` builds the script that opens a saved
simulation and extracts what a row's additional post-processing asks for,
refusing what a saved point cannot give.
"""

from __future__ import annotations

import warnings

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream._errors import (
    PyflightstreamError,
)
from pyflightstream.cases import (
    EXPORT_KINDS,
    OPT_IN_EXPORT_KINDS,
    CampaignConfigError,
    PlotsSpec,
    PprocSpec,
    SimCase,
)
from pyflightstream.commands import (
    CommandRegistry,
)
from pyflightstream.script import (
    Script,
)
from pyflightstream.versions import (
    FsVersion,
    resolve,
)

from ._conventions import (
    WorkflowConventions,
    WorkflowCoverageError,
)
from ._exports import (
    _export_block,
    with_tecplot_source,
)
from ._geometry import (
    _configuration_comment,
    _declare_inventory,
)
from ._names import (
    _refuse_a_pproc_the_geometry_shares_no_name_with,
)
from ._pproc import (
    _pproc_sections,
)
from ._registry import (
    build_script,
)
from ._solver_settings import (
    _analysis,
)
from ._steady import (
    refuse_an_untranslatable_surface,
)
from ._vocabulary import (
    _NOT_EXTRACTED_KINDS,
    _UNSTEADY_RECIPES,
    ADDITIONAL_POST_BUILDS,
    ADDITIONAL_PPROC_VARIABLE,
    RESERVED_CONTINUATION_VARIABLES,
    RESTART_VARIABLE,
)

# --- G12 (0.27.0): the additional post over a saved simulation ----------------


def refuse_what_a_saved_point_cannot_give(pproc: PprocSpec, *, pproc_id: str, where: str) -> None:
    """Refuse an additional pproc that asks what a reopened simulation does not give back.

    RPT-062 measured it on 26.124: a point's saved simulation, opened again with
    no solve, gives back the total loads, the surface solution, every surface
    section and the sectional loads computed on it, a distribution defined after
    reopening included, and on an unsteady point its plots history. It does not
    give back the field off the body: probe points updated or created after
    reopening differ from the run's. So an additional pproc declares section
    distributions, chooses among the surface exports and states its
    post-processing tables, and every table asking for something else is refused
    HERE, at plan, before a seat is spent:

    * ``[[probes]]`` and ``[volume_section]``, the field off the body (RPT-062);
    * ``[plots]`` and ``[time_averaging]``, which fill during a march, and the
      additional post runs none;
    * ``base_regions``, which marks a mesh before its solve, and a saved
      simulation carries the marks it was saved with;
    * an ``[exports]`` turning the sections or the sectional loads off, which the
      additional post always computes and exports, or turning on a kind it never
      writes: the probe points, the per-panel force distribution, the solver's
      plots.

    Parameters
    ----------
    pproc : PprocSpec
        The additional pproc artifact, as the workspace resolved it.
    pproc_id : str
        Its id, for the message.
    where : str
        What names the row, for the message: ``matrix row POL 3207``.

    Raises
    ------
    CampaignConfigError
        Naming every refused table of the artifact in one message.
    """
    reasons: list[str] = []
    if pproc.surface_probes:
        reasons.append("[[surface_probes]]: surface histories require an unsteady march")
    if pproc.probes:
        reasons.append(
            "[[probes]]: probe points updated or created after reopening differ from the "
            "run's, up to 4 percent in speed (RPT-062)"
        )
    if pproc.volume_section is not None:
        reasons.append(
            "[volume_section]: a cut through the flow off the body, which a reopened file "
            "does not give back as the run left it (RPT-062)"
        )
    if pproc.plots != PlotsSpec():
        reasons.append("[plots]: a force or fluid plot fills during a march, and none runs")
    if pproc.time_averaging is not None:
        reasons.append(
            "[time_averaging]: a surface average is taken over the per-step exports of a "
            "march, and none runs"
        )
    if pproc.base_regions:
        reasons.append(
            "base_regions: a base region is marked on a mesh before its solve, and the "
            "saved simulation carries the marks it was saved with"
        )
    switched_off = [
        kind for kind in ("sections", "sectional_loads") if pproc.exports.get(kind) is False
    ]
    if switched_off:
        reasons.append(
            f"[exports] {' and '.join(f'{kind} = false' for kind in switched_off)}: the "
            "additional post always computes and exports the sections and their loads"
        )
    switched_on = [kind for kind in _NOT_EXTRACTED_KINDS if pproc.exports.get(kind)]
    if switched_on:
        reasons.append(
            f"[exports] {' and '.join(f'{kind} = true' for kind in switched_on)}: a kind the "
            "additional post never writes"
        )
    if not reasons:
        return
    raise CampaignConfigError(
        f"{where}: the additional pproc {pproc_id!r} asks for what a reopened saved "
        f"simulation does not give back: {'; '.join(reasons)}. The additional post opens "
        "the point's final .fsm with no solve and gives back the total loads, the surface "
        "solution, the surface sections and their sectional loads, new distributions "
        "included, and the plots history of an unsteady point (RPT-062). Name an "
        "additional pproc that asks for those, and leave the rest to the pproc the row "
        "runs with."
    )


def refuse_an_additional_post_build(version: str | FsVersion, *, where: str) -> None:
    """Refuse the additional post on a build RPT-062 did not measure it on.

    Parameters
    ----------
    version : str or FsVersion
        The build the row's script is emitted under.
    where : str
        What names the row or the case, for the message.

    Raises
    ------
    CampaignConfigError
        When ``version`` is not one of :data:`ADDITIONAL_POST_BUILDS`.
    """
    try:
        canonical = resolve(version).canonical
    except PyflightstreamError:
        canonical = str(version)
    if canonical in ADDITIONAL_POST_BUILDS:
        return
    raise CampaignConfigError(
        f"{where} states {ADDITIONAL_PPROC_VARIABLE} and runs on FlightStream {canonical}. "
        "The additional post reopens a saved simulation on "
        f"{', '.join(ADDITIONAL_POST_BUILDS)} only, the build RPT-062 measured what a "
        "reopened file gives back on; run the row on that build, or drop the key."
    )


def additional_outputs(pproc: PprocSpec, *, stem: str, unsteady: bool) -> tuple[str, ...]:
    """Return the files one extraction writes, relative to its own folder (G12).

    The loads table always; the surface exports the additional pproc's
    ``[exports]`` selects, by the rule :func:`~pyflightstream.cases.default_outputs`
    applies (Tecplot unless it says false, VTK and CSV where it says true), and
    the VTK a Tecplot is written from wherever the Tecplot is (G45); the
    surface sections and the sectional loads ALWAYS, because the reopened file
    stores the sections and not their loads, so the extraction computes them
    every time (RPT-062); the plots history on an unsteady point, which the file
    keeps; and the solver log unless ``[exports]`` turns it off. Never a saved
    simulation and never probe points: the extraction saves nothing and samples
    nothing off the body.

    Parameters
    ----------
    pproc : PprocSpec
        The additional pproc artifact.
    stem : str
        The point's stem, which every name of the run's own exports carries.
    unsteady : bool
        Whether the point's run type marches in time.

    Returns
    -------
    tuple of str
        The file names, in the order :data:`~pyflightstream.cases.EXPORT_KINDS`
        exports them.
    """
    suffix = {kind: suffix for kind, suffix, _, _ in EXPORT_KINDS}
    chosen = pproc.exports
    kinds = [
        "loads",
        *(
            kind
            for kind in ("tecplot", "vtk", "csv")
            if chosen.get(kind, kind not in OPT_IN_EXPORT_KINDS)
            or (kind == "vtk" and pproc.products.boundary_layer_integrals)
        ),
        "sections",
        "sectional_loads",
    ]
    if unsteady and chosen.get("plots", True):
        kinds.append("plots")
    if chosen.get("log", True):
        kinds.append("log")
    # G45: the Tecplot is written from a VTK, which the extraction exports and keeps.
    return tuple(with_tecplot_source([f"{stem}{suffix[kind]}" for kind in kinds]))


def frame_definitions(
    text: str, *, registry: CommandRegistry | None = None
) -> tuple[tuple[str, ...], ...]:
    """Return every command of a rendered script that defines or moves a frame, with its lines.

    One entry per command of the database whose name says it is about a
    coordinate system, in order: the ones that create, place, edit, turn,
    translate, rename, normalise, copy, mirror or delete a frame, and the ones
    that assign it (the set the frame ledger of
    :class:`~pyflightstream.script.Script` classifies command by command).
    Each entry is the command's line and every line after it up to a blank
    line, a comment or the next command of the database, stripped: an
    ``EDIT_COORDINATE_SYSTEM`` carries its ``FRAME``, ``NAME``, origin and
    three axis vectors, a ``ROTATE_COORDINATE_SYSTEM`` its frame, axis and
    angle.

    It is how a saved simulation's frames are compared with the frames a script
    built today would create (G12): two scripts whose definitions agree created
    the same frames at the same indices, with the same names, in the same place
    and orientation, and moved them alike afterwards. Index and name alone take
    a frame turned since the run under its old name for the one it was.

    Parameters
    ----------
    text : str
        A rendered script.
    registry : CommandRegistry, optional
        The command database whose names end a command's lines; the committed
        one by default.

    Returns
    -------
    tuple of tuple of str
        One tuple of lines per frame command, the command's own line first.
    """
    known = (registry or CommandRegistry.load()).commands
    lines = [line.strip() for line in text.splitlines()]
    found: list[tuple[str, ...]] = []
    at = 0
    while at < len(lines):
        head = lines[at].split(" ", 1)[0]
        at += 1
        if head not in known or "COORDINATE_SYSTEM" not in head:
            continue
        block = [lines[at - 1]]
        while (
            at < len(lines)
            and lines[at]
            and not lines[at].startswith("#")
            and lines[at].split(" ", 1)[0] not in known
        ):
            block.append(lines[at])
            at += 1
        found.append(tuple(block))
    return tuple(found)


def frames_of_the_run(
    case: SimCase, version: str | FsVersion, *, registry: CommandRegistry | None = None
) -> Script:
    """Build a point's own run script again, for what it says about the saved simulation.

    The script is never written or run. Its
    :attr:`~pyflightstream.script.Script.frames_by_name`, ``num_local_frames``,
    ``boundary_inventory`` and ``section_blocks`` describe the frames, the
    boundaries and the distributions the point's saved simulation holds,
    PROVIDED the run's recorded script created the same frames: the caller
    compares the two scripts' :func:`frame_definitions` before trusting it,
    because the row may have been edited since the run.

    A continuation creates no frame of its own, so a case stating ``RESTART`` is
    built without it and its two resolved facts: the script is then the one the
    chain's first run built, whose frames the saved state carries. The run
    already said every warning the build raises, so none is raised again.

    Parameters
    ----------
    case : SimCase
        The point's case, as the run built it: its point, its outputs and its
        staged geometry.
    version : str or FsVersion
        The build the run's script was emitted under.
    registry : CommandRegistry, optional
        Alternative command database, used by tests.

    Returns
    -------
    Script
        The built script.
    """
    stripped = {
        key: value
        for key, value in case.variables.items()
        if key not in (RESTART_VARIABLE, *RESERVED_CONTINUATION_VARIABLES)
    }
    shadow_case = (
        case
        if len(stripped) == len(case.variables)
        else case.model_copy(update={"variables": stripped})
    )
    script = Script(version, registry=registry)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(shadow_case, script, registry=registry)
    return script


#: The commands an extraction must never carry: a solve, a save, a new frame, a
#: probe or a plot of a march. Checked on the rendered text after the build, as
#: :func:`build_script` checks its march label, because a line here would spend
#: the seat on the thing the additional post exists not to do.
_NEVER_IN_AN_EXTRACTION: frozenset[str] = frozenset(
    {
        "START_SOLVER",
        "INITIALIZE_SOLVER",
        "SAVEAS",
        "SOLVER_SET_FARFIELD_LAYERS",
        "CREATE_NEW_COORDINATE_SYSTEM",
        "UPDATE_PROBE_POINTS",
        "EXPORT_PROBE_POINTS",
        "NEW_PROBE_LINE",
        "NEW_PROBE_POINT",
        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
    }
)


def build_additional_script(case: SimCase, script: Script, *, saved: str, shadow: Script) -> None:
    """Build the script that extracts an additional pproc from a point's saved simulation (G12).

    WHAT IT EMITS, in this order, and nothing else: ``OPEN`` of the saved
    simulation with no initialisation argument, which the emitter follows with
    the blank line ``OPEN`` needs to stop reading its arguments (RPT-062: without
    it the next command was read as an argument and the launch exported nothing);
    the additional pproc's section distributions, in the frames the run created;
    the loads frame and the moments model the run set; the loads selections of
    a steady point's setup; ``UPDATE_ALL_SURFACE_SECTIONS`` and
    ``COMPUTE_SURFACE_SECTIONAL_LOADS``, always, because the file stores the
    sections and not their loads; the exports :func:`additional_outputs` names;
    and ``CLOSE_FLIGHTSTREAM``.

    WHAT IT NEVER EMITS: ``START_SOLVER``, ``INITIALIZE_SOLVER``, ``SAVEAS``, a
    frame, a probe or a plot. The saved simulation already holds the frames,
    the boundaries and the solved state; the setup's raw commands and custom
    flags are not replayed, because the saved state carries what they set.

    Parameters
    ----------
    case : SimCase
        The point's case with ``pproc`` and ``pproc_id`` the ADDITIONAL
        artifact's and ``outputs`` from :func:`additional_outputs`.
    script : Script
        An empty script bound to one of :data:`ADDITIONAL_POST_BUILDS`.
    saved : str
        The path of the saved simulation to open, as the solver will read it.
    shadow : Script
        The point's own run script built again (:func:`frames_of_the_run`),
        whose frames and boundary inventory the saved simulation holds.

    Raises
    ------
    CampaignConfigError
        A build other than the one RPT-062 measured, an additional pproc asking
        what a reopened file does not give back, a shadow that created no frame
        map, or a distribution citing a frame the run did not create.
    WorkflowCoverageError
        An internal defect: the rendered text carries a command an extraction
        must never carry.
    """
    refuse_an_additional_post_build(script.version, where=f"case {case.sim_id!r}")
    if case.pproc is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the additional post was asked to build an extraction "
            "with no pproc artifact on the case; the additional pproc is what it extracts."
        )
    refuse_what_a_saved_point_cannot_give(
        case.pproc, pproc_id=str(case.pproc_id), where=f"case {case.sim_id!r}"
    )
    frames = shadow.frames_by_name
    if frames is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: its run script names no frames by name, which is a script "
            "no run type built; the additional post cites the frames of a saved simulation "
            "by the names its run type gave them, and a LEGACY recipe's are its own."
        )
    unsteady = case.recipe in _UNSTEADY_RECIPES
    _configuration_comment(case, script)
    script.emit("OPEN", saved)
    # THE FRAMES AND THE BOUNDARIES THE SAVED SIMULATION HOLDS, declared rather
    # than created, so every citation below resolves exactly as the run's did.
    script.declare_existing(frames=shadow.num_local_frames)
    if shadow.boundary_inventory is not None:
        _declare_inventory(case, script, shadow.boundary_inventory)
    _refuse_a_pproc_the_geometry_shares_no_name_with(case, script)
    _pproc_sections(case, script, frames)
    moment_frame = frames.get("MRP")
    _analysis(case, script, moment_frame if isinstance(moment_frame, int) else None)
    if not unsteady:
        _setup_link.loads_selections(case, script)
    _export_block(WorkflowConventions(outputs=tuple(case.outputs)), case, script, unsteady=unsteady)
    if case.pproc.products.boundary_layer_integrals:
        for block in script.section_blocks:
            block["loads_frame_index"] = script.loads_frame
    script.emit("CLOSE_FLIGHTSTREAM")
    # G45: THE LOADS FRAME IS THE RUN'S, placed by the run's own script: the
    # extraction declares the saved simulation's frames and places none, and the
    # shadow is that script built again, whose frames the drift check held equal.
    for translation in script.surface_translations:
        stated = translation["frame"]
        assert isinstance(stated, dict)
        placed = shadow.frame_placements.get(int(stated["frame"]))  # type: ignore[call-overload]
        if placed is not None and placed.origin is not None and placed.axes is not None:
            stated["origin"] = [float(value) for value in placed.origin]
            stated["axes"] = [[float(value) for value in axis] for axis in placed.axes]
    refuse_an_untranslatable_surface(case, script)
    carried = sorted(
        {line.split(" ", 1)[0] for line in script.render().splitlines()} & _NEVER_IN_AN_EXTRACTION
    )
    if carried:
        raise WorkflowCoverageError(
            f"internal defect: the extraction of case {case.sim_id!r} carries "
            f"{', '.join(carried)}, and an extraction opens a saved simulation and never "
            "solves, saves, creates a frame, a probe or a plot. Report it; nothing was run."
        )
