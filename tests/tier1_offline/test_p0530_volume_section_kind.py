"""Tier 1: the volume section's ``kind`` samples an unsteady plane once or at every step (0.53.0).

Pipeline role: quality gate on FR-3420.

``kind = "default"`` samples the plane once, by probe points after the march, as a
``[[probes]]`` entry of that kind does; ``"instantaneous"`` and the unstated value keep
the fluid plots at every step. A steady row samples once whatever the kind.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.pproc import VolumeSectionSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case

TABLE = {
    "shape": "rectangle",
    "frame": "REFERENCE",
    "plane": "XZ",
    "corners_m": [-1, -1, 1, 1],
    "points": [2, 2],
}


def _text(make, **extra):
    pproc = PprocSpec.model_validate({"volume_section": {**TABLE, **extra}})
    case = make().model_copy(update={"pproc": pproc, "pproc_id": "p005"})
    script = Script("26.124")
    build_script(case, script)
    return script, script.render()


@pytest.mark.requirement("FR-3420")
@pytest.mark.parametrize("make", [unsteady_case, rotor_case])
def test_p0530_default_kind_samples_the_plane_once_by_probe_points(make):
    script, text = _text(make, kind="default")
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in text
    assert "PROBE_POINT" in text
    layout = script.probe_field_layout[0]
    assert layout["kind"] == "volume-section"
    assert layout["export_kind"] == "steady-probe"
    assert layout["sampled_at"] == "last-time-step"
    assert len(layout["probe_ids"]) == 4


@pytest.mark.requirement("FR-3420")
@pytest.mark.parametrize("extra", [{}, {"kind": "instantaneous"}])
@pytest.mark.parametrize("make", [unsteady_case, rotor_case])
def test_p0530_instantaneous_and_unstated_keep_the_fluid_plots(make, extra):
    script, text = _text(make, **extra)
    assert text.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT") == 12
    assert script.probe_field_layout[0]["export_kind"] == "unsteady-fluid-plot"


@pytest.mark.requirement("FR-3420")
def test_p0530_the_default_pproc_samples_normal_probes_and_the_unstated_does_not():
    default = PprocSpec.model_validate({"volume_section": {**TABLE, "kind": "default"}})
    assert default.samples_normal_probes()
    assert not PprocSpec.model_validate({"volume_section": TABLE}).samples_normal_probes()


@pytest.mark.requirement("FR-3420")
def test_p0530_an_unknown_kind_is_refused_naming_both():
    with pytest.raises(
        ValidationError, match=r"kind 'weekly' is not one of 'default' or 'instantaneous'"
    ):
        VolumeSectionSpec.model_validate({**TABLE, "kind": "weekly"})


@pytest.mark.requirement("FR-3420")
def test_p0530_the_aliases_map_and_warn():
    with pytest.warns(Warning, match="deprecated"):
        assert VolumeSectionSpec.model_validate({**TABLE, "kind": "normal"}).kind == "default"
    with pytest.warns(Warning, match="deprecated"):
        section = VolumeSectionSpec.model_validate({**TABLE, "kind": "unsteady"})
    assert section.kind == "instantaneous"
