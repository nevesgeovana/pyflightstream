"""The counter program a point's COMMAND_LINE action runs (PFS-2031.18).

The design of 2026-09-08, GeoversePlan design 67. The solver runs the
program after every unsteady time step and hands it nothing: no argument,
no step index, no environment (RPT-041 finding 4). So the program keeps
the count itself, in a file beside itself, derives the physical time, the
azimuth and the revolution from the count with the step and the rotor
speed the package wrote into it at build time, and rewrites the SCRIPT
action's file: empty until the count reaches the threshold, the row's
per-step exports from then on. The solver re-reads that file on every
invocation (finding 1) and stamps each export with the iteration (finding
3), so one program and one file give an export per step from the
threshold to the end.

The template is a string and not a module of the package, because the
written copy runs under the interpreter named on the registration line,
in a process the solver starts, with nothing of this package importable:
it must stand alone. Every constant is spelled with ``repr``, so a path
with backslashes and a script text with newlines survive the substitution
without an escaping rule of their own.

A ROW WITH NO PER-STEP EXPORT GETS A COUNTER TOO (FR-314): the progress bar
of a local run (FR-129) reads the count, and until 0.33.0 only a row asking
for per-step exports had one. Such a row's program is
:data:`COUNT_ONLY_TEMPLATE`: it keeps the count and rewrites nothing else, so
no exports file exists and no exports script runs. :func:`stage_counter`
writes whichever program the script's registration names.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import (
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    UNSTEADY_COUNTER_ACTION,
    UnsteadyExportThreshold,
    normal_probe_creation,
    unsteady_counter_steps,
    unsteady_export_threshold,
)
from pyflightstream.script import Script

#: The written program. The tokens in angle brackets are replaced by
#: :func:`render_program`; nothing else in the text is touched.
TEMPLATE = '''"""Counter of the unsteady solver actions of one pyflightstream point.

