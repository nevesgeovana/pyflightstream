"""The exports a run writes: surface and volume exports, the log, the update cadence.

:func:`_export_block` emits the export commands of a row, by kind;
:func:`_export_log` the solver log; :func:`with_tecplot_source` and its
siblings say where a Tecplot export reads from. A new export kind joins the
kinds of :mod:`pyflightstream.cases` and is emitted by
:func:`_surface_export` or :func:`_export_block`.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import (
    PurePath,
)

from pyflightstream.cases import (
    EXPORT_KINDS,
    PLOT_TYPES,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    CampaignConfigError,
    SimCase,
    classify_outputs,
)
from pyflightstream.cases import (
    windows as _windows,
)
from pyflightstream.script import (
    Script,
    helpers,
)
from pyflightstream.script._surface_averaging import (
    SurfaceAverageWindow,
)

from ._conventions import (
    WorkflowConventions,
)
from ._freestream import (
    _log_position_shape,
)
from ._reductions import (
    reduction_windows,
)
from ._rows import (
    _variable,
)
from ._vocabulary import (
    _UNSTEADY_RECIPES,
    EXPORT_LOG_VARIABLE,
    LOG_OUTPUT_VARIABLE,
    _refuse_retired_window_keys,
    read_a_choice,
)


def surface_time_averaging(case: SimCase) -> SurfaceAverageWindow | None:
    """Resolve the pproc's surface window on the same clock as LAST_REVS_AVG.

    Since 0.28.0 (G25) it is the window the PACKAGE averages the per-step surface
    exports over: its first step is where the per-step exports begin, and the
    post averages every step of it. None where the pproc states no
    ``[time_averaging]``.
    """
    stated = case.pproc.time_averaging if case.pproc is not None else None
    if stated is None:
        return None
    _refuse_retired_window_keys(case)
    if case.recipe not in _UNSTEADY_RECIPES:
        raise CampaignConfigError("[time_averaging] requires an unsteady run")
    plan = reduction_windows(case)
    assert plan is not None
    last = plan.get("time_iterations")
    clock = plan.get("steps_per_revolution")
    if not isinstance(last, int):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: surface time averaging has no valid run clock"
        )
    try:
        return _windows.surface_average_window(
            last_step=last,
            per_revolution=float(clock) if isinstance(clock, int | float) else None,
            last_revs=stated.last_revs,
            last_iters=stated.last_iters,
        )
    except ValueError as error:
        raise CampaignConfigError(f"case {case.sim_id!r}: {error}") from error


def tecplot_source(tecplot: str, kinds: Mapping[str, str]) -> str:
    """Return the VTK a point's Tecplot surface is written from (G45 of 0.28.0).

    ONE VTK EXPORT PER POINT FEEDS BOTH: where the outputs name a VTK, the
    Tecplot is written from that very file; otherwise the script exports one
    under the Tecplot's own name with the ``.vtk`` extension.

    Examples
    --------
    >>> tecplot_source("P1-AL+000.dat", {"tecplot": "P1-AL+000.dat"})
    'P1-AL+000.vtk'
    >>> tecplot_source("P1-AL+000.dat", {"tecplot": "P1-AL+000.dat", "vtk": "field.vtk"})
    'field.vtk'
    """
    declared = kinds.get("vtk")
    if declared is not None:
        return declared
    return PurePath(tecplot).with_suffix(".vtk").as_posix()


def native_tecplot_source(tecplot: str) -> str:
    """Name the retained native nodal source for a package-written surface (G53)."""
    path = PurePath(tecplot)
    return path.with_name(path.stem + "_native_tecplot.dat").as_posix()


def carries_singularity_strength(case: SimCase) -> bool:
    """Say whether the row's pproc asks its Tecplot surface to carry the strength (SS1).

    ``singularity_strength = true`` in the pproc artifact the row names; absent,
    false, or no pproc at all, the script exports no native Tecplot and the
    translated surface declares ``Singularity_strength`` not carried.
    """
    return case.pproc is not None and case.pproc.singularity_strength


def with_tecplot_source(outputs: Sequence[str], *, singularity_strength: bool = False) -> list[str]:
    """Include the sources of the translated surface in run output accounting.

    The VTK supplies panel values and is always a source. The native Tecplot
    supplies nodal strength and is one only where ``singularity_strength``
    says the row's pproc asks for it (SS1 of 0.30.0): a point is never
    incomplete for a native file it was never asked to write. The sources are
    waited for, filed and hashed, including at each exported step. Calling
    this on an already expanded output list is idempotent.
    """
    names = [str(name) for name in outputs]
    kinds = classify_outputs(names)
    tecplot = kinds.get("tecplot")
    if tecplot is None:
        return names
    at = names.index(tecplot) + 1
    dependencies = [tecplot_source(tecplot, kinds)]
    if singularity_strength:
        dependencies.append(native_tecplot_source(tecplot))
    missing = [name for name in dependencies if name not in names]
    return [*names[:at], *missing, *names[at:]]


def _export_surface_vtk(script: Script, case: SimCase, name: str) -> None:
    """Export the surface VTK, the variables the pproc selects, never the wake.

    Without ``vtk_variables`` the all-variables form, ``-1 DISABLE``: with no
    selection at all the solver also writes a ``<name>_wakes.vtk`` (RPT-074).
    """
    variables = case.pproc.vtk_variables if case.pproc is not None else None
    helpers.export_results(script, vtk=name, vtk_variables=variables or "all")


def _surface_export(
    script: Script,
    case: SimCase,
    kind: str,
    name: str,
    *,
    kinds: Mapping[str, str] | None = None,
) -> bool:
    """Emit the kinds whose export is more than ``<verb>`` and a name, validated on the build.

    The surface formats and the force distribution carry a payload. A solver
    plot is two commands: its
    ``SET_PLOT_TYPE`` first, because ``SAVE_PLOT_TO_FILE`` saves whichever plot
    is showing, then the save with the path on the line after it (RPT-067).
    False for every other kind, which the caller emits as ``<verb>`` and a name.

    The package writes the requested Tecplot from VTK panel values and, where
    the row's pproc sets ``singularity_strength = true``, native nodal strength
    (G53, SS1 of 0.30.0). Only then is the separate native export emitted, and
    it is retained as provenance. ``kinds`` contains every public export, by
    kind.
    """
    if kind in PLOT_TYPES:
        script.emit("SET_PLOT_TYPE", PLOT_TYPES[kind])
        script.emit("SAVE_PLOT_TO_FILE", name)
    elif kind == "force_distributions":
        # Every surface: the command takes a count, and -1 is all of them.
        helpers.export_results(script, force_distributions=name)
    elif kind == "tecplot":
        stated = dict(kinds or {kind: name})
        if "vtk" not in stated:
            _export_surface_vtk(script, case, tecplot_source(name, stated))
        if carries_singularity_strength(case):
            helpers.export_results(script, tecplot=native_tecplot_source(name))
    elif kind == "vtk":
        _export_surface_vtk(script, case, name)
    elif kind == "csv":
        verb = "EXPORT_SOLVER_ANALYSIS_CSV"
        args: list[object] = [name, "CP-FREESTREAM", "PASCALS"]
        if any(arg.name == "frame" for arg in script.entry(verb).args):
            args.append(1)
        script.emit(verb, *args, -1)
    elif kind in VOLUME_SECTION_KINDS.values():
        # G05. An export of a section nobody cut is an export of nothing, which
        # a declared output then reports as missing on a seat; refused here. The
        # index is the pproc's own section's, never a section a raw line cut.
        own = script.volume_section_index
        if own is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares the volume-section output {name!r} and its "
                "script cuts no volume section of its pproc, or a raw line deleted the one "
                "it cut: the section is declared by the pproc's [volume_section] table on a "
                "steady row, which also names the output"
            )
        verb = next(verb for each, _, verb, _ in EXPORT_KINDS if each == kind)
        script.emit(verb, own, name)
    else:
        return False
    return True


def _declared_export_kinds(
    conventions: WorkflowConventions, case: SimCase, *, unsteady: bool
) -> tuple[list[str], dict[str, str]]:
    """Return the row's output names and the export kind each one carries."""
    names = list(conventions.outputs or case.outputs)
    kinds = classify_outputs(names)
    if unsteady:
        for kind in STEADY_ONLY_EXPORT_KINDS:
            kinds.pop(kind, None)
    return names, kinds


