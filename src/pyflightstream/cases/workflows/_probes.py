"""Probes and the sampled volume: probe points, lines, profiles and their frames.

:func:`_pproc_probes` emits the probe tables a row declares (points,
rectangles, circles, a profile file), :func:`_pproc_surface_probes` the
surface probes, and :func:`_pproc_sampled_volume` the sampled volume; each
probe is placed in the frame it names. A new probe shape joins
:func:`_emit_one_probe_table`.
"""

from __future__ import annotations

import csv
import math
import re
import warnings
from collections.abc import (
    Callable,
)
from pathlib import (
    Path,
)

import numpy as np

from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    EXPANDING_FRAMES,
    CampaignConfigError,
    ProbesSpec,
    SimCase,
)
from pyflightstream.probes.layouts import circle_points, line_points, rectangle_points
from pyflightstream.script import (
    Script,
    helpers,
)

from ._clock import (
    unsteady_export_threshold,
)
from ._farfield import (
    declared_lattices,
    emit_declared_lattices,
    farfield_probes,
    needs_fresh_probes,
    planar_points,
    warn_declared_inside,
)
from ._frames import (
    _pproc_frame,
)
from ._names import (
    _artifact_of,
)
from ._rows import (
    _from_metres,
    _rotor_of,
    _the_rotor_a_flat_row_turns,
    _variable,
)
from ._vocabulary import (
    CLOCK_MOTION_VARIABLE,
    NORMAL_PROBE_BUILDS,
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    SIMULATION_LENGTH_UNIT,
    Frames,
)


def _pproc_surface_probes(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit surface-property histories with their own identity and coordinate contract."""
    pproc = case.pproc
    if pproc is None or not pproc.surface_probes:
        return
    allowed = (
        next(
            arg.values
            for arg in script.entry("NEW_UNSTEADY_SOLVER_SURFACE_PROBE").args
            if arg.name == "parameter"
        )
        or ()
    )
    unavailable = [
        probe.parameter for probe in pproc.surface_probes if probe.parameter not in allowed
    ]
    if unavailable:
        raise CampaignConfigError(
            f"surface_probes {', '.join(unavailable)} unavailable on FlightStream "
            f"{script.version.canonical}; select parameters supported by this build"
        )
    invalid = [
        probe.parameter for probe in pproc.surface_probes if probe.parameter.startswith("BL_")
    ]
    if invalid:
        raise CampaignConfigError(
            f"surface_probes {', '.join(invalid)} refused: native 26.124 build 8172026 "
            "returned CP_FREE for these BL requests; see RPT-083. "
            "No verified surface-history route exists for these parameters."
        )
    scale = _from_metres(case, script, "surface probe coordinates")
    script.surface_probe_layout.clear()
    for probe in pproc.surface_probes:
        frame = (
            1
            if probe.frame == "REFERENCE"
            else _pproc_frame(case, frames, probe.frame, f"surface probe {probe.name!r}")
        )
        coordinates = [float(value) * scale for value in probe.point_m]
        plot_name = f"SURFACE_{probe.name}"
        script.emit(
            "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
            name=plot_name,
            parameter=probe.parameter,
            csys=frame,
            x=coordinates[0],
            y=coordinates[1],
            z=coordinates[2],
        )
        script.surface_probe_layout.append(
            {
                "name": probe.name,
                "plot_name": plot_name,
                "parameter": probe.parameter,
                "frame": probe.frame,
                "frame_index": frame,
                "point_m": list(probe.point_m),
                "command_point": coordinates,
                "simulation_length_unit": script.simulation_length_unit,
                "coordinate_contract": "named-frame-native-length",
                "sampling_kind": "native-surface-property",
                "command": "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
            }
        )


def _warn_steady_parameter_list(
    case: SimCase, probes: ProbesSpec, entry_number: int, *, normal: bool
) -> None:
    """Warn that a steady entry lists parameters, which only enable it (B10)."""
    # B10: on a steady run the list enables the entry and filters nothing.
    # stacklevel=3 is the caller of `_pproc_probes`, as it was when this sat inline.
    warn(
        f"case {case.sim_id!r}: {_artifact_of(case)} [[probes]] entry {entry_number} "
        f"(frame {probes.frame!r}) lists parameters, but on "
        + ('a normal probe entry (kind = "normal") ' if normal else "a steady run ")
        + "this list only enables the entry; it does not filter the probe-points "
        "export's fixed set of variables. On an unsteady "
        + ("entry" if normal else "run")
        + " it selects the fluid-plot variables.",
        PyflightstreamWarning,
        stacklevel=3,
    )


def _refuse_unavailable_fluid_plot_parameters(
    case: SimCase, script: Script, probes: ProbesSpec
) -> None:
    """Refuse a fluid-plot parameter the run's build does not document (F05)."""
    # F05: a fluid plot's parameter must be one the run's build documents,
    # for a drawn entry and (F01) a cited profile alike.
    command = "UNSTEADY_SOLVER_NEW_FLUID_PLOT"
    entry = script.registry.for_version(script.version)[command]
    allowed = next(arg.values for arg in entry.args if arg.name == "parameter") or ()
    unsupported = [name for name in probes.parameters if name not in allowed]
    if unsupported:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: fluid plot parameter(s) {', '.join(unsupported)} "
            f"are not available for {command} on FlightStream "
            f"{script.version.canonical} ({entry.citation}). "
            f"The parameters for this build are: {', '.join(allowed)}."
        )


