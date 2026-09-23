"""The sections writer accepts step and warns for its former keyword."""

import warnings

import pytest

from pyflightstream._errors import PyflightstreamDeprecationWarning
from pyflightstream.post.products import read_csv_table, write_sections_table


def test_iteration_warns_and_matches_step(tmp_path):
    from tests.tier1_offline.test_post_products import SLOADS

    export = SLOADS
    with pytest.warns(PyflightstreamDeprecationWarning, match=r"step=.*0\.26\.0"):
        old = write_sections_table(tmp_path / "old.csv", export, mach=0.1, iteration=144)
    with warnings.catch_warnings(record=True) as caught:
        new = write_sections_table(tmp_path / "new.csv", export, mach=0.1, step=144)
    assert not caught
    assert old.read_bytes() == new.read_bytes()
    columns, rows = read_csv_table(new)
    assert "STEP" in columns
    assert {row["STEP"] for row in rows} == {"144"}


@pytest.mark.parametrize("step, iteration", [(144, 144), (None, 144), (144, None), (None, None)])
def test_both_keywords_are_refused(tmp_path, step, iteration):
    with pytest.raises(TypeError, match="pass only step= or iteration="):
        write_sections_table(tmp_path / "unused.csv", "", mach=0.1, step=step, iteration=iteration)
