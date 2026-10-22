"""What a campaign plan reports per point, and the lines its summary prints.

Private to :mod:`pyflightstream.run`, whose plan module re-exports every
public name of it. :func:`point_facts` reads a point's rotors, quasi-steady
wheel, wake, streamlines, far field and default angles from its case; the
``*_line`` functions turn those records into the words the plan summary prints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from pyflightstream.cases import SimCase
from pyflightstream.cases.qsteady import summarise as summarise_validity
from pyflightstream.cases.qsteady import (
    summarise_inflow_harmonics,
)
from pyflightstream.cases.workflows import (
    WakeTermination,
    angles_not_stated,
    planned_run_wake,
    planned_wake,
    qsteady_validity,
    rotor_machs,
    streamline_count,
)
from pyflightstream.cases.workflows import plan_record as farfield_plan_record

PointPlan = Any  # the PointPlan of run._plan, which imports this module


def _point_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the per-point lines of the plan's summary in display order."""
    lines: list[str] = []
    lines += _mach_lines(points)
    lines += _validity_lines(points)
    lines += _wake_lines(points)
    lines += _angle_lines(points)
    return lines + _streamline_lines(points) + _farfield_lines(points)


def _mach_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the line of each rotor of each point: tip and helical Mach numbers (M1)."""
    return [
        f"  {entry.run_id}: {rotor_mach_line(alias, mach)}"
        for entry in points
        for alias, mach in entry.rotor_mach.items()
    ]


def _validity_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the lines of every quasi-steady wheel point.

    Each states the four values of its blade's 1P reduced frequency, or why the
    chord is not known.
    """
    lines: list[str] = []
    for entry in points:
        if entry.qsteady_validity:
            lines.append(f"  {entry.run_id}: {qsteady_validity_line(entry.qsteady_validity)}")
            harmonics = entry.qsteady_validity.get("inflow_fft")
            if isinstance(harmonics, Mapping):
                lines.append(f"  {entry.run_id}: {inflow_harmonics_line(harmonics)}")
    return lines


def _wake_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the wake termination line of each rotor point (FR-584), then the run length lines.

    A run length stated as a wake length states its count (FR-906).
    """
    lines = [
        f"  {entry.run_id}: {wake_termination_line(entry.wake_termination)}"
        for entry in points
        if entry.wake_termination
    ]
    lines += [
        f"  {entry.run_id}: {run_wake_length_line(entry.run_wake_length)}"
        for entry in points
        if entry.run_wake_length
    ]
    return lines


def _angle_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the line of each point whose flow angles take the default 0.0 degrees (FR-69)."""
    lines: list[str] = []
    for entry in points:
        if entry.angles_not_stated:
            shown = ", ".join(f"{name} = 0.0 (default)" for name in entry.angles_not_stated)
            lines.append(f"  {entry.run_id}: {shown}; the row states no such angle")
    return lines


def _streamline_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the plan's line per point that seeds off-body streamlines (FR-1079)."""
    return [
        f"  {entry.run_id}: {entry.streamlines} off-body streamlines traced "
        "(the [streamlines] lines and tubes of its pproc)"
        for entry in points
        if entry.streamlines
    ]


def _farfield_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return one line per far-field input a plan adds or cannot serve (FR-1047)."""
    lines: list[str] = []
    for entry in points:
        inputs = entry.farfield.get("inputs", ()) if entry.farfield else ()
        for item in cast(Sequence[Mapping[str, object]], inputs):
            if item.get("state") in ("added", "not_applicable", "refused"):
                lines.append(f"  {entry.run_id}: far field {farfield_line(item)}")
    return lines


def farfield_line(item: Mapping[str, object]) -> str:
    """Return one far-field input of the plan as its console line (FR-1047)."""
    what = item.get("source") or item.get("reason") or ""
    return f"{item.get('analysis')} {item.get('input')} {item.get('state')}: {what}".rstrip(": ")


def run_wake_length_line(run: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's run length from a wake length (FR-422).

    ``run`` is one :attr:`PointPlan.run_wake_length`: the length asked, the
    resolved step count and the revolutions it turns, and the V_ax with the
    rule that gave it. The length is nominal (FR-908), so the revolutions are
    what a user checks near hover.
    """
    return (
        f"run length RUN_WAKE_LENGTH_R = {run.get('length_r'):g} R: "
        f"{run.get('time_iterations')} steps, {run.get('revolutions'):.4g} revolution(s), "
        f"V_ax {run.get('v_ax_m_s'):.4g} m/s ({run.get('rule')}); "
        "nominal helical travel, not a measured wake length"
    )


