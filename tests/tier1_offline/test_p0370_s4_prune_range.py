"""Tier 1 offline: ``[[prune_step_exports]]`` keeps the last K steps or deletes a range (FR-416).

An unsteady point leaves one stamped file per step and export. 0.30.0 kept the
last step of each export; a table may now state ``keep_last = K`` or
``delete_steps = [A, B]`` (never both), every other key of the table is
refused before a file is touched, and a later post that needs a deleted step
refuses by name saying what the call kept. Every workspace is a real
``tmp_path`` tree with 30 steps of the loads export and 20 of the sectional
loads export.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace import _step_prune as step_prune
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.storage import (
    MANAGEMENT_DIR,
    PRUNE_MODE,
    StorageError,
    free_space,
    pruned_step_refusal,
    read_recipe,
    read_storage_calls,
)

RUN = "camp/sim_6001/AL+000"
STEPS = 30
SLOAD_STEPS = 20


def _record(sim: str, status: RunStatus, outputs: list[str]) -> RunRecord:
    return RunRecord(
        run_id=f"camp/sim_{sim}/AL+000",
        sim_id=sim,
        matrix_stem="matriz",
        fs_version_requested="26.123",
        package_version="0.37.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=status,
        outputs=outputs,
        script_path=None,
        inputs_sha256={},
    )


def _workspace(tmp_path: Path, *, protect_step: int | None = None) -> CampaignWorkspace:
    """Sim 6001: 30 steps of ``loads`` and 20 of ``loads_sloads``; sim 6002 is SUBMITTED."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    point = workspace.sim_dir("6001") / "datapoints" / "DP-1"
    point.mkdir(parents=True)
    for step in range(1, STEPS + 1):
        (point / f"loads_iteration={step}.txt").write_text(f"loads {step}\n", encoding="utf-8")
    for step in range(1, SLOAD_STEPS + 1):
        (point / f"loads_sloads_iteration={step}.txt").write_text("s\n", encoding="utf-8")
    outputs = ["datapoints/DP-1/loads.txt"]
    (point / "loads.txt").write_text("declared output\n", encoding="utf-8")
    if protect_step is not None:
        outputs.append(f"datapoints/DP-1/loads_iteration={protect_step}.txt")
    workspace.append_record(_record("6001", RunStatus.CONVERGED, outputs))
    other = workspace.sim_dir("6002") / "datapoints" / "DP-1"
    other.mkdir(parents=True)
    for step in (1, 2, 3):
        (other / f"loads_iteration={step}.txt").write_text("x\n", encoding="utf-8")
    workspace.append_record(_record("6002", RunStatus.SUBMITTED, []))
    return workspace


def _recipe(workspace: CampaignWorkspace, body: str = "", name: str = "m1") -> str:
    path = workspace.root / MANAGEMENT_DIR / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[[{PRUNE_MODE}]]\nsims = ["6001"]\n{body}', encoding="utf-8")
    return name


def _point(workspace: CampaignWorkspace) -> Path:
    return workspace.sim_dir("6001") / "datapoints" / "DP-1"


def _steps(workspace: CampaignWorkspace, stem: str = "loads") -> list[int]:
    found = []
    for path in _point(workspace).glob(f"{stem}_iteration=*.txt"):
        found.append(int(path.stem.rsplit("=", 1)[1]))
    return sorted(found)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _only_step(entry: dict) -> dict:
    (step,) = entry["steps"]
    return step


# ------------------------------------------------------------------ R1 selection


def test_keep_last_twelve_of_thirty_keeps_the_last_twelve_of_each_export(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): keep_last = 12 keeps 19 to 30, and 9 to 20."""
    workspace = _workspace(tmp_path)
    entry = free_space(workspace.root, _recipe(workspace, "keep_last = 12\n"), apply=True)
    assert _steps(workspace) == list(range(19, 31))
    assert _steps(workspace, "loads_sloads") == list(range(9, 21))
    step = _only_step(entry)
    (point,) = step["points"]
    assert point["deleted_steps"] == list(range(1, 19))
    assert [item["step"] for item in point["kept"] if "sloads" not in item["path"]] == list(
        range(19, 31)
    )
    assert len(point["files"]) == 18 + 8


def test_delete_steps_five_to_nine_deletes_exactly_that_range_of_each_export(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): delete_steps = [5, 9] deletes 5 to 9, keeps the rest."""
    workspace = _workspace(tmp_path)
    entry = free_space(workspace.root, _recipe(workspace, "delete_steps = [5, 9]\n"), apply=True)
    expected = [step for step in range(1, STEPS + 1) if not 5 <= step <= 9]
    assert _steps(workspace) == expected
    assert _steps(workspace, "loads_sloads") == [
        step for step in range(1, SLOAD_STEPS + 1) if not 5 <= step <= 9
    ]
    (point,) = _only_step(entry)["points"]
    assert point["deleted_steps"] == [5, 6, 7, 8, 9]
    assert len(point["files"]) == 10


