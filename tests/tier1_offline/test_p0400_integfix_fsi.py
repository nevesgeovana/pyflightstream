"""Tier 1, 0.40.0 integration fixes of the FSI lane."""

from __future__ import annotations

import pytest

from pyflightstream.cases import fsi_workspace
from pyflightstream.cases.workflows import build_script, effective_fsi_config
from pyflightstream.cases.workflows._clock import _rotor_clock
from pyflightstream.script import Script
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case


@pytest.fixture(autouse=True)
def rotor_route_open(monkeypatch):
    """Open the unsteady_rotor FSI route, as the typed-setup wiring tests do."""
    guard = fsi_workspace.fsi_workflow_refusal
    monkeypatch.setattr(
        fsi_workspace,
        "fsi_workflow_refusal",
        lambda workflow: None if workflow == "unsteady_rotor" else guard(workflow),
    )


def test_p0400_unsteady_route_stages_the_resolved_time_increment(tmp_path):
    """P0400-FSI-DT (PFS-2088.004): an unset time_increment_s is staged as the solver clock's dt.

    Without it the structural callback schedules on the loads header's
    three-decimal print of dt, off by up to 13 percent at 0.0035 s.
    """
    case = coupled_case(tmp_path)
    assert case.fsi is not None
    unset = case.model_copy(update={"fsi": case.fsi.model_copy(update={"time_increment_s": None})})
    resolved = _rotor_clock(unset).delta_time_s
    build_script(unset, Script("26.124"))  # the wiring accepts the unset field
    staged = effective_fsi_config(unset)
    assert staged is not None
    assert staged.time_increment_s == resolved
    assert '"time_increment_s": ' in staged.model_dump_json(indent=2)
    # a stated value is left as the row wrote it
    stated = effective_fsi_config(case)
    assert stated is not None and stated.time_increment_s == case.fsi.time_increment_s
