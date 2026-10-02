### Added

- `pyfs-matrix history` reads present records, archived manifests and datapoint
  archives with source paths, archive stamps and continuation links (FR-390).
- `pyfs-matrix diff` compares recorded run fields and digest-verified scripts,
  with archive selectors and rebuild's line and input attribution (FR-391).
- Plain JSON-serializable query functions in `pyflightstream.workspace.ledger`
  expose the same rows as the command renderers (FR-388).
- History and diff find simulations in running batch folders and after collection,
  and inspect compacted archives without expanding them (FR-372, FR-383).
- The Python additional-register reader preserves recorded fields exactly while
  historical queries leave that register unchanged (FR-393).
