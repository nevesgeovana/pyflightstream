"""Tier 1, v0.23.0 item 18: a rotor's table names its alias inside its bytes.

THE OWNER'S WORDS, 2026-09-17:

    "E o nome do alias tem que vir escrito na primeira linha do [rotor table]
    para saber qual grupo 'e aquele [rotor table] quando tiver sido carregado
    por script"

WHY THE FILE NAME IS NOT ENOUGH, which is the whole reason this item exists. A
script that has already LOADED the file no longer has its name: it has an array
of numbers. The alias has to be inside the bytes.

SINCE 0.27.0 (G16) THE ALIAS IS A COLUMN, and a line before the header is a file no
CSV reader takes as written. Since 0.58.0 the rotor table is the rotor's own group file,
`polars/P<POL>-<ALIAS>-RCOEF.csv`: the first line is the header, the run block opens
every row (`POL` first) and the alias is the `GROUP` column of every row, with the
rotor's id in `ROTOR_ID`: a loaded table still knows which rotor it holds, and which
polar too.
"""

from __future__ import annotations

import csv

import pytest

from pyflightstream.post.products import (
    ProductError,
    read_csv_table,
    rotor_coefficient_columns,
)
from tests.tier1_offline.test_goal026_item08_per_blade import posted_blades

#: Thrust forward is minus the export's x force of a rotor declared along the aft +x.
_PUSHING = {"Blade1": {"FX": [-100.0] * 8}, "Blade2": {"FX": [-50.0] * 8}}


def _written(tmp_path):
    """The rotor table of polar 6002, as the stage writes it for rotor `PUSHER`."""
    polars, _said, _count = posted_blades(tmp_path, _PUSHING, revolutions=0.5)
    return polars / "P6002-PUSHER-RCOEF.csv"


def test_the_first_line_is_the_header_and_the_alias_is_the_group_column(tmp_path):
    written = _written(tmp_path)
    first = written.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert first[0] == "POL" and "GROUP" in first and "ROTOR_ID" in first, first
    with written.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["POL"], row["GROUP"], row["ROTOR_ID"]) for row in rows] == [
        ("6002", "PUSHER", "0")
    ], rows


def test_a_loaded_table_needs_no_line_skipped(tmp_path):
    """The package's own reader takes the file as written, with nothing skipped."""
    columns, rows = read_csv_table(_written(tmp_path))
    assert columns[:3] == ("POL", "POINT_ID", "POINT"), columns
    assert "CT" in columns and "ETAW" in columns, columns
    assert not [name for name in columns if name.endswith("_PUSHER")], columns
    assert len(rows) == 1 and float(rows[0]["CT"]) > 0.0, rows


# The case "a table whose caller states no polar says `NA` rather than inventing one" asserted
# a `pol=None` argument of the retired writer. The stage always states the matrix row's POL,
# which opens every row, and a column the row does not state reads `NA` (counterpart:
# `test_p0580_l1_run_block.py::test_a_row_carries_every_column_and_na_where_nothing_applies`).


def test_an_alias_with_no_name_is_refused():
    """A rotor column that names nobody is worse than none: the coefficients need the alias."""
    with pytest.raises(ProductError):
        rotor_coefficient_columns("   ")
