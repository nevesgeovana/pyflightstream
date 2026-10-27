"""The streamlines a pproc artifact traces after the solve (FR-460).

:func:`_pproc_streamlines` emits the ``[streamlines]`` table of the row's pproc
in the analysis phase, after the solve (after the march on an unsteady row)
and before the export block: the surface friction lines and their export, the
direction and length every off-body line takes, the seed lines and tubes, and
the off-body generation, whose export is one of the row's exports.
"""

from __future__ import annotations

from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.cases._skipped_families import leave_out_what_the_row_cannot_take
from pyflightstream.cases.pproc import StreamlineLine, StreamlinesSpec, StreamlineTube
from pyflightstream.script import Script

from ._frames import _a_rotor_frame_the_row_leaves_out, _pproc_frame
from ._gap_evidence import refuse_unprobed_commands
from ._names import _artifact_of
from ._pproc import STREAMLINE_PARTS, streamline_parts_the_row_skips
from ._probes import _in_the_reference_frame, _the_radius_the_probe_lines_are_in
from ._rows import _from_metres
from ._vocabulary import Frames

__all__ = [
    "streamline_commands",
    "streamline_count",
    "streamlines_the_row_takes",
]

_SURFACE = ("GENERATE_ALL_SURFACE_STREAMLINES", "EXPORT_ALL_SURFACE_STREAMLINES")
_DELETES = ("DELETE_ALL_SURFACE_STREAMLINES", "DELETE_ALL_OFF_BODY_STREAMLINES")


def streamline_count(case: SimCase) -> int:
    """Return the off-body streamlines one point of the case traces (FR-1079).

    Parameters
    ----------
    case : SimCase
        The case; its pproc's ``[streamlines]`` table is read.

    Returns
    -------
    int
        The sum of every line's count and every tube's ``radial * circular``; 0
        where the pproc traces none.
    """
    spec = case.pproc.streamlines if case.pproc is not None else None
    return 0 if spec is None else spec.off_body_count()


def streamline_commands(spec: StreamlinesSpec, *, reopened: bool = False) -> list[str]:
    """Return the commands a ``[streamlines]`` table emits, in order of first use.

    Parameters
    ----------
    spec : StreamlinesSpec
        The table.
    reopened : bool, optional
        Whether the script opens a saved simulation, which may carry streamlines
        to delete first.

    Returns
    -------
    list of str
        The command names.
    """
    commands: list[str] = list(_DELETES) if reopened else []
    if spec.surface:
        commands += _SURFACE
    if spec.off_body:
        if spec.direction is not None:
            commands.append(f"SET_ALL_OFF_BODY_STREAMLINES_{spec.direction.upper()}")
        if spec.length_m is not None or spec.unrestricted:
            commands.append("SET_OFF_BODY_STREAMLINE_LENGTH")
        if spec.lines:
            commands.append("NEW_STREAMLINE_DISTRIBUTION")
        if spec.tubes:
            commands.append("NEW_OFF_BODY_STREAMTUBE")
        commands += ["GENERATE_ALL_OFF_BODY_STREAMLINES", "EXPORT_ALL_OFF_BODY_STREAMLINES"]
    return commands


def streamlines_the_row_takes(case: SimCase, spec: StreamlinesSpec) -> StreamlinesSpec | None:
    """Return the part of ``spec`` this row traces, saying once what it skips (FR-1081).

    SKIPPED, NEVER REFUSED (owner rule of 2026-10-27): a part this row does not
    trace (every part on a coupled row, the off-body lines on a qsteady_rotor
    row) is left out of the row, and of its exports through
    :func:`row_outputs`, and the plan warns once naming the rows. None when
    nothing is left to trace.
    """
    skipped = streamline_parts_the_row_skips(case)
    for part, why in skipped.items():
        leave_out_what_the_row_cannot_take(
            case.sim_id, _artifact_of(case), STREAMLINE_PARTS[part][1], why
        )
    if "surface" in skipped:
        spec = spec.model_copy(update={"surface": False})
    if "off_body" in skipped:
        spec = spec.model_copy(update={"lines": [], "tubes": []})
    return spec if spec.surface or spec.off_body else None


def _scale_of(case: SimCase, script: Script, frame: str, scale: str) -> float:
    """Return the factor from the entry's stated unit to the simulation's length unit."""
    factor = 1.0
    if scale == "rotor_radius":
        factor = _the_radius_the_probe_lines_are_in(case, frame) / 2.0
    return factor * _from_metres(case, script, "streamline coordinates")


def _frame_index(case: SimCase, frames: Frames, name: str, what: str) -> int:
    """Return the index of the frame an entry cites; the reference frame is 1."""
    return 1 if name == "REFERENCE" else _pproc_frame(case, frames, name, what)


