"""The action programs of a grouped job: one counter and one clock for many points (FR-B5a, FR-B19).

A grouped job (``--batch`` or ``--polar-sweep``, 0.35.0) runs several points
in ONE solver instance. The unsteady actions are registered ONCE per instance
(MEASURED, DESIGN-0350 Test 2: the actions survive ``REMOVE_INITIALIZATION``
and ``NEW_SIMULATION``, and a second registration runs every action twice per
step), so the counter and the clock the job registers serve every point of it.
The solver hands an action nothing, so these programs re-index the job's
invocation count into (point, the point's own step) from a schedule written
beside them, and write each point's own count and clock state into the
point's own folder, in the shape a point run alone leaves.

Both programs stand alone: no package import, every path taken from their
own file's folder (the job's ``actions/``) and from the schedule, every write
with an explicit LF, like ``run/_actions_counter.py:TEMPLATE``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import PurePath, PureWindowsPath
from typing import Protocol

from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_SCRIPT,
    WALLTIME_CLOCK_STATE,
    WALLTIME_STOP_SCRIPT,
)

from ._vocabulary import CUMULATIVE_LOG_SUFFIX

__all__ = [
    "JOB_CURRENT",
    "JOB_PROGRESS",
    "JOB_SCHEDULE",
    "SchedulePoint",
    "absolute_output_lines",
    "is_absolute_target",
    "job_schedule",
    "render_job_clock_program",
    "render_job_counter_program",
]

#: The schedule the two programs read, relative to the job folder.
JOB_SCHEDULE = "actions/pfs_batch_schedule.json"
#: The configuration of the point now running, rewritten at its first step.
JOB_CURRENT = "actions/pfs_batch_current.json"
#: The job's progress, rewritten at every step; collect reads its mismatches.
JOB_PROGRESS = "actions/pfs_batch_progress.json"

#: The schema of the schedule, so a reader refuses one it does not know.
SCHEDULE_SCHEMA = "pyfs-batch-schedule/1"


class SchedulePoint(Protocol):
    """The fields of a job point the schedule reads (``JobPoint`` satisfies it)."""

    @property
    def run_id(self) -> str:
        """The point's run id."""
        ...

    @property
    def datapoint_dir(self) -> PurePath:
        """The point's absolute datapoint folder."""
        ...

    @property
    def outputs(self) -> tuple[str, ...]:
        """The outputs its script names, relative."""
        ...

    @property
    def action_exports(self) -> str:
        """Its per-step export lines, relative."""
        ...

    @property
    def first_export_step(self) -> int | None:
        """The first step of its per-step exports, from its own step 1."""
        ...

    @property
    def stop_text(self) -> str:
        """What the clock writes when it stops this point, relative."""
        ...

    @property
    def time_steps(self) -> int:
        """The time steps the point marches."""
        ...


def is_absolute_target(target: str) -> bool:
    """Whether a script's path argument is absolute, on Windows or on a POSIX cluster.

    Parameters
    ----------
    target : str
        A path argument as the script writes it.

    Returns
    -------
    bool
        True for a drive or UNC path and for a path from the POSIX root.
    """
    return target.startswith("/") or PureWindowsPath(target).is_absolute()


def _log_stem(name: str) -> str:
    """Return the stem of a point's log name: ``<stem>_log.txt`` gives ``<stem>``."""
    return name.removesuffix("_log.txt") if name.endswith("_log.txt") else PurePath(name).stem


def absolute_output_lines(text: str, datapoint_dir: PurePath, names: Iterable[str]) -> str:
    """Return ``text`` with every line naming an output made absolute under ``datapoint_dir``.

    A line equal to one of ``names`` becomes ``<datapoint_dir>/<name>``. The
    target of an ``EXPORT_LOG`` (the line after it) becomes
    ``<datapoint_dir>/<stem>`` followed by
    :data:`~pyflightstream.cases.workflows._vocabulary.CUMULATIVE_LOG_SUFFIX`,
    because a log exported inside a job holds every point run before it
    (MEASURED); collect writes the point's own log from its slice.

    Parameters
    ----------
    text : str
        A script text, an exports script or a stop text.
    datapoint_dir : PurePath
        The point's absolute datapoint folder.
    names : iterable of str
        The point's output names as its script names them, relative.

    Returns
    -------
    str
        The text with those lines replaced; every other line unchanged.
    """
    wanted = set(names)
    lines = text.split("\n")
    out: list[str] = []
    for index, line in enumerate(lines):
        bare = line.strip()
        after_log = index > 0 and lines[index - 1].strip() == "EXPORT_LOG"
        if after_log and bare and not is_absolute_target(bare):
            out.append(str(datapoint_dir / (_log_stem(bare) + CUMULATIVE_LOG_SUFFIX)))
        elif bare in wanted:
            out.append(str(datapoint_dir / bare))
        else:
            out.append(line)
    return "\n".join(out)


