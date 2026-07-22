"""Tier 1: physics harness bands, references, report, and script build."""

import pytest
import yaml

from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    SMI_CASES,
    CaseResult,
    PhysicsRun,
    PointResult,
    ReferenceBand,
    Verdict,
    build_phy01_script,
    build_phy02_script,
    build_smi_script,
    compare_metrics,
    load_reference,
    phy01_metrics,
    phy02_metrics,
    registered_cases,
    run_physics,
    smi_metrics,
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


def test_phy02_half_script_mirrors_and_enables_symmetry_loads(tmp_path):
    script = build_phy02_script("26.120", True, tmp_path / "half.stl", "loads.txt", "log.txt")
    rendered = script.render()
    assert not script.raw_flag
    assert "SYMMETRY MIRROR" in rendered
    # Explicit on purpose: the 2026-07-21 calibration observed ENABLE as
    # the solver default after MIRROR init, but the case must not depend
    # on a default that could move between versions.
    assert "SET_ANALYSIS_SYMMETRY_LOADS ENABLE" in rendered


def test_phy02_full_script_keeps_the_baseline_shape(tmp_path):
    script = build_phy02_script("26.120", False, tmp_path / "full.stl", "loads.txt", "log.txt")
    rendered = script.render()
    assert "SYMMETRY NONE" in rendered
    assert "SET_ANALYSIS_SYMMETRY_LOADS" not in rendered


def test_phy02_metrics_are_the_pair_and_its_deltas():
    full = PointResult(4.0, {"CL": 0.3370, "CDi": 0.0049}, 58, True, label="full")
    half = PointResult(4.0, {"CL": 0.3385, "CDi": 0.0049}, 55, True, label="half")
    metrics = phy02_metrics(full, half)
    assert metrics["CL_full_a4"] == pytest.approx(0.3370)
    assert metrics["CL_half_a4"] == pytest.approx(0.3385)
    assert metrics["delta_CL_a4"] == pytest.approx(0.0015)
    assert metrics["delta_CDi_a4"] == pytest.approx(0.0)


def test_point_labels_reach_both_report_faces(tmp_path):
    full = PointResult(4.0, {"CL": 0.3370, "CDi": 0.0049}, 58, True, label="full")
    half = PointResult(4.0, {"CL": 0.3385, "CDi": 0.0049}, 55, True, label="half")
    run = PhysicsRun(
        version="26.120",
        fs_exe_name="Flightstream_2612.exe",
        package_version="0.0.1.dev0",
        results=(
            CaseResult(
                case_id="PHY-02",
                title=PHYSICS_CASES["PHY-02"].title,
                geometry="pair (test stub)",
                points=(full, half),
                metrics=phy02_metrics(full, half),
                verdicts=compare_metrics(phy02_metrics(full, half), None),
            ),
        ),
    )
    yaml_path, md_path = write_physics_report(run, tmp_path, date="2026-07-21", label="pair")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    labels = [point["label"] for point in document["cases"]["PHY-02"]["points"]]
    assert labels == ["full", "half"]
    assert "| half | +4.0 |" in md_path.read_text(encoding="utf-8")


def test_smi_cases_join_the_registry_only_with_a_root():
    assert set(registered_cases()) == set(PHYSICS_CASES)
    assert set(registered_cases(include_smi=True)) == set(PHYSICS_CASES) | set(SMI_CASES)
    assert "SMI-01" in SMI_CASES and "SMI-02" in SMI_CASES


def test_smi_case_without_root_is_refused_with_a_citation(tmp_path):
    with pytest.raises(Exception, match="SMI"):
        run_physics(
            "26.120",
            fs_exe="no_such.exe",
            workroot=tmp_path,
            cases=["SMI-01"],
        )


def test_smi_script_opens_and_solves_the_local_file(tmp_path):
    script = build_smi_script("26.120", tmp_path / "28_B.fsm", "loads.txt", "log.txt")
    rendered = script.render()
    assert not script.raw_flag
    assert rendered.count("OPEN") == 1
    assert "SET_SOLVER_STEADY" in rendered
    assert "SOLVER_SET_AOA 2.0" in rendered
    assert "SOLVER_SET_REF_AREA 1.0" in rendered
    # The SMI script must also build for 26.100 (the scoped backfill).
    script_26100 = build_smi_script("26.100", tmp_path / "28_B.fsm", "loads.txt", "log.txt")
    assert not script_26100.raw_flag


def test_smi_metrics_are_the_aggregated_totals():
    point = PointResult(
        2.0,
        {"CL": 0.021, "CDi": 0.0003, "CDo": 0.0041, "CMy": -0.012, "Cx": 0.004},
        120,
        True,
        label="28_B",
    )
    metrics = smi_metrics(point)
    assert metrics == {"CL": 0.021, "CDi": 0.0003, "CDo": 0.0041, "CMy": -0.012}


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


