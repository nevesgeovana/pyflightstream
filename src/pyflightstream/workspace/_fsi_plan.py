"""Solver-free structural quantities for the workspace pre-flight."""

from __future__ import annotations

import math

from pyflightstream.fsi.centrifugal import rotating_frequencies
from pyflightstream.fsi.config import FsiConfig


def structural_assessment(config: FsiConfig) -> dict[str, object]:
    """Report effective station properties, modes and excitation ratios.

    The modal calculation uses the existing rotating beam model, including
    centrifugal stiffness. The warning is a quasi-static validity screen,
    not a claim of dynamic stability or licensed coupling validation.
    """
    modes = rotating_frequencies(config)
    frequencies = modes.frequencies_rad_per_s
    ratios = {
        str(order): [order * config.omega_rad_per_s / frequency for frequency in frequencies]
        for order in sorted({1, config.blade_count})
    }
    warnings = [
        f"Excitation order {order}, mode {index + 1}: n Omega / omega_n = {ratio:.6g} "
        "exceeds 0.3; a quasi-static structural response may be inadequate."
        for order, values in ratios.items()
        for index, ratio in enumerate(values)
        if ratio > 0.3
    ]
    return {
        "station_properties": config.blade.model_dump(mode="json"),
        "natural_frequencies_hz": [value / (2 * math.pi) for value in frequencies],
        "mode_kinds": list(modes.kinds),
        "excitation_frequency_ratios": ratios,
        "warnings": warnings,
    }
