"""Plan and build every tier-3 matrix without a solver, and keep the goldens.

The pre-flight builds each point's script and does not write it; hooking the
point planner keeps the text the builder produced, which is the package's own
render and not a re-implementation of it. The tier-1 control test
(``tests/tier1_offline/test_tier3_offline.py``) compares those renders to the
goldens under ``goldens/<matrix>/<point>.txt``, so a clone with no seat can
tell the tier-3 matrices are sound and that a change in the package moved a
script on purpose.

    python -m tests.tier3_licensed.offline           # report: rows, goldens
    python -m tests.tier3_licensed.offline --write   # regenerate the goldens

The raw meshes of ``matriz_mesh.fs`` are not in Git: ``render`` writes the
stand-in of any that is missing before it plans (``prepare.ensure_mesh_inputs``),
and the golden is the same whichever OBJ is on disk, since a script names
the file and never its bytes.

A path in a rendered script is the workspace's own (the staged geometry), so
the goldens are compared with every absolute path of this folder replaced by
``<tier3>``; a clone elsewhere then reads the same golden.

THE GOLDEN IS THE PLAN-TIME RENDER, NOT THE RUN'S BYTES, and the two differ
in the known ways ``pyflightstream.run._plan._plan_point`` states beside its own
render: the plan renders ``OPEN <library path>`` where the run renders
``OPEN <staged copy>``; a data file the run writes where the point runs (a
raw mesh's trailing-edge node file, an actuator profile's copy) is named by
its bare name, since the plan gives the script no working folder; and the run
writes the script in text mode, so the solver's bytes carry CRLF where
``render()`` returns LF. The golden pins
what the builders emit for a row; what the solver received is read from
``sims/<sim>/scripts/`` by the tier-3 tests (``conftest.Runs.script``),
which is a different artifact under a similar name.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.support_tier3 import (
    GOLDENS as GOLDENS,
)
from tests.support_tier3 import HERE as HERE
from tests.support_tier3 import (
    INTERPRETER as INTERPRETER,
)
from tests.support_tier3 import (
    PLACEHOLDER as PLACEHOLDER,
)
from tests.support_tier3 import (
    REPO as REPO,
)
from tests.support_tier3 import (
    compare as compare,
)
from tests.support_tier3 import (
    golden_of as golden_of,
)
from tests.support_tier3 import (
    matrices as matrices,
)
from tests.support_tier3 import (
    portable as portable,
)
from tests.support_tier3 import (
    render as render,
)

#: The interpreter a row stating an export threshold names on its
#: COMMAND_LINE registration line (PFS-2031.18): the one building the
#: script, so the golden replaces it as it replaces this folder.


def write_goldens(matrix: Path) -> int:
    count, rendered = render(matrix)
    for stem, text in rendered.items():
        target = golden_of(matrix, stem)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return count


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    write = "--write" in args
    bad = 0
    for matrix in matrices():
        if write:
            print(f"{matrix.name}: {write_goldens(matrix)} points written")
            continue
        count, absent, differ, orphans = compare(matrix)
        bad += len(absent) + len(differ) + len(orphans)
        print(
            f"{matrix.name}: {count} points, {len(absent)} without a golden, "
            f"{len(differ)} differing, {len(orphans)} orphan golden(s)"
        )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
