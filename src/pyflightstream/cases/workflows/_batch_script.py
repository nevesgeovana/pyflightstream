"""The job script of a grouped run: several unsteady points in one instance (FR-B3 to FR-B7b).

A grouped job (``--batch`` or ``--polar-sweep``, 0.35.0) runs every point of
several polars in ONE FlightStream instance. The script layer's phase guard
cannot hold two points in one ``Script``, so the job script is a TEXT splice
of the per-point scripts the builders already wrote, exactly as the licensed
probes of 2026-10-02 built theirs (DESIGN-0350 test report, arms A, AF, C, D
and E). Every rule below was measured there:

1. the job's first point is its whole text without its final
   ``CLOSE_FLIGHTSTREAM``, its action registrations replaced, at the place of
   the first one, by the job's registration block;
2. a later point of the same polar is ``REMOVE_INITIALIZATION`` then its text
   from its restate anchor on, registrations dropped: the model objects stay
   loaded across the re-initialization, so only what follows the anchor may
   differ from the polar's first point;
3. the first point of a later polar is ``NEW_SIMULATION`` then its whole
   text, registrations dropped: the actions survive ``NEW_SIMULATION`` and a
   second registration runs every action twice per step;
4. every relative output becomes absolute under the point's datapoint folder,
   and a point's own log export becomes its cumulative log;
5. the job ends with its own ``EXPORT_LOG`` when the points export their
   logs, then ``CLOSE_FLIGHTSTREAM``;
6. the registration block is rendered by the one emitter of those lines;
7. every save and export target of the job is absolute, or the job is refused.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.cases._unsteady_actions import register_unsteady_actions
from pyflightstream.commands import ArgSpec, CommandEntry, CommandRegistry, Layout
from pyflightstream.script import Script, helpers

from ._batch_actions import absolute_output_lines, is_absolute_target
from ._clock import unsteady_counter_steps, unsteady_export_threshold, walltime_stop_text
from ._conventions import WorkflowConventions
from ._vocabulary import WALLTIME_STOP_VERB

__all__ = [
    "RESTATE_ANCHORS",
    "JobBlock",
    "JobPoint",
    "JobPolar",
    "JobScript",
    "absolutize_outputs",
    "assemble_job",
    "drop_registrations",
    "job_point",
    "refuse_unspliceable",
    "registration_block",
    "restate_anchor",
    "write_targets",
]

#: The commands a later point of a polar is restated from, in emission order
#: (MEASURED, arms A and D): the rotor speed when the advance ratio moves (a new
#: speed and a new time step), else the unsteady solver block.
RESTATE_ANCHORS = ("SET_MOTION_ROTOR_RPM", "SET_SOLVER_UNSTEADY")

#: What a later point of the same polar starts with (FR-B3).
REINIT_VERB = "REMOVE_INITIALIZATION"
#: What the first point of a later polar starts with (FR-B4).
REFRESH_VERB = "NEW_SIMULATION"
#: The token a point's own datapoint folder becomes when two texts are compared.
DATAPOINT_TOKEN = "<datapoint>"

Transition = Literal["start", "reinit", "refresh"]
JobKind = Literal["batch", "polar_sweep"]


@dataclass(frozen=True)
class JobPoint:
    """One point of a grouped job, as its own script wrote it.

    Attributes
    ----------
    run_id : str
        The point's run id.
    sim_id : str
        The sim the point belongs to.
    point_name : str
        The point tag, the last part of the run id.
    text : str
        The per-point script exactly as written (rendered).
    datapoint_dir : PurePath
        The point's datapoint folder, absolute, the job root applied.
    outputs : tuple of str
        The outputs the point's script writes, as it names them (relative).
    action_exports : str
        Its per-step export lines ('' when it states no threshold), relative.
    first_export_step : int or None
        The threshold's first step, counted from the point's own step 1.
    stop_text : str
        What the clock writes when it stops this point, relative names.
    time_steps : int
        The time steps the point marches.
    """

    run_id: str
    sim_id: str
    point_name: str
    text: str
    datapoint_dir: PurePath
    outputs: tuple[str, ...]
    action_exports: str
    first_export_step: int | None
    stop_text: str
    time_steps: int


@dataclass(frozen=True)
class JobPolar:
    """The points of one polar, in sweep order."""

    sim_id: str
    points: tuple[JobPoint, ...]


@dataclass(frozen=True)
class JobBlock:
    """Where one point's part sits in the job text (1-based, inclusive)."""

    run_id: str
    transition: Transition
    anchor: str | None
    first_line: int
    last_line: int


