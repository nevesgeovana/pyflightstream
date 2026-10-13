"""Tier 1, 0.40.0 integration fixes: an averaged row says it is an average, an instant says so too.

PFS-2105.043 and PFS-2105.046 relabelled every native unsteady export
``last_step`` over ``last_time_step`` (FR-32 as amended at 0.40.0). The
unsteady polar carries the sweep row's provenance cells in its super content,
so its averaged row, ``FIRST_STEP`` to ``LAST_STEP`` of the plots history,
said ``last_step`` as well: a time average labelled as an instant. The
averaged row is ``time_average`` over ``averaging_window``; the super polar
of an unsteady simulation, read from the native export, stays ``last_step``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pyflightstream.post.products import write_campaign_products
from pyflightstream.results import REDUCTION_WINDOW_CODES
from tests.tier1_offline.test_b01_frozen_solve import _post_workspace
from tests.tier1_offline.test_post_superfile import _post, _workspace


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_p0400_the_unsteady_polars_averaged_row_says_time_average(tmp_path):
    """P0400-INTEGFIX-REDUCTION-LABEL (FR-32, PFS-2105.043): the row is labelled an average.

    The rotor campaign's ``polars/P7001_AL-020_uns_avg.csv`` averages the plots
    history over steps 60 to 61. Its ``reduction`` and ``reduction_window``
    cells must say ``time_average`` and ``averaging_window``; before the fix
    they carried the sweep row's ``last_step`` and ``last_time_step``.
    """
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    write_campaign_products(workspace, matrix_stem="products")
    polars = sorted((Path(workspace.root) / "post" / "products" / "polars").glob("*_uns_avg.csv"))
    assert [path.name for path in polars] == ["P7001_AL-020_uns_avg.csv"]
    rows = _rows(polars[0])
    assert len(rows) == 1
    row = rows[0]
    assert (row["FIRST_STEP"], row["LAST_STEP"], row["STEPS"]) == ("60", "61", "2")
    assert (row["reduction"], row["reduction_window"]) == ("time_average", "averaging_window")
    assert "averaging_window" in REDUCTION_WINDOW_CODES


def test_p0400_an_unsteady_super_polar_row_stays_an_instant(tmp_path):
    """P0400-INTEGFIX-REDUCTION-LABEL (PFS-2105.046): the native-export row is the last step.

    The control: the super polar of the unsteady simulation 6002 is read from
    its loads exports, which state the last time step only, so its rows keep
    ``last_step`` over ``last_time_step`` and never the average's label.
    """
    workspace = _workspace(tmp_path)
    _post(workspace)
    polars = Path(workspace.root) / "post" / "matriz" / "polars"
    supers = sorted(polars.glob("SUPER-6002-*.csv"))
    assert supers, "the campaign no longer writes the unsteady simulation's super polar"
    for path in supers:
        rows = _rows(path)
        assert rows
        for row in rows:
            assert (row["reduction"], row["reduction_window"]) == ("last_step", "last_time_step")
    assert not list(polars.glob("*6002*_uns_avg.csv"))
