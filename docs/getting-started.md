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
| `[manual]` | Reading a vendor manual pdf for `pyfs-manual` (pypdf); maintainer tooling, no run path imports it |
| `[geom]` | The spatial index behind containment culling for probe lattices (rtree, scipy). The mesh reader, trimesh, is NOT here: it became a runtime dependency in v0.8.0, because the trailing-edge extraction that reads a blade surface through it is on the default path of a rotor campaign |
| `[plot]` | matplotlib, for the plotting examples only |

Reach one without installing it and you get a single typed refusal
carrying the exact install command:

```python
>>> from pyflightstream.exceptions import MissingExtraError
```

## Which FlightStream version do you have?

This is the first question the package asks, and it asks it explicitly
rather than detecting anything. Supported versions are named by a
canonical `YY.XXX` identifier, where the last digit is the vendor's
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

### Why a brand-new build refuses commands its predecessor runs

A build can be registered before anything is known about it, and the
package would rather refuse than guess. Where a hotfix is recorded as
carrying its base release's evidence, a command the base records answers
for the hotfix too, which is right for a hotfix that did not touch it.
Where it is recorded as carrying NOTHING, every command answers absent
until somebody reads a page of that build's own manual or runs a probe
against it, and the emitter refuses each one as it is reached:

```python
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import Script

try:
    Script(version="26.123").emit("TRAILING_EDGES_IMPORT")
except CommandNotInVersionError as error:
    assert "no recorded evidence" in str(error)
else:  # pragma: no cover - the refusal is the point of the example
    raise AssertionError("the command was emitted, so this page is out of date")
```

It ASSERTS rather than prints, and that is not a style preference. The
fenced blocks on these pages are executed and their expected-output
blocks are not compared, so a `print` inside a `try` shows only that the
code ran. The day this command gains a row for this build, the `try`
would succeed, nothing would be printed, and the example would stay green
while teaching a refusal that no longer happens.

That is a statement about EVIDENCE and not about the solver. The build
may well run the command perfectly; nobody here has established that it
does. The command above is one the new edition stops documenting, which is why
it is still refused after that build's documented rows were written. The
list of what is currently in that state is committed, so you can see the
size of the gap without running anything:
`tests/tier1_offline/goldens/absent_on_26123.txt` carries every affected command and
its own count in the header.

If you meet this refusal and need the command today, use a build the
package has evidence for. The support table above tells you which.

The vendor reuses a release name across builds, so both `"26.12"` and
`"26.1"` name more than one; each is refused with every candidate and
its vendor build number named. Pass the canonical identifier, and note
what the growing count means for one you wrote down earlier: a vendor
name is unambiguous only until the vendor ships the next build under
it. A campaign never keeps the name: a `Campaign` resolves the version it
is given and stores the canonical identifier, so a matrix converted with
`26.0` writes `fs_version = "26.000"` into `campaign.toml` and the file
still loads on the day a second build claims `26.0` (PFS-2009.04). This
page does not say how many are in either family, for exactly
that reason; run the refusal and read its candidates, which this page
does rather than only recommending:

```python
from pyflightstream.versions import AmbiguousVersionAliasError, resolve

try:
    resolve("26.12")
except AmbiguousVersionAliasError as error:
    assert "26.120" in str(error) and "vendor build" in str(error)
else:  # pragma: no cover - the refusal is the point of the example
    raise AssertionError("26.12 resolved to a single build, so this page is out of date")
```

The refusal names every candidate with the vendor build number its own
solver prints, which is the one string a reader holding two installs can
match. The two families
are not the same relationship either: `26.12` is a release with its
hotfixes, while 26.100 and 26.101 are the February and May 2026
releases that happened to share a name, which is why the registry
states descent per build instead of reading it off the last digit.

If you are not sure which one you have, the
[Which build do I have](builds.md) page maps the release name and build
number your solver prints onto the identifier to pass. Read it before
assuming: some registered builds print a release name that is not even
the one the vendor sells them under.

## Your first workspace, step by step

This section assumes nothing. If you have never used this package, start
here and copy the files it names; they are real files in this repository,
not sketches, and every one of them is rendered by a test on every commit.

### The four kinds of file, and why there are four

A study is a lot of runs that share almost everything. Rather than repeat
what they share on every row, a workspace splits it into four files by
**how often it changes**:

