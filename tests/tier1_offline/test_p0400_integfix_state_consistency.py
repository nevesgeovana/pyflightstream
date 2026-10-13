"""Tier 1, 0.40.0: a fully pinned gas state at odds with p = rho R T is WARNED, P0400-STATECONS.

A session decision of the 0.40.0 integration lane, under the owner's physics
autonomy: when density, temperature and pressure are ALL pinned for a point
(``RHOkgm3``, ``TK`` and ``PPA``, by the row or by its setup's defaults), the
plan and the post warn when ``|p - rho R T| / p`` exceeds half a percent,
naming the three values, the gas constant the package uses for air and the
relative mismatch. Nothing is refused or withheld: the pins are emitted as
written. A state with any of the three derived satisfies the law by
construction and is never checked. The plan and the post call one function,
:func:`pyflightstream.workspace.flight_condition.pinned_state_mismatch`.

Every fixture is synthetic.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream._atmosphere import ISA
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run import cli
from pyflightstream.workspace.flight_condition import (
    PINNED_STATE_TOLERANCE,
    pinned_state_mismatch,
    resolve_flight_condition,
)
from pyflightstream.workspace.matrix import resolve_matrix
from tests.support_helpers import FIXTURE, make_library
from tests.tier1_offline.test_post_superfile import _workspace

R = ISA.gas_constant_j_per_kg_k
LAW = "p = rho R T"
STATED = "MACH:0.1441, REmi:4.38"


def _mismatch(density: float, temperature: float, pressure: float) -> str:
    """The relative mismatch as the warning prints it."""
    return f"{abs(pressure - density * R * temperature) / pressure:.2%}"


# ------------------------------------------------------------- the one check


def test_p0400_statecons_a_consistent_pinned_triple_is_not_warned():
    """P0400-STATECONS: 1.225 kg/m3, 288.15 K and 101325 Pa agree; nothing is said."""
    state = resolve_flight_condition(
        {"MACH": 0.2, "RHOkgm3": 1.225, "TK": 288.15, "PPA": 101325.0}, pol="P1"
    )
    assert state.pinned == ("RHOkgm3", "TK", "PPA")
    assert pinned_state_mismatch(state, pol="P1") is None


def test_p0400_statecons_an_inconsistent_pinned_triple_names_the_values_r_and_the_mismatch():
    """P0400-STATECONS: the message names the three pins, R and the relative mismatch."""
    state = resolve_flight_condition(
        {"MACH": 0.2, "RHOkgm3": 1.0, "TK": 288.15, "PPA": 101325.0}, pol="P1"
    )
    message = pinned_state_mismatch(state, pol="P1")
    assert message is not None
    for named in ("POL P1", "RHOkgm3:1,", "TK:288.15", "PPA:101325", f"R = {R}", LAW):
        assert named in message, named
    assert _mismatch(1.0, 288.15, 101325.0) in message
    # THE PINS ARE EMITTED AS WRITTEN: the check refuses and corrects nothing.
    assert (state.density_kg_m3, state.temperature_k, state.pressure_pa) == (1.0, 288.15, 101325.0)


def test_p0400_statecons_the_tolerance_is_half_a_percent_either_side():
    """P0400-STATECONS: 0.4 percent off is quiet, 0.6 percent off is warned."""
    exact = 101325.0 / (R * 288.15)
    for factor, warned in ((1.004, False), (0.996, False), (1.006, True), (0.994, True)):
        state = resolve_flight_condition(
            {"MACH": 0.2, "RHOkgm3": exact * factor, "TK": 288.15, "PPA": 101325.0}, pol="P1"
        )
        assert (pinned_state_mismatch(state, pol="P1") is not None) is warned, factor
    assert PINNED_STATE_TOLERANCE == 0.005


@pytest.mark.parametrize(
    "cell",
    [
        {"MACH": 0.2, "RHOkgm3": 1.0, "TK": 288.15},  # pressure derived
        {"MACH": 0.2, "RHOkgm3": 1.0, "PPA": 101325.0},  # temperature from the atmosphere
        {"MACH": 0.2, "TK": 250.0, "PPA": 101325.0},  # density derived
        {"MACH": 0.2, "REmi": 4.38, "TK": 250.0, "PPA": 101325.0},  # density solved
    ],
)
def test_p0400_statecons_a_state_with_one_of_the_three_derived_is_not_checked(cell):
    """P0400-STATECONS: only a state pinning all three is checked."""
    state = resolve_flight_condition(cell, pol="P1", reference_length_m=1.0)
    assert pinned_state_mismatch(state, pol="P1") is None


# ------------------------------------------------------------------ the plan


def _planned(tmp_path: Path, cell: str) -> list[str]:
    """Resolve the fixture matrix with ``cell`` in place of its condition; the warnings."""
    workspace = make_library(tmp_path)
    matrix = tmp_path / "matriz.fs"
    body = FIXTURE.read_text(encoding="utf-8")
    assert STATED in body
    matrix.write_text(body.replace(STATED, cell), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolve_matrix(
            matrix,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes={"003": "steady", "004": "steady"},
            fs_exe="C:/fs/FlightStream.exe",
        )
    return [
        str(w.message)
        for w in caught
        if issubclass(w.category, PyflightstreamWarning) and LAW in str(w.message)
    ]


def test_p0400_statecons_the_plan_warns_an_inconsistent_pinned_row(tmp_path):
    """P0400-STATECONS: the plan warns, naming the row, the three values and the mismatch."""
    said = _planned(tmp_path, "MACH:0.1441, RHOkgm3:1.0, TK:288.15, PPA:101325")
    (message,) = [m for m in said if "POL 9001" in m]
    for named in ("RHOkgm3:1,", "TK:288.15", "PPA:101325", f"R = {R}"):
        assert named in message, named
    assert _mismatch(1.0, 288.15, 101325.0) in message


def test_p0400_statecons_the_plan_is_quiet_for_a_consistent_or_derived_state(tmp_path):
    """P0400-STATECONS: a consistent triple, and a solved density beside TK and PPA, say nothing."""
    assert _planned(tmp_path / "a", "MACH:0.1441, RHOkgm3:1.225, TK:288.15, PPA:101325") == []
    assert _planned(tmp_path / "b", "MACH:0.1441, REmi:4.38, TK:250, PPA:101325") == []


# ------------------------------------------------------------------ the post


def _posted(tmp_path: Path, condition: dict[str, float] | None) -> str:
    """Post the recorded superfile campaign with sim 6001's condition replaced; post.log."""
    workspace = _workspace(tmp_path)
    if condition is not None:
        raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
        for row in raw:
            if str(row["sim_id"]) == "6001":
                row["flight_condition"] = condition
        workspace.manifest_path.write_text(json.dumps(raw, indent=1), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert cli.main(["post", "matriz", "--workspace", str(workspace.root)]) == 0
    return (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")


def test_p0400_statecons_the_post_logs_an_inconsistent_pinned_point(tmp_path):
    """P0400-STATECONS: post.log names it once; TK and PPA come from the setup's defaults."""
    log = _posted(tmp_path, {"MACH": 0.2, "RHOkgm3": 1.0})
    lines = [line for line in log.splitlines() if LAW in line]
    # Two recorded points of one simulation, one state: said ONCE.
    assert len(lines) == 1, lines
    (line,) = lines
    for named in ("POL 6001", "RHOkgm3:1,", "TK:288.15", "PPA:101325", f"R = {R}"):
        assert named in line, named
    assert _mismatch(1.0, 288.15, 101325.0) in line
    # NOTHING IS WITHHELD: the simulation's polar is still written.
    assert list((tmp_path / "camp" / "post" / "matriz").glob("polars/P6001-*_g02.csv"))


def test_p0400_statecons_the_post_is_quiet_for_a_consistent_or_derived_state(tmp_path):
    """P0400-STATECONS: the fixture's solved density, and a consistent triple, log nothing."""
    assert LAW not in _posted(tmp_path / "a", None)
    assert LAW not in _posted(tmp_path / "b", {"MACH": 0.2, "RHOkgm3": 1.225})