def _emit_line(
    case: SimCase, script: Script, frames: Frames, line: StreamlineLine, placed: Script
) -> None:
    """Emit one seed line, its vertices carried into the reference frame.

    ``placed`` is the script that placed the frames: the script itself, or on an
    extraction the point's own run script built again, since the saved
    simulation's frames are declared there and placed nowhere.
    """
    frame = _frame_index(case, frames, line.frame, "a streamline seed line")
    scale = _scale_of(case, placed, line.frame, line.scale)
    start = _in_the_reference_frame(
        case, placed, frame, line.frame, [value * scale for value in line.start]
    )
    end = _in_the_reference_frame(
        case, placed, frame, line.frame, [value * scale for value in line.end]
    )
    script.emit(
        "NEW_STREAMLINE_DISTRIBUTION",
        position_1_x=start[0],
        position_1_y=start[1],
        position_1_z=start[2],
        position_2_x=end[0],
        position_2_y=end[1],
        position_2_z=end[2],
        # The database note: SUBDIVISIONS is N + 1 for N streamlines.
        subdivisions=line.count + 1,
    )


def _emit_tube(
    case: SimCase, script: Script, frames: Frames, tube: StreamlineTube, placed: Script
) -> None:
    """Emit one seed tube, placed in its frame by index."""
    frame = _frame_index(case, frames, tube.frame, "a streamline tube")
    scale = _scale_of(case, placed, tube.frame, tube.scale)
    script.emit(
        "NEW_OFF_BODY_STREAMTUBE",
        frame,
        tube.axis,
        *(round(value * scale, 5) for value in tube.origin),
        round(tube.radius * scale, 5),
        tube.radial,
        tube.circular,
    )


def _pproc_streamlines(
    case: SimCase,
    script: Script,
    frames: Frames | None,
    *,
    surface_file: str | None,
    reopened: bool = False,
    placed: Script | None = None,
) -> None:
    """Emit the row's ``[streamlines]`` table in the analysis phase (FR-1077, FR-1078).

    Only the generation is emitted here; the surface trace is exported by the
    export block, where its export-phase command belongs.

    Before the trace, the streamlines a script already holds are deleted: those
    of the previous point of a warm steady sweep, which the solver keeps, and
    those a saved simulation carries when ``reopened`` (the additional post).

    Parameters
    ----------
    case : SimCase
        The case; its pproc's ``[streamlines]`` is read.
    script : Script
        The script, after the solve.
    frames : mapping or None
        The frames the run created, by name; None where the builder created none.
    surface_file : str or None
        The name the surface friction lines are exported to, from the row's outputs.
    reopened : bool, optional
        Whether the script opened a saved simulation.
    placed : Script, optional
        The script that placed the frames and set the length unit, where it is
        not ``script`` (an extraction's shadow).

    Raises
    ------
    CampaignConfigError
        A row FR-1081 refuses, a frame the run did not create, a gated command not
        verified on the build, or a surface trace with no declared output.
    """
    spec = case.pproc.streamlines if case.pproc is not None else None
    spec = streamlines_the_row_takes(case, spec) if spec is not None else None
    if spec is None:
        return
    rendered = script.render()
    again = reopened or "GENERATE_ALL_SURFACE_STREAMLINES" in rendered
    again = again or "GENERATE_ALL_OFF_BODY_STREAMLINES" in rendered
    refuse_unprobed_commands(
        case, script, streamline_commands(spec, reopened=again), capability="[streamlines]"
    )
    if spec.off_body and frames is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} seeds off-body "
            "streamlines and this script was built without the frames they are placed in "
            "(a continuation reopens a saved state and creates none); trace them on the "
            "run that marches from the mesh."
        )
    if again:
        for command in _DELETES:
            script.emit(command)
    if spec.surface:
        if surface_file is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} traces surface "
                "streamlines and the row's outputs declare no <point>_sls.txt to export them "
                "to; a row's outputs come from its pproc, so build it through the workspace."
            )
        # Exported with the other files by the export block: its command is an
        # export-phase command, and the analysis commands that follow the trace
        # would be refused after it.
        script.emit("GENERATE_ALL_SURFACE_STREAMLINES")
    if spec.off_body:
        assert frames is not None
        _emit_off_body(case, script, frames, spec, placed if placed is not None else script)


def _emit_off_body(
    case: SimCase, script: Script, frames: Frames, spec: StreamlinesSpec, geometry: Script
) -> None:
    """Emit the off-body direction, length, seeds and generation (FR-1077)."""
    if spec.direction is not None:
        script.emit(f"SET_ALL_OFF_BODY_STREAMLINES_{spec.direction.upper()}")
    if spec.length_m is not None:
        native = _from_metres(case, geometry, "streamline length")
        script.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_length=round(spec.length_m * native, 5))
    elif spec.unrestricted:
        script.emit("SET_OFF_BODY_STREAMLINE_LENGTH", set_unrestricted_length=True)
    for number, line in enumerate(spec.lines, start=1):
        what = f"[streamlines] seed line {number}"
        if not _a_rotor_frame_the_row_leaves_out(case, frames, line.frame, what):
            _emit_line(case, script, frames, line, geometry)
    for number, tube in enumerate(spec.tubes, start=1):
        what = f"[streamlines] tube {number}"
        if not _a_rotor_frame_the_row_leaves_out(case, frames, tube.frame, what):
            _emit_tube(case, script, frames, tube, geometry)
    script.emit("GENERATE_ALL_OFF_BODY_STREAMLINES")
