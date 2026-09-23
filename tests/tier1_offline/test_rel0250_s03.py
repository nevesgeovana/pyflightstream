"""The sections writer accepts step and refuses its former keyword since 0.26.0."""

import warnings

import pytest

from pyflightstream.post.products import ProductArgumentError, read_csv_table, write_sections_table


def test_iteration_is_refused_use_step(tmp_path):
    """The retired keyword refuses with the replacement before writing a file."""
    from tests.tier1_offline.test_post_products import SLOADS

    with pytest.raises(TypeError) as refused:
        write_sections_table(tmp_path / "old.csv", SLOADS, mach=0.1, iteration=144)
    assert "step=" in str(refused.value)
    assert isinstance(refused.value, ProductArgumentError)
    assert not (tmp_path / "old.csv").exists()
    with warnings.catch_warnings(record=True) as caught:
        new = write_sections_table(tmp_path / "new.csv", SLOADS, mach=0.1, step=144)
    assert not caught
    columns, rows = read_csv_table(new)
    assert "STEP" in columns
    assert {row["STEP"] for row in rows} == {"144"}


@pytest.mark.parametrize("step, iteration", [(144, 144), (None, 144), (144, None), (None, None)])
def test_both_keywords_are_refused(tmp_path, step, iteration):
    with pytest.raises(TypeError) as refused:
        write_sections_table(tmp_path / "unused.csv", "", mach=0.1, step=step, iteration=iteration)
    assert "step=" in str(refused.value)
    assert isinstance(refused.value, ProductArgumentError)
    assert not (tmp_path / "unused.csv").exists()
