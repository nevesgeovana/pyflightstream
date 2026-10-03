"""The job script of a grouped run: several points in one instance (FR-B3 to FR-B7b, FR-403).

A grouped job (``--batch`` or ``--polar-sweep``, 0.35.0) runs every point of
several polars in ONE FlightStream instance. Since 0.35.1 (FR-403) a job holds
steady polars (``steady``, ``qsteady_rotor``) or unsteady ones, never both.
The script layer's phase guard cannot hold two points in one ``Script``, so
the job script is a TEXT splice of the per-point scripts the builders already
wrote, exactly as the licensed probes of 2026-10-02 built theirs
(DESIGN-0350 test report, arms A, AF, C, D and E). Every rule below was
measured there:

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

A STEADY JOB (FR-403) follows the same rules with three differences: it
registers no action (a steady point registers none, so rule 1 keeps the first
point's text whole and rule 3 has nothing to drop); a later point of a polar
is restated from :data:`STEADY_RESTATE_ANCHORS`, the first line of its solver
block, after the same ``REMOVE_INITIALIZATION``; and a later point whose text
differs from its polar's first point before that anchor (a swept flow state, a
quasi-steady rotor's turning free stream) is not refused: it follows
``NEW_SIMULATION`` with its whole text, as the first point of a polar does
(rule 3, measured identical to a fresh instance). A steady point after an
unsteady one in one instance is not measured, so the two kinds never share a
job; the split keeps them apart and :func:`assemble_job` refuses a mix.
"""

from __future__ import annotations

import re
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
from ._conventions import WorkflowConventions, select_workflow
from ._vocabulary import STEADY_RUN_TYPES, WALLTIME_STOP_VERB

__all__ = [
    "RESTATE_ANCHORS",
    "STEADY_RESTATE_ANCHORS",
    "JobBlock",
    "JobPoint",
    "JobPolar",
    "JobScript",
    "absolutize_outputs",
    "assemble_job",
    "drop_registrations",
    "job_point",
    "refreshes",
    "refuse_a_second_initialization",
    "refuse_unspliceable",
    "registration_block",
    "restate_anchor",
    "write_targets",
]

#: The commands a later point of a polar is restated from, in emission order
#: (MEASURED, arms A and D): the rotor speed when the advance ratio moves (a new
#: speed and a new time step), else the unsteady solver block.
RESTATE_ANCHORS = ("SET_MOTION_ROTOR_RPM", "SET_SOLVER_UNSTEADY")

#: The command a later point of a STEADY polar is restated from (FR-403): the
#: first line of the steady solver block, which carries the point's attitude.
#: What follows it (the solver settings, the initialisation, the solve and the
#: exports) is what an unsteady point restates after ``SET_SOLVER_UNSTEADY``;
#: the geometry, the frames and the fluid before it stay loaded.
STEADY_RESTATE_ANCHORS = ("SOLVER_SET_AOA",)

#: What a later point of the same polar starts with (FR-B3).
REINIT_VERB = "REMOVE_INITIALIZATION"
#: What the first point of a later polar starts with (FR-B4).
REFRESH_VERB = "NEW_SIMULATION"
#: The command a steady point may emit once only inside a job (FR-403).
INITIALIZE_VERB = "INITIALIZE_SOLVER"
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
        The time steps the point marches; 0 for a steady point.
    steady : bool
        Whether the point is of a steady run type (FR-403): it registers no
        action and is restated from :data:`STEADY_RESTATE_ANCHORS`.
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
    steady: bool = False


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
        The point, its outputs read off its script's save and export targets. A
        steady point (FR-403) has no per-step export, no clock and no time step.
    """
    outputs = dict.fromkeys(
        target for target in write_targets(text, version) if not is_absolute_target(target)
    )
    if select_workflow(point_case) in STEADY_RUN_TYPES:
        return JobPoint(
            run_id=run_id,
            sim_id=point_case.sim_id,
            point_name=run_id.rpartition("/")[2],
            text=text,
            datapoint_dir=datapoint_dir,
            outputs=tuple(outputs),
            action_exports="",
            first_export_step=None,
            stop_text="",
            time_steps=0,
            steady=True,
        )
    conventions = WorkflowConventions.for_case(point_case)
    threshold = unsteady_export_threshold(point_case, conventions, version=version)
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


def _anchors(point: JobPoint) -> tuple[str, ...]:
    """Return the commands a later point of ``point``'s polar may be restated from."""
    return STEADY_RESTATE_ANCHORS if point.steady else RESTATE_ANCHORS