def _record_probe_field(
    case: SimCase,
    script: Script,
    frames: Frames,
    probes: ProbesSpec,
    entry_number: int,
    *,
    first_vertex: int,
    vertex: int,
    unsteady: bool,
    normal: bool,
) -> None:
    """Record the layout of the sampled probe field an entry declares (FR-418)."""
    resolved_frame = _the_probe_frame(case, probes.frame)
    frame_index = (
        1
        if resolved_frame == "REFERENCE"
        else _pproc_frame(case, frames, resolved_frame, "the sampled probe field")
    )
    if not unsteady:
        # THE POINTS THE SOLVER WAS GIVEN, in the reference frame its
        # steady probe commands take, as the sampled volume records
        # them: the layout declared reference coordinates and carried
        # the frame-local ones, and the positions file named the local
        # frame, which a continued field refuses.
        for at, point in enumerate(script.probe_points):
            if first_vertex <= point[0] <= vertex:
                x, y, z = _in_the_reference_frame(
                    case, script, frame_index, resolved_frame, list(point[1:4])
                )
                script.probe_points[at] = (point[0], x, y, z, "REFERENCE")
    script.probe_field_layout.append(
        {
            "entry": entry_number,
            "kind": "probe-field",
            "probe_ids": list(range(first_vertex, vertex + 1)),
            "frame": resolved_frame if unsteady else "REFERENCE",
            "frame_index": frame_index if unsteady else 1,
            "declared_frame": probes.frame,
            "coordinate_frame_index": frame_index if unsteady else 1,
            "command_coordinate_units": "m" if unsteady else script.simulation_length_unit,
            "coordinate_source": "emitted-local" if unsteady else "native-export-reference",
            "export_kind": "unsteady-fluid-plot" if unsteady else "steady-probe",
            "points_native": [
                list(point[1:4])
                for point in script.probe_points
                if first_vertex <= point[0] <= vertex
            ],
            "native_to_m": 1.0 / _from_metres(case, script, "probe field coordinates"),
            "formats": list(probes.field_formats),
            "reusable_inflow": probes.reusable_inflow,
            # FR-892: the product says which instant it holds.
            **({"sampled_at": "last-time-step"} if normal else {}),
        }
    )


def _pproc_probes(
    case: SimCase, script: Script, frames: Frames, *, unsteady: bool, analysis: bool
) -> None:
    """Emit every `[[probes]]` entry the artifact declares (FR-77, FR-81).

    All four builders create the declared probes. The export block selects
    `EXPORT_PROBE_POINTS` from the row's output names independently of run
    type, so steady and unsteady rows must both create the points they export.

    THE VERTEX COUNTER RUNS ACROSS THE ENTRIES (FR-77), because the plot name
    is `{parameter}{n}` and two entries restarting at 1 would write two plots to
    one name (the solver treating a repeated plot name as one plot is assumed, not
    measured in a committed report).

    NORMAL PROBES OF AN UNSTEADY ROW (FR-417) take the steady route: an
    unsteady row whose entries all state ``kind = "normal"`` places none of
    them in INIT and creates them in ANALYSIS, after the time march, with the
    commands and in the order a steady row uses; the export block then
    updates and exports them once.
    """
    pproc = case.pproc
    if pproc is None:
        return
    if pproc.surface_probes and not unsteady:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: [[surface_probes]] requires an unsteady march"
        )
    normal = unsteady and _normal_probes_of(case)
    if unsteady and not analysis:
        _pproc_surface_probes(case, script, frames)
    # F01: every declaration follows the run type, including cited profiles.
    # Unsteady fluid plots are placed in INIT; steady and normal probes in
    # ANALYSIS, after the solve or the time march.
    if analysis != (not unsteady or normal):
        return
    # FR-417: a normal entry is emitted exactly as a steady row's.
    unsteady = unsteady and not normal
    sampled = pproc.volume_section is not None or any(
        entry.field_formats or entry.reusable_inflow for entry in pproc.probes
    )
    # FR-455: a steady point whose far field lays probes starts from
    # none, as a sampled field does, so its export holds each point once.
    sampled = sampled or (not unsteady and needs_fresh_probes(case))
    declared: list[tuple[int, str, np.ndarray]] = []
    previous_layout = list(script.probe_field_layout)
    _open_the_probe_points(case, script, sampled=sampled, steady=not unsteady, normal=normal)
    # Number from the points that survive the opening, so a replaced survey restarts at 1.
    vertex = len(script.probe_points)
    for entry_number, probes in enumerate(pproc.probes, start=1):
        if not unsteady and probes.parameters:
            _warn_steady_parameter_list(case, probes, entry_number, normal=normal)
        if unsteady and probes.parameters:
            _refuse_unavailable_fluid_plot_parameters(case, script, probes)
        first_vertex = vertex + 1
        vertex = _emit_one_probe_table(case, script, frames, probes, vertex, unsteady=unsteady)
        declared.append(
            (
                entry_number,
                _the_probe_frame(case, probes.frame),
                np.array(
                    [p[1:4] for p in script.probe_points if first_vertex <= p[0] <= vertex],
                    dtype=float,
                ).reshape(-1, 3),
            )
        )
        if (probes.field_formats or probes.reusable_inflow) and vertex >= first_vertex:
            _record_probe_field(
                case,
                script,
                frames,
                probes,
                entry_number,
                first_vertex=first_vertex,
                vertex=vertex,
                unsteady=unsteady,
                normal=normal,
            )

    _pproc_sampled_volume(case, script, frames, vertex, unsteady=unsteady)
    # FR-455 and FR-1074: the far field's plane and lattice after
    # every declared point, then the inside-the-body check of the declared ones.
    farfield_probes(
        case,
        script,
        max((point[0] for point in script.probe_points), default=0),
        unsteady=unsteady,
        frames=frames,
    )
    warn_declared_inside(case, declared)
    if sampled and previous_layout and previous_layout != script.probe_field_layout:
        raise CampaignConfigError(
            "a steady job changed its sampled field layout between points; "
            "run these points separately to retain each field's placement"
        )


