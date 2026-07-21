"""Tier 1: physics harness bands, references, report, and script build."""

import pytest
import yaml

from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    CaseResult,
    PhysicsRun,
    PointResult,
    ReferenceBand,
    Verdict,
    build_phy01_script,
    compare_metrics,
    load_reference,
    phy01_metrics,
    update_reference,
    write_physics_report,
)


def make_points() -> list[PointResult]:
    lift_slope_per_deg = 0.0875
    return [
        PointResult(
            alpha_deg=alpha,
            total={"CL": lift_slope_per_deg * alpha, "CDi": 0.001 + 0.0004 * alpha**2},
            iterations=300,
            converged=True,
        )
        for alpha in (0.0, 2.0, 4.0, 6.0)
    ]


def make_run(tmp_path, references_dir=None) -> PhysicsRun:
    points = make_points()
    metrics = phy01_metrics(points)
    reference = load_reference("PHY-01", references_dir) if references_dir else None
    return PhysicsRun(
        version="26.120",
        fs_exe_name="Flightstream_2612.exe",
        package_version="0.0.1.dev0",
        results=(
            CaseResult(
                case_id="PHY-01",
                title=PHYSICS_CASES["PHY-01"].title,
                geometry="NACA 0012 rectangular wing (test stub)",
                points=tuple(points),
                metrics=metrics,
                verdicts=compare_metrics(metrics, reference),
                reference=reference,
            ),
        ),
        solver_identity=("Flightstream version 26.1, build #7012026",),
    )


def test_band_judgment_covers_pass_warn_fail():
    relative = ReferenceBand(value=1.0, warn=0.02, fail=0.05, kind="rel")
    assert relative.judge(1.015) is Verdict.PASS
    assert relative.judge(1.04) is Verdict.WARN
    assert relative.judge(1.06) is Verdict.FAIL
    absolute = ReferenceBand(value=0.0, warn=0.005, fail=0.02, kind="abs")
    assert absolute.judge(0.004) is Verdict.PASS
    assert absolute.judge(-0.01) is Verdict.WARN
    assert absolute.judge(0.05) is Verdict.FAIL


def test_compare_metrics_without_reference_reports_no_reference():
    verdicts = compare_metrics({"CL_a4": 0.35}, None)
    assert verdicts == {"CL_a4": Verdict.NO_REFERENCE}


def test_phy01_metrics_reduce_the_sweep():
    metrics = phy01_metrics(make_points())
    assert metrics["CL_a0"] == pytest.approx(0.0)
    assert metrics["CL_a4"] == pytest.approx(0.35)
    # 0.0875 per degree is 5.01 per radian, the AR-8 finite-wing anchor.
    assert metrics["CL_slope_per_rad"] == pytest.approx(5.01, abs=0.02)
    assert metrics["CDi_a4"] == pytest.approx(0.0074)


def test_phy01_script_builds_validated_for_26120(tmp_path):
    script = build_phy01_script("26.120", 4.0, tmp_path / "wing.stl", "loads.txt", "log.txt")
    rendered = script.render()
    assert not script.raw_flag
    assert "IMPORT\nUNITS METER\nFILE_TYPE STL" in rendered
    assert "CLEAR" in rendered
    assert "SOLVER_SET_AOA 4.0" in rendered
    # AIR_ALTITUDE is broken on 26.120 (CMP-26120_2026-07-21_full); the
    # case must set the fluid state through FLUID_PROPERTIES instead.
    assert "AIR_ALTITUDE" not in rendered
    assert "FLUID_PROPERTIES" in rendered


def test_report_pair_written_and_never_overwritten(tmp_path):
    run = make_run(tmp_path)
    yaml_path, md_path = write_physics_report(run, tmp_path, date="2026-07-21")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["schema"] == "pyflightstream-physics-report/1"
    assert document["cases"]["PHY-01"]["verdicts"]["CL_a4"] == "no_reference"
    markdown = md_path.read_text(encoding="utf-8")
    assert "| CL_a4 |" in markdown
    assert "no_reference" in markdown
    with pytest.raises(FileExistsError, match="never"):
        write_physics_report(run, tmp_path, date="2026-07-21")


def test_reference_seeding_requires_a_reason(tmp_path):
    run = make_run(tmp_path)
    yaml_path, _ = write_physics_report(run, tmp_path, date="2026-07-21")
    with pytest.raises(ValueError, match="reason"):
        update_reference("PHY-01", yaml_path, "   ", references_dir=tmp_path / "refs")


def test_reference_roundtrip_and_band_reuse(tmp_path):
    refs = tmp_path / "refs"
    run = make_run(tmp_path)
    yaml_path, _ = write_physics_report(run, tmp_path, date="2026-07-21")
    update_reference(
        "PHY-01",
        yaml_path,
        "initial reference from the first 26.120 run",
        references_dir=refs,
        date="2026-07-21",
    )
    reference = load_reference("PHY-01", refs)
    assert reference is not None
    assert reference.fs_version_basis == "26.120"
    assert reference.metrics["CL_a4"].value == pytest.approx(0.35)
    # CL_a0 was declared absolute because a symmetric wing's CL at zero
    # incidence sits at zero, where relative bands are meaningless.
    assert reference.metrics["CL_a0"].kind == "abs"
    verdicts = compare_metrics({"CL_a4": 0.35, "CL_a0": 0.0}, reference)
    assert verdicts == {"CL_a4": Verdict.PASS, "CL_a0": Verdict.PASS}
    # A second update keeps curated bands but must still record a reason.
    path = update_reference(
        "PHY-01",
        yaml_path,
        "re-seeded in the same session (test)",
        references_dir=refs,
        date="2026-07-21",
    )
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored["reason"] == "re-seeded in the same session (test)"
    assert stored["metrics"]["CL_a0"]["kind"] == "abs"


def test_full_run_against_seeded_reference_passes(tmp_path):
    refs = tmp_path / "refs"
    seed_run = make_run(tmp_path)
    yaml_path, _ = write_physics_report(seed_run, tmp_path, date="2026-07-21")
    update_reference("PHY-01", yaml_path, "seed (test)", references_dir=refs)
    compared = make_run(tmp_path, references_dir=refs)
    verdicts = compared.results[0].verdicts
    assert set(verdicts.values()) == {Verdict.PASS}
    assert compared.verdict_counts()["pass"] == len(verdicts)