def _anchor_index(first: JobPoint, point: JobPoint) -> int:
    """Return the 0-based line of ``point``'s restate anchor, refusing an unspliceable point.

    The anchor is the nearest line naming one of the point's anchors
    (:data:`RESTATE_ANCHORS`, or :data:`STEADY_RESTATE_ANCHORS` for a steady
    point) at or before the first line where the two texts differ (each
    point's own datapoint folder compared as one token); everything before it
    must be equal, because the model objects stay loaded across a
    re-initialization.
    """
    ours, theirs = _compared(first), _compared(point)
    anchors = _anchors(point)
    differs = next(
        (i for i, (a, b) in enumerate(zip(ours, theirs, strict=False)) if a != b),
        min(len(ours), len(theirs)),
    )
    for index in range(min(differs, len(theirs) - 1), -1, -1):
        words = theirs[index].split()
        if words and words[0] in anchors:
            return index
    first_line = ours[differs] if differs < len(ours) else "<end of text>"
    point_line = theirs[differs] if differs < len(theirs) else "<end of text>"
    raise CampaignConfigError(
        f"point {point.run_id!r} cannot follow {first.run_id!r} in one solver instance: "
        f"their scripts differ at line {differs + 1} ({first_line!r} against {point_line!r}), "
        f"before any of {', '.join(anchors)}. A geometry, frame, plot, fluid or motion "
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


def refreshes(first: JobPoint, point: JobPoint) -> bool:
    """Return whether a later point of a polar reopens its geometry rather than re-initialising.

    A steady point whose text differs from its polar's first point before
    :data:`STEADY_RESTATE_ANCHORS` follows ``NEW_SIMULATION`` with its whole
    text (FR-403); an unsteady point never does, it is refused instead
    (:func:`refuse_unspliceable`).

    Parameters
    ----------
    first : JobPoint
        The polar's first point.
    point : JobPoint
        A later point of the same polar.

    Returns
    -------
    bool
        True for a steady point that cannot be restated from its anchor.
    """
    if not point.steady:
        return False
    try:
        _anchor_index(first, point)
    except CampaignConfigError:
        return True
    return False


def refuse_a_second_initialization(point: JobPoint) -> None:
    """Refuse a steady point whose script initialises the solver more than once (FR-403).

    A job's cumulative log is cut into its points' logs at every
    ``Solution cleared. Initialization removed.`` line, which the job's own
    ``REMOVE_INITIALIZATION`` and ``NEW_SIMULATION`` print once per point. An
    ``INITIALIZE_SOLVER`` on a solver already initialised prints that line too
    (MEASURED on 26.124 build 8172026: the recorded steady log
    ``tests/tier1_offline/fixtures/log_steady_job_two_solves_26.124.txt``
    carries it at line 67, between the two initialisations of a wing whose
    trailing edges were imported), so a point initialising twice would shift
    every later point of its job onto another point's log. A quasi-steady wheel
    of several clockings and a wake termination read from a file initialise
    more than once; such a polar stays out of a grouped job, named.

    Parameters
    ----------
    point : JobPoint
        A point of a job.

    Raises
    ------
    CampaignConfigError
        Naming the point and its count of initialisations, for a steady point
        initialising more than once.
    """
    if not point.steady:
        return
    count = sum(1 for line in _lines(point.text) if line.split()[:1] == [INITIALIZE_VERB])
    if count > 1:
        raise CampaignConfigError(
            f"point {point.run_id!r} initialises the solver {count} times, and each "
            "initialisation after the first prints the line a grouped job's log is cut at "
            "('Solution cleared. Initialization removed.'), so its log and every later "
            "point's could not be told apart; run this polar on its own."
        )


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
        else ``SET_SOLVER_UNSTEADY``; ``SOLVER_SET_AOA`` for a steady point.

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
    """Rule 1: the job's first point, the job's registrations in place of its own.

    A steady point registers nothing and its job registers nothing (FR-403), so
    its text is kept whole.
    """
    if point.steady:
        return _body(point)
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
    """Return where line ``cut`` of the point's text lands once its registrations are dropped.

    The lines before the cut are joined with a final line end, so a blank line
    right before the anchor (a steady point's ``SOLVER_SET_AOA`` follows one,
    FR-403) is counted and not lost to the split.
    """
    before = _lines(point.text)[:cut]
    return len(_without_registrations("\n".join(before) + "\n")[0]) if before else 0


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
            elif order == 0 or refreshes(lead, point):
                parts.append((point, "refresh", _point_lines(lead, point, "refresh")))
            else:
                parts.append((point, "reinit", _point_lines(lead, point, "reinit")))
    return parts


def _absolute_path_token(token: str, point_dir: PurePath, job_dir: PurePath) -> str:
    """Resolve one quoted or bare path, preserving quotes and absolute spellings."""
    quote = token[:1] if token.startswith(('"', "'")) and token[-1:] == token[:1] else ""
    bare = token[1:-1] if quote else token
    portable = bare.replace("\\", "/")
    if ".." in portable.split("/"):
        raise CampaignConfigError(f"path {token!r} contains '..'; a job needs absolute paths.")
    if is_absolute_target(bare):
        return token
    root = job_dir if portable.startswith("actions/") else point_dir
    return f"{quote}{root / portable}{quote}"


def _path_line_indices(lines: list[str], version: str) -> Iterable[tuple[int, str, bool]]:
    """Locate path arguments with the database, including keyword blocks and shell actions."""
    view = CommandRegistry.load().for_version(version)
    for index, line in enumerate(lines):
        words = line.split()
        if not words or words[0] not in view or _is_target_command(words[0]):
            continue
        entry = view[words[0]]
        shell = words[:2] == [helpers.UNSTEADY_ACTION_COMMAND, "COMMAND_LINE"]
        for offset, arg in enumerate(_line_args(entry), 1):
            if arg.type == "path" and index + offset < len(lines):
                yield index + offset, "", shell
        if entry.layout is Layout.KEYWORD_BLOCK:
            keys = {arg.name.upper() for arg in entry.args if arg.type == "path"}
            for offset, argument in enumerate(lines[index + 1 :], index + 1):
                if not argument.strip():
                    break
                key, separator, _ = argument.partition(" ")
                if key in keys and separator:
                    yield offset, key + separator, False


def _absolute_splice(
    lines: list[str], point_dir: PurePath, job_dir: PurePath, version: str
) -> list[str]:
    """Resolve the remaining per-point paths after the job registrations are spliced.

    Relative-token inventory from the single-point emitters:

    - ``_unsteady_actions``: ``actions/pfs_unsteady_actions.py``,
      ``actions/pfs_unsteady_exports.txt``, ``actions/pfs_walltime_clock.py``,
      ``actions/pfs_walltime_stop.txt``;
    - ``_geometry``: ``pfs_inlet_<index>_<sha16>.txt``, ``<stem>.wake_nodes.txt``,
      and the case's geometry path (normally already bound absolutely);
    - ``_actuator``: ``<profile stem>.actuator_profile.txt``;
    - ``_freestream`` / ``prepare_field``: ``pfs-field-<sha24>.txt`` or ``.dat``
      for converted fields, otherwise the bound source path.

    FSI and user actions are refused by the grouped planner. Non-action inputs
    belong to the point's working folder. Count/state/provenance files are not
    named in the emitted solver text; the action programs locate their own files.
    Geometry imports may be whole-line or keyword-block paths. Save/export paths
    have already passed ``absolutize_outputs``, including the cumulative log rule.
    Read the grammar rather than guessing extensions; a path can contain spaces.
    """
    out = lines.copy()
    for index, prefix, shell in _path_line_indices(lines, version):
        value = lines[index][len(prefix) :].strip()
        # Optional own-line arguments are absent on e.g. SET_FREESTREAM DEFAULT.
        # Never turn the following blank or command into a filename.
        if not value or value.split()[0] in CommandRegistry.load().commands:
            continue
        if shell:
            value = re.sub(
                r'"[^"]*"|\'[^\']*\'|[^\s"\']+',
                lambda match: _absolute_path_token(match[0], point_dir, job_dir),
                value,
            )
        else:
            value = _absolute_path_token(value, point_dir, job_dir)
        out[index] = prefix + value
    return out


def _job_block(polars: Sequence[JobPolar], version: str, *, walltime: bool) -> str:
    """Return the job's registration block: none for a steady job, refusing a mix (FR-403)."""
    kinds = {point.steady for polar in polars for point in polar.points}
    if len(kinds) > 1:
        raise CampaignConfigError(
            "a job holds steady polars or unsteady ones, never both: a steady point after an "
            "unsteady one in one solver instance is not measured, and the plan splits the two "
            "kinds into jobs of their own (FR-403); the job is not assembled."
        )
    if kinds == {True}:
        return ""
    exports = any(p.first_export_step is not None for polar in polars for p in polar.points)
    return registration_block(version, exports=exports, walltime=walltime)


def assemble_job(
    polars: Sequence[JobPolar],
    *,
    kind: JobKind,
    version: str,
    job_log: PurePath | None,
    job_dir: PurePath,
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
    job_dir : PurePath
        The job's absolute runtime folder, where its shared ``actions/`` lives.
    walltime : bool, optional
        Whether the job registers the clock pair; True by default, and a
        schedule without a deadline never fires it. A steady job registers
        nothing (FR-403).

    Returns
    -------
    JobScript
        The text, each point's block and every save and export target.

    Raises
    ------
    CampaignConfigError
        When there is no point, the polars mix steady and unsteady points, a
        point cannot be spliced, an output cannot be placed, or a save or
        export target stays relative.
    """
    if not polars or not all(polar.points for polar in polars):
        raise CampaignConfigError("a job needs at least one polar with at least one point.")
    block = _job_block(polars, version, walltime=walltime)
    lines: list[str] = []
    blocks: list[JobBlock] = []
    for point, transition, part in _parts(polars, block):
        refuse_a_second_initialization(point)
        part = _absolute_splice(part, point.datapoint_dir, job_dir, version)
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
