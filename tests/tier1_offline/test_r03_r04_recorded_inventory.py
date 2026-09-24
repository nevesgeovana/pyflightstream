"""R03 and R04 of 0.27.0: the geometry's inventory settles what the cuts could not (RPT-059).

R03. Every run record carries the boundary names its script read at OPEN
(``inventory``), and the steady one-job path records its sections layout as
the point path does. The integration match then reads a selection by the
export builder's own expansion over those names: a family stem, a numbered
name over a wider family, ``all`` and a user's frame spelt like a rotor's
integrate where the geometry settles them, and stay refused where it does not.

R04. A record written before the inventory existed takes it from the mesh
block of the geometry file whose sha256 the record carries, and a legacy
split is named after the one entry the geometry leaves as its emitter. A
geometry changed since the run recovers nothing, and where the geometry
names no single owner the cuts decide as before and the rows are kept.
"""

from __future__ import annotations

import json
import shutil

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_b01_frozen_solve import _products_manifest
from tests.tier1_offline.test_integrated_sectional_loads import EXTRA, _case
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    _saved_simulation_with,
    _steady_sweep_matrix,
    converged,
)

NAMES = ["wing_left", "B"]

#: The pproc of the steady fixture with one section distribution over one
#: boundary the geometry carries, so the script records a layout.
PPROC_WITH_SECTIONS = (
    '[groups]\n"1" = "all"\n"2" = "wing_left"\n'
    "[sections]\ncount = 4\n"
    '[[sections.distributions]]\nfamilies = "wing_left"\nplanes = ["XZ"]\n'
)


def _raw_rows(workspace: CampaignWorkspace) -> list[dict]:
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    return payload["runs"] if isinstance(payload, dict) else payload


def _run(workspace, matrix):
    return run_matrix(
        matrix,
        workspace,
        name="r03",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )


# --- R03: the writer ----------------------------------------------------------


@pytest.mark.parametrize("shape", ["point", "job", "no-mesh-block"])
def test_r03_every_record_carries_the_inventory_its_script_opened(tmp_path, shape):
    """Both run paths record the names; a geometry declaring none writes no key.

    The key is ABSENT rather than null where nothing was declared, which is
    what keeps a manifest of LEGACY or geometry-less records readable by a
    reader older than 0.27.0, whose record refuses a key it does not know.
    """
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    if shape == "point":
        text = matrix.read_text(encoding="utf-8")
        matrix.write_text(text.replace("-2.0,0.0,2.0", "0.0"), encoding="utf-8")
    if shape != "no-mesh-block":
        _saved_simulation_with(workspace.inputs_dir / "geometries" / "wing_clean.fsm", NAMES)
    _run(workspace, matrix)
    (row,) = _raw_rows(workspace)
    assert row["status"] == "CONVERGED", row.get("error")
    assert bool(row.get("points_ran")) is (shape != "point"), "the fixture took the wrong path"
    if shape == "no-mesh-block":
        assert row["inventory_source"] is None
        assert "inventory" not in row, (
            f"a record whose geometry declares no names wrote inventory={row.get('inventory')!r}"
        )
        return
    assert row["inventory"] == NAMES, row.get("inventory")
    for point in workspace.read_manifest()[0].as_points():
        assert point.inventory == NAMES, point.run_id


def test_a_steady_job_records_its_sections_layout(tmp_path):
    """The one-job path records the layout the point path records (R03-JOB-LAYOUT).

    Without it every multi-point steady row with sections was refused its
    per-distribution split by a post that advised a new run, which recorded
    no layout either.
    """
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    _saved_simulation_with(workspace.inputs_dir / "geometries" / "wing_clean.fsm", NAMES)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(PPROC_WITH_SECTIONS, encoding="utf-8")
    _run(workspace, matrix)
    (row,) = _raw_rows(workspace)
    assert row["status"] == "CONVERGED", row.get("error")
    assert len(row["points_ran"]) == 3, "the fixture must take the one-job path"
    expected = [
        {
            "distribution": 1,
            "distribution_families": "wing_left",
            "families": ["wing_left"],
            "plane": "XZ",
            "frame": "MRP",
            "count": 4,
        }
    ]
    assert row.get("sections_layout") == expected
    for point in workspace.read_manifest()[0].as_points():
        assert point.sections_layout == expected, point.run_id
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    refused = {
        key: reason
        for key, reason in manifest["skipped"].items()
        if "needs the recorded sections_layout" in reason
    }
    assert not refused, refused