def test_phy05_script_pins_the_proven_unsteady_flow():
    from pyflightstream.qa.physics import PHY05_DELTA_TIME_S, PHY05_RPM, build_phy05_script

    text = build_phy05_script("26.12", "C:/work/blade.stl", "loads.txt", "log.txt").render()
    assert "SYMMETRY PERIODIC 6" in text
    assert f"SET_MOTION_ROTOR_RPM 1 {PHY05_RPM}" in text
    assert f"TIME_ITERATIONS 54\nDELTA_TIME {PHY05_DELTA_TIME_S}" in text
    assert "SET_WAKE_TERMINATION_TIME_STEPS -36" in text
    # In-solve consumers precede the solve (2026-07-21 reproduction).
    assert text.index("SET_ANALYSIS_SYMMETRY_LOADS DISABLE") < text.index("START_SOLVER")
    assert text.index("SET_SOLVER_UNSTEADY") < text.index("INITIALIZE_SOLVER")


def test_phy06_unsteady_script_differs_from_steady_only_by_time_stepping():
    from pyflightstream.qa.physics import (
        PHY06_ALPHAS_DEG,
        _build_wing_point_script,
        build_phy06_unsteady_script,
    )

    for alpha in PHY06_ALPHAS_DEG:
        steady = _build_wing_point_script(
            "PHY-06", "26.12", alpha, "C:/w/wing.stl", "l.txt", "g.txt"
        ).render()
        unsteady = build_phy06_unsteady_script(
            "26.12", alpha, "C:/w/wing.stl", "l.txt", "g.txt"
        ).render()
        extra = [
            line
            for line in unsteady.splitlines()
            if line not in steady.splitlines() and line.strip()
        ]
        assert extra == ["SET_SOLVER_UNSTEADY", "TIME_ITERATIONS 120", "DELTA_TIME 0.01"]


def test_phy06_metric_specs_cover_the_polar_trend():
    from pyflightstream.qa.physics import PHY06_ALPHAS_DEG, PHYSICS_CASES

    names = [spec.name for spec in PHYSICS_CASES["PHY-06"].metric_specs]
    for alpha in PHY06_ALPHAS_DEG:
        tag = f"a{alpha:g}"
        for quantity in ("CL", "CD", "CMy"):
            assert f"delta_{quantity}_{tag}" in names
    assert "CL_slope_steady_per_rad" in names
    assert "CL_slope_unsteady_per_rad" in names
    assert "CMy_slope_steady_per_rad" in names
    assert "CMy_slope_unsteady_per_rad" in names
    assert len(names) == 3 * len(PHY06_ALPHAS_DEG) + 4


def test_unsteady_cases_are_gated_to_versions_with_evidence(tmp_path):
    from pyflightstream.qa.physics import (
        PHYSICS_CASES,
        PhysicsEnvironmentError,
        run_physics,
    )

    assert PHYSICS_CASES["PHY-05"].supports("26.120")
    assert not PHYSICS_CASES["PHY-05"].supports("26.100")
    assert not PHYSICS_CASES["PHY-06"].supports("26.100")
    fake_exe = tmp_path / "fs.exe"
    fake_exe.write_text("not a solver")
    with pytest.raises(PhysicsEnvironmentError, match="no command evidence"):
        run_physics(
            "26.100",
            fs_exe=fake_exe,
            workroot=tmp_path / "runs",
            cases=["PHY-05"],
        )


# --- the test matrix as an inspectable table (pyfs-qa cases) ----------------


def test_case_table_is_one_line_per_registered_id():
    from pyflightstream.qa.physics import case_table

    table = case_table()
    assert [row["case_id"] for row in table] == list(PHYSICS_CASES)
    by_id = {row["case_id"]: row for row in table}
    assert by_id["PHY-01"]["title"] == PHYSICS_CASES["PHY-01"].title
    assert by_id["PHY-01"]["metrics"] == len(PHYSICS_CASES["PHY-01"].metric_specs)
    assert by_id["PHY-01"]["versions"] == "all registered"
    assert by_id["PHY-05"]["versions"] == "26.120"


def test_case_table_includes_smi_only_on_request():
    from pyflightstream.qa.physics import case_table

    assert not any(row["case_id"].startswith("SMI") for row in case_table())
    full = case_table(include_smi=True)
    assert {row["case_id"] for row in full} == set(PHYSICS_CASES) | set(SMI_CASES)


def test_cases_subcommand_prints_the_matrix(capsys):
    from pyflightstream.qa.cli import main

    assert main(["cases"]) == 0
    out = capsys.readouterr().out
    assert "CASE" in out and "VERSIONS" in out
    for case_id in PHYSICS_CASES:
        assert case_id in out
    assert "SMI-01" not in out
    assert "matrix line" in out

    assert main(["cases", "--include-smi"]) == 0
    assert "SMI-01" in capsys.readouterr().out