def _open_the_probe_points(
    case: SimCase, script: Script, *, sampled: bool, steady: bool, normal: bool
) -> None:
    """Delete and forget earlier probe points where this emission replaces them.

    A sampled field starts from no probe point. FR-890: so do the normal
    probes of a row with a per-step window, which the exports script of the
    window's first step already created; the creation after the march deletes
    them first, so the final export holds each point once.

    SO DOES EVERY STEADY CREATION. A steady sweep run as one script creates its
    probes after each point's solve, and a grouped job restates a point's
    creation into an instance that still holds the earlier point's: the points
    persist across solves, as the sections did (RPT-148), so each later export
    held every point once per earlier point, under vertex numbers that restarted
    at 1 in the positions file.
    """
    if sampled:
        if steady:
            script.emit("DELETE_PROBE_POINTS")
        script.probe_points.clear()
        script.probe_field_layout.clear()
    elif normal:
        if _has_a_per_step_window(case, script):
            script.emit("DELETE_PROBE_POINTS")
    elif steady and case.pproc is not None and case.pproc.probes:
        script.emit("DELETE_PROBE_POINTS")
        script.probe_points.clear()


def _has_a_per_step_window(case: SimCase, script: Script) -> bool:
    """Whether the row exports at every step of a window, stated or from [time_averaging].

    THE THRESHOLD ITSELF ANSWERS, not the stated keys: a ``[time_averaging]``
    window builds a per-step window with no key stated, and its exports update
    and export the normal probes at every step, so the first exporting step must
    create them, as it does for a stated key (FR-890).
    """
    return unsteady_export_threshold(case, version=script.version) is not None


def _refuse_unmeasured_normal_probes(case: SimCase, script: Script) -> None:
    """Enforce the measured version boundary before a normal-probe script is emitted."""
    if case.recipe not in ("unsteady", "unsteady_rotor") or case.pproc is None:
        return
    if any(entry.kind == "normal" for entry in case.pproc.probes):
        if script.version.canonical not in NORMAL_PROBE_BUILDS:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: normal probes of an unsteady run are verified only "
                f"on FlightStream {' and '.join(NORMAL_PROBE_BUILDS)}. Select one of those "
                "builds or use kind = 'unsteady' for the probe entries."
            )


def _normal_probes_of(case: SimCase) -> bool:
    """Whether an unsteady row samples its pproc's probes as normal probe points (FR-885).

    Every ``[[probes]]`` entry of one unsteady row is of one kind, an entry
    that states none counting as unsteady. The pproc's ``[volume_section]`` is
    sampled through fluid plots on an unsteady row, so it counts as an unsteady
    entry: a normal probes table and a fluid-plot history would write one
    ``probes/<point>_probes.csv``.

    Raises
    ------
    CampaignConfigError
        The pproc mixes the two kinds on this row, naming the entries of each.
    """
    pproc = case.pproc
    if pproc is None:
        return False
    try:
        return pproc.samples_normal_probes()
    except CampaignConfigError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} {error}"
        ) from error


#: FR-417: the commands that create the probe points of a normal entry.
_PROBE_POINT_COMMANDS = frozenset(
    {"DELETE_PROBE_POINTS", "NEW_PROBE_LINE", "NEW_PROBE_POINT", "PROBE_POINTS_IMPORT"}
)

#: One recorded emission: the command, its positional and its keyword arguments.
RecordedCommand = tuple[str, tuple[object, ...], dict[str, object]]


class _ProbePointRecorder:
    """Keep accepted post-march probe commands through Script's observation hook."""

    def __init__(self, script: Script) -> None:
        self.script = Script(script.version, registry=script.registry)
        self.recorded: list[RecordedCommand] = []
        self.recorded_text = ""
        self._marched = False

    def observe(
        self,
        name: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        text: str,
        from_line: bool,
    ) -> None:
        """Keep probe creation after START_SOLVER, excluding row setup lines."""
        if self._marched and not from_line and name in _PROBE_POINT_COMMANDS:
            self.recorded.append((name, args, kwargs))
            self.recorded_text += text
        self._marched = self._marched or name == "START_SOLVER"


