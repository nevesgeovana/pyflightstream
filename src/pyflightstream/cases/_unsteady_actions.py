"""The unsteady solver actions a march registers: the step counter, its exports, the clock.

Moved out of :mod:`pyflightstream.cases.workflows` in 0.33.0, which still
exports every name here, so the public path is unchanged.

THE STEP COUNTER ON EVERY MARCH (FR-314). Until 0.32.0 the counter was
registered only on a row asking for per-step exports (PFS-2031.18), and the
progress bar of a local run (FR-129), which reads the counter's file, showed
nothing on a long unsteady run without them. Every unsteady row now registers
it: with the exports script after it where the row asks for per-step exports,
exactly as before; alone, COUNTING ONLY, where it asks none. The run layer
writes a count-only program for such a row (:mod:`pyflightstream.run._actions_counter`),
which rewrites no exports file and so triggers no exports script. That the
counter leaves a row's results unchanged is not measured here; the licensed
round of FR-314 states the comparison.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyflightstream.cases import CampaignConfigError
from pyflightstream.script import Script, helpers

__all__ = [
    "UNSTEADY_ACTION_COUNT",
    "UNSTEADY_ACTION_PROGRAM",
    "UNSTEADY_ACTION_SCRIPT",
    "UNSTEADY_COUNTER_ACTION",
    "UNSTEADY_EXPORTS_ACTION",
    "WALLTIME_CLOCK_ACTION",
    "WALLTIME_CLOCK_PROGRAM",
    "WALLTIME_CLOCK_STATE",
    "WALLTIME_STOP_ACTION",
    "WALLTIME_STOP_SCRIPT",
    "action_interpreter",
    "documents_actions",
    "register_unsteady_actions",
    "unsteady_action_command_line",
    "walltime_clock_command_line",
]

#: The names the two registration lines carry, in creation order. The
#: solver runs actions in creation order and the order cannot be changed
#: afterwards, so the counter is registered FIRST: it rewrites the file
#: before the SCRIPT action of the same step reads it.
UNSTEADY_COUNTER_ACTION = "pfs_unsteady_counter"
UNSTEADY_EXPORTS_ACTION = "pfs_unsteady_exports"
#: The program, the file it rewrites, and the count it keeps, relative to
#: the simulation folder. Under ``actions/`` and NOT under ``inputs/``:
#: ``inputs/`` is a junction to the workspace geometry library whenever
#: the geometry came from it (PFS-2029.17), and a file written there
#: would land in the library. The two are staged inputs all the same:
#: the record carries their sha256 beside the geometry's.
UNSTEADY_ACTION_PROGRAM = "actions/pfs_unsteady_actions.py"
UNSTEADY_ACTION_SCRIPT = "actions/pfs_unsteady_exports.txt"
UNSTEADY_ACTION_COUNT = "actions/pfs_unsteady_actions.count"

#: FR-98. THE CLOCK PAIR, and it is the SAME SHAPE as the
#: counter pair above because it has the same problem: a python that can
#: compute cannot also be the command list the solver runs, so one writes
#: and one is read.
#:
#: The counter is (1), the exports script is (2), the clock is (3) and the
#: stop script is (4). Since 0.33.0 (FR-314) a row that states no export
#: threshold registers the counter alone, so the clock pair takes (2) and
#: (3), which is why the positions are conditional and not fixed.
WALLTIME_CLOCK_ACTION = "pfs_walltime_clock"
WALLTIME_STOP_ACTION = "pfs_walltime_stop"

#: The program, the file it rewrites, and the state it keeps, relative to
#: the simulation folder. Under ``actions/`` for the reason the counter's
#: files are: ``inputs/`` may be a junction into the geometry library.
WALLTIME_CLOCK_PROGRAM = "actions/pfs_walltime_clock.py"
WALLTIME_STOP_SCRIPT = "actions/pfs_walltime_stop.txt"
WALLTIME_CLOCK_STATE = "actions/pfs_walltime_clock.json"


def action_interpreter(interpreter: str) -> str:
    """Choose the sibling Windows GUI interpreter before any native action runs."""
    if sys.platform != "win32":
        return interpreter
    windowless = Path(interpreter).with_name("pythonw.exe")
    if not windowless.is_file():
        raise CampaignConfigError(
            f"Windows solver actions require the sibling pythonw.exe: {windowless}; "
            "use a Python installation that provides it before preparing the run"
        )
    return str(windowless)


def unsteady_action_command_line(interpreter: str = sys.executable) -> str:
    """Return the shell line the COMMAND_LINE action runs: the interpreter, then the program.

    Both quoted, because an interpreter path with a space in it is one
    argument. The interpreter is the one building the script, which is
    the one the run layer names when it writes the program, so the line
    the solver runs and the program it runs agree on which Python. On Windows,
    its existing pythonw.exe sibling prevents a console per callback.
    """
    return f'"{action_interpreter(interpreter)}" "{UNSTEADY_ACTION_PROGRAM}"'


def walltime_clock_command_line() -> str:
    """Return the COMMAND_LINE the clock action registers: interpreter, then program."""
    interpreter = action_interpreter(sys.executable)
    return f'"{interpreter}" "{WALLTIME_CLOCK_PROGRAM}"'


def documents_actions(script: Script) -> bool:
    """Whether the script's build documents the unsteady solver action command.

    Read from the committed command database: 26.122 and later document it,
    26.121 and earlier do not. A build that does not marches a row without
    per-step exports as one single march, with no action and so with no
    counter: a count-only counter is registered only where the build can run
    it, and a row asking per-step exports there is refused by the emitter.
    """
    try:
        script.entry(helpers.UNSTEADY_ACTION_COMMAND)
    except LookupError:
        return False
    return True


def register_unsteady_actions(
    script: Script,
    threshold: object | None,
    *,
    walltime: bool = False,
) -> None:
    """Register the actions this unsteady row needs, in creation order.

    THE COUNTER FIRST, ON EVERY ROW WHOSE BUILD DOCUMENTS THE ACTIONS
    (FR-314, :func:`documents_actions`): it is what the progress bar of a
    local run reads. The exports script follows it only where the row
    states an export threshold (``threshold``, the row's
    :class:`~pyflightstream.cases.workflows.UnsteadyExportThreshold`), as it
    did before; without one the counter only counts. Then the wall clock
    and its stop script, where the row states a wall clock.

    EACH PAIR IS A WRITER AND A READER, and the writer is registered first
    because the solver runs actions in creation order and cannot be told
    otherwise: the python rewrites the script file before the SCRIPT action
    of the same step reads it.

    Both SCRIPT files are parked EMPTY. Until the count reaches its
    threshold, and until the clock reaches its margin, the solver must find
    a file with no command in it; the run layer writes what is parked
    before the solver starts (PFS-2031.13). A build that does not document
    the action command is refused by the emitter, naming the command and
    the builds that do.
    """
    if threshold is not None or documents_actions(script):
        helpers.unsteady_action(
            script,
            name=UNSTEADY_COUNTER_ACTION,
            kind="COMMAND_LINE",
            filename=unsteady_action_command_line(),
        )
    if threshold is not None:
        helpers.unsteady_action(
            script,
            name=UNSTEADY_EXPORTS_ACTION,
            kind="SCRIPT",
            filename=UNSTEADY_ACTION_SCRIPT,
            action_script="",
        )
    if walltime:
        helpers.unsteady_action(
            script,
            name=WALLTIME_CLOCK_ACTION,
            kind="COMMAND_LINE",
            filename=walltime_clock_command_line(),
        )
        helpers.unsteady_action(
            script,
            name=WALLTIME_STOP_ACTION,
            kind="SCRIPT",
            filename=WALLTIME_STOP_SCRIPT,
            action_script="",
        )
