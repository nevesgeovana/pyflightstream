"""The native-log freeze check is OPT-IN since 0.25.1, by the owner's decision.

HER DECISION, 2026-09-22, and the reason it is hers: the check reads each point's native log
while posting, and eight rounds of review on the precision of one corner -- which steps an
INTERPOLATED average reads -- kept finding the guard wrong in one direction or the other. She
chose to ship the release with the reading off by default and to re-discuss the architecture in
0.26.0.

WHAT IS LOST BY DEFAULT, stated here because a test is where a claim is kept honest: the
averages of a FROZEN solve are published like any other. A frozen solve prints plausible
numbers, so no product says they are wrong. `--check-frozen` buys the refusals back.

WHAT IS NOT OPTIONAL: the crash. A log that cannot be read never ends the post. Off, it is not
read at all; on, it is read tolerantly and the steps it could not read are named.
"""

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


def test_by_default_the_log_is_not_read_and_a_frozen_average_is_published(tmp_path):
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
    residual block ended mid-write. Off, the log is not read; on, it is read
    tolerantly. Neither raises.
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


def test_with_the_check_off_a_successful_point_never_has_its_log_judged(tmp_path, monkeypatch):
    """The QA lens of the closing round: publication alone is satisfied by a read
    whose result is discarded, so the reading itself is observed.

    A spy stands in for `freeze_of_log`, the one helper the three post-stage
    readings go through. With the check off and a successful record it is never
    called; with the check on it is.
    """
    calls: list[object] = []

    def spy(log_path):
        calls.append(log_path)
        return None

    monkeypatch.setattr(products_module, "freeze_of_log", spy)
    workspace = _post_workspace(tmp_path / "off", 2413, (60, 61))
    write_campaign_products(workspace)
    assert calls == [], "the check was off and the log was judged for a freeze anyway"
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
