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

The log and the numbered exports are this probe's files and not the run's
collected outputs, so ``--force-rerun`` leaves them where they are and a second
run appends to the first: T12 read 16 invocations that way on 2026-09-24. Move
them aside before the row runs again.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from tests.support_tier3 import (
    _NUMBERED as _NUMBERED,
)
from tests.support_tier3 import (
    EXPORT_STEM as EXPORT_STEM,
)
from tests.support_tier3 import HERE as HERE
from tests.support_tier3 import (
    LOG as LOG,
)
from tests.support_tier3 import (
    PROBE_POL as PROBE_POL,
)
from tests.support_tier3 import (
    SIM as SIM,
)
from tests.support_tier3 import (
    invocations as invocations,
)
from tests.support_tier3 import (
    verdict as verdict,
)

#: The POL of the probe row in matriz_actions.fs, which fixes the simulation folder.
#: The file the SCRIPT action points at, rewritten on every invocation, named
#: relative to the folder the point runs in: since 0.27.0 the run writes every
#: file it parks for a point there, sims/sim_6001/datapoints/DP-<point>/.
ACTION_SCRIPT_NAME = Path("actions") / "reread.txt"
#: Where it was before 0.27.0, and where a build with no point folder puts it.
ACTION_SCRIPT = SIM / ACTION_SCRIPT_NAME


def action_script() -> Path:
    """The SCRIPT action's file: the one in the point's folder the run wrote."""
    found = sorted(SIM.glob(f"datapoints/*/{ACTION_SCRIPT_NAME.as_posix()}"))
    return found[0] if found else ACTION_SCRIPT


def export_script(tag: str) -> str:
    """The child script exporting the loads spreadsheet named for ``tag``."""
    target = SIM / f"{EXPORT_STEM}_{tag}.txt"
    return f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{target}\n"


def initial_script() -> str:
    """What the SCRIPT action's file says at registration, before any invocation."""
    return export_script("initial")


#: An export the rewritten script asked for, named for its invocation count;
#: the solver appends ``_iteration=<n>`` to the name it was given.


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
    target = action_script()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(export_script(f"{count:03d}"), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--verdict" in args:
        print(json.dumps(verdict(), indent=1))
        return 0
    return invoke()


if __name__ == "__main__":
    raise SystemExit(main())
