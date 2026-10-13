"""P0400-RFIXF2-PLANSTATES: the plan states the reuse the script makes (PFS-2081.101).

A rotor's Trefftz C reads a station of the survey lattice. When the ledgers and
the rotor's Trefftz C reuse one declared ``[[probes]]`` lattice, both analyses
must say ``reused``; before the fix ``trefftz:plane`` said the lattice was added.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF2.

from __future__ import annotations

import pytest

from pyflightstream.cases._farfield_spec import FarfieldSpec, LatticeShape
from pyflightstream.cases.farfield_inputs import resolve_farfield
from pyflightstream.cases.workflows._farfield import plan_record
from tests.tier1_offline.test_p0400_farfield_plan import _case, _script


def _probe_states(record: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for item in record["inputs"]:
        if item["input"] == "probe_points":
            out.setdefault(item["analysis"], set()).add(item["state"])
    return out


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_a_rotor_trefftz_c_reads_the_declared_lattice_flag():
    """P0400-RFIXF2-PLANSTATES (FR-455 R4): the resolver uses the lattice flag for a rotor's C."""
    spec = FarfieldSpec.model_validate(
        {"families": "all", "trefftz": {"variant": "plane"}, "ledgers": {"rotor": "R"}}
    )
    resolution = resolve_farfield(
        spec,
        run_type="qsteady_rotor",
        covered_families=(),
        selected_families=["Blade"],
        exports={},
        declares_lattice=True,
        declares_plane=False,
        coupled=False,
        admits_probes=True,
        has_command=lambda command: True,
        rotor=True,
    )
    assert _probe_states(resolution.as_record()) == {
        "trefftz:plane": {"reused"},
        "ledgers": {"reused"},
    }


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf2_the_rotor_plan_matches_the_selected_shapes(tmp_path):
    """P0400-RFIXF2-PLANSTATES (FR-455 R2, R4): a steady rotor row reusing one lattice twice.

    The script lays the declared lattice once and records it as the entry
    reused; the plan says reused for the ledgers and for the rotor's Trefftz C.
    """
    lattice = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
    case = _case(
        tmp_path,
        {
            "families": "all",
            "trefftz": {"variant": "plane"},
            "ledgers": {"rotor": "ROTOR", "m_max": 2},
        },
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [lattice]}],
    )
    case = case.model_copy(update={"point": {**case.point, "RPM": 1000.0}})
    script = _script(case)
    count = LatticeShape.model_validate(lattice).build(1.0).point_count
    assert len(script.probe_points) == count
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert (shape["kind"], shape["source"]) == ("lattice", "declared")
    states = _probe_states(plan_record(case, "26.124", script))
    assert states == {"trefftz:plane": {"reused"}, "ledgers": {"reused"}}
