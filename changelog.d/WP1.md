## Changed

- The layer table has seven pipeline rows: `run` is a row of its own above `workspace` (AD-09, P0330-WP1). The architecture chapter of the SRS, the user guide's diagram and the generated architecture page state the same rows, and no module of `workspace` imports `run`, at module level, inside a function or under `TYPE_CHECKING`.
- `resolve_manifest`, `RunsManifestError` and `DEFAULT_MANIFEST` are defined in `pyflightstream.workspace.naming` (AD-09). They still import from `pyflightstream.run.records` and `pyflightstream.exceptions`, as the same objects.
- A restoring sync (`sync --restore --apply`, library `restore=True`) reaches the records rebuild through a registry of `pyflightstream.workspace.storage` that `pyflightstream.run.records` fills when it loads; `import pyflightstream` loads it. What the sync does and records is unchanged (FR-221).
