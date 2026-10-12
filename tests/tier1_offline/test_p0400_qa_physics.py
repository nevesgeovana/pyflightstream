"""P0400-PHYSREF: the physics reductions, judgments, report and reference updates.

PFS-2102.035: the Markdown drag column carries the name the point's table prints.
PFS-2085.015: a reference metric the run did not produce judges FAIL and is counted.
PFS-2102.009: PHY-01 refuses a sweep without 4 deg or with fewer than two angles.
PFS-2102.010: evidence YAML read failures are QaEvidenceError, and so is a reference missing a key.
PFS-2102.011: update_reference refuses to lose a reference metric unless told to drop it.
PFS-2102.012: update_reference records a repository-relative source path.
PFS-2102.036: a relative band centred on zero is refused.
"""

from __future__ import annotations

import pytest
import yaml

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    CaseReference,
    CaseResult,
    PhysicsRun,
    PointResult,
    ReferenceBand,
    Verdict,
    compare_metrics,
    load_reference,
    phy01_metrics,
    read_physics_report,
    update_reference,
    write_physics_report,
)


def _points(alphas=(0.0, 2.0, 4.0, 6.0), drag="CDi") -> list[PointResult]:
    return [
        PointResult(
            alpha_deg=alpha,
            total={"CL": 0.0875 * alpha, drag: 0.001 + 0.0004 * alpha**2},
            iterations=300,
            converged=True,
        )
        for alpha in alphas
    ]


def _run(points: list[PointResult], *, reference: CaseReference | None = None) -> PhysicsRun:
    metrics = phy01_metrics(points)
    return PhysicsRun(
        version="26.120",
        fs_exe_name="FlightStream.exe",
        package_version="0.40.0",
        results=(
            CaseResult(
                case_id="PHY-01",
                title=PHYSICS_CASES["PHY-01"].title,
                geometry="test wing",
                points=tuple(points),
                metrics=metrics,
                verdicts=compare_metrics(metrics, reference),
                reference=reference,
            ),
        ),
    )


def test_p0400_physref_the_drag_column_is_the_one_the_table_prints(tmp_path):
    """P0400-PHYSREF (PFS-2102.035) a CDp table is printed under CDp, never as nan under CDi."""
    _, md_path = write_physics_report(_run(_points(drag="CDp")), tmp_path, date="2026-10-12")
    markdown = md_path.read_text(encoding="utf-8")
    assert "| point | alpha (deg) | CL | CDp | iterations | converged |" in markdown
    assert "nan" not in markdown


def test_p0400_physref_an_unproduced_reference_metric_fails_and_is_counted(tmp_path):
    """P0400-PHYSREF (PFS-2085.015) a reference metric the run lacks is a FAIL, not a silence."""
    band = ReferenceBand(value=0.35, warn=0.02, fail=0.05, kind="rel")
    reference = CaseReference(
        case_id="PHY-01",
        fs_version_basis="26.120",
        updated="2026-10-12",
        reason="test",
        metrics={"CL_a4": band, "CL_a8": band},
    )
    verdicts = compare_metrics({"CL_a4": 0.35}, reference)
    assert verdicts == {"CL_a4": Verdict.PASS, "CL_a8": Verdict.FAIL}
    run = _run(_points(), reference=reference)
    assert run.verdict_counts()["fail"] == 1
    _, md_path = write_physics_report(run, tmp_path, date="2026-10-12")
    assert "| CL_a8 | not produced | 0.35000 |" in md_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("alphas", "words"),
    [((0.0, 2.0, 6.0), "no 4 deg"), ((4.0,), "at least two angles")],
)
def test_p0400_physref_phy01_refuses_a_sweep_it_cannot_reduce(alphas, words):
    """P0400-PHYSREF (PFS-2102.009) no StopIteration, no slope fitted from one angle."""
    with pytest.raises(QaEvidenceError, match=words):
        phy01_metrics(_points(alphas))


