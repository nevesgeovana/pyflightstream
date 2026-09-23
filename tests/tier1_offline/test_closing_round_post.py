"""Closing regressions preserve recorded products across changes and missing inputs."""

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.cases import PprocSpec, select_group_members
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_b01_frozen_solve import (
    FIXTURES,
    _make_one_step_unreadable,
    _post_workspace,
    _products_manifest,
)
from tests.tier1_offline.test_f07_section_distributions import _workspace
from tests.tier1_offline.test_integrated_sectional_loads import EXTRA


def _one_distribution(tmp_path, monkeypatch, *, stamped=False):
    workspace, record = _workspace(tmp_path, monkeypatch, stamped=stamped)
    record.sections_layout = [
        dict(
            distribution=1,
            distribution_families="wing",
            families=["Wing"],
            plane="XZ",
            frame="MRP",
            count=2,
        )
    ]
    spec = PprocSpec.model_validate(
        {
            "sections": {
                "distributions": [
                    {"families": "wing", "planes": ["XZ"], "count": 2, "integrate": False}
                ]
            },
            "products": {"polars": False, "sections": True},
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: spec)
    return workspace, record, spec


@pytest.mark.parametrize("current", ["absent", "renamed-off", "renamed-on"])
def test_n_legacy_ownership_survives_current_pproc(tmp_path, monkeypatch, current):
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    for block in record.sections_layout:
        del block["distribution"]
        del block["distribution_families"]
    write_campaign_products(workspace)
    key = "sections/AL-020_cp_wing.csv"
    original = read_csv_table(workspace.products_dir(None) / key)
    identity = _products_manifest(workspace)["products"][key]
    effective = recorded.model_copy(deep=True)
    record.aliases["new_wing"] = ["Wing"]
    if current == "absent":
        effective.sections.distributions = []
    else:
        effective.sections.distributions[0].families = "new_wing"
        effective.sections.distributions[0].integrate = current == "renamed-on"
    specs = {"p001": recorded, "p002": effective}
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    record.matrix_stem = "products"
    (workspace.root / "products.fs").write_text(
        (FIXTURES / "superfile_matriz.fs")
        .read_text()
        .replace("6001", "7001")
        .replace("p001", "p002")
    )
    write_campaign_products(workspace, matrix_stem="products", overwrite=True)
    out = workspace.products_dir("products")
    manifest = _products_manifest(workspace)
    assert key in manifest["products"], manifest["skipped"]
    assert read_csv_table(out / key) == original
    assert manifest["products"][key] == identity
    assert not list((out / "sections").glob("*new_wing*"))
    columns, rows = read_csv_table(out / "sections/AL-020_sloads_wing.csv")
    assert len(rows) == 2
    assert all(name in columns for name in EXTRA) is (current == "renamed-on")


@pytest.mark.parametrize("invalid", [False, True])
def test_o_unresolved_pproc_keeps_recorded_histories(tmp_path, monkeypatch, invalid):
    workspace, record, _ = _one_distribution(tmp_path, monkeypatch, stamped=True)
    # Use the real loader for both a missing artifact and an invalid artifact.
    monkeypatch.undo()
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    if invalid:
        (workspace.inputs_dir / "pproc/p001.toml").write_text("[groups]\nTOTAL = []\n")
    write_campaign_products(workspace)
    out = workspace.products_dir(None)
    manifest = _products_manifest(workspace)
    for key, count in (
        ("sections/AL-020_cp_wing.csv", 36),
        ("sections/AL-020_sloads_wing.csv", 6),
        ("series/AL-020_sections_series.csv", 6),
    ):
        assert key in manifest["products"], manifest["skipped"]
        assert len(read_csv_table(out / key)[1]) == count
    key = "sections/AL-020_sloads_wing.csv#integration"
    assert "p001" in manifest["skipped"].get(key, "")
    log = (out / "post.log").read_text()
    assert key in log and "p001" in log


@pytest.mark.parametrize("asked", [False, True])
def test_p_combined_span_judges_gap_between_passages(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2411, (58, 61), passages=[(58, 58), (59, 59), (61, 61)])
    _make_one_step_unreadable(workspace, 60)
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    key = "probes/AL-020_per_blade.csv"
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert any(key in line and "60" in line and "unread" in line for line in log.splitlines()), log
    assert (key in manifest["products"]) is not asked
    if not asked:
        assert manifest["products"][key]["windows"] == [[58, 61]]


@pytest.mark.parametrize("archive", [False, True])
@pytest.mark.parametrize("survivor", [False, True])
def test_q_malformed_repost_retires_run_products(tmp_path, monkeypatch, archive, survivor):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    record = workspace.read_manifest()[0]
    raw = workspace.sim_dir("7001") / "datapoints/DP-AL-020"
    record.export_window = {"first_step": 58, "time_iterations": 61, "delta_time_s": 0.01}
    for step in range(58, 62):
        for suffix in ("", "_sloads"):
            (raw / f"AL-020{suffix}_iteration={step}.txt").write_bytes(
                (raw / f"AL-020{suffix}.txt").read_bytes()
            )
    records = [record]
    if survivor:
        surviving_raw = raw.parent / "DP-AL-030"
        surviving_raw.mkdir()
        for path in list(raw.glob("AL-020*.txt")):
            (surviving_raw / path.name.replace("AL-020", "AL-030")).write_bytes(path.read_bytes())
        records.append(
            record.model_copy(
                update={
                    "run_id": "surviving-point",
                    "point_name": "AL-030",
                    "sweep_name": "AL-030",
                    "outputs": [name.replace("AL-020", "AL-030") for name in record.outputs],
                }
            )
        )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: records)
    write_campaign_products(workspace)
    out = workspace.products_dir(None)
    before = {key: (out / key).read_bytes() for key in _products_manifest(workspace)["products"]}
    (raw / "AL-020.txt").write_text("loads export truncated\n")
    write_campaign_products(workspace, overwrite=True, archive=archive)
    manifest = _products_manifest(workspace)
    assert f"runs/{record.run_id}" in manifest["skipped"]
    assert "series/AL-020_sections_series.csv" in manifest["products"]
    retired = before.keys() - manifest["products"].keys()
    assert "probes/AL-020_plots.csv" in retired
    assert any(key.startswith("polars/") for key in retired) is not survivor
    for key in retired:
        path = out / key
        assert not path.exists(), f"stale product remains current: {key}"
        copies = list(path.parent.glob(f"archive/*/{path.name}"))
        assert len(copies) == int(archive)
        if archive:
            assert copies[0].read_bytes() == before[key]
    assert all((out / key).is_file() for key in manifest["products"])