def wake_termination_line(wake: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor point's wake termination (FR-584).

    ``wake`` is one :attr:`PointPlan.wake_termination`: the L asked, the V_ax
    used with the rule that gave it, and the steps emitted; a count states
    itself, its steps and the length it keeps over the run (FR-601).
    """
    steps, length, speed = wake.get("steps"), wake.get("length_r"), wake.get("v_ax_m_s")
    if not isinstance(length, int | float):
        kept = WakeTermination(**cast(dict[str, Any], wake)).count_kept_r()
        keeps = "an unknown length" if kept is None else f"about {kept:.3g} R"
        return f"wake termination {wake.get('stated_as')}: {steps} steps, keeping {keeps} of wake"
    if steps is None:
        return (
            f"wake termination L = {length:g} R ({wake.get('stated_as')}) not converted: "
            "no rotor radius is known, so no termination line is written"
        )
    used = f"{speed:.4g} m/s" if isinstance(speed, int | float) else "none"
    return (
        f"wake termination L = {length:g} R ({wake.get('stated_as')}), V_ax {used} "
        f"({wake.get('rule')}), {steps} steps"
    )


def qsteady_validity_line(validity: Mapping[str, object]) -> str:
    """Return the words the plan prints for one quasi-steady wheel point.

    ``validity`` is one :attr:`PointPlan.qsteady_validity`.
    """
    note = validity.get("note")
    if note:
        root, tip = validity.get("k_per_chord_m_root"), validity.get("k_per_chord_m_tip")
        known = (
            f"; k per metre of chord {root:.4f} at the root, {tip:.4f} at the tip"
            if isinstance(root, int | float) and isinstance(tip, int | float)
            else ""
        )
        return f"quasi-steady validity not computed: {note}{known}"
    return f"quasi-steady validity (1P reduced frequency): {summarise_validity(validity)}"


def inflow_harmonics_line(harmonics: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's ``--inflow-fft`` record.

    nP is counted on ONE BLADE (how many times it meets the perturbation per
    revolution), not the blade-passing N P of a fixed surface nor the rotor
    total (:mod:`pyflightstream.cases.qsteady`).
    """
    note = harmonics.get("note")
    if harmonics.get("n_max") is None:
        return f"inflow harmonics not computed: {note}"
    words = summarise_inflow_harmonics(harmonics)
    return f"{words}; {note}" if note else words


def rotor_mach_line(alias: str, mach: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor of one point (M1).

    ``mach`` is one entry of :attr:`PointPlan.rotor_mach`.
    """
    tip, helical = mach.get("mach_tip"), mach.get("mach_helical")
    kind = mach.get("kind") or "rotor"
    if isinstance(tip, int | float) and isinstance(helical, int | float):
        line = f"{kind} {alias} M_tip {tip:.3f}, M_hel {helical:.3f}"
        advancing = mach.get("mach_advancing")
        if isinstance(advancing, int | float):
            line += f", M_adv {advancing:.3f}"
            if mach.get("mach_advancing_bound") == "edgewise":
                line += " (rotor axis not resolved: the edgewise bound)"
        return line
    return f"{kind} {alias} M_tip and M_hel not computed: {mach.get('note')}"


def point_facts(
    point_case: SimCase, *, inflow_fft: bool, fs_version: str | None = None
) -> dict[str, Any]:
    """Return what a point's plan states about its rotors, wheel and wake, READY or not.

    The rotors' tip and helical Mach numbers (M1), a quasi-steady
    wheel's 1P reduced frequency and, on a rotor point, the wake its
    termination keeps (FR-584).
    """
    wake = planned_wake(point_case)
    run = planned_run_wake(point_case)
    return {
        "rotor_mach": {mach.alias: mach.record() for mach in rotor_machs(point_case)},
        "qsteady_validity": qsteady_validity(point_case, inflow_fft=inflow_fft) or {},
        "wake_termination": {} if wake is None else wake.record(),
        "run_wake_length": {} if run is None else run.record(),
        "streamlines": streamline_count(point_case),
        "farfield": {} if fs_version is None else farfield_plan_record(point_case, fs_version),
        "angles_not_stated": angles_not_stated(point_case),
    }
