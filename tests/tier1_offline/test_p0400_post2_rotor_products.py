"""P0400-QSRECORD: an unreadable quasi-steady record is keyed under its point.

At the 0.40.0 base the omission was filed under the made-up alias '?', which the
file-name rule turned into ``polars/P<sim>-rotor_qs_positions.csv``, a file of a
rotor no plan names.
"""

from __future__ import annotations

from types import SimpleNamespace

from pyflightstream.cases.workflows import QSTEADY_ROTOR
from pyflightstream.post._rotor_products import _qsteady_products
from pyflightstream.post._tables import ReferenceValues


def test_p0400_qsrecord_an_unreadable_record_is_keyed_under_the_run(tmp_path):
    """P0400-QSRECORD: the skip names runs/<run id>#qsteady_record and no rotor file."""
    point = SimpleNamespace(name="a+00.0", loads_path=tmp_path / "absent" / "DP.txt", state=None)
    record = SimpleNamespace(recipe=QSTEADY_ROTOR, run_id="rotor/1/a+00.0")
    skipped: dict[str, str] = {}
    written = _qsteady_products(
        "1",
        [point],
        {point.name: record},
        reference=ReferenceValues(sref_m2=1.0, cref_m=1.0, bref_m=1.0),
        out=tmp_path,
        validity_of={},
        condition_of=lambda _point: {},
        target=lambda path: path,
        skipped=skipped,
    )
    assert written == []
    assert list(skipped) == ["runs/rotor/1/a+00.0#qsteady_record"]
    assert "a+00.0" in skipped["runs/rotor/1/a+00.0#qsteady_record"]