def _export_updates(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    *,
    unsteady: bool,
    sections_updated: bool = False,
) -> None:
    """Emit the updates the row's exports read, which precede every export.

    UPDATE_ALL_SURFACE_SECTIONS and COMPUTE_SURFACE_SECTIONAL_LOADS whenever a
    section, sectional-loads, probe or section Cp export is asked for, unless
    ``sections_updated`` says the caller already emitted both (the
    post-processing script of a steady coupled row, which updates them for
    the loads the structural program reads); UPDATE_PROBE_POINTS when the
    probe points are exported. Each is an analysis command, so each must come
    before the first export.
    """
    _, kinds = _declared_export_kinds(conventions, case, unsteady=unsteady)
    if not any(kind in kinds for kind in _UPDATED_KINDS):
        return
    if not sections_updated:
        script.emit("UPDATE_ALL_SURFACE_SECTIONS")
        script.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
    # F01: only a row that still exports probe points updates them; an
    # unsteady row samples its probes through fluid plots and has none.
    if "probes" in kinds:
        script.emit("UPDATE_PROBE_POINTS")


def _export_block(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    *,
    unsteady: bool,
    updated: bool = False,
) -> None:
    """Export what the study needs, in the order, with the updates first.

    PFS-2029.14.01 and PFS-2029.18. The names come from the row's outputs
    (rendered by the workspace) and each is paired with its verb by suffix,
    so a row that declares the full set of FR-51 gets every kind and a row
    written before this release, declaring a loads table and a log, gets
    exactly what it declared. UPDATE_ALL_SURFACE_SECTIONS,
    COMPUTE_SURFACE_SECTIONAL_LOADS and UPDATE_PROBE_POINTS precede the
    exports whenever a section, sectional-loads or probe export is asked
    for, because an export of sections nobody updated is an export of the
    previous state (the reference driver, flightstreamHorse.py:522-526). The saved
    simulation comes first among the exports, as the reference did, and a build on
    which a kind carries no row is refused by the script layer naming the
    command, which is what require_coverage already checks per workflow.

    The solver log keeps its older spelling: a row that still says which
    of its outputs is the log through LOG_OUTPUT is honoured by
    :func:`_export_log`; a row whose outputs carry a ``_log.txt`` name is
    read by suffix like every other kind.

    ``updated`` says the caller already emitted the updates
    (:func:`_export_updates`), before an export of its own: then this block
    exports only, because an update after an export is refused by the phase
    order.
    """
    names, kinds = _declared_export_kinds(conventions, case, unsteady=unsteady)
    if "loads" not in kinds:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares outputs {names or 'nothing'} and none of them "
            "is a loads table (a name ending in .txt that is not one of the other "
            "export suffixes). The loads table is the export this package judges a run "
            "by, so every row leaves one; the default outputs name it {point}.txt."
        )
    if not updated:
        _export_updates(conventions, case, script, unsteady=unsteady)
    declared_log = _variable(case, LOG_OUTPUT_VARIABLE) is not None
    # A FILE-ROUTE ROW DECLARES ITS LOG (G02). The run holds a trailing-edge
    # import to the count the solver logs as imported, keyed to the SCRIPT as
    # the run layer keys it, and the solver writes a log of its own only when
    # it ends abnormally: without the exported one the check has nothing to
    # read and the point is recorded FAILED_INCOMPLETE_OUTPUT after the solve.
    if script.wake_edge_points is not None and "log" not in kinds and not declared_log:
        raise CampaignConfigError(
            f"case {case.sim_id!r} imports its trailing edges from a file, and its outputs "
            f"({', '.join(names)}) carry no solver log, a name ending in _log.txt. The run "
            "compares the count of trailing edges the solver logs as imported with the "
            "points it wrote, because a point that matches no edge marks nothing and the "
            "solver says nothing about it; the solver writes a log of its own only when it "
            "ends abnormally, so without the exported one the count cannot be read and the "
            "point would be recorded FAILED_INCOMPLETE_OUTPUT after the solve. Declare the "
            "log among the row's outputs, or leave the pproc artifact's [exports] log on."
        )
    # ASKED ONCE, FOR BOTH ROUTES TO THE LOG (0.24.0). The machine's
    # `export_log = false` was read inside `_export_log` alone, the route of a
    # row that names its log through LOG_OUTPUT. A row whose outputs carry a
    # `_log.txt` name is exported by suffix in the loop below, which asked
    # nothing, and that is the route every matrix row takes by default: the
    # command the profile exists to remove reached the one machine that aborts
    # at it, after the queue wait.
    exports_its_log = _exports_its_log(case)
    for kind, _, verb, only_unsteady in EXPORT_KINDS:
        if kind not in kinds or (only_unsteady and not unsteady):
            continue
        if kind == "log" and (declared_log or not exports_its_log):
            continue
        if not _surface_export(script, case, kind, kinds[kind], kinds=kinds):
            script.emit(verb, kinds[kind])
    if "tecplot" in kinds:
        # G45: WHAT THE RUN WRITES FROM THE VTK, and the frame the VTK is in, as
        # this script placed it at the moment of the export.
        script.surface_translations.append(
            {
                "vtk": tecplot_source(kinds["tecplot"], kinds),
                "dat": kinds["tecplot"],
                # SS1 of 0.30.0: named only where the pproc asks for the
                # strength, so a row without it translates as a record with no
                # native source always has: every VTK variable, the strength
                # declared not carried.
                **(
                    {"native_tecplot": native_tecplot_source(kinds["tecplot"])}
                    if carries_singularity_strength(case)
                    else {}
                ),
                "frame": script.loads_frame_record(),
                # 0.30.0: a periodic row's native Tecplot holds one zone per
                # copy, and the translation reads it by this count. Stated only
                # for such a row, so every other record is unchanged.
                **(
                    {"periodic_copies": script.periodic_copies}
                    if script.periodic_copies is not None
                    else {}
                ),
            }
        )
    if declared_log:
        _export_log(conventions, case, script, claimed=(names.index(kinds["loads"]) + 1,))


