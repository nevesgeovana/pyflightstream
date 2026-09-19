"""An unsteady rotor table read from the native export says it holds an instant.

A record made before its run carried a reductions plan states no window, so its
rotor rows come from the loads export, which on an unsteady run states the LAST
TIME STEP: one instant of a cycle. `products.json` called that source "the loads
export of a steady run", a steady run it is not, and the entry carried no `kind`
(found reading the code for the architecture document of 0.24.0, before release
round 2). The manifest must say what the table holds, as a sections table's entry
does with `kind: instant`.
"""

from __future__ import annotations

import json
import warnings

from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_goal028_rotor_table_average import REFERENCE, _pproc
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace


def _posted_without_a_plan(tmp_path) -> dict:
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(REFERENCE, encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        _pproc("HUB_PUSHER", "MRP", '["B"]'), encoding="utf-8"
    )
    (workspace.root / "matriz.fs").write_text(_MATRIX, encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6002":
            # A RECORD THAT STATES ITS ROTOR'S SPEED AND NO WINDOW: the rotor block
            # of the plan and nothing that says which steps to average. (With no
            # plan at all the rotor has no speed and the table is skipped, named.)
            plan = {"rotors": {"PUSHER": {"blades": 6, "rpm": 2200.0}}}
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8"))


def test_the_fixture_is_an_unsteady_rotor_record_with_no_plan(tmp_path):
    workspace = _workspace(tmp_path)
    (record,) = [r for r in workspace.read_manifest() if r.sim_id == "6002"][:1]
    assert str(record.recipe).startswith("unsteady"), record.recipe


def test_a_rotor_table_of_an_unsteady_runs_last_step_says_so(tmp_path):
    products = _posted_without_a_plan(tmp_path)["products"]
    entries = {name: entry for name, entry in products.items() if name.endswith("_rotor.csv")}
    unsteady = {name: entry for name, entry in entries.items() if "6002" in name}
    assert unsteady, sorted(products)
    for name, entry in unsteady.items():
        assert "steady run" not in entry["source"] or "unsteady" in entry["source"], (name, entry)
        assert "last time step" in entry["source"].lower(), (name, entry)
        assert entry.get("kind") == "instant", (name, entry)
