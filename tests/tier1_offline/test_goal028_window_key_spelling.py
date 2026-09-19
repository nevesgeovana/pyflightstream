"""Tier 1, 0.24.0 (MC-04): a retired window key's warning names the key as the row spells it.

A matrix key is matched EXACTLY and in upper case, like every other row key
(`DELTA_TIME`, `TIME_ITERATIONS`): the averaging window is `LAST_ITERS_AVG` or
`LAST_REVS_AVG`. The three `ROW_WINDOW_*` deprecation entries told a user to
write `last_iters_avg` / `last_revs_avg`. A row written that way is refused on a
workflow row as a key of no run type, and on the post-only path it is not read
at all, so the point reduces with no window and nothing says the key was ignored.

THE CHECK IS THE CONSUMER'S: what the warning tells the user to write is put on a
row and resolved by the function both stages call. A spelling that resolves to
no window is a spelling the warning must not teach.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream import _deprecations
from pyflightstream.cases.windows import averaging_span

#: Each retired key and the key the matrix reads in its place.
_SUPERSEDED_BY = {
    "ROW_WINDOW_STEPS": "LAST_ITERS_AVG",
    "ROW_WINDOW_REVOLUTIONS": "LAST_REVS_AVG",
    "ROW_WINDOW_DEGREES": "LAST_REVS_AVG",
}


@pytest.mark.parametrize("entry", sorted(_SUPERSEDED_BY))
def test_the_key_the_warning_names_is_the_key_the_matrix_reads(entry):
    promise = getattr(_deprecations, entry)
    assert promise.new == _SUPERSEDED_BY[entry], (
        f"{entry} tells the user to write {promise.new!r}; the matrix reads "
        f"{_SUPERSEDED_BY[entry]!r} and matches it exactly"
    )


@pytest.mark.parametrize("entry", sorted(_SUPERSEDED_BY))
def test_a_row_written_as_the_warning_says_resolves_to_a_window(entry):
    """One revolution of 250 steps, or 250 iterations, ending at step 1000: 751-1000."""
    promise = getattr(_deprecations, entry)
    value = "250" if _SUPERSEDED_BY[entry] == "LAST_ITERS_AVG" else "1.0"
    window = averaging_span({promise.new: value}, last_step=1000, per_revolution=250.0)
    assert window == (751, 1000), (
        f"a row stating {promise.new} = {value}, which is what the warning of {entry} says "
        f"to write, resolves to {window}"
    )


@pytest.mark.parametrize("entry", sorted(_SUPERSEDED_BY))
def test_no_sentence_of_the_warning_spells_a_window_key_in_another_case(entry):
    """The extra sentence is read by the same user, so it spells the keys the same way."""
    message = getattr(_deprecations, entry).message()
    spelled = re.findall(r"last_(?:iters|revs)_avg", message, flags=re.IGNORECASE)
    assert spelled, f"the warning of {entry} names no averaging key at all: {message}"
    assert all(word == word.upper() for word in spelled), (
        f"the warning of {entry} spells {sorted(set(spelled))}; a matrix key is upper case "
        f"and matched exactly: {message}"
    )