# --- R03: the integration match over the recorded inventory --------------------


@pytest.mark.parametrize(
    ("selection", "held", "block_frame", "entry_frame", "inventory", "integrated"),
    [
        ("Blade", ["Blade1", "Blade2"], "MRP", "MRP", ["Wing", "Blade1", "Blade2"], True),
        ("Blade", ["Blade1", "Blade2"], "MRP", "MRP", ["Wing", "Blade", "Blade1", "Blade2"], False),
        ("Blade", ["Blade1", "Blade2"], "MRP", "MRP", ["Blade1", "Blade2", "Blade3"], False),
        ("Blade1", ["Blade11", "Blade12"], "MRP", "MRP", ["Blade11", "Blade12"], True),
        ("Blade1", ["Blade11", "Blade12"], "MRP", "MRP", ["Blade1", "Blade11", "Blade12"], False),
        ("all", [], "MRP", "MRP", ["Wing", "Tail"], True),
        ("all", [], "MRP", "MRP", None, False),
        ("ACTIVE", ["Blade11", "Blade12"], "ACTIVE_RMRP", "RMRP", ["Blade11", "Blade12"], False),
        ("Blade", ["Blade1", "Blade2"], "MRP", "MRP", None, False),
    ],
    ids=[
        "stem-settled",
        "stem-is-a-boundary",
        "third-blade",
        "numbered-over-wider-settled",
        "numbered-is-a-boundary",
        "all-settled",
        "all-no-inventory",
        "rotor-name-stays-refused",
        "stem-no-inventory",
    ],
)
def test_r03_a_recorded_inventory_settles_the_selection(
    tmp_path, monkeypatch, selection, held, block_frame, entry_frame, inventory, integrated
):
    """The builder's own expansion over the recorded names decides; the cuts never do.

    A stem integrates where the geometry's family is exactly the block, and
    is refused where the geometry carries the stem as a boundary or a third
    blade. ``all`` is recorded as an empty family list and is the whole
    inventory. A rotor's name that no definition in hand spells resolves to
    nothing over the names and stays refused by name. Without an inventory
    every case keeps its raw columns, as it did before.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.sections_layout[0].update(
        families=held, distribution_families=selection, frame=block_frame
    )
    if inventory is not None:
        record.inventory = inventory
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    entry.families = selection
    entry.frame = entry_frame
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    key = f"sections/AL-020_sloads_{selection}.csv"
    assert key in manifest["products"], manifest["skipped"]
    columns, rows = read_csv_table(workspace.products_dir(None) / key)
    assert len(rows) == 4
    assert (tuple(columns[-4:]) == EXTRA) is integrated, manifest["skipped"]
    reason = manifest["skipped"].get(f"{key}#integration", "")
    assert ("missing" in reason) is (not integrated), reason


@pytest.mark.parametrize("inventory", [["Blade1", "Blade2"], None], ids=["settled", "no-inventory"])
def test_r03_a_users_frame_spelt_like_a_rotors_integrates_over_the_inventory(
    tmp_path, monkeypatch, inventory
):
    """Two entries on a user's own `X_RMRP`, each integrating its own recorded block.

    With the geometry's names each entry's selection is exactly its block,
    so each owns it alone; without them both stay ambiguous by name, which is
    the refusal `test_gh3_post.py` pins for the rotor-shaped case.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[(0, 1), (0, 1)])
    record = workspace.read_manifest()[0]
    for k, block in enumerate(record.sections_layout, 1):
        block.update(distribution=k, distribution_families=f"Blade{k}", frame="X_RMRP")
    if inventory is not None:
        record.inventory = inventory
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": f"Blade{k}", "frame": "X_RMRP", "integrate": True})
        for k in (1, 2)
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    for k in (1, 2):
        key = f"sections/AL-020_sloads_Blade{k}.csv"
        columns, rows = read_csv_table(workspace.products_dir(None) / key)
        assert len(rows) == 2 and {row["FAMILY"] for row in rows} == {f"Blade{k}"}
        if inventory is not None:
            assert tuple(columns[-4:]) == EXTRA, manifest["skipped"]
            assert f"{key}#integration" not in manifest["skipped"]
        else:
            assert not set(EXTRA) & set(columns)
            assert "ambiguous" in manifest["skipped"].get(f"{key}#integration", "")


# --- R04: an older record, by the geometry's hash ------------------------------


