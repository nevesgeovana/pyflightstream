"""Tier 1, 0.40.0 integration fixes: a requested velocity is compared at the printed precision."""

from __future__ import annotations

from pathlib import Path

from pyflightstream.results import bind_conditions, parse_loads

FIXTURE = Path(__file__).parent / "fixtures" / "loads_steady_26.120.txt"


def _export(printed: str) -> str:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        if line.strip().startswith("Freestream velocity (m/s)"):
            line = line.replace("30.000", printed)
        out.append(line)
    text = "".join(out)
    assert f"Freestream velocity (m/s)                   {printed}" in text
    return text


def test_p0400_a_velocity_is_held_to_the_digits_the_export_printed():
    """P0400-VELOCITY-PRINTED-PRECISION (PFS-2092.001): tolerance from the printed digits.

    The free-stream velocity was compared at 5e-4 m/s whatever width the export
    printed it with, so an export printing two decimals refused a requested
    velocity that rounds to the printed one. It is held to half a count of the
    printed digit; the three-decimal export keeps 5e-4 (the control).
    """
    coarse = parse_loads(_export("30.00"))
    assert coarse.print_tolerances == {"freestream_velocity_m_s": 0.005}
    assert not bind_conditions({"velocity": 30.003}, reported=coarse).mismatches
    assert bind_conditions({"velocity": 30.006}, reported=coarse).mismatches
    fine = parse_loads(_export("30.000"))
    assert abs(fine.print_tolerances["freestream_velocity_m_s"] - 5e-4) < 1e-12
    assert bind_conditions({"velocity": 30.003}, reported=fine).mismatches
