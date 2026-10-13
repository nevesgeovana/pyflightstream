"""P0400-SETPREC: the settings table writes its values at full precision.

At the 0.40.0 base every float went through the five-decimal funnel, so a
convergence threshold of 1e-6 was written 0.00000 and read back as 0
(PFS-2105.020).
"""

from __future__ import annotations

from pyflightstream.post.settings_table import (
    read_settings_table,
    settings_table,
    write_settings_table,
)
from pyflightstream.script import Script, helpers


def test_p0400_setprec_small_values_round_trip_equal(tmp_path):
    """P0400-SETPREC (PFS-2105.020): 1e-6 and 2.5e-5 read back equal, every row as written."""
    setup = helpers.solver_settings(
        Script(version="26.120"), velocity=30.0, convergence=1e-6, surface_roughness=2.5e-5
    )
    table, _legend = write_settings_table(tmp_path / "settings.csv", [setup])
    read = read_settings_table(table)
    numbers = {row["flag_id"]: row["value_num"] for row in read}
    stated = {row["flag_id"]: row["value_num"] for row in settings_table([setup])}
    assert 1e-6 in numbers.values() and 2.5e-5 in numbers.values()
    assert numbers == stated
    text = table.read_text(encoding="utf-8")
    assert "1e-06" in text and "2.5e-05" in text


def test_p0400_setprec_the_r10_admission_takes_the_spelling_and_no_value():
    """P0400-SETPREC (PFS-2105.020): R10 admits a 0.38.0 cell's new spelling, never a new value."""
    from tests.tier1_offline.test_p0390_r03 import settings_spelling_admitted

    old = "POL,f1_value\n7002,0.00001\n7002,30.00000\n"
    assert settings_spelling_admitted("POL,f1_value\n7002,1e-05\n7002,30.0\n", old)
    assert not settings_spelling_admitted("POL,f1_value\n7002,2e-05\n7002,30.0\n", old)
    assert not settings_spelling_admitted("POL,f1_value\n7002,1e-05\n", old)
    assert not settings_spelling_admitted("POL,f2_value\n7002,1e-05\n7002,30.0\n", old)
