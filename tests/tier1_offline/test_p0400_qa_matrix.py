"""P0400-PHYSRUN: the physics matrix driver, its reduction, and the pyfs-qa front of it.

PFS-2085.016: a steady point stopped at the iteration limit is not judged.
PFS-2085.017: one report is evidence of one executable.
PFS-2102.034: only the campaign that ran is reduced; one record per point; one point per case.
PFS-2102.006: the report version is the one the build's registry entry declares.
PFS-2102.007: a case that cannot be reduced is reported, and a failed reduction is post-run.
PFS-2102.008: both drift sides are checked before either runs.
PFS-2102.009: a record without an alpha axis is refused.
PFS-2102.002, PFS-2102.010, PFS-2102.015: pyfs-qa refusals reach the operator without a traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.qa import matrix as matrix_module
from pyflightstream.qa.cli import main
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import PhysicsEnvironmentError
from pyflightstream.workspace import RunRecord, RunStatus

TIER3 = Path(__file__).resolve().parents[1] / "tier3_licensed"


def _record(run_id: str, *, status=RunStatus.CONVERGED, alpha=4.0, sha=None) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=run_id.split("/")[1].removeprefix("sim_"),
        point={} if alpha is None else {"alpha": alpha},
        fs_version_requested="26.120",
        fs_exe_sha256=sha,
        package_version="0.40.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=status,
        matrix_stem="matriz_physics",
    )


ROW = SimpleNamespace(pol="5002", description="PHY-02_full_span_baseline_at_4_deg")


def _workspace(tmp_path: Path, build: str = "26.120", entry: str | None = None) -> Path:
    root = tmp_path / "ws"
    (root / "inputs").mkdir(parents=True)
    text = (TIER3 / "matriz_physics.fs").read_text(encoding="utf-8")
    (root / "matriz_physics.fs").write_text(
        text.replace("| 26.120   |", f"| {build:<8} |"), encoding="utf-8"
    )
    registry = entry or (TIER3 / "inputs" / "executables.toml").read_text(encoding="utf-8")
    (root / "inputs" / "executables.toml").write_text(registry, encoding="utf-8")
    return root


def test_p0400_physrun_an_unsettled_steady_point_is_not_judged():
    """P0400-PHYSRUN (PFS-2085.016) MAX_ITER_REACHED makes the case an error, not a pass."""
    records = [_record("ws/sim_5002/AL+004", status=RunStatus.MAX_ITER_REACHED)]
    with pytest.raises(QaEvidenceError, match="MAX_ITER_REACHED"):
        matrix_module._points_of_row(None, ROW, records)


def test_p0400_physrun_two_records_of_one_point_are_refused():
    """P0400-PHYSRUN (PFS-2102.034) a point recorded twice never reaches a fit or an unpack."""
    records = [_record("ws/sim_5002/AL+004"), _record("ws/sim_5002/AL+004b")]
    with pytest.raises(QaEvidenceError, match="more than one record of one point"):
        matrix_module._points_of_row(None, ROW, records)


def test_p0400_physrun_only_the_campaign_that_ran_is_reduced():
    """P0400-PHYSRUN (PFS-2102.034) the run under --name and the run under the directory differ."""
    records = [_record("ws/sim_5002/AL+004"), _record("other/sim_5002/AL+004")]
    workspace = SimpleNamespace(read_manifest=lambda: records)
    by_row = matrix_module._records_by_row(workspace, "matriz_physics", "ws")
    assert [r.run_id for r in by_row["5002"]] == ["ws/sim_5002/AL+004"]


def test_p0400_physrun_a_single_point_case_refuses_a_sweep():
    """P0400-PHYSRUN (PFS-2102.034) a QaEvidenceError, never a bare unpacking ValueError."""
    from pyflightstream.qa.physics import PointResult

    points = [PointResult(a, {"CL": 0.1}, 10, True, f"p{a:g}") for a in (2.0, 4.0)]
    with pytest.raises(QaEvidenceError, match="reads one point"):
        matrix_module._one_point("PHY-05", ROW, points)


def test_p0400_physrun_a_record_without_alpha_is_refused():
    """P0400-PHYSRUN (PFS-2102.009) an unknown incidence is never read as 0 deg."""
    with pytest.raises(QaEvidenceError, match="no alpha axis"):
        matrix_module.point_result(None, _record("ws/sim_5001/X", alpha=None))


def _fake_workspace(root: Path, records: list[RunRecord]):
    return SimpleNamespace(
        root=root, read_manifest=lambda: records, manifest_path=root / "runs.json"
    )


def test_p0400_physrun_two_executables_of_one_version_are_refused(tmp_path):
    """P0400-PHYSRUN (PFS-2085.017) both digests are named; nothing is pooled."""
    root = _workspace(tmp_path)
    records = [
        _record("ws/sim_5002/AL+004", sha="a" * 64),
        _record("ws/sim_5003/AL+004", sha="b" * 64),
    ]
    with pytest.raises(PhysicsEnvironmentError, match="fs_exe_sha256") as refused:
        matrix_module.reduce_physics(_fake_workspace(root, records), root / "matriz_physics.fs")
    assert "a" * 64 in str(refused.value) and "b" * 64 in str(refused.value)


def test_p0400_physrun_a_case_that_cannot_be_reduced_is_reported(tmp_path, monkeypatch):
    """P0400-PHYSRUN (PFS-2102.007) an archived loads table is the case's error, not the run's."""

    def archived(workspace, record):
        raise FileNotFoundError(f"{record.run_id}: loads table archived")

    monkeypatch.setattr(matrix_module, "parse_run_loads", archived)
    root = _workspace(tmp_path)
    records = [_record("ws/sim_5005/AL+000", alpha=0.0)]
    run = matrix_module.reduce_physics(_fake_workspace(root, records), root / "matriz_physics.fs")
    errors = {result.case_id: result.error for result in run.results}
    assert "FileNotFoundError" in errors["PHY-05"], errors


def test_p0400_physrun_a_failed_reduction_says_the_matrix_ran(tmp_path, monkeypatch):
    """P0400-PHYSRUN (PFS-2102.007, PFS-2102.034) never the pre-run 'matrix not run'."""
    root = _workspace(tmp_path)
    monkeypatch.setattr(matrix_module, "run_physics_matrix", lambda *a, **k: [])

    def failing(*args, **kwargs):
        raise ValueError("too many values to unpack")

    monkeypatch.setattr(matrix_module, "reduce_physics", failing)
    with pytest.raises(PhysicsEnvironmentError, match="the matrix ran"):
        matrix_module.physics_from_workspace(root)


def test_p0400_physrun_the_report_version_is_the_declared_one(tmp_path):
    """P0400-PHYSRUN (PFS-2102.006) a build id is a name, never read as a version."""
    entry = '"main" = { path = "FlightStream.exe", version = "26.120" }\n'
    root = _workspace(tmp_path, build="main", entry=entry)
    assert matrix_module.physics_build(root / "matriz_physics.fs") == "26.120"
    bare = _workspace(tmp_path / "bare", build="main", entry='"main" = "FlightStream.exe"\n')
    with pytest.raises(PhysicsEnvironmentError, match="declares no version"):
        matrix_module.physics_build(bare / "matriz_physics.fs")


def test_p0400_physrun_both_drift_sides_are_checked_before_either_runs(tmp_path, monkeypatch):
    """P0400-PHYSRUN (PFS-2102.008) side B's typo costs no seat on side A."""

    def no_seat(*args, **kwargs):
        raise AssertionError("side a ran before side b was checked")

    monkeypatch.setattr(matrix_module, "run_physics_matrix", no_seat)
    root = _workspace(tmp_path)
    workroot = tmp_path / "drift"
    with pytest.raises(PhysicsEnvironmentError, match="is not a file"):
        matrix_module.drift_from_workspace(
            root,
            "26.120",
            "26.123",
            fs_exes={"26.120": sys.executable, "26.123": str(tmp_path / "nowhere.exe")},
            workroot=workroot,
        )
    assert not workroot.exists() or not any(workroot.iterdir())
    (workroot / "b_26123").mkdir(parents=True)
    with pytest.raises(PhysicsEnvironmentError, match="already exists"):
        matrix_module.drift_from_workspace(
            root,
            "26.120",
            "26.123",
            fs_exes={"26.120": sys.executable, "26.123": sys.executable},
            workroot=workroot,
        )
    assert not (workroot / "a_26120").exists()


