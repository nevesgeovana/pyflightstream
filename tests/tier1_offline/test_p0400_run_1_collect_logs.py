"""Tier 1, 0.40.0 lane run-1: how collect reads a point's solver log (the HPC profile's globs).

The submitted workspace of the collect tests and a hand-written profile; no solver runs.
"""

from __future__ import annotations

import pytest

from pyflightstream.run.collect import collect_once
from tests.support_helpers import no_sleep as _no_sleep
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import _work_dir, _write_profile
from tests.tier1_offline.test_p0350_batch_collect import _workspace as _grouped_workspace


def test_p0400_a_native_log_placeholder_no_point_fills_is_a_refusal_not_a_traceback(tmp_path):
    """P0400-NATIVE-LOG-PLACEHOLDER (PFS-2095.026): ``native_log = "FTS{Sim}.l*"``, a typo.

    The profile reader does not read native_log's placeholders, and the per-record collect
    formatted the glob with ``{sim}`` and ``{point}`` alone and let the KeyError out, so
    collect ended in a traceback. The point is now refused naming the placeholder and what
    the point fills.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace, '\n[log]\nexport_log = false\nnative_log = "FTS{Sim}.l*"\n')
    work = _work_dir(workspace, sim)
    (work / "loads.txt").write_text("data", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.failed) == 1, report
    detail = report.failed[0].detail
    assert "native_log" in detail and "{Sim}" in detail and "{sim}" in detail, detail


@pytest.mark.parametrize("placeholder", ["{sim.missing}", "{sim[bad]}"])
@pytest.mark.parametrize("grouped", [False, True])
def test_p0400_native_log_invalid_access_is_a_named_refusal(tmp_path, placeholder, grouped):
    """P0400-NATIVE-LOG-ACCESS: invalid attribute or index access cannot abort collection."""
    if grouped:
        workspace, _job_dir, _staged = _grouped_workspace(tmp_path, "batch", written=())
    else:
        workspace, sim = _submitted_workspace(
            tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt")
        )
        work = _work_dir(workspace, sim)
        (work / "loads.txt").write_text("data", encoding="utf-8")
    _write_profile(
        workspace,
        '[log]\nexport_log = false\nnative_log = "FTS' + placeholder + '.l*"\n',
    )
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.failed) == (2 if grouped else 1)
    assert all(
        "native_log" in entry.detail and placeholder in entry.detail for entry in report.failed
    )
