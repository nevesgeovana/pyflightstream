"""P0400-TREFFTZB (FR-452): the wake export, its crossings and the trace on them.

The wake exports here are written in the recorded format (VTK legacy ASCII
POLYDATA, POINTS, two-point LINES, one CELL_DATA scalar
``Normalized_Vorticity``) with synthetic values: one straight line per
trailing-edge station, or a sheet whose lines roll up, so the expected trace is
known in closed form. No recorded research export enters the repository.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.farfield import (
    calibration_scale,
    trace_coefficients,
    trace_forces,
    wake_crossings,
)
from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.wake import parse_wake_export

RHO = 1.2
V = 30.0
SPAN = 10.0
Q = 0.5 * RHO * V * V


def _stations(per_side: int = 20) -> np.ndarray:
    h = (SPAN / 2.0) / per_side
    return -SPAN / 2.0 + h * (np.arange(2 * per_side) + 0.5)


def _vtk(lines: list[np.ndarray], values: list[float], *, shared: bool = True) -> str:
    """Write wake lines in the recorded format; ``shared`` reuses a node between segments."""
    points: list[np.ndarray] = []
    segments: list[tuple[int, int]] = []
    cell_values: list[float] = []
    for line, value in zip(lines, values, strict=True):
        if shared:
            base = len(points)
            points.extend(line)
            segments += [(base + k, base + k + 1) for k in range(len(line) - 1)]
        else:
            for k in range(len(line) - 1):
                base = len(points)
                points += [line[k], line[k + 1]]
                segments.append((base, base + 1))
        cell_values += [value] * (len(line) - 1)
    rows = [
        "# vtk DataFile Version 3.0",
        "FlightStream wakes",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(points)} float",
        *(f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g}" for p in points),
        f"LINES {len(segments)} {3 * len(segments)}",
        *(f"2 {a} {b}" for a, b in segments),
        f"CELL_DATA {len(segments)}",
        "SCALARS Normalized_Vorticity float 1",
        "LOOKUP_TABLE default",
        *(f"{value:.9g}" for value in cell_values),
    ]
    return "\n".join(rows) + "\n"


def _straight_wake(y: np.ndarray, values: np.ndarray, length: float = 30.0) -> list[np.ndarray]:
    x = np.linspace(0.0, length, 31)
    return [np.column_stack([x, np.full_like(x, yi), np.zeros_like(x)]) for yi in y]


@pytest.mark.requirement("FR-452")
@pytest.mark.parametrize("shared", [True, False])
def test_p0400_trefftzb_the_reader_chains_the_segments_into_one_line_per_station(shared):
    """P0400-TREFFTZB (FR-452 R1): one line per trailing-edge node, its one value."""
    y = _stations(5)
    values = np.sqrt(1.0 - (2.0 * y / SPAN) ** 2)
    wake = parse_wake_export(_vtk(_straight_wake(y, values), list(values), shared=shared))
    assert len(wake.lines) == len(y)
    order = np.argsort([line[0, 1] for line in wake.lines])
    assert np.allclose(np.asarray(wake.values)[order], values, rtol=1e-8)
    for line in wake.lines:
        assert line.shape == (31, 3) and line[0, 0] == 0.0 and line[-1, 0] == 30.0


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_the_reader_refuses_what_is_no_wake():
    """P0400-TREFFTZB (FR-452 R1): counts, a varying value and polygons are each refused."""
    y = _stations(2)
    good = _vtk(_straight_wake(y, np.ones_like(y)), [1.0] * len(y))
    with pytest.raises(MalformedOutputError, match="LINES state"):
        parse_wake_export(good.replace(f"LINES {30 * len(y)} ", f"LINES {30 * len(y) + 1} "))
    with pytest.raises(IncompleteOutputError):
        parse_wake_export("\n".join(good.splitlines()[:8]) + "\n")
    varying = good.rsplit("1\n", 1)[0] + "1.5\n"
    with pytest.raises(MalformedOutputError, match="changes along one line"):
        parse_wake_export(varying)
    with pytest.raises(MalformedOutputError, match="POLYGONS"):
        parse_wake_export(good.replace("LINES", "POLYGONS 1 4\n3 0 1 2\nLINES", 1))


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_each_line_is_cut_at_its_first_crossing():
    """P0400-TREFFTZB (FR-452 R3): linear interpolation on the straddling segment."""
    line = np.array([[0.0, 1.0, 0.0], [2.0, 1.0, 0.2], [4.0, 1.0, 0.6], [1.0, 1.0, 1.0]])
    other = np.array([[0.0, 2.0, 0.0], [4.0, 2.0, 0.4]])
    trace = wake_crossings([line, other], np.array([1.0, 2.0]), x_t=3.0)
    assert trace.problem is None
    assert trace.z[0] == pytest.approx(0.4)
    assert trace.z[1] == pytest.approx(0.3)


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_a_line_ending_before_the_plane_makes_the_row_na():
    """P0400-TREFFTZB (FR-452 R3): never a trace of the lines that did reach."""
    short = np.array([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
    long = np.array([[0.0, 2.0, 0.0], [5.0, 2.0, 0.0]])
    trace = wake_crossings([short, long], np.array([1.0, 1.0]), x_t=3.0)
    assert trace.short == 1 and "end before the plane" in trace.problem
    assert trace.y.size == 0


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_a_rolled_up_sheet_keeps_the_order_of_its_starts():
    """P0400-TREFFTZB (FR-452 R4): ordered by the trailing edge, not by the crossing."""
    y0 = np.linspace(-1.0, 1.0, 9)
    lines = []
    for k, y in enumerate(y0):
        # Each line turns about the tip region: outboard lines cross inboard of
        # their neighbours, so the crossing order is not the start order.
        twist = 0.4 * (k / 8.0) ** 4
        end_y = y * math.cos(6.0 * twist) - 0.3 * math.sin(6.0 * twist)
        end_z = y * math.sin(6.0 * twist)
        lines.append(np.array([[0.0, y, 0.0], [4.0, end_y, end_z]]))
    values = np.arange(9.0)
    trace = wake_crossings(lines, values, x_t=4.0)
    assert trace.problem is None
    assert trace.values.tolist() == values.tolist()
    assert np.any(np.diff(trace.y) < 0.0), "the fixture does not roll up, so it proves nothing"


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_two_sheets_are_not_one_run():
    """P0400-TREFFTZB (FR-452 R4, R5): starts that interleave two sheets make the row NA."""
    wing = [np.array([[0.0, y, 0.0], [5.0, y, 0.0]]) for y in np.linspace(-5, 5, 21)]
    tail = [np.array([[4.0, y + 0.05, 1.0], [5.0, y + 0.05, 1.0]]) for y in np.linspace(-1, 1, 5)]
    trace = wake_crossings(wing + tail, np.ones(26), x_t=4.5)
    assert trace.problem is not None and "more than one wake sheet" in trace.problem


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_on_a_planar_trace_b_returns_a():
    """P0400-TREFFTZB (FR-452 R6): shed values at strip edges reconstruct A's loading."""
    y = _stations(20)
    gamma = 5.0 * np.sqrt(1.0 - (2.0 * y / SPAN) ** 2)
    edges = np.linspace(-SPAN / 2, SPAN / 2, len(y) + 1)
    shed = -np.diff(np.r_[0.0, gamma, 0.0])
    wake = parse_wake_export(_vtk(_straight_wake(edges, shed), list(shed)))
    trace = wake_crossings(list(wake.lines), wake.values, x_t=12.5)
    b = trace.forces(rho=RHO, v_inf=V)
    a = trace_forces(y, np.zeros_like(y), gamma, rho=RHO, v_inf=V)
    assert b.lift == pytest.approx(a.lift, rel=1e-8)
    assert b.induced_drag == pytest.approx(a.induced_drag, rel=1e-8)