@dataclass(frozen=True)
class JobScript:
    """The assembled job: its text, each point's block and every write target."""

    kind: JobKind
    text: str
    blocks: tuple[JobBlock, ...]
    targets: tuple[str, ...]


def _lines(text: str) -> list[str]:
    """Return the lines of a script text, any line end accepted."""
    return text.splitlines()


def _line_args(entry: CommandEntry) -> list[ArgSpec]:
    """Return the arguments a command writes on the lines after its own, in order."""
    if entry.layout is Layout.PARAM_LINES:
        return [arg for arg in entry.args if not arg.on_command_line]
    if entry.layout is Layout.INLINE:
        return [arg for arg in entry.args if arg.own_line]
    return []


def _is_target_command(name: str) -> bool:
    """Whether a command writes a file the job must place absolutely (rule 7)."""
    return name in ("SAVEAS", "SAVE_PLOT_TO_FILE", "UNSTEADY_SOLVER_EXPORT_PLOTS") or (
        name.startswith("EXPORT_")
    )


def _target_offset(entry: CommandEntry) -> int | None:
    """Return the line offset of the command's path argument, or None when it names no path."""
    for offset, arg in enumerate(_line_args(entry), start=1):
        if arg.type == "path":
            return offset
    return None


def write_targets(text: str, version: str) -> tuple[str, ...]:
    """Return the path argument of every save and export command of a script, in order.

    A command counts when its name is ``SAVEAS``, starts with ``EXPORT_``, or
    is ``SAVE_PLOT_TO_FILE`` or ``UNSTEADY_SOLVER_EXPORT_PLOTS``; its path is
    read with the command database's ``type: path`` argument and layout.

    Parameters
    ----------
    text : str
        A script text.
    version : str
        The build whose command database reads it.

    Returns
    -------
    tuple of str
        Each target as the script writes it.
    """
    view = CommandRegistry.load().for_version(version)
    lines = _lines(text)
    found: list[str] = []
    for index, line in enumerate(lines):
        words = line.split()
        if not words or not _is_target_command(words[0]) or words[0] not in view:
            continue
        offset = _target_offset(view[words[0]])
        if offset is not None and index + offset < len(lines):
            found.append(lines[index + offset].strip())
    return tuple(found)


def job_point(
    point_case: SimCase, *, run_id: str, text: str, datapoint_dir: PurePath, version: str
) -> JobPoint:
    """Return one point of a job: its script and what its actions need, from its case.

    Parameters
    ----------
    point_case : SimCase
        The point's case (the grouped case, at its point).
    run_id : str
        The point's run id; its last part is the point tag.
    text : str
        The per-point script exactly as written.
    datapoint_dir : PurePath
        The point's datapoint folder, absolute, the job root applied.
    version : str
        The build the script was written for.

    Returns
    -------
    JobPoint
        The point, its outputs read off its script's save and export targets.
    """
    conventions = WorkflowConventions.for_case(point_case)
    threshold = unsteady_export_threshold(point_case, conventions, version=version)
    outputs = dict.fromkeys(
        target for target in write_targets(text, version) if not is_absolute_target(target)
    )
    return JobPoint(
        run_id=run_id,
        sim_id=point_case.sim_id,
        point_name=run_id.rpartition("/")[2],
        text=text,
        datapoint_dir=datapoint_dir,
        outputs=tuple(outputs),
        action_exports=threshold.exports if threshold is not None else "",
        first_export_step=threshold.first_step if threshold is not None else None,
        stop_text=walltime_stop_text(point_case, conventions, version=version),
        time_steps=unsteady_counter_steps(point_case),
    )


def _compared(point: JobPoint) -> list[str]:
    """Return the point's lines with its own datapoint folder replaced by one token."""
    folder = str(point.datapoint_dir)
    posix = point.datapoint_dir.as_posix()
    return [
        line.replace(folder, DATAPOINT_TOKEN).replace(posix, DATAPOINT_TOKEN)
        for line in _lines(point.text)
    ]


