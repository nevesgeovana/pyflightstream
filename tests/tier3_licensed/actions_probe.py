"""The program the action re-read probe runs after every unsteady time step.

GOAL-012 item 7b, PFS-2031.08. The row ``6001`` of ``matriz_actions.fs``
registers two actions on the solver before ``INITIALIZE_SOLVER``, in this
order: a ``COMMAND_LINE`` action running ``actions_probe.cmd``, which runs
this module, and a ``SCRIPT`` action pointing at ``actions/reread.txt`` in
the row's simulation folder. Each invocation of this module appends one
record to ``actions_probe.log`` and REWRITES ``actions/reread.txt`` so that
it exports a spreadsheet named for the invocation number. The question the
run answers is whether the solver re-reads the SCRIPT action's file on every
invocation, or reads it once at registration:

* YES: the simulation folder holds exports named for distinct invocations.
* NO: it holds the export the registration-time text names, and no other.

The verdict is read from the files the run leaves, never from this module's
own log alone, and ``python -m tests.tier3_licensed.actions_probe --verdict``
prints it as JSON for the report and the tier-3 test to quote.

Every path is derived from this file's own location and the row's fixed POL,
because nothing documented says which directory the solver runs an action
from, whether it passes arguments, or what environment the child gets
(RPT-030); the record each invocation appends carries those three so the
same run answers them too.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: The POL of the probe row in matriz_actions.fs, which fixes the simulation folder.
PROBE_POL = "6001"
SIM = HERE / "sims" / f"sim_{PROBE_POL}"
LOG = SIM / "actions_probe.log"
#: The file the SCRIPT action points at, rewritten on every invocation.
ACTION_SCRIPT = SIM / "actions" / "reread.txt"
EXPORT_STEM = "probe_export"


def export_script(tag: str) -> str:
    """The child script exporting the loads spreadsheet named for ``tag``."""
    target = SIM / f"{EXPORT_STEM}_{tag}.txt"
    return f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{target}\n"


def initial_script() -> str:
    """What the SCRIPT action's file says at registration, before any invocation."""
    return export_script("initial")


def invocations() -> int:
    if not LOG.is_file():
        return 0
    return sum(1 for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip())


def invoke() -> int:
    """One invocation: log the context, rewrite the action script for this count."""
    SIM.mkdir(parents=True, exist_ok=True)
    count = invocations() + 1
    record = {
        "invocation": count,
        "argv": sys.argv[1:],
        "cwd": os.getcwd(),
        "time": time.time(),
        "environment_mentioning_the_solver": sorted(
            key for key in os.environ if "FLIGHTSTREAM" in key.upper()
        ),
    }
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    ACTION_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    ACTION_SCRIPT.write_text(export_script(f"{count:03d}"), encoding="utf-8")
    return 0


def verdict() -> dict[str, object]:
    """Read the run folder and say what it shows."""
    exports = sorted(path.name for path in SIM.glob(f"{EXPORT_STEM}_*.txt"))
    initial = f"{EXPORT_STEM}_initial.txt"
    numbered = [name for name in exports if name != initial]
    count = invocations()
    if count == 0:
        word = "NOT_RUN"
        meaning = (
            "the COMMAND_LINE action never ran this module: no invocation was logged, so "
            "nothing here says anything about the SCRIPT action"
        )
    elif len(numbered) >= 2:
        word = "YES"
        meaning = (
            "the SCRIPT action's file is re-read on every invocation: the folder holds "
            f"{len(numbered)} exports named for distinct invocations"
        )
    elif not exports:
        word = "NONE"
        meaning = (
            "the COMMAND_LINE action ran and the SCRIPT action exported nothing, neither "
            "the registration-time file nor a rewritten one"
        )
    elif numbered:
        word = "PARTIAL"
        meaning = "exactly one rewritten export exists, which neither reading predicts"
    else:
        word = "NO"
        meaning = (
            "the SCRIPT action's file is read once, at registration: only the export the "
            "registration-time text names exists, after every rewrite"
        )
    return {
        "verdict": word,
        "meaning": meaning,
        "invocations": count,
        "exports": exports,
        "simulation_folder": str(SIM),
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--verdict" in args:
        print(json.dumps(verdict(), indent=1))
        return 0
    return invoke()


if __name__ == "__main__":
    raise SystemExit(main())
