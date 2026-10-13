"""P0400-RFIXF2-PLOTS: a reused declared lattice on an unsteady row gets the histories it lacks.

PFS-2081.99 (REL2-003): the far field reads ``VX``, ``VY``, ``VZ`` and
``CP_REF`` at every step. A declared ``[[probes]]`` lattice reused by identity
keeps its points and its own histories, and the plan adds the missing ones at
the same vertices, in the entry's frame, and states their count; before the fix
a ``VX``-only declaration left the other three absent and post read NaN.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF2.

from __future__ import annotations

import re
import warnings

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import build_script
from pyflightstream.post.farfield_fields import far_samples, recorded_layout, unsteady_samples
from pyflightstream.script import Script
from tests.tier1_offline.test_p0400_ffproof_plan import _LATTICE, _POINTS, _unsteady

pytestmark = pytest.mark.requirement("FR-455")

_PLOT = "UNSTEADY_SOLVER_NEW_FLUID_PLOT"


def _plot_names(text: str) -> list[str]:
    """The names of the fluid plots a rendered script creates, in order."""
    lines = text.splitlines()
    named = re.compile(r"^\s*NAME\s+(\w+)\s*$")
    names = []
    for at, line in enumerate(lines):
        if line.strip() == _PLOT:
            names += [m.group(1) for m in map(named.match, lines[at + 1 : at + 6]) if m]
    return names


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_vx_only_lattice_gets_the_other_histories(tmp_path):
    """P0400-RFIXF2-PLOTS (FR-455 R2, R9): VX declared; VY, VZ and CP_REF added at its vertices.

    No probe point is laid twice; every vertex of the lattice carries the four
    histories post reads, so one step of synthetic plots under those names
    leaves no NaN in the matched lattice.
    """
    entry = {"frame": "MRP", "parameters": ["VX"], "lattices": [_LATTICE]}
    case = _unsteady(
        tmp_path, {"families": "all", "ledgers": dict(_LATTICE, m_max=2)}, probes=[entry]
    )
    script = Script("26.124")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build_script(case, script)
    messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    text = script.render()
    assert len(script.probe_points) == _POINTS, "the declared lattice, laid once"
    assert text.count(_PLOT) == 4 * _POINTS
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert (shape["source"], shape["plots_added"]) == ("declared", ["VY", "VZ", "CP_REF"])
    assert any(f"{3 * _POINTS} fluid plots at every time step (FR-455 R9)" in m for m in messages)
    names = _plot_names(text)
    vertices = [point[0] for point in script.probe_points]
    for parameter in ("VX", "VY", "VZ", "CP_REF"):
        assert sorted(n for n in names if re.fullmatch(f"{parameter}\\d+", n)) == sorted(
            f"{parameter}{v}" for v in vertices
        )
    series = {name: np.array([1.0]) for name in names}
    positions = {p[0]: (p[1], p[2], p[3], p[4]) for p in script.probe_points}
    samples = unsteady_samples(series, positions, 0)
    lattice, _, why = far_samples(samples, recorded_layout([shape]), per_m=1.0)
    assert why == ""
    assert np.isfinite(samples.velocity[lattice]).all() and np.isfinite(samples.cp[lattice]).all()


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_lattice_stating_every_history_adds_none(tmp_path):
    """P0400-RFIXF2-PLOTS (FR-455 R2): nothing is added to an entry that states all four."""
    entry = {
        "frame": "MRP",
        "parameters": ["VX", "VY", "VZ", "CP_REF"],
        "lattices": [_LATTICE],
    }
    case = _unsteady(
        tmp_path, {"families": "all", "ledgers": dict(_LATTICE, m_max=2)}, probes=[entry]
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    assert script.render().count(_PLOT) == 4 * _POINTS
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert "plots_added" not in shape