def _saved_simulation(point: SchedulePoint) -> str | None:
    """Return the absolute path of the simulation the point saves, or None when it saves none."""
    for name in point.outputs:
        if name.lower().endswith(".fsm"):
            return str(point.datapoint_dir / name)
    return None


def job_schedule(points: Sequence[SchedulePoint], *, deadline_s: float | None) -> dict[str, object]:
    """Return the schedule the job's counter and clock read, every path absolute.

    Parameters
    ----------
    points : sequence of SchedulePoint
        The job's points in the order the job runs them (``JobPoint``).
    deadline_s : float or None
        The job's elapsed time at which the clock stops the current point
        (the job's walltime minus its margin); None for a job without one.

    Returns
    -------
    dict
        ``{"schema", "deadline_s", "total_steps", "points": [...]}``, each
        point with ``run_id``, ``datapoint_dir``, ``time_steps``,
        ``first_export_step``, ``exports``, ``stop_text`` and ``fsm``.
    """
    entries: list[dict[str, object]] = []
    for point in points:
        entries.append(
            {
                "run_id": point.run_id,
                "datapoint_dir": str(point.datapoint_dir),
                "time_steps": point.time_steps,
                "first_export_step": point.first_export_step,
                "exports": absolute_output_lines(
                    point.action_exports, point.datapoint_dir, point.outputs
                ),
                "stop_text": absolute_output_lines(
                    point.stop_text, point.datapoint_dir, point.outputs
                ),
                "fsm": _saved_simulation(point),
            }
        )
    return {
        "schema": SCHEDULE_SCHEMA,
        "deadline_s": deadline_s,
        "total_steps": sum(point.time_steps for point in points),
        "points": entries,
    }


#: The job's counter. Registered FIRST, so it runs before the exports SCRIPT
#: and the clock of the same step: it decides which point is running and
#: which of its steps this is, and everything after it reads that.
COUNTER_TEMPLATE = '''"""Counter of the unsteady solver actions of one pyflightstream grouped job.

Written by pyflightstream (FR-B5a, FR-B19). The solver runs this program after
every unsteady time step of the job and passes it nothing. The job count kept
in COUNT_FILE is the job's step; the schedule turns it into the point running
and that point's own step, writes the point's own count where a point run
alone writes it, and rewrites the exports script with that point's exports
from its own first export step. At a point's first step it records the point
as current, empties the exports and the stop scripts, and checks that the
previous point saved its simulation. Every path is taken from this file's own
location and from the schedule, never from the working directory.
"""

import json
import time
from pathlib import Path

#: Written by pyflightstream when the job was assembled.
TIME_ITERATIONS = <TIME_ITERATIONS>
INTERPRETER = <INTERPRETER>

HERE = Path(__file__).resolve().parent
JOB = HERE.parent
SCHEDULE = JOB / <SCHEDULE>
CURRENT = JOB / <CURRENT>
PROGRESS = JOB / <PROGRESS>
COUNT_FILE = JOB / <COUNT>
EXPORTS_FILE = JOB / <EXPORTS>
STOP_FILE = JOB / <STOP>
POINT_COUNT = <COUNT>


def read(path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\\n")


def locate(points, count):
    """Return (index, step): the point the job count falls in and its own step."""
    before = 0
    for index, point in enumerate(points):
        if count <= before + int(point["time_steps"]):
            return index, count - before
        before += int(point["time_steps"])
    last = len(points) - 1
    return last, count - (before - int(points[last]["time_steps"]))


def start_point(points, index, now):
    """The point's first step: record it, empty both scripts, check the previous save."""
    point = points[index]
    write(EXPORTS_FILE, "")
    write(STOP_FILE, "")
    current = {
        "point": index + 1,
        "run_id": point["run_id"],
        "datapoint_dir": point["datapoint_dir"],
        "first_export_step": point["first_export_step"],
        "exports": point["exports"],
        "stop_text": point["stop_text"],
        "started_at": now,
    }
    write(CURRENT, json.dumps(current, indent=2))
    if index == 0:
        return None
    saved = points[index - 1]["fsm"]
    if saved is not None and not Path(saved).is_file():
        return {"previous": index, "point": index + 1, "missing": saved}
    return None


def main():
    points = read(SCHEDULE, {})["points"]
    count = int(read(COUNT_FILE, {"count": 0})["count"]) + 1
    write(COUNT_FILE, json.dumps({"count": count}))
    index, step = locate(points, count)
    point = points[index]
    progress = read(PROGRESS, {})
    mismatches = list(progress.get("mismatches", []))
    if step == 1:
        found = start_point(points, index, time.time())
        if found is not None:
            mismatches.append(found)
    write(Path(point["datapoint_dir"]) / POINT_COUNT, json.dumps({"count": step}))
    first = point["first_export_step"]
    exporting = first is not None and step >= int(first)
    write(EXPORTS_FILE, point["exports"] if exporting else "")
    progress = {
        "point": index + 1,
        "run_id": point["run_id"],
        "step": step,
        "job_count": count,
        "mismatch": bool(mismatches),
        "mismatches": mismatches,
    }
    write(PROGRESS, json.dumps(progress, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

#: The job's clock (D3). Its start is its first invocation; when the job's
#: elapsed time reaches the schedule's deadline it writes the CURRENT point's
#: stop text into the stop script, once, and records where it stopped in the
#: job's state and in the point's own, in the shape a point run alone leaves.
CLOCK_TEMPLATE = '''"""Wall clock of one pyflightstream grouped job.

Written by pyflightstream (FR-B5a, D3). The solver cannot be asked how long
the job has been going, so this program keeps its own state: the first
invocation writes the start, every later one asks whether the job's elapsed
time reached the schedule's deadline. When it does, the CURRENT point's stop
text goes into the stop script, once, and the point's own clock state records
the step it stopped at. Every path is taken from this file's own location and
from the schedule and the counter's current point, never from the working
directory.
"""

