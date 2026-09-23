"""Since 0.26.0 the post always warns; check_frozen opts into refusing averages."""

from __future__ import annotations

import pyflightstream.post.products as products_module
import pyflightstream.workspace as workspace_module
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run.cli import _build_parser, main
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_b01_frozen_solve import (
    _cut_the_log_mid_table,
    _post_workspace,
    _products_manifest,
)

AVERAGE = "probes/AL-020_time_average.csv"


def test_by_default_the_log_warns_and_a_frozen_average_is_published(tmp_path):
    """Row 2413 freezes at step 60, and its average is written all the same."""
    workspace = _post_workspace(tmp_path, 2413, (60, 61))
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert AVERAGE in manifest["products"], manifest["skipped"]
    assert not [key for key in manifest["skipped"] if "frozen" in manifest["skipped"][key]]


def test_asking_for_the_check_refuses_that_same_average(tmp_path):
    """The same campaign, the same freeze, with the reading asked for."""
    workspace = _post_workspace(tmp_path, 2413, (60, 61))
    write_campaign_products(workspace, check_frozen=True)
    manifest = _products_manifest(workspace)
    assert AVERAGE not in manifest["products"], "the check was asked for and did not refuse"
    assert "step 60" in manifest["skipped"][AVERAGE], manifest["skipped"][AVERAGE]


def test_a_log_that_cannot_be_read_never_ends_the_post_either_way(tmp_path):
    """The defect this release exists for is not behind the flag.

    `pyfs-matrix collect` died with a traceback and `post` wrote nothing when a
    residual block ended mid-write. Both modes read the log tolerantly. Neither raises.
    """
    for asked in (False, True):
        workspace = _post_workspace(tmp_path / str(asked), 2411, (60, 61))
        _cut_the_log_mid_table(workspace)
        write_campaign_products(workspace, check_frozen=asked)
        manifest = _products_manifest(workspace)
        assert "probes/AL-020_plots.csv" in manifest["products"], manifest["skipped"]


def test_a_frozen_failed_point_is_still_admitted_when_the_check_is_off(tmp_path):
    """The architect lens of the closing round, 2026-09-22, on the opt-in itself.

    A FAILED_DIVERGED record is admitted to the post stage when its log PROVES
    the freeze, so its histories, instants and pre-freeze averages are written.
    Gating that admission behind the flag EXCLUDED every frozen failure by
    default, which is the opposite of "nothing is refused unless asked": the
    reading that admits a point is not the reading that refuses its averages.
    """
    workspace = _post_workspace(tmp_path, 2413, (58, 59), status=RunStatus.FAILED_DIVERGED)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_plots.csv" in manifest["products"], manifest["skipped"]
    assert manifest["products"]["sections/AL-020_sections.csv"]["kind"] == "instant"


def test_both_modes_read_the_log_to_explain_doubts(tmp_path, monkeypatch):
    """Since 0.26.0 the default reads the log to warn while preserving products."""
    calls: list[object] = []

    # THE SPY TAKES WHAT THE CALLER PASSES, by name: since the closing round
    # of 0.26.0 the stage says whether the loads export reports a steady solve
    # (`steady=`), and a spy that could not take it made this test red before
    # it asserted anything (the QA read of that round's fixes).
    def spy(log_path, *, steady=False):
        calls.append((log_path, steady))
        return None

    monkeypatch.setattr(products_module, "freeze_of_log", spy)
    workspace = _post_workspace(tmp_path / "off", 2413, (60, 61))
    write_campaign_products(workspace)
    assert calls, "since 0.26.0 the native log is read to warn by default"
    assert all(steady is False for _path, steady in calls), "an unsteady fixture was called steady"
    calls.clear()
    workspace = _post_workspace(tmp_path / "on", 2413, (60, 61))
    write_campaign_products(workspace, check_frozen=True)
    assert calls, "the check was asked for and the log was never judged"


def test_the_command_line_forwards_the_flag_to_the_stage(tmp_path, monkeypatch):
    """`pyfs-matrix post` passes what it was told, and nothing else, to the stage."""
    seen: list[bool] = []

    def stage(ws, *, overwrite, archive, matrix_stem, check_frozen=False):
        seen.append(check_frozen)
        return []

    # A STAGE REGISTERED BEFORE 0.25.1 takes no `check_frozen` at all, and the
    # bare command must still run it: forwarding the flag unconditionally
    # raised TypeError before any stage ran (the fourth independent reading).
    def older_stage(ws, *, overwrite, archive, matrix_stem):
        seen.append("older")
        return []

    monkeypatch.setattr(workspace_module, "post_stages", lambda: [stage, older_stage])
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    assert main(["post", "--workspace", str(workspace.root)]) == 0
    assert seen == [False, "older"], seen
    seen.clear()
    monkeypatch.setattr(workspace_module, "post_stages", lambda: [stage])
    assert main(["post", "--workspace", str(workspace.root), "--check-frozen"]) == 0
    assert seen == [True], seen
    # `collect` parses the same switch to the same destination, so the one
    # closure it hands the collector forwards the same way.
    parser = _build_parser()
    assert parser.parse_args(["collect", "--workspace", str(workspace.root)]).check_frozen is False
    assert (
        parser.parse_args(
            ["collect", "--workspace", str(workspace.root), "--check-frozen"]
        ).check_frozen
        is True
    )
