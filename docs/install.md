# Install pyflightstream

## Supported Python

Use Python 3.12 or newer (`>=3.12`), with no Python upper bound.
CI tests Python 3.12 on Linux and Windows.
The `test-lean` CI job runs tier 1 with `pytest -n auto` using the base
package and development tools, without user-facing extras.


## Tested dependency ranges

The endpoint CI jobs run tier 1 at every declared floor and at the newest
release pip resolves within each range. Both read `pyproject.toml`; `manual`
and `dev` are maintainer extras and are outside this runtime range policy.

| Dependency | Range | Installation |
|---|---|---|
| NumPy | `>=2.2,<3` | Base |
| Pydantic | `>=2.10,<3` | Base |
| PyYAML | `>=6.0.1,<7` | Base |
| trimesh | `>=4.12,<6` | Base |
| matplotlib | `>=3.10,<4` | Base |
| rtree | `>=1.1,<2` | Base |
| SciPy | `>=1.15,<2` | Base |
| pandas | `>=2.3,<3` | `pandas` extra |
| PyNiteFEA | `>=3.0,<4` | `fsi` extra, which also raises NumPy to `>=2.4` (PyNiteFEA 3 requires it) |
| XlsxWriter | `>=3.2.9,<4` | `excel` extra |

Existing floors are unchanged. PyYAML gains its first explicit floor, 6.0.1.
The existing trimesh range includes the measured 5.x major; its ceiling remains 6.

## Choose an installation route

| Environment | Route |
|---|---|
| Workstation | Install the package in a virtual environment with pip. |
| Cluster | Install in the environment used by the cluster profile. |
| Offline | Download the package and dependencies on a connected machine, then install from the local wheelhouse. |

## Install with pip

Install the release into an isolated Python environment, then select the
optional extras needed by the workflow. The `excel` extra adds workbook
synchronization; the `manual` extra supports manual database maintenance.
The `pandas` extra provides `Table.to_pandas()` for dataframe workflows:
`pip install "pyflightstream[pandas]"`. Parsing, NumPy tables and CSV products
work with the core install alone. See [upgrading](upgrading.md#numpy-tables-and-optional-pandas).

## Choose the FlightStream build

Use [Which build do I have](builds.md) to map the solver build to the package
version identifier. Install does not install or license FlightStream.

## Check the installation

Run `pyfs-matrix --help` to check the command is available; it exits 0 and
lists the installed subcommands. Use `pyfs-matrix <subcommand> --help` to
inspect the options of one before preparing a run.

## Read the documentation offline

Each release has its documentation edition, `pyflightstream-docs-<version>.zip`,
among the release's assets on GitHub, built from that release's own sources. Unzip it and
open its `index.html` in a browser: the pages and the requirements, code and execution
views work from the folder with no network connection. Search does not work
offline, since it needs a server; use the navigation or the browser's find in page.

## Dependency licenses

The package uses these third-party libraries. The versions below identify the
distributions inspected for the license summary, rather than installation pins.
The installed distributions supply their own copyright notices and license texts;
preserve those notices when redistributing them.

| Library | Version inspected | License recorded |
|---|---|---|
| numpy | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pandas (`pandas`) | 3.0.3 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| PyYAML | 6.0.3 | MIT |
| trimesh | 4.12.2 and 5.0.0 | MIT |
| PyNiteFEA (`fsi`) | 3.0.0 | MIT |
| scipy | 1.18.0 | BSD-3-Clause |
| rtree | 1.4.1 | MIT |
| matplotlib | 3.11.1 | Matplotlib License, derived from the PSF license |
| pypdf (`manual`) | 6.14.2 | BSD-3-Clause |
| XlsxWriter (`excel`) | 3.2.9 | BSD-2-Clause |

This summary describes the inspected versions. It does not establish the licenses
of future releases or every transitive dependency. Scientific wheels can include
additional components: the inspected scipy wheels include OpenBLAS, LAPACK and
the GCC runtime with its Runtime Library Exception. Read the notices accompanying
the wheels you redistribute. FlightStream remains separately licensed and is not
included with pyflightstream.
