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


def test_ad_a_rotors_members_are_boundary_names_not_words(tmp_path, monkeypatch):
    """Rotor R declares blades [Blade1, AERO]; the alias AERO = [Blade1].

    Seeding the rotor's members through the alias reader resolved AERO into
    Blade1 and erased the declared boundary, so `families = "R"` matched the
    recorded Blade1-only block where the builder emits Blade1 and AERO.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0]["frame"] = "R_RMRP"
    recorded = workspace.resolve_pproc("p001")
    entry = recorded.sections.distributions[0]
    entry.families = "R"
    entry.frame = "RMRP"
    entry.integrate = True
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nAERO = ["Blade1"]\n'
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Blade1", "AERO"]\n'
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_Blade1.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a rotor member read as an alias erased a boundary"
    assert len(rows) == 4 and "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ad_a_nested_member_the_cuts_do_not_carry_may_be_a_boundary(tmp_path, monkeypatch):
    """OUTER = [AERO], AERO = [Wing]; the geometry may carry a boundary named AERO.

    The builder reads a member as the boundary of that name first, over the
    whole geometry; the cuts hold Wing alone and cannot say whether AERO is a
    boundary, so OUTER's membership is uncertain and the Wing-only block keeps
    its raw columns, named missing.
    """
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    recorded.sections.distributions[0].families = "OUTER"
    recorded.sections.distributions[0].integrate = True
    record.sections_layout[0]["distribution_families"] = "OUTER"
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nOUTER = ["AERO"]\nAERO = ["Wing"]\n'
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_OUTER.csv"
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a nested member owned the block by a guess"
    assert {row["FAMILY"] for row in rows} == {"Wing"}
    assert "missing" in manifest["skipped"].get(f"{key}#integration", "")


def test_ad_a_member_that_names_a_recorded_boundary_is_that_boundary_first(tmp_path, monkeypatch):
    """OUTER = [AERO], AERO = [Tail], Tail = [Tail], and a recorded boundary named AERO.

    The builder's alias reader takes the recorded boundary first, so OUTER
    selects AERO and the recorded AERO block IS its emission: integrated. A
    reader that followed the alias first would refuse a match the builder
    grants.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0].update(families=["AERO"], distribution_families="OUTER", frame="MRP")
    recorded = workspace.resolve_pproc("p001")
    entry = recorded.sections.distributions[0]
    entry.families = "OUTER"
    entry.frame = "MRP"
    entry.integrate = True
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nOUTER = ["AERO"]\nAERO = ["Tail"]\nTail = ["Tail"]\n'
    )
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    key = "sections/AL-020_sloads_OUTER.csv"
    columns, rows = read_csv_table(out / key)
    assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"AERO"}
    assert f"{key}#integration" not in manifest["skipped"]


