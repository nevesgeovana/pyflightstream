"""P0400 rotor-table defects (post-1 lane).

P0400-ETAWSENSE (PFS-2105.017): ETAW's sense is fixed once per rotor, so a lift
rotor swept through alpha 0 keeps the sign of its ETAW.
P0400-NOATTITUDE (PFS-2105.018): a row stating no ALPHA or BETA gets ETAW NA and a
warning, never level flight; the keys are read case-folded.
P0400-NAROWSAID (PFS-2105.040): a loads export in another frame is a refused row
with its reason; a static row stays and is said once.
"""

from __future__ import annotations

import math
import warnings

import pytest

from pyflightstream.post.products import read_csv_table, write_rotor_table
from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces


def _row(run_id: str = "camp/sim_1/P1", **update):
    row = {
        "run_id": run_id,
        "surfaces": _surfaces(Blade1={"Cz": 0.5, "Cx": 0.2}),
        "condition": {"MACH": 0.15, "ALPHA": 0.0, "BETA": 0.0, "VINF": 40.0, "J": 0.5},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 40.0,
        "free_stream": 40.0,
    }
    row.update(update)
    return row


def _etaw(tmp_path, rows, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = write_rotor_table(
            tmp_path / "P1-PUSHER_rotor.csv",
            rotor=_rotor("Z"),
            rows=rows,
            reference=_reference(),
            **kwargs,
        )
    assert written is not None
    _columns, table = read_csv_table(written)
    return [row["ETAW_PUSHER"] for row in table], [str(w.message) for w in caught]


def _at(alpha: float, run_id: str, **condition):
    stated = {"MACH": 0.15, "ALPHA": alpha, "BETA": 0.0, "VINF": 40.0, "J": 0.5, **condition}
    return _row(run_id, condition=stated)


@pytest.mark.parametrize((), [pytest.param(id="P0400-ETAWSENSE")])
def test_p0400_etawsense_a_lift_rotor_keeps_its_sign_through_alpha_zero(tmp_path):
    """P0400-ETAWSENSE: alpha -2 and +2 on a +Z rotor give ETAW of one sign."""
    etaw, _ = _etaw(tmp_path, [_at(-2.0, "r1"), _at(2.0, "r2")])
    signs = {math.copysign(1.0, float(value)) for value in etaw}
    assert len(signs) == 1, etaw


@pytest.mark.parametrize((), [pytest.param(id="P0400-NOATTITUDE")])
def test_p0400_noattitude_is_na_and_said(tmp_path):
    """P0400-NOATTITUDE: no BETA gives NA and a line; lower-case keys are read."""
    no_beta = _row("r1", condition={"MACH": 0.15, "ALPHA": 2.0, "VINF": 40.0, "J": 0.5})
    lower = _row("r2", condition={"MACH": 0.15, "alpha": 2.0, "beta": 0.0, "J": 0.5})
    stated = _at(2.0, "r3")
    etaw, caught = _etaw(tmp_path, [no_beta, lower, stated])
    assert etaw[0] == "NA", etaw
    assert etaw[1] == etaw[2] != "NA", etaw
    assert any("state no ALPHA or BETA (r1)" in message for message in caught), caught


@pytest.mark.parametrize((), [pytest.param(id="P0400-NAROWSAID")])
def test_p0400_narowsaid_frame_refused_and_static_said(tmp_path):
    """P0400-NAROWSAID: frame BODY is left out with its reason; the static row is warned."""
    left_out: list[tuple[str, str]] = []
    written_runs: list[str] = []
    rows = [_row("r1", frame="BODY"), _row("r2", speed=0.0), _row("r3")]
    _etaw_values, caught = _etaw(tmp_path, rows, left_out=left_out, written_runs=written_runs)
    assert [run for run, _why in left_out] == ["r1"], left_out
    assert "analysis frame 'BODY'" in left_out[0][1]
    assert written_runs == ["r2", "r3"]
    assert any("static points (r2)" in message for message in caught), caught
