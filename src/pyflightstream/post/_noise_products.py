"""Exploratory compact loading-noise products of recorded quasi-steady wheels."""

from __future__ import annotations

import csv
import math
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream._tokens import CONTEXT_COLUMNS, POLAR_ID_COLUMN
from pyflightstream.cases.qsteady import QsteadyRecord, read_qsteady_record
from pyflightstream.post._tables import context_row, write_csv_table
from pyflightstream.post.axes import clocked_blade_azimuth_deg
from pyflightstream.post.polar import PolarPoint
from pyflightstream.post.qsteady import Clocking, clockings_of
from pyflightstream.post.qsteady_noise import (
    RotorMotion,
    compare_signals,
    gutin_harmonic_rms,
    reconstruct_blade_load,
    rotor_loading_noise,
)
from pyflightstream.post.rotor_table import rotor_shaft_loads
from pyflightstream.workspace import RunRecord

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext


def _point_signals(ctx: SimContext, spec: Any, point: PolarPoint, key: str):
    """Return the sample times and observer signals of one point, or raise its refusal."""
    record = ctx.record_of[point.name]
    if record.recipe != "qsteady_rotor":
        raise ValueError("exploratory loading noise requires a recorded quasi-steady wheel")
    quasi = read_qsteady_record(point.loads_path)
    if quasi.case != "wheel" or not np.allclose(quasi.axis_vector, (1, 0, 0)):
        raise ValueError("loading-noise reconstruction currently requires a wheel about +X")
    density = _recorded_density(point, record)
    clockings = clockings_of(
        quasi,
        point.loads_path.parent,
        reference=ctx.reference,
        density_kg_m3=float(density),
        shaft_loads=rotor_shaft_loads,
    )
    azimuths, forces, moments = _blade_load_samples(quasi, clockings)
    load = reconstruct_blade_load(
        azimuths,
        forces,
        moments,
        axis=quasi.axis_vector,
        reference=(0, 0, 1),
        orders=spec.orders,
        axial_radius_m=spec.axial_radius_m,
        inplane_radius_m=spec.inplane_radius_m,
    )
    omega = quasi.rpm * 2 * math.pi / 60
    if omega == 0:
        raise ValueError("loading noise requires nonzero rotor speed")
    motion = RotorMotion(
        blades=quasi.blades,
        omega_rad_s=omega,
        azimuth0_deg=quasi.blade1_azimuth_deg,
        axis=quasi.axis_vector,
        reference=(0, 0, 1),
        hub_m=quasi.hub_m,
        hub_velocity_m_s=spec.hub_velocity_m_s,
    )
    times = (
        np.arange(spec.samples_per_revolution)
        * (2 * math.pi / abs(omega))
        / spec.samples_per_revolution
    )
    return (
        times,
        _observer_signals(ctx, spec, key, times=times, motion=motion, load=load),
        motion,
        load,
    )


def _observer_signals(ctx: SimContext, spec: Any, key: str, *, times, motion, load):
    """Return the signal of each observer; an unusable observer costs only its own file."""
    signals: list[tuple[int, np.ndarray]] = []
    for index, observer in enumerate(spec.observers_m, start=1):
        # ONE UNUSABLE OBSERVER COSTS ONLY ITS OWN FILE: the others are independent.
        try:
            signal = rotor_loading_noise(
                times,
                observer,
                motion,
                load,
                c0=spec.sound_speed_m_s,
                observer_velocity_m_s=spec.observer_velocity_m_s,
            )
            if not np.isfinite(signal).all():
                raise ValueError("loading-noise pressure is not finite at the requested observer")
        except (ValueError, PyflightstreamError) as error:
            ctx.skipped[f"{key}_observer_{index}.csv"] = str(error)
            continue
        signals.append((index, signal))
    return signals


