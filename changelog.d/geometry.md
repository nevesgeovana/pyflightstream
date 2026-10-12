## Added
- The geometry stage: `pyfs-workspace geometry build` reads `<name>.geometry.toml` (one source table, `[ccs]`, `[cad]`, `[create]` or `[mesh]`, then `[[operations]]` and `[trailing_edges]`), previews the build without running anything, and with `--apply` runs the solver once with no solve, reads the saved body back against the stated boundaries, audits it, and writes a ParaView preview and a `<name>.build.json` record (FR-470, FR-471).
- A control-surface deflection sweep builds one sibling geometry per angle, `<name>_<SURFACE><sign><tenths>` (FR-472).
- `pyfs-workspace geometry accept` records the inspection of a built body; `pyfs-matrix plan` refuses a row whose body is stale against its instruction and warns on a resaved, unaccepted, audit-failed or other-build body (FR-473).
- Mesh operations in the instruction file: circular and linear copies, a cut by a plane, hole filling, degenerate-face removal, face extraction and deletion by threshold, and node moves pinned to the mesh's sha256 (FR-474).
- CAD body operations before the conversion of an IGES file, and bodies and section-lofted wings built by the solver's CAD Create commands (FR-475).
- `pyfs-workspace geometry from-sidecar` writes the instruction of a geometry a matrix row builds today (FR-476).
- `pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate`, the homes of the `pyfs-matrix` verbs of the same results (FR-477).

## Changed
- A row naming a CCS, IGES or STL file, or a sidecar whose import operations scale, rename or mirror, is warned at plan with its replacement; it still runs as before, and 0.41.0 refuses it (FR-476).
- `pyfs-matrix refine`, `audit-mesh`, `inventory` and `degenerate` warn that `pyfs-workspace geometry` is their home; their results are unchanged (FR-477).

## Migration
- The in-row geometry routes (a CCS, IGES or STL file in the `GEOMETRY` cell, and the sidecar operations `scale`, `rename` and `mirror`) warn in 0.40.0 and are refused in 0.41.0: write the instruction with `pyfs-workspace geometry from-sidecar <file> --apply`, build it with `pyfs-workspace geometry build <folder> --apply`, and name the built `.fsm` (or `.obj`) in the `GEOMETRY` cell. Translate and rotate stay in the run.
- The row key `CCS_SHEDDING` moves to `shedding` in the `[ccs]` table of the instruction file. A row that names the built body instead of the CCS, IGES or STL file opens it rather than making it, so its script and its input set change and its points run again; recorded points are never rewritten.
- `pyfs-matrix refine`, `audit-mesh`, `inventory` and `degenerate` give the same results and warn that `pyfs-workspace geometry refine`, `audit`, `inventory` and `degenerate` are their home.
