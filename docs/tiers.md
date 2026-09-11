# The test tiers, and the licensed workspace

The suite is three folders under `tests/`, and the folder says what a
test needs before it says what it checks.

| Folder | Needs | What it proves | How it runs |
|---|---|---|---|
| `tests/tier1_offline` | nothing but the package | the command database is consistent, the emitter refuses per version, the parsers read the committed fixtures, every generated script equals its golden, and the tier-3 matrices plan READY without a seat | `pytest`, the default |
| `tests/tier2_validity` | a licensed solver | each database command does what its manual page says on a given build; the reports land under `reports/compat/` and statuses are promoted from them | `pyfs-qa probe` on the licensed machine |
| `tests/tier3_licensed` | a licensed solver | the whole workspace runs: every capability of the run matrix is a row, every row ran on the build it names, and one test per row asserts what came back | `pyfs-matrix run` per matrix, then `pytest -m needs_flightstream tests/tier3_licensed` |

Every module of the two licensed tiers carries the `needs_flightstream`
marker and the default `pytest` deselects it, so a clone with no seat
runs tier 1 alone and is told nothing about the other two except that
their matrices are sound.

## Tier 3 is a workspace

`tests/tier3_licensed` is not a folder of tests that happens to hold a
workspace. It IS a campaign workspace, laid out exactly as
[the workspace page](workspace-and-workflows.md) describes: `inputs/`
with the library, `sims/` and `post/` written by the runs, `runs.json`
as the one manifest, and seven run matrices at the root. The tests sit
beside the matrices and read what the runs recorded. That makes it the
largest usage example this repository carries: every feature of the
matrix, set through the workspace, with the row that sets it and the
test that checks it.

### The library

`inputs/geometries/` holds nine saved simulations, every one SYNTHETIC:
a NACA 0012 wing and its half at two resolutions, a blunt body with a
flat base, a blade and its physics-resolution twin, a pusher body with a
two-blade rotor behind its base, and a twin-rotor body whose second rotor
is the mirror image of the first. They are generated from public shape
laws by `recipes.py` and saved by the solver through `prepare.py`, which
imports the STL parts with their length units declared, detects the
trailing edges and the wake termination nodes, and saves the file; each
file is committed beside its boundary sidecar and a provenance record
carrying the generator, the specs, the build and the sha256. Nothing
of the author's enters, and a guard refuses a saved simulation in that
folder without its provenance record.

```text
python -m tests.tier3_licensed.prepare            # every missing shape
python -m tests.tier3_licensed.prepare twin       # one shape
```

