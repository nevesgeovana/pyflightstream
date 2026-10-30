"""Normal probes are measured on 26.124 and 26.125; another build is warned (FR-3404)."""

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import PprocSpec, SimCase, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


@pytest.mark.parametrize("recipe", ["unsteady", "unsteady_rotor"])
@pytest.mark.parametrize("version", ["26.120", "26.123", "26.124", "26.125"])
def test_normal_probes_of_an_unmeasured_version_are_warned_and_emitted(recipe, version):
    """P0370-S5-PROBE-KIND (FR-417), P0520-NOREFUSAL-NORMAL-PROBES (FR-3404).

    A measured build emits the update action the measurement found needed. THE
    EXPECTATION CHANGED WITH THE REQUIREMENT (0.52.0): another build emits the same
    lines and the plan warns, naming that build and the two measured ones, where
    it refused.
    """
    case = SimCase(
        sim_id="1",
        aircraft="test",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=recipe,
        variables={
            "VELOCITY": 30.0,
            "DELTA_TIME": 0.01,
            "TIME_ITERATIONS": 6,
            **(
                {"LAST_ITERS_AVG": 2}
                if recipe == "unsteady"
                else {"LAST_REVS_AVG": 0.25, "RPM": 1200, "ROTOR_AXIS": "X", "BLADES": 1}
            ),
        },
        rotors={
            "ROTOR": {
                "alias": "ROTOR",
                "axis": "X",
                "diameter_m": 3.0,
                "families_blades": ["Blade1"],
                "blade1": {"zero": "Y", "azimuth_deg": 0},
            }
        }
        if recipe == "unsteady_rotor"
        else {},
        point={"alpha": 0.0},
        outputs=["A.txt", "A_probes.txt"],
        pproc=PprocSpec.model_validate(
            {
                "probes": [
                    {
                        "kind": "default",
                        "parameters": ["VX"],
                        "frame": "REFERENCE",
                        "points": 2,
                        "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
                    }
                ]
            }
        ),
    )
    script = Script(version)
    if version in ("26.124", "26.125"):
        build_script(case, script)
        assert "UPDATE_PROBE_POINTS" in script.render()
        return
    with pytest.warns(PyflightstreamWarning, match=f"normal probes.*{version}.*26.124 and 26.125"):
        build_script(case, script)
    assert "UPDATE_PROBE_POINTS" in script.render()
