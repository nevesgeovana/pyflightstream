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

A path in a rendered script is the workspace's own (the staged geometry), so
the goldens are compared with every absolute path of this folder replaced by
``<tier3>``; a clone elsewhere then reads the same golden.

THE GOLDEN IS THE PLAN-TIME RENDER, NOT THE RUN'S BYTES, and the two differ
in two known ways ``pyflightstream.run._plan_point`` states beside its own
render: the plan renders ``OPEN <library path>`` where the run renders
``OPEN <staged copy>``, and the run writes the script in text mode, so the
solver's bytes carry CRLF where ``render()`` returns LF. The golden pins
what the builders emit for a row; what the solver received is read from
``sims/<sim>/scripts/`` by the tier-3 tests (``conftest.Runs.script``),
which is a different artifact under a similar name.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GOLDENS = HERE / "goldens"
PLACEHOLDER = "<tier3>"


def matrices() -> list[Path]:
    return sorted(HERE.glob("*.fs"))


def portable(text: str) -> str:
    """The rendered script with this folder's absolute path replaced."""
    for spelling in (HERE.as_posix(), str(HERE), str(HERE).replace("\\", "\\\\")):
        text = text.replace(spelling, PLACEHOLDER)
    return text.replace("\r\n", "\n")


def render(matrix: Path) -> tuple[int, dict[str, str]]:
    """Plan one matrix against this workspace; return (points, {point: script})."""
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import pyflightstream.run as prun
    from pyflightstream.cases import workflows
    from pyflightstream.run.matrix import plan_matrix
    from pyflightstream.script import Script
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate

    rendered: dict[str, str] = {}
    original = prun._plan_point

    def hooked(campaign, case, point, ws, recipe, case_error, recorded, *, fs_version):
        plan = original(
            campaign, case, point, ws, recipe, case_error, recorded, fs_version=fs_version
        )
        if plan.status.name in ("READY", "ALREADY_RECORDED") and recipe is not None:
            stem, outputs = prun._point_names(campaign, case, point, ws)
            point_case = case.model_copy(update={"point": dict(point), "outputs": outputs})
            script = Script(version=fs_version)
            recipe(point_case, script)
            rendered[stem] = portable(script.render())
        return plan

    prun._plan_point = hooked
    try:
        plan = plan_matrix(
            matrix,
            CampaignWorkspace(HERE, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)),
            name=matrix.stem,
            recipes={},
            recipe_registry=workflows.workflow_registry(),
            write_plan=False,
        )
    finally:
        prun._plan_point = original
    blocked = [p for p in plan.points if p.status.name not in ("READY", "ALREADY_RECORDED")]
    if blocked:
        first = blocked[0]
        raise RuntimeError(
            f"{matrix.name}: {len(blocked)} point(s) blocked at pre-flight, for example "
            f"{first.run_id}: {first.error}"
        )
    return len(plan.points), rendered


def golden_of(matrix: Path, stem: str) -> Path:
    return GOLDENS / matrix.stem / f"{stem}.txt"


def compare(matrix: Path) -> tuple[int, list[str], list[str], list[str]]:
    """Return (points, scripts without a golden, scripts differing, orphan goldens).

    An orphan is a golden no rendered point produced, left behind when a row
    is renumbered, deactivated or deleted; it is reported so the goldens
    folder cannot quietly carry a script of a row that no longer exists.
    """
    count, rendered = render(matrix)
    absent, differ = [], []
    for stem, text in rendered.items():
        golden = golden_of(matrix, stem)
        if not golden.is_file():
            absent.append(stem)
        elif golden.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            differ.append(stem)
    folder = GOLDENS / matrix.stem
    orphans = (
        sorted(p.stem for p in folder.glob("*.txt") if p.stem not in rendered)
        if folder.is_dir()
        else []
    )
    return count, absent, differ, orphans


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
