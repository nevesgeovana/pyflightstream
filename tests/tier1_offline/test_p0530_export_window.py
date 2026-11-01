"""Tier 1: the far-field export_type "export_window" (0.53.0).

A ``[[farfields]]`` entry at export_window exports the far field at every step of
the window the row states with EXPORT_UNSTEADY_LAST_ITER or EXPORT_UNSTEADY_LAST_REV,
one stamped file per step, and post writes the per-step products. A row without
that window, or a steady row, warns and skips the entry; last_revs and last_steps
are a writing error with it.
"""

from __future__ import annotations

import csv
import runpy
from typing import cast

import numpy as np
import pytest

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import build_script, row_outputs
from pyflightstream.cases.workflows._farfield import farfield_export_windows
from pyflightstream.script import Script
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _FFPROOF_PLAN___LATTICE,
    _ffproof_plan___unsteady,
)

LAST_ITER = "EXPORT_UNSTEADY_LAST_ITER"
LAST_REV = "EXPORT_UNSTEADY_LAST_REV"
SCRIPT_FILE = "actions/pfs_unsteady_exports.txt"
PROGRAM = "actions/pfs_unsteady_actions.py"


def _window_entries(export_type: str = "export_window") -> list[dict]:
    return [
        {"variant": "plane", "export_type": export_type, "spacing_bref": 0.25},
        {"variant": "power", "export_type": export_type, **dict(_FFPROOF_PLAN___LATTICE, m_max=2)},
    ]


def _fixed_wing(tmp_path, **variables):
    case = _ffproof_plan___unsteady(tmp_path, _window_entries())
    merged = {**case.variables, "TIME_ITERATIONS": "8", **variables}
    case = case.model_copy(
        update={
            "variables": merged,
            "pproc": PprocSpec.model_validate({"farfields": _window_entries()}),
        }
    )
    return case.model_copy(update={"outputs": row_outputs(case, "unsteady")})


@pytest.mark.requirement("FR-3430")
def test_p0530_fw_each_window_step_exports_the_far_field(tmp_path):
    """LAST_ITER: 4 on an 8 step row exports the far field at steps 5 to 8, nowhere else."""
    from pyflightstream.run._actions_counter import stage_counter

    case = _fixed_wing(tmp_path, **{LAST_ITER: "4"})
    script = Script("26.124")
    build_script(case, script)
    for name, payload in script.pending_input_files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    (tmp_path / SCRIPT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / SCRIPT_FILE).write_text("", encoding="utf-8")
    assert stage_counter(tmp_path, script, case, "26.124", {}) is not None
    exported = []
    for step in range(1, 10):
        assert runpy.run_path(str(tmp_path / PROGRAM))["main"]() == 0
        text = (tmp_path / SCRIPT_FILE).read_text() if (tmp_path / SCRIPT_FILE).exists() else ""
        if "_farfield_survey.txt" in text:
            exported.append(step)
    assert exported == [5, 6, 7, 8]


@pytest.mark.requirement("FR-3430")
def test_p0530_fw_rotor_row_windows_in_steps_and_in_turns():
    """LAST_ITER: 9 is the last nine steps; LAST_REV: 1 is one turn (36 steps) of the clock."""
    from tests.tier1_offline.test_regression_workflow_emission import (
        _cases_workflows_clock___two_speeds,
    )

    spec = PprocSpec.model_validate(
        {"farfields": [{"variant": "plane", "export_type": "export_window"}]}
    )
    steps = _cases_workflows_clock___two_speeds(**{LAST_ITER: "9"})
    turns = _cases_workflows_clock___two_speeds(**{LAST_REV: "1"})
    assert farfield_export_windows(steps.model_copy(update={"pproc": spec})) == (
        (64, 72, "farfield_probes"),
    )
    assert farfield_export_windows(turns.model_copy(update={"pproc": spec})) == (
        (37, 72, "farfield_probes"),
    )
    full = steps.model_copy(update={"pproc": spec})
    assert any(
        name.endswith("_farfield_survey.txt") for name in row_outputs(full, "unsteady_rotor")
    )


@pytest.mark.requirement("FR-3430")
def test_p0530_fw_a_row_without_the_window_warns_and_skips(tmp_path):
    """No LAST_ITER or LAST_REV (AFTER_ITER alone does not count): no window, no refusal."""
    for variables in ({}, {"EXPORT_UNSTEADY_AFTER_ITER": "2"}):
        case = _fixed_wing(tmp_path, **variables)
        assert farfield_export_windows(case) == ()
        build_script(case, Script("26.124"))


@pytest.mark.requirement("FR-3430")
def test_p0530_fw_a_steady_row_skips_the_entry(tmp_path):
    from tests.tier1_offline.test_regression_farfield_interfaces import (
        _farfield_plan___script,
        _p0450_rotor_case,
    )

    case = _p0450_rotor_case(tmp_path, [{"variant": "plane"}], "steady")
    spec = PprocSpec.model_validate(
        {"farfields": [{"variant": "plane", "export_type": "export_window"}]}
    )
    script = _farfield_plan___script(case.model_copy(update={"pproc": spec}))
    assert not script.farfield_layout


@pytest.mark.parametrize("key", ["last_steps", "last_revs"])
@pytest.mark.requirement("FR-3430")
def test_p0530_fw_last_steps_and_last_revs_are_a_writing_error(tmp_path, key):
    case = _fixed_wing(tmp_path, **{LAST_ITER: "4"})
    spec = PprocSpec.model_validate(
        {"farfields": [{"variant": "plane", "export_type": "export_window", key: 2}]}
    )
    with pytest.raises(CampaignConfigError, match=key):
        farfield_export_windows(case.model_copy(update={"pproc": spec}))


@pytest.mark.requirement("FR-3430")
def test_p0530_fw_post_writes_the_far_field_products_of_every_step(tmp_path):
    """A recorded run of two window steps gives a wake row for each step, not the last only."""
    from pathlib import Path

    from pyflightstream.post.farfield_products import farfield_products
    from tests.tier1_offline.test_regression_farfield_numerics import _p0470_helical_wake
    from tests.tier1_offline.test_regression_farfield_products import (
        _p0470_post_rotor_wake,
        _p0470_wake_vtk,
    )

    lines, values = _p0470_helical_wake(
        2, gamma=np.ones(4), radii=np.linspace(0.2, 1.0, 5), v=10, omega=100, turns=2
    )
    first = [line + np.array([3.0, 0.0, 2.0]) for line in lines]
    _, _, ctx = _p0470_post_rotor_wake(tmp_path, first, values, rotor=True)
    ctx.pproc = PprocSpec.model_validate(
        {"farfields": [{"variant": "wake", "export_type": "export_window"}]}
    )
    record = ctx.record_of["point"]
    record.recipe = "unsteady_rotor"
    record.stopped_at = {"step": 2}
    record.export_window = {"first_step": 1, "time_iterations": 2}
    for step in (1, 2):
        (tmp_path / f"point_iteration={step}.vtk").write_text("surface", encoding="utf-8")
        (tmp_path / f"point_iteration={step}_wakes.vtk").write_text(
            _p0470_wake_vtk(first, values), encoding="utf-8"
        )
    farfield_products(cast("object", ctx))
    steps = set()
    for path in Path(tmp_path, "post/farfield").glob("*_trefftz_instant.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        steps |= {row["STEP"] for row in rows}
    assert steps == {"1", "2"}
