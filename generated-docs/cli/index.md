# Command-line tools

Every tool the package installs, with every subcommand and every option, generated from the argument parsers at build time. The workspace route through these tools is taught in [Getting started](../getting-started.md) and [The workspace and the workflow](../workspace-and-workflows.md).

| Tool | Entry point | What it does |
|---|---|---|
| [`pyfs-qa`](pyfs-qa.md) | `pyflightstream.qa.cli:main` | Tier 2 and 3 evidence tooling for the pyflightstream command database; probes run FlightStream locally and need a licensed machine. |
| [`pyfs-fsi`](pyfs-fsi.md) | `pyflightstream.fsi.cli:main` | FSI coupling executable for the FlightStream Aeroelastic Toolbox. Called with no arguments it executes one coupling step in the current directory (coupled with config.json, dummy only when configured). |
| [`pyfs-workspace`](pyfs-workspace.md) | `pyflightstream.workspace.cli:main` | Managed campaign workspace tooling; the tree it creates is owned by pyflightstream and never hand-built. |
| [`pyfs-matrix`](pyfs-matrix.md) | `pyflightstream.run.cli:main` | Run-matrix tooling: the matrix is a first-class interface of the file-managed modality, with campaign.toml as the canonical internal form. |
| [`pyfs-manual`](pyfs-manual.md) | `pyflightstream.utils.cli:main` | Read a FlightStream manual and compare it against the command database. The manual is licensed vendor material: pass its path explicitly, it is never guessed, and nothing from it is copied into anything this writes. |
| [`python -m pyflightstream.workspace.excel`](excel.md) | `pyflightstream.workspace.excel:main` | Create the optional workbook without launching Excel or changing trust settings. |
| [`python -m pyflightstream.workspace.excel_bridge`](excel-bridge.md) | `pyflightstream.workspace.excel_bridge:main` | A text bridge for the embedded workbook controls; Excel remains the cell writer. |