| File | Lives in | Answers | Changes |
|---|---|---|---|
| **geometry** | `inputs/geometries/` | what shape is in the wind | per configuration |
| **reference `r###`** | `inputs/references/` | what the numbers are measured AGAINST, and what the parts are CALLED | per configuration |
| **setup `s###`** | `inputs/setups/` | how the solver is to be run | per study |
| **pproc `p###`** | `inputs/pproc/` | what to write down afterwards | per study |
| **the matrix** | anywhere | which combinations to run | it IS the study |

A matrix row names one of each by its code, plus its own flight condition.
That is the whole model: **the row says what is different, the four files
say what is shared.**

Read them in this order the first time.

### 1. The geometry: what is in the wind

A `.fsm` file the solver saved, with a boundary for each part. This
repository ships ten of them under
`tests/tier3_licensed/inputs/geometries/`, all SYNTHETIC: generated from
public shape laws by a committed generator, with a `.provenance.toml`
beside each recording the generator and the specification it was built
from. `41_TWIN.fsm` is a body with two rotors and carries four boundaries:
`Body`, `Base`, `Blade1`, `Blade2`. Its inventory is written out beside it
in `41_TWIN.boundaries.toml`, which is what `pyfs-matrix inventory` prints
for a geometry of your own.

You will refer to those boundary names in the next file, so open the
inventory first and keep it in front of you.

### 2. The reference `r###`: the lengths, and the vocabulary

Read `tests/tier3_licensed/inputs/references/r006.toml`. It does two jobs.

**It says what the coefficients are divided by.** `area_m2`, `chord_m` and
`span_m` are SREF, CREF and BREF, and `[moment_point]` is where moments are
taken about. Change one of these and every coefficient in your results
changes, which is why they live in a file a row cites rather than in the
row.

**It says what the parts are CALLED**, and this is the half that saves you
the most work:

```toml
[aliases]
airframe = ["Body", "Base"]
rotors = ["PORT", "STARBOARD"]
```

An alias is a name YOUR study gives to a set of boundaries, and it is read
everywhere a boundary is cited. Write `airframe` once here and every row,
every group and every plot can say `airframe` instead of listing the parts
again. A member may be another alias, followed to the end, and a member the
opened mesh does not carry is left out, which is what lets one reference
serve a wing-body and an isolated rotor.

A rotor is a block whose NAME is an alias over everything that rotor owns:

```toml
[PORT]
kind = "rotor"
x_m = 4.5           # the hub
y_m = 0.9144
z_m = 0.0
axis = "X"          # what it turns about
rpm_sign = 1        # which way
diameter_m = 3.6576 # what an advance ratio resolves against
families_general = []             # the hub, spinner, anything not a blade
families_blades = ["Blade1"]      # the blades; the COUNT is this list's length
blade1 = { azimuth_deg = 0.0, zero = "Y" }   # where blade 1 sits
```

After this a row says `PORT` and states nothing else about that rotor.

### 3. The setup `s###`: how the solver runs

Read `tests/tier3_licensed/inputs/setups/s002.toml`. Iteration counts,
convergence, the wake, the boundary-layer type: the knobs you would set
once for a study and leave alone. What is NOT here is the clock, because
a time step is what a point IS rather than how the solver is configured.

### 4. The pproc `p###`: what gets written down

Read `tests/tier3_licensed/inputs/pproc/p005.toml`. Boundary groups, the
exports, the sectional distributions, the force plots, the probe lines, and
the product tables the campaign writes.

The one idea to take from it: **the frame decides how an entry expands.**
You do not say how many plots you want; you say which frame each quantity
is measured in, and the count follows:

| `frame =` | you get |
|---|---|
| `MRP`, or a frame the reference declares | ONE, over the whole cited set |
| `SMRP` or `RMRP` | one per ROTOR, in that rotor's own frame |
| `LOCAL_AXIS` | one per BLADE, in that blade's frame |

So the four `[[plots.groups]]` entries in `p005.toml` become nine emissions
on this two-rotor aircraft, and would become twenty-seven on a nine-rotor
one without a line changing.

### 5. The matrix: which combinations to run

Read `tests/tier3_licensed/matriz_vocab.fs`. Every row names a geometry,
an `r`, an `s` and a `p`, its own flight condition, and the values it
sweeps. Row 8002 is the one to look at first:

