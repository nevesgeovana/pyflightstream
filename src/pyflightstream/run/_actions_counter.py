"""The counter program a point's COMMAND_LINE action runs (PFS-2031.18).

The author's design of 2026-09-08, GeoversePlan design 67. The solver runs the
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
"""

from __future__ import annotations

from pathlib import PurePosixPath

from pyflightstream.cases.workflows import (
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_SCRIPT,
    UnsteadyExportThreshold,
)

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
    COUNT_FILE.write_text(json.dumps(current), encoding="utf-8")
    SCRIPT_FILE.write_text(EXPORTS if current["exporting"] else "", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_program(threshold: UnsteadyExportThreshold, *, interpreter: str) -> str:
    r"""Return the program text for one point.

    Parameters
    ----------
    threshold : UnsteadyExportThreshold
        The resolved threshold of the row, carrying the step in degrees,
        the rotor speed, the clock and the per-step export lines.
    interpreter : str
        The Python the registration line names, recorded in the program
        so a reader of the folder can see which one ran it.

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
        "THRESHOLD_FORM": threshold.stated_form,
        "THRESHOLD": threshold.stated_value,
        "EXPORTS": threshold.exports,
        "INTERPRETER": interpreter,
        "COUNT_NAME": PurePosixPath(UNSTEADY_ACTION_COUNT).name,
        "SCRIPT_NAME": PurePosixPath(UNSTEADY_ACTION_SCRIPT).name,
    }
    text = TEMPLATE
    for token, value in values.items():
        text = text.replace(f"<{token}>", repr(value))
    return text