Written by pyflightstream (PFS-2031.18). The solver runs this program
after every unsteady time step and passes it nothing, so the count of
invocations kept in COUNT_FILE is the time step, exactly (RPT-041). Each
invocation increments the count, derives the physical time, the azimuth
and the revolution from it, and rewrites SCRIPT_FILE: empty until the
count reaches THRESHOLD, EXPORTS from then on. Every path is taken from
this file's own location, never from the working directory.
"""

import json
from pathlib import Path

#: Written by pyflightstream at build time, from the row.
STEP_DEG = <STEP_DEG>
RPM = <RPM>
DELTA_TIME_S = <DELTA_TIME_S>
TIME_ITERATIONS = <TIME_ITERATIONS>
THRESHOLD_FORM = <THRESHOLD_FORM>
THRESHOLD = <THRESHOLD>
EXPORTS = <EXPORTS>
INTERPRETER = <INTERPRETER>

HERE = Path(__file__).resolve().parent
COUNT_FILE = HERE / <COUNT_NAME>
SCRIPT_FILE = HERE / <SCRIPT_NAME>


def state(count):
    """What the count means, in the units the row was designed in."""
    azimuth = None if STEP_DEG is None else count * STEP_DEG
    revolutions = None if azimuth is None else azimuth / 360.0
    reached = count if THRESHOLD_FORM == "iterations" else revolutions
    return {
        "count": count,
        "time_s": count * DELTA_TIME_S,
        "azimuth_deg": azimuth,
        "revolutions": revolutions,
        "exporting": reached is not None and reached + 1e-9 >= THRESHOLD,
    }


def main():
    count = 0
    if COUNT_FILE.is_file():
        count = int(json.loads(COUNT_FILE.read_text(encoding="utf-8"))["count"])
    current = state(count + 1)
    COUNT_FILE.write_text(json.dumps(current), encoding="utf-8", newline="\\n")
    SCRIPT_FILE.write_text(EXPORTS if current["exporting"] else "", encoding="utf-8", newline="\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


#: FR-417 R7: what the program of a row with normal probes and a per-step window
#: writes instead of the plain rewrite. The probe points are created after the
#: march, which the window's steps precede, so the first exporting step writes
#: the creation lines (``DELETE_PROBE_POINTS`` first, so a continued run that
#: already holds them does not hold them twice) before the exports, and every
#: later step updates and exports them.
_PLAIN_REWRITE = (
    '    SCRIPT_FILE.write_text(EXPORTS if current["exporting"] else "", '
    'encoding="utf-8", newline="\\n")\n'
)
_FIRST_STEP_CREATES = (
    '    first = current["exporting"] and not state(count)["exporting"]\n'
    '    text = (CREATE + EXPORTS) if first else (EXPORTS if current["exporting"] else "")\n'
    '    SCRIPT_FILE.write_text(text, encoding="utf-8", newline="\\n")\n'
)


def render_program(
    threshold: UnsteadyExportThreshold, *, interpreter: str, creation: str = ""
) -> str:
    r"""Return the program text for one point.

    Parameters
    ----------
    threshold : UnsteadyExportThreshold
        The resolved threshold of the row, carrying the step in degrees,
        the rotor speed, the clock and the per-step export lines.
    interpreter : str
        The Python the registration line names, recorded in the program
        so a reader of the folder can see which one ran it.
    creation : str, optional
        The lines that create the row's normal probe points (FR-417 R7),
        written on the first exporting step only; empty, the program is the
        one every other row gets.

    Returns
    -------
    str
        The program, ready to be written where the registration line
        points.

    Examples
    --------
    >>> from pyflightstream.cases.workflows import UnsteadyExportThreshold
    >>> threshold = UnsteadyExportThreshold(
    ...     stated_form="iterations", stated_value=4.0, first_step=4,
    ...     time_iterations=8, delta_time_s=0.01, step_deg=None, rpm=None,
    ...     exports="EXPORT_SOLVER_ANALYSIS_SPREADSHEET\\nloads.txt\\n",
    ... )
    >>> "THRESHOLD = 4.0" in render_program(threshold, interpreter="python")
    True
    """
    values = {
        "STEP_DEG": threshold.step_deg,
        "RPM": threshold.rpm,
        "DELTA_TIME_S": threshold.delta_time_s,
        "TIME_ITERATIONS": threshold.time_iterations,
        "THRESHOLD_FORM": threshold.program_form,
        "THRESHOLD": threshold.program_value,
        "EXPORTS": threshold.exports,
        "INTERPRETER": interpreter,
        "COUNT_NAME": PurePosixPath(UNSTEADY_ACTION_COUNT).name,
        "SCRIPT_NAME": PurePosixPath(UNSTEADY_ACTION_SCRIPT).name,
    }
    text = TEMPLATE
    if creation:
        text = text.replace("EXPORTS = <EXPORTS>\n", "EXPORTS = <EXPORTS>\nCREATE = <CREATE>\n")
        text = text.replace(_PLAIN_REWRITE, _FIRST_STEP_CREATES)
        values["CREATE"] = creation
    for token, value in values.items():
        text = text.replace(f"<{token}>", repr(value))
    return text


#: The program of a row that asks no per-step export (FR-314): the count and
#: nothing else. The tokens in angle brackets are replaced by
#: :func:`render_count_program`.
COUNT_ONLY_TEMPLATE = '''"""Step counter of one pyflightstream point, counting only.

