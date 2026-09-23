"""Independent main-reading regressions for metadata, retirement and live aliases."""

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_b01_frozen_solve import (
    FIXTURES,
    _post_workspace,
    _products_manifest,
)
from tests.tier1_offline.test_closing_round_post import _one_distribution
from tests.tier1_offline.test_integrated_sectional_loads import EXTRA, _case


def _matrix(workspace):
    (workspace.root / "products.fs").write_text(
        (FIXTURES / "superfile_matriz.fs").read_text().replace("6001", "7001")
    )


@pytest.mark.parametrize("matrix", [False, True])
def test_v_metadata_poor_failure_first_keeps_healthy_polar(tmp_path, monkeypatch, matrix):
    workspace = _case(tmp_path, monkeypatch, option=False)
    healthy = workspace.read_manifest()[0]
    healthy.matrix_stem = "products" if matrix else None
    failed = healthy.model_copy(
        update={
            "run_id": "failed-script",
            "point_name": "AL-999",
            "sweep_name": "AL-999",
            "status": RunStatus.FAILED_SCRIPT,
            "pproc": None,
            "mach": None,
            "reference": None,
            "description": None,
            "outputs": [],
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [failed, healthy])
    if matrix:
        _matrix(workspace)
    write_campaign_products(workspace, matrix_stem=healthy.matrix_stem)
    manifest = _products_manifest(workspace)
    key = "polars/P7001-AL-020_TOTAL.csv"
    assert key in manifest["products"], manifest["skipped"]
    assert manifest["products"][key]["runs"] == [healthy.run_id]
    assert manifest["products"][key]["pproc"] == "p001"
    out = workspace.products_dir(healthy.matrix_stem)
    _, rows = read_csv_table(out / key)
    assert len(rows) == 1 and float(rows[0]["MACH"]) == pytest.approx(0.2)
    reason = manifest["skipped"].get("runs/failed-script", "")
    assert "FAILED_SCRIPT" in reason and "metadata" in reason
    log = (out / "post.log").read_text()
    assert "runs/failed-script" in log and reason in log
    assert healthy.pproc == "p001" and failed.pproc is None


@pytest.mark.parametrize("archive", [False, True])
def test_w_status_refusal_retires_previous_products(tmp_path, monkeypatch, archive):
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    record = workspace.read_manifest()[0]
    record.status = RunStatus.FAILED_INCOMPLETE_OUTPUT
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    write_campaign_products(workspace)
    out = workspace.products_dir(None)
    before = {key: (out / key).read_bytes() for key in _products_manifest(workspace)["products"]}
    assert "probes/AL-020_time_average.csv" in before
    assert "probes/AL-020_plots.csv" in before
    assert "FAILED_INCOMPLETE_OUTPUT" in (out / "post.log").read_text()
    write_campaign_products(workspace, overwrite=True, check_frozen=True, archive=archive)
    manifest = _products_manifest(workspace)
    assert manifest["complete"] is True
    assert not manifest["products"]
    for key, contents in before.items():
        path = out / key
        assert not path.exists(), f"stale product remains current: {key}"
        copies = list(path.parent.glob(f"archive/*/{path.name}"))
        assert len(copies) == int(archive)
        if archive:
            assert copies[0].read_bytes() == contents
    reason = manifest["skipped"].get(f"runs/{record.run_id}", "")
    assert "FAILED_INCOMPLETE_OUTPUT" in reason and "check_frozen=True" in reason
    log = (out / "post.log").read_text()
    assert f"runs/{record.run_id}" in log and reason in log


@pytest.mark.parametrize("legacy", [False, True])
def test_x_integration_resolves_new_alias_only_in_live_reference(tmp_path, monkeypatch, legacy):
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    record.aliases = {"old_wing": ["Wing"]}
    recorded.sections.distributions[0].families = "old_wing"
    record.sections_layout[0]["distribution_families"] = "old_wing"
    if legacy:
        del record.sections_layout[0]["distribution"]
        del record.sections_layout[0]["distribution_families"]
    original = record.model_dump()
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        'area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n[aliases]\nnew_wing = ["Wing"]\n'
    )
    current = recorded.model_copy(deep=True)
    current.sections.distributions[0].families = "new_wing"
    current.sections.distributions[0].integrate = True
    specs = {"p001": recorded, "p002": current}
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    matrix = workspace.root / "products.fs"
    matrix.write_text(matrix.read_text().replace("p001", "p002"))
    write_campaign_products(workspace, matrix_stem="products")
    out = workspace.products_dir("products")
    manifest = _products_manifest(workspace)
    key = "sections/AL-020_sloads_old_wing.csv"
    columns, rows = read_csv_table(out / key)
    assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
    assert {row["FAMILY"] for row in rows} == {"Wing"}
    assert manifest["products"][key]["families"] == "old_wing"
    assert f"{key}#integration" not in manifest["skipped"]
    assert record.aliases == original["aliases"]
    assert record.sections_layout == original["sections_layout"]
    assert not list((out / "sections").glob("*new_wing*"))


