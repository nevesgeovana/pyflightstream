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

Run `pyfs-matrix --version` to check the command is available. Use
`pyfs-matrix --help` to inspect the installed options before preparing a run.
