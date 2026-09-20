"""Falsify C01's reader with synthetic data in the observed native formats.

No licensed payload is copied here. The VTK is two independent triangles;
the headerless CSV is one triangle, and the native log states two periodic
copies. Inner-iteration lines carry cumulative indices and NUL separators,
as the solver logs do. Expected counts come from these constructed fixtures.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/measure_c01_verification.py"


def _instrument():
    spec = importlib.util.spec_from_file_location("measure_c01_verification", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _vtk(workspace: Path, copies: int = 2) -> Path:
    # Disjoint triangles, all vertices used: POINT_DATA and CELL_DATA have
    # different lengths, and both must be checked before accepting a file.
    points = 3 * copies
    text = (
        "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
        f"POINTS {points} float\n"
        + "0 0 0\n1 0 0\n0 1 0\n" * copies
        + f"POLYGONS {copies} {4 * copies}\n"
        + "".join(f"3 {3 * i} {3 * i + 1} {3 * i + 2}\n" for i in range(copies))
        + f"POINT_DATA {points}\nSCALARS X FLOAT\nLOOKUP_TABLE default\n"
        + "0\n1\n0\n" * copies
        + f"CELL_DATA {copies}\nSCALARS Cp_freestream FLOAT\nLOOKUP_TABLE default\n"
        + "0.25\n" * copies
        + "SCALARS Boundary_Index FLOAT\nLOOKUP_TABLE default\n"
        + "1\n" * copies
    )
    return _write(workspace / "sims/sim_2505/datapoints/DP-test/point.vtk", text)


def _surface_files(workspace: Path) -> Path:
    vtk = _vtk(workspace)
    _write(vtk.with_suffix(".csv"), "0,0,0,0.25\n1,0,0,0.25\n0,1,0,0.25\n")
    _write(vtk.with_name("point_log.txt"), "3 vertices assigned to solver.\n")
    _write(workspace / "sims/sim_2505/scripts/point.txt", "SYMMETRY PERIODIC 2\n")
    return vtk


def _log(workspace: Path, row: int, counts: list[int], limit: int) -> Path:
    lines = []
    iteration = 0
    for step, count in enumerate(counts, 1):
        lines += [
            f"Solving unsteady time-step iteration ({step}/{len(counts)})...",
            "Iteration  Res. Vel.  Res. Pres.  CL  CDi (vorticity)  CM",
        ]
        for _ in range(count):
            iteration += 1
            lines.append(
                f"{iteration}\t+1.0000000E-3\t+2.0000000E-4\t*************\t+1.0E-2\t*************"
            )
    lines.append("Unsteady solver run time: 0.01 minutes.")
    sim = workspace / "sims" / f"sim_{row}"
    path = _write(sim / "datapoints/DP-test/point_log.txt", "\n\x00\n".join(lines))
    _write(
        path.with_name("point.txt"),
        f"Requested solver iterations {limit}\nCurrent solver iteration number: {iteration}\n",
    )
    if row == 2503:
        _write(sim / "scripts/point.txt", "SET_SOLVER_CONVERGENCE_ITERATIONS 3\n")
    return path


def _probes(root: Path) -> None:
    # Three scripts differing in exactly one command, in the two tested positions.
    _write(root / "without/probe.txt", "INITIALIZE_SOLVER\nSTART_SOLVER\nEXPORT_LOG\n")
    _write(root / "without/point_log.txt", "Unsteady solver run time: 1.99 minutes.\n")
    _write(
        root / "with/probe.txt",
        "SOLVER_TIME_AVERAGING ENABLE 19 36\nINITIALIZE_SOLVER\nSTART_SOLVER\nEXPORT_LOG\n",
    )
    _write(
        root / "after_init/probe.txt",
        "INITIALIZE_SOLVER\nSOLVER_TIME_AVERAGING ENABLE 19 36\nSTART_SOLVER\nEXPORT_LOG\n",
    )


def test_vtk_validates_payloads_and_surface_identities(tmp_path):
    instrument = _instrument()
    path = _vtk(tmp_path)
    check = instrument.vtk_export(tmp_path)
    assert check["verdict"] == "verified"
    assert check["measured"] == {
        "points": 6,
        "variables": 3,
        "surfaces": {"1": {"points": 6, "cells": 2}},
    }
    _write(path, path.read_text().replace("POLYGONS 2 8", "POLYGONS 2 9"))
    assert instrument.vtk_export(tmp_path)["verdict"] == "could-not-measure", (
        "VTK polygon payload count must match the header"
    )


def test_csv_rejects_vtk_point_count_disagreement(tmp_path):
    instrument = _instrument()
    _surface_files(tmp_path)
    check = instrument.csv_export(tmp_path)
    assert check["verdict"] == "verified"
    assert check["measured"] == {
        "rows": 3,
        "columns": 4,
        "sector_points": 3,
        "vtk_points": 6,
        "periodic_copies": 2,
    }
    # Still a fully valid VTK, but now nine points instead of the evidenced six.
    _vtk(tmp_path, copies=3)
    assert instrument.csv_export(tmp_path)["verdict"] == "failed", (
        "CSV rows times recorded copies must equal VTK points"
    )


def test_niter_rejects_a_time_step_above_its_limit(tmp_path):
    instrument = _instrument()
    _log(tmp_path, 2502, [5, 5], 5)
    _log(tmp_path, 2503, [6, 8], 300)
    check = instrument.niter_limit(tmp_path)
    assert check["verdict"] == "verified"
    assert check["measured"]["2502"] == {
        "min": 5,
        "max": 5,
        "median": 5,
        "total": 10,
        "steps": 2,
        "niter": 5,
    }
    assert check["measured"]["2503"] == {
        "min": 6,
        "max": 8,
        "median": 7,
        "total": 14,
        "steps": 2,
        "niter": 300,
        "convergence_iterations": 3,
    }
    _log(tmp_path, 2503, [6, 301], 300)
    assert instrument.niter_limit(tmp_path)["verdict"] == "failed", (
        "NITER must bound every time step"
    )


def test_refusal_requires_a_remedy(tmp_path):
    instrument = _instrument()
    _receipted_probes(tmp_path)
    check = instrument.solver_time_averaging(tmp_path)
    assert check["verdict"] == "refused-by-measurement"
    assert check["measured"]["control_wall_seconds"] == 133.0
    assert check["measured"]["mutant_wall_seconds"] == 240.5
    assert check["measured"]["control_output_count"] == 1
    assert check["measured"]["mutant_output_count"] == 0
    assert check["measured"]["positions_tried"] == 1
    assert "receipts" in check["how"]
    assert "not verified" in check["remedy"]
    assert instrument.solver_time_averaging(tmp_path, remedy="")["verdict"] == "failed", (
        "refusal without a remedy must fail"
    )


@pytest.mark.parametrize("receipted_output", [False, True])
def test_refusal_rejects_mutant_outputs(tmp_path, receipted_output):
    instrument = _instrument()
    _receipted_probes(tmp_path)
    assert instrument.solver_time_averaging(tmp_path)["verdict"] == "refused-by-measurement"
    _write(tmp_path / "with/point_log.txt", "Unsteady solver run time: 1.0 minutes.\n")
    if receipted_output:
        path = tmp_path / "with/receipt.json"
        receipt = json.loads(path.read_text())
        receipt["outputs"] = ["point_log.txt"]
        receipt["log_exported"] = True
        _write(path, json.dumps(receipt))
    check = instrument.solver_time_averaging(tmp_path)
    assert check["verdict"] == "could-not-measure", (
        "a mutant which writes outputs does not support the measured refusal"
    )
    assert check["measured"] == "NA"


def test_per_step_exports_rejects_a_missing_step(tmp_path):
    instrument = _instrument()
    sim = tmp_path / "sims/sim_2506"
    _write(
        sim / "actions/pfs_unsteady_actions.py",
        "TIME_ITERATIONS = 4\n"
        "STEP_DEG = 90.0\nTHRESHOLD_FORM = 'revolutions'\nTHRESHOLD = 0.5\n"
        "EXPORTS = 'EXPORT_ALL_SURFACE_SECTIONS\\npoint_cp.txt\\n'\n",
    )
    for step in (2, 3, 4):
        _write(sim / f"point_cp_iteration={step}.txt", "Section Cp\n")
    check = instrument.per_step_exports(tmp_path)
    assert check["verdict"] == "verified"
    assert check["measured"] == {
        "files": 3,
        "first_step": 2,
        "last_step": 4,
        "steps": 3,
        "expected_files": 3,
    }
    (sim / "point_cp_iteration=3.txt").unlink()
    assert instrument.per_step_exports(tmp_path)["verdict"] == "failed", (
        "a missing stamped step must not be verified"
    )


def test_missing_evidence_writes_na_and_returns_nonzero(tmp_path):
    instrument = _instrument()
    workspace = tmp_path / "missing"
    output = tmp_path / "evidence.json"
    status = instrument.main([str(workspace), str(output), "--probe-workspace", str(workspace)])
    assert status == 1, "unmeasured evidence must return nonzero"
    report = json.loads(output.read_text())
    assert set(report["checks"]) == {
        "solver_time_averaging",
        "vtk_export",
        "csv_export",
        "niter_limit",
        "per_step_exports",
    }
    for check in report["checks"].values():
        assert check["measured"] == "NA"
        assert check["verdict"] == "could-not-measure"
        assert check["how"]
    assert report["checks"]["solver_time_averaging"]["remedy"]


def _receipted_probes(root: Path) -> None:
    _probes(root)
    for variant, wall, outputs, code, killed in (
        ("without", 133.0, ["point_log.txt"], 0, False),
        ("with", 240.5, [], -1, True),
    ):
        receipt = {
            "variant": variant,
            "wall_seconds": wall,
            "outputs": outputs,
            "exit": code,
            "killed_at_limit": killed,
            "log_exported": bool(outputs),
            "script_sha256": hashlib.sha256(
                (root / variant / "probe.txt").read_bytes()
            ).hexdigest(),
            "fs_exe": "FlightStream_26124.exe",
            "fs_exe_sha256": "a" * 64,
            "measured_at": "2026-09-19T23:42:35-0300",
        }
        _write(root / variant / "receipt.json", json.dumps(receipt))


@pytest.mark.parametrize("variant", ["without", "with"])
def test_missing_probe_receipt_cannot_certify(tmp_path, variant):
    _receipted_probes(tmp_path)
    (tmp_path / variant / "receipt.json").unlink()
    check = _instrument().solver_time_averaging(tmp_path)
    assert check["verdict"] == "could-not-measure", "missing receipt must prevent certification"
    assert check["measured"] == "NA"


@pytest.mark.parametrize("variant", ["without", "with"])
def test_mismatched_probe_script_digest_cannot_certify(tmp_path, variant):
    _receipted_probes(tmp_path)
    path = tmp_path / variant / "receipt.json"
    receipt = json.loads(path.read_text())
    receipt["script_sha256"] = "0" * 64
    _write(path, json.dumps(receipt))
    check = _instrument().solver_time_averaging(tmp_path)
    assert check["verdict"] == "could-not-measure", (
        "script digest mismatch must prevent certification"
    )
    assert check["measured"] == "NA"


@pytest.mark.parametrize("variant", ["without", "with"])
def test_contradictory_probe_outputs_cannot_certify(tmp_path, variant):
    _receipted_probes(tmp_path)
    path = tmp_path / variant / "receipt.json"
    receipt = json.loads(path.read_text())
    receipt["outputs"] = [] if variant == "without" else ["unexpected.txt"]
    _write(path, json.dumps(receipt))
    check = _instrument().solver_time_averaging(tmp_path)
    assert check["verdict"] == "could-not-measure", (
        "contradictory outputs must prevent certification"
    )
    assert check["measured"] == "NA"


def test_probe_verdict_uses_receipted_measurements(tmp_path):
    _receipted_probes(tmp_path)
    instrument = _instrument()
    check = instrument.solver_time_averaging(tmp_path)
    assert check["verdict"] == "refused-by-measurement"
    measured = check["measured"]
    assert measured["control_wall_seconds"] == 133.0
    assert measured["mutant_wall_seconds"] == 240.5
    assert measured["control_output_count"] == 1
    assert measured["mutant_output_count"] == 0
    assert measured["control_exit"] == 0
    assert measured["mutant_exit"] == -1
    assert measured["control_killed_at_limit"] is False
    assert measured["mutant_killed_at_limit"] is True
    assert measured["fs_exe_sha256"] == "a" * 64
    assert measured["positions_tried"] == 1
    assert instrument.solver_time_averaging(tmp_path, remedy="")["verdict"] == "failed"