def test_v_a_successful_record_wins_a_metadata_conflict_and_only_absent_fields_fall_back():
    """The QA read of the reading's fixes, 2026-09-23: the preference was unguarded.

    The six cases above remove the failed record's metadata, so an input-order
    choice passed them all while taking the FAILED record's pproc over the
    successful one's. Here both carry conflicting values: the successful
    record's win on every field it carries, and a field it lacks falls back to
    the failed record's, which is the field-by-field contract.
    """
    from pyflightstream.post.products import _simulation_metadata
    from pyflightstream.workspace import RunRecord

    base = dict(
        sim_id="7001",
        fs_version_requested="26.124",
        package_version="0.26.0",
        script_sha256="0" * 64,
        raw_flag=False,
        outputs=[],
    )
    failed = RunRecord(
        run_id="camp/sim_7001/failed",
        status=RunStatus.FAILED_SCRIPT,
        pproc="failed",
        mach=0.8,
        description="FAILED_DESC",
        **base,
    )
    healthy = RunRecord(
        run_id="camp/sim_7001/healthy",
        status=RunStatus.CONVERGED,
        pproc="p001",
        mach=0.2,
        description=None,
        **base,
    )
    chosen = _simulation_metadata([failed, healthy])
    assert chosen.pproc == "p001", "the failed record's pproc won over the successful one's"
    assert chosen.mach == 0.2, "the failed record's Mach won over the successful one's"
    assert chosen.description == "FAILED_DESC", "a field the successful record lacks falls back"
    assert chosen.run_id == healthy.run_id, "the carrier of record is the successful one"


@pytest.mark.parametrize("archive", [False, True])
@pytest.mark.parametrize("previous", ["healthy", "failed"])
def test_y_skipped_first_record_cannot_name_or_leave_a_stale_polar(
    tmp_path, monkeypatch, archive, previous
):
    workspace, healthy, spec = _one_distribution(tmp_path, monkeypatch)
    spec.products.polars = True
    spec.groups = {"TOTAL": ["all"]}
    sim = workspace.sim_dir("7001")
    failed = healthy.model_copy(
        update={
            "run_id": "failed-first",
            "point_name": "AL-999",
            "sweep_name": "AL-999",
            "status": RunStatus.FAILED_INCOMPLETE_OUTPUT,
            "outputs": ["AL-999.txt"],
        }
    )
    (sim / "AL-999.txt").write_bytes((sim / "AL-020.txt").read_bytes())
    records = [healthy] if previous == "healthy" else [failed]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: records)
    write_campaign_products(workspace)
    out = workspace.products_dir(None)
    old_key = f"polars/P7001-{'AL-020' if previous == 'healthy' else 'AL-999'}_TOTAL.csv"
    old_bytes = (out / old_key).read_bytes()
    records[:] = [failed, healthy]
    (sim / "AL-999.txt").write_text("loads export truncated\n")
    key = "polars/P7001-AL-020_TOTAL.csv"
    for value in ("+0.4310000", "+0.5310000"):
        native = sim / "AL-020.txt"
        native.write_text(native.read_text().replace("+0.4310000", value))
        write_campaign_products(workspace, overwrite=True, archive=archive)
        manifest = _products_manifest(workspace)
        assert key in manifest["products"], manifest["skipped"]
        assert manifest["products"][key]["runs"] == [healthy.run_id]
        assert float(read_csv_table(out / key)[1][0]["CLB"]) == pytest.approx(float(value))
        assert {p.name for p in (out / "polars").glob("P7001-*_TOTAL.csv")} == {
            "P7001-AL-020_TOTAL.csv"
        }
        if previous == "failed" and value == "+0.4310000":
            assert old_key in manifest["skipped"]
            assert old_key in (out / "post.log").read_text()
            copies = list((out / "polars").glob("archive/*/P7001-AL-999_TOTAL.csv"))
            assert len(copies) == int(archive)
            if archive:
                assert copies[0].read_bytes() == old_bytes