def _built_from_the_mesh(
    case: SimCase, script: Script, build: Callable[[SimCase, Script], None]
) -> _ProbePointRecorder:
    """Build the row from the mesh on a scratch script that is never written (FR-889, FR-890).

    Raises
    ------
    CampaignConfigError
        The row cannot be built from the mesh, so where its normal probes are
        placed is unknown; the message names the entries and the remedy.
    """
    scratch = _ProbePointRecorder(script)
    from pyflightstream.cases.windows import RESTART_STEP_OFFSET_VARIABLE

    restart = {
        RESTART_VARIABLE,
        RESTART_FROM_VARIABLE,
        RESTART_ITERATIONS_VARIABLE,
        RESTART_STEP_OFFSET_VARIABLE,
    }
    variables = {key: value for key, value in case.variables.items() if key not in restart}
    try:
        with warnings.catch_warnings(), scratch.script.observe_commands(scratch.observe):
            warnings.simplefilter("ignore")
            build(case.model_copy(update={"variables": variables}), scratch.script)
    except PyflightstreamError as error:
        count = len(case.pproc.probes) if case.pproc is not None else 0
        entries = ", ".join(str(number) for number in range(1, count + 1))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: its pproc artifact {case.pproc_id!r} samples normal "
            f"probes (entries {entries}), which are created where the row's full script "
            f"places them, and that script cannot be built here ({error}). A continued "
            "march never created them. Run the row again from the mesh: name the point in "
            "force_rerun (CLI: --force-rerun) of run_matrix, as in "
            "pyfs-matrix run --force-rerun <point>."
        ) from error
    for name, payload in scratch.script.pending_input_files.items():
        if name in scratch.recorded_text:
            script.park_input_file(name, payload)
    return scratch


def _normal_probes_of_a_continuation(
    case: SimCase,
    script: Script,
    build: Callable[[SimCase, Script], None],
) -> list[RecordedCommand]:
    """Return the probe-point commands a continuation emits after its march (FR-889).

    A stopped march saved its state before the full script created its normal
    probes, so the continuation creates them after the continued march, with
    the commands and the order of the full script. Those depend on where the
    full script placed its frames, which a continuation does not emit (FR-396):
    the row is built from the mesh on a scratch script, which is never written,
    and its probe-point commands, positions and layout are taken from there.
    Empty for a row whose probes are not normal, which then emits as before.
    """
    if case.pproc is None or not _normal_probes_of(case):
        return []
    scratch = _built_from_the_mesh(case, script, build)
    script.probe_points[:] = scratch.script.probe_points
    script.probe_field_layout[:] = scratch.script.probe_field_layout
    script.farfield_layout[:] = scratch.script.farfield_layout
    return scratch.recorded


def _creation_of_normal_probes(
    case: SimCase, script: Script, build: Callable[[SimCase, Script], None]
) -> str:
    """Return the lines the first exporting step runs to create the normal probes (FR-890).

    ``DELETE_PROBE_POINTS`` and the creation commands of the post-march route,
    taken from the row built from the mesh on a scratch script; empty for a
    row whose probes are not normal or that states no per-step window.
    """
    if case.recipe not in ("unsteady", "unsteady_rotor"):
        return ""
    if case.pproc is None or not _normal_probes_of(case):
        return ""
    if not _has_a_per_step_window(case, script):
        return ""
    return _built_from_the_mesh(case, script, build).recorded_text


#: FR-91: the simulation subfolder for generated probe positions, per SIM
#: and not per point. A user-cited survey (FR-80) stays under workspace
#: inputs/profiles and is imported by the absolute path resolved by binding
#: (GOAL-021 item 2).
PROBE_PROFILE_DIR = "profiles"

#: FR-91: the ordered probe-position columns shared by the run writer and
#: post reader. cases is the deepest layer both readers import.
PROBE_POSITION_COLUMNS: tuple[str, ...] = ("PROBE", "X", "Y", "Z", "FRAME")

#: The first line of every probe positions file the run writer creates, above the
#: header: what tells the writer's own file from a user's file that carries the same
#: header. The readers skip it, and a file written before it existed has none.
PROBE_POSITIONS_MARKER = "# pyflightstream probe positions"


def _read_probe_profile(path: str, *, volume_only: bool = False) -> list[list[float]]:
    """Read the counted X,Y,Z,TYPE profile defined by PROBE_POINTS_IMPORT.

    Both surface (0) and volume (1) rows supply fixed vertices to unsteady
    fluid plots. The type does not change the fluid-plot sampling command.

    With ``volume_only`` (a steady row whose profile is scaled, transformed
    into the reference frame, or requested as a field and expanded into
    ``NEW_PROBE_POINT VOLUME``), a surface row is refused by
    number: a surface probe and a point in the flow are different
    observations, and expanding one as the other would sample the wrong
    quantity under the right coordinates.
    """
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if not rows or len(rows[0]) != 1:
            raise ValueError("the first line must contain the point count")
        count = int(rows[0][0])
        if count < 0 or len(rows) - 1 != count:
            blank = sum(1 for row in rows[1:] if not row)
            note = f" ({blank} of them blank lines; remove them)" if blank else ""
            raise ValueError(f"declares {count} points but contains {len(rows) - 1} rows{note}")
        points = []
        for number, row in enumerate(rows[1:], start=1):
            if len(row) != 4 or row[3].strip() not in ("0", "1"):
                raise ValueError(f"point {number} must be X,Y,Z,TYPE with TYPE 0 or 1")
            if volume_only and row[3].strip() == "0":
                raise ValueError(
                    f"point {number}: a surface TYPE 0 row cannot be expanded as a "
                    "volume probe; a steady row that scales or transforms a survey, "
                    "or requests a field, volume section or reusable inflow, expands "
                    "every cited point in the flow. Cite TYPE 1 rows for that route. "
                    "A TYPE 0 survey needs the native import: REFERENCE frame, scale "
                    "m, and no field request."
                )
            point = [float(value) for value in row[:3]]
            if not all(math.isfinite(value) for value in point):
                raise ValueError(f"point {number} has a non-finite coordinate")
            points.append(point)
        return points
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        raise CampaignConfigError(f"probe profile {path!r} cannot be read: {error}") from error


