"""The campaign instrument recognises a frozen solve in a native unsteady log.

pfs0240 row 2413 and row 2412 at alpha 10 froze: from some time step on, the velocity
and pressure residuals are exactly zero from the second inner iteration of every step,
and the loads are a constant. The expected steps come from the log's own layout (the
solver prints a step header, then one line per inner iteration with the two residuals
first), never from the instrument.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "measure_campaign_coherence", ROOT / "scripts" / "measure_campaign_coherence.py"
)
coherence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coherence)  # type: ignore[union-attr]


def _step(n: int, total: int, residuals: list[tuple[str, str]]) -> str:
    lines = [
        f"Solving unsteady time-step iteration ({n}/{total})...",
        " ",
        "Iteration  Res. Vel.  Res. Pres.  CL",
    ]
    for k, (vel, pres) in enumerate(residuals, start=100 * n):
        lines.append(f"{k}               \t{vel}      \t{pres}      \t-3.7E-5")
    return "\n".join(lines) + "\n"


LIVE = [
    ("+5.5597573E-4", "+5.6313020E-4"),
    ("+7.8795882E-6", "+2.0446362E-5"),
    ("+1.8103714E-5", "+8.6087889E-6"),
]
DEAD = [
    ("+3.1809946E-2", "+1.9365193E-2"),
    ("+0.0000000E+0", "+4.7449983E-6"),
    ("+0.0000000E+0", "+0.0000000E+0"),
    ("+0.0000000E+0", "+0.0000000E+0"),
]
DEAD_FROM_TWO = [
    ("+3.1809946E-2", "+1.9365193E-2"),
    ("+0.0000000E+0", "+0.0000000E+0"),
    ("+0.0000000E+0", "+0.0000000E+0"),
]


def test_a_log_that_freezes_names_every_frozen_step(tmp_path: Path) -> None:
    log = tmp_path / "P9999-M144RE438AL+000BE+000_log.txt"
    log.write_text(
        _step(1, 4, LIVE)
        + _step(2, 4, DEAD)
        + _step(3, 4, DEAD_FROM_TWO)
        + _step(4, 4, DEAD_FROM_TWO),
        encoding="latin-1",
    )
    # Step 2 is the ONSET, laid out as pfs0240 row 2413's step 60 is in its log: one
    # live iteration, one where only the pressure residual is left, zeros after. It
    # counts, since every iteration after the first two is zero.
    assert coherence.frozen_steps(log) == [2, 3, 4]


def test_a_step_whose_pressure_still_moves_is_not_frozen(tmp_path: Path) -> None:
    # BOTH residuals must sit at zero: the velocity residual reaching zero while the
    # pressure one still falls is a solve still iterating.
    moving = [
        ("+3.1809946E-2", "+1.9365193E-2"),
        ("+0.0000000E+0", "+4.7449983E-6"),
        ("+0.0000000E+0", "+2.1000000E-6"),
        ("+0.0000000E+0", "+9.0000000E-7"),
    ]
    log = tmp_path / "P9999-M144RE438AL+000BE+000_log.txt"
    log.write_text(_step(1, 1, moving), encoding="latin-1")
    assert coherence.frozen_steps(log) == []


def test_a_live_log_has_no_frozen_step(tmp_path: Path) -> None:
    log = tmp_path / "P9999-M144RE438AL+000BE+000_log.txt"
    log.write_text(_step(1, 2, LIVE) + _step(2, 2, LIVE), encoding="latin-1")
    assert coherence.frozen_steps(log) == []
