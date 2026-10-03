### Added

- Collected points retain the solver version and build read by the same assessor as a point run alone (FR-366).
- Restated steady and unsteady points reuse existing sections across `REMOVE_INITIALIZATION`; a point opened by `NEW_SIMULATION` creates its sections (FR-362, FR-403).
- Each acoustic polar runs in its own job, keeping all its points together (FR-406).
