"""Tier 1: the 0.32.0 rigor package J (FR-280 to FR-289).

Requirement ids delivered here: P0320-D-RIG, P0320-TOL-0291, P0320-AVG-0291,
P0320-ARCH2-S2, P0320-QA2-2 and P0320-QS-J.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from tests.tier1_offline.test_goal024_point_name import RECIPES
from tests.tier1_offline.test_goal024_rpm import ROTOR_CELL, _rotor_matrix


def test_p0320_d_rig_a_static_rig_with_motions_is_not_refused_for_a_double_speed(tmp_path):
    """P0320-D-RIG: fixed rpm and a swept J, with MOTIONS, states the speed once.

    The rig states the speed once and sweeps J, which then means the free
    stream (V = J x (RPM/60) x D). The plan's point carries the derived
    velocity, and the plan must not read that derived velocity as a stated
    one and refuse the row for "stating its rotor speed twice".
    """
    workspace, matrix = _rotor_matrix(
        tmp_path,
        condition="REmi:4.38, ALPHA:0.0, RPM:800, ADVANCE_RATIO:sweep",
        values="0.8,1.0",
        cell=ROTOR_CELL,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix,
            workspace,
            name="rig",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
    assert "twice" not in " ".join(str(item.message) for item in caught)
    assert len(plan.points) == 2
    for entry in plan.points:
        (mach,) = entry.rotor_mach.values()
        assert mach.get("note") is None, mach.get("note")
        assert mach["rpm"] == pytest.approx(800.0)


# --- the native match tolerance (0.29.1-tol, 0.29.1-avg) ------------------------

FAR = 100000.05


def _far_pair(tmp_path, *, steps=(7,)):
    """A unit square 1e5 from the origin: a float32 VTK and a native printed at 7 digits.

    X = 100000.05 prints as 1.000000E+05 (0.05 off) and its float32 value is
    100000.0547, so the two differ by 0.0547, more than four single-precision
    epsilons of the magnitude (0.0477) allow and inside the printed-precision
    slack this package states.
    """
    import numpy as np

    from pyflightstream.results.surface import write_vtk_surface
    from tests.tier1_offline.test_native_nodal_surface import _native_at, _vtk

    square = _vtk()
    truth = square.points + np.array([FAR, 0.0, 0.0])
    from dataclasses import replace

    written = replace(square, points=truth.astype(np.float32).astype(float))
    vtk, native = {}, {}
    for step in steps:
        vtk[step] = write_vtk_surface(tmp_path / f"p_iteration={step}.vtk", written, title="far")
        native[step] = _native_at(tmp_path / f"n_iteration={step}.dat", truth, spelling=".6E")
    return vtk, native, written


def test_p0320_tol_0291_one_function_gives_the_printed_precision_slack(tmp_path):
    """P0320-TOL-0291: a native far from the origin is granted the slack its printing costs."""
    import numpy as np

    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        native_match_tolerance,
        native_printed_digits,
        read_native_tecplot_surface,
    )

    vtk, native, written = _far_pair(tmp_path)
    surface = read_native_tecplot_surface(native[7])
    magnitude = float(np.abs(surface.points[:, 0]).max())
    assert native_printed_digits(native[7]) == 7
    # Without the digits the rule is the one it always was: it cannot match.
    plain = native_match_tolerance(surface.points)
    assert plain[0] == pytest.approx(4 * np.finfo(np.float32).eps * magnitude)
    with pytest.raises(PyflightstreamError, match="missing or ambiguous"):
        attach_native_strength(written, surface)
    # Told the digits, the slack is half a unit of the last one plus the float32 rounding.
    limits = native_match_tolerance(surface.points, printed_digits=7)
    assert limits[0] >= 5e-7 * magnitude
    assert limits[0] > plain[0]
    assert limits[1] == pytest.approx(plain[1]) and limits[1] < 1e-5
    joined, record = attach_native_strength(written, surface, coordinate_tolerance=limits)
    assert record["coordinate_tolerance_by_axis"] == pytest.approx(limits.tolist())
    assert joined.point_data["Singularity_strength"].tolist() == [10.0, 20.0, 30.0, 40.0]


def test_p0320_tol_0291_a_full_precision_native_adds_no_slack(tmp_path):
    """P0320-TOL-0291: sixteen printed digits leave the default rule as it was."""
    import numpy as np

    from pyflightstream.results.native_surface import (
        native_match_tolerance,
        native_printed_digits,
    )
    from tests.tier1_offline.test_native_nodal_surface import _native_at, _vtk

    truth = _vtk().points + np.array([FAR, 0.0, 0.0])
    path = _native_at(tmp_path / "full.dat", truth)
    digits = native_printed_digits(path)
    assert digits is not None and digits >= 16
    assert native_match_tolerance(truth, printed_digits=digits)[0] == pytest.approx(
        native_match_tolerance(truth)[0]
    )


def test_p0320_avg_0291_the_time_average_matches_a_far_native_with_that_tolerance(tmp_path):
    """P0320-AVG-0291: the time-averaged native strength uses the same tolerance function."""
    from pyflightstream.post.surfaces import average_surface_exports
    from pyflightstream.results.native_surface import (
        native_match_tolerance,
        read_native_tecplot_surface,
    )
    from pyflightstream.results.surface import REFERENCE_FRAME

    vtk, native, _ = _far_pair(tmp_path, steps=(7, 8))
    result = average_surface_exports(
        vtk, window=(7, 8), frame=REFERENCE_FRAME, native_exports=native
    )
    assert result.surface.point_data["Singularity_strength"].tolist() == [10.0, 20.0, 30.0, 40.0]
    expected = native_match_tolerance(
        read_native_tecplot_surface(native[7]).points, printed_digits=7
    )
    assert result.native_matching is not None
    assert result.native_matching[7]["coordinate_tolerance_by_axis"] == pytest.approx(
        expected.tolist()
    )


def test_p0320_arch2_s2_the_default_drift_limit_is_public_in_cases():
    """P0320-ARCH2-S2: DEFAULT_DRIFT_LIMIT_PCT is in cases.__all__ and is the field's default."""
    from pyflightstream import cases
    from pyflightstream.cases import DEFAULT_DRIFT_LIMIT_PCT, PerRevolutionSpec

    assert "DEFAULT_DRIFT_LIMIT_PCT" in cases.__all__
    assert DEFAULT_DRIFT_LIMIT_PCT == 1.0
    assert PerRevolutionSpec.model_fields["drift_limit_pct"].default == DEFAULT_DRIFT_LIMIT_PCT


