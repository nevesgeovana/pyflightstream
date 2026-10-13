"""P0400 review: probes must use configured timeouts and prove continued execution."""

from pathlib import Path

import pytest

from pyflightstream.options import OptionError, get_option, option_context
from pyflightstream.qa import ProbeOutcome, probe_version
from tests.tier1_offline.test_qa_probes import FakeFlightStream, run_pilot


@pytest.mark.parametrize("explicit,expected", [(None, 7.0), (11.0, 11.0)])
def test_p0400_probe_timeout_uses_option_unless_explicit(tmp_path, explicit, expected):
    seen = []

    class TimedSolver(FakeFlightStream):
        def run_script(self, script_path, working_dir, timeout_s=None):
            seen.append(timeout_s)
            return super().run_script(script_path, working_dir, timeout_s)

    with option_context("qa.probe_timeout_s", 7.0):
        kwargs = {} if explicit is None else {"timeout_s": explicit}
        probe_version("26.120", workroot=tmp_path, executor=TimedSolver(), commands=[], **kwargs)
    assert seen == [expected]


def test_p0400_unused_case_timeout_is_not_advertised():
    with pytest.raises(OptionError, match="no option is registered"):
        get_option("qa.case_timeout_s")


def test_p0400_missing_end_sentinel_cannot_verify_an_observed_effect(tmp_path: Path):
    class MissingEnd(FakeFlightStream):
        def _say(self, message):
            if message == "PYFS_PROBE_END_PRINT":
                return
            super()._say(message)

    results, _ = run_pilot(tmp_path, MissingEnd(), commands=["PRINT"])
    result = results["PRINT"]
    assert result.outcome is ProbeOutcome.BROKEN
    assert "END sentinel" in result.detail


def test_p0400_section_export_requires_a_filename_and_is_not_verified():
    from pyflightstream.commands import CommandRegistry, Status

    entry = CommandRegistry.load().commands["EXPORT_SURFACE_SECTIONS"]
    assert [(arg.name, arg.own_line) for arg in entry.args] == [
        ("index", False),
        ("filename", True),
    ]
    assert entry.versions["26.125"].status is Status.DOCUMENTED
