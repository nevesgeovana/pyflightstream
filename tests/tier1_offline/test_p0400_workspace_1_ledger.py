"""P0400-WSLEDGER: ledger diff, the activity log reader and the query API's refusals.

0.40.0 lane workspace-1. Each test is the regression of one planning node and
fails on the code before its fix.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import WorkspaceError, _make_dir_link
from pyflightstream.workspace.ledger import activity_rows, additional_rows, diff, post_log_groups
from tests.tier1_offline.test_p0350_query_history import NEXT, RUN, _record, _script, _write

pytestmark = pytest.mark.requirement("P0400-WSLEDGER")

CLUSTER = "/scratch/user/sample"


def _two_runs(tmp_path, *, script_a: str, script_b: str, cwd_a: str, cwd_b: str, folder="scripts"):
    path_a, sha_a = _script(tmp_path, f"sims/sim_2006/{folder}/a.txt", script_a)
    path_b, sha_b = _script(tmp_path, f"sims/sim_2006/{folder}/b.txt", script_b)
    rows = [
        _record(script_path=f"{folder}/a.txt", script_sha256=sha_a, cwd=cwd_a),
        _record(NEXT, script_path=f"{folder}/b.txt", script_sha256=sha_b, cwd=cwd_b),
    ]
    _write(tmp_path / "runs.json", rows)
    return tmp_path


def _scripts(root: str) -> str:
    return f'LOAD_FILE\n"{root}/inputs/geometries/wing.fsm"\nSOLVER_SET_AOA\n2\n'


def test_p0400_wsledger_a_local_and_a_cluster_run_of_one_script_do_not_differ(tmp_path):
    """P0400-WSLEDGER (PFS-2103.013): each side is normalised by its own root, either order."""
    local = tmp_path.as_posix()
    root = _two_runs(
        tmp_path,
        script_a=_scripts(local),
        script_b=_scripts(CLUSTER),
        cwd_a=f"{local}/sims/sim_2006/datapoints/DP-A0",
        cwd_b=f"{CLUSTER}/sims/sim_2006/datapoints/DP-A0",
    )
    for first, second in ((RUN, NEXT), (NEXT, RUN)):
        fields = [row["field"] for row in diff(root, first, second)]
        assert "script_comparison" not in fields, (first, fields)


def test_p0400_wsledger_a_real_change_between_two_runs_is_still_named(tmp_path):
    """P0400-WSLEDGER (PFS-2103.013): the control, a changed command is reported."""
    local = tmp_path.as_posix()
    root = _two_runs(
        tmp_path,
        script_a=_scripts(local),
        script_b=_scripts(CLUSTER).replace("\n2\n", "\n4\n"),
        cwd_a=f"{local}/sims/sim_2006/datapoints/DP-A0",
        cwd_b=f"{CLUSTER}/sims/sim_2006/datapoints/DP-A0",
    )
    rows = {row["field"]: row for row in diff(root, RUN, NEXT)}
    assert "SOLVER_SET_AOA | 2" in rows["script_comparison"]["detail"]
    assert "geometries" not in rows["script_comparison"]["detail"]
    assert ": a " in rows["script_comparison"]["detail"]
    assert ", b " in rows["script_comparison"]["detail"]
    assert "renders" not in rows["script_comparison"]["detail"]


def test_p0400_wsledger_the_recorded_script_path_is_read_in_the_simulation_folder(tmp_path):
    """P0400-WSLEDGER (PFS-2103.039): script_path is relative to the simulation folder."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (tmp_path / "sims" / "sim_2006").mkdir(parents=True)
    _make_dir_link(shared, tmp_path / "sims" / "sim_2006" / "linked")
    text = _scripts(tmp_path.as_posix())
    root = _two_runs(tmp_path, script_a=text, script_b=text, cwd_a="", cwd_b="", folder="linked")
    rows = {row["field"]: row for row in diff(root, RUN, NEXT)}
    assert "script_comparison" not in rows, rows.get("script_comparison")


def test_p0400_wsledger_a_malformed_additional_register_is_a_workspace_error(tmp_path):
    """P0400-WSLEDGER (PFS-2095.028): additional_rows raises the class it documents."""
    _write(tmp_path / "runs.json", [_record()])
    _write(tmp_path / "additional.json", {"not": "a list"})
    with pytest.raises(WorkspaceError, match="additional"):
        additional_rows(tmp_path)


def test_p0400_wsledger_a_malformed_post_log_is_a_workspace_error(tmp_path):
    """P0400-WSLEDGER (PFS-2095.028): post_log_groups raises the class it documents."""
    _write(tmp_path / "runs.json", [_record()])
    _write(tmp_path / "post" / "sample" / "post.log.json", {"records": "none"})
    with pytest.raises(WorkspaceError, match="post"):
        post_log_groups(tmp_path, "sample")


def _activity_log(tmp_path, *lines: str):
    _write(tmp_path / "runs.json", [_record()])
    log = tmp_path / "logs" / "activity.log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


GOOD = '{"timestamp": "2026-10-01T12:00:00Z", "event": "started", "stage": "run"}'


def test_p0400_wsledger_an_invalid_since_filter_is_a_workspace_error(tmp_path):
    """P0400-WSLEDGER (PFS-2095.028): an invalid filter raises the documented class."""
    with pytest.raises(WorkspaceError, match="since"):
        activity_rows(_activity_log(tmp_path, GOOD), since="yesterday")


@pytest.mark.parametrize(
    "bad",
    [
        '{"timestamp": "2026-10-01T12:05:00Z", "event": "fini',
        '["not", "an", "object"]',
        '{"timestamp": "yesterday", "event": "finished", "stage": "run"}',
    ],
    ids=["torn", "not-an-object", "non-iso-time"],
)
def test_p0400_wsledger_one_bad_activity_line_is_named_and_the_rest_is_read(tmp_path, bad):
    """P0400-WSLEDGER (PFS-2081.25): a torn or malformed line warns; the query still answers."""
    root = _activity_log(tmp_path, GOOD, bad)
    with pytest.warns(PyflightstreamWarning, match="line 2"):
        rows = activity_rows(root)
    assert [row["event"] for row in rows] == ["started"]


def test_p0400_wsledger_a_sim_id_is_not_read_inside_a_longer_one(tmp_path):
    """P0400-WSLEDGER (PFS-2094.043): sims 20 does not select the events of sim 20-b."""
    root = _activity_log(
        tmp_path,
        '{"timestamp": "2026-10-01T12:00:00Z", "event": "started", "detail": "sims/sim_20/x"}',
        '{"timestamp": "2026-10-01T12:01:00Z", "event": "failed", "detail": "sims/sim_20-b/x"}',
        '{"event": "suffix", "detail": "sims/sim_prefix-sim_20/x"}',
    )
    assert [row["event"] for row in activity_rows(root, sims=["20"])] == ["started"]
    assert [row["event"] for row in activity_rows(root, sims=["20-b"])] == ["failed"]


def test_p0400_wsledger_explicit_sim_ids_win_over_mentions_in_details(tmp_path):
    """P0400-WSLEDGER (PFS-2094.043): structured simulation identity wins over text."""
    root = _activity_log(
        tmp_path,
        '{"sim_id": "20-b", "event": "other", "detail": "copied from sim_20/x"}',
        '{"sims": ["20-b"], "event": "batch", "detail": "copied from sim_20/x"}',
    )
    assert activity_rows(root, sims=["20"]) == []
