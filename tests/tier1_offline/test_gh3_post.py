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
    # The finding is a CURRENT pproc that differs from the record's own: the
    # recorded one produced the cuts and is trusted over them.
    recorded = workspace.resolve_pproc("p001")
    spec = recorded.model_copy(deep=True)
    specs = {"p001": recorded, "p002": spec}
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    record.matrix_stem = "products"
    _matrix(workspace)
    matrix = workspace.root / "products.fs"
    matrix.write_text(matrix.read_text().replace("p001", "p002"))
    entry = spec.sections.distributions[0]
    if selection == "rotor":
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
@pytest.mark.parametrize("selection", ["Blade", "blade_alias", "Blade1"])
def test_ad_a_stem_owns_its_legacy_cuts_and_integrates_nothing(
    tmp_path, monkeypatch, legacy, selection
):
    """`families = "Blade"` (an alias of it, or `Blade1` over Blade11 and Blade12).

    Ownership of a legacy layout resolves the recorded selector over the cuts,
    so the raw split is present under its name; integration is never trusted
    to a stem, because the post cannot tell the recorded specification from an
    edited one (both resolve to the same artifact id) and the geometry may
    carry a boundary the stem names or a third blade. Raw columns, named.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.aliases = {"blade_alias": ["Blade"]}
    blades = ["Blade11", "Blade12"] if selection == "Blade1" else ["Blade1", "Blade2"]
    record.sections_layout[0].update(families=blades, distribution_families=selection, frame="MRP")
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
    assert not set(EXTRA) & set(columns), "a stem's membership integrated by a guess"
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"+".join(blades)}
    assert "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ad_an_entry_that_emitted_nothing_claims_no_other_entrys_cuts(tmp_path, monkeypatch):
    """Entry 1 asks integration over an idle rotor's `Blade1` and emitted nothing.

    Entry 2 selects rotor ACTIVE (Blade11, Blade12), integrate off, and owns
    the one recorded block. Trusting every recorded selector expanded entry 1
    over the cuts by stem and applied its integration to entry 2's block; a
    selector is knowable only by exact names, aliases and rotors, so entry 1
    matches nothing and entry 2's block keeps its raw columns. (On a layout
    with no identity the rotor name resolves to nothing without a definition
    and the split is refused by name, on this matcher and on every earlier
    one: a false miss registered for 0.27.0, not a number.)
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    # ACTIVE is a ROTOR name the live reference would define; none reaches
    # this match, so nothing resolves it, and nothing may resolve Blade1 either.
    record.sections_layout[0].update(
        families=["Blade11", "Blade12"],
        distribution=2,
        distribution_families="ACTIVE",
        frame="ACTIVE_RMRP",
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "Blade1", "frame": "RMRP", "integrate": True}),
        entry.model_copy(update={"families": "ACTIVE", "frame": "RMRP", "integrate": False}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    key = "sections/AL-020_sloads_ACTIVE.csv"
    assert key in manifest["products"], manifest["skipped"]
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "entry 1's integration applied to entry 2's block"
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"Blade11+Blade12"}


