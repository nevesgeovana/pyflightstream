"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.results import (
    REDUCTION_CODES,
    REDUCTION_WINDOW_CODES,
    parse_force_distributions,
    parse_loads,
    parse_off_body_streamlines,
    parse_surface_sections,
    to_csv,
    to_table,
    write_table,
)
from pyflightstream.results.core import MalformedOutputError

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _unsteady(text: str) -> str:
    """The same export printed by an unsteady run: only the mode line moves."""
    moved, count = re.subn(r"(Solver mode:\s+)Steady", r"\1Unsteady", text)
    assert count == 1, "the fixture must print exactly one steady solver mode"
    return moved


# --- PFS-2105.043 and PFS-2105.046: an unsteady export is its last time step ---


def test_p0400_results_a_recorded_unsteady_loads_export_is_labelled_last_step(tmp_path):
    """P0400-RESULTS (PFS-2105.043, PFS-2105.046): the recorded unsteady export, read back."""
    report = parse_loads(_fixture("loads_unsteady_26.120.txt"))
    assert report.solver_mode.strip().lower() == "unsteady", "the control: a recorded unsteady run"
    back = pd.read_csv(to_csv(report, tmp_path / "loads.csv"))
    assert set(zip(back["reduction"], back["reduction_window"], strict=True)) == {
        ("last_step", "last_time_step")
    }


def test_p0400_results_a_recorded_unsteady_sectional_export_is_labelled_last_step():
    """P0400-RESULTS (PFS-2105.043): the recorded unsteady sectional loads of 26.125."""
    frame = to_table(parse_sectional_loads(_fixture("s10_26125/sloads_26.125.txt")))
    assert set(zip(frame["reduction"], frame["reduction_window"], strict=True)) == {
        ("last_step", "last_time_step")
    }


@pytest.mark.parametrize(
    ("fixture", "parse"),
    [
        ("force_distributions_26.123.txt", parse_force_distributions),
        ("off_body_streamlines_26.123.txt", parse_off_body_streamlines),
        ("all_surface_sections_26.123.txt", parse_surface_sections),
    ],
)
def test_p0400_results_no_unsteady_solver_export_is_labelled_time_average(fixture, parse):
    """P0400-RESULTS (PFS-2105.043): force distribution, streamline and section exports."""
    steady = to_table(parse(_fixture(fixture)))
    assert set(steady["reduction"]) == {"none"}, "the control: the steady export"
    frame = to_table(parse(_unsteady(_fixture(fixture))))
    assert set(zip(frame["reduction"], frame["reduction_window"], strict=True)) == {
        ("last_step", "last_time_step")
    }


def test_p0400_results_the_last_step_tokens_are_appended_and_paired(tmp_path):
    """P0400-RESULTS (PFS-2105.043): appended codes, and each token refuses another partner."""
    assert REDUCTION_CODES["last_step"] == 3
    assert REDUCTION_WINDOW_CODES["last_time_step"] == 3
    for reduction, window in (("last_step", "not_printed"), ("time_average", "last_time_step")):
        frame = pd.DataFrame(
            {
                "CL": [0.4],
                "data_origin": ["raw"],
                "reduction": [reduction],
                "reduction_window": [window],
            }
        )
        with pytest.raises(MalformedOutputError, match="last_step with last_time_step"):
            write_table(frame, tmp_path / f"{reduction}.csv")