```
8002 | Twin | ... | MACH:0.1, REmi:2.3, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep | 0.6,0.8 | r006 | s002 | p005 | ...
     | GEOMETRY: 41_TWIN.fsm / DELTA_THETA: 30 / REVOLUTIONS: 0.5 /
       CLOCK_MOTION: PORT / MOTIONS: {MOVING_BC_ALIAS: PORT}, {MOVING_BC_ALIAS: STARBOARD}
```

Read it left to right: at Mach 0.1, at zero incidence and sideslip,
sweeping the advance ratio over 0.6 and 0.8, against reference `r006`,
setup `s002` and post-processing `p005`. Two rotors turn; neither states a
speed, so both take the swept ratio; `CLOCK_MOTION` says the time step
follows `PORT`.

**One number gives two speeds.** The rendered script for the first point is
`tests/tier3_licensed/goldens/matriz_vocab/POLAR-8002_M10AL+000BE+000J+060.txt`,
and it emits:

```
SET_MOTION_ROTOR_RPM 1 930.3642
SET_MOTION_ROTOR_RPM 2 -1860.7283
```

Exactly twice the speed on the rotor of half the diameter, and negative
because `STARBOARD` declares `rpm_sign = -1`. You wrote one ratio; the
reference did the rest.

### 6. Run it

```
pyfs-matrix plan  matriz_vocab.fs --workspace . --fs-version 26.123
pyfs-matrix run   matriz_vocab.fs --workspace . --fs-version 26.123
```

`plan` spends no solver time: it binds every code, builds every script in
dry run and tells you READY or BLOCKED with the reason. **Always plan
before you run.** A blocked point costs you a message; a bad run costs you
the licence.

### What to copy

The fastest start is to copy `tests/tier3_licensed/inputs/` whole, delete
the artifacts you do not need, and edit `r006.toml` to your own lengths and
your own boundary names. Then write one matrix row and plan it.

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
  documented set (the set is everything the manual page accepts: where
  a page takes an axis as a letter or as its index, the integer `2`
  and the string `"2"` both print as `2`, and a refusal lists every
  spelling);
* a command emitted after its phase has passed (geometry, setup, init,
  exec, analysis, export);
* a command a probe measured **broken** on this version, which is the
  one that would otherwise produce a plausible wrong number rather than
  an error.

A line transcribed straight off a manual page is typed as the page
prints it, integers included:

```python
from pyflightstream.script import CommandArgumentError, Script

script = Script(version="26.120")
script.emit("CAD_BODY_ROTATE", 1, 2, 15.0)
assert "CAD_BODY_ROTATE 1 2 15.0" in script.render()
try:
    script.emit("CAD_BODY_ROTATE", 1, 4, 15.0)
except CommandArgumentError as error:
    assert "one of X, Y, Z, 1, 2, 3" in str(error)
```

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
from pyflightstream.run import LoadsAssessor, LocalExecutor, run_campaign

records = run_campaign(
    campaign,
    LocalExecutor(campaign.fs_exe),
    workspace,
    assess=LoadsAssessor(),
)
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

### Time-resolved history

The loads spreadsheet and the probe export each describe one instant.
The unsteady plot export is the only file the solver writes that carries
a HISTORY: one column per plot, one row per time step. Read it by label
and never by column position, because the column set is whatever plots
the run defined.

```python
from pyflightstream.results import parse_unsteady_plots

export = (
    "Time (sec), CL, CDi\n"
    ".000, +2.3500000E-3, -1.9800000E-4\n"
    ".004, +2.1000000E-3, -1.4000000E-4\n"
)
report = parse_unsteady_plots(export)
assert report.steps == 2
assert report.series("CL")[-1] == 0.0021
```

READ THE STATUS OF THIS ONE BEFORE YOU RELY ON IT. The file's shape is
DOCUMENTED and not yet OBSERVED: no export of that command exists in
this repository, so the parser was written against the manual's
description and its fixture is synthetic and says so in its own header.
An emitted command is not a proven one, and a parser written against a
description is not a parser proven against a file. The first real export
is what turns this from documented into verified.

## Where to go next

* [Replaying a recorded run](tutorial-replay.md): what the manifest
  keeps, and how to reproduce a run from it months later.
* [Command reference](reference/index.md): every command, its
  arguments, and its evidence per version.
* [Compatibility matrix](compatibility.md): what is verified where.
* [Mesh inputs and GUI-only operations](mesh-inputs.md): the supported
  route when a step exists in the interface and has no script command.
