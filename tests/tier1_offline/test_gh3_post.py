"""Third main reading: missing evidence costs only the affected product row."""

from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_b01_frozen_solve import _post_workspace, _products_manifest
from tests.tier1_offline.test_closing_round_post import _one_distribution
from tests.tier1_offline.test_ghmain0260_post import _matrix
from tests.tier1_offline.test_integrated_sectional_loads import EXTRA, _case


def test_ab_missing_group_surface_omits_only_its_point(tmp_path, monkeypatch):
    workspace, healthy, spec = _one_distribution(tmp_path, monkeypatch)
    spec.products.polars = True
    spec.groups = {"WING": ["Wing"]}
    other = healthy.model_copy(
        update={
            "run_id": "tail-only",
            "point_name": "AL+020",
            "sweep_name": "ALsweep",
            "point": {"alpha": 2.0},
            "outputs": ["AL+020.txt"],
        }
    )
    healthy.sweep_name = "ALsweep"
    sim = workspace.sim_dir("7001")
    (sim / "AL+020.txt").write_text((sim / "AL-020.txt").read_text().replace("Wing,", "Tail,"))
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [healthy, other])
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    keys = [
        key
        for key in manifest["products"]
        if key.startswith("polars/P") and key.endswith("_WING.csv")
    ]
    assert len(keys) == 1, manifest["skipped"]
    key = keys[0]
    out = workspace.products_dir(None)
    _, rows = read_csv_table(out / key)
    assert len(rows) == 1, "a surface-free point must not publish a row of zeros"
    assert key == "polars/P7001-AL-020_WING.csv"
    assert float(rows[0]["CLB"]) == pytest.approx(0.431)
    assert manifest["products"][key]["runs"] == [healthy.run_id]
    reason = manifest["skipped"].get(f"{key}#AL+020", "")
    assert all(word in reason for word in ("AL+020", "WING", "surface", "alias")), reason
    assert reason in (out / "post.log").read_text()
    super_keys = [key for key in manifest["products"] if "SUPER" in key.upper()]
    assert super_keys
    for super_key in super_keys:
        assert len(read_csv_table(out / super_key)[1]) == 1
        assert manifest["products"][super_key]["runs"] == [healthy.run_id]


def test_ac_unassignable_failed_frame_keeps_healthy_polar(tmp_path, monkeypatch):
    workspace, healthy, spec = _one_distribution(tmp_path, monkeypatch)
    spec.products.polars = True
    spec.groups = {"TOTAL": ["all"]}
    failed = healthy.model_copy(
        update={
            "run_id": "bad-frame-first",
            "point_name": "AL-999",
            "sweep_name": "ALsweep",
            "point": {"alpha": -99.9},
            "status": RunStatus.FAILED_INCOMPLETE_OUTPUT,
            "outputs": ["AL-999.txt"],
        }
    )
    sim = workspace.sim_dir("7001")
    native = (sim / "AL-020.txt").read_text()
    (sim / "AL-999.txt").write_text(
        native.replace("analysis:              Reference", "analysis:              ROTOR_RMRP")
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [failed, healthy])
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    key = "polars/P7001-AL-020_TOTAL.csv"
    assert key in manifest["products"], manifest["skipped"]
    assert manifest["products"][key]["runs"] == [healthy.run_id]
    out = workspace.products_dir(None)
    assert len(read_csv_table(out / key)[1]) == 1
    reason = manifest["skipped"].get("runs/bad-frame-first", "")
    assert all(word in reason for word in ("AL-999", "ROTOR_RMRP", "frame")), reason
    assert reason in (out / "post.log").read_text()