def test_p0320_qa2_2_the_na_shares_read_clocking_zero_rows_only(tmp_path):
    """P0320-QA2-2: a wheel's table holds every clocking, and the shares are clocking 0's alone.

    Clocking 0 is the point's own solve. The rows of clocking 2 carry other
    forces and one NA force; if the filter did not hold, the shares would mix
    the two solves or read NA for a gap that is not the point's.
    """
    from pyflightstream.post import qsteady as post_qsteady
    from tests.tier1_offline.test_goal036_thrust_axis import (
        HEADER,
        STATIONS,
        _layout,
        _record,
        _share,
    )
    from tests.tier1_offline.test_goal036_thrust_axis import STRIPS as STRIP_LENGTHS

    forces = ((1.0, 10.0), (1.0, 20.0), (1.0, 30.0), (50.0, 40.0))
    other = ((9.0, 90.0), (9.0, "NA"), (9.0, 5.0), (9.0, 1.0))

    def rows(block, clocking):
        return [
            f"9001,60,Blade1,XZ,PROP,NA,{r},{c},0,0,{fx},{fz},0,{clocking}"
            for (r, c), (fx, fz) in zip(STATIONS, block, strict=True)
        ]

    table = tmp_path / "s.csv"
    table.write_text(
        "\n".join([HEADER + ",CLOCKING", *rows(forces, 0), *rows(other, 2)]) + "\n",
        encoding="utf-8",
    )
    validity = post_qsteady.add_reduced_frequency_to_sections(
        table,
        _record(letter="Z", axis=(0.0, 0.0, 1.0)),
        velocity_m_per_s=30.0,
        layout=_layout("PROP_RMRP1"),
    )
    assert validity is not None and validity.notes == ()
    thrust = [fz * w for (_fx, fz), w in zip(forces, STRIP_LENGTHS, strict=True)]
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(_share(thrust))


# --- the quasi-steady products state J (P0320-QS-J) ------------------------------


def _qs_tables(tmp_path, condition):
    """Write the two tables of the wheel fixture (1200 rev/min, D 2 m) at ``condition``."""
    from pyflightstream.post import qsteady as post_qsteady
    from pyflightstream.post._tables import ReferenceValues
    from pyflightstream.post.products import rotor_shaft_loads
    from tests.tier1_offline.test_goal035_qsteady_rotor import _clocked_point

    reference = ReferenceValues(sref_m2=3.14, cref_m=0.2, bref_m=2.0)
    record, folder = _clocked_point(tmp_path)
    clockings = post_qsteady.clockings_of(
        record, folder, reference=reference, density_kg_m3=1.2, shaft_loads=rotor_shaft_loads
    )
    point = post_qsteady.WheelPoint(
        pol="9001",
        condition=condition,
        record=record,
        clockings=clockings,
        validity=post_qsteady.PointValidity({"K_1P_MAX": 0.25, "K_1P_SOURCE": "mesh"}),
    )
    post_qsteady.write_qsteady_tables(
        tmp_path / "pos.csv", tmp_path / "avg.csv", [point], reference=reference
    )
    out = {}
    for name in ("pos", "avg"):
        head, *rows = (tmp_path / f"{name}.csv").read_text().splitlines()
        heading = head.split(",")
        out[name] = [dict(zip(heading, line.split(","), strict=True)) for line in rows]
    return out


