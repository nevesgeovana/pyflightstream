"""The solver's `CL` against the wind-axis lift of the vector printed beside it.

0.24.0 builds `CLS` and `CLW` from the export's `(Cx, Cy, Cz)`, so they fall
against a table of 0.23.0 by the gap between the solver's own `CL` and the lift
of that vector. The pages state that gap as a RANGE, and this module is where
the range is measured, over the committed recorded exports
(`fixtures/recorded_total_rows.csv`), so the figure is re-measured and never
remembered. The release review found the pages quoting one number, 0.13 per
cent, beside a worked point that was 0.15.

The cause of the gap is not known. What is asserted is only what the exports
show: it is positive on every lifting export, between 0.10 and 0.25 per cent on
all but one, and 0.71 per cent on that one.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "recorded_total_rows.csv"
#: Below this lift the ratio is dominated by the digits the export prints.
LIFTING = 0.05
#: What the pages say, in per cent. Move these and the pages move with them.
STATED_LOW, STATED_HIGH, STATED_OUTLIER = 0.10, 0.25, 0.71


def _gaps() -> list[tuple[float, str]]:
    gaps = []
    with FIXTURE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            alpha = math.radians(float(row["alpha_deg"]))
            lift = float(row["Cz"]) * math.cos(alpha) - float(row["Cx"]) * math.sin(alpha)
            if abs(lift) < LIFTING:
                continue
            gaps.append((100.0 * (float(row["CL"]) / lift - 1.0), row["export"]))
    return sorted(gaps)


def test_the_fixture_holds_enough_lifting_exports_to_state_a_range():
    assert len(_gaps()) >= 25, len(_gaps())


def test_the_solvers_cl_sits_above_the_lift_of_its_own_vector_on_every_lifting_export():
    assert all(gap > 0.0 for gap, _export in _gaps()), _gaps()[0]


def test_the_gap_is_inside_the_range_the_pages_state_on_all_but_one_export():
    gaps = _gaps()
    outside = [(gap, export) for gap, export in gaps if not STATED_LOW <= gap <= STATED_HIGH]
    assert len(outside) == 1, outside
    assert round(outside[0][0], 2) == STATED_OUTLIER, outside
    # The range is not slack: the exports reach both of its halves.
    assert gaps[0][0] < 0.12 and gaps[-2][0] > 0.20, (gaps[0], gaps[-2])


def test_the_pages_state_the_measured_range_and_no_single_figure():
    root = Path(__file__).parents[2]
    for page in ("CHANGELOG.md", "docs/post-processing-definitions.md"):
        text = (root / page).read_text(encoding="utf-8")
        assert "0.13 per cent" not in text, page
        assert "between 0.10 and 0.25 per cent" in text, page