@pytest.mark.parametrize("selection", ["rotor", "common", "unknown"])
def test_ad_unrecorded_family_cannot_shrink_integration_match(tmp_path, monkeypatch, selection):
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    if selection == "rotor":
        record.matrix_stem = "products"
        _matrix(workspace)
        reference = workspace.inputs_dir / "references/r001.toml"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text(
            "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
            '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
            'families_blades = ["Blade1", "Blade2"]\n'
        )
        record.sections_layout[0]["frame"] = "R_RMRP"
        entry.families = "R"
        entry.frame = "RMRP"
        family = "Blade1"
    else:
        family = "Wing"
        record.sections_layout[0].update(
            families=[family], distribution_families=family, frame="MRP"
        )
        entry.families = ["Wing", "Tail"] if selection == "common" else "all"
        entry.frame = "MRP"
    write_campaign_products(workspace, matrix_stem=record.matrix_stem)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(record.matrix_stem)
    key = f"sections/AL-020_sloads_{family}.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "layout silence must not remove selected families"
    assert len(rows) == 4
    reason = manifest["skipped"].get(f"{key}#integration", "")
    assert "missing" in reason and "block 1" in reason
    log = (out / "post.log").read_text()
    assert key in log and "without integrated columns" in log


@pytest.mark.parametrize("archive", [False, True])
def test_ae_unsteady_name_uses_averaged_contributors(tmp_path, monkeypatch, archive):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    healthy = workspace.read_manifest()[0]
    sim = workspace.sim_dir("7001")
    healthy.outputs = [name.replace("AL-020", "AL+020") for name in healthy.outputs]
    for name in healthy.outputs:
        target = sim / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((sim / name.replace("AL+020", "AL-020")).read_bytes())
    healthy.point_name = "AL+020"
    healthy.point = {"alpha": 2.0}
    healthy.sweep_name = "ALsweep"
    missing = healthy.model_copy(
        update={
            "run_id": "missing-history",
            "point_name": "AL-020",
            "point": {"alpha": -2.0},
            "outputs": ["datapoints/DP-AL-020/AL-020.txt"],
        }
    )
    records = [healthy]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: records)
    write_campaign_products(workspace)
    out = workspace.products_dir(None)
    key = "polars/P7001_AL+020_uns_avg.csv"
    assert key in _products_manifest(workspace)["products"]
    records[:] = [missing, healthy]
    write_campaign_products(workspace, overwrite=True, archive=archive)
    manifest = _products_manifest(workspace)
    assert key in manifest["products"], manifest["skipped"]
    assert {p.name for p in (out / "polars").glob("*_uns_avg.csv")} == {Path(key).name}
    assert len(read_csv_table(out / key)[1]) == 1
    assert manifest["products"][key]["runs"] == [healthy.run_id]
    assert "AL-020" in manifest["skipped"].get(key, "")
    assert key in (out / "post.log").read_text()


def test_af_released_changelog_has_no_development_version():
    text = (Path(__file__).resolve().parents[2] / "CHANGELOG.md").read_text(encoding="utf-8")
    release = text.split("## [0.26.0]", 1)[1].split("\n## [", 1)[0]
    assert "0.26.0.dev0" not in release
    assert "[Migrating to 0.26.0](docs/migrating-to-0.26.0.md)" in release


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("selection", ["Blade", "blade_alias"])
def test_ad_a_family_stem_still_expands_over_the_recorded_cuts(
    tmp_path, monkeypatch, legacy, selection
):
    """`families = "Blade"` over a block of Blade1 and Blade2 resolves as the builder resolves it.

    The geometry inventory keeps an unrecorded member so silence cannot shrink a
    match; a family STEM the recorded cuts already expand is not an unrecorded
    member, and appending it as a literal boundary name made the resolver pick
    the invented name instead of the two blades.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.aliases = {"blade_alias": ["Blade"]}
    record.sections_layout[0].update(
        families=["Blade1", "Blade2"], distribution_families=selection, frame="MRP"
    )
    if legacy:
        del record.sections_layout[0]["distribution"]
        del record.sections_layout[0]["distribution_families"]
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    entry.families = selection
    entry.frame = "MRP"
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    key = f"sections/AL-020_sloads_{selection}.csv"
    assert key in manifest["products"], manifest["skipped"]
    columns, rows = read_csv_table(out / key)
    assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"Blade1+Blade2"}
