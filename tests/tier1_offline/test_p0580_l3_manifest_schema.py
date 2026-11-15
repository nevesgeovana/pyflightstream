"""PFS-2232 (FR-3779): the products.json schema states every column of every kind."""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post import _family_columns as fc
from pyflightstream.post import _manifest_schema as ms
from pyflightstream.post._run_block import run_block_columns

ROTORS = [
    {"id": 0, "alias": "PUSHER", "pitch_deg": 0.0, "toe_deg": 0.0},
    {"id": 1, "alias": "LIFT", "pitch_deg": 90.0, "toe_deg": 0.0},
]


def _document(**kwargs):
    return ms.manifest_sections(rotors=ROTORS, identifiers=("FLAP",), **kwargs)


def test_p0580_schema_version_and_top_level_keys():
    doc = _document()
    assert doc["schema_version"] == 2
    assert set(doc) == {
        "schema_version",
        "tree",
        "kinds",
        "run_block",
        "frames",
        "families",
        "groups",
        "polars",
        "migrated",
    }


def test_p0580_tree_names_every_folder_and_its_kinds():
    tree = ms.tree_section()
    assert {"polars", "time_history", "reductions", "probes", "sections"} <= set(tree)
    assert tree["time_history"]["kinds"] == ["plots"]
    assert tree["polars"]["kinds"] == ["FAM-DIM", "FAM-ACOEF", "FAM-RCOEF", "DIM", "ACOEF", "RCOEF"]
    assert tree["reductions"]["kinds"] == [
        "phase_locked",
        "per_revolution",
        "harmonics",
        "disc_map",
    ]
    assert "plots" not in tree["probes"]["kinds"]


def test_p0580_kinds_columns_equal_the_registry_expanded():
    doc = _document()
    names = lambda kind: [c["name"] for c in doc["kinds"][kind]["columns"]]  # noqa: E731
    assert names("FAM-ACOEF") == list(fc.column_names(fc.acoef_columns((0, 1))))
    assert names("FAM-RCOEF") == list(fc.column_names(fc.rcoef_columns((0, 1))))
    assert names("FAM-DIM")[2:5] == ["FX_MRP", "FY_MRP", "FZ_MRP"]
    assert "CDR1" in names("ACOEF") and "CTR1" in names("RCOEF")


@pytest.mark.requirement("FR-3779")
def test_p0580_every_column_states_unit_frame_definition():
    doc = _document()
    for kind, entry in doc["kinds"].items():
        for column in entry["columns"]:
            assert column["unit"], (kind, column["name"])
            assert "frame" in column and column["definition"], (kind, column["name"])
    cd = next(c for c in doc["kinds"]["FAM-ACOEF"]["columns"] if c["name"] == "CDW")
    assert (cd["frame"], cd["sign"], cd["unit"]) == ("W", "positive aft", "-")


def test_p0580_no_rcoef_kind_without_a_rotor():
    doc = ms.manifest_sections()
    assert "FAM-RCOEF" not in doc["kinds"] and "RCOEF" not in doc["kinds"]
    assert "FAM-ACOEF" in doc["kinds"]


@pytest.mark.requirement("FR-3779")
def test_p0580_run_block_section_matches_the_header_and_units():
    doc = _document()
    names = [c["name"] for c in doc["run_block"]]
    assert names == list(run_block_columns(("FLAP",), (0, 1)))
    by_name = {c["name"]: c for c in doc["run_block"]}
    assert by_name["VINF"]["unit"] == "m/s"
    assert by_name["RPM1"]["unit"] == "rev/min"
    assert by_name["FLAP"]["unit"] == "as written"
    assert by_name["VINF"]["definition"].startswith("docs/definitions/the-run-block.md#")


def test_p0580_expected_header_is_run_block_then_kind_columns():
    doc = _document()
    header = ms.expected_header(doc, "FAM-DIM")
    run = [c["name"] for c in doc["run_block"]]
    assert header[: len(run)] == run
    assert header[len(run) :][:2] == ["FAMILY", "FAMILY_ID"]
    with pytest.raises(ProductError, match="no kind"):
        ms.expected_header(doc, "nothing")


def test_p0580_frames_state_the_rotor_angles_and_mesh():
    frames = _document(mesh_converted=True)["frames"]
    assert frames["B"]["dcm"] == "C2(pi)"
    assert frames["R1"] == {
        "rotor": "LIFT",
        "from": "B",
        "dcm": "C2(theta) C3(psi)",
        "pitch_deg": 90.0,
        "toe_deg": 0.0,
    }
    assert frames["mesh"] == {"declared": ["aft", "right", "up"], "converted": True}


def test_p0580_families_and_groups_sorted_and_unique():
    fams = ms.families_section([ms.FamilyEntry(2, "Prop", 0), ms.FamilyEntry(1, "Wing")])
    assert [f["FAMILY_ID"] for f in fams] == [1, 2] and fams[1]["ROTOR_ID"] == 0
    with pytest.raises(ProductError, match="repeated"):
        ms.families_section([ms.FamilyEntry(1, "a"), ms.FamilyEntry(1, "b")])
    groups = ms.groups_section(
        [
            ms.GroupEntry(ms.group_id("rotor", rotor_id=0), "PUSHER", "rotor", (2,)),
            ms.GroupEntry(ms.group_id("TOTAL"), "TOTAL", "default", (1, 2)),
            ms.GroupEntry(
                ms.group_id("declared", position=1), "MIX", "declared", (1, 2), "DIM and ACOEF only"
            ),
        ]
    )
    assert [g["GROUP_ID"] for g in groups] == [0, 10, 101]
    assert groups[2]["note"] == "DIM and ACOEF only"
    with pytest.raises(ProductError, match="repeated"):
        ms.groups_section(
            [ms.GroupEntry(0, "a", "default", ()), ms.GroupEntry(0, "b", "default", ())]
        )


def test_p0580_polars_and_migrated_pass_through():
    doc = ms.manifest_sections(
        polars={"P0001": {"description": "d", "run_type": "steady"}},
        migrated={"probes/a_plots.csv": "time_history/a_plots.csv"},
    )
    assert doc["polars"]["P0001"]["run_type"] == "steady"
    assert doc["migrated"] == {"probes/a_plots.csv": "time_history/a_plots.csv"}
