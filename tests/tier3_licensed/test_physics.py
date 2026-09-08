"""The physics cases as rows of ``matriz_physics.fs``, judged against qa/references.

GOAL-012 item 7, PFS-2031.07. PHY-01, PHY-02, PHY-05 and PHY-06 exist in
``pyflightstream.qa.physics`` as hand-built scripts with committed
references and the bands she set on 26.120. Here the same cases are rows
of a matrix, built by the workflows, and their metrics are reduced from
the loads the rows exported with the SAME reduction functions the qa
layer uses, then judged against the SAME references. A FAIL is a finding:
either the workflow builds the case differently from the hand-built
script, or the solver moved; the test does not say which, the diff of
the two scripts does. A WARN is reported and accepted.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from pyflightstream.qa.physics import (
    PointResult,
    Verdict,
    compare_metrics,
    load_reference,
    phy01_metrics,
    phy02_metrics,
)
from tests.tier3_licensed.conftest import TERMINAL_OK

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_physics"


def _point(runs, record) -> PointResult:
    report = runs.loads(record)
    return PointResult(
        alpha_deg=float(record.point.get("alpha", 0.0)),
        total=dict(report.total),
        iterations=report.current_iteration,
        converged=report.current_iteration < report.requested_iterations,
        label=record.run_id,
    )


def _judge(case_id: str, metrics: dict[str, float]) -> dict[str, Verdict]:
    reference = load_reference(case_id)
    assert reference is not None, f"no committed reference for {case_id}"
    assert metrics, f"{case_id}: no metric was reduced, so nothing was judged"
    assert set(metrics) == set(reference.metrics), (
        f"{case_id}: the row reduces {sorted(metrics)} and the reference judges "
        f"{sorted(reference.metrics)}; every metric of the reference is judged, not fewer"
    )
    verdicts = compare_metrics(metrics, reference)
    assert all(v in (Verdict.PASS, Verdict.WARN) for v in verdicts.values()), verdicts
    failed = {
        name: (metrics[name], reference.metrics[name].value)
        for name, v in verdicts.items()
        if v is Verdict.FAIL
    }
    assert not failed, f"{case_id} outside her FAIL band: {failed}"
    warned = [name for name, v in verdicts.items() if v is Verdict.WARN]
    if warned:
        warnings.warn(f"{case_id} inside FAIL and outside WARN on {warned}", stacklevel=2)
    missing = [name for name, v in verdicts.items() if v is Verdict.NO_REFERENCE]
    assert not missing, f"{case_id} metrics the reference does not carry: {missing}"
    return verdicts


def test_every_physics_row_is_recorded_terminal(runs):
    for pol, count in (("5001", 4), ("5002", 1), ("5003", 1), ("5005", 1), ("5006", 4)):
        records = runs.of(MATRIX, pol)
        assert len(records) == count, (pol, len(records))
        for record in records:
            assert record.status in TERMINAL_OK, (record.run_id, record.status, record.error)
            assert record.fs_version_requested == "26.120"


def test_phy01_the_lift_slope_of_the_wing_polar_against_its_reference(runs):
    points = sorted((_point(runs, r) for r in runs.of(MATRIX, "5001")), key=lambda p: p.alpha_deg)
    assert [p.alpha_deg for p in points] == [0.0, 2.0, 4.0, 6.0]
    metrics = phy01_metrics(points)
    _judge("PHY-01", metrics)
    assert 4.0 < metrics["CL_slope_per_rad"] < 5.5, "the AR-8 finite-wing anchor is 5.0/rad"


def test_phy02_the_mirrored_half_span_reproduces_the_full_span(runs):
    full = _point(runs, runs.one(MATRIX, "5002", alpha=4.0))
    half = _point(runs, runs.one(MATRIX, "5003", alpha=4.0))
    _judge("PHY-02", phy02_metrics(full, half))


def test_phy05_the_periodic_propeller_after_a_revolution_and_a_half(runs):
    record = runs.one(MATRIX, "5005", alpha=0.0, beta=0.0)
    script = runs.script(record)
    assert "TIME_ITERATIONS 54" in script and "SYMMETRY PERIODIC 6" in script
    total = runs.total(record)
    _judge("PHY-05", {name: total[name] for name in ("CL", "CDi", "CDo", "CMy")})


def test_phy06_the_time_march_of_the_static_wing_lands_on_the_steady_polar(runs):
    steady = {r.point["alpha"]: runs.total(r) for r in runs.of(MATRIX, "5001")}
    unsteady = {r.point["alpha"]: runs.total(r) for r in runs.of(MATRIX, "5006")}
    assert sorted(unsteady) == [0.0, 2.0, 4.0, 6.0]
    metrics: dict[str, float] = {}
    for alpha in (0.0, 2.0, 4.0, 6.0):
        tag = f"a{alpha:g}"
        s, u = steady[alpha], unsteady[alpha]
        metrics[f"delta_CL_{tag}"] = u["CL"] - s["CL"]
        metrics[f"delta_CD_{tag}"] = (u["CDi"] + u["CDo"]) - (s["CDi"] + s["CDo"])
        metrics[f"delta_CMy_{tag}"] = u["CMy"] - s["CMy"]
    alphas = np.radians([0.0, 2.0, 4.0, 6.0])
    metrics["CL_slope_steady_per_rad"] = float(
        np.polyfit(alphas, [steady[a]["CL"] for a in (0.0, 2.0, 4.0, 6.0)], 1)[0]
    )
    metrics["CL_slope_unsteady_per_rad"] = float(
        np.polyfit(alphas, [unsteady[a]["CL"] for a in (0.0, 2.0, 4.0, 6.0)], 1)[0]
    )
    metrics["CMy_slope_steady_per_rad"] = float(
        np.polyfit(alphas, [steady[a]["CMy"] for a in (0.0, 2.0, 4.0, 6.0)], 1)[0]
    )
    metrics["CMy_slope_unsteady_per_rad"] = float(
        np.polyfit(alphas, [unsteady[a]["CMy"] for a in (0.0, 2.0, 4.0, 6.0)], 1)[0]
    )
    _judge("PHY-06", metrics)
