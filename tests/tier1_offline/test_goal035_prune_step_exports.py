"""Tier 1 offline: the ``prune_step_exports`` free-space mode of 0.30.0 (S7).

An unsteady row that exports at every step (``EXPORT_UNSTEADY_AFTER_ITER`` or
``_AFTER_REV``) leaves one stamped file per step and export,
``<stem>_iteration=<step>.<ext>``, where the point ran. The mode keeps the
LAST step of each export of each point and deletes the others: preview by
default, files deleted only with ``apply``, and the call recorded in
``storage_management.json`` with the steps deleted per point.

Afterwards a product made before the call stays, file and manifest entry; a
NEW post that needs a deleted step refuses by name (the step and the storage
call), in the series, the time-averaged surface and the section
distributions, never a silent gap. A step that was never exported keeps the
rule it had. Every workspace here is a real ``tmp_path`` tree.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-174.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunStatus, _make_dir_link
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.storage import (
    PRUNE_MODE,
    STEP_EXPORTS_PRUNED,
    free_space,
    pruned_step_refusal,
    read_storage_calls,
)
from tests.tier1_offline.test_goal028_series import _submitted_workspace
from tests.tier1_offline.test_post_products import _products_manifest, _series

RUN = "camp/sim_7001/AL-020"
KINDS = ("", "_sloads", "_probes")


def _recipe(workspace, text: str = f'[[{PRUNE_MODE}]]\nsims = "all"\n', name: str = "m1"):
    path = workspace.root / storage_module.MANAGEMENT_DIR / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


def _dp(workspace) -> Path:
    return workspace.sim_dir("7001") / "datapoints" / "DP-AL-020"


def _stamped(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir() if "_iteration=" in path.name)


# --------------------------------------------------------------------------- the mode


def test_the_preview_deletes_nothing_and_records_the_steps_it_would_delete(tmp_path):
    # P0300-S7-PREVIEW-APPLY
    workspace = _submitted_workspace(tmp_path)
    before = _stamped(_dp(workspace))
    entry = free_space(workspace.root, _recipe(workspace))
    assert _stamped(_dp(workspace)) == before and len(before) == 9
    (step,) = entry["steps"]
    assert step["mode"] == PRUNE_MODE and entry["applied"] is False
    (point,) = step["points"]
    assert point["deleted_steps"] == [3, 4] and len(point["files"]) == 6
    assert entry["bytes_freed"] == 0
    assert read_storage_calls(workspace.root)[-1]["applied"] is False


def test_apply_keeps_the_last_step_of_each_export_and_records_the_steps_per_point(tmp_path):
    # P0300-S7-LAST-STEP
    workspace = _submitted_workspace(tmp_path)
    entry = free_space(workspace.root, _recipe(workspace), apply=True)
    assert _stamped(_dp(workspace)) == [f"AL-020{kind}_iteration=5.txt" for kind in sorted(KINDS)]
    assert (_dp(workspace) / "AL-020.txt").is_file(), "the declared output is never pruned"
    (point,) = entry["steps"][0]["points"]
    assert point["folder"] == "sims/sim_7001/datapoints/DP-AL-020"
    assert point["run_ids"] == [RUN]
    assert point["deleted_steps"] == [3, 4]
    assert sorted(item["step"] for item in point["files"]) == [3, 3, 3, 4, 4, 4]
    assert {item["step"] for item in point["kept"]} == {5} and len(point["kept"]) == 3
    assert entry["bytes_freed"] == sum(item["bytes"] for item in point["files"]) > 0
    recorded = read_storage_calls(workspace.root)[-1]
    assert recorded["applied"] is True and recorded["steps"][0]["points"][0] == point


def test_each_export_keeps_its_own_last_step(tmp_path):
    """A probe export that stopped a step early keeps ITS last step, not the loads'."""
    workspace = _submitted_workspace(tmp_path)
    (_dp(workspace) / "AL-020_probes_iteration=5.txt").unlink()
    free_space(workspace.root, _recipe(workspace), apply=True)
    assert "AL-020_probes_iteration=4.txt" in _stamped(_dp(workspace))


