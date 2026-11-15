"""products.json states the tree it describes, and the polar files share the point's block.

THE REQUIREMENT (design of the post outputs, sections 3 and 6; FR-3778, FR-3779).
``products.json`` of a post carries ``schema_version`` 2 and, beside the files,
``kinds`` (every column of every polar kind, with unit and frame), ``run_block``,
``frames`` (one ``R<id>`` per declared rotor), ``families`` (FAMILY_ID to FAMILY),
``groups`` (GROUP_ID 0 TOTAL, 1 AIRFRAME, 10 + id per rotor, 100 + k per declared
group, each with its member FAMILY_IDs), ``polars`` (POL to description and run
type) and ``migrated``; each product entry names its ``polar``. The run block of
a polar file's row is the point's one run block: ``POINT_ID`` is the point's place
in its sweep.

The expected values come from the fixture's inputs (the reference, the pproc, the
matrix), never from a product read back.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post._manifest_schema import expected_header
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_p0580_l2_polar_files import _posted

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-MANIFEST")])


def _document(polars):
    return json.loads((polars.parent / "products.json").read_text(encoding="utf-8"))


def test_p0580_products_json_states_the_groups_families_frames_and_polars(tmp_path):
    polars, _said, _rho = _posted(tmp_path, rotors=(("PUSHER", 3, "B"),))
    doc = _document(polars)
    assert doc["schema_version"] == 2
    groups = {entry["GROUP"]: entry for entry in doc["groups"]}
    assert groups["TOTAL"]["GROUP_ID"] == 0
    assert groups["AIRFRAME"]["GROUP_ID"] == 1
    # Rotor id 3 is group 13; the pproc's two declared groups are 101 and 102.
    assert groups["PUSHER"]["GROUP_ID"] == 13
    assert {groups["g01"]["GROUP_ID"], groups["g02"]["GROUP_ID"]} == {101, 102}
    families = {entry["FAMILY"]: entry for entry in doc["families"]}
    assert set(families) >= {"W", "B"}
    assert families["B"]["ROTOR_ID"] == 3 and families["W"]["ROTOR_ID"] is None
    assert groups["PUSHER"]["members"] == [families["B"]["FAMILY_ID"]]
    assert doc["frames"]["R3"]["rotor"] == "PUSHER"
    assert set(doc["polars"]) == {"6001", "6002"}
    assert doc["polars"]["6002"]["run_type"] in {"unsteady", "unsteady_rotor"}
    assert "CTR3" in [column["name"] for column in doc["kinds"]["RCOEF"]["columns"]]
    names = [column["name"] for column in doc["run_block"]]
    assert names[:3] == ["POL", "POINT_ID", "POINT"] and "RPM3" in names


def test_p0580_every_polar_product_names_its_polar(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    doc = _document(polars)
    entries = {name: entry for name, entry in doc["products"].items() if name.startswith("polars/")}
    assert entries
    for name, entry in entries.items():
        assert entry["polar"] == entry["sim_id"], name


def test_p0580_the_fam_acoef_header_is_the_one_products_json_states(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    doc = _document(polars)
    header = read_csv_table(polars / "FAM-ACOEF-P6002.csv")[0]
    stated = expected_header(doc, "FAM-ACOEF")
    # The run block of products.json is the matrix's; a file carries its own
    # reference's rotors, so compare the kind's columns after the block.
    tail = [column["name"] for column in doc["kinds"]["FAM-ACOEF"]["columns"]]
    assert list(header[-len(tail) :]) == tail
    assert stated[-len(tail) :] == tail


def test_p0580_a_retired_polar_file_is_listed_under_migrated(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    old = polars / "P6001-M200RE1177AL+sweepBE+000_g01.csv"
    old.write_text("POL\n6001\n", encoding="utf-8")
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.warns(PyflightstreamWarning, match="names its group by number"):
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    doc = _document(polars)
    assert doc["migrated"]["polars/P6001-M200RE1177AL+sweepBE+000_g01.csv"] == (
        "polars/P6001-g01-ACOEF.csv"
    )
    assert old.read_text(encoding="utf-8") == "POL\n6001\n"


def test_p0580_a_polar_row_carries_the_run_block_of_its_point(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    header, rows = read_csv_table(polars / "P6001-TOTAL-ACOEF.csv")
    # 6001 sweeps AL-020 then AL+000: POINT_ID is the place in that sweep.
    by_point = {row["POINT"]: row for row in rows}
    assert by_point["POLAR-6001_M20AL-020BE+000"]["POINT_ID"] == "1"
    assert by_point["POLAR-6001_M20AL+000BE+000"]["POINT_ID"] == "2"
    assert list(header[:3]) == ["POL", "POINT_ID", "POINT"]


def test_p0580_a_group_name_with_a_slash_is_one_file_and_keeps_its_name(tmp_path):
    polars, _said, _rho = _posted(tmp_path, groups='"Left/Right" = "W"\n')
    names = sorted(path.name for path in polars.iterdir())
    assert "P6002-Left_Right-ACOEF.csv" in names, names
    assert not [path for path in polars.iterdir() if path.is_dir()], names
    _header, rows = read_csv_table(polars / "P6002-Left_Right-ACOEF.csv")
    assert {row["GROUP"] for row in rows} == {"Left/Right"}
