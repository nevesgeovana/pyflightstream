"""P0400-SETPREC: the settings table writes its values at full precision.

At the 0.40.0 base every float went through the five-decimal funnel, so a
convergence threshold of 1e-6 was written 0.00000 and read back as 0.
"""

from __future__ import annotations

from pyflightstream.post.settings_table import (
    read_settings_table,
    settings_table,
    write_settings_table,
)
from pyflightstream.script import Script, helpers


def test_p0400_setprec_small_values_round_trip_equal(tmp_path):
    """P0400-SETPREC: 1e-6 and 2.5e-5 read back equal, and every row reads back as written."""
    setup = helpers.solver_settings(
        Script(version="26.120"), velocity=30.0, convergence=1e-6, surface_roughness=2.5e-5
    )
    table, _legend = write_settings_table(tmp_path / "settings.csv", [setup])
    read = read_settings_table(table)
    numbers = {row["flag_id"]: row["value_num"] for row in read}
    stated = {row["flag_id"]: row["value_num"] for row in settings_table([setup])}
    assert 1e-6 in numbers.values() and 2.5e-5 in numbers.values()
    assert numbers == stated