def _record_probe_line_frame(script: Script, points: list[list[float]], frame: str) -> None:
    """Retain declared coordinates after the helper records reference coordinates."""
    first = len(script.probe_points) - len(points)
    for offset, point in enumerate(points):
        script.probe_points[first + offset] = (
            first + offset + 1,
            float(point[0]),
            float(point[1]),
            float(point[2]),
            frame,
        )


def _emit_surveyed_probes(case, script, probes, vertex: int, *, unsteady: bool) -> int | None:
    """Emit the import of a cited survey, returning the vertex count after it.

    None where the entry is not one the solver imports whole, so the caller places
    its points itself.
    """
    if probes.points_file:
        from pyflightstream.probes import emit_probe_import

        # Import by the absolute path resolved at binding (GOAL-021 item 2).
        # Refuse an unresolved citation: the file is not staged into the submitted
        # point's working directory.
        if not probes.resolved_points_file:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: a probe entry cites the survey "
                f"{probes.points_file!r} and nothing resolved it to a file. A cited survey "
                "is resolved against the workspace's inputs/profiles/ when the row binds, so "
                "build this case through the workspace (plan_matrix or run_matrix)."
            )
        if (
            not unsteady
            and case.pproc.volume_section is None
            and not any(entry.field_formats or entry.reusable_inflow for entry in case.pproc.probes)
            # IN ROTOR RADII the file's numbers are not the positions, and the
            # import takes them as written: the lattice below scales them, as
            # the unsteady and the sampled routes do (FR-80).
            and probes.scale == "m"
            and probes.frame.strip().upper() == "REFERENCE"
        ):
            # A script that has established no unit (a saved geometry whose header
            # states none, no explicit setup key) is in the solver's default, the
            # metre (P0400-INTEGFIX-PROBE-UNITS).
            emit_probe_import(
                script,
                probes.resolved_points_file,
                units=script.simulation_length_unit or SIMULATION_LENGTH_UNIT,
            )
            # L4 (F-067, 26.124 and 26.125, namespace 63503b6a, F-067/analysis.json):
            # imported and drawn probes share ONE id space, the import rows first.
            # The survey's points advance the counter, so a probe drawn after it
            # is numbered after them and its recorded id is the solver's row.
            try:
                imported = _read_probe_profile(probes.resolved_points_file)
            except CampaignConfigError:
                # A survey not readable where the script is built (it is staged to the
                # solver machine) has no count to advance by; the import itself stands.
                imported = []
            for point in imported:
                vertex += 1
                script.probe_points.append(
                    (vertex, float(point[0]), float(point[1]), float(point[2]), "REFERENCE")
                )
            return vertex
    return None