def noise_products(ctx: SimContext) -> None:
    """Write requested pressure histories, never claiming licensed validation."""
    spec = ctx.pproc.noise
    if spec is None:
        return
    for point in ctx.points:
        key = f"noise/{point.name}"
        try:
            times, signals, motion, load = _point_signals(ctx, spec, point, key)
        except (OSError, ValueError, PyflightstreamError) as error:
            ctx.skipped[key] = str(error)
            continue
        # POL AND THE CONDITION LEAD EVERY TABLE THE POST WRITES.
        context = context_row(ctx.condition(point), ctx.reference.as_lengths())
        for index, signal in signals:
            target = ctx.target(ctx.out / f"{key}_observer_{index}.csv")
            write_csv_table(
                target,
                (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, "time_s", "pressure_pa"),
                [
                    (ctx.sim_id, *context, format(time, ".17g"), format(pressure, ".17g"))
                    for time, pressure in zip(times, signal, strict=True)
                ],
            )
            ctx.add(
                target,
                {
                    "runs": ctx.sources[point.name],
                    "kind": "loading_noise",
                    "validation": "exploratory, not validated",
                    "terms": "loading only, no thickness",
                    "observer_m": spec.observers_m[index - 1],
                },
            )
            _observer_products(
                ctx, spec, point, index, times=times, signal=signal, motion=motion, load=load
            )


def _observer_products(ctx, spec, point, index, *, times, signal, motion, load):
    """Write independent harmonic and optional comparison products, with named skips."""
    stem = f"noise/{point.name}_observer_{index}"
    context = context_row(ctx.condition(point), ctx.reference.as_lengths())
    for kind, suffix, make in (
        (
            "loading_noise_harmonics",
            "harmonics",
            lambda: _harmonic_rows(spec, index, signal, motion, load),
        ),
        (
            "loading_noise_comparison",
            "comparison",
            lambda: _comparison_rows(ctx, spec, index, times, signal),
        ),
    ):
        key = f"{stem}_{suffix}.csv"
        try:
            result = make()
            if result is None:
                continue
            columns, rows, notes = result
            target = ctx.target(ctx.out / key)
            write_csv_table(
                target,
                (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *columns),
                [(ctx.sim_id, *context, *_noise_cells(row)) for row in rows],
            )
            ctx.add(
                target,
                {
                    "runs": ctx.sources[point.name],
                    "kind": kind,
                    "validation": "exploratory, not validated",
                    "notes": notes,
                },
            )
            for note in notes:
                ctx.skipped[f"{key}: Gutin comparison"] = note
        except (OSError, ValueError, PyflightstreamError) as error:
            ctx.skipped[key] = str(error)


def _noise_cells(row):
    """Preserve small acoustic quantities and sample clocks through the text writer."""
    return [format(value, ".17g") if isinstance(value, float) else value for value in row]


def _harmonic_rows(spec, index, signal, motion, load):
    columns = ("HARMONIC", "BPF_ORDER", "FREQ_HZ", "RMS_PA", "GUTIN_RMS_PA", "RATIO")
    if spec.gutin_orders * motion.blades >= len(signal) / 2:
        raise ValueError(
            f"gutin_orders={spec.gutin_orders}: increase samples_per_revolution "
            "so every requested blade-passage harmonic is below Nyquist"
        )
    spectrum = np.fft.rfft(signal) / len(signal)
    moving = any(value != 0 for value in motion.hub_velocity_m_s)
    notes = (
        ["Gutin columns NA: the hub moves relative to the medium; Gutin requires a hub at rest"]
        if moving
        else []
    )
    observer = np.asarray(spec.observers_m[index - 1]) - np.asarray(motion.hub_m)
    distance = float(np.linalg.norm(observer))
    theta = math.acos(float(np.clip(np.dot(observer, motion.axis) / distance, -1, 1)))
    rows = []
    for order in range(1, spec.gutin_orders + 1):
        harmonic = order * motion.blades
        rms = float(abs(spectrum[harmonic]) * math.sqrt(2))
        gutin = (
            None
            if moving
            else gutin_harmonic_rms(
                harmonic,
                blades=motion.blades,
                omega_rad_s=abs(motion.omega_rad_s),
                c0=spec.sound_speed_m_s,
                distance_m=distance,
                theta_rad=theta,
                axial_force_n=load.axial.mean,
                tangential_force_n=load.tangential.mean * (1 if motion.omega_rad_s > 0 else -1),
                axial_radius_m=load.axial_radius_m,
                inplane_radius_m=load.inplane_radius_m,
            )
        )
        rows.append(
            (
                harmonic,
                order,
                harmonic * abs(motion.omega_rad_s) / (2 * math.pi),
                rms,
                "NA" if gutin is None else gutin,
                rms / gutin if gutin else "NA",
            )
        )
    return columns, rows, notes


