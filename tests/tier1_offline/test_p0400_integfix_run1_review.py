"""Tier 1, 0.40.0 integration fix: the run-1 review findings R1-004 and R1-007 on the merged tree.

R1-007 (PFS-2095.026): an invalid native_log access (``{sim.missing}``, ``{sim[bad]}``) is
refused by name. In the integrated tree the profile reader refuses it when the profile is
read (the item's acceptance), so collect stops before any point is touched, and the shared
per-point formatter still turns any formatting failure into a refusal rather than a
traceback. No solver runs.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import cli
from pyflightstream.run._batch_collect import _formatted
from pyflightstream.run._collect_logs import _profile_glob
from pyflightstream.run.collect import collect_once
from tests.support_helpers import no_sleep as _no_sleep
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import _work_dir, _write_profile
from tests.tier1_offline.test_p0350_batch_collect import _workspace as _grouped_workspace

PLACEHOLDERS = ["{sim.missing}", "{sim[bad]}", "{Sim}"]


def _workspace_with_profile(tmp_path, placeholder, grouped):
    if grouped:
        workspace, _job_dir, _staged = _grouped_workspace(tmp_path, "batch", written=())
    else:
        workspace, sim = _submitted_workspace(
            tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt")
        )
        (_work_dir(workspace, sim) / "loads.txt").write_text("data", encoding="utf-8")
    _write_profile(
        workspace, '[log]\nexport_log = false\nnative_log = "FTS' + placeholder + '.l*"\n'
    )
    return workspace


@pytest.mark.parametrize("placeholder", PLACEHOLDERS)
@pytest.mark.parametrize("grouped", [False, True])
def test_p0400_invalid_native_log_access_is_refused_before_any_point(
    tmp_path, placeholder, grouped
):
    """P0400-NATIVE-LOG-READ-REFUSAL (PFS-2095.026): named, and nothing recorded.

    The profile reader refuses a native_log placeholder outside {work_dir}, {batch}, {sim}
    and {point}; collect, ordinary or grouped, raises that named refusal and leaves the
    manifest as it found it, so a corrected profile collects the same points again.
    """
    workspace = _workspace_with_profile(tmp_path, placeholder, grouped)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(InputArtifactError) as raised:
        collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert "native_log" in str(raised.value) and placeholder in str(raised.value)
    assert workspace.manifest_path.read_bytes() == before


@pytest.mark.parametrize("placeholder", ["{sim.missing}", "{sim[bad]}"])
def test_p0400_invalid_native_log_access_cli_is_a_message_not_a_traceback(
    tmp_path, placeholder, capsys
):
    """P0400-NATIVE-LOG-CLI (PFS-2095.026): ``collect`` prints the refusal and exits 2."""
    workspace = _workspace_with_profile(tmp_path, placeholder, grouped=False)
    status = cli.main(
        ["collect", "--workspace", str(workspace.root), "--interval", "0.001", "--no-post"]
    )
    captured = capsys.readouterr()
    assert status == 2
    assert "native_log" in captured.err and placeholder in captured.err
    # The banner's art says "Traceback"; a real one says "most recent call last".
    assert "most recent call last" not in captured.err + captured.out


@pytest.mark.parametrize("pattern", ["FTS{sim.missing}.l*", "FTS{sim[bad]}.l*", "FTS{nope}.l*"])
def test_p0400_shared_profile_glob_formatter_refuses_every_failure(pattern):
    """P0400-PROFILE-GLOB-FORMATTER (PFS-2095.026): one formatter, no exception escapes.

    AttributeError and TypeError join KeyError, IndexError and ValueError: the per-record
    formatter returns the refusal naming the profile key, and the grouped one, which calls
    it, returns None, for a pattern that reached collection without the read-time check.
    """
    glob, refusal = _profile_glob("native_log", pattern, {"sim": "9001", "point": "p"})
    assert glob is None and "native_log" in refusal and pattern in refusal
    job = {"values": {"sim": "9001", "batch": "b1"}}
    assert _formatted(pattern, job) is None  # type: ignore[arg-type]