@pytest.mark.parametrize(
    "body",
    [
        "keep_last = 30\n",
        "keep_last = 40\n",
        "delete_steps = [31, 40]\n",
        "delete_steps = [21, 25]\n",
    ],
)
def test_a_count_above_the_steps_or_a_range_outside_them_deletes_nothing_and_is_no_error(
    tmp_path, body
):
    """P0370-S4-PRUNE-RANGE (FR-416): nothing to delete is recorded as such, not refused."""
    workspace = _workspace(tmp_path)
    before = _snapshot(workspace.root / "sims")
    entry = free_space(workspace.root, _recipe(workspace, body), apply=True)
    if body == "delete_steps = [21, 25]\n":
        # 21 to 25 holds steps of the loads export (30 steps) but none of the sloads export.
        assert _steps(workspace) == [s for s in range(1, STEPS + 1) if not 21 <= s <= 25]
        assert _steps(workspace, "loads_sloads") == list(range(1, SLOAD_STEPS + 1))
        return
    assert _snapshot(workspace.root / "sims") == before
    step = _only_step(entry)
    assert step["points"] == [] and entry["bytes_freed"] == 0
    key, value = body.split(" = ")
    assert step[key] == json.loads(value)


# ------------------------------------------------------------------ R2 keys and values


def test_an_unknown_key_is_refused_naming_it_and_the_accepted_keys_with_the_tree_unchanged(
    tmp_path,
):
    """P0370-S4-PRUNE-RANGE (FR-416): a misspelt key never becomes a silent default."""
    workspace = _workspace(tmp_path)
    before = _snapshot(workspace.root)
    # The first table is valid and would delete; the second carries the bad key.
    name = _recipe(workspace, "keep_last = 12\n")
    recipe = workspace.root / MANAGEMENT_DIR / f"{name}.toml"
    recipe.write_text(
        recipe.read_text(encoding="utf-8")
        + f'\n[[{PRUNE_MODE}]]\nsims = ["6001"]\nkeep_lastt = 3\n',
        encoding="utf-8",
    )
    before[recipe.relative_to(workspace.root).as_posix()] = recipe.read_bytes()
    with pytest.raises(StorageError) as caught:
        free_space(workspace.root, name, apply=True)
    message = str(caught.value)
    assert "keep_lastt" in message
    for accepted in ("sims", "status", "keep_last", "delete_steps"):
        assert accepted in message
    assert _snapshot(workspace.root) == before


def test_the_accepted_keys_are_the_030_keys_plus_keep_last_and_delete_steps(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): sims and status of 0.30.0, and the two new keys."""
    assert set(step_prune.PRUNE_KEYS) == {"sims", "status"} | {"keep_last", "delete_steps"}
    workspace = _workspace(tmp_path)
    name = _recipe(workspace, 'status = ["CONVERGED"]\nkeep_last = 2\n')
    _, document = read_recipe(workspace.root, name)
    assert document[PRUNE_MODE][0]["keep_last"] == 2
    name = _recipe(workspace, 'status = ["CONVERGED"]\ndelete_steps = [1, 2]\n', name="m2")
    read_recipe(workspace.root, name)
    name = _recipe(workspace, "older_than_days = 3\n", name="m3")
    with pytest.raises(StorageError, match="older_than_days"):
        read_recipe(workspace.root, name)


def test_both_keys_stated_is_refused_with_the_tree_unchanged(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): keep_last and delete_steps together are refused."""
    workspace = _workspace(tmp_path)
    name = _recipe(workspace, "keep_last = 2\ndelete_steps = [1, 2]\n")
    before = _snapshot(workspace.root)
    with pytest.raises(StorageError, match="keep_last and delete_steps"):
        free_space(workspace.root, name, apply=True)
    assert _snapshot(workspace.root) == before
    assert not (workspace.root / storage_module.STORAGE_FILE).exists()


@pytest.mark.parametrize(
    "body",
    [
        "keep_last = 0\n",
        "keep_last = -1\n",
        "keep_last = true\n",
        "keep_last = 2.5\n",
        'keep_last = "3"\n',
        "delete_steps = [9, 5]\n",
        "delete_steps = [5]\n",
        "delete_steps = [1, 2, 3]\n",
        "delete_steps = [0, 3]\n",
        "delete_steps = [true, 3]\n",
        "delete_steps = 5\n",
    ],
)
def test_a_value_that_is_not_a_positive_count_or_an_ordered_pair_is_refused_before_any_file(
    tmp_path, body
):
    """P0370-S4-PRUNE-RANGE (FR-416): the value is checked as the key is, tree unchanged."""
    workspace = _workspace(tmp_path)
    name = _recipe(workspace, body)
    before = _snapshot(workspace.root)
    with pytest.raises(StorageError, match="keep_last|delete_steps"):
        free_space(workspace.root, name, apply=True)
    assert _snapshot(workspace.root) == before


# ------------------------------------------------------------------ R3 what 0.30.0 did


