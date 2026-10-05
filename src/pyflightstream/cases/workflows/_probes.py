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

from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    EXPANDING_FRAMES,
    CampaignConfigError,
    SimCase,
)
from pyflightstream.script import (
    Script,
)

from ._export_first_step import (
    stated_threshold_keys,
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
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    Frames,
)


def _pproc_surface_probes(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit surface-property histories with their own identity and coordinate contract."""
    pproc = case.pproc
    if pproc is None or not pproc.surface_probes:
        return
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


def _pproc_probes(
    case: SimCase, script: Script, frames: Frames, *, unsteady: bool, analysis: bool
) -> None:
    """Emit every `[[probes]]` entry the artifact declares (FR-77, FR-81).

    CALLED BY ALL FOUR BUILDERS, which is the fix. This lived inside
    `_pproc_plots` until 0.16.0, and `_pproc_plots` is called by the three
    UNSTEADY builders alone, so a steady row never reached the probes code at
    all. Meanwhile the export block emitted `EXPORT_PROBE_POINTS` off the row's
    OUTPUT NAMES, which know nothing about run type. Two halves that never
    agreed to be in the same place, and the reader got an export of points
    nobody made.

    THE VERTEX COUNTER RUNS ACROSS THE ENTRIES (FR-77), because the plot name
    is `{parameter}{n}` and two entries restarting at 1 would write two plots to
    one name, which the solver takes as the same plot.

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
    vertex = 0
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
    previous_layout = list(script.probe_field_layout)
    _open_the_probe_points(case, script, sampled=sampled, steady=not unsteady, normal=normal)
    for entry_number, probes in enumerate(pproc.probes, start=1):
        if not unsteady and probes.parameters:
            # B10: on a steady run the list enables the entry and filters nothing.
            warn(
                f"case {case.sim_id!r}: {_artifact_of(case)} [[probes]] entry {entry_number} "
                f"(frame {probes.frame!r}) lists parameters, but on "
                + ('a normal probe entry (kind = "normal") ' if normal else "a steady run ")
                + "this list only enables the entry; it does not filter the probe-points "
                "export's fixed set of variables. On an unsteady "
                + ("entry" if normal else "run")
                + " it selects the fluid-plot variables.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        if unsteady and probes.parameters:
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
        first_vertex = vertex + 1
        vertex = _emit_one_probe_table(case, script, frames, probes, vertex, unsteady=unsteady)
        if (probes.field_formats or probes.reusable_inflow) and vertex >= first_vertex:
            resolved_frame = _the_probe_frame(case, probes.frame)
            frame_index = (
                1
                if resolved_frame == "REFERENCE"
                else _pproc_frame(case, frames, resolved_frame, "the sampled probe field")
            )
            script.probe_field_layout.append(
                {
                    "entry": entry_number,
                    "kind": "probe-field",
                    "probe_ids": list(range(first_vertex, vertex + 1)),
                    "frame": resolved_frame,
                    "frame_index": frame_index,
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
                    # FR-418 R2: the product says which instant it holds.
                    **({"sampled_at": "last-time-step"} if normal else {}),
                }
            )

    _pproc_sampled_volume(case, script, frames, vertex, unsteady=unsteady)
    if sampled and previous_layout and previous_layout != script.probe_field_layout:
        raise CampaignConfigError(
            "a steady job changed its sampled field layout between points; "
            "run these points separately to retain each field's placement"
        )


def _open_the_probe_points(
    case: SimCase, script: Script, *, sampled: bool, steady: bool, normal: bool
) -> None:
    """Delete and forget earlier probe points where this emission replaces them.

    A sampled field starts from no probe point. FR-417 R7: so do the normal
    probes of a row with a per-step window, which the exports script of the
    window's first step already created; the creation after the march deletes
    them first, so the final export holds each point once.
    """
    if sampled:
        if steady:
            script.emit("DELETE_PROBE_POINTS")
        script.probe_points.clear()
        script.probe_field_layout.clear()
    elif normal and stated_threshold_keys(case):
        script.emit("DELETE_PROBE_POINTS")


def _normal_probes_of(case: SimCase) -> bool:
    """Whether an unsteady row samples its pproc's probes as normal probe points (FR-417 R2).

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
    if pproc is None or not pproc.probes:
        return False
    normal = [str(n) for n, entry in enumerate(pproc.probes, 1) if entry.kind == "normal"]
    if not normal:
        return False
    unsteady = [str(n) for n, entry in enumerate(pproc.probes, 1) if entry.kind != "normal"]
    if pproc.volume_section is not None:
        unsteady.append("[volume_section]")
    if unsteady:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} mixes probe kinds "
            f"on an unsteady row: unsteady (fluid plots at every time step) "
            f"{', '.join(unsteady)}; normal (probe points at the last time step) "
            f"{', '.join(normal)}. One unsteady row samples every [[probes]] entry one "
            'way, an entry stating no kind counting as kind = "unsteady", and a '
            "[volume_section] is sampled through fluid plots. State one kind on every "
            "entry, or move the other entries to a second pproc on their own row."
        )
    return True


#: FR-417: the commands that create the probe points of a normal entry.
_PROBE_POINT_COMMANDS = frozenset(
    {"DELETE_PROBE_POINTS", "NEW_PROBE_LINE", "NEW_PROBE_POINT", "PROBE_POINTS_IMPORT"}
)

#: One recorded emission: the command, its positional and its keyword arguments.
RecordedCommand = tuple[str, tuple[object, ...], dict[str, object]]


class _ProbePointRecorder(Script):
    """A scratch script keeping the probe-point commands its build emits after the march.

    Each is kept as a call (:attr:`recorded`) and as the text it rendered
    (:attr:`recorded_text`). A raw line of the setup is emitted by the
    continuation itself, so a probe command reaching :meth:`emit` through
    :meth:`emit_line` is not kept.
    """

    def __init__(self, script: Script) -> None:
        super().__init__(script.version, registry=script.registry)
        self.recorded: list[RecordedCommand] = []
        self.recorded_text = ""
        self._marched = False
        self._in_a_raw_line = False

    def emit(self, name: str, /, *args: object, label: str | None = None, **kwargs: object) -> None:
        """Emit as :class:`Script` does, keeping each probe-point command after the march."""
        kept = self._marched and not self._in_a_raw_line and name in _PROBE_POINT_COMMANDS
        before = len(self.render()) if kept else 0
        super().emit(name, *args, label=label, **kwargs)
        self._marched = self._marched or name == "START_SOLVER"
        if kept:
            self.recorded.append((name, args, {**kwargs, **({"label": label} if label else {})}))
            self.recorded_text += self.render()[before:]

    def emit_line(self, line: str, /) -> None:
        """Emit a raw line as :class:`Script` does, without keeping it."""
        self._in_a_raw_line = True
        try:
            super().emit_line(line)
        finally:
            self._in_a_raw_line = False


def _built_from_the_mesh(
    case: SimCase, script: Script, build: Callable[[SimCase, Script], None]
) -> _ProbePointRecorder:
    """Build the row from the mesh on a scratch script that is never written (FR-417 R6, R7).

    Raises
    ------
    CampaignConfigError
        The row cannot be built from the mesh, so where its normal probes are
        placed is unknown; the message names the entries and the remedy.
    """
    scratch = _ProbePointRecorder(script)
    restart = {RESTART_VARIABLE, RESTART_FROM_VARIABLE, RESTART_ITERATIONS_VARIABLE}
    variables = {key: value for key, value in case.variables.items() if key not in restart}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            build(case.model_copy(update={"variables": variables}), scratch)
    except PyflightstreamError as error:
        count = len(case.pproc.probes) if case.pproc is not None else 0
        entries = ", ".join(str(number) for number in range(1, count + 1))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: its pproc artifact {case.pproc_id!r} samples normal "
            f"probes (entries {entries}), which are created where the row's full script "
            f"places them, and that script cannot be built here ({error}). A continued "
            "march never created them. Run the row again from the mesh with "
            "pyfs-matrix run --force-rerun <point>."
        ) from error
    return scratch


def _normal_probes_of_a_continuation(
    case: SimCase,
    script: Script,
    build: Callable[[SimCase, Script], None],
) -> list[RecordedCommand]:
    """Return the probe-point commands a continuation emits after its march (FR-417 R6).

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
    script.probe_points[:] = scratch.probe_points
    script.probe_field_layout[:] = scratch.probe_field_layout
    return scratch.recorded


def _creation_of_normal_probes(
    case: SimCase, script: Script, build: Callable[[SimCase, Script], None]
) -> str:
    """Return the lines the first exporting step runs to create the normal probes (FR-417 R7).

    ``DELETE_PROBE_POINTS`` and the creation commands of the post-march route,
    taken from the row built from the mesh on a scratch script; empty for a
    row whose probes are not normal or that states no per-step window.
    """
    if case.recipe not in ("unsteady", "unsteady_rotor") or not stated_threshold_keys(case):
        return ""
    if case.pproc is None or not _normal_probes_of(case):
        return ""
    return _built_from_the_mesh(case, script, build).recorded_text


#: FR-91. The simulation subfolder the package writes a simulation's probe
#: positions file into. Per SIM and not per point, by the requirement of
#: 2026-09-11. A survey a USER cites (FR-80) is NOT here: it is imported where
#: it lives, under the workspace's `inputs/profiles/`, by the absolute path the
#: row's binding resolved. This comment said the cited file was staged here too,
#: and nothing ever staged it (GOAL-021 item 2, measured 2026-09-14).
PROBE_PROFILE_DIR = "profiles"

#: FR-91. The columns of the probe positions file, in order, and the ONE home
#: of that vocabulary. The run layer writes the file and the post layer reads
#: it, and until this existed each end spelled the five names for itself: a
#: literal header string on one side and a tuple on the other, with nothing
#: to make them disagree loudly (the architecture lens, 2026-09-11). It lives
#: here because `cases` is the deepest layer both of them already import.
PROBE_POSITION_COLUMNS: tuple[str, ...] = ("PROBE", "X", "Y", "Z", "FRAME")


def _rectangle_points(rectangle, scale: float) -> list[list[float]]:
    """Lay out the grid of a rectangular probe plane, row by row (FR-79).

    Three corners give two edge vectors from `origin`, and the grid runs along
    both with BOTH ENDS INCLUDED, so a declaration of 3 by 4 is twelve points
    and three of its corners are the three declared vertices. The order is v
    fastest within u, which is the reading order of a row of stations.
    """
    origin = list(rectangle.origin)
    edge_u = [b - a for a, b in zip(rectangle.origin, rectangle.along_u, strict=True)]
    edge_v = [b - a for a, b in zip(rectangle.origin, rectangle.along_v, strict=True)]
    out: list[list[float]] = []
    for index_u in range(rectangle.points_u):
        fraction_u = index_u / (rectangle.points_u - 1)
        for index_v in range(rectangle.points_v):
            fraction_v = index_v / (rectangle.points_v - 1)
            out.append(
                [
                    round(
                        (origin[axis] + edge_u[axis] * fraction_u + edge_v[axis] * fraction_v)
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


def _circle_points(circle, scale: float) -> list[list[float]]:
    """Lay out the polar grid of a circular probe plane (FR-79).

    `points_radial` stations from the centre to the rim INCLUDING both, and
    `points_azimuth` around. THE CENTRE APPEARS ONCE rather than once per
    azimuth: a survey that sampled its own centre eight times would weight it
    eight times in anything that averages the file.

    The two in-plane axes are built from the normal by taking the world axis
    least aligned with it, which is the standard way to get a stable basis and
    avoids the degenerate cross product a fixed choice hits when the normal
    happens to be that axis.
    """
    import math

    normal = list(circle.normal)
    length = math.sqrt(sum(value * value for value in normal))
    normal = [value / length for value in normal]
    least = min(range(3), key=lambda axis: abs(normal[axis]))
    seed = [1.0 if axis == least else 0.0 for axis in range(3)]
    first = [
        seed[1] * normal[2] - seed[2] * normal[1],
        seed[2] * normal[0] - seed[0] * normal[2],
        seed[0] * normal[1] - seed[1] * normal[0],
    ]
    span = math.sqrt(sum(value * value for value in first))
    first = [value / span for value in first]
    second = [
        normal[1] * first[2] - normal[2] * first[1],
        normal[2] * first[0] - normal[0] * first[2],
        normal[0] * first[1] - normal[1] * first[0],
    ]

    out: list[list[float]] = []
    for index_r in range(circle.points_radial):
        radius = circle.radius * index_r / (circle.points_radial - 1)
        if radius == 0.0:
            out.append([round(value * scale, 5) for value in circle.center])
            continue
        for index_a in range(circle.points_azimuth):
            angle = 2.0 * math.pi * index_a / circle.points_azimuth
            out.append(
                [
                    round(
                        (
                            circle.center[axis]
                            + radius
                            * (math.cos(angle) * first[axis] + math.sin(angle) * second[axis])
                        )
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


def _read_probe_profile(path: str, *, volume_only: bool = False) -> list[list[float]]:
    """Read the counted X,Y,Z,TYPE profile defined by PROBE_POINTS_IMPORT.

    Both surface (0) and volume (1) rows supply fixed vertices to unsteady
    fluid plots. The type does not change the fluid-plot sampling command.

    With ``volume_only`` (a steady row whose profile is expanded point by
    point into ``NEW_PROBE_POINT VOLUME``), a surface row is refused by
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
            raise ValueError(f"declares {count} points but contains {len(rows) - 1} rows")
        points = []
        for number, row in enumerate(rows[1:], start=1):
            if len(row) != 4 or row[3].strip() not in ("0", "1"):
                raise ValueError(f"point {number} must be X,Y,Z,TYPE with TYPE 0 or 1")
            if volume_only and row[3].strip() == "0":
                raise ValueError(
                    f"point {number}: a surface TYPE 0 row cannot be expanded as a "
                    "volume probe; a steady row that requests a field (or a volume "
                    "section, or a reusable inflow) samples every cited point in the "
                    "flow, so cite a profile of TYPE 1 rows or drop the field request"
                )
            point = [float(value) for value in row[:3]]
            if not all(math.isfinite(value) for value in point):
                raise ValueError(f"point {number} has a non-finite coordinate")
            points.append(point)
        return points
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        raise CampaignConfigError(f"probe profile {path!r} cannot be read: {error}") from error


def _emit_one_probe_table(case, script, frames, probes, vertex: int, *, unsteady: bool) -> int:
    """Emit one `[[probes]]` entry, returning the vertex count after it."""
    if not probes.parameters:
        return vertex
    if probes.points_file:
        from pyflightstream.probes import emit_probe_import

        # BY ABSOLUTE PATH, resolved when the row bound (GOAL-021 item 2). The
        # relative `profiles/<file>` this emitted until 0.18.1 named a file
        # nothing staged, in a folder that is not a submitted point's working
        # directory, so a builder that meets an unresolved citation refuses
        # rather than emitting a line that imports nothing.
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
        ):
            emit_probe_import(script, probes.resolved_points_file)
            return vertex
    if not (probes.points_file or probes.lines or probes.rectangles or probes.circles):
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
        for step in range(probes.points):
            fraction = step / (probes.points - 1)
            point = [
                round((a + (b - a) * fraction) * scale, 5)
                for a, b in zip(line.start, line.end, strict=True)
            ]
            vertex += 1
            # FR-91. RECORDED BY THE LOOP THAT PLACES IT, so the position a
            # reader is given is the position the solver was given. It is
            # recorded for BOTH run types: a steady export carries its own
            # X, Y and Z and still never names the frame they are in, and a
            # table of coordinates that does not say which frame is as
            # unplaceable as one carrying none.
            script.probe_points.append(
                (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
            )
            if unsteady:
                for parameter in probes.parameters:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                        frame=frame,
                        parameter=parameter,
                        name=f"{parameter}{vertex}",
                        vertex=" ".join(str(value / native_per_m) for value in point),
                    )

    if not unsteady:
        # FR-81. A STEADY ROW CREATES THE POINTS IT EXPORTS. It has no
        # fluid plots, which is what places a vertex on an unsteady row, so
        # until 0.16.0 it emitted `EXPORT_PROBE_POINTS` and no creation verb
        # at all: the script asked the solver to export a thing nobody
        # made. WHAT THE SOLVER THEN RETURNED IS INFERRED AND NOT MEASURED,
        # and this comment used to assert it. FR-81's measurement is of the
        # EMITTED SCRIPT -- creation verbs none, export present -- which is
        # a fact about this package; what an unpaired export produces at
        # the machine is a solver behaviour no dated probe in this tree
        # covers.
        # That is the same defect as the fifty dummy surface sections, one
        # family over.
        #
        # THIS BLOCK IS OUTSIDE THE LOOP OVER THE LINES (B04). It sat inside it
        # until 0.27.0, so N declared lines gave N squared commands and the
        # solver exported every point N times (RPT-062: 99 points for 33).
        #
        # ONE `NEW_PROBE_LINE` PER DECLARED LINE, with the point count the
        # entry states, rather than one command per vertex: the survey line
        # is what the solver's own vocabulary offers for exactly this, it
        # takes the count and the two ends, and it is verified on four
        # builds. The coordinates are scaled the same way the vertices
        # above are, so a `rotor_radius` entry lands on the same disk in
        # both run types.
        #
        # IN THE REFERENCE FRAME (reading B30): `NEW_PROBE_LINE` takes no frame,
        # so a line declared in another frame is carried into the reference by
        # where this script placed that frame; the unsteady route passes the
        # frame to its command instead.
        ends = [
            _in_the_reference_frame(
                case, script, frame, probes.frame, [v * scale for v in line.start]
            )
            + _in_the_reference_frame(
                case, script, frame, probes.frame, [v * scale for v in line.end]
            )
            for line in probes.lines
        ]
        for first_x, first_y, first_z, last_x, last_y, last_z in ends:
            script.emit(
                "NEW_PROBE_LINE",
                numpts=probes.points,
                x1=first_x,
                y1=first_y,
                z1=first_z,
                x2=last_x,
                y2=last_y,
                z2=last_z,
            )

    # FR-79: A RECTANGLE AND A CIRCLE ARE EMITTED POINT BY POINT, by the
    # decision of 2026-09-10: a rectangular or circular plane is always
    # defined point by point. The reason is TRANSPARENCY
    # rather than geometry. On the unsteady path the points reach the solver
    # one at a time whatever the shape was, so emitting a line per grid row on
    # one path and points on the other would make one declaration produce two
    # different exports, which is the thing every requirement of this release
    # is against.
    #
    # BOTH RUN TYPES REACH THIS. An unsteady row places each vertex with its
    # fluid plots; a steady row places it with `NEW_PROBE_POINT`, which is the
    # per-vertex verb beside the survey line.
    lattice: list[list[float]] = []
    if probes.points_file:
        lattice += [
            [value * scale for value in point]
            for point in _read_probe_profile(probes.resolved_points_file, volume_only=not unsteady)
        ]
    for rectangle in probes.rectangles:
        lattice += _rectangle_points(rectangle, scale)
    for circle in probes.circles:
        lattice += _circle_points(circle, scale)
    for point in lattice:
        vertex += 1
        # FR-91, and the lattice reaches here for BOTH run types, so one
        # append covers a rectangle and a circle on either path.
        script.probe_points.append(
            (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
        )
        if unsteady:
            for parameter in probes.parameters:
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=frame,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value / native_per_m) for value in point),
                )
        else:
            # A VOLUME PROBE, the point in the flow a fluid probe is. The
            # command's `type` is required on every build, and this line was
            # emitted without it from FR-79 until 0.28.0, so a steady row
            # drawing a rectangle or a circle never planned (found by the
            # input template's test, G47); `helpers.new_probe_points` and the
            # survey file (`TYPE` 1) say VOLUME for the same point. The command
            # takes no frame either, so the point goes into the reference frame
            # the way a steady line's ends do (reading B30).
            x, y, z = _in_the_reference_frame(case, script, frame, probes.frame, list(point))
            script.emit("NEW_PROBE_POINT", type="VOLUME", x=x, y=y, z=z)
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
    ex, ey, ez = placement.axes
    return [
        round(origin[i] + point[0] * ex[i] + point[1] * ey[i] + point[2] * ez[i], 5)
        for i in range(3)
    ]


#: THE SHAPE OF A ROTOR'S FRAME NAME, used only to tell a rotor frame this
#: RUN did not create from a frame no row could create. It is deliberately
#: NOT used to say WHOSE frame a name is: `_the_rotor_whose_frame_this_is`
#: answers that by composing the names forward, because a custom frame the
#: reference declares may share a rotor's prefix and reading the shape
#: backward once scaled probe lines to the wrong disk.
_ROTOR_FRAME_SPELLING = re.compile(r"_(SMRP|RMRP\d*)$")


def _the_probe_frame(case: SimCase, stated: str) -> str:
    """Resolve an unstated probe frame to a rotor THIS ROW TURNS (FR-65).

    It was the literal ``PROP_MRP`` until 0.15.0, when a reference described
    one propulsor and one name could stand for it. A name is not enough now,
    because which hub it is depends on the row, so the default is resolved
    here and the artifact states nothing.

    WHICH ROTOR, and this is the part the first fix got wrong. It read the
    rotor a row with no MOTIONS turns, which answers None whenever the
    reference declares more than one, so the name became ``ROTOR_SMRP``, no
    builder created it, and the probe lines were DROPPED behind a warning
    saying the row does not turn that rotor when there is no rotor of that
    name at all (the interface lens of the 0.15.0 release review, on the
    round-two fix). The rotors a row TURNS are the ones its motions name, and
    the clock names which of them the row is about.

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

    Splitting the NAME on its last underscore instead was the shape this
    replaced, and it answered PUSHER for `PUSHER_TIP`: a custom frame the
    reference declares under any name it likes (FR-72) that merely shares
    a rotor's prefix was read as that rotor's, so probe lines were scaled
    to its disk. That is the failure the caller exists to prevent,
    reintroduced one level down (the architecture lens, 2026-09-10;
    measured: PUSHER_TIP returned the pusher's 1.8 m).
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
    measured in, so `frame = "PUSHER_SMRP"` means pusher radii. That
    matters at 0.15.0 and did not before it, because the reference now
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


#: The create command of each volume-section shape (G05).
_VOLUME_SECTION_COMMANDS = {
    "rectangle": "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
    "circle": "CREATE_NEW_CIRCLE_VOLUME_SECTION",
}


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
        script.probe_points.append((vertex, *map(float, point), label))
        if unsteady:
            for parameter in ("VX", "VY", "VZ"):
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=frame,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value / factor) for value in point),
                )
        else:
            script.emit("NEW_PROBE_POINT", x=point[0], y=point[1], z=point[2], type="VOLUME")
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
