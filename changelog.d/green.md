### Fixed

- Complete the boundary-marking exception catalog and public API documentation.
- Keep marking helpers in their owning private modules and write probe text through
  the common LF writer.
- Update runnable examples for prepared simulations and marking previews. Offline
  inventory fixtures must be replaced with prepared simulations before licensed runs.

Migration: the examples follow the existing prepare, mark, then run workflow;
no additional matrix route or solver behavior is introduced.
