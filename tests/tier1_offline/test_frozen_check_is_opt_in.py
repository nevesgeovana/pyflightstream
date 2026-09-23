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

from pyflightstream.post.products import write_campaign_products
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