def test_the_preview_protected_files_and_submitted_refusal_are_those_of_030(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): preview, a record's file and SUBMITTED as in 0.30.0."""
    workspace = _workspace(tmp_path, protect_step=7)
    name = _recipe(workspace, "delete_steps = [5, 9]\n")
    recipe = workspace.root / MANAGEMENT_DIR / f"{name}.toml"
    recipe.write_text(
        recipe.read_text(encoding="utf-8").replace('["6001"]', '"all"'), encoding="utf-8"
    )
    before = _snapshot(workspace.root / "sims")
    preview = free_space(workspace.root, name)
    assert _snapshot(workspace.root / "sims") == before
    assert preview["applied"] is False and _only_step(preview)["delete_steps"] == [5, 9]
    assert "6002" in _only_step(preview)["refused"]
    entry = free_space(workspace.root, name, apply=True)
    (point,) = _only_step(entry)["points"]
    assert [s for s in range(5, 10) if s in _steps(workspace)] == [7]
    assert point["protected"] == ["sims/sim_6001/datapoints/DP-1/loads_iteration=7.txt"]
    assert point["deleted_steps"] == [5, 6, 7, 8, 9]
    assert (workspace.sim_dir("6002") / "datapoints" / "DP-1" / "loads_iteration=1.txt").is_file()
    assert read_storage_calls(workspace.root)[-1]["applied"] is True


def test_the_recorded_call_carries_the_stated_key_in_its_step_entry(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): the step entry states keep_last or delete_steps."""
    workspace = _workspace(tmp_path)
    free_space(workspace.root, _recipe(workspace, "keep_last = 12\n"), apply=True)
    free_space(workspace.root, _recipe(workspace, "delete_steps = [1, 3]\n", name="m2"))
    first, second = read_storage_calls(workspace.root)
    assert first["steps"][0]["keep_last"] == 12 and "delete_steps" not in first["steps"][0]
    assert second["steps"][0]["delete_steps"] == [1, 3] and "keep_last" not in second["steps"][0]


# ------------------------------------------------------------------ R4 the post refusal


def _refusal(workspace: CampaignWorkspace, step: int) -> str | None:
    expected = {step: [_point(workspace) / f"loads_iteration={step}.txt"]}
    return pruned_step_refusal(
        workspace.sim_dir("6001"), RUN, expected, product="series", window=(1, STEPS)
    )


def test_a_later_post_refusal_says_what_the_call_kept_not_the_last_step(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): "the last 12 steps" or "every step outside 5 to 9"."""
    workspace = _workspace(tmp_path)
    free_space(workspace.root, _recipe(workspace, "keep_last = 12\n"), apply=True)
    text = _refusal(workspace, 3)
    assert text is not None and text.startswith(storage_module.STEP_EXPORTS_PRUNED)
    assert "which kept the last 12 steps of each export only." in text
    assert "the last step" not in text
    other = _workspace(tmp_path / "range")
    free_space(other.root, _recipe(other, "delete_steps = [5, 9]\n"), apply=True)
    text = _refusal(other, 6)
    assert text is not None and "which kept every step outside 5 to 9 of each export." in text
    assert "last step" not in text and "last 12" not in text
    assert _refusal(other, 4) is None, "a step no call deleted is left to the caller's own rule"


# ------------------------------------------------------------------ R5 nothing stated


def test_a_table_that_states_neither_key_deletes_and_records_what_0360_did(tmp_path):
    """P0370-S4-PRUNE-RANGE (FR-416): all but the last step, no new key in entry or message."""
    workspace = _workspace(tmp_path)
    entry = free_space(workspace.root, _recipe(workspace), apply=True)
    assert _steps(workspace) == [STEPS] and _steps(workspace, "loads_sloads") == [SLOAD_STEPS]
    step = _only_step(entry)
    assert set(step) == {"mode", "points", "refused", "products_json"}
    (point,) = step["points"]
    assert [item["step"] for item in point["kept"]] == [SLOAD_STEPS, STEPS] or [
        item["step"] for item in point["kept"]
    ] == [STEPS, SLOAD_STEPS]
    assert point["deleted_steps"] == list(range(1, STEPS))
    text = _refusal(workspace, 3)
    assert text is not None and "which kept the last step of each export only." in text


def test_the_command_line_summary_says_what_each_table_keeps(tmp_path, capsys):
    """P0370-S4-PRUNE-RANGE (FR-416): the printed line names the last K steps or the range."""
    workspace = _workspace(tmp_path)
    for body, words in (
        ("keep_last = 12\n", "the last 12 steps of each export kept"),
        ("delete_steps = [5, 9]\n", "every step outside 5 to 9 of each export kept"),
        ("", "the last step of each export kept"),
    ):
        name = _recipe(workspace, body)
        capsys.readouterr()
        code = matrix_cli.main(["free-space", name, "--workspace", str(workspace.root), "--list"])
        out = capsys.readouterr().out
        assert code == 0 and words in out, out
    assert "kept (step 30)" in out or "kept (last step 30)" in out
