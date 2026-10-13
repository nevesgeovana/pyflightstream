"""P0400-FFPROOF: what the plan says about the far field it lays (FR-451 R10, FR-455 R9, FR-459 R5).

Each case is a row built by the public script builder the plan calls, on the
synthetic box mesh of ``test_p0400_farfield_plan`` (one family ``W``): the
WARNINGs are the ones the plan prints, read as they are emitted, and the
counts they state are checked against the commands of the emitted script.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.cases.workflows import build_script, row_outputs
from pyflightstream.script import Script
from tests.tier1_offline.test_p0400_farfield_plan import _case
from tests.tier1_offline.test_workflows import _case_for

#: A survey lattice of the MRP frame, clear of the box (its station lies aft of it).
_LATTICE = {"frame": "MRP", "tip_radius_m": 0.5, "stations": [2.0], "n_r": 2, "n_psi": 8}
_POINTS = LatticeShape.model_validate(_LATTICE).build(0.5).point_count
_PLOT = "UNSTEADY_SOLVER_NEW_FLUID_PLOT"


def _built(case) -> tuple[str, list[str]]:
    """Build the row's script as the plan does; return it and the WARNINGs it gave."""
    script = Script("26.124")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build_script(case, script)
    messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    return script.render(), messages


def _unsteady(root: Path, farfield: dict | None, **pproc: object):
    """The box row as a fixed-wing ``unsteady`` row, its outputs as the plan declares them.

    ``farfield`` None is an artifact without ``[farfield]``.
    """
    case = _case(root, cast("dict", farfield), **pproc)
    case = case.model_copy(
        update={
            "recipe": "unsteady",
            "rotors": {},
            "variables": dict(_case_for("unsteady").variables),
        }
    )
    return case.model_copy(update={"outputs": row_outputs(case, "unsteady")})


def _declared(count: int) -> dict[str, object]:
    return {
        "distributions": [{"families": ["W"], "frame": "MRP", "planes": ["XZ"], "count": count}]
    }


@pytest.mark.requirement("FR-451")
def test_p0400_ffproof_the_plan_warns_a_reused_distribution_with_few_stations(tmp_path):
    """P0400-FFPROOF (FR-451 R10): one plan WARNING naming the family, its count and the bias.

    A full model's declared distribution of 80 sections is 40 stations per
    side, under the 80 of ``[farfield.trefftz]``: the plan reuses it and says
    so once, with the bias the definitions page measured at 40 (1.05 percent).
    A distribution of 160 sections (80 per side) is reused in silence.
    """
    farfield = {"families": "all", "trefftz": {"variant": "sections"}}
    text, messages = _built(_case(tmp_path, farfield, sections=_declared(80)))
    assert text.splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION") == 1, "reused, not added"
    few = [m for m in messages if "stations per side" in m]
    assert len(few) == 1, messages
    assert "family W has 40 stations per side" in few[0]
    assert "fewer than the 80 of [farfield.trefftz]" in few[0]
    assert "1.05 percent at 40 stations per side" in few[0]
    (tmp_path / "dense").mkdir()
    _text, quiet = _built(_case(tmp_path / "dense", farfield, sections=_declared(160)))
    assert not [m for m in quiet if "stations per side" in m], quiet


@pytest.mark.requirement("FR-455")
def test_p0400_ffproof_the_plan_states_the_fluid_plots_an_added_lattice_costs(tmp_path):
    """P0400-FFPROOF (FR-455 R9): an unsteady row's added lattice, sampled at every step.

    The WARNING states the point count and the fluid-plot count, and the
    script carries exactly that many fluid plots, four parameters per point.
    """
    case = _unsteady(tmp_path, {"families": "all", "ledgers": dict(_LATTICE, m_max=2)})
    text, messages = _built(case)
    assert text.count(_PLOT) == 4 * _POINTS
    stated = [m for m in messages if "FR-455 R9" in m]
    assert stated == [
        f"case '7002': the far-field lattice samples {_POINTS} points at every time step, "
        f"{4 * _POINTS} fluid plots (FR-455 R9)."
    ]
    assert any(name.endswith("_plots.txt") for name in case.outputs)


@pytest.mark.requirement("FR-455")
def test_p0400_ffproof_a_reused_normal_lattice_is_laid_once_as_probe_points(tmp_path):
    """P0400-FFPROOF (FR-455 R2, R9): a lattice declared in a ``kind = "normal"`` entry.

    The far field reuses it by identity: the lattice is laid once, as probe
    points after the march (no fluid plot, no cost WARNING), and the row
    exports the probe points the instant is read from.
    """
    entry = {"frame": "MRP", "kind": "normal", "parameters": ["VX"], "lattices": [_LATTICE]}
    farfield = {"families": "all", "ledgers": dict(_LATTICE, m_max=2)}
    case = _unsteady(tmp_path, farfield, probes=[entry])
    text, messages = _built(case)
    assert text.count("NEW_PROBE_POINT") == _POINTS, "the declared lattice, laid once"
    assert _PLOT not in text
    assert not [m for m in messages if "FR-455 R9" in m]
    assert any(name.endswith("_probes.txt") for name in case.outputs)


@pytest.mark.requirement("FR-459")
def test_p0400_ffproof_a_declared_unsteady_lattice_states_its_fluid_plots(tmp_path):
    """P0400-FFPROOF (FR-459 R5): a ``[[probes]]`` lattice on an unsteady entry is accepted.

    One plan WARNING states its fluid-plot count, the points times the
    entry's parameters, which is the count of fluid plots the script carries.
    """
    entry = {"frame": "MRP", "parameters": ["VX", "VY"], "lattices": [_LATTICE]}
    case = _unsteady(tmp_path, None, probes=[entry])
    text, messages = _built(case)
    stated = [m for m in messages if "FR-459 R5" in m]
    assert stated == [
        f"case '7002': a [[probes]] lattice samples {_POINTS} points at every time step, "
        f"{2 * _POINTS} fluid plots (FR-459 R5)."
    ]
    assert text.count(_PLOT) == 2 * _POINTS
