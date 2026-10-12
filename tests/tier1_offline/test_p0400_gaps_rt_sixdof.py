"""P0400-SIXDOF (FR-461): the SIXDOF row key frees a body to move under its loads.

The free-to-pitch input is resolved and its motion block is held to a golden
(R1, R2), built against the committed database with the 6DOF commands recorded
verified on the build; the evidence gate refuses a build recording one of them
documented (R-GATE); every
refusal of R3 and R4 is asserted by its message; the provenance and the custom
force file are staged with the script (R5).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.sixdof import SixDofSpec
from pyflightstream.cases.workflows import build_script, sixdof_commands
from pyflightstream.cases.workflows._sixdof import SIXDOF_PROVENANCE_FILE
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script
from pyflightstream.workspace.sixdof_setup import SixDofSetupError, resolve_row_sixdof
from tests.tier1_offline._p0400_gaps_rt_support import registry_with
from tests.tier1_offline.test_workflows import _case_for, _wb_geometry, _with_pproc

GOLDENS = Path(__file__).parent / "goldens"
BUILD = "26.124"

FREE_TO_PITCH = """
families = ["W", "B"]
frame = "MRP"

[mass]
mass_kg = 4.2
inertia_kg_m2 = [0.05, 0.31, 0.33, 0.0, 0.0, 0.0]

[gravity]
vector_reference_m_per_s2 = [0.0, 0.0, -9.80665]

[initial]
velocity_body_m_per_s = [0.0, 0.0, 0.0]
angular_velocity_body_deg_per_s = [0.0, 0.0, 0.0]

[free]
q = true

[[forces]]
kind = "external"
point_body_m = [0.25, 0.0, 0.0]
force_body_n = [0.0, 0.0, -40.0]
start_s = 0.0
duration_s = 0.01

[[forces]]
kind = "spring"
point_body_m = [0.0, 0.0, 0.0]
axis_body = [0.0, 0.0, 1.0]
free_length_m = 0.40
solid_length_m = 0.05
initial_length_m = 0.30
rate_n_per_m = 800.0

