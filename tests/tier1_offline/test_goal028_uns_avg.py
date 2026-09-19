"""The unsteady polar says what it is: `P<sim>_<name>_uns_avg.csv` (scope 4b, WR-09, CC-09).

Three requirements, each the product owner's:

- THE NAME. Every file under `post/` comes from a sweep, so a sweep token in the
  middle of the name says nothing; `uns_avg` says what the file IS, the average of
  the unsteady history, and the `P` prefix is the one every per-point product has.
- THE WINDOW IS IN THE ROWS. The reductions beside it state `FIRST_STEP`,
  `LAST_STEP` and `STEPS`; the polar stated its window in `products.json` alone,
  so the CSV on its own could not say it was an average or over what.
- THE SUPER CONTENT IS ADDED TO IT, not written as a second file: the super file
  is what the polar does NOT have, the setup flags and the rest of the simulation.

And a moment coefficient states its moment point (CC-09): the table carries the
plots' `MX_/MY_/MZ_` columns and carried no `XMOM, YMOM, ZMOM`.

The fixture is the recorded two-simulation campaign of `test_post_superfile`,
whose unsteady row turns one rotor; its window is stated here through the matrix,
LAST_REVS_AVG 0.5 of a 2-step revolution over a 2-step run: step 2 alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table, unsteady_polar_file_name
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace


def test_the_name_has_the_point_prefix_and_says_it_is_an_average():
    assert unsteady_polar_file_name("6002", name="M144AL+000J+sweep") == (
        "P6002_M144AL+000J+sweep_uns_avg.csv"
    )


@pytest.fixture
def table(tmp_path):
    workspace = _workspace(tmp_path)
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    assert "LAST_REVS_AVG" not in row, "the fixture's row must gain the window here"
    stated = _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5")
    (workspace.root / "matriz.fs").write_text(stated, encoding="utf-8")
    written = [Path(path) for path in _post(workspace)]
    found = [path for path in written if path.name.endswith("_uns_avg.csv")]
    assert len(found) == 1, [path.name for path in written]
    return workspace, found[0]


def test_the_window_leads_the_row_and_is_the_matrix_window_of_that_point(table):
    _workspace_, path = table
    assert path.name.startswith("P6002_"), path.name
    columns, rows = read_csv_table(path)
    assert list(columns[:3]) == ["FIRST_STEP", "LAST_STEP", "STEPS"], columns[:6]
    # Half of a 2-step revolution is one step, ending at the run's last step, 2.
    assert [(row["FIRST_STEP"], row["LAST_STEP"], row["STEPS"]) for row in rows] == [
        ("2", "2", "1")
    ], rows


def test_a_moment_states_its_moment_point_and_the_clock_is_still_no_coefficient(table):
    _workspace_, path = table
    columns, rows = read_csv_table(path)
    for name in ("XMOM", "YMOM", "ZMOM"):
        assert name in columns, columns
    assert "Time-step" not in columns and "Time (sec)" not in columns, columns


def test_the_super_content_rides_in_the_same_file(table):
    workspace, path = table
    columns, rows = read_csv_table(path)
    record = next(r for r in workspace.read_manifest() if r.sim_id == "6002")
    # What the polar does not have: a matrix cell, a record scalar, a rotor's speed.
    assert "DESCRIPTION" in columns, columns
    assert rows[0]["DESCRIPTION"] == "ROTOR_sector_periodic_J_sweep"
    assert "submitted_by" in columns and rows[0]["submitted_by"] == record.submitted_by
    assert any(name.startswith("RPM") for name in columns), columns
    # And no second file beside it.
    supers = list(path.parent.glob("SUPER-6002*"))
    assert supers == [], [p.name for p in supers]
