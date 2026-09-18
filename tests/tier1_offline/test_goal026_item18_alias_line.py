"""Tier 1, v0.23.0 item 18: the rotor table names its alias on its first line.

THE OWNER'S WORDS, 2026-09-17:

    "E o nome do alias tem que vir escrito na primeira linha do [rotor table]
    para saber qual grupo 'e aquele [rotor table] quando tiver sido carregado
    por script"

and her confirmation the same day that the first line carries the alias ALONE.

WHY THE FILE NAME IS NOT ENOUGH, which is the whole reason this item exists. A
script that has already LOADED the file no longer has its name: it has an array
of numbers. The alias has to be inside the bytes, on the first line, where a
reader reaches it without parsing the table.

ALONE ON THE LINE, with nothing else on it. A line carrying a label and the
alias makes every reader strip a prefix, and the prefix is the kind of thing
that is spelled two ways within a year.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import ProductError, rotor_table_alias_line


def test_the_first_line_is_the_alias_and_nothing_else():
    assert rotor_table_alias_line("PUSHER").strip() == "PUSHER"


def test_the_line_carries_no_label_and_no_separator():
    """A reader takes the line, not a substring of it."""
    line = rotor_table_alias_line("LIFT_L1")
    assert line.strip() == "LIFT_L1"
    assert "," not in line, line
    assert ":" not in line, line
    assert "=" not in line, line


def test_an_alias_with_no_name_is_refused():
    """A first line that names nobody is worse than no first line."""
    with pytest.raises(ProductError):
        rotor_table_alias_line("   ")


def test_an_alias_that_would_span_two_lines_is_refused():
    """The line is the unit; an alias carrying a newline breaks the file's shape."""
    with pytest.raises(ProductError):
        rotor_table_alias_line("PUSHER\nLIFT_L1")
