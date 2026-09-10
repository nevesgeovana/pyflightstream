"""The physics cases as rows of ``matriz_physics.fs``, judged against qa/references.

GOAL-012 item 7, PFS-2031.07, and since 0.13.0 the reading of PFS-2031.17:
PHY-01, PHY-02, PHY-05 and PHY-06 are rows of this workspace's matrix,
built by the workflows, and ``pyflightstream.qa.matrix.reduce_physics`` is
what turns the rows' loads into the case metrics with the reductions of
``pyflightstream.qa.physics`` and judges them against the committed
references and the bands the author set on 26.120. This module asks that driver
for the judged run and asserts it; it reduces nothing of its own, so the
test and ``pyfs-qa physics`` read a record the same way. A FAIL is a
finding: either the workflow builds the case differently from what the
reference was recorded on, or the solver moved; the test does not say
which, the diff of the row's script against the golden does. A WARN is
reported and accepted.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.qa.matrix import reduce_physics
from pyflightstream.qa.physics import CaseResult, PhysicsRun, Verdict
from tests.tier3_licensed.conftest import HERE, TERMINAL_OK

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_physics"


@pytest.fixture(scope="module")
def physics(workspace) -> PhysicsRun:
    return reduce_physics(workspace, HERE / f"{MATRIX}.fs")


def _case(run: PhysicsRun, case_id: str) -> CaseResult:
    matches = [result for result in run.results if result.case_id == case_id]
    assert len(matches) == 1, f"{case_id}: {len(matches)} result(s) in the run"
    return matches[0]


def _judge(result: CaseResult) -> None:
    case_id = result.case_id
    assert result.error is None, f"{case_id} was not reduced: {result.error}"
    assert result.reference is not None, f"no committed reference for {case_id}"
    assert result.metrics, f"{case_id}: no metric was reduced, so nothing was judged"
    assert set(result.metrics) == set(result.reference.metrics), (
        f"{case_id}: the rows reduce {sorted(result.metrics)} and the reference judges "
        f"{sorted(result.reference.metrics)}; every metric of the reference is judged, not fewer"
    )
    failed = {
        name: (result.metrics[name], result.reference.metrics[name].value)
        for name, verdict in result.verdicts.items()
        if verdict is Verdict.FAIL
    }
    assert not failed, f"{case_id} outside the author's FAIL band: {failed}"
    warned = [name for name, verdict in result.verdicts.items() if verdict is Verdict.WARN]
    if warned:
        warnings.warn(f"{case_id} inside FAIL and outside WARN on {warned}", stacklevel=2)
    missing = [name for name, verdict in result.verdicts.items() if verdict is Verdict.NO_REFERENCE]
    assert not missing, f"{case_id} metrics the reference does not carry: {missing}"


def test_every_physics_row_is_recorded_terminal(runs):
    for pol, count in (("5001", 4), ("5002", 1), ("5003", 1), ("5005", 1), ("5006", 4)):
        records = runs.of(MATRIX, pol)
        assert len(records) == count, (pol, len(records))
        for record in records:
            assert record.status in TERMINAL_OK, (record.run_id, record.status, record.error)
            assert record.fs_version_requested == "26.120"


def test_the_run_names_the_build_and_every_case_the_rows_state(physics):
    assert physics.version == "26.120"
    assert [result.case_id for result in physics.results] == [
        "PHY-01",
        "PHY-02",
        "PHY-05",
        "PHY-06",
    ]
    assert physics.source == f"{MATRIX}.fs in workspace {HERE.name}"


def test_phy01_the_lift_slope_of_the_wing_polar_against_its_reference(physics):
    result = _case(physics, "PHY-01")
    assert [point.alpha_deg for point in result.points] == [0.0, 2.0, 4.0, 6.0]
    _judge(result)
    assert 4.0 < result.metrics["CL_slope_per_rad"] < 5.5, "the AR-8 finite-wing anchor is 5.0/rad"


def test_phy02_the_mirrored_half_span_reproduces_the_full_span(physics):
    result = _case(physics, "PHY-02")
    assert [point.label for point in result.points] == ["sim_5002/a+04.0", "sim_5003/a+04.0"]
    _judge(result)


def test_phy05_the_periodic_propeller_after_a_revolution_and_a_half(runs, physics):
    record = runs.one(MATRIX, "5005", alpha=0.0, beta=0.0)
    script = runs.script(record)
    assert "TIME_ITERATIONS 54" in script and "SYMMETRY PERIODIC 6" in script
    _judge(_case(physics, "PHY-05"))


def test_phy06_the_time_march_of_the_static_wing_lands_on_the_steady_polar(physics):
    result = _case(physics, "PHY-06")
    # The steady polar of row 5001 and the unsteady march of row 5006.
    assert len(result.points) == 8
    assert sorted({point.alpha_deg for point in result.points}) == [0.0, 2.0, 4.0, 6.0]
    _judge(result)