Written by pyflightstream (FR-314). The solver runs this program after
every unsteady time step and passes it nothing, so the count of
invocations kept in COUNT_FILE is the time step, exactly (RPT-041). Each
invocation increments the count and writes nothing else: the row asks no
per-step export. Every path is taken from this file's own location.
"""

import json
from pathlib import Path

#: Written by pyflightstream at build time, from the row.
TIME_ITERATIONS = <TIME_ITERATIONS>
INTERPRETER = <INTERPRETER>

HERE = Path(__file__).resolve().parent
COUNT_FILE = HERE / <COUNT_NAME>


def main():
    count = 0
    if COUNT_FILE.is_file():
        count = int(json.loads(COUNT_FILE.read_text(encoding="utf-8"))["count"])
    COUNT_FILE.write_text(json.dumps({"count": count + 1}), encoding="utf-8", newline="\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_count_program(time_iterations: int, *, interpreter: str) -> str:
    """Return the count-only program of a point whose row asks no per-step export.

    Parameters
    ----------
    time_iterations : int
        The time steps the point marches, which the progress bar counts to.
    interpreter : str
        The Python the registration line names, recorded in the program.

    Returns
    -------
    str
        The program, ready to be written where the registration line points.

    Examples
    --------
    >>> "TIME_ITERATIONS = 40" in render_count_program(40, interpreter="python")
    True
    """
    values = {
        "TIME_ITERATIONS": int(time_iterations),
        "INTERPRETER": interpreter,
        "COUNT_NAME": PurePosixPath(UNSTEADY_ACTION_COUNT).name,
    }
    text = COUNT_ONLY_TEMPLATE
    for token, value in values.items():
        text = text.replace(f"<{token}>", repr(value))
    return text


def stage_counter(
    work_dir: Path,
    script: Script,
    point_case: SimCase,
    fs_version: str,
    inputs_sha256: Mapping[str, str],
) -> dict[str, object] | None:
    """Write the counter program a point's script registers, and return the record fields.

    PFS-2031.18, FR-314. The threshold is resolved from the case again (the
    same function the builder called, so the two agree); with one, the
    program counts and rewrites the exports file, and the record states the
    export window; without one, the count-only program is written. Either is
    rendered with the interpreter the registration line names and hashed into
    the record as the staged input it is. The count file of an EARLIER point
    of the same case is removed: every point runs in the same folder, and a
    count carried over would start the second point past its first step.

    Returns
    -------
    dict or None
        The fields the record gains (``inputs_sha256``, ``action_program``
        and, with a threshold, ``action_script`` and ``export_window``);
        None when the script registers no counter.
    """
    if not any(use.name == UNSTEADY_COUNTER_ACTION for use in script.unsteady_actions):
        return None
    threshold = unsteady_export_threshold(point_case, version=fs_version)
    program = work_dir / UNSTEADY_ACTION_PROGRAM
    program.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(
        program,
        render_program(
            threshold,
            interpreter=sys.executable,
            creation=normal_probe_creation(point_case, fs_version),
        )
        if threshold is not None
        else render_count_program(unsteady_counter_steps(point_case), interpreter=sys.executable),
    )
    (work_dir / UNSTEADY_ACTION_COUNT).unlink(missing_ok=True)
    hashes = {**inputs_sha256, UNSTEADY_ACTION_PROGRAM: file_sha256(program)}
    fields: dict[str, object] = {"inputs_sha256": hashes, "action_program": UNSTEADY_ACTION_PROGRAM}
    if threshold is None:
        return fields
    hashes[UNSTEADY_ACTION_SCRIPT] = file_sha256(work_dir / UNSTEADY_ACTION_SCRIPT)
    fields["action_script"] = UNSTEADY_ACTION_SCRIPT
    # What the row stated and the step the exports begin on, so a reader of the
    # manifest answers "from which step" without opening the counter program
    # (the release review of 2026-09-09), and the clock the program ran with, so
    # the series tables compute each step's time and azimuth by the same
    # arithmetic (PFS-2031.18.01); a rotorless row has no azimuth step.
    window: dict[str, object] = {
        "stated_form": threshold.stated_form,
        "stated_value": threshold.stated_value,
        "first_step": threshold.first_step,
        "time_iterations": threshold.time_iterations,
        "delta_time_s": threshold.delta_time_s,
    }
    if threshold.step_deg is not None:
        window["step_deg"] = threshold.step_deg
    fields["export_window"] = window
    return fields
