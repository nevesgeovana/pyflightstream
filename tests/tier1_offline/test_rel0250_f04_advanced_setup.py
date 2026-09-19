"""F04: setup keys reach the existing advanced-setting emitters and flag IDs."""

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import _settings, build_script
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.post.settings_table import FLAG_IDS, settings_table
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import InputArtifactError, resolve_setup
from pyflightstream.workspace.matrix import _solver_from_setup

# Arguments and availability transcribed from commands/advanced_settings.yaml;
# IDs are the existing, frozen product contract.
SETTINGS = [
    ("laminar_separation", "LAMINAR_SEPARATION", True, "ENABLE", "26.123", 54),
    ("kutta_joukowski_lift", "KUTTA_JOUKOWSKI_LIFT_FORCES", False, "DISABLE", "26.123", 23),
    ("aeroelastic_rbf_type", "AEROELASTIC_RBF_TYPE", "GAUSSIAN", "GAUSSIAN", "26.123", 64),
    (
        "print_rotor_induced_velocities",
        "PRINT_ROTOR_INDUCED_VELOCITIES",
        True,
        "ENABLE",
        "26.123",
        24,
    ),
    (
        "adaptive_field_grid_refinement",
        "SET_ADAPTIVE_FIELD_GRID_REFINEMENT",
        False,
        "DISABLE",
        "26.123",
        25,
    ),
    (
        "rotor_induced_velocity_blending",
        "ROTOR_INDUCED_VELOCITY_BLENDING",
        0.4,
        "0.4",
        "26.123",
        27,
    ),
    ("wake_numerical_relaxation", "SET_WAKE_NUMERICAL_RELAXATION", 0.2, "0.2", "26.123", 28),
    ("wake_relaxation", "SET_WAKE_RELAXATION", True, "ENABLE", "26.000", 36),
    ("wake_decay_constant", "SET_WAKE_DECAY_CONSTANT", 0.3, "0.3", "26.123", 30),
    (
        "wake_streamwise_agglomeration",
        "SET_WAKE_STREAMWISE_AGGLOMERATION",
        False,
        "DISABLE",
        "26.000",
        37,
    ),
    (
        "jet_wake_decay_normalized_length",
        "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH",
        2.5,
        "2.5",
        "26.123",
        29,
    ),
    (
        "jet_wake_filaments_grid_induction",
        "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
        True,
        "ENABLE",
        "26.120",
        26,
    ),
    (
        "adverse_gradient_boundary_layer",
        "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
        True,
        "ENABLE",
        "26.000",
        38,
    ),
    (
        "vortex_ring_normalization",
        "SOLVER_VORTEX_RING_NORMALIZATION",
        False,
        "DISABLE",
        "26.000",
        39,
    ),
]


def setup_case(tmp_path, body):
    directory = tmp_path / "setups"
    directory.mkdir(exist_ok=True)
    (directory / "s900.toml").write_text(body, encoding="utf-8", newline="\n")
    artifact = resolve_setup(tmp_path, "s900")
    return SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["loads.txt"],
        solver=_solver_from_setup(artifact, "s900"),
        raw_commands=artifact.raw_commands,
    )


@pytest.mark.parametrize("key,command,value,token,build,flag_id", SETTINGS)
def test_setup_emits_advanced_setting_and_preserves_post_flag(
    tmp_path, key, command, value, token, build, flag_id
):
    literal = str(value).lower() if isinstance(value, bool) else repr(value)
    case = setup_case(tmp_path, f"{key} = {literal}\n")
    script = Script(build)
    build_script(case, script)
    assert script.render().splitlines().count(f"{command} {token}") == 1
    # All fourteen are init-phase commands in the database.
    assert script.render().index(f"{command} {token}\n") < script.render().index(
        "INITIALIZE_SOLVER"
    )
    assert script.solver_setup is not None
    record = script.solver_setup.flags[command]
    assert record.provenance == "explicit"
    assert record.emitted
    assert record.value == value
    assert FLAG_IDS[command] == flag_id
    row = next(row for row in settings_table([script.solver_setup]) if row["flag_id"] == flag_id)
    assert row["emitted"] == 1
    assert row["provenance_code"] == 1


@pytest.mark.parametrize(
    "key,build,command",
    [
        ("wake_decay_constant", "26.120", "SET_WAKE_DECAY_CONSTANT"),
        ("wake_relaxation", "26.121", "SET_WAKE_RELAXATION"),
        ("jet_wake_filaments_grid_induction", "26.121", "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION"),
    ],
)
def test_setup_refuses_unavailable_command_with_build(tmp_path, key, build, command):
    value = "0.3" if key == "wake_decay_constant" else "true"
    case = setup_case(tmp_path, f"{key} = {value}\n")
    with pytest.raises(CommandNotInVersionError) as raised:
        _settings(case, Script(build))
    assert command in str(raised.value)
    assert build in str(raised.value)


def test_unknown_setup_key_stays_refused(tmp_path):
    with pytest.raises(InputArtifactError, match="laminar_seperation"):
        setup_case(tmp_path, "laminar_seperation = true\n")


def test_unset_advanced_keys_preserve_existing_script(tmp_path):
    case = setup_case(tmp_path, "iterations = 250\nviscous_coupling = false\n")
    script = Script("26.123")
    build_script(case, script)
    # Captured from this setup before F04; a compatibility fixture, not a
    # numerical oracle. No newly reachable setting is stated by this preset.
    assert script.render() == (
        "SET_FREESTREAM CONSTANT\n"
        "SOLVER_SET_AOA 0.0\n"
        "SOLVER_SET_SIDESLIP 0.0\n"
        "SOLVER_SET_VELOCITY 30.0\n"
        "SOLVER_SET_REF_VELOCITY 30.0\n"
        "SOLVER_SET_ITERATIONS 250\n"
        "SOLVER_SET_CONVERGENCE 1e-05\n"
        "SET_SOLVER_VISCOUS_COUPLING DISABLE\n"
        "SOLVER_MINIMUM_CP -100\n"
        "INITIALIZE_SOLVER\n"
        "SOLVER_MODEL INCOMPRESSIBLE\n"
        "SURFACES -1\n"
        "WAKE_TERMINATION_X DEFAULT\n"
        "SYMMETRY NONE\n\n"
        "START_SOLVER\n"
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nloads.txt\n\n"
        "CLOSE_FLIGHTSTREAM\n"
    )


def test_raw_advanced_setting_still_works(tmp_path):
    case = setup_case(
        tmp_path,
        '[[raw]]\ncommand = "LAMINAR_SEPARATION ENABLE"\nbefore = "init"\n',
    )
    script = Script("26.123")
    build_script(case, script)
    assert "LAMINAR_SEPARATION ENABLE\n" in script.render()
