"""Round r2 (A1, A2): one rotor-id map, one upgrade pointer.

The rotor aliases of a reference are compared case-insensitively by its reader,
so the map of alias to declared id keeps the alias as written and every caller
folds the key itself.
"""

from __future__ import annotations

import json
import warnings
from types import SimpleNamespace

from pyflightstream.post import _point_stage, _retired_polars, _tree_migration
from pyflightstream.post._block_scope import rotor_ids_from
from pyflightstream.post.products import write_campaign_products
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_p0580_l2_polar_files import _posted


def _block(rotor_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=rotor_id)


def test_p0580_r2_the_two_call_paths_agree_on_an_alias_as_written() -> None:
    rotors = {"Prop1": _block(3), "Lift2": _block(7)}
    ctx = SimpleNamespace(live=SimpleNamespace(rotors=rotors))
    assert _point_stage.rotor_ids_of(ctx) == rotor_ids_from(rotors) == {"Prop1": 3, "Lift2": 7}


def test_p0580_r2_the_campaign_lookup_finds_an_alias_written_in_another_case(tmp_path) -> None:
    polars, _said, _rho = _posted(tmp_path, rotors=(("Pusher", 3, "B"),))
    out = polars.parent
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    (polars / "P6002-PUSHER_rotor.csv").write_text("POL,CDB\n6002,0.1\n", encoding="utf-8")
    manifest["products"]["polars/P6002-PUSHER_rotor.csv"] = {"sim_id": "6002", "runs": []}
    (out / "products.json").write_text(json.dumps(manifest), encoding="utf-8")
    workspace = CampaignWorkspace(out.parent.parent)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    assert any("rotor PUSHER (id 3)" in str(w.message) for w in caught)


def test_p0580_r2_the_retired_polars_module_keeps_no_copy() -> None:
    assert not hasattr(_retired_polars, "rotor_ids_of")


def test_p0580_r2_the_upgrade_pointer_is_the_migration_s_own_object() -> None:
    assert _retired_polars.UPGRADE_POINTER is _tree_migration.POINTER
