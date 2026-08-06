# pyflightstream

[![ci](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml/badge.svg)](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyflightstream)](https://pypi.org/project/pyflightstream/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21482924.svg)](https://doi.org/10.5281/zenodo.21482924)

Version-aware, didactic Python driver for the FlightStream panel-method
solver. Successor of the author's legacy research scripts. MIT licensed.

Status: v0.4.0 is public on [PyPI](https://pypi.org/project/pyflightstream/),
archived on Zenodo (DOI recorded in CITATION.cff). CHANGELOG.md carries
the release history.

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

try:
    Script(version="26.0").emit("SOLVER_SET_AOA", 4.0)
except CommandNotInVersionError as error:
    print(error)  # refused: no recorded evidence for that version
```

The worked examples in `examples/` take it from here to executed
polars, campaign matrices, a static wing deflection, and a Campbell
diagram. No example runs the coupled loop: it needs a licensed solver in the
loop, and the rotary case is solver-blocked (`reports/RPT-007`). The
capability status below says what the FSI subpackage does and does not
claim.

Optional extras: `[fsi]` (aeroelastic coupling, PyNiteFEA), `[geom]`
(probe-survey geometry gating, trimesh/rtree/scipy), `[plot]`
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

Every database entry carries a manual page citation, and its status per
version (documented, verified, broken) can only be promoted by citing a
committed probe report from a licensed machine. Nothing is guessed; the
honest gaps are reported as such.

## What ships

- Command database with per-version evidence and a manual citation on
  every entry, browsable offline via `pyflightstream.help()` (including
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
- Run-matrix support as a first-class interface: read, convert,
  pre-flight, and run the pipe-delimited 15-column matrix format.
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
| Rotary two-way coupling | **not validated** | `reports/RPT-007` states two-way rotor FSI is blocked in this build; `docs/srs/roadmap.md` records it in the M6 row; no acceptance evidence exists |

Experimental means the interface may change without the deprecation
window of NFR-20, and that the evidence behind it is narrower than
the supported rows: replaying archived fixtures shows the machine
runs, not that its physics is right for a case nobody has measured.

## Command-line tools

| Tool | Purpose |
|---|---|
| `pyfs-qa` | Tier 2 command-validity probes, Tier 3 physics regression and cross-version drift, status promotion from committed reports |
| `pyfs-workspace` | Initialize the managed campaign workspace tree |
| `pyfs-matrix` | Convert and pre-flight run matrices |
| `pyfs-manual` | Compare a FlightStream manual against the command database (maintainer tool, needs the `[manual]` extra; writes only with `--write`) |
| `pyfs-fsi` | The structural executable of the aeroelastic coupling loop |

## Supported FlightStream versions

"Supported" covered four different states, so it is now four named
values (`pyflightstream.SupportLevel`), every one of them derived from
the evidence rather than declared:

| Version | Vendor name | Support level | What that means here |
|---|---|---|---|
| 26.000 | 26.0 | `registered` | Ordered in the registry, no command carries evidence for it, so nothing can be built yet |
| 26.100 | 26.1 | `documented` | The February 2026 build. Commands drafted from its own manual edition with page citations; an ad-hoc probe ran some of them (RPT-018) and no status moves without a harness report, since the Tier 2 harness reaches only commands carrying a probe spec. The compatibility matrix carries the live counts |
| 26.101 | 26.1 | `documented` | The May 2026 build. Commands drafted from the manual with page citations, none promoted by a harness probe. It sits at a hotfix index and does NOT inherit from 26.100: the two are separate vendor releases under one name |
| 26.120 | 26.12 | `operational` | Probe evidence from a licensed machine, and the minimal end-to-end workflow builds |
| 26.121 | 26.12 | `operational` | Hotfix build 1. It inherits the 26.120 records except where a probe on this build overrode them; the compatibility matrix marks every inherited cell and counts them |

```python
import pyflightstream

for row in pyflightstream.support_table():
    print(row.summary)
```

`operational` is the level that claims a user can get from geometry to
a loads file, and it is checkable rather than asserted: it holds only
when `pyflightstream.support.minimal_workflow(version)` builds, which a
tier 1 test builds for every version reported at that level.

Canonical identifiers use the 26.XXX scheme, the last digit indexing
vendor hotfix builds, so 26.121 is hotfix build 1 of the 26.12 release.
The vendor ships both 26.120 and 26.121 under the one release name
"26.12", and both 26.100 and 26.101 under "26.1", so neither name
selects a build and each is refused with its candidates named; pass the
canonical identifier. A vendor name is unique only until the vendor
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
| `src/pyflightstream/commands/` | The command database: what exists in which FlightStream version, with manual page citations |
| `tests/` | Tier 1 tests, runnable anywhere, no FlightStream needed |
| `reports/` | Committed evidence from licensed machines: command validity (compat), physics regression, drift, and research cards |
| `docs/` | Documentation source (ProperDocs); reference pages are generated from the database, never committed |
| `examples/` | Runnable example scripts in percent format |
| `guide/` | LaTeX source of the user guide (the built pdf never enters Git) |
| `deprecated/` | Discontinued public items, grouped here instead of scattered at the top level |
| `.claude/skills/` | Maintenance procedures (version updates, command additions, QA runs, releases) |
| `_private/` | Local only, never committed: FlightStream manuals, executables, research geometry, the design documents and the plan ledger |

## Development setup

Maintainers: several machine-specific environment variables locate local
tooling and session state and are not in Git. A fresh clone must set
them in `.claude/settings.local.json`; `CLAUDE.md` (Session protocol)
is their single home, lists them, and states what each one does when
unset. The count is deliberately not repeated here: it lived in two
places and went stale in this one.

```
pip install -e .[dev,fsi,geom]
pre-commit install
pytest
```

Tier 1 (the pytest suite) runs anywhere. Tier 2 (command validity
probes) and Tier 3 (physics regression) require a local FlightStream
license and are documented in CONTRIBUTING.md. The docs build with
`properdocs build --strict`.

## License

MIT. Contributions must be original or MIT-compatible; code derived
from the AGPL pyFlightscript package is not accepted. See
CONTRIBUTING.md.
