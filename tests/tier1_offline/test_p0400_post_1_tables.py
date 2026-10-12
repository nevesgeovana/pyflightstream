"""P0400 table-helper defects (post-1 lane).

P0400-NAMEDGROUP (PFS-2095.044): the recorded file-name helpers refuse a
named group with a ProductError, never a bare ValueError.
P0400-SKIPLINE (PFS-2100.013): read_csv_table names the file's own line when
it skips lines before the header.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post._tables import polar_file_name, read_csv_table
from pyflightstream.post.custom_polar import custom_polar_file_name


@pytest.mark.parametrize((), [pytest.param(id="P0400-NAMEDGROUP")])
def test_p0400_namedgroup_is_a_product_error():
    """P0400-NAMEDGROUP: a group named WING is refused by both helpers, by name."""
    assert polar_file_name(7, 0.2, "3") == "7_M20_g03.csv"
    with pytest.raises(ProductError, match="'WING'"):
        polar_file_name(7, 0.2, "WING")
    with pytest.raises(ProductError, match="'WING'"):
        custom_polar_file_name(7, mach=0.2, group="WING")


@pytest.mark.parametrize((), [pytest.param(id="P0400-SKIPLINE")])
def test_p0400_skipline_names_the_files_line(tmp_path):
    """P0400-SKIPLINE: with skip=1 the short first data row is file line 3."""
    table = tmp_path / "rotor.csv"
    table.write_text("PUSHER\nPOL,CT\n1\n", encoding="utf-8")
    with pytest.raises(ProductError, match="line 3 carries 1 values"):
        read_csv_table(table, skip=1)
