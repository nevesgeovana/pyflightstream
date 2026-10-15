# pyflightstream

[![ci](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml/badge.svg)](https://github.com/nevesgeovana/pyflightstream/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyflightstream)](https://pypi.org/project/pyflightstream/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21482924.svg)](https://doi.org/10.5281/zenodo.21482924)

Version-aware Python driver for the FlightStream panel-method solver: write a
run matrix, and pyflightstream plans, runs and post-processes every point,
from your workstation or a cluster. MIT licensed.

Use the [upgrade guidance](https://nevesgeovana.github.io/pyflightstream/upgrading/)
when moving an existing workspace to a newer package version.

**Documentation: [nevesgeovana.github.io/pyflightstream](https://nevesgeovana.github.io/pyflightstream/)**

## What it does

```
matrix  ->  plan  ->  run  ->  collect  ->  post  ->  products
(.fs)       (free,     (local     (cluster     (polars, rotor tables,
            no solver) or HPC)    jobs)        sections, averages, provenance)
```

- **One row, one simulation.** A pipe-separated matrix names each case, its
  flight condition, its sweep and the input artifacts it uses (reference,
  setup, post-processing).
- **Checked before it costs a licence.** `plan` builds every script without
  the solver and refuses what the target FlightStream build cannot run, with
  the reason.
- **Every command has evidence.** Each solver command is validated against a
  per-version database; every entry cites a manual page or a committed probe
  report.
- **Products you open directly.** CSV polars, rotor coefficient tables,
  sections, probes and time averages, each stating the flight condition it
  belongs to, plus a provenance record per run.

## Install

```
pip install "pyflightstream[geom,fsi,plot,excel]"
```

Python 3.12 or newer. FlightStream itself is licensed separately and is
located through your workspace, never guessed.

## Quick start without a solver

```
pyfs-workspace init my-study
```

[Getting started](https://nevesgeovana.github.io/pyflightstream/getting-started/)
starts with an executable solver-free example, then walks the geometry,
matrix, reference, setup and post-processing inputs needed before planning.
Initialization creates `my-study/inputs/INPUTS.md`; read it next. Planning
needs those inputs but no solver license. Running requires a separately
licensed FlightStream installation.

[From the GUI to pyfs](https://nevesgeovana.github.io/pyflightstream/gui-to-pyfs/)
maps each GUI step to the key that takes it here.

## Command-line tools

| Tool | What it is for |
|---|---|
| `pyfs-workspace` | Create or migrate a workspace; archive simulations; prepare geometry, custom fields and actuator profiles |
| `pyfs-matrix` | Plan, run, collect and post a run matrix; storage (`space-in-use`, `free-space`, `delete-sims`) and `sync` between workspaces |
| `pyfs-qa` | Command-validity probes and physics regression on a licensed machine |
| `pyfs-fsi` | The structural executable of the aeroelastic coupling loop |
| `pyfs-manual` | Maintainer tool: compare FlightStream manuals with the command database |

## Capability status

| Capability | Status |
|---|---|
| Command database, script builder, version refusals | supported |
| Parsers, tables, run manifest, reconstruction | supported |
| Campaigns, run matrices, workspace, pre-flight | supported |
| Far-field ledgers and probe surveys | **experimental** |
| FSI structural beam and modal analysis | **experimental** (`docs/examples/_sources/wing_static_deflection.py`, `docs/examples/_sources/fsi_campbell_diagram.py`) |
| FSI coupled driver (the four-phase loop) | **experimental**: offline replay only, never run against a live solver in CI |
| Rotary two-way coupling | **not validated** |

Experimental means the interface may change without a deprecation window,
and the evidence behind it is narrower than for the supported rows.

## Supported FlightStream versions

| Version | Vendor name | Support level |
|---|---|---|
| 25.000 | 25.0 | `documented` |
| 25.100 | 25.1 | `documented` |
| 26.000 | 26.0 | `documented` |
| 26.100 | 26.1 | `operational` |
| 26.101 | 26.1 | `operational` |
| 26.120 | 26.12 | `operational` |
| 26.121 | 26.12 | `operational` |
| 26.122 | 26.12 | `operational` |
| 26.123 | 26.12 | `operational` |
| 26.124 | 26.12 | `operational` |
| 26.125 | 26.12 | `operational` |

`operational` means the minimal geometry-to-loads workflow builds for that
version, checked by a test. `documented` describes the database support level;
it does not imply that no measurements exist for that build. Individual commands
may carry different evidence. The details, and how to tell
which build you have, are on
[Which build do I have](https://nevesgeovana.github.io/pyflightstream/builds/):

```python
import pyflightstream

for row in pyflightstream.support_table():
    print(row.summary)
```

## Contributing

```
pip install -e .[dev,fsi,geom]
pre-commit install
pytest
```

The hard invariants are in `CONTRIBUTING.md`. Tier 1 runs anywhere; tiers 2
and 3 need a licensed FlightStream and are described in
[the test tiers](https://nevesgeovana.github.io/pyflightstream/tiers/).

## Citing and license

Cite the release you used through its Zenodo DOI (`CITATION.cff`). MIT
licensed; contributions must be original or MIT-compatible, and code derived
from the AGPL pyFlightscript package is not accepted.