def _emit_one_probe_table(case, script, frames, probes, vertex: int, *, unsteady: bool) -> int:
    """Emit one `[[probes]]` entry, returning the vertex count after it."""
    if not probes.parameters:
        return vertex
    imported_count = _emit_surveyed_probes(case, script, probes, vertex, unsteady=unsteady)
    if imported_count is not None:
        return imported_count
    if not (
        probes.points_file
        or probes.lines
        or probes.rectangles
        or probes.circles
        or probes.lattices
        or probes.grids
    ):
        return vertex
    probes = probes.model_copy(update={"frame": _the_probe_frame(case, probes.frame)})
    # A PROBE TABLE NAMES ONE ROTOR'S FRAME, and a row that does not turn
    # that rotor places it nowhere. The same rule the plots and the
    # sections already keep (FR-65): an entry this RUN cannot place is left
    # out, because one artifact serves a row that turns the pusher and a
    # row that turns only the lifters, and only one of them has a
    # PUSHER_SMRP. An entry naming a frame NO ROW could place is still
    # refused below, by `_pproc_frame`, because that cannot come right on
    # another row.
    if (
        EXPANDING_FRAMES.get(probes.frame.strip().upper()) is None
        and _ROTOR_FRAME_SPELLING.search(probes.frame.strip().upper()) is not None
        # ONLY A FRAME OF A ROTOR THE REFERENCE DECLARES, or of the unnamed default
        # rotor (ROTOR, ROTOR<k>), is left out; any other rotor-shaped name no
        # declared rotor owns is refused below by `_pproc_frame`.
        and (
            _the_rotor_whose_frame_this_is(case, probes.frame) is not None
            or _UNNAMED_ROTOR_FRAME.match(probes.frame.strip().upper()) is not None
        )
        and frames.get(probes.frame) is None
    ):
        warn(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} lays its probe "
            f"lines in {probes.frame!r}, a frame of a rotor this row does not turn, so "
            "they are left out. A row places the frames of the rotors its motions name, "
            "which is the same rule that lets one artifact serve a wing-body row and a "
            "rotor row.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return vertex
    frame = (
        1
        if probes.frame == "REFERENCE"
        else _pproc_frame(case, frames, probes.frame, "the probe lines")
    )
    scale = 1.0
    if probes.scale == "rotor_radius":
        scale = _the_radius_the_probe_lines_are_in(case, probes.frame) / 2.0
    # Both forms above are physical metres; the frame ledger and solver are
    # in native simulation units. Convert before placement and recording.
    native_per_m = _from_metres(case, script, "probe coordinates")
    scale *= native_per_m
    # RPT-083: fluid-plot VERTEX consumes metres even in a MILLIMETER
    # simulation. Keep the recorded local points in native units, then
    # convert only this command boundary back to SI. Steady probes differ.
    for line in probes.lines:
        for point in line_points(line.start, end=line.end, points=probes.points, scale=scale):
            vertex += 1
            # FR-91. RECORDED BY THE LOOP THAT PLACES IT, so the position a
            # reader is given is the position the solver was given. It is
            # recorded for BOTH run types: a steady export carries its own
            # X, Y and Z and still never names the frame they are in, and a
            # table of coordinates that does not say which frame is as
            # unplaceable as one carrying none.
            if unsteady:
                script.probe_points.append(
                    (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
                )
                for parameter in probes.parameters:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                        frame=frame,
                        parameter=parameter,
                        name=f"{parameter}{vertex}",
                        vertex=" ".join(str(value / native_per_m) for value in point),
                    )

    if not unsteady:
        # FR-81: a steady row creates the probe points it exports. Emit one
        # NEW_PROBE_LINE per declared line outside the per-line setup loop (B04),
        # using its point count and endpoints. Coordinate scaling matches the
        # unsteady vertices, so rotor_radius selects the same disk in both types.
        # NEW_PROBE_LINE takes no frame: transform endpoints into the reference
        # frame using the frame placed by this script (B30). The unsteady route
        # passes the frame to its command. The behavior of an unpaired probe
        # export is unmeasured; the package must emit the creation commands.
        ends = [
            _in_the_reference_frame(
                case, script, frame, probes.frame, [v * scale for v in line.start]
            )
            + _in_the_reference_frame(
                case, script, frame, probes.frame, [v * scale for v in line.end]
            )
            for line in probes.lines
        ]
        # THROUGH THE SCRIPT HELPER (PFS-2140.001): the public helper is what the
        # workspace runs, so the two cannot disagree on the command's grammar.
        for line, (first_x, first_y, first_z, last_x, last_y, last_z) in zip(
            probes.lines, ends, strict=True
        ):
            helpers.probe_line(
                script,
                points=probes.points,
                start=(first_x, first_y, first_z),
                end=(last_x, last_y, last_z),
            )
            # The helper records reference coordinates; workflow records retain
            # the declared local frame used by the field-layout join.
            _record_probe_line_frame(
                script,
                line_points(line.start, end=line.end, points=probes.points, scale=scale),
                probes.frame,
            )

    # FR-79: rectangles and circles are emitted point by point so one
    # declaration produces the same sampling on steady and unsteady paths.
    # Unsteady rows place vertices with fluid plots; steady rows use
    # NEW_PROBE_POINT, the per-vertex verb beside the survey line.
    lattice: list[list[float]] = []
    if probes.points_file:
        lattice += [
            [value * scale for value in point]
            for point in _read_probe_profile(probes.resolved_points_file, volume_only=not unsteady)
        ]
    for rectangle in probes.rectangles:
        lattice += rectangle_points(rectangle, scale=scale)
    for circle in probes.circles:
        lattice += circle_points(circle, scale=scale)
    lattice += planar_points(case, probes, native_per_m)
    # FR-1072: the survey lattices, laid by `probes`. A steady entry
    # in the reference frame has the probes home emit them too
    # (`emit_declared_lattices`), placed and rounded as recorded here; in
    # another frame each point is carried into the reference one.
    surveyed = declared_lattices(case, probes, native_per_m, unsteady=unsteady)
    by_probes = not unsteady and frame == 1 and bool(surveyed)
    for points, emit in ((lattice, True), (surveyed, not by_probes)):
        vertex = _lay_points(
            case,
            script,
            probes,
            points,
            vertex,
            frame=frame,
            unsteady=unsteady,
            native_per_m=native_per_m,
            emit=emit,
        )
    if by_probes:
        emit_declared_lattices(case, script, probes, native_per_m)
    return vertex


def _lay_points(
    case: SimCase,
    script: Script,
    probes: ProbesSpec,
    points: list[list[float]],
    vertex: int,
    *,
    frame: int,
    unsteady: bool,
    native_per_m: float,
    emit: bool = True,
) -> int:
    """Record and place an entry's points one vertex each; return the vertex count after them.

    ``emit`` False counts a steady point and leaves its creation and recording
    to the caller, which emits the declared lattices through the probes home.
    """
    for point in points:
        vertex += 1
        # FR-91, and the lattice reaches here for BOTH run types, so one
        # append covers a rectangle and a circle on either path.
        record = (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
        if unsteady:
            script.probe_points.append(record)
            for parameter in probes.parameters:
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=frame,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value / native_per_m) for value in point),
                )
        elif emit:
            # A fluid probe is a VOLUME point, matching helpers.probe_points and
            # survey-file TYPE 1 (G47). The command requires its type on every build.
            # It takes no frame, so transform the point into the reference frame as
            # for a steady line's endpoints (B30).
            x, y, z = _in_the_reference_frame(case, script, frame, probes.frame, list(point))
            helpers.probe_points(script, [(x, y, z)], kind="VOLUME")
            script.probe_points[-1] = record
    return vertex


