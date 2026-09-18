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

import pytest

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


#: What the shipped sections fixture states as its own iteration. Asserted
#: below rather than trusted, so this file fails loudly if the fixture moves
#: instead of silently measuring a different number.
FIXTURE_ITERATION = 3134


def _sections_export() -> str:
    """The shipped sections export, which ALREADY states its iteration.

    Used rather than a new fixture, so the body is the same bytes every other
    sections test reads. My first attempt built one by injecting a
    `Current solver iteration number` line, on the belief that the fixture
    carried none -- it carries 3134, and the writer read that instead. The
    header line was there the whole time and nothing had ever read it.

    The real-export fixture (`fixtures/all_surface_sections_26.123.txt`) is not
    used here because it carries forces in COEFFICIENTS, which the writer
    refuses by name (FSI-R03) -- a refusal that fired on the first run of this
    test and was right to.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_post_products import SLOADS

    assert f"number:            {FIXTURE_ITERATION}" in SLOADS, "the fixture's iteration moved"
    return SLOADS


def test_the_iteration_is_read_from_the_export_that_states_it(tmp_path):
    """THE COLUMNS EXIST AND THE VALUES NEVER DO, item 13's half of it.

    All three tests above assert the COLUMN TUPLE and none asserts a value, so
    the file they describe passed while every row read `NA,NA` -- which is what
    a release round measured on real products. The same shape as item 5, in the
    family beside it.

    The writer's own docstring says the iteration is "read from the export where
    it states them", and nothing read it. It IS stated: the surface sections
    export carries `Current solver iteration number` in its header, exactly as
    the loads export does. So the writer reads it, and a caller that knows
    better may still override it.
    """
    from pyflightstream.post.products import read_csv_table, write_sections_table

    target = write_sections_table(
        tmp_path / "sections" / "P_sections.csv", _sections_export(), mach=0.2
    )
    assert target is not None
    _, rows = read_csv_table(target)
    assert rows, "the export declares a section and the table has no row"
    assert rows[0]["ITERATION"] == str(FIXTURE_ITERATION), rows[0]


def test_the_azimuth_is_where_the_blade_was_at_that_iteration(tmp_path):
    """The azimuth is the iteration ON THE ROW'S CLOCK, and it WRAPS.

    A step count is not an angle. This fixture is 3134 steps at 3.6 degrees
    each, which is 11282.4 degrees -- thirty-one full turns and a bit, and a
    blade is not 11282 degrees round. The cell states where the blade WAS,
    which is that modulo a turn.

    The wrap is what this test is for: without it the column would carry a
    number that grows without bound down a long unsteady run, and every reader
    would have to know to take a modulus the file never mentions.
    """
    from pyflightstream.post.products import read_csv_table, write_sections_table

    target = write_sections_table(
        tmp_path / "sections" / "Q_sections.csv",
        _sections_export(),
        mach=0.2,
        step_deg=3.6,
    )
    assert target is not None
    _, rows = read_csv_table(target)
    assert float(rows[0]["AZIMUTH"]) == pytest.approx(122.4), rows[0]
    assert 0.0 <= float(rows[0]["AZIMUTH"]) < 360.0, rows[0]


def test_a_run_with_no_clock_states_no_azimuth_and_never_a_zero(tmp_path):
    """`NA` and not `0`, because zero is a real azimuth.

    Without this the fix is satisfied by writing 0 wherever the clock is
    unknown, which is a number a reader would believe.
    """
    from pyflightstream.post.products import NOT_APPLICABLE, read_csv_table, write_sections_table

    target = write_sections_table(
        tmp_path / "sections" / "R_sections.csv", _sections_export(), mach=0.2
    )
    assert target is not None
    _, rows = read_csv_table(target)
    assert rows[0]["AZIMUTH"] == NOT_APPLICABLE, rows[0]
