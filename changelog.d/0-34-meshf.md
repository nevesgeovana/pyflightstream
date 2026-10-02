## Added

- The boundary inventory states the face count of its geometry when it is taken: `pyfs-matrix inventory <geometry>`, and the plan for an OBJ that has no inventory, write `mesh_faces` into `<stem>.boundaries.toml`, with `boundary_faces`, the count of each boundary in the order of `boundaries`, where the reader gives it (a saved simulation whose faces are all triangles and whose block names each face's boundary, and an OBJ, one count per group that holds a face), and `mesh_sha256`, the sha256 of the file counted. A count that cannot be taken is not written, and the inventory is then written as before. The input glossary states the three keys, and the input template's example of a saved simulation's inventory shows them (FR-348).
- `MESH_FACES`, the last column of every super file and of every unsteady polar (`polars/P<sim>_<name>_uns_avg.csv`): the face count of the geometry each row's run opened, taken from its inventory only where the inventory states it with the sha256 that run recorded for the file, `NA` otherwise. The post never counts a face; the definitions page states the column (FR-348).

## Changed

- `scripts/check_parity.py` names the new last column of the super files and the unsteady polars under FR-348 only where the release file is the 0.33.1 file with that one column appended and each of its cells `NA` or a whole number, and the products snapshot compares those two products with the column taken off and refuses one without it (FR-348).

## Migration

- **The super file and the unsteady polar gain a last column, `MESH_FACES` (FR-348).** Every column 0.33.1 wrote keeps its name, its place and its cells, so a reader by position or by name reads them as before; a reader that counts the columns, or that takes the last one as the last column of 0.33.1, finds one more. The column holds `NA` until the geometry's inventory states its face count: for a saved simulation, take the inventory again with `pyfs-matrix inventory <geometry> --overwrite` and post again; an OBJ's inventory is never rewritten by the package, so move it aside, take the inventory again and copy its tables beneath the new list. A count is carried only for runs that recorded the sha256 of the very file the inventory counted.
