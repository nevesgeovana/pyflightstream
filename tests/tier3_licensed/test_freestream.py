"""Tier 3: a custom free stream on a row (``matriz_gui.fs`` 5012 to 5014, G15, the probe T14).

Three rows on the 12_WING_PHY wing, the qa physics preset with five far-field
layers, on 26.124, at zero incidence and sideslip, the only attitude a row
stating a field may run at:

* 5012 writes ``SET_FREESTREAM CUSTOM STRUCTURED`` with ``fs_uniform.txt``,
  vx = 30 m/s everywhere (the row's own ``TASmps``) and vy = vz = 0;
* 5013 is their control, ``SET_FREESTREAM CONSTANT`` at the same speed;
* 5014 writes ``fs_shear.txt``, vx = 30 + 2.5 z m/s.

What they hold, measured by T14 (RPT-T14):

(a) the uniform field loads as the constant free stream it equals, so the file
    is read in m and m/s as it is written;
(c) a sheared field moves the loads off that control, so the field reaches the
    solve.

The probe's fourth row, 5011, the uniform field at 4 deg, loaded near its own
0 deg self and far from the CONSTANT free stream at 4 deg: ``SOLVER_SET_AOA``
does not turn a custom field. The plan now refuses a field beside a non-zero
angle, so the row is retired, and that rule is held in tier 1
(``test_g15_a_field_beside_an_angle_of_attack_or_a_sideslip_is_refused``).

"Equal" is 1e-4 relative over a 1e-3 floor, on CL, CDi and CDo, as
``test_gui.py`` judges a disc; a solve repeated with nothing changed prints the
same digits (RPT-067's control and its three repeats).
"""

from __future__ import annotations

import hashlib

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK
from tests.tier3_licensed.freestreams import FOLDER

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_gui"
#: Two loads are the same within this, relative to the second.
EQUAL = 1e-4
#: The denominator's floor, so a coefficient near zero (the lift of the
#: symmetric wing at 0 deg) is judged absolutely.
FLOOR = 1e-3
#: The loads judged.
LOADS = ("CL", "CDi", "CDo")
#: Each row and the field it names (None: CONSTANT), all at 0 deg.
ROWS = {"5012": "fs_uniform", "5013": None, "5014": "fs_shear"}


def _loads(runs, pol: str) -> dict[str, float]:
    total = runs.total(runs.one(MATRIX, pol, alpha=0.0))
    return {name: total[name] for name in LOADS}


def _gap(loads: dict[str, float], control: dict[str, float]) -> dict[str, float]:
    return {
        name: abs(loads[name] - control[name]) / max(abs(control[name]), FLOOR) for name in LOADS
    }


def _said(loads: dict[str, float]) -> str:
    return ", ".join(f"{name} {value:.6g}" for name, value in loads.items())


@pytest.mark.parametrize("pol", sorted(ROWS))
def test_every_row_ran_terminal_on_26_124_with_its_free_stream(runs, pol):
    """Each point converged on 26.124 with five far-field layers, writing the free
    stream its row names, and a custom row's record hashes the field it read."""
    field = ROWS[pol]
    record = runs.one(MATRIX, pol, alpha=0.0)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == "26.124"
    lines = runs.script(record).splitlines()
    assert "SOLVER_SET_FARFIELD_LAYERS 5" in lines
    if field is None:
        assert "SET_FREESTREAM CONSTANT" in lines
        return
    at = lines.index("SET_FREESTREAM CUSTOM STRUCTURED")
    assert lines[at + 1].replace("\\", "/").endswith(f"inputs/freestreams/{field}.txt")
    path = FOLDER / f"{field}.txt"
    assert record.inputs_sha256.get(path.name) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_the_uniform_field_loads_as_its_constant_control(runs):
    """(a) 5012 against 5013: the field in m/s as written is the constant free stream."""
    custom, control = _loads(runs, "5012"), _loads(runs, "5013")
    gap = _gap(custom, control)
    assert max(gap.values()) <= EQUAL, (
        f"the uniform field (5012) does not load as the constant free stream (5013): gap "
        f"{gap} over {EQUAL} (5012: {_said(custom)}; 5013: {_said(control)}), so the file "
        "is read otherwise than as written (its unit, its frame, or a scale)"
    )


def test_c_a_sheared_field_moves_the_loads_off_its_control(runs):
    """(c) 5014 against 5013: the field reached the solve."""
    sheared, control = _loads(runs, "5014"), _loads(runs, "5013")
    gap = _gap(sheared, control)
    assert max(gap.values()) > EQUAL, (
        f"the sheared field (5014) loads as its CONSTANT control (5013): {gap}, so the "
        f"field did not reach the solve (5014: {_said(sheared)})"
    )
