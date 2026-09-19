"""Tier 1, 0.24.0 (WT-04, WT-06, WT-09): three fixtures that could not tell two behaviours apart.

Each case here exists because an older fixture's VALUES made a wrong behaviour
and the right one agree, so the mutant the older test was written against
survived it. No expected number below comes from running the code: each is the
convention worked by hand, and the arithmetic is written beside it.

WT-04. The rotor table's regression test built both points of its sweep from ONE
loads text, so the reference velocity it says was hoisted out of the point loop
was identical on both rows, and no test wrote a rotor table of more than one
row. Here the two points differ in rotor speed, density, free stream and
reference velocity, and the WRITTEN FILE is read back.

WT-06. `per_blade_rows` was tested over constant fields, so its value could not
depend on the window its row claims. Here the history is quadratic.

WT-09. The unsteady polar's fixture was a linear ramp, on which the mean, the
median and the average of the two end values of a window coincide. Here the
history is quadratic, where the three differ.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.post.products import read_csv_table, write_unsteady_polar
from pyflightstream.post.unsteady import TimestepSeries, per_blade_rows

# --- WT-04 -----------------------------------------------------------------

#: One point of the sweep: name, rotor rev/min, air density, and the ONE speed
#: the loads export states as both its free stream and its reference velocity.
_SWEEP = (("J083", 2400.0, 1.225, 40.0), ("J250", 1200.0, 1.100, 60.0))
_DIAMETER_M = 1.2
_SREF_M2 = 50.0
#: The `Cx` the loads fixture prints for the surface that stands for the blade.
_CX = 0.0193288


def _loads_text(speed: float) -> str:
    """The shared loads fixture, its first surface renamed `Blade1`, at ``speed`` m/s."""
    from tests.tier1_offline.test_post_products import LOADS

    assert LOADS.count("68.058") == 2, "the fixture states its two velocities once each"
    assert LOADS.count("     W,") == 1
    return LOADS.replace("68.058", f"{speed:.3f}").replace("     W,", "     Blade1,")


def _rotor_sweep(tmp_path):
    """Plan the rotor table of a two-point sweep through `_rotor_tables`, the stage's planner."""
    from pyflightstream.post.products import (
        PolarPoint,
        ReferenceValues,
        _rotor_tables,
        matrix_rows,
    )
    from pyflightstream.results import parse_loads
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "\n".join(
            [
                "area_m2 = 50.0",
                "chord_m = 2.526",
                "span_m = 20.0",
                "",
                "[rotors.PUSHER]",
                'alias = "PUSHER"',
                "x_m = 0.0",
                "y_m = 0.0",
                "z_m = 0.0",
                'axis = "X"',
                "rpm_sign = 1",
                f"diameter_m = {_DIAMETER_M}",
                'families_blades = ["Blade1"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    points, records, sources = [], [], {}
    for name, rpm, density, speed in _SWEEP:
        text = _loads_text(speed)
        path = tmp_path / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        points.append(PolarPoint(name=name, loads=parse_loads(text), loads_path=path))
        run_id = f"camp/sim_0001/{name}"
        sources[name] = [run_id]
        records.append(
            RunRecord(
                run_id=run_id,
                sim_id="0001",
                fs_version_requested="26.123",
                package_version="0.24.0",
                script_sha256="0" * 64,
                raw_flag=False,
                status="CONVERGED",
                density_kg_m3=density,
                velocity_requested_m_s=speed,
                mach=0.12,
                reductions={"rotors": {"PUSHER": {"rpm": rpm, "blades": 2}}},
            )
        )
    matrix_row = next(
        row
        for row in matrix_rows(workspace.root, "matriz").values()
        if str(getattr(row, "ref_code", "")) == "r002"
    )
    reference = ReferenceValues.from_mapping(
        {"SREF": _SREF_M2, "CREF": 2.526, "BREF": 20.0, "XMOM": 0.0, "YMOM": 0.0, "ZMOM": 0.0}
    )
    tables = _rotor_tables(
        workspace, "0001", points, records, sources, reference, matrix_row, tmp_path / "out"
    )
    assert len(tables) == 1, tables
    target, alias, plan = tables[0]
    assert alias == "PUSHER"
    return target, plan, reference


def test_the_fixture_gives_each_point_its_own_speed(tmp_path):
    """The premise, asserted: a fixture whose two speeds were equal is the defect of WT-04."""
    _target, plan, _reference = _rotor_sweep(tmp_path)
    assert [row["speed"] for row in plan["rows"]] == [40.0, 60.0], plan["rows"]
    assert [row["free_stream"] for row in plan["rows"]] == [40.0, 60.0], plan["rows"]
    assert [row["rpm"] for row in plan["rows"]] == [2400.0, 1200.0], plan["rows"]
    assert [row["density"] for row in plan["rows"]] == [1.225, 1.100], plan["rows"]


def test_every_row_of_the_written_rotor_table_is_normalised_by_its_own_point(tmp_path):
    """TWO ROWS, WRITTEN AND READ BACK.

    ``J = V / (n D)``: 40 / (40 x 1.2) = 0.83333 and 60 / (20 x 1.2) = 2.50000.

    ``CT = T / (rho n^2 D^4)`` with ``T = Cx (rho V^2 / 2) S``, so the density
    cancels and ``|CT| = Cx V^2 S / (2 n^2 D^4)``:

        row 1: 0.0193288 x 1600 x 50 / (2 x 1600 x 2.0736) = 0.23303
        row 2: 0.0193288 x 3600 x 50 / (2 x  400 x 2.0736) = 2.09731

    and their ratio is 9. A table that takes the speed of the FIRST point for
    every row writes a ratio of 4 (the rotor speeds alone) and J = 1.66667 on
    the second row. The magnitude is asserted because the sign of a thrust
    along the shaft is another convention's, tested where it is defined.
    """
    from pyflightstream.post.products import write_rotor_table

    target, plan, reference = _rotor_sweep(tmp_path)
    left_out: list[tuple[str, str]] = []
    written = write_rotor_table(
        target, rotor=plan["rotor"], rows=plan["rows"], reference=reference, left_out=left_out
    )
    assert written is not None and not left_out, left_out
    _columns, rows = read_csv_table(written, skip=1)
    assert len(rows) == 2, rows

    assert [row["J_PUSHER"] for row in rows] == ["0.83333", "2.50000"], rows
    assert [row["RPM_PUSHER"] for row in rows] == ["2400.00000", "1200.00000"], rows

    expected = [
        _CX * speed**2 * _SREF_M2 / (2.0 * (rpm / 60.0) ** 2 * _DIAMETER_M**4)
        for _name, rpm, _density, speed in _SWEEP
    ]
    assert expected == pytest.approx([0.23303, 2.09731], abs=5e-6), expected
    thrust = [abs(float(row["CT_PUSHER"])) for row in rows]
    assert thrust == pytest.approx(expected, abs=6e-6), (thrust, expected)
    assert thrust[1] / thrust[0] == pytest.approx(9.0, rel=1e-4), thrust


# --- WT-06 -----------------------------------------------------------------


def _quadratic_blades(n_steps: int = 8) -> TimestepSeries:
    """Blade 1 holds ``step^2`` and blade 2 ``2 step^2``: no two windows share a mean."""
    steps = np.arange(1, n_steps + 1)
    squares = (steps.astype(float) ** 2).reshape(n_steps, 1)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"Blade1_CMx": squares, "Blade2_CMx": 2.0 * squares},
        sources=(),
    )