def _in_the_reference_frame(
    case: SimCase, script: Script, frame: int, name: str, point: list[float]
) -> list[float]:
    """Carry a point stated in a pproc's frame into the reference frame, rounded as emitted.

    A steady row's probe commands, ``NEW_PROBE_LINE`` and ``NEW_PROBE_POINT``, take
    no frame: their coordinates are the reference frame's. A point declared in
    another frame is placed by where THIS SCRIPT put that frame (the ledger of
    :attr:`~pyflightstream.script.Script.frame_placements`), p = o + x ex + y ey + z ez;
    a frame whose placement the script does not follow is refused by name rather
    than guessed, because a probe placed from a stale origin samples the wrong
    point and is recorded at the right one.
    """
    if frame == 1:
        return [round(value, 5) for value in point]
    placement = script.frame_placements.get(frame)
    if placement is None or placement.origin is None or placement.axes is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} places probes in the "
            f"frame {name!r}, and this script does not follow where that frame stands, so a "
            "steady row, whose probe commands take reference-frame coordinates, cannot place "
            "them. State the probes in a frame the reference declares, or in the reference frame."
        )
    origin = placement.origin
    # UNIT AXES: the axes are normalised here. Without that, an x_axis of
    # length 2 in [[frames]] would double every probe's distance from the origin
    # on this route, while the unsteady route, which hands the solver the frame,
    # is assumed to place the same declaration at its stated distance (the
    # solver's reading of a non-unit axis is not measured in a committed report).
    axes = []
    for axis in placement.axes:
        length = math.sqrt(sum(float(value) ** 2 for value in axis))
        if length == 0.0:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} places probes in "
                f"the frame {name!r}, one of whose axes has zero length as the script placed "
                "it, so it points nowhere. Give the frame an x_axis and a y_axis that are not "
                "zero and not parallel."
            )
        axes.append([float(value) / length for value in axis])
    ex, ey, ez = axes
    for first, second in ((ex, ey), (ey, ez), (ex, ez)):
        if abs(sum(a * b for a, b in zip(first, second, strict=True))) > 1e-6:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} places probes in "
                f"the frame {name!r}, whose axes are not square to each other as the script "
                "placed it, so a point stated in it has no single position. Give the frame "
                "an x_axis and a y_axis at right angles."
            )
    return [
        round(origin[i] + point[0] * ex[i] + point[1] * ey[i] + point[2] * ez[i], 5)
        for i in range(3)
    ]


#: The rotor-frame name shape distinguishes a frame this run did not
#: create from an impossible frame name. Ownership is determined by
#: _the_rotor_whose_frame_this_is composing each rotor's names: a custom
#: frame may share a rotor prefix without belonging to that rotor.
_ROTOR_FRAME_SPELLING = re.compile(r"_(SMRP|RMRP\d*)$")

#: The frames of the unnamed default rotor, which no reference declares.
_UNNAMED_ROTOR_FRAME = re.compile(r"ROTOR\d*_(SMRP|RMRP\d*)$")


def _the_probe_frame(case: SimCase, stated: str) -> str:
    """Resolve an unstated probe frame to a rotor THIS ROW TURNS (FR-65).

    The default hub depends on the rotors this row turns, so it is resolved
    here when the artifact states no frame.

    The rotors a row TURNS are the ones its motions name, and the clock
    identifies which rotor supplies the default hub. The reference alone
    cannot choose among several rotors.

    Raises
    ------
    CampaignConfigError
        The row turns several rotors and the artifact states no frame, so
        which of them the lines are laid out in is unanswered. Naming the
        candidates is the useful half of the refusal.
    """
    if stated.strip():
        return stated.strip()
    moved = (_rotor_of(case, record) for record in case.motions)
    turning = [block.alias for block in moved if block is not None]
    if not turning:
        block = _the_rotor_a_flat_row_turns(case)
        if block is not None:
            return f"{block.alias}_SMRP"
        # A ROW THAT TURNS NOTHING lays its lines in the moment frame, which
        # is where an unstated frame put them on a rotorless run before this
        # release too.
        if not case.rotors:
            return "MRP"
        declared = ", ".join(sorted(case.rotors))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} states no frame "
            f"for its probe lines, and the reference declares more than one rotor "
            f"({declared}) while the row moves none of them, so there is no hub to lay "
            "them out about. Write the frame, as <ALIAS>_SMRP."
        )
    if len(set(turning)) == 1:
        return f"{turning[0]}_SMRP"
    # THE CLOCK ALREADY NAMES THE ROTOR THE ROW IS ABOUT, so a row that
    # states it has answered this question too.
    clock = str(_variable(case, CLOCK_MOTION_VARIABLE) or "").strip()
    for alias in turning:
        if alias.casefold() == clock.casefold():
            return f"{alias}_SMRP"
    raise CampaignConfigError(
        f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} states no frame for "
        f"its probe lines and this row turns {', '.join(sorted(set(turning)))}, so which "
        "rotor's disk they are laid out over is unanswered. Write the frame in the "
        "artifact, as <ALIAS>_SMRP; an unstated frame is only an answer where one rotor "
        "turns."
    )


