"""Tier 1, v0.23.0 item 5: every product says what flight condition it is OF.

THE OWNER'S WORDS, 2026-09-17, and they are two rules rather than one:

    "Todos os arquivos gerados no post precisam carregar todas as variáveis de
    flight condition, se não não da para saber do que se trata."
    "Todos precisam carregar tambem os comprimentos de referencia."

WHY IT IS A DEFECT AND NOT A WISH. Measured on the tree before this item:

    POLAR      carries ALPHA BETA MACH RE J, and NOT VINF or ALT
    SECTIONS   carries the condition, and NOT SREF CREF BREF
    PROBES     carries NEITHER
    REDUCTION  carries NEITHER

So three of the four product families could not say what they were files of,
and a coefficient sat beside no reference length at all in two of them. A
coefficient without the area it was normalised by is a number nobody can check,
and a probe sample with no condition is a table of numbers about nowhere.

THE AUTHORITY is FR-89, "One derived file per polar and group carries
everything the workspace knows", which this item extends from the one derived
file to every product the post stage writes.

THE USAGE, as a user meets it: open any file under `post/` and read its header.

    POLAR,DESCRIPTION,GROUP,SREF,CREF,BREF,XMOM,YMOM,ZMOM,VINF,ALT,J,ALPHA,...
    PROBE,X,Y,Z,FRAME,STEP,ALPHA,BETA,MACH,RE,VINF,ALT,J,SREF,CREF,BREF,...
"""

from __future__ import annotations

import pytest

from pyflightstream.post import products

#: What EVERY product must state, whichever family it belongs to. `J` is not
#: here: a steady campaign has no advance ratio to state and requiring it would
#: put `NA` in every column of every steady product, which says nothing.
REQUIRED = ("ALPHA", "BETA", "MACH", "RE", "VINF", "ALT", "SREF", "CREF", "BREF")

#: The four product families and the tuple that declares each one's columns.
FAMILIES = ("POLAR_COLUMNS", "SECTION_COLUMNS", "PROBE_SPINE", "REDUCTION_COLUMNS")


@pytest.mark.parametrize("family", FAMILIES)
def test_every_product_family_states_the_condition_and_the_reference_lengths(family):
    """One family at a time, so a failure names WHICH product cannot say what it is.

    PARAMETRIZED RATHER THAN ONE ASSERTION OVER A DICT, deliberately: a single
    test over all four reports the first family it meets and hides the other
    three, and the tree before this item was short in three different ways.
    """
    columns = getattr(products, family)
    missing = sorted(set(REQUIRED) - set(columns))
    assert not missing, (
        f"{family} does not state {missing}, so a reader holding that file cannot "
        f"tell what it is a file of. It carries: {list(columns)}"
    )


def test_the_condition_columns_are_declared_in_one_place():
    """The rule has ONE home, so a fifth product cannot be added short.

    A product family that assembles its own condition list is a family that
    will drift from the other three, which is exactly the state this item
    repairs. The constant is what a new writer composes rather than remembers.
    """
    declared = set(products.FLIGHT_CONDITION_COLUMNS) | set(products.REFERENCE_LENGTH_COLUMNS)
    assert set(REQUIRED) <= declared, (
        "the package declares no single home for the flight condition and the "
        f"reference lengths; these are in no shared tuple: {sorted(set(REQUIRED) - declared)}"
    )


def test_the_advance_ratio_stays_outside_the_twenty_four_coefficients():
    """A guard on the fix, not on the defect, and it is the one that can bite.

    `COEFFICIENT_COLUMNS` IS the custom format's own line 9 and a fixture pins
    it line by line, so a flight-condition column added there changes a file
    format that was specified byte by byte. `J` was already outside for that
    reason; `VINF` and `ALT` must join it there and not inside.
    """
    twenty_four = set(products.COEFFICIENT_COLUMNS)
    for name in ("J", "VINF", "ALT"):
        assert name not in twenty_four, (
            f"{name} is inside COEFFICIENT_COLUMNS, which is the custom format's "
            "line 9 and is pinned by a fixture; adding a column there changes a "
            "specified file format"
        )
    assert len(products.COEFFICIENT_COLUMNS) == 24, len(products.COEFFICIENT_COLUMNS)


def test_a_recorded_condition_reaches_the_column_it_means():
    """THE COLUMNS EXIST AND THE VALUES NEVER DO, which the QA lens measured.

    `context_row` folds CASE and nothing else, so a recorded key reaches a
    column only when the two are the same word. None of the three columns item 5
    most needs is spelled the way the run recorded it:

        VINF   recorded as `TASmps` (the cell) or `freestream_velocity_m_s`
        ALT    recorded as `ALTFT` or `altitude_ft`
        J      recorded as `advance_ratio` or `ADVANCE_RATIO`

    which is why the products stage already special-cases exactly one of them by
    hand. Three hand-written special cases is what this becomes without a table,
    and having none is what the lens measured on real products: VINF and ALT
    read NA in every row of every polar and super file.
    """
    from pyflightstream.post._tables import CONTEXT_COLUMNS, context_row

    recorded = {
        "alpha": -2.0,
        "beta": 0.0,
        "MACH": 0.15,
        "TASmps": 49.036,
        "ALTFT": 0.0,
        "advance_ratio": 0.85,
    }
    row = dict(zip(CONTEXT_COLUMNS, context_row(recorded), strict=True))
    assert row["VINF"] == 49.036, row
    assert row["ALT"] == 0.0, row
    assert row["J"] == 0.85, row
    # The ones that already folded must not have broken.
    assert row["ALPHA"] == -2.0 and row["BETA"] == 0.0 and row["MACH"] == 0.15, row


def test_what_the_loads_export_reports_reaches_the_same_columns():
    """The REPORTED condition, which is what a product should carry.

    Two sources exist per point and they are not equivalent: the matrix cell is
    what was ASKED for, the loads export header is what the solver SAYS it ran
    at. A file that says what it is a file OF must carry the second -- the two
    differ exactly when something went wrong, which is the case a reader most
    needs to see.
    """
    from pyflightstream.post._tables import CONTEXT_COLUMNS, context_row

    reported = {
        "angle_of_attack_deg": 2.0,
        "sideslip_deg": -1.0,
        "freestream_velocity_m_s": 49.036,
        "altitude_ft": 1000.0,
        "reynolds": 4380000.0,
    }
    row = dict(zip(CONTEXT_COLUMNS, context_row(reported), strict=True))
    assert row["ALPHA"] == 2.0 and row["BETA"] == -1.0, row
    assert row["VINF"] == 49.036 and row["ALT"] == 1000.0, row
    assert row["RE"] == 4380000.0, row


def test_a_reynolds_in_millions_is_not_written_into_an_absolute_column():
    """THE UNIT TRAP, refused rather than aliased.

    `REmi` is the Reynolds number in MILLIONS; the export's "Reynolds Number" is
    absolute and the fixture reads 4380000. Aliasing `REmi` onto `RE` would
    write 4.38 into a column where every other row writes 4380000, silently, in
    a column whose name says nothing about which it holds.

    So the cell key does NOT reach the column, and a point carrying only the
    cell key leaves RE as NA -- which is the honest answer and is visibly
    absent rather than quietly wrong by six orders of magnitude.
    """
    from pyflightstream.post._tables import (
        CONTEXT_COLUMNS,
        NOT_APPLICABLE,
        _cell,
        context_row,
    )

    row = dict(zip(CONTEXT_COLUMNS, context_row({"REmi": 4.38}), strict=True))
    assert row["RE"] is None, row
    assert _cell(row["RE"]) == NOT_APPLICABLE
