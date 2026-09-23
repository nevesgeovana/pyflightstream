"""Re-post recorded exports after a mismatch, a lost history, or a frozen solve."""

from pathlib import Path

import pytest

from pyflightstream.post import products
from pyflightstream.post.products import ProductError, read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_b01_frozen_solve import _log, _post_workspace
from tests.tier1_offline.test_f01_probe_source import PLOTS_HEADER
from tests.tier1_offline.test_f01_probe_source import _post_workspace as probe_workspace
from tests.tier1_offline.test_f07_section_distributions import _workspace
from tests.tier1_offline.test_post_products import _products_manifest


def test_reference_mismatch_refuses_all_distribution_tables(tmp_path, monkeypatch):
    workspace, record = _workspace(tmp_path, monkeypatch)
    record.reference["SREF"] = 99.0
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "reference" in manifest["skipped"]["7001"]
    assert not list(workspace.products_dir(None).glob("sections/*.csv")), (
        "reference mismatch published distribution tables"
    )


@pytest.mark.parametrize("source", ["missing", "unreadable", "empty"])
def test_requested_probe_skip_names_source_and_remedy(tmp_path, monkeypatch, source):
    workspace = probe_workspace(tmp_path, monkeypatch)
    path = workspace.sim_dir("7001") / "outputs/AL-020_plots.txt"
    if source == "missing":
        path.unlink()
    elif source == "empty":
        path.write_text("", newline="\n")
    else:
        original = Path.read_text

        def denied(self, *args, **kwargs):
            if self == path:
                raise PermissionError("test plots access denied")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    try:
        write_campaign_products(workspace)
    except OSError as error:
        pytest.fail(f"probe source failure escaped post: {error}")
    reason = _products_manifest(workspace)["skipped"].get("probes/AL-020_probes.csv", "")
    assert reason, f"requested probes lost without a {source} source skip"
    assert any(word in reason.lower() for word in ("restore", "collect", "run again"))
    assert ("missing" if source == "missing" else "history") in reason.lower()


def test_mixed_probe_parameters_keep_available_samples(tmp_path, monkeypatch):
    workspace = probe_workspace(tmp_path, monkeypatch, cited_parameters='["VX"]')
    workspace.read_manifest()[0].reductions = {
        "time_iterations": 2,
        "time_average": {"windows": [[1, 2]]},
    }
    path = workspace.sim_dir("7001") / "outputs/AL-020_plots.txt"
    path.write_text(
        PLOTS_HEADER
        + "Time-step,CL_MRP_TOTAL,MACH1,VELOCITY1,MACH2,VELOCITY2,VX3,VX4\n"
        + "1,0.1,0.2,10,0.3,20,30,40\n2,0.2,0.4,11,0.5,21,31,41\n"
        + "-" * 60
        + "\n     Force Units: Coefficients\n",
        newline="\n",
    )
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    key = "probes/AL-020_probes.csv"
    assert key in manifest["products"], "mixed parameters lost available probe history"
    _, rows = read_csv_table(workspace.products_dir(None) / key)
    assert len(rows) == 8
    first = {int(row["PROBE"]): row for row in rows if row["STEP"] == "1"}
    assert float(first[1]["MACH"]) == 0.2
    assert first[1]["VX"] == "NA"
    assert float(first[3]["VX"]) == 30
    assert first[3]["MACH"] == "NA"
    assert any(name.endswith("_uns_avg.csv") for name in manifest["products"])


def test_probe_writer_refusal_does_not_abort_other_products(tmp_path, monkeypatch):
    workspace = probe_workspace(tmp_path, monkeypatch)

    workspace.read_manifest()[0].reductions = {
        "time_iterations": 2,
        "time_average": {"windows": [[1, 2]]},
    }

    def refuse(*args, **kwargs):
        raise ProductError("bad probe history; restore the plots export")

    monkeypatch.setattr(products, "write_unsteady_probes_table", refuse)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_probes.csv" in manifest["skipped"], "probe refusal escaped its product"
    assert any(name.endswith("_uns_avg.csv") for name in manifest["products"])


@pytest.mark.parametrize("window", [(58, 59), (60, 61)])
def test_frozen_failed_record_keeps_histories_and_safe_windows(tmp_path, monkeypatch, window):
    workspace = _post_workspace(tmp_path, 2413, window)
    record = workspace.read_manifest()[0].model_copy(update={"status": RunStatus.FAILED_DIVERGED})
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    # Since 0.25.1 the native log is read only when asked (her decision of
    # 2026-09-22); this test is about what the reading refuses, so it asks.
    write_campaign_products(workspace, check_frozen=True)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_plots.csv" in manifest["products"], "frozen failure lost its history"
    assert "sections/AL-020_sections.csv" in manifest["products"]
    key = "probes/AL-020_time_average.csv"
    assert key in manifest["products" if window[1] < 60 else "skipped"]
    assert record.status is RunStatus.FAILED_DIVERGED


@pytest.mark.parametrize("archive", [True, False])
def test_malformed_repost_retires_previous_distribution(tmp_path, monkeypatch, archive):
    workspace, _ = _workspace(tmp_path, monkeypatch)
    write_campaign_products(workspace)
    key = "sections/AL-020_cp_wing.csv"
    table = workspace.products_dir(None) / key
    before = table.read_bytes()
    (workspace.sim_dir("7001") / "AL-020_cp.txt").write_text("truncated", newline="\n")
    write_campaign_products(workspace, overwrite=True, archive=archive)
    assert key in _products_manifest(workspace)["skipped"]
    assert not table.exists(), "refused distribution remains current"
    copies = list(table.parent.glob("archive/*/AL-020_cp_wing.csv"))
    assert len(copies) == int(archive)
    if archive:
        assert copies[0].read_bytes() == before


@pytest.mark.parametrize("archive", [True, False])
def test_frozen_repost_retires_previous_average(tmp_path, archive):
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    write_campaign_products(workspace, check_frozen=True)
    log = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    log.write_text(_log(2413), newline="\n")
    write_campaign_products(workspace, overwrite=True, archive=archive, check_frozen=True)
    key = "probes/AL-020_time_average.csv"
    assert key in _products_manifest(workspace)["skipped"]
    assert not (workspace.products_dir(None) / key).exists(), "frozen average remains current"


@pytest.mark.parametrize("archive", [True, False])
def test_reference_refused_repost_retires_previous_tables(tmp_path, monkeypatch, archive):
    workspace, record = _workspace(tmp_path, monkeypatch)
    write_campaign_products(workspace)
    record.reference["SREF"] = 99.0
    write_campaign_products(workspace, overwrite=True, archive=archive)
    assert "7001" in _products_manifest(workspace)["skipped"]
    assert not list(workspace.products_dir(None).glob("sections/*.csv")), (
        "reference-refused rebuild left old tables current"
    )


@pytest.mark.parametrize("archive", [True, False])
def test_unresolved_layout_repost_retires_previous_split(tmp_path, monkeypatch, archive):
    workspace, record = _workspace(tmp_path, monkeypatch)
    write_campaign_products(workspace)
    record.sections_layout = None
    write_campaign_products(workspace, overwrite=True, archive=archive)
    key = "sections/AL-020_cp#distributions"
    assert key in _products_manifest(workspace)["skipped"]
    assert not (workspace.products_dir(None) / "sections/AL-020_cp_wing.csv").exists(), (
        "unresolved distribution left its old table current"
    )
