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
    physics_report_paths,
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
    script = build_phy02_script(
        "26.120",
        half=True,
        stl_path=tmp_path / "half.stl",
        loads_name="loads.txt",
        log_name="log.txt",
    )
    rendered = script.render()
    assert not script.raw_flag
    assert "SYMMETRY MIRROR" in rendered
    # Explicit on purpose: the 2026-07-21 calibration observed ENABLE as
    # the solver default after MIRROR init, but the case must not depend
    # on a default that could move between versions.
    assert "SET_ANALYSIS_SYMMETRY_LOADS ENABLE" in rendered


def test_phy02_full_script_keeps_the_baseline_shape(tmp_path):
    script = build_phy02_script(
        "26.120",
        half=False,
        stl_path=tmp_path / "full.stl",
        loads_name="loads.txt",
        log_name="log.txt",
    )
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
    # The SMI script must also build for 26.101 (the scoped backfill).
    script_26100 = build_smi_script("26.101", tmp_path / "28_B.fsm", "loads.txt", "log.txt")
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


def test_the_writer_lands_exactly_where_the_pre_flight_looked(tmp_path):
    """The pairing that protects a licensed seat, asserted end to end.

    `pyfs-qa physics` asks `physics_report_paths` whether a report
    already exists BEFORE it starts the solver, and then this writer
    produces the file. Until 2026-08-18 those were two independent
    expressions: the CLI stripped the dots off the build and pasted the
    prefix `PHY` itself, and this writer did the same a few hundred lines
    away. They agreed by coincidence, and the review pass measured the
    cost of that coincidence by changing this writer's prefix to PHZ:
    forty-five tests stayed green while the pre-flight silently inspected
    a name nothing would ever write, which is the incident it exists to
    prevent, one field over.

    So this asserts the writer's OWN answer against the helper the CLI
    asks, rather than against a literal either of them could drift from.
    """
    run = make_run(tmp_path)
    yaml_path, md_path = write_physics_report(run, tmp_path, date="2026-07-21", label="pinned")
    assert (yaml_path, md_path) == physics_report_paths(
        tmp_path, version=run.version, date="2026-07-21", label="pinned"
    )


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

    text = build_phy05_script("26.120", "C:/work/blade.stl", "loads.txt", "log.txt").render()
    assert "SYMMETRY PERIODIC 6" in text
    assert f"SET_MOTION_ROTOR_RPM 1 {PHY05_RPM}" in text
    assert f"TIME_ITERATIONS 54\nDELTA_TIME {PHY05_DELTA_TIME_S}" in text
    assert "SET_WAKE_TERMINATION_TIME_STEPS -36" in text
    # In-solve consumers precede the solve (2026-07-21 case-reproduction run).
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
            "PHY-06", "26.120", alpha, "C:/w/wing.stl", "l.txt", "g.txt"
        ).render()
        unsteady = build_phy06_unsteady_script(
            "26.120", alpha, "C:/w/wing.stl", "l.txt", "g.txt"
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
    assert not PHYSICS_CASES["PHY-05"].supports("26.101")
    assert not PHYSICS_CASES["PHY-06"].supports("26.101")
    fake_exe = tmp_path / "fs.exe"
    fake_exe.write_text("not a solver")
    with pytest.raises(PhysicsEnvironmentError, match="no command evidence"):
        run_physics(
            "26.101",
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
    assert by_id["PHY-01"]["minimum_version"] == "all registered"
    # The rotor cases are pinned to a MINIMUM rather than to a list, and
    # the table renders it as one. Their pin cited a backfill owed for
    # EARLIER builds, which is a minimum written as an enumeration, so
    # every arriving build fell outside it until somebody appended it:
    # 26.121 and 26.122 on 2026-08-11, 26.123 on 2026-08-17. Rendering a
    # list here would put the same decay on the page a reader compares
    # their own build against.
    assert by_id["PHY-05"]["minimum_version"] == "26.120 and after"


def test_case_table_includes_smi_only_on_request():
    from pyflightstream.qa.physics import case_table

    assert not any(row["case_id"].startswith("SMI") for row in case_table())
    full = case_table(include_smi=True)
    assert {row["case_id"] for row in full} == set(PHYSICS_CASES) | set(SMI_CASES)


def test_cases_subcommand_prints_the_matrix(capsys):
    from pyflightstream.qa.cli import main

    assert main(["cases"]) == 0
    out = capsys.readouterr().out
    assert "CASE" in out and "MINIMUM VERSION" in out
    for case_id in PHYSICS_CASES:
        assert case_id in out
    assert "SMI-01" not in out
    assert "matrix line" in out

    assert main(["cases", "--include-smi"]) == 0
    assert "SMI-01" in capsys.readouterr().out


def test_the_unsteady_pin_is_a_minimum_and_not_a_list(tmp_path):
    """An enumeration of allowed builds excludes the newest one every time.

    PHY-05 and PHY-06 were pinned to a TUPLE of canonical identifiers,
    and the pin's own reason was a backfill owed for builds EARLIER than
    26.120. A minimum expressed as an enumeration has to be extended by
    hand for every build that arrives, so it excludes each new one on the
    day it is registered, and it has already happened twice: 26.121 and
    26.122 sat outside it until somebody appended them on 2026-08-11,
    and 26.123 sat outside it on 2026-08-17.

    The pin is a MINIMUM read through the ordering authority, so no
    arriving build can fall outside it and the intent is unchanged. Read
    through the ordering authority and not by string comparison, because
    release order is the registry's own list position and the identifier
    does not encode it: 26.100 is newer than 26.000 and both precede
    26.120, which string order gets right by luck rather than by rule.
    """
    from pyflightstream.qa.physics import PHYSICS_CASES

    for case_id in ("PHY-05", "PHY-06"):
        case = PHYSICS_CASES[case_id]
        assert case.minimum_version == "26.120", (
            f"{case_id} does not carry a minimum build; if the pin is back to an "
            "enumeration it will exclude the next registered build silently"
        )
        # Every build from the minimum on, INCLUDING ones registered
        # after this test was written, which is the whole point.
        for canonical in ("26.120", "26.121", "26.122", "26.123"):
            assert case.supports(canonical), f"{case_id} does not support {canonical}"
        for canonical in ("25.000", "25.100", "26.000", "26.100", "26.101"):
            assert not case.supports(canonical), (
                f"{case_id} claims to support {canonical}, which precedes its minimum"
            )


def test_the_minimum_follows_release_order_and_not_the_identifier(monkeypatch):
    """The claim `supports` makes about itself, made falsifiable.

    Its docstring says AFTER is read from the ordering authority "and
    NOT from the identifier", and until 2026-08-17 nothing measured
    that: replacing the whole body with `canonical >= self.minimum_version`
    passed every test, because the registry's list order happens to
    agree with string order today. The test that noticed said so out
    loud and then relied on it anyway.

    That agreement is a coincidence the charter warns about. Versions are
    ordered by RELEASE order and only added, never dropped, and a build
    obtained later can belong EARLIER in the list; two already do. So
    the ordering is put in deliberate disagreement with string order
    here, which is the only way this assertion can fail for the right
    reason.
    """
    from pyflightstream.qa import physics
    from pyflightstream.qa.physics import PhysicsCase

    class _Fake:
        def __init__(self, canonical):
            self.canonical = canonical

    # Release order: 26.130 shipped FIRST, then 26.120, then 26.121.
    # String order would put 26.130 last.
    monkeypatch.setattr(
        physics,
        "known_versions",
        lambda: (_Fake("26.130"), _Fake("26.120"), _Fake("26.121")),
    )
    case = PhysicsCase(
        case_id="PHY-XX",
        title="ordering probe",
        minimum_version="26.120",
        metric_specs=(),
        runner=lambda context: None,
    )
    assert not case.supports("26.130"), (
        "26.130 is EARLIER in release order than the minimum, so it is not supported; "
        "reading the identifier rather than the list position says the opposite"
    )
    assert case.supports("26.120")
    assert case.supports("26.121")
    assert not case.supports("26.999"), "a build the registry does not carry must fail closed"


def test_a_build_registered_later_is_inside_the_minimum_without_an_edit():
    """The property the minimum exists for, stated over the registry.

    Derived rather than named: every registered build at or after the
    minimum's list position supports the case, whatever it is called and
    whenever it arrived.
    """
    from pyflightstream.qa.physics import PHYSICS_CASES
    from pyflightstream.versions import known_versions

    order = [version.canonical for version in known_versions()]
    for case_id in ("PHY-05", "PHY-06"):
        case = PHYSICS_CASES[case_id]
        floor = order.index(case.minimum_version)
        for position, canonical in enumerate(order):
            assert case.supports(canonical) == (position >= floor), (
                f"{case_id}.supports({canonical}) disagrees with the release order the "
                "ordering authority declares"
            )


def test_the_full_suite_refuses_rather_than_running_a_subset(tmp_path):
    """A run that cannot deliver every case must not report success on four.

    The selection used to FILTER the registry by support, so a build the
    unsteady cases excluded ran the other four and reported success, and
    the report said nothing about the two that never entered the loop. On
    a build about to carry a large study that is worse than no run: it
    produces a record saying the build was validated.

    Asking for a SUBSET by name is still allowed; what is refused is
    asking for everything and silently getting less.
    """
    from pyflightstream.qa.physics import PhysicsEnvironmentError, run_physics

    fake_exe = tmp_path / "fs.exe"
    fake_exe.write_text("not a solver")
    with pytest.raises(PhysicsEnvironmentError) as caught:
        run_physics("26.101", fs_exe=fake_exe, workroot=tmp_path / "runs")
    message = str(caught.value)
    assert "PHY-05" in message and "PHY-06" in message, message
    assert "26.120" in message, "the refusal does not say what the restriction IS"
    assert "cases=" in message and "PHY-01" in message, (
        "the refusal does not tell the caller how to ask for the subset deliberately, "
        "and it must name the runnable set rather than leaving them to work it out"
    )
    assert "--cases" not in message, (
        "a library refusal must not name a command-line flag: this function's own "
        "parameter is `cases`, and a Python caller cannot type a flag. The CLI owns "
        "that translation, and tests/test_qa_cli.py pins it"
    )


def test_the_physics_helper_and_writer_default_their_date_the_same_way(tmp_path):
    """The two-arm guard compat has, which physics did not.

    `INC-20260817-2210` happened because the date default lived in the
    writer and the helper and one of them lost it. Compat has a test on
    each arm for that reason: the mirror-image mutation, the default kept
    in the writer and lost from the helper, writes a perfectly dated
    report and corrupts the PRE-FLIGHT instead, so a single-arm guard
    passes it.

    Physics and drift acquired the same two-site shape on 2026-08-18 when
    they gained helpers of their own, and acquired NEITHER arm: their
    pairing tests pass an explicit date to both sides, so deleting either
    `resolve_report_date` call changes nothing they observe. A mutation
    battery comment even asserted the mutation was "impossible there by
    construction", which was true of `report_paths` and false of the two
    helpers that wrap it.
    """
    import datetime

    today = datetime.date.today().isoformat()

    yaml_path, md_path = physics_report_paths(tmp_path, version="26.120", label="probe")
    assert yaml_path.name == f"PHY-26120_{today}_probe.yaml"
    assert md_path.name == f"PHY-26120_{today}_probe.md"

    written_yaml, written_md = write_physics_report(make_run(tmp_path), tmp_path, label="probe")
    assert written_yaml.name == f"PHY-26120_{today}_probe.yaml"
    document = yaml.safe_load(written_yaml.read_text(encoding="utf-8"))
    assert document["date"] == today, (
        "the body carries a different date from the file name, which is the shape "
        "that reached a committed evidence file and cannot be repaired by editing it"
    )
    assert today in written_md.read_text(encoding="utf-8").splitlines()[0]