[[forces]]
kind = "custom"
type = "FORCE_VS_TIME"
file = "pulse_force.txt"
"""

PULSE = "0.000 0.0\n0.010 0.0\n0.015 -20.0\n0.020 0.0\n1.000 0.0\n"


def _inputs(tmp_path: Path, text: str = FREE_TO_PITCH, *, code: str = "d001") -> Path:
    inputs = tmp_path / "inputs"
    folder = inputs / "sixdof"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{code}.toml").write_text(text, encoding="utf-8")
    (folder / "pulse_force.txt").write_text(PULSE, encoding="utf-8")
    return inputs


def _resolved(tmp_path: Path, text: str = FREE_TO_PITCH, **variables: str):
    cell = {"SIXDOF": "d001", **variables}
    return resolve_row_sixdof(_inputs(tmp_path, text), cell, workflow="unsteady", pol="9401")


def _verified(spec: SixDofSpec) -> CommandRegistry:
    """The committed database with every command of ``spec`` recorded verified on BUILD."""
    return registry_with(sixdof_commands(spec), BUILD, Status.VERIFIED)


def _script(tmp_path: Path, resolved, registry: CommandRegistry | None = None) -> Script:
    case = _with_pproc(_case_for("unsteady"), _wb_geometry(tmp_path), pproc=None)
    case = case.model_copy(
        update={"sixdof": resolved.spec, "sixdof_provenance": resolved.provenance()}
    )
    from pyflightstream.cases.workflows._pproc import row_outputs

    names = [name.replace("{name}", "P") for name in row_outputs(case, "unsteady")]
    case = case.model_copy(update={"outputs": names})
    script = Script(BUILD, registry if registry is not None else _verified(resolved.spec))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script


def _block(script: Script) -> str:
    lines = script.render().splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_MOTION 6DOF"))
    last = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_6DOF_TRAJECTORY"))
    return "\n".join(lines[first : last + 2]) + "\n"


def test_p0400_sixdof_free_to_pitch_golden(tmp_path):
    """P0400-SIXDOF (FR-461 R1, R2): the motion block, before the solver is initialised."""
    resolved = _resolved(tmp_path)
    assert resolved is not None
    script = _script(tmp_path, resolved)
    text = script.render()
    assert text.index("CREATE_NEW_MOTION 6DOF") < text.index("INITIALIZE_SOLVER")
    assert _block(script) == (GOLDENS / "p0400_sixdof_free_to_pitch.txt").read_text(
        encoding="utf-8"
    )


def test_p0400_sixdof_stages_its_provenance_and_force_file(tmp_path):
    """P0400-SIXDOF (FR-461 R5): the provenance and the custom force file go with the script."""
    resolved = _resolved(tmp_path)
    assert resolved is not None
    staged = _script(tmp_path, resolved).pending_input_files
    source = tmp_path / "inputs" / "sixdof" / "pulse_force.txt"
    assert staged["pulse_force.txt"] == source.read_bytes()
    record = json.loads(staged[SIXDOF_PROVENANCE_FILE])
    assert record["source_sha256"] == resolved.source_sha256
    assert set(record["files_sha256"]) == {"pulse_force.txt"}


def test_p0400_sixdof_gate_refuses_an_unprobed_build(tmp_path):
    """P0400-SIXDOF (FR-461 R-GATE): an unverified 6DOF command is refused by name."""
    resolved = _resolved(tmp_path)
    assert resolved is not None
    documented = registry_with(
        ["SET_MOTION_MASS_PROPERTIES"], BUILD, Status.DOCUMENTED, base=_verified(resolved.spec)
    )
    with pytest.raises(CampaignConfigError, match="SET_MOTION_MASS_PROPERTIES.*6DOF probes"):
        _script(tmp_path, resolved, documented)


def _replace(old: str, new: str) -> str:
    assert old in FREE_TO_PITCH
    return FREE_TO_PITCH.replace(old, new)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        (_replace("mass_kg = 4.2", "mass_kg = 0.0"), "above zero"),
        (
            _replace("[0.05, 0.31, 0.33, 0.0, 0.0, 0.0]", "[0.05, 0.31, 0.33, 0.2, 0.0, 0.0]"),
            "positive definite",
        ),
        (_replace("q = true", "q = false"), "locks every freedom"),
        (_replace("duration_s = 0.01", "duration_s = 0.0"), "duration"),
        (_replace("solid_length_m = 0.05", "solid_length_m = 0.5"), "exceeds"),
        (_replace('file = "pulse_force.txt"', 'file = "missing.txt"'), "missing.txt"),
        (_replace("[gravity]", "[gravity]\ng = 9.8"), "Extra inputs are not permitted"),
    ],
)
def test_p0400_sixdof_input_refusals(tmp_path, text, words):
    """P0400-SIXDOF (FR-461 R3): each refusal names its key."""
    with pytest.raises(SixDofSetupError, match=words):
        _resolved(tmp_path, text)


def test_p0400_sixdof_mirror_refuses_a_lateral_freedom(tmp_path):
    """P0400-SIXDOF (FR-461 R3): a mirrored half model frees no lateral freedom."""
    text = _replace("q = true", "q = true\nv = true")
    with pytest.raises(SixDofSetupError, match="MIRROR"):
        _resolved(tmp_path, text, SYMMETRY="MIRROR")
    assert _resolved(tmp_path, FREE_TO_PITCH, SYMMETRY="MIRROR") is not None


@pytest.mark.parametrize("workflow", ["steady", "qsteady_rotor", "unsteady_rotor"])
def test_p0400_sixdof_refused_off_the_unsteady_run_type(tmp_path, workflow):
    """P0400-SIXDOF (FR-461 R4): a free body needs the march, and no rotor turning."""
    with pytest.raises(SixDofSetupError, match="time march"):
        resolve_row_sixdof(_inputs(tmp_path), {"SIXDOF": "d001"}, workflow=workflow)


def test_p0400_sixdof_refused_with_fsi_and_a_bad_code(tmp_path):
    """P0400-SIXDOF (FR-461 R3, R4): SIXDOF with FSI, and a code that is not d-prefixed."""
    with pytest.raises(SixDofSetupError, match="FSI"):
        resolve_row_sixdof(
            _inputs(tmp_path), {"SIXDOF": "d001", "FSI": "f001"}, workflow="unsteady"
        )
    with pytest.raises(SixDofSetupError, match="d-prefixed"):
        resolve_row_sixdof(_inputs(tmp_path), {"SIXDOF": "x001"}, workflow="unsteady")
    assert resolve_row_sixdof(_inputs(tmp_path), {}, workflow="unsteady") is None


def test_p0400_sixdof_frame_the_run_does_not_create(tmp_path):
    """P0400-SIXDOF (FR-461 R4): a body frame the run does not create is refused."""
    resolved = _resolved(tmp_path, _replace('frame = "MRP"', 'frame = "PIVOT"'))
    assert resolved is not None
    with pytest.raises(CampaignConfigError, match="PIVOT"):
        _script(tmp_path, resolved)


def test_p0400_sixdof_rotor_run_type_does_not_register_the_key():
    """P0400-SIXDOF (FR-461 R4): the key is the unsteady run type's alone."""
    from pyflightstream.cases.workflows import WORKFLOWS

    assert "SIXDOF" in WORKFLOWS["unsteady"].keys
    for name in ("steady", "unsteady_rotor", "qsteady_rotor"):
        assert "SIXDOF" not in WORKFLOWS[name].keys


def test_p0400_sixdof_active_lines_in_solver_order():
    """P0400-SIXDOF (FR-461 R2): six lines, U V W P Q R, each named once."""
    spec = SixDofSpec.model_validate(
        {
            "families": ["W"],
            "frame": "MRP",
            "mass": {"mass_kg": 1.0, "inertia_kg_m2": [1, 1, 1, 0, 0, 0]},
            "free": {"q": True, "w": True},
        }
    )
    assert spec.active_lines() == [
        "U DISABLE",
        "V DISABLE",
        "W ENABLE",
        "P DISABLE",
        "Q ENABLE",
        "R DISABLE",
    ]
