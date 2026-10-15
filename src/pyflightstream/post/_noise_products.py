"""Exploratory compact loading-noise products of recorded quasi-steady wheels."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.qsteady import QsteadyRecord, read_qsteady_record
from pyflightstream.post._tables import write_csv_table
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


def noise_products(ctx: SimContext) -> None:
    """Write requested pressure histories, never claiming licensed validation."""
    spec = ctx.pproc.noise
    if spec is None:
        return
    for point in ctx.points:
        key = f"noise/{point.name}"
        record = ctx.record_of[point.name]
        try:
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
            if isinstance(clockings, str):
                raise ValueError(clockings)
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
            signals = [
                rotor_loading_noise(
                    times,
                    observer,
                    motion,
                    load,
                    c0=spec.sound_speed_m_s,
                    observer_velocity_m_s=spec.observer_velocity_m_s,
                )
                for observer in spec.observers_m
            ]
            if not all(np.isfinite(signal).all() for signal in signals):
                raise ValueError("loading-noise pressure is not finite at the requested observer")
        except (OSError, ValueError, PyflightstreamError) as error:
            ctx.skipped[key] = str(error)
            continue
        for index, signal in enumerate(signals, start=1):
            target = ctx.target(ctx.out / f"{key}_observer_{index}.csv")
            write_csv_table(
                target, ("time_s", "pressure_pa"), list(zip(times, signal, strict=True))
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
