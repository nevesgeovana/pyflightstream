# Getting started

Half an hour, no FlightStream license needed for most of it. The order
below is deliberate: everything up to "Run it" happens at build time,
where this package does its work, and the solver only appears at the
end.

## Install

```
pip install pyflightstream
```

Optional extras, each gating one subsystem:

| Extra | What it adds |
|---|---|
| `[fsi]` | The aeroelastic coupling loop (PyNiteFEA) |
| `[geom]` | Containment culling for probe lattices (trimesh) |
| `[plot]` | matplotlib, for the plotting examples only |

Reach one without installing it and you get a single typed refusal
carrying the exact install command:

```python
>>> from pyflightstream.exceptions import MissingExtraError
```

## Which FlightStream version do you have?

This is the first question the package asks, and it asks it explicitly
rather than detecting anything. Supported versions are named by a
canonical `26.XXX` identifier, where the last digit is the vendor's
hotfix build.

```python
import pyflightstream

for row in pyflightstream.support_table():
    print(row.summary)
```

Four levels, all derived from the evidence rather than declared:
`registered` means nothing can be built for it yet, `documented` means
the commands come from the manual and no solver has been asked,
`verified` means a probe measured some of them on a real installation,
and `operational` means the minimal end-to-end workflow builds.

The vendor ships every hotfix of a minor release under one name, so
`"26.12"` names two builds and is refused with both named. Pass the
canonical identifier.

## Build a script

Nothing here runs a solver. The point of this package is that the
mistakes surface now:

```python
from pyflightstream.script import Script

script = Script(version="26.120")
script.emit("NEW_SIMULATION")
script.emit("IMPORT", "METER", "STL", "wing.stl", clear=True)
script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
script.emit("AUTO_DETECT_TRAILING_EDGES")
print(script.render())
```

Four kinds of mistake are refused at this point, each with the manual
page that settles it:

* a command that does not exist in this version, with its successor
  when one is recorded;
* an argument of the wrong type, or an enum token outside the
  documented set;
* a command emitted after its phase has passed (geometry, setup, init,
  exec, analysis, export);
* a command a probe measured **broken** on this version, which is the
  one that would otherwise produce a plausible wrong number rather than
  an error.

That last one has a documented way through, because a run sometimes
needs it anyway:

```python
script.allow_broken("AIR_ALTITUDE", reason="reproducing a run from July")
```

The waiver is recorded in the run manifest with the command, the
committed probe report and your reason, so nobody reading the results
later has to wonder.

### The curated helpers

`script.emit` speaks the solver's vocabulary. The helpers speak the
aerodynamicist's, and compose to the same validated lines:

```python
from pyflightstream.script import helpers

helpers.free_stream(script)
helpers.atmosphere(script, density=1.225, pressure=101325.0,
                   temperature=288.15, viscosity=1.789e-5,
                   specific_heat_ratio=1.4)
helpers.initialize_solver(script, symmetry="MIRROR")
helpers.solver_settings(script, aoa=2.0, velocity=30.0,
                        ref_area=11.5, ref_length=1.5)
helpers.start_solver(script)
```

## Declare a campaign

A campaign is data, not code: cases, a sweep, and the recipe that turns
each point into a script.

```python
from pyflightstream.cases import Campaign, SimCase, SweepAxis

case = SimCase(
    sim_id="9001",
    aircraft="TestWing",
    velocity=30.0,
    geometry="wing.fsm",
    sweep=SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
    recipe="mypackage.recipes:steady",
    outputs=["loads_{point}.txt"],
)
campaign = Campaign(name="polar", fs_version="26.120",
                    fs_exe="C:/path/to/FlightStream.exe", sims=[case])
```

`outputs` carries `{point}` for a reason: every point of a case runs in
one folder, so two points rendering the same output name would
overwrite each other's evidence. That is refused before anything runs.

## Pre-flight it

Before spending solver time, build every point and check every path:

<!-- skip: next -->
```python
from pyflightstream.run import plan_campaign
from pyflightstream.workspace import CampaignWorkspace

workspace = CampaignWorkspace.init("runs/polar")
plan = plan_campaign(campaign, workspace)
for point in plan.points:
    print(point.run_id, point.status, point.error or "")
```

This costs no solver time and catches the recipe that does not import,
the geometry file that is not there, the naming template that collides,
and every build-time refusal above.

## Run it

<!-- skip: next -->
```python
from pyflightstream.run import LocalExecutor, run_campaign

records = run_campaign(campaign, LocalExecutor(campaign.fs_exe), workspace)
```

Every point lands in the manifest with exactly one terminal status.
There is no path from "point started" to "loop continued" that writes
nothing, so a silently skipped point is structurally impossible.

## Read the results

<!-- skip: next -->
```python
from pyflightstream.results import sweep_table

table = sweep_table(workspace)
print(table[["run_id", "alpha", "CL", "CDi"]])
```

## Where to go next

* [Replaying a recorded run](tutorial-replay.md): what the manifest
  keeps, and how to reproduce a run from it months later.
* [Command reference](reference/index.md): every command, its
  arguments, and its evidence per version.
* [Compatibility matrix](compatibility.md): what is verified where.
* [Mesh inputs and GUI-only operations](mesh-inputs.md): the supported
  route when a step exists in the interface and has no script command.
