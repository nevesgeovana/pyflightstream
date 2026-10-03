"""Regression coverage for grouped walltime and matrix sweep refusals in 0.35.1."""

from __future__ import annotations

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix
from pyflightstream.run._batch_split import (
    JobSplit,
    Overheads,
    best_walltime_s,
    job_estimate,
    job_walltime,
    walltime_text,
)
from tests.tier1_offline.test_p0350_batch_plan import _fixture
from tests.tier1_offline.test_p0350_batch_split import _unit


def _mixed_split(seconds=(3600.0, 3600.0)):
    return JobSplit(
        (
            _unit(
                "2001",
                1,
                0.0,
                points=2,
                cell_s=7200.0,
                cell_text="2h",
                seconds=(None, None),
                best=False,
            ),
            _unit("2002", 2, 0.0, points=2, seconds=seconds),
        )
    )


def _estimate(split):
    return job_estimate(split, Overheads(0.0, 0.0, 0.0, "synthetic zero overheads"))[0]


def test_p0351_walltime_no_false_short_when_the_estimate_is_the_cells():
    """P0351-WALLTIME-NO-FALSE-SHORT (FR-364): cells are not their own estimate evidence."""
    split = JobSplit(
        tuple(
            _unit(
                sim,
                order,
                0.0,
                points=2,
                cell_s=14400.0,
                cell_text="4h",
                seconds=(None, None),
                best=False,
            )
            for order, sim in enumerate(("2001", "2002"), 1)
        )
    )
    estimate = _estimate(split)
    assert estimate == 4 * 14400
    assert job_walltime(split, estimate, max_walltime_s=None) == (
        57600,
        "matrix",
        None,
        None,
        [],
        None,
    )


def test_p0351_walltime_best_rows_add_their_estimate():
    """P0351-WALLTIME-BEST-MIX (FR-364): each BEST row adds its own priced estimate."""
    split = _mixed_split()
    seconds, source, *_ = job_walltime(split, _estimate(split), max_walltime_s=None)
    assert seconds == 14400 + best_walltime_s(7200.0, 1200.0) == 24600
    assert walltime_text(seconds) == "410m"
    assert source == "matrix"


def test_p0351_walltime_unestimated_best_row_asks_the_maximum():
    """P0351-WALLTIME-BEST-MIX (FR-364): one unknown BEST point asks the profile maximum."""
    split = _mixed_split((3600.0, None))
    assert job_walltime(split, _estimate(split), max_walltime_s=36000) == (
        36000,
        "max_walltime",
        None,
        None,
        ["no estimate for m/sim_2002/p1; the job asks the profile's max_walltime."],
        None,
    )


def test_p0351_walltime_unestimated_best_row_refuses_without_maximum():
    """P0351-WALLTIME-BEST-MIX (FR-364): an unknown BEST point needs a maximum or a sample."""
    split = _mixed_split((3600.0, None))
    assert job_walltime(split, _estimate(split), max_walltime_s=None) == (
        None,
        "none",
        None,
        None,
        [],
        "no estimate for m/sim_2002/p1, and the profile states no max_walltime to ask for; "
        "write a wall clock with its unit in those rows, or run one point of the row "
        "first so the fit has a sample.",
    )


@pytest.mark.parametrize(
    ("key", "values", "a", "b", "i", "j", "name"),
    [
        ("ADVANCE_RATIO", "1.2,1.4,1.3,1.5,1.3", "1.3", "1.3", 3, 5, "J+130"),
        ("ADVANCE_RATIO", "1.301,1.304", "1.301", "1.304", 1, 2, "J+130"),
        ("ALPHA", "1.01,1.04", "1.01", "1.04", 1, 2, "AL+010"),
        ("BETA", "-1.01,-1.04", "-1.01", "-1.04", 1, 2, "BE-010"),
    ],
)
def test_p0351_sweep_duplicate_names_the_pol(tmp_path, key, values, a, b, i, j, name):
    """P0351-SWEEP-DUPLICATE (FR-408): the matrix refusal identifies the POL and both values."""
    _, matrix = _fixture(tmp_path, walltimes=("2h",), sweep=values)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    keys = [cell.strip() for cell in header.split("|")]
    cells = row.split("|")
    cells[keys.index("POL")] = " 1004 "
    cells[keys.index("FLIGHT_CONDITION")] = ", ".join(
        f"{axis}:{'sweep' if axis == key else '0'}" for axis in ("ALPHA", "BETA", "ADVANCE_RATIO")
    )
    matrix.write_text("\n".join((header, rule, "|".join(cells))) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(matrix)
    message = str(caught.value)
    assert f"POL 1004: SWEEP_VALUES repeats {a} (position {i}) and {b} (position {j})" in message
    assert name in message
    assert message.endswith(
        "so they would share one run_id and one datapoint folder; remove the repeat, or "
        "separate the values by 0.1 degree for an angle or 0.01 for an advance ratio."
    )
