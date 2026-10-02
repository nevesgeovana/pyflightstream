"""Tier 1: the 0.35.0 command-line skeleton of the grouped run modes.

Pipeline role: quality gate on the dispatch between the per-point functions and
the grouped ones. ``--polar-sweep`` and ``--batch N`` parse on ``run`` and on
``plan``, exclude each other, and leave the default per-point mode on the very
function it always called.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-350, FR-351.

from __future__ import annotations

import argparse

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows._vocabulary import WALLTIME_VARIABLE
from pyflightstream.run._grouped import (
    grouped_case,
    planner_for,
    refuse_grouped_options,
    runner_for,
)
from pyflightstream.run.cli import main


def _default(*_args: object, **_kwargs: object) -> str:
    return "per-point"


def test_p0350_cli_fr350_fr351_the_options_parse_and_default_mode_is_unchanged(
    tmp_path, capsys
) -> None:
    """P0350-RUN-POLAR-SWEEP, P0350-RUN-BATCH: both options parse; neither leaves the default."""
    for option in (["--polar-sweep"], ["--batch", "2"]):
        # `run` parses the option and stops at its own plan gate, before any grouped code.
        assert main(["run", "none.fs", "--workspace", str(tmp_path), *option]) == 2
        assert "plan" in capsys.readouterr().err
    for command in ("run", "plan"):
        with pytest.raises(SystemExit) as stop:
            main([command, "--help"])
        assert stop.value.code == 0
        help_text = capsys.readouterr().out
        assert "--polar-sweep" in help_text and "--batch N" in help_text
    none = argparse.Namespace(polar_sweep=False, batch=None)
    assert runner_for(none, _default) is _default
    assert planner_for(none, _default) is _default


def test_p0350_cli_refusals(tmp_path, capsys) -> None:
    """P0350-RUN-POLAR-SWEEP, P0350-RUN-BATCH: the parser refuses bad combinations by name."""
    for argv, named in (
        (["--polar-sweep", "--batch", "2"], "--batch"),
        (["--batch", "0"], "--batch"),
        (["--batch", "-3"], "--batch"),
    ):
        with pytest.raises(SystemExit) as stop:
            main(["run", "none.fs", "--workspace", str(tmp_path), *argv])
        assert stop.value.code == 2
        assert named in capsys.readouterr().err
    assert refuse_grouped_options(force_rerun=None, force_rerun_all=False, sweep_csv=None) is None
    for kwargs, flag in (
        ({"force_rerun": ["2006"]}, "--force-rerun"),
        ({"force_rerun_all": True}, "--force-rerun-all"),
        ({"sweep_csv": "t.csv"}, "--sweep-csv"),
    ):
        base = {"force_rerun": None, "force_rerun_all": False, "sweep_csv": None, **kwargs}
        assert flag in (refuse_grouped_options(**base) or "")


def test_p0350_grouping_fr364_grouped_case_strips_only_the_clock() -> None:
    """P0350-RUN-BATCH: grouped_case removes WALLTIME and nothing else."""
    case = SimCase(
        sim_id="2006",
        aircraft="A",
        mach=0.2,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="m:f",
        variables={WALLTIME_VARIABLE: "4h", "OTHER": 3, "FLAG": True},
    )
    stripped = grouped_case(case)
    assert WALLTIME_VARIABLE not in stripped.variables
    assert stripped.variables == {"OTHER": 3, "FLAG": True}
    for name in SimCase.model_fields:
        if name != "variables":
            assert getattr(stripped, name) == getattr(case, name), name
    assert WALLTIME_VARIABLE in case.variables