def _three_sims(tmp_path):
    """7001 and 7002 CONVERGED, 7003 FAILED_EXECUTION, each with the same stamped steps."""
    import shutil

    workspace = _submitted_workspace(tmp_path)
    raw = workspace.read_raw_manifest()
    for sim, status in (("7002", RunStatus.CONVERGED), ("7003", RunStatus.FAILED_EXECUTION)):
        shutil.copytree(workspace.sim_dir("7001"), workspace.sim_dir(sim))
        row = dict(raw[0], run_id=f"camp/sim_{sim}/AL-020", sim_id=sim, status=status.value)
        raw.append(row)
    workspace._replace_manifest(raw)
    return workspace


def _pruned_sims(workspace) -> list[str]:
    return [
        sim
        for sim in ("7001", "7002", "7003")
        if len(_stamped(workspace.sim_dir(sim) / "datapoints" / "DP-AL-020")) == 3
    ]


@pytest.mark.parametrize(
    ("selection", "pruned"),
    [
        ('sims = ["7002"]', ["7002"]),
        ('sims = "all"\nstatus = ["CONVERGED"]', ["7001", "7002"]),
        ('sims = ["7001", "7003"]\nstatus = ["CONVERGED"]', ["7001"]),
    ],
)
def test_the_named_sims_and_the_status_filter_limit_what_is_pruned(tmp_path, selection, pruned):
    # P0300-S7-LAST-STEP: the selection of a [[prune_step_exports]] table is
    # honoured; a simulation it does not select keeps every step.
    workspace = _three_sims(tmp_path)
    text = f"[[{PRUNE_MODE}]]\n{selection}\n"
    entry = free_space(workspace.root, _recipe(workspace, text), apply=True)
    assert _pruned_sims(workspace) == pruned
    for sim in {"7001", "7002", "7003"}.difference(pruned):
        assert len(_stamped(workspace.sim_dir(sim) / "datapoints" / "DP-AL-020")) == 9, sim
    folders = [point["folder"] for point in entry["steps"][0]["points"]]
    assert folders == [f"sims/sim_{sim}/datapoints/DP-AL-020" for sim in pruned]


