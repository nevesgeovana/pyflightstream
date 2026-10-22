"""Exploratory compact loading-noise products of recorded quasi-steady wheels."""

from __future__ import annotations

import math
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
    return times, _observer_signals(ctx, spec, key, times=times, motion=motion, load=load)


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
            times, signals = _point_signals(ctx, spec, point, key)
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
                    (ctx.sim_id, *context, time, pressure)
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
