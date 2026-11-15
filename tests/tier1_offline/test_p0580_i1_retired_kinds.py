"""The retired-layout warning names only retired kinds (design sections 1 and 2.2).

THE REQUIREMENT: the post leaves a 0.57.0 polar file untouched and names its
kind once; the quasi-steady rotor tables (``P<sim>-<ALIAS>_qs_avg.csv``,
``_qs_positions.csv``) keep their names in 0.58.0 (section 1: the ``qsteady_rotor``
run type keeps its own tables), so they are current products, never warned as
the earlier layout, and a stale one is retired like any other current table.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.post._retired_polars import is_retired_layout, warn_retired_polar_files

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-RETIRED-KINDS")])


@pytest.mark.parametrize("name", ["P7001-PROP_qs_avg.csv", "P7001-PROP_qs_positions.csv"])
def test_p0580_the_quasi_steady_tables_are_not_of_the_earlier_layout(tmp_path, name):
    (tmp_path / "polars").mkdir()
    (tmp_path / "polars" / name).write_text("POL\n7001\n", encoding="utf-8")
    assert not is_retired_layout(f"polars/{name}")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert warn_retired_polar_files(tmp_path) == {}
    assert not caught, [str(w.message) for w in caught]


def test_p0580_a_retired_group_file_is_still_named(tmp_path):
    (tmp_path / "polars").mkdir()
    (tmp_path / "polars" / "P6001-M200AL+sweepBE+000_WING.csv").write_text("POL\n", "utf-8")
    with pytest.warns(Warning, match="per-group, per-Mach polar"):
        found = warn_retired_polar_files(tmp_path)
    assert found == {"polars/P6001-M200AL+sweepBE+000_WING.csv": "polars/P6001-WING-ACOEF.csv"}