def _comparison_rows(ctx, spec, index, times, signal):
    if spec.reference is None or not spec.reference[index - 1]:
        return None
    stated = spec.reference[index - 1]
    root = ctx.workspace.root.resolve()
    path = (root / stated).resolve()
    if Path(stated).is_absolute() or not path.is_relative_to(root):
        raise ValueError(
            f"noise reference {stated!r}: use a workspace-relative CSV inside the workspace"
        )
    values = _reference_values(path, stated)
    period = float((times[1] - times[0]) * len(times))
    sampled = _last_revolution(values, times, period, stated)
    comparison = asdict(compare_signals(sampled, signal))
    return tuple(comparison), [tuple("NA" if v is None else v for v in comparison.values())], []


def _reference_values(path, stated):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        clocks = [name for name in fields if name.lower() == "time_s"]
        pressures = [name for name in fields if name.lower() == "pressure_pa"]
        if len(clocks) != 1 or len(pressures) != 1:
            raise ValueError(
                f"noise reference {stated}: needs time_s and pressure_pa columns in SI"
            )
        try:
            return np.asarray([(float(row[clocks[0]]), float(row[pressures[0]])) for row in reader])
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"noise reference {stated}: invalid numeric time or pressure: {error}"
            ) from error


def _last_revolution(values, times, period, stated):
    if values.ndim != 2 or values.shape[0] < 2 or not np.isfinite(values).all():
        raise ValueError(f"noise reference {stated}: needs at least two finite time/pressure rows")
    t, p = values[:, 0], values[:, 1]
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"noise reference {stated}: time_s must increase strictly")
    if t[-1] - t[0] < period * (1 - 1e-10):
        raise ValueError(
            f"noise reference {stated}: shorter than one full revolution ({period:g} s)"
        )
    start = t[-1] - period
    # Include an interpolated boundary, and keep absolute clock phase modulo
    # the period. A clock-origin offset therefore remains visible in correlation.
    inside = (t > start) & (t < t[-1])
    cycle_t = np.r_[start, t[inside], t[-1]]
    cycle_p = np.r_[np.interp(start, t, p), p[inside], p[-1]]
    target = start + np.mod(times - start, period)
    return np.interp(target, cycle_t, cycle_p)


def _blade_load_samples(quasi: QsteadyRecord, clockings: list[Clocking]):
    """Collect complete per-blade force and moment samples in clocking order."""
    azimuths, forces, moments = [], [], []
    for clocking in clockings:
        for blade in range(1, quasi.blades + 1):
            azimuth = clocked_blade_azimuth_deg(
                quasi.blade1_azimuth_deg,
                blade=blade,
                blades=quasi.blades,
                clocking=clocking.index,
                positions=len(clockings),
                rpm=quasi.rpm,
            )
            values = clocking.loads[8 * blade : 8 * blade + 6]
            if azimuth is None or len(values) != 6 or any(value is None for value in values):
                raise ValueError("noise reconstruction needs each blade's force and hub moment")
            azimuths.append(azimuth)
            forces.append([float(value) for value in values[:3] if value is not None])
            moments.append([float(value) for value in values[3:] if value is not None])
    return azimuths, forces, moments


def _recorded_density(point: PolarPoint, record: RunRecord) -> float:
    """Resolve the point density with the same recorded fallback as its loads."""
    density = point.state.density_kg_m3 if point.state is not None else record.density_kg_m3
    if density is None:
        density = record.density_kg_m3
    if density is None:
        raise ValueError("loading noise needs the recorded density")
    return density