def _the_rotor_whose_frame_this_is(case: SimCase, frame: str) -> str | None:
    """Return the alias of the rotor that OWNS ``frame``, or None (FR-62, FR-65).

    COMPOSED FORWARD, never parsed backward. A rotor's frames are exactly
    ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` and ``<ALIAS>_RMRP<k>``, so the
    question is answered by building those names and comparing, which is
    what `_frames_the_alias_owns` does one layer up.

    Compose the rotor's frame names rather than splitting the supplied
    name: a custom frame such as `PUSHER_TIP` may share a rotor prefix
    without belonging to that rotor (FR-72). Its probes must not inherit
    that rotor's disk scale.
    """
    wanted = frame.strip().casefold()
    for alias, block in case.rotors.items():
        owned = {f"{alias}_SMRP".casefold(), f"{alias}_RMRP".casefold()}
        owned |= {
            f"{alias}_RMRP{number}".casefold()
            for number in range(1, len(block.families_blades) + 1)
        }
        if wanted in owned:
            return alias
    return None


def _the_radius_the_probe_lines_are_in(case: SimCase, frame: str) -> float:
    """Return the diameter a probe table's ``rotor_radius`` is measured against (FR-65).

    THE ROTOR THE LINES ARE LAID OUT ON, which is the one whose frame the
    table names: the nine lines cross the disk of the rotor they are
    measured in, so `frame = "PUSHER_SMRP"` means pusher radii. The reference
    states a diameter PER ROTOR (FR-60): one number for the whole
    configuration cannot be right for a 1.20 m lifter and a 1.80 m pusher
    at once, and reading the configuration's would have laid the reference lifter
    probes out over the pusher's disk without saying so.

    A frame that is not a rotor's falls back to the reference's own
    rotor diameter, which is what every artifact written before this
    release meant and what keeps them reading.
    """
    alias = _the_rotor_whose_frame_this_is(case, frame)
    if alias is not None:
        return case.rotors[alias].diameter_m
    diameter = None if case.reference is None else case.reference.rotor_diameter
    if diameter is None:
        declared = ", ".join(sorted(case.rotors)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} lays its probe "
            f"lines out in rotor radii and names the frame {frame!r}, which is not a "
            f"rotor's, so there is no rotor to take a radius from. The rotors the "
            f"reference declares are {declared}, and each carries its own diameter_m; "
            f"name one of their frames (<ALIAS>_SMRP), or state a rotor diameter on "
            'the reference, or write the lines in metres (scale = "m").'
        )
    return diameter


def _pproc_sampled_volume(case, script, frames, vertex: int, *, unsteady: bool) -> None:
    """Sample a declared volume plane without using the FSM's section indices."""
    section = case.pproc.volume_section
    if section is None:
        return
    factor = _from_metres(case, script, "sampled volume section coordinates")
    frame = (
        1
        if section.frame == "REFERENCE"
        else _pproc_frame(case, frames, section.frame, "the volume section sampled through probes")
    )
    if section.shape == "rectangle":
        count_u, count_v = section.points or (25, 25)
        count_u = (count_u - 1) * 2 ** (section.refinement_layers - 1) + 1
        count_v = (count_v - 1) * 2 ** (section.refinement_layers - 1) + 1
        u0, v0, u1, v1 = section.corners_m
        pairs = [
            (u0 + (u1 - u0) * i / (count_u - 1), v0 + (v1 - v0) * j / (count_v - 1))
            for i in range(count_u)
            for j in range(count_v)
        ]
    else:
        radial, azimuth = section.points
        inner, outer = section.radii_m
        pairs = []
        for i in range(radial):
            radius = inner + (outer - inner) * i / (radial - 1)
            if radius == 0:
                pairs.append((0.0, 0.0))
            else:
                pairs.extend(
                    (
                        radius * math.cos(2 * math.pi * j / azimuth),
                        radius * math.sin(2 * math.pi * j / azimuth),
                    )
                    for j in range(azimuth)
                )
    first = vertex + 1
    label = section.frame if unsteady else "REFERENCE"
    for u, v in pairs:
        offset = section.offset_m
        local = {"XY": [u, v, offset], "XZ": [u, offset, v], "YZ": [offset, u, v]}[section.plane]
        native = [value * factor for value in local]
        point = (
            native
            if unsteady
            else _in_the_reference_frame(case, script, frame, section.frame, native)
        )
        vertex += 1
        if unsteady:
            script.probe_points.append((vertex, *map(float, point), label))
            for parameter in ("VX", "VY", "VZ"):
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=frame,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value / factor) for value in point),
                )
        else:
            helpers.probe_points(script, [(point[0], point[1], point[2])], kind="VOLUME")
    script.probe_field_layout.append(
        {
            "entry": len(case.pproc.probes) + 1,
            "kind": "volume-section",
            "probe_ids": list(range(first, vertex + 1)),
            "frame": label,
            "frame_index": frame if unsteady else 1,
            "coordinate_frame_index": frame if unsteady else 1,
            "command_coordinate_units": "m" if unsteady else script.simulation_length_unit,
            "coordinate_source": "emitted-local" if unsteady else "native-export-reference",
            "export_kind": "unsteady-fluid-plot" if unsteady else "steady-probe",
            "points_native": [
                list(point[1:4]) for point in script.probe_points if first <= point[0] <= vertex
            ],
            "native_to_m": 1.0 / factor,
            "formats": [section.format],
            "reusable_inflow": False,
            "declared_frame": section.frame,
            "declared_plane": section.plane,
            "shape": section.shape,
        }
    )
