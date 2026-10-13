"""P0400-CW-STEADY: a steady sweep built as one script is built as its points would be.

0.40.0 items PFS-2104.012 and PFS-2104.041 (the sweep runs build_script's pre-
and post-build steps, the loads frame of every section block included),
PFS-2104.043 (a later point whose free stream turns otherwise is refused) and
PFS-2104.036 with PFS-2104.040 (each point's probes replace the previous
point's).
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases import CampaignConfigError, ReferenceData
from pyflightstream.cases.workflows import build_steady_sweep
from pyflightstream.script import Script
from tests.tier1_offline.test_p0370_s5_probe_kind import _entry, _spec
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case


def _points(case, alphas, **point):
    names = [name.replace("{name}", "P") for name in case.pproc.outputs(False)]
    return [
        case.model_copy(
            update={
                "point": {"alpha": alpha, **point},
                "outputs": [name.replace("P", f"P{index}", 1) for name in names],
            }
        )
        for index, alpha in enumerate(alphas)
    ]


def _built(points) -> Script:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_steady_sweep(points, script)
    return script


def test_p0400_cw_steady_a_sweep_stamps_the_loads_frame_on_every_section_block(tmp_path):
    """P0400-CW-STEADY (PFS-2104.012, PFS-2104.041): the BL product reads it on every block."""
    requirement = "P0400-CW-STEADY"
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path))
    case.pproc.products.boundary_layer_integrals = True
    script = _built(_points(case, (0.0, 5.0)))
    assert script.section_blocks, requirement
    for block in script.section_blocks:
        assert block.get("loads_frame_index") == script.loads_frame, block


def test_p0400_cw_steady_a_sweep_refuses_what_build_script_refuses(tmp_path):
    """P0400-CW-STEADY (PFS-2104.012), the pre-build half: the BL dependency check runs."""
    requirement = "P0400-CW-STEADY"
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path))
    case.pproc.products.boundary_layer_integrals = True
    points = [point.model_copy(update={"outputs": ["P.txt"]}) for point in _points(case, (0, 5))]
    with pytest.raises(CampaignConfigError, match="boundary_layer_integrals requires") as refusal:
        _built(points)
    assert str(refusal.value), requirement


def test_p0400_cw_steady_a_swept_body_rate_is_refused_in_one_script(tmp_path):
    """P0400-CW-STEADY (PFS-2104.043): every point was solved at the first point's rate."""
    requirement = "P0400-CW-STEADY"
    axes = {"roll": "X", "pitch": "Y", "yaw": "Z"}
    reference = ReferenceData(
        area=50.0, length=2.526, moment_point_m=(9.152, 0.0, 0.0), body_axes=axes
    )
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path)).model_copy(
        update={"reference": reference}
    )
    points = _points(case, (0.0, 0.0), pitch_rate=2.0)
    points[1] = points[1].model_copy(update={"point": {"alpha": 0.0, "pitch_rate": 4.0}})
    with pytest.raises(CampaignConfigError, match="free stream differently") as refusal:
        _built(points)
    _built(_points(case, (0.0, 5.0), pitch_rate=2.0))  # one rate: one free stream, builds
    assert str(refusal.value), requirement


def test_p0400_cw_steady_each_points_probes_replace_the_last_points(tmp_path):
    """P0400-CW-STEADY (PFS-2104.036, PFS-2104.040): one creation per point, one ledger."""
    requirement = "P0400-CW-STEADY"
    spec = _spec(_entry(None))
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=spec)
    script = _built(_points(case, (0.0, 2.0, 4.0)))
    lines = script.render().splitlines()
    starts = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
    assert len(starts) == 3, requirement
    bounds = [*starts, len(lines)]
    for here, there in zip(bounds, bounds[1:], strict=False):
        chunk = lines[here:there]
        heads = [line.split()[0] for line in chunk if line[:1].isalpha()]
        assert heads.count("NEW_PROBE_LINE") == 1, heads
        assert heads.count("DELETE_PROBE_POINTS") == 1, heads
        assert heads.index("DELETE_PROBE_POINTS") < heads.index("NEW_PROBE_LINE")
    # One line of three and a 2 by 2 rectangle: seven points, once.
    assert len(script.probe_points) == 7, script.probe_points
