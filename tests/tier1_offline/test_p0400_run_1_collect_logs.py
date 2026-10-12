"""Tier 1, 0.40.0 lane run-1: how collect reads a point's solver log (the HPC profile's globs).

The submitted workspace of the collect tests and a hand-written profile; no solver runs.
Since 0.40.0 the profile reader refuses an unknown native_log placeholder when the profile
is read (PFS-2095.026), before any point; the invalid-access cases (``{sim.missing}``,
``{sim[bad]}``), ordinary and grouped, and the unchanged manifest are pinned in
``test_p0400_integfix_run1_review.py``. This file keeps what that one does not assert.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run.collect import collect_once
from tests.support_helpers import no_sleep as _no_sleep
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import _work_dir, _write_profile


def test_p0400_a_native_log_placeholder_no_point_fills_is_a_refusal_not_a_traceback(tmp_path):
    """P0400-NATIVE-LOG-PLACEHOLDER (PFS-2095.026): ``native_log = "FTS{Sim}.l*"``, a typo.

    The per-record collect once formatted the glob with ``{sim}`` and ``{point}`` alone and
    let the KeyError out, so collect ended in a traceback. The profile reader now refuses
    the placeholder when the profile is read, naming it and the placeholders a point fills,
    which is the remedy the reader needs.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace, '\n[log]\nexport_log = false\nnative_log = "FTS{Sim}.l*"\n')
    (_work_dir(workspace, sim) / "loads.txt").write_text("data", encoding="utf-8")
    with pytest.raises(InputArtifactError) as raised:
        collect_once(workspace, interval=0.0, sleep=_no_sleep)
    message = str(raised.value)
    assert "native_log" in message and "{Sim}" in message, message
    assert "{sim}" in message and "{point}" in message, message
