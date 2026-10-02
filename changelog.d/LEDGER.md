## Added

- `pyfs-matrix status` (FR-379 to FR-385): one row per polar with the simulation, the polar, the swept variable, the datapoints (recorded/planned), the matrix and the status, one word when every datapoint shares it and otherwise the count of each word; `--sims` (with or without brackets), `--matrix`, `--status WORD` (repeatable, a trailing `*`), `--failed`, `--points` (one row per datapoint), `--json` (schema `pyfs-status/1`) and `--csv` (LF line ends), `--workspace`, `--runs`. A point a plan names and no record carries is shown as `planned`, in lower case; a footer states whether each matrix's plan was made from the matrix on disk and whether its post indexes every recorded run and is complete. The command writes no file, takes no lock and expands no compacted simulation.
- `pyflightstream.workspace.ledger` (FR-388): `read_ledger(root, runs=None)` returns one read-only snapshot whose `status()`, `points()`, `card(run_id)`, `freshness()` and `sim_folders(sim_id)` return the rows the command prints, as plain dictionaries.

## Changed

- The rules that choose the effective record of a datapoint (a refused continuation that never started is a note; the latest record of a point is found by its name) moved from the run layer to the workspace layer (FR-381), where the run and the ledger both read them; no behaviour changes.
