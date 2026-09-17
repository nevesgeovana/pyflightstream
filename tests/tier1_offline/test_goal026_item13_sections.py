"""Tier 1, v0.23.0 item 13: a sections row says WHICH iteration and WHICH azimuth.

THE OWNER'S WORDS, 2026-09-17, after opening one of her own `_sections` files:

    "ele tá com o nome da polar escrito em point, eu quero aqui o numero da
    iteracao e outra coluna para posição azimutal (se não tiver rotor, ela
    fica na)"

WHY IT IS A DEFECT. `POINT` carried the polar's name, which the FILE NAME
already carries, so the column spent a field restating the one fact a reader
holds before opening the file, while the two facts that tell one row from
another -- which iteration it was sampled at, and where the blade was -- were
nowhere. On an unsteady run every row of the table looked identical apart from
its position, which is the shape this estate refuses: a table whose rows are
told apart by their order is not a table.

AZIMUTH IS `NA` WITHOUT A ROTOR, not zero and not blank: a run with no rotor
has no azimuth, and zero is a real azimuth that a rotor row can hold.

THE USAGE, as a user meets it:

    ITERATION,AZIMUTH,ALPHA,BETA,MACH,RE,VINF,ALT,J,SREF,CREF,BREF,Offset,...
    412,37.50000,-2.00000,...
"""

from __future__ import annotations

from pyflightstream.post import products


def test_the_sections_table_says_which_iteration_and_which_azimuth():
    """The two columns that tell one sections row from another."""
    columns = products.SECTION_COLUMNS
    assert "ITERATION" in columns, columns
    assert "AZIMUTH" in columns, columns


def test_the_polar_name_is_no_longer_a_column():
    """`POINT` restated the file name, which is the one fact the reader already has.

    This is the half that has to be asserted rather than assumed: adding two
    columns beside `POINT` would satisfy the test above and leave the defect
    she reported -- a field spent on the file's own name -- exactly where it
    was.
    """
    assert "POINT" not in products.SECTION_COLUMNS, products.SECTION_COLUMNS


def test_the_iteration_and_the_azimuth_lead_the_row():
    """They are the row's identity, so they come before the condition it shares.

    Every row of one sections table carries the SAME flight condition and the
    same reference lengths; only these two vary down the file. A reader
    scanning the left edge of the table should be reading what changes.
    """
    columns = products.SECTION_COLUMNS
    assert columns[0] == "ITERATION", columns
    assert columns[1] == "AZIMUTH", columns
