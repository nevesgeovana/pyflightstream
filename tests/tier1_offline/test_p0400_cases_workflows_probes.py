"""P0400-CW-PROBES: the probe points a script creates, where and how often.

0.40.0 items PFS-2104.033 (normal probes on a row whose per-step window comes
from ``[time_averaging]`` alone were never created during the march),
PFS-2104.009 (a steady cited survey in rotor radii is scaled), PFS-2104.038 (a
steady probe in a named frame is placed with unit axes) and PFS-2105.027 (a
steady probe field records the reference-frame points it declares).
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases import CampaignConfigError, FrameSpec, PprocSpec
from pyflightstream.cases.workflows import build_script, normal_probe_creation
from pyflightstream.script import Script
from tests.tier1_offline.test_p0370_s5_probe_kind import _entry, _heads, _spec
from tests.tier1_offline.test_workflows import _case_for, _wb_geometry, _with_pproc, steady_case


def _averaged(tmp_path):
    spec = _spec(_entry("normal", frame="MRP"), time_averaging={"last_iters": 3})
    case = _with_pproc(_case_for("unsteady"), _wb_geometry(tmp_path), pproc=spec)
    case = case.model_copy(
        update={"outputs": [name.replace("{name}", "P") for name in spec.outputs(True)]}
    )
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return case, script


def test_p0400_cw_probes_a_time_averaging_window_creates_its_normal_probes(tmp_path):
    """P0400-CW-PROBES (PFS-2104.033): the averaging-only window creates what it exports."""
    requirement = "P0400-CW-PROBES"
    case, script = _averaged(tmp_path)
    creation = normal_probe_creation(case, "26.124")
    assert creation.startswith("DELETE_PROBE_POINTS\nNEW_PROBE_LINE"), (requirement, creation)
    heads = _heads(script)
    assert heads[heads.index("START_SOLVER") + 1] == "DELETE_PROBE_POINTS", heads


def _steady_with(tmp_path, *entries, frames=()):
    spec = PprocSpec.model_validate({"groups": {"1": "all"}, "probes": list(entries)})
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=spec)
    return case.model_copy(
        update={
            "outputs": ["point.txt", "point_probes.txt", "point_plots.txt"],
            "frames": list(frames),
        }
    )


def _rendered(case) -> tuple[list[str], Script]:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script.render().splitlines(), script


def test_p0400_cw_probes_a_survey_in_rotor_radii_is_scaled_on_a_steady_row(tmp_path):
    """P0400-CW-PROBES (PFS-2104.009): the import took the file's numbers as metres."""
    requirement = "P0400-CW-PROBES"
    survey = tmp_path / "survey.txt"
    survey.write_text("1\n2,3,4,1\n", encoding="utf-8", newline="\n")
    entry = {
        "frame": "REFERENCE",
        "parameters": ["MACH"],
        "points_file": "survey.txt",
        "scale": "rotor_radius",
    }
    case = _steady_with(tmp_path, entry)
    case.pproc.probes[0] = case.pproc.probes[0].model_copy(
        update={"resolved_points_file": str(survey)}
    )
    lines, _ = _rendered(case)
    assert "PROBE_POINTS_IMPORT" not in lines, requirement
    radius = 3.6576 / 2.0
    expected = " ".join(str(round(value * radius, 5)) for value in (2, 3, 4))
    created = [line for line in lines if line.startswith("NEW_PROBE_POINT")]
    assert created == [f"NEW_PROBE_POINT VOLUME {expected}"], created


TILTED = FrameSpec(name="PROBE_F", origin=(1.0, 0.0, 0.0), x_axis=(2.0, 0.0, 0.0))


def test_p0400_cw_probes_a_cited_survey_in_a_named_frame_is_placed(tmp_path):
    """P0400-CW-PROBES (PFS-2104.009): the import has no named-frame argument."""
    requirement = "P0400-CW-PROBES"
    survey = tmp_path / "survey.txt"
    survey.write_text("1" + chr(10) + "2,3,4,1" + chr(10), encoding="utf-8")
    entry = {"frame": "PROBE_F", "parameters": ["MACH"], "points_file": "survey.txt"}
    case = _steady_with(tmp_path, entry, frames=[TILTED])
    case.pproc.probes[0] = case.pproc.probes[0].model_copy(
        update={"resolved_points_file": str(survey)}
    )
    lines, _ = _rendered(case)
    assert "PROBE_POINTS_IMPORT" not in lines, requirement
    assert "NEW_PROBE_POINT VOLUME 3.0 3.0 4.0" in lines


def test_p0400_cw_probes_a_transformed_surface_survey_is_refused(tmp_path):
    """P0400-CW-PROBES (PFS-2104.009): transforming TYPE 0 cannot invent a volume sample."""
    requirement = "P0400-CW-PROBES"
    survey = tmp_path / "survey.txt"
    survey.write_text("1" + chr(10) + "2,3,4,0" + chr(10), encoding="utf-8")
    entry = {"frame": "PROBE_F", "parameters": ["MACH"], "points_file": "survey.txt"}
    case = _steady_with(tmp_path, entry, frames=[TILTED])
    case.pproc.probes[0] = case.pproc.probes[0].model_copy(
        update={"resolved_points_file": str(survey)}
    )
    with pytest.raises(CampaignConfigError, match="surface TYPE 0.*transforms a survey") as refusal:
        _rendered(case)
    assert "REFERENCE frame" in str(refusal.value), requirement


def test_p0400_cw_probes_a_steady_line_in_a_frame_uses_its_unit_axes(tmp_path):
    """P0400-CW-PROBES (PFS-2104.038): an x_axis of length 2 doubled the line's reach."""
    requirement = "P0400-CW-PROBES"
    entry = {
        "frame": "PROBE_F",
        "parameters": ["MACH"],
        "points": 2,
        "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
    }
    lines, _ = _rendered(_steady_with(tmp_path, entry, frames=[TILTED]))
    created = [line for line in lines if line.startswith("NEW_PROBE_LINE")]
    assert created == ["NEW_PROBE_LINE 2 1.0 0.0 0.0 2.0 0.0 0.0"], (requirement, created)


def test_p0400_cw_probes_a_steady_probe_field_records_the_reference_points(tmp_path):
    """P0400-CW-PROBES (PFS-2105.027): the layout says REFERENCE and carries those points."""
    requirement = "P0400-CW-PROBES"
    square = FrameSpec(name="PROBE_F", origin=(1.0, 0.0, 0.0))
    entry = {
        "frame": "PROBE_F",
        "parameters": ["VX", "VY", "VZ"],
        "points": 2,
        "field_formats": ["vtk"],
        "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
    }
    _, script = _rendered(_steady_with(tmp_path, entry, frames=[square]))
    (layout,) = [item for item in script.probe_field_layout if item["kind"] == "probe-field"]
    assert layout["frame"] == "REFERENCE" and layout["declared_frame"] == "PROBE_F", requirement
    assert layout["points_native"] == [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
    assert [point[4] for point in script.probe_points] == ["REFERENCE", "REFERENCE"]
