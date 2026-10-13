"""P0400-WSSTORAGE: storage recipes are judged whole before any file moves.

0.40.0 lane workspace-1.

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream.workspace import storage as storage_module
from tests.tier1_offline.test_goal035_storage import _record, _sync_pair, _write, _write_recipe, _ws

pytestmark = pytest.mark.requirement("P0400-WSSTORAGE")

_COMPACT = '[[compact_sims]]\nsims = "all"\n'


def _one_sim(tmp_path):
    workspace = _ws(tmp_path)
    sim = workspace.sim_dir("1201")
    _write(sim / "datapoints" / "DP-1" / "loads.vtk", "payload")
    workspace.append_record(_record("1201", "camp/sim_1201/AL+000"))
    return workspace, sim


@pytest.mark.parametrize(
    ("later", "named"),
    [
        ('[[delete_extensions]]\nextensions = [".fsm"]\n', "never deleted by a recipe"),
        ('[[post_archives]]\nkeep_latest = "two"\n', "keep_latest is a whole number"),
        ('[[post_archives]]\naction = "shred"\n', 'action is "compact" or "delete"'),
        ('[[delete_extensions]]\nextensions = [".vtk"]\nsims = ["9999"]\n', "9999"),
    ],
    ids=["fsm", "keep-latest-text", "action", "sims-without-folder"],
)
def test_p0400_wsstorage_a_later_bad_table_stops_the_recipe_before_the_first_step(
    tmp_path, later, named
):
    """P0400-WSSTORAGE (PFS-2096.028): a valid compaction is not run before a refused table."""
    workspace, sim = _one_sim(tmp_path)
    _write_recipe(workspace, "m001", _COMPACT + later)
    with pytest.raises(storage_module.StorageError, match=re.escape(named)):
        storage_module.free_space(workspace.root, "m001", apply=True)
    assert sim.is_dir() and (sim / "datapoints" / "DP-1" / "loads.vtk").is_file()
    assert not sim.with_name(sim.name + storage_module.COMPACTED_SUFFIX).exists()


@pytest.mark.parametrize(
    ("table", "named"),
    [
        ("[[post_archives]]\nkeep_last = 2\n", "keep_last is spelled keep_latest here"),
        ("[[compact_sims]]\nolder_than = 3\n", "[[compact_sims]] does not read ['older_than']"),
        ('[[delete_extensions]]\nextensions = [".vtk"]\nstatuses = ["FAILED"]\n', "statuses"),
        ("[[post_archives]]\nkeep_latest = -1\n", "keep_latest is a whole number"),
    ],
    ids=["keep-last", "older-than", "statuses", "negative-keep"],
)
def test_p0400_wsstorage_a_key_no_table_reads_is_refused_by_name(tmp_path, table, named):
    """P0400-WSSTORAGE (PFS-2093.007): a misspelt key is no silent widest default."""
    workspace, sim = _one_sim(tmp_path)
    _write_recipe(workspace, "m001", table)
    with pytest.raises(storage_module.StorageError, match=re.escape(named)):
        storage_module.free_space(workspace.root, "m001", apply=True)


def test_p0400_wsstorage_a_status_string_is_refused_as_a_list(tmp_path):
    """P0400-WSSTORAGE (PFS-2097.020): status = "CONVERGED" names the list form and the recipe."""
    workspace, _ = _one_sim(tmp_path)
    _write_recipe(workspace, "m001", '[[compact_sims]]\nstatus = "CONVERGED"\n')
    with pytest.raises(storage_module.StorageError) as refused:
        storage_module.free_space(workspace.root, "m001")
    assert 'status = ["CONVERGED"]' in str(refused.value)
    assert "m001.toml" in str(refused.value)


def test_p0400_wsstorage_an_unknown_status_lists_the_statuses_and_the_recipe(tmp_path):
    """P0400-WSSTORAGE (PFS-2097.020): an unknown name lists every RunStatus and the recipe."""
    workspace, _ = _one_sim(tmp_path)
    _write_recipe(workspace, "m001", '[[compact_sims]]\nstatus = ["CONVERGD"]\n')
    with pytest.raises(storage_module.StorageError) as refused:
        storage_module.free_space(workspace.root, "m001")
    assert "m001.toml" in str(refused.value) and "CONVERGED" in str(refused.value)


@pytest.mark.parametrize("source", ["absent", "main"])
def test_p0400_wsstorage_sync_refusals_name_the_python_keyword(tmp_path, source):
    """P0400-WSSTORAGE (PFS-2100.018): the refusal names source and --from."""
    main, _ = _sync_pair(tmp_path, "source")
    with pytest.raises(storage_module.StorageError, match=r"source \(CLI: --from\)"):
        storage_module.sync_workspaces(main.root, "runs", source=source)