def test_the_value_of_a_per_blade_row_is_the_average_over_the_window_it_states():
    """Steps 3 to 6 of ``step^2`` are 9, 16, 25, 36: mean 21.5, and 43.0 for twice that.

    Over the whole history the means are 25.5 and 51.0, which is what a row
    reads when it states one window and averages another.
    """
    rows = per_blade_rows(_quadratic_blades(), window=(3, 6), blades=2, steps_per_revolution=8.0)
    assert [(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows] == [(3, 6), (3, 6)], rows
    assert rows[0]["CMx"] == pytest.approx(21.5), rows[0]
    assert rows[1]["CMx"] == pytest.approx(43.0), rows[1]


# --- WT-09 -----------------------------------------------------------------


class _Point:
    def __init__(self, name: str) -> None:
        self.name = name


def test_the_unsteady_polar_holds_the_mean_and_not_a_number_that_agrees_on_a_ramp(tmp_path):
    """``CL = step^2`` over steps 5 to 8 is 25, 36, 49, 64.

    The MEAN is 43.5. The median is 42.5, the average of the two end values is
    44.5 and the last step is 64: four readings, four numbers.
    """
    lines = ["Time-step,CL,CDi"]
    lines += [f"{step},{step**2:.5f},{step**2 / 10:.5f}" for step in range(1, 9)]
    plots = tmp_path / "a.txt"
    plots.write_text("\n".join(lines) + "\n", encoding="utf-8")

    written = write_unsteady_polar(
        tmp_path / "out.csv",
        points=[_Point("a")],
        plots={"a": plots},
        window=(5, 8),
        conditions=[{"ALPHA": 0.0}],
        reference=None,
    )
    assert written is not None
    _, rows = read_csv_table(written)
    assert rows[0]["CL"] == "43.50000", rows[0]
    assert rows[0]["CDi"] == "4.35000", rows[0]