def test_p0400_physref_a_missing_or_broken_evidence_file_is_refused_in_the_catalogued_type(
    tmp_path,
):
    """P0400-PHYSREF (PFS-2102.010) no FileNotFoundError, YAMLError or KeyError escapes."""
    with pytest.raises(QaEvidenceError, match="cannot be read"):
        read_physics_report(tmp_path / "PHY-26120_2026-10-12.yaml")
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "PHY-01.yaml").write_text("schema: [unclosed\n", encoding="utf-8")
    with pytest.raises(QaEvidenceError, match="not parsable YAML"):
        load_reference("PHY-01", refs)
    (refs / "PHY-01.yaml").write_text(
        "schema: pyflightstream-physics-reference/1\ncase: PHY-01\nmetrics: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(QaEvidenceError, match="fs_version_basis"):
        load_reference("PHY-01", refs)


def _seeded(tmp_path):
    refs = tmp_path / "refs"
    full, _ = write_physics_report(_run(_points()), tmp_path, date="2026-10-11")
    update_reference(
        "PHY-01", full, "seed (test)", references_dir=refs, date="2026-10-11", repo_root=tmp_path
    )
    partial, _ = write_physics_report(_run(_points((0.0, 2.0, 4.0))), tmp_path, date="2026-10-12")
    return refs, partial


def test_p0400_physref_an_update_never_loses_a_curated_metric_silently(tmp_path):
    """P0400-PHYSREF (PFS-2102.011) a report without CL_a6 is refused unless CL_a6 is dropped."""
    refs, partial = _seeded(tmp_path)
    with pytest.raises(QaEvidenceError, match="CL_a6"):
        update_reference(
            "PHY-01", partial, "partial (test)", references_dir=refs, repo_root=tmp_path
        )
    assert "CL_a6" in load_reference("PHY-01", refs).metrics
    update_reference(
        "PHY-01",
        partial,
        "drops 6 deg (test)",
        references_dir=refs,
        repo_root=tmp_path,
        drop=["CL_a6"],
    )
    assert "CL_a6" not in load_reference("PHY-01", refs).metrics


def test_p0400_physref_the_source_report_is_repository_relative(tmp_path):
    """P0400-PHYSREF (PFS-2102.012) no machine path reaches a committed reference."""
    refs = tmp_path / "refs"
    reports = tmp_path / "repo" / "reports" / "physics"
    report, _ = write_physics_report(_run(_points()), reports, date="2026-10-12")
    path = update_reference(
        "PHY-01", report, "seed (test)", references_dir=refs, repo_root=tmp_path / "repo"
    )
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored["source_report"] == "reports/physics/PHY-26120_2026-10-12.yaml"
    with pytest.raises(QaEvidenceError, match="outside"):
        update_reference(
            "PHY-01", report, "seed (test)", references_dir=refs, repo_root=tmp_path / "other"
        )


def test_p0400_physref_a_relative_band_centred_on_zero_is_refused():
    """P0400-PHYSREF (PFS-2102.036) a zero-width band cannot judge; it is refused with the cause."""
    with pytest.raises(QaEvidenceError, match="kind 'abs'"):
        ReferenceBand(value=0.0, warn=0.02, fail=0.05, kind="rel")
    assert ReferenceBand(value=0.0, warn=0.02, fail=0.05, kind="abs").judge(0.01) is Verdict.PASS


def _case(case_id: str, metrics: dict[str, float]) -> CaseResult:
    return CaseResult(case_id=case_id, title=case_id, geometry="test", metrics=metrics)


def _physics(version: str, *results: CaseResult) -> PhysicsRun:
    return PhysicsRun(
        version=version, fs_exe_name="FlightStream.exe", package_version="0.40.0", results=results
    )


def test_p0400_physref_drift_reports_what_one_side_lacks():
    """P0400-PHYSREF (PFS-2102.004) a one-sided metric fails and a one-sided case aborts."""
    from pyflightstream.qa.drift import diff_runs

    run_a = _physics(
        "26.124", _case("PHY-01", {"CL_a4": 0.35, "CDi_a4": 0.01}), _case("PHY-05", {})
    )
    run_b = _physics("26.125", _case("PHY-01", {"CL_a4": 0.35, "CDp_a4": 0.01}))
    drift = diff_runs(run_a, run_b)
    by_case = {result.case_id: result for result in drift.results}
    assert by_case["PHY-01"].metrics["CDi_a4"].verdict is Verdict.FAIL
    assert by_case["PHY-01"].metrics["CDp_a4"].verdict is Verdict.FAIL
    assert by_case["PHY-01"].metrics["CL_a4"].verdict is Verdict.PASS
    assert drift.verdict_counts()["fail"] == 2
    assert "26.124 only" in by_case["PHY-05"].error


def test_p0400_physref_drift_from_a_zero_baseline_does_not_crash():
    """P0400-PHYSREF (PFS-2102.036) a relative metric at exactly zero on side A has no band."""
    from pyflightstream.qa.drift import diff_runs

    drift = diff_runs(
        _physics("26.120", _case("PHY-01", {"CL_a4": 0.0})),
        _physics("26.123", _case("PHY-01", {"CL_a4": 0.001})),
    )
    assert drift.results[0].metrics["CL_a4"].verdict is Verdict.NO_REFERENCE