def _anchor_index(first: JobPoint, point: JobPoint) -> int:
    """Return the 0-based line of ``point``'s restate anchor, refusing an unspliceable point.

    The anchor is the nearest line naming one of :data:`RESTATE_ANCHORS` at or
    before the first line where the two texts differ (each point's own
    datapoint folder compared as one token); everything before it must be
    equal, because the model objects stay loaded across a re-initialization.
    """
    ours, theirs = _compared(first), _compared(point)
    differs = next(
        (i for i, (a, b) in enumerate(zip(ours, theirs, strict=False)) if a != b),
        min(len(ours), len(theirs)),
    )
    for index in range(min(differs, len(theirs) - 1), -1, -1):
        words = theirs[index].split()
        if words and words[0] in RESTATE_ANCHORS:
            return index
    first_line = ours[differs] if differs < len(ours) else "<end of text>"
    point_line = theirs[differs] if differs < len(theirs) else "<end of text>"
    raise CampaignConfigError(
        f"point {point.run_id!r} cannot follow {first.run_id!r} in one solver instance: "
        f"their scripts differ at line {differs + 1} ({first_line!r} against {point_line!r}), "
        f"before any of {', '.join(RESTATE_ANCHORS)}. A geometry, frame, plot, fluid or motion "
        "difference cannot be restated after REMOVE_INITIALIZATION, because the model objects "
        "stay loaded; run this polar on its own."
    )


def refuse_unspliceable(first: JobPoint, point: JobPoint) -> None:
    """Refuse a point whose text differs from its polar's first point before its anchor.

    Parameters
    ----------
    first : JobPoint
        The polar's first point.
    point : JobPoint
        A later point of the same polar.

    Raises
    ------
    CampaignConfigError
        Naming the first differing line, when no restate anchor precedes it.
    """
    _anchor_index(first, point)


def restate_anchor(first: JobPoint, point: JobPoint) -> str:
    """Return the command a later point of a polar is restated from.

    Parameters
    ----------
    first : JobPoint
        The polar's first point.
    point : JobPoint
        A later point of the same polar.

    Returns
    -------
    str
        ``SET_MOTION_ROTOR_RPM`` when the rotor speed is the first difference,
        else ``SET_SOLVER_UNSTEADY``.

    Raises
    ------
    CampaignConfigError
        When the point cannot be spliced (:func:`refuse_unspliceable`).
    """
    return _lines(point.text)[_anchor_index(first, point)].split()[0]


def absolutize_outputs(text: str, datapoint_dir: PurePath, names: Iterable[str]) -> str:
    """Return a point's text with every output it names made absolute in its folder (FR-B7b).

    Parameters
    ----------
    text : str
        The point's script text.
    datapoint_dir : PurePath
        The point's absolute datapoint folder.
    names : iterable of str
        The point's declared outputs, as named in its script.

    Returns
    -------
    str
        The text with each output line absolute and its ``EXPORT_LOG`` target
        made the point's cumulative log.

    Raises
    ------
    CampaignConfigError
        When a declared output is not a whole line of the text.
    """
    wanted = tuple(names)
    present = {line.strip() for line in _lines(text)}
    missing = [name for name in wanted if name not in present]
    if missing:
        raise CampaignConfigError(
            f"the outputs {missing} are not written as a whole line of the point's script, "
            f"so they cannot be placed under {datapoint_dir}; the job is not assembled."
        )
    return absolute_output_lines(text, datapoint_dir, wanted)


def _registration_span(lines: list[str], index: int, arguments: int) -> int:
    """Return how many lines the registration at ``index`` occupies, its blank line included."""
    span = 1 + arguments
    if index + span < len(lines) and not lines[index + span].strip():
        span += 1
    return span


def _without_registrations(text: str) -> tuple[list[str], int | None]:
    """Return the lines without any action registration, and where the first one stood."""
    head = helpers.UNSTEADY_ACTION_COMMAND
    arguments = len(_line_args(CommandRegistry.load().commands[head]))
    lines = _lines(text)
    kept: list[str] = []
    first: int | None = None
    index = 0
    while index < len(lines):
        words = lines[index].split()
        if words and words[0] == head:
            first = len(kept) if first is None else first
            index += _registration_span(lines, index, arguments)
            continue
        kept.append(lines[index])
        index += 1
    return kept, first


def drop_registrations(text: str) -> str:
    """Return a script text without its unsteady action registrations (FR-B4).

    Parameters
    ----------
    text : str
        A per-point script text.

    Returns
    -------
    str
        The text with every ``SET_NEW_UNSTEADY_SOLVER_ACTION`` and its
        argument line removed.
    """
    return "\n".join(_without_registrations(text)[0]) + "\n"


def registration_block(version: str, *, exports: bool, walltime: bool) -> str:
    """Return the job's action registrations, rendered by their one emitter.

    Parameters
    ----------
    version : str
        The build of the job.
    exports : bool
        Whether any point states a per-step export threshold.
    walltime : bool
        Whether the job registers the clock pair.

    Returns
    -------
    str
        The lines ``register_unsteady_actions`` renders on a fresh script.
    """
    script = Script(version)
    register_unsteady_actions(script, True if exports else None, walltime=walltime)
    return script.render()