def test_z_combined_entry_does_not_integrate_separate_recorded_blocks(tmp_path, monkeypatch):
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    spec = workspace.resolve_pproc("p001")
    for k, (block, family) in enumerate(
        zip(record.sections_layout, ("Wing", "Tail"), strict=True), 1
    ):
        block.update(distribution=k, distribution_families=family, families=[family], frame="MRP")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": ["Wing", "Tail"], "frame": "MRP"})
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    log = (out / "post.log").read_text()
    for number, family in enumerate(("Wing", "Tail"), 1):
        key = f"sections/AL-020_sloads_{family}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{family} inherited combined-entry integration"
        assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {family}
        reason = manifest["skipped"].get(f"{key}#integration", "")
        assert f"block {number}" in reason and "missing" in reason
        warnings = [
            line
            for line in log.splitlines()
            if key in line and "without integrated columns" in line
        ]
        assert len(warnings) == 1, warnings


@pytest.mark.parametrize("selection", ["PUSHER", "renamed_blades"])
def test_aa_rotor_names_and_live_aliases_use_builder_expansion(tmp_path, monkeypatch, selection):
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0]["frame"] = "PUSHER_RMRP1"
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nrenamed_blades = ["PUSHER"]\n'
        '[rotors.PUSHER]\nalias = "PUSHER"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Blade1"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    spec.sections.distributions[0].families = selection
    write_campaign_products(workspace, matrix_stem="products")
    key = "sections/AL-020_sloads_Blade1.csv"
    manifest = _products_manifest(workspace)
    columns, rows = read_csv_table(workspace.products_dir("products") / key)
    assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"Blade1"}
    assert f"{key}#integration" not in manifest["skipped"]
    assert manifest["products"][key]["families"] == "Blade1"


@pytest.mark.parametrize("integrate", [False, True])
@pytest.mark.parametrize(
    ("frame", "block_frames", "names"),
    [
        ("LOCAL_AXIS", ("ROTOR_RMRP1", "ROTOR_RMRP2"), ("Blade1", "Blade2")),
        ("LOCAL_AXIS", ("ROTOR_RMRP1", "ROTOR_RMRP2"), ("PB_1", "PB_2")),
        ("RMRP", ("L_RMRP", "R_RMRP"), ("Blade1", "Blade2")),
        ("SMRP", ("L_SMRP", "R_SMRP_ORIGINAL"), ("Blade1", "Blade2")),
    ],
)
def test_ab_legacy_layout_keeps_one_expanding_entry_over_two_blocks(
    tmp_path, monkeypatch, integrate, frame, block_frames, names
):
    """An entry on an expanding frame was recorded as one block per rotor or blade.

    A legacy layout carries no distribution identity and no rotor definition
    reaches the matcher, so the fallback cannot rebuild the builder's grouping;
    what it knows is that on an expanding frame each emitted block is a SUBSET
    of the entry's selection. The equal-set rule alone rejected every block and
    the split lost its raw files, and a blade predicate by name pattern lost a
    declared blade named outside the pattern.
    """
    workspace = _case(tmp_path, monkeypatch, option=integrate, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for block, block_frame, name in zip(record.sections_layout, block_frames, names, strict=True):
        del block["distribution"]
        del block["distribution_families"]
        block.update(families=[name], frame=block_frame)
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": list(names), "frame": frame})
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    key = f"sections/AL-020_sloads_{'-'.join(names)}.csv"
    assert key in manifest["products"], manifest["skipped"]
    columns, rows = read_csv_table(out / key)
    assert {row["FAMILY"] for row in rows} == set(names) and len(rows) == 4
    assert (tuple(columns[-4:]) == EXTRA) is integrate, manifest["skipped"]
    assert f"{key}#integration" not in manifest["skipped"]


def test_ab_legacy_common_frame_entry_still_needs_the_whole_block(tmp_path, monkeypatch):
    """The subset rule stays out of a common frame: Z's case holds on a legacy layout."""
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for block, family in zip(record.sections_layout, ("Wing", "Tail"), strict=True):
        del block["distribution"]
        del block["distribution_families"]
        block.update(families=[family], frame="MRP")
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": ["Wing", "Tail"], "frame": "MRP"})
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert not any(key.startswith("sections/AL-020_sloads") for key in manifest["products"])
    reason = manifest["skipped"].get("sections/AL-020_sloads#distributions", "")
    assert "does not identify" in reason