@pytest.mark.requirement("FR-452")
def test_p0400_trefftzb_the_scale_is_calibrated_from_the_near_field_lift():
    """P0400-TREFFTZB (FR-452 R2): CL_T is the solver's, E_T does not see the scale."""
    y = _stations(20)
    raw = np.sqrt(1.0 - (2.0 * y / SPAN) ** 2)
    s_ref, cl_near = 8.0, 0.65
    base = trace_forces(y, np.zeros_like(y), raw, rho=RHO, v_inf=V)
    doubled = trace_forces(y, np.zeros_like(y), 2.0 * raw, rho=RHO, v_inf=V)
    results = []
    for trace in (base, doubled):
        k = calibration_scale(trace.lift, cl_near=cl_near, q=Q, s_ref=s_ref)
        scaled = trace.scaled(k)
        results.append(
            (
                k,
                trace_coefficients(
                    scaled.lift,
                    scaled.side_force,
                    scaled.induced_drag,
                    q=Q,
                    s_ref=s_ref,
                    b_ref=SPAN,
                ),
            )
        )
    (k1, c1), (k2, c2) = results
    assert c1["CL_T"] == pytest.approx(cl_near, rel=1e-12)
    assert k2 == pytest.approx(k1 / 2.0, rel=1e-12)
    assert c2["CDI_T"] == pytest.approx(c1["CDI_T"], rel=1e-12)
    raw_c = trace_coefficients(
        base.lift, base.side_force, base.induced_drag, q=Q, s_ref=s_ref, b_ref=SPAN
    )
    assert c1["E_T"] == pytest.approx(raw_c["E_T"], rel=1e-12)
    assert doubled.induced_drag == pytest.approx(4.0 * base.induced_drag, rel=1e-12)
    assert doubled.lift == pytest.approx(2.0 * base.lift, rel=1e-12)
    assert math.isnan(calibration_scale(base.lift, cl_near=0.0, q=Q, s_ref=s_ref))
    assert math.isnan(calibration_scale(base.lift, cl_near=float("nan"), q=Q, s_ref=s_ref))
