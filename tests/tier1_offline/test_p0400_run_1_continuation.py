"""Tier 1, 0.40.0 lane run-1: continuing a recorded point (RESTART).

Synthetic cases and records; no solver runs.
"""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

import tests.tier1_offline.test_restart_continuation as fr96
from pyflightstream.cases import CampaignConfigError
from pyflightstream.run._continuation import _refuse_a_field_the_stopped_run_did_not_read
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_g15_custom_freestream import field, with_field
from tests.tier1_offline.test_workflows import steady_case


def test_p0400_a_changed_units_declaration_is_refused_naming_the_point(tmp_path):
    """P0400-CONTINUATION-UNITS-NAMED (PFS-2100.015): case, point, run, both declarations.

    The refusal named neither the point nor the two declarations, so a person continuing
    a campaign could not tell which row to correct, or to what.
    """
    source = field(tmp_path)
    case = with_field(steady_case(), source).model_copy(update={"freestream_units": "SI"})
    previous = SimpleNamespace(
        run_id="c/sim_9001/AL+000",
        inputs_sha256={source.name: sha256(source.read_bytes()).hexdigest()},
        freestream_units="NATIVE",
    )
    with pytest.raises(CampaignConfigError) as refused:
        _refuse_a_field_the_stopped_run_did_not_read(case, "AL+000", previous)
    message = str(refused.value)
    for part in (repr(case.sim_id), "AL+000", "'c/sim_9001/AL+000'", "'SI'", "'NATIVE'"):
        assert part in message, (part, message)
    assert "Restore the declaration" in message and "RESTART" in message


def test_p0400_a_ran_missing_log_march_is_not_continued_as_converged():
    """P0400-RAN-MISSING-LOG-NOT-CONTINUED (PFS-2103.025): ADDITIONAL_REVS on RAN_MISSING_LOG.

    The verdict announced 'continuing a CONVERGED unsteady run' for a run whose log is
    absent, which FR-413 says is never CONVERGED by assumption, and continued it although
    the continuable set excludes it. It is now refused naming its status; the control, a
    CONVERGED march, is continued with the words it had.
    """
    verdict = fr96._fr96_converged_continuation___verdict(
        "ADDITIONAL_REVS=1", fr96._fr96_converged_continuation___record(RunStatus.RAN_MISSING_LOG)
    )
    assert not verdict.pending
    assert "RAN_MISSING_LOG" in str(verdict.said) and "CONVERGED" not in str(verdict.said)
    control = fr96._fr96_converged_continuation___verdict(
        "ADDITIONAL_REVS=1", fr96._fr96_converged_continuation___record(RunStatus.CONVERGED)
    )
    assert control.pending
    assert (
        control.said
        == f"continuing a CONVERGED unsteady run, {fr96._FR96_CONVERGED_CONTINUATION__POINT!r}, by 1 revolution(s)"  # noqa: E501
    )