import json
import time
from pathlib import Path

INTERPRETER = <INTERPRETER>

HERE = Path(__file__).resolve().parent
JOB = HERE.parent
SCHEDULE = JOB / <SCHEDULE>
CURRENT = JOB / <CURRENT>
PROGRESS = JOB / <PROGRESS>
STATE = JOB / <STATE>
STOP_FILE = JOB / <STOP>
POINT_STATE = <STATE>


def read(path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\\n")


def main():
    deadline = read(SCHEDULE, {}).get("deadline_s")
    current = read(CURRENT, None)
    step = int(read(PROGRESS, {}).get("step", 0))
    now = time.time()
    state = {"started_at": None, "steps": 0, "fired": False}
    state.update(read(STATE, {}))
    if state["started_at"] is None:
        state["started_at"] = now
    state["steps"] = int(state["steps"]) + 1
    elapsed = now - float(state["started_at"])
    state["elapsed_s"] = elapsed
    fire = deadline is not None and not state["fired"] and elapsed >= float(deadline)
    if fire and current is not None:
        write(STOP_FILE, current["stop_text"])
        state["fired"] = True
        state["stopped_at"] = {
            "step": state["steps"], "elapsed_s": elapsed, "point": current["point"]
        }
    write(STATE, json.dumps(state, indent=2))
    if current is None:
        return 0
    own_path = Path(current["datapoint_dir"]) / POINT_STATE
    own = read(own_path, {"fired": False})
    own["started_at"] = current["started_at"]
    own["steps"] = step
    own["elapsed_s"] = now - float(current["started_at"])
    if fire:
        own["fired"] = True
        own["stopped_at"] = {"step": step, "elapsed_s": own["elapsed_s"]}
    write(own_path, json.dumps(own, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _filled(template: str, values: dict[str, object]) -> str:
    """Return ``template`` with each ``<NAME>`` replaced by the repr of its value."""
    text = template
    for name, value in values.items():
        text = text.replace(f"<{name}>", repr(value))
    return text


def render_job_counter_program(*, total_steps: int, interpreter: str) -> str:
    """Return the job's counter program, written where the counter registration points.

    Parameters
    ----------
    total_steps : int
        The time steps of every point of the job, summed: the local progress
        bar reads ``TIME_ITERATIONS`` off the program as it reads a point's.
    interpreter : str
        The Python the registration line names, recorded in the program.

    Returns
    -------
    str
        The program text.
    """
    return _filled(
        COUNTER_TEMPLATE,
        {
            "TIME_ITERATIONS": int(total_steps),
            "INTERPRETER": interpreter,
            "SCHEDULE": JOB_SCHEDULE,
            "CURRENT": JOB_CURRENT,
            "PROGRESS": JOB_PROGRESS,
            "COUNT": UNSTEADY_ACTION_COUNT,
            "EXPORTS": UNSTEADY_ACTION_SCRIPT,
            "STOP": WALLTIME_STOP_SCRIPT,
        },
    )


def render_job_clock_program(*, interpreter: str) -> str:
    """Return the job's clock program, written where the clock registration points.

    Parameters
    ----------
    interpreter : str
        The Python the registration line names, recorded in the program.

    Returns
    -------
    str
        The program text; its deadline is read from the schedule.
    """
    return _filled(
        CLOCK_TEMPLATE,
        {
            "INTERPRETER": interpreter,
            "SCHEDULE": JOB_SCHEDULE,
            "CURRENT": JOB_CURRENT,
            "PROGRESS": JOB_PROGRESS,
            "STATE": WALLTIME_CLOCK_STATE,
            "STOP": WALLTIME_STOP_SCRIPT,
        },
    )