def _body(point: JobPoint) -> list[str]:
    """Return the point's absolute text as lines, its final ``CLOSE_FLIGHTSTREAM`` removed."""
    lines = _lines(absolutize_outputs(point.text, point.datapoint_dir, point.outputs))
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == WALLTIME_STOP_VERB:
        lines.pop()
    return lines


def _start_lines(point: JobPoint, block: str) -> list[str]:
    """Rule 1: the job's first point, the job's registrations in place of its own."""
    kept, first = _without_registrations("\n".join(_body(point)))
    if first is None:
        raise CampaignConfigError(
            f"point {point.run_id!r} registers no unsteady action, so a job cannot count its "
            "steps; a grouped job needs a build that documents the unsteady solver action."
        )
    return kept[:first] + _lines(block) + kept[first:]


def _point_lines(first: JobPoint, point: JobPoint, transition: Transition) -> list[str]:
    """Rules 2 and 3: a later point's lines, its transition verb first."""
    body, _ = _without_registrations("\n".join(_body(point)))
    if transition == "refresh":
        return [REFRESH_VERB, "", *body]
    return [REINIT_VERB, "", *body[_shifted(point, _anchor_index(first, point)) :]]


def _shifted(point: JobPoint, cut: int) -> int:
    """Return where line ``cut`` of the point's text lands once its registrations are dropped."""
    before = "\n".join(_lines(point.text)[:cut])
    return len(_without_registrations(before)[0]) if before else 0


def _ending(polars: Sequence[JobPolar], job_log: PurePath | None) -> list[str]:
    """Rule 5: the job's own log when its points export theirs, then the close."""
    exports_log = any(
        line.strip() == "EXPORT_LOG"
        for polar in polars
        for point in polar.points
        for line in _lines(point.text)
    )
    tail = ["EXPORT_LOG", str(job_log), ""] if job_log is not None and exports_log else []
    return [*tail, WALLTIME_STOP_VERB]


def _parts(polars: Sequence[JobPolar], block: str) -> list[tuple[JobPoint, Transition, list[str]]]:
    """Return every point of the job with its transition and its lines, in job order."""
    parts: list[tuple[JobPoint, Transition, list[str]]] = []
    for number, polar in enumerate(polars):
        lead = polar.points[0]
        for order, point in enumerate(polar.points):
            if number == 0 and order == 0:
                parts.append((point, "start", _start_lines(point, block)))
            elif order == 0:
                parts.append((point, "refresh", _point_lines(lead, point, "refresh")))
            else:
                parts.append((point, "reinit", _point_lines(lead, point, "reinit")))
    return parts


def assemble_job(
    polars: Sequence[JobPolar],
    *,
    kind: JobKind,
    version: str,
    job_log: PurePath | None,
    walltime: bool = True,
) -> JobScript:
    """Return the job script that runs every point of ``polars`` in one solver instance.

    Parameters
    ----------
    polars : sequence of JobPolar
        The job's polars in job order, each with its points in sweep order.
    kind : {"batch", "polar_sweep"}
        The grouped mode.
    version : str
        The build of the job.
    job_log : PurePath or None
        The job's own final log, absolute; written only when the points
        export their logs.
    walltime : bool, optional
        Whether the job registers the clock pair; True by default, and a
        schedule without a deadline never fires it.

    Returns
    -------
    JobScript
        The text, each point's block and every save and export target.

    Raises
    ------
    CampaignConfigError
        When there is no point, a point cannot be spliced, an output cannot be
        placed, or a save or export target stays relative.
    """
    if not polars or not all(polar.points for polar in polars):
        raise CampaignConfigError("a job needs at least one polar with at least one point.")
    exports = any(p.first_export_step is not None for polar in polars for p in polar.points)
    block = registration_block(version, exports=exports, walltime=walltime)
    lines: list[str] = []
    blocks: list[JobBlock] = []
    for point, transition, part in _parts(polars, block):
        lead = next(polar.points[0] for polar in polars if point in polar.points)
        anchor = restate_anchor(lead, point) if transition == "reinit" else None
        blocks.append(
            JobBlock(point.run_id, transition, anchor, len(lines) + 1, len(lines) + len(part))
        )
        lines += [*part, ""]
    text = "\n".join([*lines, *_ending(polars, job_log)]) + "\n"
    targets = write_targets(text, version)
    relative = [target for target in targets if not is_absolute_target(target)]
    if relative:
        raise CampaignConfigError(
            f"the job's save and export targets {relative} are relative; inside one instance "
            "every target must name its point's folder, so the job is not assembled."
        )
    return JobScript(kind=kind, text=text, blocks=tuple(blocks), targets=targets)
