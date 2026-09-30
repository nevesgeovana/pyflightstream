## Fixed

- The noise products are reachable: the post finds the acoustic export among the outputs of the point's record, the entry ending `_acoustic_signals.txt`, instead of a record field that does not exist, so an `unsteady_rotor` point that declares observers now writes its `acoustics/` products (FR-290).
- `pyfs-matrix restore` has copies to bring back for `storage`, `additional`, `plan` and `products`: their writers now copy the previous file into the archive form `restore` reads before rewriting it, and a failed copy warns and never blocks the write (FR-291, FR-292, FR-293, FR-294).

## Changed

- `products.json` is archived to `post/<matrix>/archive/<stamp>/products.json` when a post rebuilds, where it was removed before (FR-293).
- The archive names are spelled once, in `pyflightstream.workspace.naming` (`archive_previous`, `free_root_archive`, `free_matrix_archive`), which `restore` also uses (FR-294).

## Migration

- `products.json` is now archived rather than removed when a post rebuilds; `storage_management.json`, `additional.json` and `plan.json` are archived on every rewrite, so `archive/` and `post/<matrix>/archive/` grow by one small copy per write (FR-291, FR-292, FR-293).
