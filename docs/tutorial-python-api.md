# Your first session with the Python API

This tutorial drives pyflightstream from Python alone, with no workspace
tool and no solver. In about fifteen minutes you check a solver build, build
a validated script, watch the builder refuse a wrong argument, declare a
three-point polar as a campaign, pre-flight it, and read a loads export into
numbers. Every block on this page runs as it stands: the documentation tests
execute them, so what you read here is what the package does today.

If you would rather drive a campaign from a run matrix and the `pyfs-matrix`
tool, the [Getting started](getting-started.md) page takes that route. Both
routes build the same scripts and write the same records. The
[Python API reference](api/index.md) lists every public name used below.

## Before you start

Install the package with `python -m pip install pyflightstream`. Nothing on
this page needs FlightStream installed; the solver is the last step of a
real campaign, and this tutorial stops just before it.

The examples write into a fresh temporary folder, so they leave nothing in
your working directory:

```python
import tempfile
from pathlib import Path

work = Path(tempfile.mkdtemp(prefix="pyfs_tutorial_"))
```

## 1. Name the build you will run

FlightStream changes its command set between builds, so every script is
built for one build, named by its canonical identifier. Resolve the one you
have, and ask the package how well it supports it:

```python
import pyflightstream
from pyflightstream.versions import resolve

version = resolve("26.124")
print(version, pyflightstream.support_level(version))
assert str(version) == "26.124"
```

[Which build do I have](builds.md) maps the line your solver prints onto
this identifier.

## 2. Build a script the solver will accept

A `Script` is bound to that build. Each `emit` is checked against the
command database for the build: the command name, the number and type of
its arguments, and the order of the phases. Nothing reaches the file until
it has passed.

```python
from pyflightstream.script import Script

script = Script(version="26.124")
script.emit("NEW_SIMULATION")
script.emit("IMPORT", "METER", "STL", "wing.stl", clear=True)
script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
script.emit("AUTO_DETECT_TRAILING_EDGES")
text = script.render()
print(text)
assert "SET_SIMULATION_LENGTH_UNITS METER" in text
```

## 3. Let the builder refuse a mistake

A wrong value fails here, when you build the script, and not hours later
inside the solver. The message names the values the build accepts and the
manual page the rule comes from:

```python
from pyflightstream.exceptions import CommandArgumentError

try:
    script.emit("SET_SIMULATION_LENGTH_UNITS", "FURLONG")
except CommandArgumentError as error:
    print(error)
    assert "METER" in str(error)
else:  # pragma: no cover - the refusal is the point of this step
    raise AssertionError("the builder accepted a unit the solver does not know")
```

Every refusal the package raises is listed in the
[exceptions catalog](exceptions.md), and all of them derive from
`PyflightstreamError`, so one `except` clause catches any of them.

## 4. Write a recipe for one point

A campaign runs many points, and a recipe is the function that writes the
script of one of them. It receives the case, with the sweep value of the
point already filled in, and an empty script bound to the campaign's build.
The curated helpers in `pyflightstream.script.helpers` emit the common
blocks with their arguments named:

```python
from pyflightstream.script import helpers


def steady_point(case, script):
    """Emit the steady script of one angle of attack."""
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", case.geometry, clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    helpers.free_stream(script)
    helpers.atmosphere(
        script,
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.789e-5,
        specific_heat_ratio=1.4,
    )
    helpers.initialize_solver(script, symmetry="NONE")
    helpers.solver_settings(
        script,
        aoa=case.point["alpha"],
        velocity=case.velocity,
        ref_area=8.0,
        ref_length=1.0,
    )
    helpers.start_solver(script)
```

## 5. Declare the campaign

A `SimCase` is one simulation: its geometry, its flight condition and the
sweep it runs. A `Campaign` groups the cases and names the build and the
solver executable. The geometry here is a placeholder file, because the
pre-flight in the next step checks that the file exists but runs nothing:

```python
from pyflightstream.cases import Campaign, SimCase, SweepAxis

geometry = work / "wing.stl"
geometry.write_text("solid wing\nendsolid wing\n", encoding="utf-8")

case = SimCase(
    sim_id="9001",
    aircraft="TutorialWing",
    velocity=30.0,
    geometry=str(geometry),
    sweep=SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
    recipe="tutorial:steady_point",
    outputs=[],
)
campaign = Campaign(
    name="polar",
    fs_version="26.124",
    fs_exe="FlightStream.exe",
    sims=[case],
)
```

## 6. Pre-flight it

`plan_campaign` builds every point's script in a dry run and validates it,
executing nothing. A broken recipe or a missing geometry shows up here,
before any solver time is spent. The campaign lives in a managed workspace,
which records every run:

```python
from pyflightstream.run import PlanStatus, plan_campaign
from pyflightstream.workspace import CampaignWorkspace

workspace = CampaignWorkspace.init(work / "campaign")
plan = plan_campaign(campaign, workspace, recipes={"tutorial:steady_point": steady_point})
for point in plan.points:
    print(point.run_id, point.status, point.error or "")
assert [point.status for point in plan.points] == [PlanStatus.READY] * 3
```

## 7. Run it, when you have the solver

With a licensed FlightStream, `run_campaign` executes the ready points and
records each one in the workspace. This block needs the solver, so the
documentation tests skip it:

<!-- skip: next -->
```python
from pyflightstream.run import LoadsAssessor, LocalExecutor, run_campaign

records = run_campaign(
    campaign,
    LocalExecutor("C:/path/to/FlightStream.exe"),
    workspace,
    assess=LoadsAssessor(),
    recipes={"tutorial:steady_point": steady_point},
)
```

## 8. Read a loads export

The results layer reads the files the solver writes. Its parsers find their
data by the structure of the file, so an incomplete file raises an error
rather than returning less. Here is a short loads export of the kind a
steady point writes, parsed into a typed report:

```python
from pyflightstream.results import parse_loads

export = """
                              Aerodynamic loads

     Angle of attack (Deg)                       2.000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   30.000
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        1.000
     Solver model:                               Incompressible
     Solver mode:                                Steady
     Reference velocity (m/s)                    30.000
     Reference length (m)                        1.000
     Reference area (m^2)                        8.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             2054000.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            120
     ----------------------------------------------------------------------------------------------------
     Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
     ----------------------------------------------------------------------------------------------------
     Wing,+0.0102000,+0.0000000,+0.1720000,+0.1722000,+0.0021000,+0.0081000,+0.0000000,-0.0110000,+0.0000000
     Total,+0.0102000,+0.0000000,+0.1720000,+0.1722000,+0.0021000,+0.0081000,+0.0000000,-0.0110000,+0.0000000
     ----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #7012026
     Date: 8/3/2026, Time: 2305 hours (local)
"""
report = parse_loads(export)
print(report.angle_of_attack_deg, report.total["CL"], report.total["CDi"])
assert report.total["CL"] == 0.1722
```

A real campaign reads these files for you: after a run, the sweep table of
the workspace holds one row per point with its coefficients.

## Where to go next

- [The Python API reference](api/index.md): every public name, one page per
  subpackage.
- [The command-line tools](cli/index.md): the same work driven from a run
  matrix.
- [The workspace and the workflow](workspace-and-workflows.md): what the
  workspace records, and why.
- [Steady polar](examples/steady_polar.md): this tutorial's polar with a
  generated wing and, when you pass it a solver, a real run.
