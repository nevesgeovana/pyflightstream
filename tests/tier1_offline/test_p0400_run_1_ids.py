"""Tier 1, 0.40.0 lane run-1: which steady rows run as one warm job (``_ids``).

The one-row rate matrix of the 0.24.0 rotation tests, run through ``run_matrix`` with a
stub standing in for the solver.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline.test_goal024_freestream_rotation import RECIPES, _rate_matrix
from tests.tier1_offline.test_matrix_run import WRITES_EVERY_EXPORT, CountingStub, converged


def _free_stream_words(text: str) -> list[str]:
    line = next(line.strip() for line in text.splitlines() if line.startswith("SET_FREESTREAM"))
    return line.split()


def test_p0400_a_steady_row_sweeping_a_body_rate_runs_one_point_per_rate(tmp_path):
    """P0400-RATE-SWEEP-ONE-JOB (PFS-2104.044): ``pitch_rate:sweep`` over 2 and 4 deg/s.

    The row ran as one warm job whose free stream was set once, at the first point's rate,
    and every later point was recorded under its own rate. Each point now has its own
    script, whose SET_FREESTREAM ROTATION turns at that point's rate.
    """
    workspace, matrix = _rate_matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
        values="2.0,4.0",
    )
    records = run_matrix(
        matrix,
        workspace,
        name="turning",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert [r.run_id.rsplit("/", 1)[-1] for r in records] == [
        "M200RE230AL+000Q+020",
        "M200RE230AL+000Q+040",
    ]
    scripts = sorted((workspace.sim_dir("3207") / "scripts").glob("*.txt"))
    assert len(scripts) == 2, scripts
    rates = []
    for script in scripts:
        words = _free_stream_words(script.read_text(encoding="utf-8"))
        assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
        rates.append(float(words[4]) * 360.0 / 60.0)
    assert sorted(rates) == pytest.approx([2.0, 4.0])
