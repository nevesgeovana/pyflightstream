"""P0400-DERIVEDNA (PFS-2105.033): a column derived from a corrected component is NA.

ETAW turns the whole force into wind axes, so a calibration of CN alone left
it raw beside the corrected CN; THRUST is the shaft projection of FX to FZ, so
a calibration of FX alone left THRUST and the rotor state derived from it raw.
"""

from __future__ import annotations

import pytest

from tests.tier1_offline.test_goal036_qsteady_corrections import (
    _post_recorded,
    _recorded_wheel,
    _row,
    _table,
)


def _calibration(component: str) -> str:
    text = 'route = "table"\n'
    for alpha in (-4.0, 4.0):
        text += _row(component, 1.7, alpha, 0.0, 0.001, 1.1, 1.0, 0.0)
    return text


@pytest.mark.parametrize((), [pytest.param(id="P0400-DERIVEDNA")])
def test_p0400_derivedna_cn_alone_makes_etaw_na(tmp_path):
    """P0400-DERIVEDNA: a CN calibration leaves ETAW NA in the corrected rotor table."""
    extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
    workspace = _recorded_wheel(
        tmp_path, pproc_extra=extra, files={"c001.toml": _calibration("CN")}
    )
    products, folder, _ = _post_recorded(workspace)
    (rotor,) = [name for name in products["products"] if name.endswith("PROP_rotor_corrected.csv")]
    assert {row["ETAW_PROP"] for row in _table(folder, rotor)} == {"NA"}
    assert "ETAW_PROP" in products["products"][rotor]["derived_na"]


@pytest.mark.parametrize((), [pytest.param(id="P0400-DERIVEDNA")])
def test_p0400_derivedna_fx_alone_makes_thrust_na(tmp_path):
    """P0400-DERIVEDNA: an FX calibration leaves THRUST, TORQUE and CT_ROTOR NA."""
    extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
    workspace = _recorded_wheel(
        tmp_path, pproc_extra=extra, files={"c001.toml": _calibration("FX")}
    )
    products, folder, _ = _post_recorded(workspace)
    (average,) = [
        name for name in products["products"] if name.endswith("PROP_qs_avg_corrected.csv")
    ]
    rows = _table(folder, average)
    for column in ("THRUST_PROP", "TORQUE_PROP", "CT_ROTOR", "LAMBDA_I"):
        assert {row[column] for row in rows} == {"NA"}, column
