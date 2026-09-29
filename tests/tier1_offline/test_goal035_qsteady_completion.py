"""Tier 1: the quasi-steady rotor completed for 0.30.0 (GOAL-035, the second pass).

What the first pass left and a skeptical reading found, and what the owner
added after it:

* A: a blade the row names by an alias is present; a point with no free stream
  and no rotation says why its validity is not defined instead of dividing by
  zero; ``PASSAGE_POSITIONS`` is read as every count of a row is read; a ring of
  an extracted inflow is read to a tolerance a real field meets; the relative
  free stream is composed about the HUB, along the SHAFT the reference states.
* B: after the post, each wheel point's validity (with the thrust and torque
  shares of the stations above k = 0.1) sits in its datapoint folder, and the
  super file carries it.
* C: FSI on a periodic sector: the rotating blade solve (centrifugal tension,
  stiffening, in-plane softening) at the speed the row turns the free stream.
* D: ``pyfs-matrix plan --inflow-fft``: the harmonic content of a custom inflow
  as ONE BLADE meets it over one revolution, ``k_eff = n95 k_1P`` and the
  suggested ``PASSAGE_POSITIONS``.

Every expected number is worked by hand from the definitions and the
fixture's own values, never read off the implementation.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.cases import CampaignConfigError, RotorBlock
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.cases.workflows import qsteady_validity
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    OMEGA,
    ROTOR,
    _blade_obj,
    _case,
    _custom,
    _field,
    _lines,
    _rotations,
    _with_obj,
)


def _field_rows(script, lines: list[str]) -> list[list[float]]:
    at = lines.index("SET_FREESTREAM CUSTOM UNSTRUCTURED")
    payload = script.pending_input_files[lines[at + 1]]
    return [[float(v) for v in line.split()] for line in bytes(payload).decode().splitlines()]


# ------------------------------------------------------------ A: the fixes --


def test_a_blade_named_by_an_alias_of_the_row_is_present(tmp_path):
    """The mesh calls blade three `B3_surface`; the row's alias `Blade3` names it.

    The ownership check resolved the alias and the presence check did not, so the
    wheel was refused for a blade it carries.
    """
    # P0300-QS-WHEEL
    obj = _blade_obj(tmp_path / "prop.obj")
    obj.write_text(obj.read_text().replace("o Blade3", "o B3_surface"))
    inventory = ("Blade1", "Blade2", "B3_surface")
    case = _with_obj(_case(), obj, inventory).model_copy(
        update={"aliases": {"Blade3": ["B3_surface"]}}
    )
    lines, _ = _lines(case)
    assert lines.count("START_SOLVER") == 1


def test_a_point_with_no_free_stream_and_no_rotation_says_so_and_does_not_raise():
    """V = 0 and RPM = 0: V_rel = 0 everywhere, k is 0 / 0; the plan asks it anyway."""
    # P0300-QS-VALIDITY-PLAN
    validity = qsteady_validity(_case(VELOCITY="0.0", RPM="0"))
    assert validity is not None
    assert "no relative flow" in str(validity["note"])
    assert validity["k_per_chord_m_tip"] is None and validity["k_per_chord_m_root"] is None


def test_passage_positions_is_read_as_every_count_of_a_row():
    """`2.0` is two clockings; `2.5` and `two` are refused naming the key."""
    # P0300-QS-PASSAGE-POSITIONS
    lines, _ = _lines(_case(PASSAGE_POSITIONS="2.0", ALPHA_POINT=5.0))
    assert _rotations(lines)[0] == "ROTATE_SURFACE 2 X 60.0 -1 DISABLE"
    with pytest.raises(CampaignConfigError, match="PASSAGE_POSITIONS.*fractional"):
        _lines(_case(PASSAGE_POSITIONS="2.5", ALPHA_POINT=5.0))
    with pytest.raises(CampaignConfigError, match="PASSAGE_POSITIONS.*not a number"):
        _lines(_case(PASSAGE_POSITIONS="two", ALPHA_POINT=5.0))


def test_an_extracted_ring_is_read_to_a_tolerance_a_real_field_meets():
    """0.01 % speed noise and up to 3e-5 radius noise on a 30 m/s ring: axisymmetric.

    A cross wind of 2 m/s (6.7 % of the speed) is refused and the refusal states
    the tolerance, 0.1 % of the largest speed, 0.03 m/s.
    """
    # P0300-QS-SECTOR-INFLOW
    noisy = [
        (0.0, s * math.cos(t), s * math.sin(t), 30.0 + 0.003 * i, 0.0, 0.0)
        for r in (0.5, 1.0)
        for i, t in enumerate((0.0, math.pi / 2, math.pi, 3 * math.pi / 2))
        for s in (r * (1 + 1e-5 * i),)
    ]
    assert arithmetic.azimuthal_variation(noisy, hub=(0, 0, 0), axis=(1, 0, 0)) is None
    cross = [
        (0.0, 0.5 * math.cos(t), 0.5 * math.sin(t), 30.0, 2.0, 0.0)
        for t in (0.0, math.pi / 2, math.pi)
    ]
    why = arithmetic.azimuthal_variation(cross, hub=(0, 0, 0), axis=(1, 0, 0))
    assert why is not None and "0.001 of the field's largest speed" in why
    # And a caller who knows the field's noise states another tolerance: the two
    # rows differ by 4 m/s in radial velocity, under 0.2 of 30.07 m/s.
    loose = arithmetic.azimuthal_variation(cross, hub=(0, 0, 0), axis=(1, 0, 0), relative=0.2)
    assert loose is None


def test_the_relative_free_stream_turns_about_the_hub_not_the_origin(tmp_path):
    """Hub at y = 0.5 m: the row at (0, 1.5, 0) is 1 m from the shaft.

    v_rel = v - Omega x (p - hub) = (30, 0, 0) - 40 pi (1, 0, 0) x (0, 1, 0)
          = (30, 0, -40 pi); about the origin it would read -1.5 * 40 pi.
    """
    # P0300-QS-WHEEL
    offset = ROTOR.model_copy(update={"y_m": 0.5})
    rows = [
        (0.0, 0.5 + r * math.cos(t), r * math.sin(t), 30.0, 0.0, 0.0)
        for r in (0.5, 1.0)
        for t in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2)
    ]
    path = _field(tmp_path, rows)
    lines, script = _lines(_custom(_case(rotor=offset, PASSAGE_POSITIONS="2"), path))
    written = _field_rows(script, lines)
    at = next(row for row in written if row[1] == pytest.approx(1.5) and abs(row[2]) < 1e-12)
    assert at[3:] == pytest.approx([30.0, 0.0, -OMEGA], abs=1e-9)


def test_a_rotor_whose_shaft_is_a_vector_turns_along_that_vector(tmp_path):
    """Shaft (-1, 0, 0), right-handed at 1200 rev/min: the air at (0, 1, 0) meets +40 pi in z.

    Omega axis x p = 40 pi (-1, 0, 0) x (0, 1, 0) = 40 pi (0, 0, -1), so
    v_rel_z = 0 - (-40 pi) = +40 pi. Without a field the free stream turns about
    the hub frame's third axis, the shaft of a vector rotor (``Z``), and the
    clockings rotate about it too.
    """
    # P0300-QS-WHEEL
    aft = RotorBlock(
        alias="PROP",
        axis=(-1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_blades=["Blade1", "Blade2", "Blade3"],
        blade1=ROTOR.blade1,
    )
    path = _field(tmp_path, [(0.0, 1.0, 0.0, 30.0, 0.0, 0.0), (0.0, 0.0, 1.0, 30.0, 0.0, 0.0)])
    lines, script = _lines(_custom(_case(rotor=aft, PASSAGE_POSITIONS="2"), path))
    at = next(row for row in _field_rows(script, lines) if row[1] == pytest.approx(1.0))
    assert at[3:] == pytest.approx([30.0, 0.0, OMEGA], abs=1e-9)
    plain, _ = _lines(_case(rotor=aft, PASSAGE_POSITIONS="2", ALPHA_POINT=5.0))
    assert "SET_FREESTREAM ROTATION 2 Z 1200.0" in plain
    assert _rotations(plain)[0].startswith("ROTATE_SURFACE 2 Z 60.0")