def test_p0400_physrun_the_drift_pre_flight_checks_the_executables(tmp_path, monkeypatch, capsys):
    """P0400-PHYSRUN (PFS-2102.008) pyfs-qa drift refuses before it hands over a seat."""
    from pyflightstream.qa import cli as cli_module

    monkeypatch.setattr(
        cli_module, "drift_from_workspace", lambda *a, **k: pytest.fail("a seat was spent")
    )
    root = _workspace(tmp_path)
    code = main(
        [
            "drift",
            "--workspace",
            str(root),
            "--fs-versions",
            "26.120,26.123",
            "--fs-exe",
            f"26.120={sys.executable}",
            "--fs-exe",
            f"26.123={tmp_path / 'nowhere.exe'}",
            "--workroot",
            str(tmp_path / "drift"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 2
    assert "nothing run" in capsys.readouterr().err


def test_p0400_physrun_a_missing_executable_is_refused_without_a_traceback(tmp_path, capsys):
    """P0400-PHYSRUN (PFS-2102.002) pyfs-qa probe with a mistyped --fs-exe."""
    code = main(
        [
            "probe",
            "--fs-version",
            "26.123",
            "--fs-exe",
            str(tmp_path / "nowhere.exe"),
            "--workroot",
            str(tmp_path / "work"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 2
    assert "nothing run" in capsys.readouterr().err


def test_p0400_physrun_a_label_that_is_no_file_name_is_refused_before_the_run(tmp_path, capsys):
    """P0400-PHYSRUN (PFS-2102.015) pilot/2 is refused at the pre-flight, not at the write."""
    from pyflightstream.qa.reports import report_paths

    with pytest.raises(QaEvidenceError, match="file-name token"):
        report_paths(tmp_path, series="PHY", versions=["26.120"], date="2026-10-12", label="10:30")
    code = main(
        [
            "probe",
            "--fs-version",
            "26.123",
            "--fs-exe",
            sys.executable,
            "--label",
            "pilot/2",
            "--workroot",
            str(tmp_path / "work"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 2
    assert "file-name token" in capsys.readouterr().err


def test_p0400_physrun_an_unreadable_manifest_is_refused_by_pyfs_qa_cost(tmp_path, capsys):
    """P0400-PHYSRUN (PFS-2102.010) a corrupt runs.json is a refusal, not a traceback."""
    (tmp_path / "runs.json").write_text("{", encoding="utf-8")
    assert main(["cost", str(tmp_path)]) == 2
    assert "no cost read" in capsys.readouterr().err
