## Fixed

- Collected points retain the solver version and build read by the same assessor as a point run alone (FR-366; compared on 26.124, RPT-148).
- Restated steady and unsteady points reuse existing sections across `REMOVE_INITIALIZATION`; a point opened by `NEW_SIMULATION` creates its sections (FR-362, FR-403; compared on 26.124, RPT-148).
- Each acoustic polar runs in its own job, keeping all its points together (FR-406).
