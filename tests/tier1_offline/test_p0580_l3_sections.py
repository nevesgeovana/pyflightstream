"""PFS-2232 (FR-3786): sections and Cp rows keyed by FAMILY and FAMILY_ID."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post import _manifest_schema as ms
from pyflightstream.post._run_block import run_block_columns
from pyflightstream.post._section_tables import (
    CP_COLUMNS,
    SECTIONS_SPLITS,
    family_cell,
    family_file_name,
    sections_split,
    write_cp_table,
)
from pyflightstream.post.products import SECTION_COLUMNS, read_csv_table, write_sections_table
from pyflightstream.results.exports import SURFACE_SECTION_COLUMNS
from tests.tier1_offline.test_goal028_sections_identity import LAYOUT, ROTORS
from tests.tier1_offline.test_post_products import SLOADS

CP_EXPORT = Path(__file__).parent / "fixtures" / "all_surface_sections_26.123.txt"
INVENTORY = ["Body", "Wing", "Blade1"]
BLOCK = run_block_columns((), ())


def test_p0580_the_sections_table_names_family_and_ids(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv",
        SLOADS,
        mach=0.2,
        layout=LAYOUT,
        rotors=ROTORS,
        inventory=INVENTORY,
        rotor_ids={"PUSHER": 3},
    )
    columns, rows = read_csv_table(written)
    # Design 4.5 (I1): the rotor's alias is no column of the sections table; ROTOR_ID is.
    assert columns[:7] == ("POL", "FAMILY", "FAMILY_ID", "STEP", "PLANE", "ROTOR_ID", "AZIMUTH")
    assert "ROTOR" not in columns
    assert columns == SECTION_COLUMNS
    assert [(r["FAMILY"], r["FAMILY_ID"], r["ROTOR_ID"]) for r in rows] == [
        ("Wing", "2", "NA"),
        ("Blade1", "3", "3"),
    ]


def test_p0580_a_family_the_inventory_does_not_name_has_no_id(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS
    )
    _, rows = read_csv_table(written)
    assert {r["FAMILY_ID"] for r in rows} == {"NA"}
    assert family_cell("A+B", ["A", "B"]) == "1;2"
    assert family_cell("Z", ["A"]) is None and family_cell("A", None) is None


def test_p0580_the_split_key_accepts_three_words_and_refuses_the_rest():
    assert SECTIONS_SPLITS == ("point", "family", "both")
    assert sections_split(None) == "point"
    for word in SECTIONS_SPLITS:
        assert sections_split(word) == word
    with pytest.raises(ProductError, match="point, family, both") as refused:
        sections_split("polar")
    assert "never one per polar" in str(refused.value)


@pytest.mark.parametrize("split", ["point", "family", "both"])
def test_p0580_sections_split_writes_the_files_asked(tmp_path, split):
    extra: list[Path] = []
    point = write_sections_table(
        tmp_path / "sections" / "AL_sections.csv",
        SLOADS,
        mach=0.2,
        layout=LAYOUT,
        rotors=ROTORS,
        inventory=INVENTORY,
        split=split,
        family_files=extra,
    )
    assert point is not None
    names = sorted(p.name for p in extra)
    if split == "point":
        assert names == []
    else:
        assert names == ["AL_FAM-Blade1_sections.csv", "AL_FAM-Wing_sections.csv"]
        _, rows = read_csv_table(tmp_path / "sections" / "AL_FAM-Wing_sections.csv")
        assert {r["FAMILY"] for r in rows} == {"Wing"} and len(rows) == 1


def test_p0580_the_family_file_name_is_made_safe():
    assert family_file_name("AL+000", "Blade 1", "cp") == "AL+000_FAM-Blade_1_cp.csv"


def test_p0580_the_cp_table_keys_every_cut_point_by_family_and_section(tmp_path):
    layout = [{"families": ["Wing"], "plane": "XZ", "count": 1, "frame": "MRP"}]
    done = write_cp_table(
        tmp_path / "sections" / "AL_cp.csv",
        CP_EXPORT.read_text(encoding="utf-8"),
        layout=layout,
        inventory=INVENTORY,
        step=65,
        pol="7001",
    )
    assert done is not None
    columns, rows = read_csv_table(done)
    assert columns == CP_COLUMNS
    assert columns[1:9] == (
        "FAMILY",
        "FAMILY_ID",
        "STEP",
        "PLANE",
        "ROTOR_ID",
        "AZIMUTH",
        "SECTION",
        "ALPHA",
    )
    assert columns[-len(SURFACE_SECTION_COLUMNS) :] == SURFACE_SECTION_COLUMNS
    assert len(rows) == 12
    assert {(r["FAMILY"], r["FAMILY_ID"], r["PLANE"], r["SECTION"], r["STEP"]) for r in rows} == {
        ("Wing", "2", "XZ", "1", "65")
    }
    # The first cut point's Cp, read off the fixture line by hand: the ninth printed value.
    line = next(
        text
        for text in CP_EXPORT.read_text(encoding="utf-8").splitlines()
        if text.lstrip().startswith("0.9665064E+00")
    )
    expected = float(line.split(",")[8])
    assert float(rows[0]["Cp"]) == pytest.approx(expected, abs=1e-5)


def test_p0580_the_cp_table_splits_by_family(tmp_path):
    layout = [{"families": ["Wing"], "plane": "XZ", "count": 1, "frame": "MRP"}]
    extra: list[Path] = []
    first = write_cp_table(
        tmp_path / "sections" / "AL_cp.csv",
        CP_EXPORT.read_text(encoding="utf-8"),
        layout=layout,
        inventory=INVENTORY,
        split="family",
        family_files=extra,
    )
    assert [p.name for p in extra] == ["AL_FAM-Wing_cp.csv"]
    assert first == extra[0] and not (tmp_path / "sections" / "AL_cp.csv").exists()


def test_p0580_the_manifest_states_the_columns_the_tables_write(tmp_path):
    doc = ms.manifest_sections(rotors=[{"id": 0, "alias": "P", "pitch_deg": 0.0, "toe_deg": 0.0}])
    sections = [c["name"] for c in doc["kinds"]["sections"]["columns"]]
    # The identity of the sections table, without the rotor's alias (design 4.5).
    assert sections[:6] == list(SECTION_COLUMNS[1:7])
    assert "ROTOR" not in sections
    cp = [c["name"] for c in doc["kinds"]["cp"]["columns"]]
    assert cp == [name for name in CP_COLUMNS[1:] if name not in run_block_columns((), ())]
    assert [s.name for s in ms.cp_export_specs()] == list(SURFACE_SECTION_COLUMNS)
    assert all(s.unit for s in ms.cp_export_specs())


def test_p0580_the_stage_writes_sections_and_cp_at_the_asked_granularity(tmp_path):
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_goal028_explained_products import _give
    from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    (outputs / "AL-020_cp.txt").write_text(CP_EXPORT.read_text(encoding="utf-8"), encoding="utf-8")
    layout = [{"families": ["Wing"], "plane": "XZ", "count": 1, "frame": "MRP"}]
    _give(
        workspace,
        outputs=[
            "outputs/AL-020.txt",
            "outputs/AL-020_plots.txt",
            "outputs/AL-020_sloads.txt",
            "outputs/AL-020_cp.txt",
        ],
        sections_layout=layout,
        inventory=INVENTORY,
    )
    write_campaign_products(workspace)
    products = workspace.root / "post" / "products" / "sections"
    assert (products / "AL-020_sections.csv").is_file() and (products / "AL-020_cp.csv").is_file()
    columns, rows = read_csv_table(products / "AL-020_cp.csv")
    assert columns[: len(BLOCK)] == BLOCK
    assert {r["FAMILY_ID"] for r in rows} == {"2"}
    manifest = _products_manifest(workspace)
    assert "sections/AL-020_cp.csv" in manifest["products"]


def _fake_context(tmp_path, split_files):
    from types import SimpleNamespace

    written = []
    names = {}
    out = tmp_path / "post"
    return SimpleNamespace(
        out=out,
        written=written,
        written_names=names,
        sources={"AL-020": ["camp/sim_7001/AL-020"]},
        record_of={"AL-020": SimpleNamespace(outputs=[], package_version="0.58.0")},
        add=lambda path, entry: (written.append(path), names.update({path.name: entry})),
    )


@pytest.mark.parametrize("split", ["family", "both"])
def test_p0580_the_family_split_indexes_the_family_files_and_drops_the_point_table_when_alone(
    tmp_path, split
):
    from types import SimpleNamespace

    from pyflightstream.post._point_stage import finish_sections

    folder = tmp_path / "post" / "sections"
    folder.mkdir(parents=True)
    done = folder / "AL-020_sections.csv"
    done.write_text("POL", encoding="utf-8")
    family = folder / "AL-020_FAM-Wing_sections.csv"
    family.write_text("POL", encoding="utf-8")
    ctx = _fake_context(tmp_path, [family])
    ctx.written.append(done)
    ctx.written_names["sections/AL-020_sections.csv"] = {"kind": "instant"}
    point = SimpleNamespace(name="AL-020")
    finish_sections(ctx, point, done, [family], split)
    assert family in ctx.written and ctx.written_names[family.name]["split"] == "family"
    assert done.exists() == (split == "both")
    assert (done in ctx.written) == (split == "both")
    assert ("sections/AL-020_sections.csv" in ctx.written_names) == (split == "both")


def test_p0580_the_stage_reads_the_split_key_off_the_pproc_where_it_is_declared(tmp_path):
    from pyflightstream.cases.pproc import SectionsSpec

    if "split" not in SectionsSpec.model_fields:
        pytest.skip("[sections] split is declared by the pproc model of the polar lane (L2)")
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_goal028_explained_products import _give
    from tests.tier1_offline.test_post_products import _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    toml = "\n".join(["[groups]", '"1" = "all"', "[sections]", 'split = "family"', ""])
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(toml, encoding="utf-8")
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    (outputs / "AL-020_cp.txt").write_text(CP_EXPORT.read_text(encoding="utf-8"), encoding="utf-8")
    _give(
        workspace,
        outputs=[
            "outputs/AL-020.txt",
            "outputs/AL-020_plots.txt",
            "outputs/AL-020_sloads.txt",
            "outputs/AL-020_cp.txt",
        ],
        sections_layout=LAYOUT[:1],
        inventory=INVENTORY,
    )
    write_campaign_products(workspace)
    folder = workspace.root / "post" / "products" / "sections"
    names = {p.name for p in folder.glob("AL-020_*")}
    assert "AL-020_FAM-Wing_cp.csv" in names and "AL-020_cp.csv" not in names
