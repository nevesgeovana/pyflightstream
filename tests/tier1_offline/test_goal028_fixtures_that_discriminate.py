"""Tier 1, 0.24.0 (WT-04, WT-06, WT-09): three fixtures that could not tell two behaviours apart.

Each case here exists because an older fixture's VALUES made a wrong behaviour
and the right one agree, so the mutant the older test was written against
survived it. No expected number below comes from running the code: each is the
convention worked by hand, and the arithmetic is written beside it.

WT-04. The rotor table's regression test built both points of its sweep from ONE
loads text, so the reference velocity it says was hoisted out of the point loop
was identical on both rows, and no test wrote a rotor table of more than one
row. Here the two points differ in rotor speed, density, free stream and
reference velocity, and the WRITTEN FILE is read back. Since 0.58.0 the rotor
table is the rotor group's RCOEF file, written by the post stage.

WT-06. The per-blade row was tested over constant fields, so its value could not
depend on the window its row claims. Here the history is quadratic, and the
blade is a family row of the FAM files, which the post stage averages over the
window the row states.

WT-09. The unsteady polar's fixture was a linear ramp, on which the mean, the
median and the average of the two end values of a window coincide. Here the
history is quadratic, where the three differ.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from pyflightstream.post.products import read_csv_table

# --- WT-04 -----------------------------------------------------------------

#: One point of the sweep: name, rotor rev/min, air density, and the ONE speed
#: the loads export states as both its free stream and its reference velocity.
_SWEEP = (("AL-020", 2400.0, 1.225, 40.0), ("AL+000", 1200.0, 1.100, 60.0))
_DIAMETER_M = 1.2
_SREF_M2 = 50.0
#: The `Cx` the loads fixture prints for the surface that stands for the blade.
_CX = 0.0193288


def _rotor_sweep(tmp_path):
    """Post the steady sweep of simulation 6001 with a rotor of the blade family, one per point."""
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_superfile import _loads, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
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
                'families_blades = ["W"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            tag = "AL-020" if "AL-020" in record.point_name else "AL+000"
            _tag, rpm, density, speed = next(row for row in _SWEEP if row[0] == tag)
            loads = workspace.sim_dir("6001") / "outputs" / f"POLAR-6001_M20{tag}BE+000.txt"
            loads.write_text(
                _loads(-2.0 if tag == "AL-020" else 0.0, velocity=f"{speed:.3f}"),
                encoding="utf-8",
            )
            record = record.model_copy(
                update={
                    "density_kg_m3": density,
                    "velocity_requested_m_s": speed,
                    "reductions": {"rotors": {"PUSHER": {"rpm": rpm, "blades": 2}}},
                }
            )
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    return workspace.root / "post" / "matriz" / "polars" / "P6001-PUSHER-RCOEF.csv"


def test_the_fixture_gives_each_point_its_own_speed(tmp_path):
    """The premise, asserted: a fixture whose two speeds were equal is the defect of WT-04."""
    _columns, rows = read_csv_table(_rotor_sweep(tmp_path))
    assert [row["VINF"] for row in rows] == ["40.00000", "60.00000"], rows
    assert [row["RPM0"] for row in rows] == ["2400.00000", "1200.00000"], rows
    assert [row["RHO"] for row in rows] == ["1.22500", "1.10000"], rows


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
    _columns, rows = read_csv_table(_rotor_sweep(tmp_path))
    assert len(rows) == 2, rows

    # J is a coefficient column, written at six significant figures (PFS-2081.53);
    # in the rotor group's RCOEF file it is the run block's J of rotor 0.
    assert [row["J0"] for row in rows] == ["0.833333", "2.50000"], rows
    assert [row["RPM0"] for row in rows] == ["2400.00000", "1200.00000"], rows

    expected = [
        _CX * speed**2 * _SREF_M2 / (2.0 * (rpm / 60.0) ** 2 * _DIAMETER_M**4)
        for _name, rpm, _density, speed in _SWEEP
    ]
    assert expected == pytest.approx([0.23303, 2.09731], abs=5e-6), expected
    thrust = [abs(float(row["CT"])) for row in rows]
    assert thrust == pytest.approx(expected, abs=6e-6), (thrust, expected)
    assert thrust[1] / thrust[0] == pytest.approx(9.0, rel=1e-4), thrust


# --- WT-06 -----------------------------------------------------------------


def _quadratic_history(n_steps: int = 8) -> dict[str, list[float]]:
    """Family B holds ``step^2`` and family W ``2 step^2`` in FX: no two windows share a mean.

    The six components of both families and of the total are plotted, as a run declares
    them (design of the post outputs, 4.8); only FX moves.
    """
    steps = np.arange(1, n_steps + 1, dtype=float)
    squares = (steps**2).tolist()
    history: dict[str, list[float]] = {"steps": list(range(1, n_steps + 1))}
    for group, scale in (("W", 2.0), ("B", 1.0), ("TOTAL", 3.0)):
        for part in ("FX", "FY", "FZ", "MX", "MY", "MZ"):
            moving = part == "FX"
            history[f"{part}_MRP_{group}"] = [scale * value if moving else 0.0 for value in squares]
    return history


def test_the_value_of_a_family_row_is_the_average_over_the_window_it_states(tmp_path):
    """Steps 3 to 6 of ``step^2`` are 9, 16, 25, 36: mean 21.5, and 43.0 for twice that.

    Over the whole history the means are 25.5 and 51.0, which is what a row
    reads when it states one window and averages another.
    """
    from tests.tier1_offline.test_goal028_uns_axes import posted_unsteady

    _workspace, polars, _said = posted_unsteady(tmp_path, [_quadratic_history()], window=(3, 6))
    _columns, rows = read_csv_table(polars / "FAM-DIM-P6002.csv")
    by_family = {row["FAMILY"]: row for row in rows}
    assert [(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows] == [("3", "6")] * 2, rows
    assert float(by_family["B"]["FX_MRP"]) == pytest.approx(21.5), by_family["B"]
    assert float(by_family["W"]["FX_MRP"]) == pytest.approx(43.0), by_family["W"]


# --- WT-09 -----------------------------------------------------------------


def test_the_unsteady_polar_holds_the_mean_and_not_a_number_that_agrees_on_a_ramp(tmp_path):
    """``FX = step^2`` over steps 5 to 8 is 25, 36, 49, 64.

    The MEAN is 43.5. The median is 42.5, the average of the two end values is
    44.5 and the last step is 64: four readings, four numbers. ``FZ`` is a tenth
    of it, 4.35.
    """
    from tests.tier1_offline.test_goal028_uns_axes import posted_unsteady

    history = _quadratic_history()
    for group in ("W", "B", "TOTAL"):
        history[f"FZ_MRP_{group}"] = [value / 10.0 for value in history[f"FX_MRP_{group}"]]
    _workspace, polars, _said = posted_unsteady(tmp_path, [history], window=(5, 8))
    _columns, rows = read_csv_table(polars / "P6002-TOTAL-DIM.csv")
    # The group is the sum of its families, 3 x step^2 here: the same four readings, scaled.
    assert float(rows[0]["FX_MRP"]) == pytest.approx(3 * 43.5), rows[0]
    assert float(rows[0]["FZ_MRP"]) == pytest.approx(3 * 4.35), rows[0]
    _columns, family = read_csv_table(polars / "FAM-DIM-P6002.csv")
    (blade,) = [row for row in family if row["FAMILY"] == "B"]
    assert float(blade["FX_MRP"]) == pytest.approx(43.5), blade
    assert float(blade["FZ_MRP"]) == pytest.approx(4.35), blade


@pytest.mark.parametrize("direction", [-1, 1])
def test_p0420_convection_speed_keeps_propagation_direction(direction):
    from tests import support_tier3 as support

    # rfft uses exp(-i wt): cos(wt - kx) travels downstream and has phase -kx.
    omega = 2 * np.pi * support.V_INF / (support.J * 2 * support.R_M)
    speed = 1.4 * support.V_INF
    wave_number = support.BLADES * omega / speed
    line = [
        (float(x), complex(np.exp(direction * 1j * wave_number * x * support.R_M)))
        for x in np.linspace(0.3, 1.0, 100)
    ]
    measured, end = support.convection_speed(line)
    assert end == pytest.approx(1.0)
    if direction == -1:
        assert measured == pytest.approx(1.4)
    else:
        assert measured is None
