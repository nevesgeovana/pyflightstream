"""P0400-REVIEW-PROOFS: regressions exercise entry points present before the fix.

Reproduction: reduce two campaigns in one manifest, reduce a single-point
case containing a sweep, and promote into the repository's own database.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pyflightstream.qa import compat
from pyflightstream.qa import matrix as matrix_module
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import PointResult
from tests.tier1_offline.test_p0400_qa_compat import _commands, _report
from tests.tier1_offline.test_p0400_qa_matrix import ROW, _fake_workspace, _record, _workspace

REPO = Path(__file__).resolve().parents[2]
METRICS_SPEC = importlib.util.spec_from_file_location(
    "p0400_qa_review_architecture", REPO / "scripts" / "arch_metrics.py"
)
assert METRICS_SPEC is not None and METRICS_SPEC.loader is not None
am = importlib.util.module_from_spec(METRICS_SPEC)
sys.modules[METRICS_SPEC.name] = am
METRICS_SPEC.loader.exec_module(am)
BASELINES = json.loads(
    (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(encoding="utf-8")
)


def test_p0400_review_proofs_campaign_filter_reaches_the_reducer(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    records = [_record("ws/sim_5002/AL+004"), _record("other/sim_5002/AL+004")]
    observed = []

    def reduce_case(case_id, rows, workspace, by_row, steady_rows, matrix):
        observed.extend(record.run_id for record in by_row["5002"])
        return (), {}

    monkeypatch.setattr(matrix_module, "_reduce_case", reduce_case)
    monkeypatch.setattr(matrix_module, "load_reference", lambda *args, **kwargs: None)
    matrix_module.reduce_physics(_fake_workspace(root, records), root / "matriz_physics.fs")
    assert observed
    assert set(observed) == {"ws/sim_5002/AL+004"}


def test_p0400_review_proofs_single_point_case_refuses_through_its_caller(tmp_path, monkeypatch):
    points = [PointResult(a, {"CL": 0.1}, 10, True, f"p{a:g}") for a in (2.0, 4.0)]
    monkeypatch.setattr(matrix_module, "_points_of_row", lambda *args: points)
    with pytest.raises(QaEvidenceError, match="reads one point"):
        matrix_module._reduce_case("PHY-05", [ROW], None, {}, [], tmp_path / "matrix.fs")


def test_p0400_review_proofs_default_promotion_writes_the_named_repository(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    inside = _commands(root / "src" / "pyflightstream" / "commands")
    installed = _commands(tmp_path / "installed" / "commands")
    before = (installed / "script_controls.yaml").read_bytes()
    monkeypatch.setattr(compat.resources, "files", lambda package: installed)
    report = _report(root, {"STOP": {"outcome": "verified", "detail": "halted"}})
    compat.apply_compat(report, repo_root=root)
    assert "status: verified" in (inside / "script_controls.yaml").read_text(encoding="utf-8")
    assert (installed / "script_controls.yaml").read_bytes() == before


@pytest.mark.parametrize(
    "relative",
    [
        "probes/geometry.py",
        "probes/planar.py",
        "qa/cli.py",
        "qa/compat.py",
        "qa/matrix.py",
        "qa/physics.py",
        "qa/probes.py",
    ],
)
def test_p0400_review_proofs_function_ratchets_hold_for_the_changed_modules(relative):
    source = (REPO / "src" / "pyflightstream" / relative).read_text(encoding="utf-8")
    tree = am.Tree({relative: source})
    limits = {
        key: value
        for key, value in BASELINES["function_limits"].items()
        if key.startswith(relative + ":")
    }
    lengths = {
        key: value
        for key, value in BASELINES["function_lines"].items()
        if key.startswith(relative + ":")
    }
    assert am.function_findings(tree, lengths, limits) == []
