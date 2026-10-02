### Added

- `pyfs-matrix show` prints outcome-first point cards by run id, alias or simulation and point, including evidence, logs, continuation chain, identities and inputs (FR-386).
- Coupled point cards name their FSI records, missing coupling files and last exchange row (FR-394).
- `pyfs-matrix log` reads filtered activity and unfinished stages, and `--post MATRIX` shares category, family and message grouping with `--pproc-warnings` (FR-387).
- `log --storage` reads storage calls as recorded, with meaningful activity filters (FR-392).
- `status --additional` lists the additional register without deriving fields (FR-393).
- `pyfs-matrix trace` follows indexed products to effective run identities, sidecars and provenance documents; `--run` prints a provenance tree (FR-389).
- Query tests cover status, show, log and trace while a simulation lives in a running batch and after it moves home, and prove ZIP evidence is read without extraction or workspace writes (FR-372, FR-383).
