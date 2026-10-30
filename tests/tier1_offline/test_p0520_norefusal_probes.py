"""P0520-NOREFUSAL-NORMAL-PROBES (FR-3404): normal probes of a march on an unmeasured build.

Normal (``kind = "default"``) probes of an unsteady row were measured on the
builds of ``NORMAL_PROBE_BUILDS`` (RPT-153). On another build the plan warns,
naming the build, and emits them after the march as on the measured builds.
The test builds on 26.123, a build the registry lists and no run measured
the probes on.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import PprocSpec
from tests.tier1_offline.test_p0520_norefusal import build, first_words, messages
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

_RECTANGLE = {
    "origin": [0.0, -1.0, -2.0],
    "along_u": [0.0, 1.0, -2.0],
    "along_v": [0.0, -1.0, 2.0],
    "points_u": 2,
    "points_v": 3,
}


@pytest.mark.requirement("FR-3404")
def test_p0520_normal_probes_of_an_unmeasured_build_warn_and_emit(tmp_path):
    # P0520-NOREFUSAL-NORMAL-PROBES
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "probes": [
                {
                    "frame": "REFERENCE",
                    "kind": "default",
                    "field_formats": ["tecplot"],
                    "rectangles": [_RECTANGLE],
                }
            ],
        }
    )
    case = _with_pproc(unsteady_case(), _wb_geometry(tmp_path), pproc=spec)
    script, caught = build(case, "26.123")
    words = first_words(script.render())
    # The probe points are created after the march, as on a measured build.
    assert "PROBE_POINTS_IMPORT" in words
    assert words.index("START_SOLVER") < words.index("PROBE_POINTS_IMPORT")
    named = [m for m in messages(caught) if "normal probes" in m]
    assert named and "26.123" in named[0], messages(caught)
