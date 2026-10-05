"""Normal probes are admitted only on the version with licensed evidence."""

import pytest

from pyflightstream.cases import CampaignConfigError, PprocSpec, SimCase, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


@pytest.mark.parametrize("recipe", ["unsteady", "unsteady_rotor"])
@pytest.mark.parametrize("version", ["26.120", "26.123", "26.124"])
def test_normal_probes_refuse_an_unmeasured_version(recipe, version):
    """P0370-S5-PROBE-KIND (FR-417): no other version is admitted before measurement."""
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
                        "kind": "normal",
                        "points": 2,
                        "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
                    }
                ]
            }
        ),
    )
    script = Script(version)
    if version == "26.124":
        build_script(case, script)
        assert "UPDATE_PROBE_POINTS" in script.render()
        return
    with pytest.raises(CampaignConfigError, match="normal probes.*26.124"):
        build_script(case, script)
    assert not script.render().strip()
