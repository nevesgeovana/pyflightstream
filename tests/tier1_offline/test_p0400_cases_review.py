"""P0400 adversarial regressions for the cases lane."""

import json
import warnings

import pytest

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.corrections import CalibrationRow, calibration_text, parse_calibration
from pyflightstream.cases.matrix import MatrixError, convert_matrix
from pyflightstream.cases.selection import (
    alias_members_missing,
    resolve_alias,
    select_families,
    select_group_members,
)
from pyflightstream.cases.windows import averaging_steps, replan, stated_key
from pyflightstream.cases.workflows import build_script, reduction_windows
from pyflightstream.post.products import write_campaign_products
from pyflightstream.script import Script
from tests.tier1_offline.test_goal028_window_resolver import _matrix as window_matrix
from tests.tier1_offline.test_p0400_cases_matrix import CAMPAIGN, _matrix
from tests.tier1_offline.test_p0400_cases_pproc import NORMAL_PROBES
from tests.tier1_offline.test_post_products import _unsteady_workspace
from tests.tier1_offline.test_workflows import _case_for, _wb_geometry, _with_pproc, rotor_case


def test_p0400_review_probe_kind_decision_includes_volume_section(tmp_path):
    """P0400-REVIEW-PROBES: outputs and builders refuse the same mixed source."""
    spec = PprocSpec.model_validate(
        {
            "probes": [NORMAL_PROBES],
            "volume_section": {
                "shape": "rectangle",
                "plane": "YZ",
                "corners_m": [-1, -2, 1, 2],
                "points": [2, 2],
            },
        }
    )
    case = _with_pproc(_case_for("unsteady"), _wb_geometry(tmp_path), pproc=spec)
    with pytest.raises(CampaignConfigError, match="volume_section"):
        spec.outputs(True)
    with pytest.raises(CampaignConfigError, match="volume_section"):
        build_script(case, Script("26.124"))
    assert spec.outputs(False)


@pytest.mark.parametrize("token", ["Wing", ["Wing"]])
def test_p0400_review_boundary_alias_collision_has_one_meaning(token):
    """P0400-REVIEW-SELECTION: plots, groups and nested aliases select the exact label."""
    inventory = ["Wing", "Tail"]
    aliases = {"Wing": ["Tail"], "nested": ["Wing"]}
    assert select_families(token, inventory, lambda _: False, aliases) == [["Wing"]]
    assert select_group_members(["Wing"], inventory, aliases) == ["Wing"]
    assert resolve_alias("nested", inventory, aliases) == ["Wing"]
    assert alias_members_missing("Wing", inventory, {"Wing": ["Absent"]}) == []


def test_p0400_review_conversion_refuses_to_drop_row_build(tmp_path):
    """P0400-REVIEW-BUILD: an unbound per-row installation cannot silently use the default."""
    path = _matrix(tmp_path, FS_BUILD="26.125")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(MatrixError, match="9001.*FS_BUILD.*26.125.*26.124"):
            convert_matrix(path, **CAMPAIGN)


INVALID_WINDOWS = [
    {"LAST_REVS_AVG": "0.01"},
    {"LAST_REVS_AVG": "1", "LAST_ITERS_AVG": "10"},
    {"LAST_REVS_AVG": "inf"},
    {"LAST_ITERS_AVG": "0"},
    {"LAST_ITERS_AVG": "-1"},
    {"LAST_ITERS_AVG": "nan"},
]


@pytest.mark.parametrize("j", [0.7, 0.6])
def test_p0400_review_phase_wrap_uses_only_contributing_corners(j):
    """P0400-REVIEW-PHASE: a zero-weight corner cannot choose the other edge's arc."""
    rows = [
        CalibrationRow("THRUST", x, alpha, 0, 0, 1, 1, phase)
        for x, alpha, phase in [(0.5, 0, 0), (0.5, 1, 0), (0.7, 0, 170), (0.7, 1, 190)]
    ]
    calibration = parse_calibration(calibration_text("table", rows))
    found = calibration.lookup("THRUST", {"J": j, "ALPHA": 0.5})
    if j == 0.7:
        assert found.coefficients[3] % 360 == pytest.approx(180)
    else:
        assert found.coefficients is None
        assert "phase" in found.reason and "half a turn" in found.reason


@pytest.mark.parametrize("variables", INVALID_WINDOWS)
def test_p0400_review_invalid_windows_refused_by_plan_and_post(variables):
    """P0400-REVIEW-WINDOW: invalid input never becomes a recorded or one-step window."""
    plan = {"time_iterations": 1000, "steps_per_revolution": 36.0}
    case = rotor_case(LAST_REVS_AVG=None, DELTA_TIME=str(60 / (1200 * 36)))
    case.variables.update(variables)
    with pytest.raises(CampaignConfigError, match="LAST_|averag"):
        averaging_steps(variables, per_revolution=36.0)
    with pytest.raises(CampaignConfigError, match="7001"):
        reduction_windows(case)
    with pytest.raises(CampaignConfigError):
        replan(plan, variables)


@pytest.mark.parametrize("value", ["inf", "nan", "0", "-1"])
def test_p0400_review_stated_key_refuses_invalid_values(value):
    """P0400-REVIEW-WINDOW-KEY: a stated invalid value is not an absent window."""
    with pytest.raises(CampaignConfigError):
        stated_key({"LAST_REVS_AVG": value})


@pytest.mark.parametrize(
    "window",
    ["LAST_ITERS_AVG: inf", "LAST_ITERS_AVG: 0.01", "LAST_ITERS_AVG: 4 / LAST_REVS_AVG: 1"],
)
def test_p0400_review_post_records_invalid_window_refusal(tmp_path, window):
    """P0400-REVIEW-POST-WINDOW: products.json and post.log name the invalid current row."""
    plan = {
        "window_stated": True,
        "time_iterations": 8,
        "steps_per_revolution": 36.0,
        "time_average": {"windows": [[5, 8]], "window_from": "recorded"},
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan, recipe="unsteady")
    manifest = workspace.root / "runs.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))
    container = records["runs"] if isinstance(records, dict) else records
    container[0]["matrix_stem"] = "matriz"
    manifest.write_text(json.dumps(records), encoding="utf-8")
    (workspace.root / "matriz.fs").write_text(window_matrix(window), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    root = workspace.root / "post" / "matriz"
    result = json.loads((root / "products.json").read_text(encoding="utf-8"))
    reason = result["skipped"][f"runs/{container[0]['run_id']}"]
    assert "averaging window" in reason and "LAST_" in reason
    assert "averaging window" in (root / "post.log").read_text(encoding="utf-8")
    assert not any(name.endswith("_time_average.csv") for name in result.get("products", {}))