def _record(**update) -> RunRecord:
    return RunRecord(
        run_id="camp/sim_7001/AL-020",
        sim_id="7001",
        fs_version_requested="26.123",
        package_version="0.26.0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        **update,
    )


def test_r04_an_old_record_takes_its_inventory_by_the_geometry_hash(tmp_path):
    """The HASH, never the name, says a file is the one that ran.

    The library file answers while its bytes are the recorded ones; an edit
    since the run recovers nothing; the simulation's own staged copy answers
    once the library file is gone; and a record that carries its own names
    is read as written, without hashing anything.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    library = _saved_simulation_with(
        workspace.inputs_dir / "geometries" / "geo.fsm", ["Blade1", "Blade11", "Blade12"]
    )
    original = library.read_bytes()
    record = _record(
        inputs_sha256={"geo.fsm": file_sha256(library), "scripts/counter.py": "0" * 64}
    )
    assert workspace.recorded_inventory(record) == ("Blade1", "Blade11", "Blade12")

    _saved_simulation_with(library, ["Blade1", "Blade11", "Blade13"])
    assert workspace.recorded_inventory(record) is None, "an edited geometry answered"

    staged = workspace.sim_dir("7001") / "inputs" / "geo.fsm"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(original)
    library.unlink()
    assert workspace.recorded_inventory(record) == ("Blade1", "Blade11", "Blade12")

    shutil.rmtree(staged.parent)
    assert workspace.recorded_inventory(record) is None, "a deleted geometry answered"
    own = record.model_copy(update={"inventory": ["X"]})
    assert workspace.recorded_inventory(own) == ("X",)


@pytest.mark.parametrize(
    ("first", "rivals", "edited", "owner", "distribution"),
    [
        ("Blade1", ("ACTIVE",), False, "ACTIVE", 2),
        ("Blade1", ("ACTIVE",), True, "Blade1", 1),
        ("Blade1", ("ACTIVE", "OTHER"), False, "Blade1", 1),
        ("Blade", ("ACTIVE",), False, "Blade", 1),
    ],
    ids=[
        "settled-by-hash",
        "edited-geometry",
        "two-unreadable-rivals",
        "a-certain-rival-on-a-rotor-frame",
    ],
)
def test_r04_a_legacy_split_is_named_after_the_entry_the_geometry_leaves(
    tmp_path, monkeypatch, first, rivals, edited, owner, distribution
):
    """RPT-059's own case: a 0.24.x block of rotor ACTIVE, with no rotor definition in hand.

    Entry 1 selects `Blade1`, which the geometry carries as a boundary of its
    own, so it did not emit a block of Blade11 and Blade12; the only entry
    that could have is the one whose word nothing resolves, and the block is
    named after it. Ownership adds no number: nothing is integrated either way.

    An entry the geometry reads with certainty is not thereby excluded on a
    rotor's frame with no rotor definition: `Blade` selects Blade1, Blade11
    and Blade12, and rotor ACTIVE may own exactly the last two, so it remains
    a possible emitter beside ACTIVE, the geometry names no single owner, and
    the cuts decide as they did before.
    """
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    block = record.sections_layout[0]
    del block["distribution"]
    del block["distribution_families"]
    block.update(families=["Blade11", "Blade12"], frame="ACTIVE_RMRP")
    geometry = _saved_simulation_with(
        workspace.inputs_dir / "geometries" / "geo.fsm", ["Blade1", "Blade11", "Blade12"]
    )
    record.inputs_sha256 = {"geo.fsm": file_sha256(geometry)}
    if edited:
        _saved_simulation_with(geometry, ["Blade1", "Blade11", "Blade13"])
    spec = workspace.resolve_pproc("p001")
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(update={"families": first, "frame": "RMRP", "integrate": True}),
        *[
            entry.model_copy(update={"families": name, "frame": "RMRP", "integrate": False})
            for name in rivals
        ],
    ]
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    key = f"sections/AL-020_sloads_{owner}.csv"
    assert key in manifest["products"], manifest["skipped"]
    assert manifest["products"][key]["distribution"] == distribution
    columns, rows = read_csv_table(workspace.products_dir(None) / key)
    assert len(rows) == 4 and {row["FAMILY"] for row in rows} == {"Blade11+Blade12"}
    assert not set(EXTRA) & set(columns), "ownership integrated a legacy block"
    others = {
        k for k in manifest["products"] if k.startswith("sections/AL-020_sloads_") and k != key
    }
    assert not others, f"the one block was written under {sorted(others)} as well"
