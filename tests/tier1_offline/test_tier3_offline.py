"""The one offline control tier 1 keeps over the tier-3 workspace (GOAL-012,
PFS-2031.06).

Tier 3 is a campaign workspace run on a licensed solver. A clone with no seat
can still tell its matrices are sound: every matrix plans with the package to
READY on every active point, and every script the builders render equals its
golden under ``tests/tier3_licensed/goldens``. A change in the package that
moves one of those scripts is seen here, on the row it moves, before any seat
is spent.

``python -m tests.tier3_licensed.offline --write`` regenerates the goldens
when a script is meant to move.
"""

from __future__ import annotations

import shutil

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import CampaignWorkspace
from tests.tier3_licensed import offline

MATRICES = offline.matrices()


def test_the_tier3_workspace_has_matrices():
    assert MATRICES, "tests/tier3_licensed holds no matrix"


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_matrix_plans_ready(matrix):
    count, rendered = offline.render(matrix)
    assert count >= 1
    assert len(rendered) == count, "a ready point rendered no script"


# --- the refusals, at plan time, over the tier-3 workspace's own library ----------
#
# PFS-2031.05 asked for the refusals as RUN 0 rows of the matrices; the
# reader refuses a malformed row whatever its RUN cell says, so a refusal
# cannot sit in a matrix that must plan READY. They live here instead, as
# one-row matrices planned against a copy of the tier-3 inputs, and they
# cost no seat.

TIER3 = offline.HERE
TOUR = TIER3 / "matriz.fs"


def _tier3_copy(tmp_path, *, with_tour=False):
    """A workspace root holding a copy of the tier-3 inputs, and the tour when asked."""
    root = tmp_path / "ws"
    shutil.copytree(
        TIER3 / "inputs", root / "inputs", ignore=shutil.ignore_patterns("*.local.toml")
    )
    if with_tour:
        shutil.copy(TOUR, root / TOUR.name)
    return root


def _one_row_matrix(root, name, row):
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    path = root / name
    path.write_text("\n".join([header, rule, row]) + "\n", encoding="utf-8")
    return path


def _plan(root, matrix):
    return plan_matrix(
        matrix,
        CampaignWorkspace(root),
        name="refusal",
        default_fs_version="26.120",
        recipes={},
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


STEADY = "MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 26.120 | 0 | 1 | steady | "
ROTOR = (
    "MACH:0.1, REmi:2.3 | AL | 0.0 | r004 | s002 | p001 | 26.120 | 0 | 1 | unsteady_rotor | "
    "GEOMETRY: 40_PUSHER.fsm / SYMMETRY: NONE / ROTOR_AXIS: X / MOVING_BOUNDARIES: Blade / "
    "DELTA_THETA: 30 / REVOLUTIONS: 0.5 / "
)

REFUSALS = {
    "a geometry the library does not hold": (
        f"7001 | Wing | REFUSED | {STEADY}GEOMETRY: 99_MISSING.fsm / SYMMETRY: NONE",
        ("99_MISSING", "geometries"),
    ),
    "a reference code the library does not hold": (
        "7002 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r999 | s001 | p002 | 26.120 | 0 "
        "| 1 | steady | GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
        ("r999", "references"),
    ),
    "a rotor hub named by a free point name": (
        f"7003 | Pusher | REFUSED | {ROTOR}RPM: -800 / ROTOR_ORIGIN: HUB",
        ("HUB", "ERP"),
    ),
    "a rotor stating RPM and RPM_SIGN both": (
        f"7004 | Pusher | REFUSED | {ROTOR}RPM: -800 / RPM_SIGN: 1 / ROTOR_ORIGIN: ERP3",
        ("RPM_SIGN",),
    ),
    "a LEGACY row with a bare recipe code and no mapping": (
        "7005 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 26.120 | 0 "
        "| 1 | LEGACY | RECIPE: 003 / GEOMETRY: 10_WING.fsm / OUTPUTS: loads_{point}.txt",
        ("recipe mapping",),
    ),
    "a build the registry does not hold": (
        "7006 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 27.000 | 0 "
        "| 1 | steady | GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
        ("27.000", "executables.toml"),
    ),
}


@pytest.mark.parametrize("case", list(REFUSALS), ids=list(REFUSALS))
def test_the_workspace_refuses_a_row_it_cannot_plan_naming_the_cause(tmp_path, case):
    """A refusal arrives in one of two shapes and both are asserted the same way: the
    resolution raises before any point is planned (a code the library lacks, a point
    name outside the convention), or the point's builder refuses and the plan marks
    the point BLOCKED with the reason (a workflow key the run type cannot honor)."""
    row, fragments = REFUSALS[case]
    root = _tier3_copy(tmp_path)
    matrix = _one_row_matrix(root, "refused.fs", row)
    try:
        plan = _plan(root, matrix)
    except PyflightstreamError as error:
        message = str(error)
    else:
        assert plan.blocked, f"{case}: planned READY"
        message = " ".join(str(point.error) for point in plan.blocked)
    for fragment in fragments:
        assert fragment in message, f"{case}: {message}"


def test_the_workspace_refuses_a_pol_the_tour_already_states(tmp_path):
    root = _tier3_copy(tmp_path, with_tour=True)
    matrix = _one_row_matrix(
        root, "second.fs", f"1001 | Wing | REFUSED | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE"
    )
    with pytest.raises(PyflightstreamError) as caught:
        _plan(root, matrix)
    message = str(caught.value)
    assert "1001" in message and "matriz.fs" in message and "second.fs" in message, message


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_script_equals_its_golden(matrix):
    count, absent, differ = offline.compare(matrix)
    assert not absent, (
        f"{len(absent)} of {count} scripts have no golden: {absent[:4]}; regenerate with "
        "python -m tests.tier3_licensed.offline --write"
    )
    assert not differ, (
        f"{len(differ)} of {count} scripts differ from their golden: {differ[:4]}; a moved "
        "script is either a defect or a golden to regenerate, and the diff says which"
    )
