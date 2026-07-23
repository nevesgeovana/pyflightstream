# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. Successor of the author's legacy research scripts. MIT licensed.

Status: v0.2.0 is public on [PyPI](https://pypi.org/project/pyflightstream/)
with the archived release on Zenodo (DOI 10.5281/zenodo.21482925; see
CITATION.cff). Development continues toward v0.3.0; CHANGELOG.md carries
the release history.

```
pip install pyflightstream
```

Optional extras: `[fsi]` (aeroelastic coupling, PyNiteFEA), `[geom]`
(probe-survey geometry gating, trimesh/rtree/scipy), `[plot]`
(matplotlib for the plotting examples).

## Why this package

FlightStream is scripted through an ASCII command file whose commands
change between solver versions, and not every change reaches the
changelog. This package makes the FlightStream version an explicit
input: every command it emits is validated against a per-version
command database, and old versions are only ever added, never dropped.

Every database entry carries a manual page citation, and its status per
version (documented, verified, broken) can only be promoted by citing a
committed probe report from a licensed machine. Nothing is guessed; the
honest gaps are reported as such.

## What ships

- Command database: 144 commands with per-version evidence and manual
  citations, browsable offline via `pyflightstream.help()` (including a
  manual-coverage section) and as a generated docs site.
- Validating script builder with curated helpers: phase ordering,
  didactic refusals at build time, entity labels (recipes can name
  frames, actuators, motions, and boundaries instead of raw indices),
  and a solver-setup provenance snapshot recording the effective value
  of every solver flag per run.
- Campaign workspace: an input-artifact library (references, solver
  presets, boundary groups, geometries, profiles, executables by build
  id), a run manifest as the single identity authority, output naming
  templates, campaign pre-flight with zero solver time, and resumable
  incremental sweeps.
- Runner and parsers: headless execution, anchor-based parsers for the
  solver outputs, and a pandas table layer (per-result tables, one wide
  row per run, whole-sweep DataFrame straight from the manifest).
- Legacy run-matrix support as a first-class interface: read, convert,
  pre-flight, and run the author's historical 15-column matrix format.
- Far-field probe surveys (planar grids, geometry gating, VTK/Tecplot
  writers, conservation ledgers on xarray) and an aeroelastic coupling
  subpackage (structural beam, coupled driver, replay harness).
- Architecture overview from the live module docstrings via
  `pyflightstream.overview()`.

## Command-line tools

| Tool | Purpose |
|---|---|
| `pyfs-qa` | Tier 2 command-validity probes, Tier 3 physics regression and cross-version drift, status promotion from committed reports |
| `pyfs-workspace` | Initialize the managed campaign workspace tree |
| `pyfs-matrix` | Convert and pre-flight legacy run matrices |
| `pyfs-fsi` | The structural executable of the aeroelastic coupling loop |

## Supported FlightStream versions

Registered: 26.000, 26.100, 26.120 (canonical 26.XXX scheme; the last
digit indexes vendor hotfix builds). The ordered list in
`src/pyflightstream/commands/_meta.yaml` is the only ordering
authority. Evidence is strongest on 26.120 (probed on a licensed
machine); 26.100 is partially backfilled from the manuals; the 26.000
column is honestly empty until probed. The compatibility matrix in the
docs is generated from the database at build time.

## What is each folder?

| Folder | Purpose in plain language |
|---|---|
| `src/pyflightstream/` | The package, one subpackage per pipeline stage (versions, commands, script, results, cases, run, workspace, post, qa, plus fsi, probes, farfield) |
| `src/pyflightstream/commands/` | The command database: what exists in which FlightStream version, with manual page citations |
| `tests/` | Tier 1 tests (448), runnable anywhere, no FlightStream needed |
| `reports/` | Committed evidence from licensed machines: command validity (compat), physics regression, drift, and research cards |
| `docs/` | Documentation source (mkdocs); reference pages are generated from the database, never committed |
| `examples/` | Runnable example scripts in percent format |
| `guide/` | LaTeX source of the user guide (the built pdf never enters Git) |
| `deprecated/` | Discontinued public items, grouped here instead of scattered at the top level |
| `.claude/skills/` | Maintenance procedures (version updates, command additions, QA runs, releases) |
| `_private/` | Local only, never committed: FlightStream manuals, executables, research geometry |

## Development setup

```
pip install -e .[dev,fsi,geom]
pre-commit install
pytest
```

Tier 1 (the pytest suite) runs anywhere. Tier 2 (command validity
probes) and Tier 3 (physics regression) require a local FlightStream
license and are documented in CONTRIBUTING.md. The docs build with
`mkdocs build --strict`.

## License

MIT. Contributions must be original or MIT-compatible; code derived
from the AGPL pyFlightscript package is not accepted. See
CONTRIBUTING.md.