#: The kinds whose export reads the surface sections, the sectional loads or
#: the probe points, so the three updates precede the exports when any is
#: declared. The section Cp plot is one: it plots the sections, and a point
#: whose pproc switched every other section export off still updates them.
_UPDATED_KINDS: tuple[str, ...] = ("sections", "sectional_loads", "probes", "plot_sections_cp")


def _exports_its_log(case: SimCase) -> bool:
    """Say whether the SCRIPT writes the solver log for this run.

    THROUGH `read_a_choice`, which is the one place both readers ask and which
    REFUSES a word it does not know. The first writing carried a word list of
    its own and read anything outside it as True, so `EXPORT_LOG: flase` would
    have put the command back into the script on the one machine that aborts at
    it, after the queue wait (the architecture lens, 2026-09-16).
    """
    stated = _variable(case, EXPORT_LOG_VARIABLE)
    if stated is None:
        return True
    try:
        return read_a_choice(stated, context=f"{EXPORT_LOG_VARIABLE} of case {case.sim_id!r}")
    except ValueError as error:
        raise CampaignConfigError(str(error)) from None


def _export_log(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    *,
    claimed: tuple[int, ...],
) -> None:
    """Export the solver log where the row says WHICH of its outputs is one.

    NOT WHERE THE MACHINE WRITES ITS OWN. Some clusters abort at EXPORT_LOG;
    their profile states ``export_log = false`` and names the log the scheduler
    writes instead, and `collect` copies that file to this name. The row still
    DECLARES the log among its outputs, because the point is judged by it and
    collected with it: what changes is only who writes it.

    WHY A ROTOR ROW WANTS ONE. Without a log this package cannot judge
    convergence of an unsteady run at all: the time loop always reaches
    its prescribed end, so the iteration counter says nothing, and every
    such run is recorded COMPLETED_MAX_ITER whether it converged at
    every time step or at none. That word is a statement about the
    evidence and it reads as a statement about the solver. One more
    export line turns it into a real verdict.

    WHY AN INDEX, which is the less pretty of the two spellings and the
    only correct one. Two earlier spellings were wrong, and both are
    recorded here as DEVELOPMENT RECOLLECTION rather than as evidence:
    neither left a committed artifact, so nothing in this tree can be
    read to confirm them. What IS committed is the pair of tests each
    one now has, and those are the falsifiable half.

    The first read ``outputs[1]``, so a row whose second output is a
    force-distribution export would have had a solver log written over
    that name. A second declared output means "a second file this row
    expects", never "a log".

    The second took the name as the row WRITES it in OUTPUTS, and the
    names have been RENDERED by the time a builder sees them: the cell
    says ``loads_{point}.txt`` and the case carries
    ``loads_a+00.0.txt``, so the comparison could never match.

    An index is the one thing that survives rendering, because rendering
    preserves order. It is 1-BASED, matching how the cell is read left
    to right rather than how a list is subscripted.

    ``claimed`` is the set of 1-based positions the calling builder has
    already exported something else to, and naming one of them is
    REFUSED. Position 1 is the loads spreadsheet in both builders, and
    it is the most likely typo of someone who has just read "counted
    from 1"; without this the solver writes the log over the loads
    table, the run completes, and the assessor sends the user to look
    for a truncated export instead of at the cell they typed.
    """
    declared = _variable(case, LOG_OUTPUT_VARIABLE)
    if declared is None:
        return
    names = conventions.outputs or tuple(case.outputs)
    text = str(declared).strip()
    try:
        position = int(text)
    except ValueError:
        # THE TWO WRONG SHAPES GET DIFFERENT MESSAGES. `2.0` is not a
        # name, and telling its writer why a NAME cannot be used here
        # answers a question they did not ask.
        why = {
            "name": (
                "A name cannot be used here: the output names carry the point "
                "placeholder in the cell and reach a builder already RENDERED, so the "
                "cell's spelling and the case's never match."
            ),
            "decimal": (
                "It is a whole number of files and not a measurement, so it takes no decimal point."
            ),
            "neither": "That is not a whole number.",
        }[_log_position_shape(text)]
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {LOG_OUTPUT_VARIABLE} as {declared!r}, and "
            "it is the POSITION of the solver log among the row's own OUTPUTS, counted "
            f"from 1. {why} {LOG_OUTPUT_VARIABLE}: 2 says 'the second file this row "
            "declares'."
        ) from None
    if not 1 <= position <= len(names):
        raise CampaignConfigError(
            f"case {case.sim_id!r} names output {position} as its solver log and "
            f"declares {len(names)}: {', '.join(names) or 'nothing'}. The log is "
            "declared in OUTPUTS like every other file the row produces, so that it is "
            f"collected, and {LOG_OUTPUT_VARIABLE} says which one it is."
        )
    if not _exports_its_log(case):
        return
    if position in claimed:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names output {position} as its solver log and this "
            f"run type already exports {names[position - 1]!r} there. The solver would "
            "write the log over that file, the run would complete, and the export that "
            "was overwritten is the one this package judges the run by. Declare the log "
            f"as its own entry in OUTPUTS and point {LOG_OUTPUT_VARIABLE} at it."
        )
    script.emit("EXPORT_LOG", names[position - 1])
