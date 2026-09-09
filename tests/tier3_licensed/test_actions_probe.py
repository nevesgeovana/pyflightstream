"""The action re-read probe's verdict is recorded where a reader meets the command.

GOAL-012 item 7b, PFS-2031.08. ``matriz_actions.fs`` was run on 26.123
through ``pyfs-matrix run``; this module reads what the run left in the
row's simulation folder, derives the verdict the same way the probe module
does, and asserts that the committed report and the command database entry
of ``SET_NEW_UNSTEADY_SOLVER_ACTION`` state that verdict and no other. It
asks the files, never the report, for the measurement.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier3_licensed import actions_probe

pytestmark = pytest.mark.needs_flightstream

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MATRIX = "matriz_actions"
COMMAND = "SET_NEW_UNSTEADY_SOLVER_ACTION"
BUILD = "26.123"


def _probe_record():
    records = [
        record
        for record in CampaignWorkspace(HERE).read_manifest()
        if record.sim_id == actions_probe.PROBE_POL and record.matrix_stem == MATRIX
    ]
    assert records, f"no record of {MATRIX}.fs row {actions_probe.PROBE_POL}; run it first"
    return records[-1]


def test_the_script_action_reread_verdict_is_recorded():
    record = _probe_record()
    assert record.status in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER), record.error
    assert record.fs_version_requested == BUILD

    measured = actions_probe.verdict()
    assert measured["invocations"] > 0, measured["meaning"]
    assert measured["verdict"] in ("YES", "NO"), measured

    # The committed report quotes the verdict the files give.
    reports = sorted(REPO.glob("reports/RPT-*_script-action-reread*.md"))
    assert reports, "no committed report of the probe under reports/"
    text = reports[-1].read_text(encoding="utf-8")
    assert f"Verdict: {measured['verdict']}" in text, f"{reports[-1].name} states another verdict"
    assert f"Build: {BUILD}" in text
    assert f"Invocations: {measured['invocations']}" in text

    # And the database entry carries it on the build that was probed.
    database = REPO / "src" / "pyflightstream" / "commands" / "unsteady_solver.yaml"
    entry = yaml.safe_load(database.read_text(encoding="utf-8"))[COMMAND]
    note = entry["versions"][BUILD]["note"]
    assert reports[-1].name in note, f"the {BUILD} row of {COMMAND} does not cite the report"
    assert f"re-read on every invocation: {measured['verdict']}" in note