def test_ad_a_selector_word_inside_a_list_is_a_boundary_name(tmp_path, monkeypatch):
    """`families = ["all"]` over a recorded boundary literally named `all`.

    The builder reads a list's items as names (its `blades` and `airframe`
    excepted), so `["all"]` selects the boundary called all and the recorded
    block is its emission: integrated, not refused as a whole-geometry
    selector.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0].update(families=["all"], distribution_families=["all"], frame="MRP")
    recorded = workspace.resolve_pproc("p001")
    entry = recorded.sections.distributions[0]
    entry.families = ["all"]
    entry.frame = "MRP"
    entry.integrate = True
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    key = "sections/AL-020_sloads_all.csv"
    columns, rows = read_csv_table(out / key)
    assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"all"}


@pytest.mark.parametrize("flags", [(True, False), (False, True)])
def test_ad_an_uncertain_entry_is_a_possible_owner_not_a_dropped_one(tmp_path, monkeypatch, flags):
    """Two entries, Wing and OUTER (OUTER = [AERO], AERO = [Wing]), two recorded Wing blocks.

    The builder emits a Wing block for each; ownership of either block is
    ambiguous. Dropping OUTER as uncertain left Wing the only candidate for
    both blocks and handed its integration flag to OUTER's file (and, with
    the flags reversed, withheld Wing's). Both blocks are refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {"OUTER": ["AERO"], "AERO": ["Wing"]}
    for k, (block, name) in enumerate(
        zip(record.sections_layout, ("Wing", "OUTER"), strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=["Wing"], frame="MRP")
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": flags[0]}),
        entry.model_copy(update={"families": "OUTER", "frame": "MRP", "integrate": flags[1]}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in ("Wing", "OUTER"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


@pytest.mark.parametrize("flags", [(False, True), (True, False)])
def test_ad_a_possible_owner_in_a_literally_cited_frame_is_still_possible(
    tmp_path, monkeypatch, flags
):
    """EXPAND = [Blade1] on RMRP and DIRECT = [Blade1] on the literal R_RMRP, two recorded blocks.

    The builder emits an identical R_RMRP block for each entry. The strict
    reading refuses the expanding entry because the block's frame is cited
    literally, and the possible reading repeated that refusal, so DIRECT was
    the only candidate for both blocks and its flag was applied to both. Both
    blocks are ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {"EXPAND": ["Blade1"], "DIRECT": ["Blade1"]}
    for k, (block, name) in enumerate(
        zip(record.sections_layout, ("EXPAND", "DIRECT"), strict=True), 1
    ):
        block.update(
            distribution=k, distribution_families=name, families=["Blade1"], frame="R_RMRP"
        )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "EXPAND", "frame": "RMRP", "integrate": flags[0]}),
        entry.model_copy(update={"families": "DIRECT", "frame": "R_RMRP", "integrate": flags[1]}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in ("EXPAND", "DIRECT"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_possible_reading_that_raises_costs_no_raw_row(tmp_path, monkeypatch):
    """A Wing entry that integrates beside `families = ["blades"]`, which the resolver refuses.

    The artifact accepts both entries; the retired selector raises when the
    common resolver reads it, yet the expanding builder has emitted for a
    bare selector word beside a family of that name, so the entry is
    uncertain: the post completes, the raw split has its rows, and the Wing
    entry's integration is withheld as ambiguous, by name.
    """
    workspace, record, recorded = _one_distribution(tmp_path, monkeypatch)
    entry = recorded.sections.distributions[0]
    recorded.sections.distributions = [
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": True}),
        entry.model_copy(update={"families": ["blades"], "frame": "MRP", "integrate": False}),
    ]
    record.sections_layout[0].update(families=["Wing"], distribution_families="Wing", frame="MRP")
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    key = "sections/AL-020_sloads_Wing.csv"
    assert key in manifest["products"], manifest["skipped"]
    columns, rows = read_csv_table(out / key)
    assert not set(EXTRA) & set(columns), "a retired selector word beside Wing owned nothing"
    assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {"Wing"}
    assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


@pytest.mark.parametrize("word", ["all", "ALL"])
@pytest.mark.parametrize("flags", [(False, True), (True, False)])
def test_ad_an_entry_the_possible_reading_cannot_read_is_a_possible_owner(
    tmp_path, monkeypatch, flags, word
):
    """Rotor R declares Blade1 and Blade2; `["all"]` on RMRP beside `Blade1` on the literal R_RMRP.

    The builder emits an identical R_RMRP block for each entry. The strict
    reading refuses `["all"]` (Blade2 is declared and unrecorded), and a
    possible reading that resolved the list with the common resolver read it
    as nothing and dropped it, so the literal entry was the only candidate
    for both blocks and its flag went to both. A selection the possible
    reading cannot read owns any block of its frame, plane and count: both
    blocks are ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, (block, name) in enumerate(
        zip(record.sections_layout, ("all", "Blade1"), strict=True), 1
    ):
        block.update(
            distribution=k, distribution_families=name, families=["Blade1"], frame="R_RMRP"
        )
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Blade1", "Blade2"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": [word], "frame": "RMRP", "integrate": flags[0]}),
        entry.model_copy(update={"families": "Blade1", "frame": "R_RMRP", "integrate": flags[1]}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("all", "Blade1"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_ownership_of_a_legacy_layout_takes_no_possible_reading(tmp_path, monkeypatch):
    """A legacy layout with a Wing block and a Wing+Tail block, entries Wing and [Wing, Tail].

    Ownership reads the recorded pproc over its own cuts and is exact; a
    possible reading made the combined entry a possible owner of the Wing
    block beside it, the split was refused as ambiguous and both files were
    lost. Both files exist, two rows each.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for block, families in zip(record.sections_layout, (["Wing"], ["Wing", "Tail"]), strict=True):
        block.update(families=families, frame="MRP")
        del block["distribution"]
        del block["distribution_families"]
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": ["Wing", "Tail"], "frame": "MRP", "integrate": False}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name, families in (("Wing", {"Wing"}), ("Wing-Tail", {"Wing+Tail"})):
        key = f"sections/AL-020_sloads_{name}.csv"
        assert key in manifest["products"], manifest["skipped"]
        _, rows = read_csv_table(out / key)
        assert len(rows) == 2 and {row["FAMILY"] for row in rows} == families


@pytest.mark.parametrize("word", ["blades", "airframe"])
def test_ad_an_alias_named_like_a_retired_selector_is_an_alias(tmp_path, monkeypatch, word):
    """The reference declares `blades = [Wing, Missing]`; two entries, `blades` and `Wing`.

    The builder resolves a declared alias before the retirement rule, and
    emits a Wing block for each entry. The strict reading refuses the alias
    entry (Missing is unrecorded); a possible reading that refused the word by
    its spelling dropped it, and the Wing entry's flag went to both blocks.
    The alias entry is uncertain and a possible owner: both blocks ambiguous.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {word: ["Wing", "Missing"]}
    for k, (block, name) in enumerate(zip(record.sections_layout, (word, "Wing"), strict=True), 1):
        block.update(distribution=k, distribution_families=name, families=["Wing"], frame="MRP")
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": word, "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": True}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in (word, "Wing"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_rotor_name_overridden_by_an_alias_is_still_a_possible_owner(tmp_path, monkeypatch):
    """Rotor R declares Hub and Blade1; the alias R = [Hub] overrides its name; cuts hold Blade1.

    Entry 1 selects R on RMRP, entry 2 Blade1 on the literal R_RMRP; the
    builder emits a Blade1 block for each. The strict reading refuses entry 1
    (Hub is declared and unrecorded); a possible reading that read R through
    the alias saw Hub alone and dropped it, and entry 2's flag went to both.
    Entry 1 is uncertain and a possible owner: both blocks ambiguous.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, (block, name) in enumerate(zip(record.sections_layout, ("R", "Blade1"), strict=True), 1):
        block.update(
            distribution=k, distribution_families=name, families=["Blade1"], frame="R_RMRP"
        )
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nR = ["Hub"]\n'
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_general = ["Hub"]\nfamilies_blades = ["Blade1"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "R", "frame": "RMRP", "integrate": False}),
        entry.model_copy(update={"families": "Blade1", "frame": "R_RMRP", "integrate": True}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("R", "Blade1"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_bare_selector_word_is_uncertain_not_refused(tmp_path, monkeypatch):
    """`airframe` bare on RMRP beside `airframe1` on the literal R_RMRP, two recorded blocks.

    The common resolver raises on the bare word; the expanding builder has
    emitted for it beside a rotor family named airframe1. The matcher cannot
    tell which path the entry takes, so it is uncertain and a possible owner;
    a reader that refused the word outright left the literal entry alone with
    both blocks and its flag. Both blocks are ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, (block, name) in enumerate(
        zip(record.sections_layout, ("airframe", "airframe1"), strict=True), 1
    ):
        block.update(
            distribution=k, distribution_families=name, families=["airframe1"], frame="R_RMRP"
        )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "airframe", "frame": "RMRP", "integrate": False}),
        entry.model_copy(update={"families": "airframe1", "frame": "R_RMRP", "integrate": True}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in ("airframe", "airframe1"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


@pytest.mark.parametrize("alias", [["R"], ["Wing"]])
def test_ad_a_rotor_name_keeps_its_expanding_meaning_under_any_alias(tmp_path, monkeypatch, alias):
    """Rotor R declares Blade1 (and Blade2); the alias R = [R] or R = [Wing]; cuts hold Blade1.

    On RMRP the builder reads the top-level rotor name as the whole rotor and
    emits a Blade1 block for `families = "R"`, beside the literal entry over
    Blade1 that emits the same block. A self-referencing alias returned
    unmarked and a rotor name shadowed by an alias of a recorded cut read as
    certain, so entry 1 was dropped and entry 2's flag went to both blocks.
    The builder's own reading over the maximal inventory keeps entry 1 a
    possible owner: both blocks ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    frames = ("R_RMRP", "R_RMRP", "MRP")
    names = ("R", "Blade1", "Wing")
    families = (["Blade1"], ["Blade1"], ["Wing"])
    for k, (block, frame, name, held) in enumerate(
        zip(record.sections_layout, frames, names, families, strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=held, frame=frame)
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    members = ", ".join(f'"{m}"' for m in alias)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        f"[aliases]\nR = [{members}]\n"
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Blade1", "Blade2"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "R", "frame": "RMRP", "integrate": False}),
        entry.model_copy(update={"families": "Blade1", "frame": "R_RMRP", "integrate": True}),
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": False}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("R", "Blade1"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_common_frame_alias_is_a_possible_owner_whatever_the_order(tmp_path, monkeypatch):
    """A = [A], B = [A]; the geometry carries A1; entries A (off), A1 (on), B on another frame.

    The builder emits A1 for `A` over the geometry; a later entry citing the
    name A turns the member's stem reading into an exact one, so the
    subset argument over the maximal inventory fails on a common frame. The
    alias entry is a possible owner on frame, plane and count whatever the
    entry order: both A1 blocks ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {"A": ["A"], "B": ["A"]}
    for k, (block, name) in enumerate(zip(record.sections_layout, ("A", "A1"), strict=True), 1):
        block.update(distribution=k, distribution_families=name, families=["A1"], frame="MRP")
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "A", "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": "A1", "frame": "MRP", "integrate": True}),
        entry.model_copy(update={"families": "B", "frame": "Other", "integrate": False}),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in ("A", "A1"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_literal_frame_owns_its_original_twin_too(tmp_path, monkeypatch):
    """Two Wing blocks in R_SMRP_ORIGINAL, entries A = [Wing, Tail] on R_SMRP and Wing on the twin.

    The builder emits the ORIGINAL twin for a literal frame that has one, so
    the alias entry could own the twin's block; the possible reading's frame
    gate rejected it before asking, and the Wing entry's flag went to both.
    Both blocks ambiguous and refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {"A": ["Wing", "Tail"]}
    for k, (block, name) in enumerate(zip(record.sections_layout, ("A", "Wing"), strict=True), 1):
        block.update(
            distribution=k, distribution_families=name, families=["Wing"], frame="R_SMRP_ORIGINAL"
        )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "A", "frame": "R_SMRP", "integrate": False}),
        entry.model_copy(
            update={"families": "Wing", "frame": "R_SMRP_ORIGINAL", "integrate": True}
        ),
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for name in ("A", "Wing"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_two_recorded_blades_without_a_rotor_definition_integrate_uniquely(
    tmp_path, monkeypatch
):
    """Blade1 and Blade2 entries on LOCAL_AXIS, both recorded with identity, no rotor definition.

    The builder emits nothing over the cuts without a rotor, and reading
    every expanding entry as possible made Blade2 a possible owner of every
    Blade1 block: both files lost their integration as ambiguous. Exact
    recorded names alone are settled by the recorded-frame grouping, so each
    entry owns its own block uniquely and both files integrate.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, block in enumerate(record.sections_layout, 1):
        block.update(distribution=k, distribution_families=f"Blade{k}")
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": f"Blade{k}", "frame": "LOCAL_AXIS", "integrate": True})
        for k in (1, 2)
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for k in (1, 2):
        key = f"sections/AL-020_sloads_Blade{k}.csv"
        columns, rows = read_csv_table(out / key)
        assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
        assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {f"Blade{k}"}
        assert f"{key}#integration" not in manifest["skipped"]


@pytest.mark.parametrize("selection", ["Blade1", "A"])
def test_ad_a_name_whose_stem_another_spelling_shares_is_uncertain_on_a_common_frame(
    tmp_path, monkeypatch, selection
):
    """Cuts hold blade1 and blade2; rotor R declares Blade1, recorded under that spelling.

    Over the geometry the builder reads `Blade1` by its stem (both lowercase
    blades); over the maximal inventory, which carries the rotor's spelling,
    it reads it exactly. The entry citing it (or an alias of it) refused by
    the strict reading was dropped as certain and the neighbour's flag went
    to both common-frame blocks. It is a possible owner: both ambiguous.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    record.aliases = {"A": ["Blade1"]}
    layout = (
        (selection, ["blade1", "blade2"], "MRP"),
        ("blade1-blade2", ["blade1", "blade2"], "MRP"),
        ("R", ["Blade1"], "R_RMRP1"),
    )
    for k, (block, (name, held, frame)) in enumerate(
        zip(record.sections_layout, layout, strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=held, frame=frame)
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nA = ["Blade1"]\n'
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Blade1"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": selection, "frame": "MRP", "integrate": False}),
        entry.model_copy(
            update={"families": ["blade1", "blade2"], "frame": "MRP", "integrate": True}
        ),
        entry.model_copy(update={"families": "R", "frame": "LOCAL_AXIS", "integrate": False}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in (selection, "blade1-blade2"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


@pytest.mark.parametrize("tail_alias", ["", 'Tail = ["Tail"]\n'])
def test_ad_a_member_that_is_a_boundary_and_an_alias_leading_elsewhere_is_uncertain(
    tmp_path, monkeypatch, tail_alias
):
    """A = [Wing], Wing = [Tail]; rotor R declares Wing (recorded so); the cuts hold Tail.

    Over a geometry that carries the boundary `wing` and not `Wing`, the
    builder follows the alias Wing to Tail for `A`; over the maximal
    inventory, which carries the rotor's `Wing`, it stops at the boundary.
    The A entry read as certain, was dropped, and the Tail entry's flag went
    to both common-frame blocks. It is a possible owner: both ambiguous.
    The same with the self-alias `Tail = ["Tail"]` beside it (QA read of f211ec2).
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    layout = (("A", ["Tail"], "MRP"), ("Tail", ["Tail"], "MRP"), ("R", ["Wing"], "R_RMRP1"))
    for k, (block, (name, held, frame)) in enumerate(
        zip(record.sections_layout, layout, strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=held, frame=frame)
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nA = ["Wing"]\nWing = ["Tail"]\n'
        + tail_alias
        + '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["Wing"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "A", "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": "Tail", "frame": "MRP", "integrate": True}),
        entry.model_copy(update={"families": "R", "frame": "LOCAL_AXIS", "integrate": False}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("A", "Tail"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


@pytest.mark.parametrize("frame", ["MRP", "X_RMRP"])
def test_ad_two_recorded_blades_on_a_common_frame_integrate_uniquely(tmp_path, monkeypatch, frame):
    """Blade1 and Blade2 entries on a COMMON frame, both recorded there, both integrating.

    They share a stem, and the stem rule made each a possible owner of the
    other's block, losing both integrations as ambiguous. A name a common
    block attests is the geometry's own spelling and reads the same over the
    geometry and the maximal inventory, so each entry owns its block alone.
    A literal common frame spelt like a rotor's (`X_RMRP`, no rotor X) is a
    common frame too: classifying it by name alone lost both integrations
    again (QA read of f211ec2).
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, block in enumerate(record.sections_layout, 1):
        block.update(distribution=k, distribution_families=f"Blade{k}", frame=frame)
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": f"Blade{k}", "frame": frame, "integrate": True})
        for k in (1, 2)
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    out = workspace.products_dir(None)
    for k in (1, 2):
        key = f"sections/AL-020_sloads_Blade{k}.csv"
        columns, rows = read_csv_table(out / key)
        assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
        assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {f"Blade{k}"}
        assert f"{key}#integration" not in manifest["skipped"]


def test_ad_a_nested_member_recorded_by_a_rotor_block_is_uncertain(tmp_path, monkeypatch):
    """A = [B], B = [Wing]; rotor R declares B (recorded in R_RMRP1); the geometry carries b.

    The matcher's inventory holds the rotor's B, so the builder over it stops
    at that boundary for A; over the geometry it follows B to Wing. The A
    entry is uncertain and a possible owner of the Wing blocks: ambiguous.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    layout = (("A", ["Wing"], "MRP"), ("Wing", ["Wing"], "MRP"), ("R", ["B"], "R_RMRP1"))
    for k, (block, (name, held, frame)) in enumerate(
        zip(record.sections_layout, layout, strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=held, frame=frame)
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nA = ["B"]\nB = ["Wing"]\n'
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["B"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "A", "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": "Wing", "frame": "MRP", "integrate": True}),
        entry.model_copy(update={"families": "R", "frame": "LOCAL_AXIS", "integrate": False}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("A", "Wing"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]


def test_ad_a_nested_self_alias_still_leads_elsewhere(tmp_path, monkeypatch):
    """A = [B], B = [Tail], Tail = [Tail]; rotor R declares B (recorded); the cuts hold Tail.

    The builder reads `Tail = ["Tail"]` as the family, not a ring, so over the
    geometry `A` reaches Tail through B while over the maximal inventory it
    stops at the rotor's B. A reader that walked the alias chain with a seen
    set dropped Tail as visited and read B as leading nowhere else; the A
    entry was read as certain and the Tail entry's flag went to both blocks.
    Both blocks ambiguous, refused by name.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    layout = (("A", ["Tail"], "MRP"), ("Tail", ["Tail"], "MRP"), ("R", ["B"], "R_RMRP1"))
    for k, (block, (name, held, frame)) in enumerate(
        zip(record.sections_layout, layout, strict=True), 1
    ):
        block.update(distribution=k, distribution_families=name, families=held, frame=frame)
    record.matrix_stem = "products"
    _matrix(workspace)
    reference = workspace.inputs_dir / "references/r001.toml"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 20.0\n"
        '[aliases]\nA = ["B"]\nB = ["Tail"]\nTail = ["Tail"]\n'
        '[rotors.R]\nalias = "R"\naxis = "Z"\ndiameter_m = 2.0\n'
        'families_blades = ["B"]\n'
    )
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": "A", "frame": "MRP", "integrate": False}),
        entry.model_copy(update={"families": "Tail", "frame": "MRP", "integrate": True}),
        entry.model_copy(update={"families": "R", "frame": "LOCAL_AXIS", "integrate": False}),
    ]
    write_campaign_products(workspace, matrix_stem="products")
    manifest = _products_manifest(workspace)
    out = workspace.products_dir("products")
    for name in ("A", "Tail"):
        key = f"sections/AL-020_sloads_{name}.csv"
        columns, rows = read_csv_table(out / key)
        assert not set(EXTRA) & set(columns), f"{name} integrated through a falsely unique match"
        assert len(rows) == 2
        assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", ""), manifest["skipped"]
