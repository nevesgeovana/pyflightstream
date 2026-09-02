# pyflightstream

[![ci](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml/badge.svg)](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyflightstream)](https://pypi.org/project/pyflightstream/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21482924.svg)](https://doi.org/10.5281/zenodo.21482924)

Version-aware, didactic Python driver for the FlightStream panel-method
solver. Successor of the author's legacy research scripts. MIT licensed.

Status: v0.10.1 is the current release. It publishes to
[PyPI](https://pypi.org/project/pyflightstream/) and archives on Zenodo
from the tag, so the concept DOI in CITATION.cff resolves to the newest
archived version and the version DOI is recorded one commit after the
tag that names it. CHANGELOG.md carries the release history.

**What changes for you, and what you must do.** v0.10.1 changes no
column of the run-matrix file and no cell you have already written. What
it changes is what one cell MEANS.

**A rotor row's `MOVING_BOUNDARIES` used to cite boundaries by their
POSITION** in one geometry's boundary order. Those positions were right
for the file they were written against and named different surfaces in
any file that ordered them differently, and nothing said so. Write the
names now, or the FAMILY they belong to, and the package reads the
geometry the row opens and resolves them:

    MOVING_BOUNDARIES: Blade,S

One cell, and it is right for a three-boundary sector and an
eight-boundary wheel alike. Positions still work and now warn, naming the
surfaces they actually selected, so nothing you have written stops
running.

**And this patch carries a third run type, `unsteady`,** an unsteady run
with nothing turning. It is a new capability under a patch number, by the
author's explicit exception, and it is named here because a patch number
will not carry that news on its own. It asks nothing of you: no existing
row changes. `docs/workspace-and-workflows.md` describes it.

**What v0.10.0 asked of you, kept here because a reader may be arriving
from 0.9.x.** v0.10.0 changes no
column of the run-matrix file, so no conversion is needed. Two things
still want a look before you re-run anything.

**Your solver preset now reaches the script, and that is the SILENT
half.** A preset key naming a real setting used to be honoured only
where the model already defaulted to it: a preset asking for
`SUBSONIC_PRANDTL_GLAUERT` ran `INCOMPRESSIBLE` and said nothing. Twelve
settings and eleven of the solver's own key spellings now reach the
emitted script. Nothing refuses and nothing warns; the NUMBERS move. On
the author's own campaign the axial force coefficient moved about one
percent. If your preset states anything the solver was not already
defaulting to, re-baseline before you compare against an older run.

The loud half is smaller: a preset key this package cannot emit at all
used to be dropped with a warning and is now refused, naming the key and
listing what applies. The remedy is usually one line in the preset file,
and for one key it is a line in the row instead, which the refusal says.

**Five names are now the package's inside `VAR_NAMES_VALUES`:**
`ADVANCE_RATIO`, `RPM_SIGN`, `DELTA_THETA`, `REVOLUTIONS` and
`LOG_OUTPUT`. The match is on the exact key. If a cell of yours already
spells one, rename yours or adopt the meaning; a row spelling
`ADVANCE_RATIO` or `RPM_SIGN` beside an existing `RPM` is REFUSED,
because that states the rotor speed twice.

If you are coming from v0.8.x you still have the older job. If you have
a run matrix written then, v0.9.0 changed its FILE FORMAT and you must
convert it.
The `RE` and `MACH` columns are gone, replaced by one mandatory
`FLIGHT_CONDITION` cell. A file written under either older layout is
recognised and refused rather than misread, so nothing runs silently
wrong; run this on it:

```
pyfs-matrix upgrade your_matrix.fs --in-place
```

**Then read the next sentence before you re-run a campaign.** The
conversion is lossless as a FILE, every value moving across verbatim,
and it is **not neutral as a RESULT**. Under v0.8.x the `RE` column was
recorded metadata that reached no emitted line; from v0.9.0 `REmi` is a
constraint that solves for density, so every upgraded row emits a fluid
state it never emitted before and your numbers will move. How far they
move is not something this repository can tell you, because the row
previously emitted NO fluid state at all and what the solver assumed
instead is a question about the solver. What is measured, on this
repository's own fixture, is the state your row will now be run at: one
row solves at 1.3319 kg/m3, 8.7 percent above sea level. To keep the
previous behaviour, state the condition without `REmi`.
[docs/flight-conditions.md](docs/flight-conditions.md) is the whole
grammar, the units, and the migration in full.

The earlier upgrade action still applies if you are coming from before
v0.8.1: three names inside the free
`VAR_NAMES_VALUES` cell of a run matrix are the package's:
`GEOMETRY`, `SYMMETRY` and `PERIODIC_COPIES`. If a cell of yours already
spells one of them, the package reads it, so rename your key or
stage the file the id names. The match is on the exact key, so a cell
spelling it `SYMMETRY_TYPE` is untouched, and a row that names none of
the three renders the script it always did.

**What v0.8.1 fixed**, and it is why a patch followed v0.8.0 by two
days. A run matrix had no way to name a geometry at all, so a workflow
built a script with no `OPEN` in it: the solver solved whatever it
already had in memory, and reported numbers with nothing said. A row
names its geometry now, and declares the symmetry a periodic sector
needs, which was fixed at `NONE` so a sector ran as a one-bladed rotor
and converged. Separately, `pyfs-matrix run` could not run at all under
its own documented default: `--workspace` defaults to `"."` and every
path was then spelled from your directory while the solver resolved it
from the run's.

Everything each earlier release broke or added is described under its
own heading in CHANGELOG.md, which carries the reasoning, the
measurements and the rejected alternatives behind every entry. The word
"unchanged" used to stand here about v0.8.0's four breaking changes, and
a review pointed out that a reader cannot check it: the four were never
enumerated, and v0.9.0 has just changed the same file format again.

```
pip install pyflightstream
```

A first taste, no solver required (build time is where errors surface):

```python
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import Script

script = Script(version="26.120")  # the FlightStream version is explicit input
script.emit("NEW_SIMULATION")
script.emit("IMPORT", "METER", "STL", "wing.stl", clear=True)
script.emit("SOLVER_SET_AOA", 4.0)
script.emit("START_SOLVER")
print(script.render())  # validated ASCII script, ready for the solver

# The version is checked, and the check ASSERTS rather than prints:
# an example whose only claim is that something is refused goes green
# in CI the day the refusal stops firing, which is how this block came
# to promise a refusal it no longer made.
try:
    Script(version="26.0").emit("CAD_CREATE_BOX", frame=1, x=0.0, y=0.0, z=0.0,
                                len_x=1.0, len_y=1.0, len_z=1.0)
    raise AssertionError("26.000 has no CAD chapter; this must refuse")
except CommandNotInVersionError as error:
    print(error)  # the CAD primitives arrive at 26.100
```

The worked examples in `examples/` take it from here to executed
polars, campaign matrices, a static wing deflection, and a Campbell
diagram. No example runs the coupled loop: it needs a licensed solver in the
loop, and the rotary case was solver-blocked on 26.120 and 26.121
(`reports/RPT-007`), which `reports/RPT-025` measures fixed in 26.122. The
capability status below says what the FSI subpackage does and does not
claim.

Optional extras: `[fsi]` (aeroelastic coupling, PyNiteFEA), `[geom]`
(the SPATIAL INDEX behind probe-survey geometry gating, rtree and scipy;
the mesh reader itself, trimesh, left this extra and is a runtime
dependency since v0.8.0), `[plot]`
(matplotlib for the plotting examples), and `[manual]` (pypdf), which
is maintainer tooling rather than a user feature: it backs `pyfs-manual`
and nothing in a run imports it.

## Why this package

FlightStream is scripted through an ASCII command file, and the solver
is under active development: the FlightStream team is responsive to
user requests and works with intermediate hotfix builds that
consolidate into stable releases. A fast-moving solver naturally means
a scripting command set that evolves from version to version, faster
than any single document can track. This package makes the
FlightStream version an explicit input: every command it emits is
validated against a per-version command database, and old versions are
only ever added, never dropped, so campaigns stay reproducible across
that evolution.

Every database entry carries exactly one piece of evidence: the manual
page that documents the command, or, for the few the solver accepts and
no manual edition describes, a committed probe report measuring that it
does. Every status that rests on a RUN (verified, broken, and a
removed the solver refused) can only be promoted by citing a committed
probe report from a licensed machine; a removed read off an edition is
a hand-written row carrying a note and a page.
Nothing is guessed; the honest gaps are reported as such.

## What ships

- Command database with per-version evidence and a manual or probe-report
  citation on every entry, browsable offline via `pyflightstream.help()`
  (including
  a manual-coverage section) and as a generated docs site; the
  compatibility matrix carries the live counts.
- Validating script builder with curated helpers: phase ordering,
  didactic refusals at build time, entity labels (recipes can name
  frames, actuators, motions, and boundaries instead of raw indices),
  and a solver-setup provenance snapshot recording the effective value
  of every solver flag per run. A command a probe measured `broken` in
  the target version is refused too, because that one produces a
  complete run with wrong numbers rather than no run at all; the
  waiver that emits it anyway records the report and the reason in the
  manifest.
- Campaign workspace: an input-artifact library (references, solver
  presets, boundary groups, geometries, profiles, executables by build
  id), a run manifest as the single identity authority, output naming
  templates, campaign pre-flight with zero solver time, and resumable
  incremental sweeps.
- Runner and parsers: headless execution, anchor-based parsers for the
  solver outputs, and a pandas table layer (per-result tables, one wide
  row per run, whole-sweep DataFrame straight from the manifest).
- Run-matrix support as a first-class interface: read, upgrade,
  convert, pre-flight, and run the pipe-delimited 15-column matrix
  format. Each row states its whole flow condition in one mandatory
  `FLIGHT_CONDITION` cell, and `WORKFLOW` names the run type the package
  builds for that row. A matrix written under either older layout is
  RECOGNISED and refused naming its converter:
  `pyfs-matrix upgrade <path> --in-place`.
- Far-field probe surveys (planar grids, geometry gating, VTK/Tecplot
  writers, conservation ledgers on xarray) and an aeroelastic coupling
  subpackage (structural beam, coupled driver, replay harness).
- Architecture overview from the live module docstrings via
  `pyflightstream.overview()`.
- Predictable surfaces: a declared-options registry
  (`pyflightstream.options`), one public exception catalog
  (`pyflightstream.exceptions`), test assertions with quantified
  reports (`pyflightstream.testing`), and the house conventions
  rendered by `help()`.

## Capability status

Not every subpackage carries the same weight of evidence, and until
2026-08-03 nothing said so: an independent review found the feature
list above reading as one uniform claim, with the aeroelastic
boundary stated only inside the code. The author's decision of
2026-08-03 is that the FSI and probe-survey paths are **experimental**
behind an explicit boundary rather than release-supported, and this
table is that boundary.

| Capability | Status | Evidence |
|---|---|---|
| Command database, script builder, version refusals | supported | tier 1 over every registered version; probe reports under `reports/` |
| Parsers, tables, run manifest, reconstruction | supported | tier 1 on committed solver fixtures |
| Campaigns, run matrices, workspace, pre-flight | supported | tier 1 end-to-end with a stub solver |
| Far-field ledgers and probe surveys | **experimental** | tier 1 on synthetic fields; the licensed far-field acceptance work is deferred, not done |
| FSI structural beam and modal analysis | **experimental** | tier 1 against analytic beam solutions; `examples/wing_static_deflection.py`, `examples/fsi_campbell_diagram.py` |
| FSI coupled driver (the four-phase loop) | **experimental** | tier 1 offline replay on archived WP1 fixtures only; never run against a live solver in CI |
| Rotary two-way coupling | **not validated** | `reports/RPT-025` measures the solver defect of `reports/RPT-007` fixed in 26.122 and still present in 26.120 and 26.121, so the path is no longer blocked on 26.122. It stays NOT VALIDATED: that report says only that an imposed deformation reaches the mesh, not that the morphing is correct, and no coupled acceptance run has been made against a build where it applies |

Experimental means the interface may change without the deprecation
window of NFR-20, and that the evidence behind it is narrower than
the supported rows: replaying archived fixtures shows the machine
runs, not that its physics is right for a case nobody has measured.

## Command-line tools

| Tool | Purpose |
|---|---|
| `pyfs-qa` | Tier 2 command-validity probes, Tier 3 physics regression and cross-version drift, status promotion from committed reports |
| `pyfs-workspace` | Initialize the managed campaign workspace tree |
| `pyfs-matrix` | Upgrade, convert, pre-flight and run run matrices |
| `pyfs-manual` | Compare FlightStream manuals against the command database: one manual, every registered edition at once (`sweep`, which reports both what has no entry and what an edition documents that its build cannot emit), what each build documents and what changed between builds (`surface`), or whether the citations already written still point where they say (`citations`, the one subcommand that fails by default on a finding, because a citation that does not hold is a statement already shipped rather than work remaining). `register` carries a build's documentation forward: for every command a new edition describes exactly as its predecessor did, it writes a `documented` row citing the new edition, and it reports rather than writes anything described differently. Maintainer tool; needs the `[manual]` extra, and only `draft` and `register` write, both with `--write` and both dry-run by default. `register` is the one that edits the command database rather than emitting a file |
| `pyfs-fsi` | The structural executable of the aeroelastic coupling loop |

## Supported FlightStream versions

"Supported" covered four different states, so it is now four named
values (`pyflightstream.SupportLevel`), every one of them derived from
the evidence rather than declared:

| Version | Vendor name | Support level | What that means here |
|---|---|---|---|
| 25.000 | 25.0 | `documented` | Vendor build 12162024, December 2024. Registered on 2026-08-09 so that published work run on it has an identifier that resolves, and its own manual read command by command on 2026-08-10. Not yet `operational`, and the blocker is solver evidence rather than database rows: no command has been measured on this build, and the level stops at `documented` for that reason before the workflow is even considered. 26.000 shows it, having every workflow command and the same level. Its manual documents 272 commands and 268 are emittable, the difference being four readings withheld where a version row cannot express a layout (PLN-20260810-1200). Behind the evidence gap there is also a workflow one: this edition runs the trailing-edge autodetection from inside a `PHYSICS` block and the standalone command arrives at 26.000 |
| 25.100 | 25.1 | `documented` | Vendor build 5062025, May 2025. Registered for the same reason. Its manual documents 274 commands and 270 are emittable, with the same four layout withholdings, and it uses the same `PHYSICS` block as 25.000. The 25 series checks out an EDU licence rather than the full feature set, so what either of these builds refuses may be the licence rather than the build; that is not yet measured |
| 26.000 | 26.0 | `documented` | Vendor build 10202025, October 2025. Its manual documents 276 commands and 274 are emittable, the two withheld for the same layout reason. Nothing has been probed on it either, which is what holds it at this level. The CAD BODY operations, the four CAD primitives and the three CCS mesh chapters do not exist in this edition; they arrive with 26.100. What it does document, and what its sixteen CAD rows are, is CAD import and conversion plus the curve and cross-section commands |
| 26.100 | 26.1 | `operational` | The February 2026 build, and the last of the pre-26.12 builds to reach this level, on 2026-08-08. It was held at `verified` less by the solver than by the database: the per-edition sweep that day found 40 commands its own manual documents and this database had no row for, so the emitter refused them and the minimal end-to-end workflow could not be built. With those rows written the workflow builds. Probe coverage is still thinner here than on the newer builds, the harness reaching only commands that carry a probe spec; the compatibility matrix carries the live counts |
| 26.101 | 26.1 | `operational` | The May 2026 build. Commands drafted from the manual with page citations, with the first harness promotions on 2026-08-08, which also carried it to the level where the minimal end-to-end workflow builds. It sits at a hotfix index and does NOT inherit from 26.100: the two are separate vendor releases under one name |
| 26.120 | 26.12 | `operational` | Probe evidence from a licensed machine, and the minimal end-to-end workflow builds |
| 26.121 | 26.12 | `operational` | Hotfix build 1. It inherits the 26.120 records except where a probe on this build overrode them; the compatibility matrix marks every inherited cell and counts them |
| 26.122 | 26.12 | `operational` | Hotfix build 2, vendor build 8092026, registered 2026-08-10 the day after it was issued. Its manual documents the largest command surface of the nine editions, 372 against 364 for the one before it and 371 for the one after, which deletes a command from its chapter body. Measured on 2026-08-11: 84 commands probed on this build (83 verified, 1 broken) and the Tier 3 matrix passing 30 of 30 metrics (`reports/physics/PHY-26122_2026-08-11_rotor.yaml`). The rest of its record is still inherited from 26.120 and the matrix marks every inherited cell. The run refuted the inheritance once, on `AIR_ALTITUDE`, which is broken on the base releases and works here |
| 26.123 | 26.12 | `operational` | Hotfix build 3, delivered 2026-08-16 and registered 2026-08-17, the day after. It is the first build in this project that INHERITS NOTHING, by the author's decision, so it claims support only for what has been measured or read on IT rather than on 26.120. Read the level as a statement about evidence and not about the build: it reached `operational` the same day, in two steps. First 369 of the 371 commands its own edition documents were compared word for word against the edition before it and given a row. Then a probe run measured 85 of them on this build, 84 accepted and one refused (`reports/compat/CMP-26123_2026-08-17_full-sim.yaml`), which is one more verified than 26.122 has and the same single broken command, `NEW_OFF_BODY_STREAMLINE`, that three builds now carry on their own evidence. The emitter still refuses the commands that carry no row at all, and the enumeration of exactly which, with their count in its own header, is committed as `tests/goldens/absent_on_26123.txt`. The number is NOT repeated here: this sentence said 45 against a golden that says 43, in the paragraph whose whole purpose is that the gap is a number a reader can check. Its manual is 417 pages like 26.122's and every page outside seventeen is text-identical, so a page citation transfers where the seventeen do not touch it |

```python
import pyflightstream

for row in pyflightstream.support_table():
    print(row.summary)
```

`operational` is the level that claims a user can get from geometry to
a loads file, and it is checkable rather than asserted: it holds only
when `pyflightstream.support.minimal_workflow(version)` builds, which a
tier 1 test builds for every version reported at that level.

Not sure which one you have? Every install prints its release name and
its build number when it starts, and the generated
[Which build do I have](https://nevesgeovana.github.io/pyflightstream/builds/)
page maps that pair onto the identifier to pass. The release name alone
does not identify a build.

Canonical identifiers use the YY.XXX scheme, the last digit indexing
vendor hotfix builds, so 26.121 is hotfix build 1 of the 26.12 release.
The vendor reuses a release name across builds, so a release name may
name more than one, and the families it has produced are not all alike: one is a release with its hotfixes, the other is
two separate releases that happen to share a name. Which builds sit in
either is a fact about the registry rather than about this page, so it
is not written here; the refusal enumerates them from the registry and
the generated build page carries the tally. Pass the canonical
identifier. A vendor name is unique only until the vendor
ships the next build under it, which is why a script should not rely on
one. The ordered list
in `src/pyflightstream/commands/_meta.yaml` is the only ordering
authority, and it orders releases, not support: 26.100 is newer than
26.000 and both sit below 26.120. Supported versions are only ever
added, never dropped, which is why the February 2026 build entered as
26.100 and the May build it displaced was appended as 26.101 rather
than either being renamed away. The compatibility matrix in the docs is generated
from the database at build time.

## What is each folder?

| Folder | Purpose in plain language |
|---|---|
| `src/pyflightstream/` | The package, one subpackage per pipeline stage (versions, commands, script, results, cases, run, workspace, post, qa, plus fsi, probes, farfield) |
| `src/pyflightstream/commands/` | The command database: what exists in which FlightStream version, with a manual page or probe-report citation per entry |
| `tests/` | Tier 1 tests, runnable anywhere, no FlightStream needed |
| `reports/` | Committed evidence from licensed machines: command validity (compat), physics regression, drift, and research cards |
| `docs/` | Documentation source (ProperDocs); reference pages are generated from the database, never committed |
| `examples/` | Runnable example scripts in percent format |
| `guide/` | LaTeX source of the user guide (the built pdf never enters Git) |
| `deprecated/` | Discontinued public items, grouped here instead of scattered at the top level |
| `_private/` | Local only, never committed: FlightStream manuals, executables, research geometry, the design documents and the plan ledger |

## Development setup

Maintainers: **no tracked file here reads a named environment variable to
configure this package**, and a fresh clone is owed no list of them. The
wording is careful and the earlier draft was not: the run layer does hand
the AMBIENT environment to the solver subprocess, because the solver's own
licence server address and installation variables live there, and a
sentence saying this repository reads nothing at all would send a
maintainer hunting a licence failure that is not a bug. What no tracked
file does is read a NAMED variable to decide how this package behaves.
The licensed solver is located by a required argument that is never
guessed, `--fs-exe` on the quality-assurance command line; a run matrix
locates it instead through its workspace's own executables table. An earlier version of
this paragraph said a few machine-specific variables located the solver
and its manuals for the licensed tiers, and pointed at a file that
stopped being published. Both halves were wrong, and the paragraph
shipped inside the package metadata, so it reached every reader of the
published page.

The contributor rules a clone does need are the numbered hard invariants
in `CONTRIBUTING.md`.

```
pip install -e .[dev,fsi,geom]
pre-commit install
pytest
```

Tier 1 (the pytest suite) runs anywhere. Tier 2 (command validity
probes) and Tier 3 (physics regression) require a local FlightStream
license and are documented in CONTRIBUTING.md, which also says which
extras a full run needs and why two of them are left out on purpose.
The docs build with `properdocs build --strict`.

## License

MIT. Contributions must be original or MIT-compatible; code derived
from the AGPL pyFlightscript package is not accepted. See
CONTRIBUTING.md.