@pytest.mark.parametrize("selection", ["Blade", "Blade1"])
def test_ad_a_different_pproc_cannot_know_what_a_stem_selects(tmp_path, monkeypatch, selection):
    """A current pproc citing a stem over a recorded two-blade block integrates nothing.

    The geometry may carry a third blade or a boundary named by the stem
    itself; the cuts cannot say, so membership is uncertain and the raw
    columns are kept, named missing.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    blades = ["Blade11", "Blade12"] if selection == "Blade1" else ["Blade1", "Blade2"]
    record.sections_layout[0].update(families=blades, distribution_families=blades, frame="MRP")
    recorded = workspace.resolve_pproc("p001")
    entry = recorded.sections.distributions[0]
    recorded.sections.distributions = [
        entry.model_copy(update={"families": blades, "frame": "MRP", "integrate": False})
    ]
    current = recorded.model_copy(deep=True)
    current.sections.distributions = [
        entry.model_copy(update={"families": selection, "frame": "MRP", "integrate": True})
    ]
    specs = {"p001": recorded, "p002": current}
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    record.matrix_stem = "products"
    _matrix(workspace)
    matrix = workspace.root / "products.fs"
    matrix.write_text(matrix.read_text().replace("p001", "p002"))
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = f"sections/AL-020_sloads_{'-'.join(blades)}.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a stem's membership owned by a guess"
    assert len(rows) == 4 and "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ad_a_widened_live_alias_is_not_the_recorded_block(tmp_path, monkeypatch):
    """The pproc is unchanged; the live reference widened AERO from [Wing] to [Wing, Tail].

    Equal pproc text does not establish an unchanged selector meaning. The
    current entry over AERO now names Tail, which the layout has no block
    for, so the Wing-only block is not its emission and keeps its raw columns.
    """
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    record.aliases = {"AERO": ["Wing"]}
    recorded.sections.distributions[0].families = "AERO"
    recorded.sections.distributions[0].integrate = True
    record.sections_layout[0]["distribution_families"] = "AERO"
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        'area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n[aliases]\nAERO = ["Wing", "Tail"]\n'
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_AERO.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a widened alias integrated the old block"
    assert {row["FAMILY"] for row in rows} == {"Wing"}
    assert "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ab_a_deleted_live_alias_does_not_resurrect_its_recorded_group(tmp_path, monkeypatch):
    """The record aliases AERO = [Wing]; the current reference has no aliases at all.

    An empty live table is the live table. The polar group AERO selects no
    surface under it, so no row is published from the recorded membership and
    the table is named as selecting nothing.
    """
    workspace, healthy, spec = _one_distribution(tmp_path, monkeypatch)
    healthy.aliases = {"AERO": ["Wing"]}
    spec.products.polars = True
    spec.groups = {"AERO": ["AERO"]}
    healthy.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text("area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n")
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    key = "polars/P7001-AL-020_AERO.csv"
    assert key not in manifest["products"], "a deleted alias published its recorded group"
    reason = manifest["skipped"].get(key, "")
    assert "AERO" in reason and "selects no surface" in reason, manifest["skipped"]
    assert reason in (workspace.products_dir("products") / "post.log").read_text()


@pytest.mark.parametrize("member", ["each", "each_blade", "all"])
def test_ad_a_selector_word_inside_an_alias_is_a_boundary_name(tmp_path, monkeypatch, member):
    """The live alias AERO widened from [Wing] to [Wing, <selector word>].

    The builder reads a selector word that is a member of an alias as a
    boundary NAME; the matcher read it as the selector and matched the
    recorded Wing-only block. It is an unrecorded name, so the block is not
    the entry's emission and keeps its raw columns, named missing.
    """
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    record.aliases = {"AERO": ["Wing"]}
    recorded.sections.distributions[0].families = "AERO"
    recorded.sections.distributions[0].integrate = True
    record.sections_layout[0]["distribution_families"] = "AERO"
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        f'area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n[aliases]\nAERO = ["Wing", "{member}"]\n'
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_AERO.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a selector word in an alias matched the old block"
    assert {row["FAMILY"] for row in rows} == {"Wing"}
    assert "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ad_a_case_folded_name_is_not_the_builders_exact_name(tmp_path, monkeypatch):
    """The recorded block holds Blade1; the current entry asks `blade1`.

    The builder's boundary lookup is case-sensitive, and the geometry may hold
    a Blade2 the cuts do not show, so `blade1` is not exact evidence of the
    recorded block: raw columns, named missing.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    recorded = workspace.resolve_pproc("p001")
    current = recorded.model_copy(deep=True)
    current.sections.distributions[0].families = "blade1"
    current.sections.distributions[0].frame = "MRP"
    record.sections_layout[0]["frame"] = "MRP"
    specs = {"p001": recorded, "p002": current}
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: specs[key])
    record.matrix_stem = "products"
    _matrix(workspace)
    matrix = workspace.root / "products.fs"
    matrix.write_text(matrix.read_text().replace("p001", "p002"))
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_Blade1.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a case-folded name integrated the block"
    assert len(rows) == 4 and "missing" in manifest["skipped"].get(f"{key}#integration", "")


@pytest.mark.parametrize("collision", ["rotor", "case"])
def test_ad_the_matchers_vocabulary_is_the_builders(tmp_path, monkeypatch, collision):
    """OUTER = [AERO], AERO = [Wing, Tail], and a colliding definition of AERO.

    A rotor named AERO owning Wing only, or an alias `aero` = [Wing]: the
    builder reads the reference's alias table first and the exact spelling
    first, so OUTER selects Wing and Tail. The matcher's vocabulary let the
    rotor, or the case-folded twin, overwrite AERO, dropped Tail before the
    equality test and integrated the Wing-only block.
    """
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    recorded.sections.distributions[0].families = "OUTER"
    recorded.sections.distributions[0].integrate = True
    record.sections_layout[0]["distribution_families"] = "OUTER"
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    head = "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
    aliases = '[aliases]\nOUTER = ["AERO"]\nAERO = ["Wing", "Tail"]\n'
    if collision == "rotor":
        tail = (
            '[rotors.AERO]\nalias = "AERO"\naxis = "Z"\ndiameter_m = 2.0\n'
            'families_blades = ["Wing"]\n'
        )
    else:
        tail = 'aero = ["Wing"]\n'
    reference.write_text(head + aliases + tail)
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_OUTER.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a vocabulary collision integrated the Wing-only block"
    assert {row["FAMILY"] for row in rows} == {"Wing"}
    assert "missing" in manifest["skipped"].get(f"{key}#integration", "")


@pytest.mark.parametrize("order", ["exact_first", "folded_first"])
def test_ad_two_aliases_that_differ_in_case_only_are_two_aliases(tmp_path, monkeypatch, order):
    """AERO = [Blade1, Blade2] beside aero = [Blade1], in either insertion order.

    The builder resolves the exact spelling first, so `AERO` selects both
    blades and the recorded Blade1-only block is not its emission; a
    case-folded vocabulary let whichever came last win and integrated it.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0]["frame"] = "MRP"
    recorded = workspace.resolve_pproc("p001")
    recorded.sections.distributions[0].families = "AERO"
    recorded.sections.distributions[0].frame = "MRP"
    recorded.sections.distributions[0].integrate = True
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    lines = ['AERO = ["Blade1", "Blade2"]', 'aero = ["Blade1"]']
    if order == "folded_first":
        lines.reverse()
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n[aliases]\n" + "\n".join(lines) + "\n"
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_Blade1.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a case twin of the alias integrated the block"
    assert len(rows) == 4 and "missing" in manifest["skipped"].get(f"{key}#integration", "")