def test_a_submitted_simulation_is_refused_and_keeps_every_step(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    raw = workspace.read_raw_manifest()
    raw[0]["status"] = RunStatus.SUBMITTED.value
    workspace._replace_manifest(raw)
    entry = free_space(workspace.root, _recipe(workspace), apply=True)
    assert entry["steps"][0]["refused"] == {"7001": "a run is still SUBMITTED; every step is kept"}
    assert len(_stamped(_dp(workspace))) == 9


def test_a_file_a_record_names_is_protected_even_when_stamped(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    raw = workspace.read_raw_manifest()
    raw[0]["outputs"].append("datapoints/DP-AL-020/AL-020_iteration=3.txt")
    workspace._replace_manifest(raw)
    entry = free_space(workspace.root, _recipe(workspace), apply=True)
    assert (_dp(workspace) / "AL-020_iteration=3.txt").is_file()
    (point,) = entry["steps"][0]["points"]
    assert point["protected"] == ["sims/sim_7001/datapoints/DP-AL-020/AL-020_iteration=3.txt"]


def test_inputs_are_never_pruned_linked_or_copied(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    library = workspace.inputs_dir / "geometries" / "g1"
    library.mkdir(parents=True)
    for step in (1, 2):
        (library / f"g1_iteration={step}.txt").write_text("mesh", encoding="utf-8")
    _make_dir_link(library, workspace.sim_dir("7001") / "inputs")
    copy = workspace.sim_dir("7002") / "inputs"
    copy.mkdir(parents=True)
    for step in (1, 2):
        (copy / f"g1_iteration={step}.txt").write_text("mesh", encoding="utf-8")
    free_space(workspace.root, _recipe(workspace), apply=True)
    assert _stamped(library) == ["g1_iteration=1.txt", "g1_iteration=2.txt"]
    assert _stamped(copy) == ["g1_iteration=1.txt", "g1_iteration=2.txt"]


def test_a_recipe_can_prune_then_compact_in_one_call(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    text = f'[[{PRUNE_MODE}]]\nsims = "all"\n\n[[compact_sims]]\nsims = "all"\n'
    entry = free_space(workspace.root, _recipe(workspace, text), apply=True)
    assert [step["mode"] for step in entry["steps"]] == [PRUNE_MODE, "compact_sims"]
    assert entry["steps"][0]["points"][0]["deleted_steps"] == [3, 4]


def test_the_cli_prints_the_pruned_steps_of_each_point(tmp_path, capsys):
    workspace = _submitted_workspace(tmp_path)
    recipe = _recipe(workspace)
    assert matrix_cli.main(["free-space", recipe, "--workspace", str(workspace.root)]) == 0
    printed = capsys.readouterr().out
    assert "prune_step_exports: 1 point(s), 6 per-step file(s)" in printed, printed
    assert "sims/sim_7001/datapoints/DP-AL-020: steps 3 to 4 (2 step(s))" in printed, printed


# --------------------------------------------------------------------------- the post after


def test_a_post_after_pruning_refuses_the_series_by_step_and_keeps_the_one_made_before(tmp_path):
    # P0300-S7-REFUSE-DELETED
    workspace = _submitted_workspace(tmp_path)
    write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "series" / "AL-020_loads_series.csv"
    made = table.read_bytes()
    free_space(workspace.root, _recipe(workspace), apply=True)
    write_campaign_products(workspace, overwrite=True)
    manifest = _products_manifest(workspace)
    reason = manifest["skipped"]["series/AL-020_loads_series.csv"]
    assert reason.startswith(STEP_EXPORTS_PRUNED), reason
    assert "step(s) 3, 4 of the window 3 to 5" in reason, reason
    assert "AL-020_iteration=3.txt" in reason and "call 0 of storage_management.json" in reason
    # THE PRODUCT MADE BEFORE STAYS: its file untouched, its entry in the manifest.
    assert table.read_bytes() == made
    entry = manifest["products"]["series/AL-020_loads_series.csv"]
    assert entry["steps_tabled"] == [3, 4, 5] and entry["kept_after_pruning"] == reason


def test_a_post_that_never_made_the_series_refuses_it_and_writes_nothing(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    free_space(workspace.root, _recipe(workspace), apply=True)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    for kind in ("loads", "sections", "probes"):
        name = f"series/AL-020_{kind}_series.csv"
        assert manifest["skipped"][name].startswith(STEP_EXPORTS_PRUNED), name
        assert name not in manifest["products"]
        assert not (workspace.root / "post" / "products" / name).exists()


def test_a_step_never_exported_keeps_the_rule_it_had(tmp_path):
    """The control: a gap no storage call made is tabled around, as before 0.30.0."""
    workspace = _submitted_workspace(tmp_path)
    free_space(workspace.root, _recipe(workspace))  # a preview: a record, nothing deleted
    (_dp(workspace) / "AL-020_iteration=3.txt").unlink()
    write_campaign_products(workspace)
    _columns, rows = _series(workspace, "AL-020_loads_series.csv")
    assert [int(row["STEP"]) for row in rows] == [4, 5]


def test_a_pruned_step_of_another_run_refuses_nothing(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    free_space(workspace.root, _recipe(workspace), apply=True)
    expected = {3: [_dp(workspace) / "AL-020_iteration=3.txt"]}
    sim_dir = workspace.sim_dir("7001")
    assert pruned_step_refusal(sim_dir, RUN, expected, product="x", window=(3, 5)) is not None
    assert pruned_step_refusal(sim_dir, "other/run", expected, product="x", window=(3, 5)) is None


def test_the_time_averaged_surface_is_refused_by_step_and_the_instants_leave_the_manifest(
    tmp_path,
):
    from pyflightstream.results import translate_surface_exports
    from tests.tier1_offline.test_g25_surface_time_average import _averaged_record, _exports
    from tests.tier1_offline.test_g45_tecplot_from_vtk import MRP, _write_solver_vtk

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record = _averaged_record()
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    bodies = _exports(sim, range(3, 7))
    (sim / "p.txt").write_text("native export", encoding="utf-8")
    _write_solver_vtk(sim / "p.vtk", *bodies[6], MRP)
    translate_surface_exports(sim, [{"vtk": "p.vtk", "dat": "p.dat", "frame": MRP}])
    workspace.append_record(record)
    write_campaign_products(workspace, overwrite=True)
    out = workspace.products_dir(None)
    average = out / "surfaces" / "p_time_average.dat"
    made = average.read_bytes()
    listed = json.loads((out / "products.json").read_text(encoding="utf-8"))["products"]
    assert "../../sims/sim_7003/p_iteration=3.vtk" in listed
    entry = free_space(workspace.root, _recipe(workspace), apply=True)
    assert sorted(path.name for path in sim.glob("*_iteration=*")) == [
        "p_iteration=6.dat",
        "p_iteration=6.vtk",
    ]
    # THE MANIFEST NEVER CLAIMS A DELETED FILE: the pruned instants leave it at once.
    after = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert entry["steps"][0]["products_json"] == {"post/products/products.json": 6}
    assert not any("_iteration=3." in name for name in after["products"])
    assert "surfaces/p_time_average.dat" in after["products"]
    assert len(after["pruned_by_storage"][0]["listings_removed"]) == 6
    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    reason = manifest["skipped"]["surfaces/p_time_average.dat"]
    assert reason.startswith(STEP_EXPORTS_PRUNED) and "step(s) 3, 4, 5 of the window 3 to 6" in (
        reason
    ), reason
    assert average.read_bytes() == made
    assert manifest["products"]["surfaces/p_time_average.dat"]["kept_after_pruning"] == reason


@pytest.mark.parametrize("kind", ["sloads", "cp"])
def test_the_section_distributions_are_refused_by_step(tmp_path, monkeypatch, kind):
    from tests.tier1_offline.test_f07_section_distributions import _post
    from tests.tier1_offline.test_f07_section_distributions import _workspace as _sections

    workspace, record = _sections(tmp_path, monkeypatch, stamped=True)
    workspace._replace_manifest([record.model_dump(mode="json")])
    free_space(workspace.root, _recipe(workspace), apply=True)
    _out, manifest = _post(workspace)
    relative = f"sections/AL-020_{kind}_wing.csv"
    reason = manifest["skipped"][relative]
    assert reason.startswith(STEP_EXPORTS_PRUNED) and "step(s) 3, 4 of the window 3 to 5" in (
        reason
    ), reason
    assert relative not in manifest["products"]
    assert f"{relative}#step=3" not in manifest["skipped"]


def test_only_a_pruned_step_refusal_keeps_a_previous_product_and_only_one_on_disk(tmp_path):
    from pyflightstream.post.products import products_kept_after_pruning

    (tmp_path / "surfaces").mkdir()
    for name in ("p_time_average.vtk", "q_time_average.dat"):
        (tmp_path / "surfaces" / name).write_text("made before", encoding="utf-8")
    previous = {
        "surfaces/p_time_average.dat": {"runs": ["r"]},
        "surfaces/p_time_average.vtk": {"runs": ["r"]},
        "surfaces/q_time_average.dat": {"runs": ["s"]},
    }
    skipped = {
        "surfaces/p_time_average.dat": f"{STEP_EXPORTS_PRUNED}p needs step(s) 3",
        "surfaces/q_time_average.dat": "2 step(s) of the window 3 to 6 were not exported",
    }
    kept = products_kept_after_pruning(skipped, previous, tmp_path)
    # The Tecplot is gone from disk, so only the VTK beside it is kept; the other
    # product's refusal is not about a pruned step, so it is retired as before.
    assert list(kept) == ["surfaces/p_time_average.vtk"]
    assert kept["surfaces/p_time_average.vtk"]["kept_after_pruning"].startswith(STEP_EXPORTS_PRUNED)
