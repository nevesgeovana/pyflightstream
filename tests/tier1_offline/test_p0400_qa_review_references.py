"""P0400-REVIEW-REFERENCES: promotion validates evidence at its own boundary.

Reproduction: update_reference must refuse an old report with an unconverged
steady point, and must never write a zero-centred relative band it cannot load.
"""

import pytest
import yaml

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import PHYSICS_SCHEMA, load_reference, update_reference


def _report(tmp_path, case_id, metric, points, value=0.35):
    path = tmp_path / "report.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": PHYSICS_SCHEMA,
                "fs_version": "26.120",
                "cases": {case_id: {"metrics": {metric: value}, "points": points}},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("case_id", "metric", "points"),
    [
        ("PHY-01", "CL_a4", [{"converged": False}]),
        ("PHY-02", "delta_CL_a4", [{"converged": True}, {"converged": False}]),
        ("PHY-06", "delta_CL_a4", [{"converged": False}, {"converged": False}]),
    ],
)
def test_p0400_review_references_unconverged_steady_evidence_is_refused(
    tmp_path, case_id, metric, points
):
    path = _report(tmp_path, case_id, metric, points)
    refs = tmp_path / "refs"
    with pytest.raises(QaEvidenceError, match="unconverged steady"):
        update_reference(case_id, path, "refresh", references_dir=refs, repo_root=tmp_path)
    assert not (refs / f"{case_id}.yaml").exists()


def test_p0400_review_references_unsteady_completion_still_promotes(tmp_path):
    path = _report(tmp_path, "PHY-06", "delta_CL_a4", [{"converged": True}, {"converged": False}])
    refs = tmp_path / "refs"
    update_reference("PHY-06", path, "refresh", references_dir=refs, repo_root=tmp_path)
    assert load_reference("PHY-06", refs) is not None


def test_p0400_review_references_incomplete_polar_pair_is_refused(tmp_path):
    path = _report(
        tmp_path,
        "PHY-06",
        "delta_CL_a4",
        [{"converged": True}, {"converged": False}, {"converged": False}],
    )
    refs = tmp_path / "refs"
    with pytest.raises(QaEvidenceError, match="paired steady and unsteady"):
        update_reference("PHY-06", path, "refresh", references_dir=refs, repo_root=tmp_path)
    assert not (refs / "PHY-06.yaml").exists()


def test_p0400_review_references_zero_relative_update_keeps_existing_bytes(tmp_path):
    path = _report(tmp_path, "PHY-01", "CL_a4", [{"converged": True}])
    refs = tmp_path / "refs"
    target = update_reference("PHY-01", path, "seed", references_dir=refs, repo_root=tmp_path)
    before = target.read_bytes()
    path = _report(tmp_path, "PHY-01", "CL_a4", [{"converged": True}], value=0.0)
    with pytest.raises(QaEvidenceError, match="relative band"):
        update_reference("PHY-01", path, "refresh", references_dir=refs, repo_root=tmp_path)
    assert target.read_bytes() == before
