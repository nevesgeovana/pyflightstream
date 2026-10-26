import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.script import Script
from pyflightstream.workspace import InputArtifactError


def _case(tmp_path, settings, variables=None):
    sidecar = tmp_path / "duct.boundaries.toml"
    sidecar.write_text('[ports]\nfeed="Inlet"\nexit="Outlet"\n[trailing_edges]\nnone=true\n')
    return SimCase(
        sim_id="9011",
        aircraft="Duct",
        recipe="steady",
        geometry=str(tmp_path / "duct.obj"),
        inventory=["Inlet", "Outlet"],
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"VELOCITY": "30", **(variables or {})},
        outputs=["point.txt"],
        solver=SolverSettings.model_validate(settings),
    )


def _script():
    script = Script("26.124")
    script.declare_existing(boundaries={"Inlet": 1, "Outlet": 2})
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    return script


def test_outlet_profile_is_refused_by_the_setup_model():
    with pytest.raises(ValueError, match="outlet profile"):
        SolverSettings(
            ports=[
                {
                    "port": "exit",
                    "kind": "outlet",
                    "velocity_variable": "SPEED",
                    "profile_variable": "PROFILE",
                }
            ]
        )


def test_setup_rejects_inline_condition_or_surface_values():
    from pyflightstream.workspace.inputs import SetupArtifact
    from pyflightstream.workspace.matrix import _solver_from_setup

    for field, value in (("velocity", 10), ("boundary", "Inlet"), ("profile", "p.txt")):
        with pytest.raises(InputArtifactError, match="MATRIX"):
            _solver_from_setup(
                SetupArtifact(
                    settings={"ports": [{"port": "feed", "kind": "inlet", field: value}]}
                ),
                "s001",
            )


def test_p0460_saved_geometry_refuses_fresh_port_creation(tmp_path):
    from pyflightstream.workspace.matrix import _bind_setup_ports
    from tests.tier1_offline.test_workflows import steady_case

    case = steady_case().model_copy(
        update={
            "geometry": str(tmp_path / "duct.fsm"),
            "solver": SolverSettings(
                ports=[{"port": "feed", "kind": "inlet", "velocity_variable": "SPEED"}]
            ),
        }
    )
    with pytest.raises(InputArtifactError, match="saved simulation"):
        _bind_setup_ports(case, tmp_path)
