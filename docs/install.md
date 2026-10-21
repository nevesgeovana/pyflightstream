# Install pyflightstream

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

## Choose the FlightStream build

Use [Which build do I have](builds.md) to map the solver build to the package
version identifier. Install does not install or license FlightStream.

## Check the installation

Run `pyfs-matrix --help` to check the command is available; it exits 0 and
lists the installed subcommands. Use `pyfs-matrix <subcommand> --help` to
inspect the options of one before preparing a run.

## Dependency licenses

The package uses these third-party libraries. The versions below identify the
distributions inspected for the license summary, rather than installation pins.
The installed distributions supply their own copyright notices and license texts;
preserve those notices when redistributing them.

| Library | Version inspected | License recorded |
|---|---|---|
| numpy | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pandas | 3.0.3 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| PyYAML | 6.0.3 | MIT |
| xarray | 2026.7.0 | Apache-2.0 |
| trimesh | 4.12.2 and 5.0.0 | MIT |
| PyNiteFEA (`fsi`) | 3.0.0 | MIT |
| scipy (`geom`) | 1.18.0 | BSD-3-Clause |
| rtree (`geom`) | 1.4.1 | MIT |
| matplotlib (`plot`) | 3.11.1 | Matplotlib License, derived from the PSF license |
| pypdf (`manual`) | 6.14.2 | BSD-3-Clause |
| XlsxWriter (`excel`) | 3.2.9 | BSD-2-Clause |

This summary describes the inspected versions. It does not establish the licenses
of future releases or every transitive dependency. Scientific wheels can include
additional components: the inspected scipy wheels include OpenBLAS, LAPACK and
the GCC runtime with its Runtime Library Exception. Read the notices accompanying
the wheels you redistribute. FlightStream remains separately licensed and is not
included with pyflightstream.
