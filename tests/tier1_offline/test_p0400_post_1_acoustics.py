"""P0400-ACOUSTICPRECISION (PFS-2105.032): the acoustic tables round-trip their numbers.

Written at five fixed decimals, a 30 kHz clock alternated between 3e-5 and
4e-5 s steps and a 4e-6 Pa harmonic was written as 0.00000.
"""

from __future__ import annotations

import csv
import math

import pytest

from pyflightstream.cases.acoustics import AcousticSignal
from pyflightstream.post.acoustics import write_acoustic_products


@pytest.mark.parametrize((), [pytest.param(id="P0400-ACOUSTICPRECISION")])
def test_p0400_acousticprecision_time_and_micro_pascals_survive(tmp_path):
    """P0400-ACOUSTICPRECISION: TIME_S at a 1e-5 s step and a 1e-6 Pa amplitude read back."""
    rate, samples = 100_000.0, 200
    times = tuple(n / rate for n in range(samples))
    pressure = tuple(1e-6 * math.cos(2 * math.pi * 5000.0 * t) for t in times)
    signal = AcousticSignal("m", 1.0, 0.0, 0.0, times, pressure)
    write_acoustic_products([signal], tmp_path, stem="P1", rotors={})
    (table,) = tmp_path.glob("P1_01_*_pressure.csv")
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row["TIME_S"]) for row in rows] == list(times)
    assert [float(row["PRESSURE_PA"]) for row in rows] == list(pressure)
    (spectrum,) = tmp_path.glob("P1_01_*_spectrum.csv")
    with spectrum.open(encoding="utf-8", newline="") as handle:
        peak = max(float(row["AMPLITUDE_PA"]) for row in csv.DictReader(handle))
    assert abs(peak - 1e-6) < 1e-9, peak