def test_p0320_qs_j_a_wheel_point_states_its_j_from_its_own_speed_and_diameter(tmp_path):
    """P0320-QS-J: J = V / (n D) = 30 / (20 x 2) = 0.75, never NA with a speed and a free stream."""
    tables = _qs_tables(tmp_path, {"ALPHA": 5.0, "VINF": 30.0})
    for name in ("pos", "avg"):
        for row in tables[name]:
            assert float(row["J"]) == pytest.approx(0.75)
            assert float(row["J_CLOCK"]) == pytest.approx(0.75)
            assert float(row["RPM_CLOCK"]) == pytest.approx(1200.0)


def test_p0320_qs_j_a_requested_j_is_kept_and_a_missing_free_stream_stays_na(tmp_path):
    """P0320-QS-J: the row's own J is not overwritten, and nothing is invented without a V."""
    kept = _qs_tables(tmp_path, {"ALPHA": 5.0, "VINF": 30.0, "ADVANCE_RATIO": 0.8})
    assert float(kept["avg"][0]["J"]) == pytest.approx(0.8)
    assert float(kept["avg"][0]["J_CLOCK"]) == pytest.approx(0.75)
    bare = tmp_path / "bare"
    bare.mkdir()
    unknown = _qs_tables(bare, {"ALPHA": 5.0})
    assert unknown["avg"][0]["J"] == "NA" and unknown["avg"][0]["J_CLOCK"] == "NA"


# --- review of package J: the gaps the mutants found ---------------------------------


def test_p0320_qs_j_the_ratio_uses_the_magnitude_of_the_speed_and_refuses_what_is_not_a_number():
    """P0320-QS-J: J = V / (n D) with |n|; a missing or unusable input gives None."""
    from pyflightstream.post._tables import rotor_advance_ratio

    assert rotor_advance_ratio(30.0, 1200.0, 2.0) == pytest.approx(0.75)
    assert rotor_advance_ratio(30.0, -1200.0, 2.0) == pytest.approx(0.75)
    for bad in (
        (None, 1200.0, 2.0),
        (30.0, None, 2.0),
        (30.0, 1200.0, None),
        (30.0, 0.0, 2.0),
        (30.0, 1200.0, 0.0),
        (30.0, 1200.0, -2.0),
        (True, 1200.0, 2.0),
        (30.0, float("nan"), 2.0),
        (float("inf"), 1200.0, 2.0),
        ("30", 1200.0, 2.0),
    ):
        assert rotor_advance_ratio(*bad) is None, bad


def test_p0320_tol_0291_the_printed_digits_are_refused_when_not_a_positive_whole_number():
    """P0320-TOL-0291: a bool, a float or fewer than one digit is refused, never guessed."""
    import numpy as np

    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.results.native_surface import native_match_tolerance

    points = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    for bad in (0, -3, True, 7.0):
        with pytest.raises(PyflightstreamError, match="digits"):
            native_match_tolerance(points, printed_digits=bad)  # type: ignore[arg-type]


def test_p0320_tol_0291_a_native_of_short_exact_numbers_states_no_precision(tmp_path):
    """P0320-TOL-0291: whole numbers are exact, not a one-digit print, so no half-magnitude slack.

    A file that prints 100000 and 101000 shows one and two digits by their
    text, but they are exact values. A print precision below four
    digits is not stated, because it would grant half the coordinate as slack.
    """
    import numpy as np

    from pyflightstream.results.native_surface import (
        native_match_tolerance,
        native_printed_digits,
    )
    from tests.tier1_offline.test_native_nodal_surface import _native_at, _vtk

    truth = _vtk().points * 1000.0 + np.array([100000.0, 0.0, 0.0])
    path = _native_at(tmp_path / "whole.dat", truth, spelling=".0f")
    digits = native_printed_digits(path)
    assert digits is None
    limits = native_match_tolerance(truth, printed_digits=digits)
    assert limits[0] < 1e-3 * float(np.abs(truth[:, 0]).max())
    missing = native_printed_digits(tmp_path / "absent.dat")
    assert missing is None
