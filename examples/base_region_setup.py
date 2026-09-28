# %% [markdown]
# # Ordered base-region setup
# This repository example generates commands from the public body fixture.
# Creation names the mesh boundary; later actions name the current base-region
# index. Inspect existing regions before adapting these actions to another FSM.
# No native state or flow-accuracy claim follows from script generation.
# %%
"""Generate an ordered base-region setup script without launching FlightStream."""

from pathlib import Path

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


def build_example(geometry: Path | None = None) -> str:
    """Render the public body example against the documented 26.124 command set."""
    if geometry is None:
        geometry = (
            Path(__file__).resolve().parents[1]
            / "tests/tier3_licensed/inputs/geometries/20_BODY.fsm"
        )
    case = SimCase(
        sim_id="9012",
        aircraft="Body",
        recipe="steady",
        geometry=str(geometry),
        inventory=["Body", "Base"],
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["body-loads.txt"],
        solver=SolverSettings(
            base_region_operations=[
                {"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.2},
                {"operation": "set_pressure", "index": 1, "model": "CUSTOM", "cp": -0.3},
                {"operation": "mark_trailing_edges", "index": 1},
            ]
        ),
    )
    script = Script("26.124")
    build_script(case, script)
    return script.render()


if __name__ == "__main__":
    print(build_example())