def test_r_each_uses_section_selector_semantics(tmp_path, monkeypatch):
    workspace, _, spec = _one_distribution(tmp_path, monkeypatch)
    spec.sections.distributions[0].families = "each"
    spec.sections.distributions[0].integrate = True
    write_campaign_products(workspace)
    columns, rows = read_csv_table(workspace.products_dir(None) / "sections/AL-020_sloads_wing.csv")
    assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {"Wing"}
    assert tuple(columns[-4:]) == EXTRA


@pytest.mark.parametrize("shape", ["boundary", "alias"])
def test_t_empty_group_remedy_accounts_for_all_collision(shape):
    inventory = ["W", "B", "all"] if shape == "boundary" else ["W", "B"]
    aliases = {"whole_aircraft": inventory, **({"all": ["W"]} if shape == "alias" else {})}
    with pytest.raises(InputArtifactError) as caught:
        PprocSpec(groups={"TOTAL": []})
    message = str(caught.value)
    assert all(word in message for word in ("boundary", "alias", "all", "unique alias")), message
    assert "only if" in message, message
    with pytest.warns(PyflightstreamWarning):
        assert select_group_members(["all"], inventory, aliases) != inventory
    assert select_group_members(["whole_aircraft"], inventory, aliases) == inventory


@pytest.mark.parametrize("recipe", [None, "user_recipes:steady_case"])
@pytest.mark.parametrize("asked", [False, True])
@pytest.mark.parametrize(
    "fixture", ["log_residuals_paged_26.123.txt", "log_residuals_overflow_26.123.txt"]
)
def test_u_steady_log_mode_does_not_depend_on_recipe(tmp_path, monkeypatch, recipe, asked, fixture):
    workspace, record, _ = _one_distribution(tmp_path, monkeypatch)
    record.recipe = recipe
    path = workspace.sim_dir("7001") / "AL-020_log.txt"
    path.write_bytes((FIXTURES / fixture).read_bytes())
    record.outputs.append(path.name)
    write_campaign_products(workspace, check_frozen=asked)
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "no unsteady residual evidence" not in log
    assert "product=native-log" not in log
    assert "sections/AL-020_sections.csv" in _products_manifest(workspace)["products"]


@pytest.mark.parametrize(
    "text,mode",
    [
        ("Solver run time: 1 minutes.", "steady"),
        ("Unsteady solver run time: 1 minutes.", "unsteady"),
        ("Solving unsteady time-step iteration (1/2)", "unsteady"),
        ("header only", None),
    ],
)
def test_u_log_parser_states_mode_or_unknown(text, mode):
    from pyflightstream.results import parse_log_times

    assert parse_log_times(text).solver_mode == mode


@pytest.mark.parametrize(
    "name",
    [
        "docs/post-processing-definitions.md",
        "CHANGELOG.md",
        "reports/RPT-055_partial-residual-anchor_2026-09-22.md",
    ],
)
def test_s_terminal_cut_contract_requires_a_residual_page(name):
    text = (Path(__file__).resolve().parents[2] / name).read_text(encoding="utf-8")
    assert "at least one residual page" in text
    if name.startswith("reports/"):
        assert "### Clarification, 2026-09-23" in text
