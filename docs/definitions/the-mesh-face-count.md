<a id="the-mesh-face-count-since-0340"></a>

## The mesh face count

- **`MESH_FACES` is the last column of every super file and of every unsteady
  polar** (`polars/P<sim>_<name>_uns_avg.csv`), after every column 0.33 wrote,
  so a reader that takes those columns by position keeps each of them. It holds
  the face count of the geometry the row's run opened.
- **It comes from the boundary inventory, and the post never counts a face.**
  `pyfs-matrix inventory <geometry>`, and the plan for an OBJ that has no
  inventory, write into `<stem>.boundaries.toml`, when they take the inventory,
  `mesh_faces`, the face count of a saved simulation's mesh block or of an OBJ;
  `boundary_faces`, the count of each boundary in the order of `boundaries`,
  where the reader gives it (a saved simulation whose faces are all triangles
  and whose block names each face's boundary, and an OBJ, one count per group
  that holds a face); and `mesh_sha256`, the sha256 of the file counted.
- **A row carries the count whenever the inventory states it for that row's
  geometry**, the library's inventory read first and then the simulation's
  staged copy. Otherwise the cell is `NA`: a row whose point has no run record,
  and an inventory without `mesh_faces`.
- **Where the inventory's `mesh_sha256` is not the sha256 the run recorded** for
  the file, because the geometry was replaced, edited or cleaned (`--clean`)
  between the inventory and the run, the count is still carried and `post.log`
  warns, naming the inventory, both sha256 and the run. The warning never
  blocks the post; take the inventory again if the geometry changed.
- **Taking the count again.** For a saved simulation, `pyfs-matrix inventory
  <geometry> --overwrite` rewrites its inventory with the count. The package
  never rewrites an OBJ's inventory, because it may carry tables written by
  hand: move it aside, take the inventory again, and copy those tables beneath
  the new list.

---
