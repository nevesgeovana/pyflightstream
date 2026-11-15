"""The polar files of the 0.57.0 layout are left untouched and said (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, section 2.2). The post writes only
the new files. An earlier-layout file already in ``polars/`` (a SUPER file, a
numbered ``_g<NN>`` polar, an ``uns_avg`` polar, a per-group per-Mach polar, a rotor
table) is not rewritten, archived or removed, and each kind is named once in one
warning carrying the design's text and ending with the pointer to the upgrade note.
"""

from __future__ import annotations

import json
import warnings

import pytest

from pyflightstream.post.products import write_campaign_products
from tests.tier1_offline.test_p0580_l2_polar_files import _posted

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-RETIRED")])

POINTER = "See docs/upgrading.md#0580-post-tree."

OLD = {
    "SUPER-6001-M200RE1177AL+sweepBE+000_WING.csv": (
        "The SUPER file is retired; every family is in FAM-DIM-P6001.csv and FAM-ACOEF-P6001.csv, "
        "the run condition in their run block, and the setup codes in settings/."
    ),
    "P6002_M144RE438AL+000BE+000J+170_uns_avg.csv": (
        "P6002_M144RE438AL+000BE+000J+170_uns_avg.csv is the 0.57.0 unsteady polar; 0.58.0 "
        "writes the window average of every family in FAM-*-P6002.csv and of every group in "
        "its group files, under the same names as a steady polar."
    ),
    "P6002-PUSHER_rotor.csv": (
        "The rotor table is retired; rotor PUSHER (id 0) is the group of its own RCOEF file, "
        "P6002-PUSHER-RCOEF.csv; its J, tip and helical Mach numbers are in the run block as "
        "J0, MTIP0, MHEL0."
    ),
    "P6001-M200RE1177AL+sweepBE+000_g01.csv": (
        "P6001-M200RE1177AL+sweepBE+000_g01.csv names its group by number; 0.58.0 writes it "
        "as group g01; name the group in [groups] to name its files."
    ),
    "P6001-M200RE1177AL+sweepBE+000_WING.csv": (
        "P6001-M200RE1177AL+sweepBE+000_WING.csv is the 0.57.0 per-group, per-Mach polar; "
        "0.58.0 writes one file set per polar: the families in FAM-DIM, FAM-ACOEF and "
        "FAM-RCOEF-P6001.csv and the group WING in its own group files."
    ),
}


def _replanted(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    out = polars.parent
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    for name in OLD:
        (polars / name).write_text("POL,CDB\n6001,0.1\n", encoding="utf-8")
        sim = "6001" if "6001" in name else "6002"
        manifest["products"][f"polars/{name}"] = {"sim_id": sim, "runs": []}
    (out / "products.json").write_text(json.dumps(manifest), encoding="utf-8")
    workspace_root = out.parent.parent
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace(workspace_root)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return polars, [str(w.message) for w in caught]


def test_each_retired_file_is_left_untouched_and_said_once_per_kind(tmp_path):
    polars, said = _replanted(tmp_path)
    for name, sentence in OLD.items():
        assert (polars / name).read_text(encoding="utf-8") == "POL,CDB\n6001,0.1\n", name
        holding = [text for text in said if sentence in text]
        assert len(holding) == 1, (name, [t[:120] for t in said if "0.58.0" in t or "SUPER" in t])
        assert holding[0].endswith(POINTER), holding[0]
    assert (polars / "FAM-ACOEF-P6001.csv").is_file()
    assert (polars / "P6002-PUSHER-RCOEF.csv").is_file()


def test_a_post_of_a_tree_with_no_earlier_file_says_nothing_of_it(tmp_path):
    _polars, said = _posted(tmp_path)[:2]
    assert not [text for text in said if POINTER in text and "retired" in text and "SUPER" in text]


def test_the_retired_layout_is_told_from_the_new():
    from pyflightstream.post._retired_polars import is_retired_layout

    for name in OLD:
        assert is_retired_layout(f"polars/{name}"), name
    for name in (
        "FAM-ACOEF-P6001.csv",
        "P6001-TOTAL-ACOEF.csv",
        "P6001-LEFT_WING-DIM.csv",
        "P6001-WING-ACOEF_trim.csv",
        "P6001-WING-ACOEF.dat",
    ):
        assert not is_retired_layout(f"polars/{name}"), name
