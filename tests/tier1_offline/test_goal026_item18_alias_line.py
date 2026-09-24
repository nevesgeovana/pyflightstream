"""Tier 1, v0.23.0 item 18: a rotor table names its alias inside its bytes.

THE OWNER'S WORDS, 2026-09-17:

    "E o nome do alias tem que vir escrito na primeira linha do [rotor table]
    para saber qual grupo 'e aquele [rotor table] quando tiver sido carregado
    por script"

WHY THE FILE NAME IS NOT ENOUGH, which is the whole reason this item exists. A
script that has already LOADED the file no longer has its name: it has an array
of numbers. The alias has to be inside the bytes.

SINCE 0.27.0 (G16) THE ALIAS IS A COLUMN. From 0.23.0 it stood alone on the
table's first line, before the header, and a line before the header is a file no
CSV reader takes as written. It is the `ROTOR` column now, right after `POL`, on
every row: the promise of this item is kept -- a loaded table still knows which
rotor it holds, and now which polar too -- in the form every other table of the
post uses, and the first line is the header.
"""

from __future__ import annotations

import csv

import pytest

from pyflightstream.post.products import (
    ProductError,
    read_csv_table,
    rotor_coefficient_columns,
    write_rotor_table,
)
from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces


def _written(tmp_path, *, pol="0001"):
    """One rotor table of one row, as the stage writes it for rotor `PUSHER`."""
    return write_rotor_table(
        tmp_path / "polars" / "P0001-PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        rows=[
            {
                "surfaces": _surfaces(Blade1={"Cz": 0.5}),
                "condition": {"MACH": 0.15, "ALPHA": 0.0},
                "rpm": 3000.0,
                "density": 1.225,
                "speed": 40.0,
            }
        ],
        reference=_reference(),
        pol=pol,
    )


def test_the_first_line_is_the_header_and_the_alias_is_the_rotor_column(tmp_path):
    written = _written(tmp_path)
    first = written.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert first[:2] == ["POL", "ROTOR"], first
    with written.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["POL"], row["ROTOR"]) for row in rows] == [("0001", "PUSHER")], rows


def test_a_loaded_table_needs_no_line_skipped(tmp_path):
    """The package's own reader takes the file as written, with nothing skipped."""
    columns, rows = read_csv_table(_written(tmp_path))
    assert columns[:2] == ("POL", "ROTOR"), columns
    assert "CT_PUSHER" in columns and "ETAW_PUSHER" in columns, columns
    assert len(rows) == 1 and float(rows[0]["CT_PUSHER"]) > 0.0, rows


def test_a_table_whose_caller_states_no_polar_says_so_rather_than_inventing_one(tmp_path):
    """No polar stated is `NA` in the column, never a blank and never another table's."""
    _, rows = read_csv_table(_written(tmp_path, pol=None))
    assert rows[0]["POL"] == "NA", rows[0]


def test_an_alias_with_no_name_is_refused():
    """A rotor column that names nobody is worse than none: the coefficients need the alias."""
    with pytest.raises(ProductError):
        rotor_coefficient_columns("   ")
