"""The unsteady polar says what it is: the window average, in the files of a steady polar.

0.58.0 retired `P<sim>_<name>_uns_avg.csv` (D14: no file name carries `uns_avg`). An
unsteady row is written to the same family and group files a steady one is, and what
the three requirements of scope 4b (WR-09, CC-09) asked of the old file now holds for
those:

- THE NAME. The file is named for its polar and its group, `P<POL>-<GROUP>-ACOEF.csv`,
  and no file name says `uns_avg` or carries a sweep token.
- THE WINDOW IS IN THE ROWS. `FIRST_STEP`, `LAST_STEP` and `STEPS` are in the run block
  every row opens with, so the CSV on its own says it is an average and over what.
- THE SUPER CONTENT IS NOT A SECOND FILE. The condition is in the run block, the
  description in `products.json` (`polars.<POL>.description`), the operator in the
  provenance document and the setup codes in `settings/`; no SUPER file exists.

And a moment coefficient states its moment point (CC-09): the run block carries
`XMOM, YMOM, ZMOM`.

The fixture is the recorded two-simulation campaign of `test_post_superfile`,
whose unsteady row turns one rotor; its window is stated here through the matrix,
LAST_REVS_AVG 0.5 of a 2-step revolution over a 2-step run: step 2 alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace


@pytest.fixture
def table(tmp_path):
    workspace = _workspace(tmp_path)
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    assert "LAST_REVS_AVG" not in row, "the fixture's row must gain the window here"
    stated = _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5")
    (workspace.root / "matriz.fs").write_text(stated, encoding="utf-8")
    written = [Path(path) for path in _post(workspace)]
    found = [path for path in written if path.name == "P6002-TOTAL-ACOEF.csv"]
    assert len(found) == 1, [path.name for path in written]
    return workspace, found[0]


def test_no_file_name_says_uns_avg_or_carries_a_sweep(table):
    _workspace_, path = table
    names = [p.name for p in path.parent.iterdir()]
    assert not [name for name in names if "uns_avg" in name or "sweep" in name], names
    assert path.name.startswith("P6002-"), path.name


def test_the_window_is_in_the_run_block_of_the_row(table):
    _workspace_, path = table
    columns, rows = read_csv_table(path)
    # THE POLAR FIRST (G16), then the point, and the window inside the run block.
    assert list(columns[:3]) == ["POL", "POINT_ID", "POINT"], columns[:6]
    first = columns.index("FIRST_STEP")
    assert list(columns[first : first + 3]) == ["FIRST_STEP", "LAST_STEP", "STEPS"], columns
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


def test_the_super_content_has_a_home_and_no_second_file(table):
    workspace, path = table
    columns, rows = read_csv_table(path)
    record = next(r for r in workspace.read_manifest() if r.sim_id == "6002")
    # What the polar does not have: the description, the operator, the rotor's speed.
    assert "DESCRIPTION" not in columns, columns
    assert any(name.startswith("RPM") for name in columns), columns
    # And no SUPER file beside it.
    supers = list(path.parent.glob("SUPER-6002*"))
    assert supers == [], [p.name for p in supers]
    manifest = json.loads((path.parent.parent / "products.json").read_text(encoding="utf-8"))
    document = json.loads(
        (path.parent.parent / manifest["provenance"][record.run_id]).read_text(encoding="utf-8")
    )
    assert record.submitted_by == "an.operator"
    assert "an.operator" in json.dumps(document)
    # Design section 6: the description moved from the rows to products.json.
    assert manifest["polars"]["6002"]["description"] == "ROTOR_sector_periodic_J_sweep"