The rest of the library is five references (`r001` the wing, `r002`
the body, `r003` the isolated rotor, `r004` the installed rotor, `r005`
the qa cases' block with the moment point at the origin), eight setups
(`s001` the tour preset through `s008`, each a comment on what it
changes; `s008` is `s001` plus one raw solver line before init
(PFS-2033.01), whose row 2004 is booked to run on the author's seat
(PFS-2033.03)), three
post-processing profiles, and a reference-point file
with the airframe point `ARP` and the rotor points `ERP1` to `ERP3`.

### The machine's own file

The committed `inputs/executables.toml` maps the build ids `26.120` and
`26.123` onto placeholder paths, because an installation path is machine
configuration and never enters Git. The machine that runs tier 3 writes
`inputs/executables.local.toml` beside it, gitignored, with the same ids
and its own paths (PFS-2031.15):

```toml
"26.120" = "C:/builds/26120/FlightStream.exe"
"26.123" = "C:/builds/26123/FlightStream.exe"
```

The package reads that overlay over the registry, so every row runs on
the build its `FS_BUILD` cell names and nothing is passed on the command
line but the matrix and the workspace.

### The seven matrices

| Matrix | What it is | Rows |
|---|---|---|
| `matriz.fs` | the tour: every column, every key, every run type, every input kind | 1001 a steady polar with the fluid pins from the setup; 1002 the half wing mirrored with velocity and density on the row; 1003 a sideslip sweep at altitude on a hot day; 1004 a combined sweep with every pin on the row; 1005 the body detecting its base on the second build; 1006 an inactive row; 1010 and 1011 the rotorless unsteady clock in seconds and in azimuth; 1020 one blade under periodic symmetry; 1021 the installed pusher with a signed RPM and its hub by a point; 1022 two rotors from a MOTIONS list; 1090 a LEGACY row naming its recipe in the cell |
| `matriz_setup.fs` | one point, four presets | 2001 the tour preset, 2002 tighter and longer, 2003 incompressible without stabilization, 2004 the tour preset plus one raw line (booked for the author's seat, not yet run) |
| `matriz_vocab.fs` | the 0.15.0 vocabulary, on the twin geometry | 8001 a rotor named by alias, 8002 two rotors at two speeds from ONE advance ratio, 8003 one rotor held while the other sweeps, 8004 a rotation citing an alias and keeping the frame it turned from, 8005 a raw solver command the row states itself. It is the workspace the getting-started walkthrough sends a reader to copy, so its files are written to be read: `r006.toml` and `p005.toml` state the same aircraft as `r004.toml` and `p003.toml` in the newer vocabulary, and the two pairs are kept side by side so the difference can be diffed rather than described |
| `matriz_time.fs` | one rotor at six step sizes, 30 down to 2.5 deg, one wing at two | 3001 to 3006, 3010 and 3011 |
| `matriz_geometry.fs` | one condition, four shapes | 4001 the wing, 4002 its mirrored half, 4003 the body, 4004 the wing with its boundary renamed before the save (RPT-044) |
| `matriz_physics.fs` | the qa physics cases as rows | 5001 PHY-01, 5002 and 5003 PHY-02, 5005 PHY-05, 5006 PHY-06 |
| `matriz_actions.fs` | the unsteady solver actions | 6001 on 26.123, RPT-041 the script-action re-read probe; 6002 the `unsteady` type exporting after iteration 4 of 8 through the two actions of PFS-2031.18, RPT-045 |
| `matriz_builds.fs` | one rotor row per build this machine holds | 7001 on 26.120 and 7002 on 26.123, RPT-043 the thirteen solver-setting emitters of the rotor path |

Each matrix keeps its own `plan.json`, `campaign_sweep.csv` and products under
`post/<matrix stem>/` (PFS-2031.04); `runs.json` holds every point of
all seven.

### Running it

```text
pyfs-matrix plan matriz.fs --workspace tests/tier3_licensed     # no seat
pyfs-matrix run matriz.fs --workspace tests/tier3_licensed      # the seat
pytest -m needs_flightstream tests/tier3_licensed
```

`test_tour.py`, `test_studies.py`, `test_physics.py`,
`test_actions_probe.py`, `test_actions.py` and `test_builds.py` read the manifest, the script each point's
solver received, the loads it exported and the products the run left,
through the package's own readers, and assert per row what the row's
cell was meant to reach. The physics module asks
`pyflightstream.qa.matrix.reduce_physics` for the judged run: the rows'
loads reduced with the functions of `pyflightstream.qa.physics` and judged
against the committed references under `qa/references/`, so a FAIL there
says either that the workflow builds the case differently from what the
reference was recorded on or that the solver moved, and the diff of the
row's script against its golden says which. An identity that holds
without a band of the author's, the antisymmetry of the side force under
sideslip for one, is asserted to the solver's measured noise and says so;
a number that needs a band the author has not set is read and reported, not
judged.

### The physics report is read out of the workspace

`pyfs-qa physics` is a reader of this workspace since 0.13.0
(PFS-2031.17, the author's decision B of 2026-09-08): it runs
`matriz_physics.fs` through the run layer exactly as `pyfs-matrix run`
does, reduces the records with the qa functions and writes the same
`reports/physics/PHY-*` pair the hand-built scripts wrote. The hand-built
builders of PHY-01, PHY-02, PHY-05 and PHY-06 retired with it; the rows
are the one place a case is stated.

```text
pyfs-qa physics --workspace tests/tier3_licensed --resume     # the matrix already ran: no seat
pyfs-qa physics --workspace tests/tier3_licensed              # runs the matrix, then reports
pyfs-qa drift   --workspace tests/tier3_licensed --fs-versions 26.120,26.123 --fs-exe 26.120=C:/builds/26120/FlightStream.exe --fs-exe 26.123=C:/builds/26123/FlightStream.exe
```

`--resume` is the form for a workspace whose matrix already ran: the
recorded points are skipped, nothing executes, and the report is the
reduction of what `runs.json` holds. Without it a recorded point is
refused before anything executes, as `pyfs-matrix run` refuses it. The
report names its source (`matriz_physics.fs in workspace tier3_licensed`)
and the one build every active row names; rows naming two builds are
refused, because two builds of one case set is a drift. `pyfs-qa drift`
makes a workspace per side under `--workroot` (`a_26120`, `b_26123`), a
copy of the library and the matrix with an `executables.local.toml`
overlay sending every build id the rows name to that side's executable,
runs the matrix in each, and diffs the two reductions inside the case
bands centered on side A (`reports/physics/DRF-*`).

### What a clone without a seat still gets

`tests/tier1_offline/test_tier3_offline.py` plans every matrix of the
workspace with the package and compares every rendered script to its
golden under `tests/tier3_licensed/goldens/`, with the workspace path
replaced by `<tier3>` and its separators written as forward slashes, so one
set of goldens serves Windows and Linux and a change in the package that
moves a tier-3
script is seen on the row it moves before any seat is spent; and it
plans the refusals, six one-row matrices over a copy of the library and
one second matrix stating a POL the tour states, each asserting that the
workspace refuses the row naming the cause. Regenerate
the goldens when a script is meant to move:

```text
python -m tests.tier3_licensed.offline           # report
python -m tests.tier3_licensed.offline --write   # regenerate
```
