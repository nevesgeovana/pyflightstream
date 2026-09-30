## Changed

- Every constant 0.32.0 defined in two modules has one home, and the other module imports it from there (AD-10, P0330-WP2): the archive stamp pattern beside its spelling in `pyflightstream.workspace.naming` (`ARCHIVE_STAMP_PATTERN`), the length unit that names no length in `pyflightstream._lengths` (`UNIT_THAT_NAMES_NO_LENGTH`), the coupling's loads export and displacement file names in `pyflightstream.fsi.state`, and three solver command names, public in their one home: `LENGTH_UNIT_COMMAND` in `pyflightstream.script` (also still in `pyflightstream.workspace.wake_edges`), `WAKE_STABILIZATION_COMMAND` in `pyflightstream.script.helpers` and `SECTION_DISTRIBUTION_COMMAND` in `pyflightstream.cases.workflows`. Every public name keeps importing from where it did.
- `parse_sectional_loads`, `SectionalLoadsReport`, `SectionBlock`, `UnitsError` and `EXPECTED_COLUMNS` are defined in the new module `pyflightstream.results.sectional_loads` (AD-10, decision 15); `pyflightstream.fsi.loads` re-exports every one of them, and `FsiInputError` is defined in the package floor and re-exported by `pyflightstream.fsi.errors`. The results row imports nothing of `fsi`, which removes the import cycle between `fsi.loads` and `results.tables`.
- `read_csv_table` and `plots_table_series` are defined in `pyflightstream.post._tables` (AD-10); `pyflightstream.post.products` re-exports them with its `__all__` unchanged, and `post.corrections` no longer imports `post.products`.

## Removed

- `pyflightstream.cases.stamp_derived_campaign`, the writer of the `[campaign.derived_from]` marker, which no code called (decision 9 of the 0.33.0 scope, AD-10). `load_campaign` still reads the marker of a campaign file an earlier release stamped, and still refuses such a file once it is edited.
