## Fixed

- `solver_settings` resolves `valarezo_criterion`, `wake_relaxation`, `wake_streamwise_agglomeration`, `adverse_gradient_boundary_layer` and `vortex_ring_normalization` as it resolves its other toggles, so a value of DISABLE emits DISABLE where 0.33.0 emitted ENABLE, a value in neither vocabulary is refused before anything is emitted, and the setup snapshot records a boolean instead of the string (FR-349).

## Migration

- A row that asked DISABLE (the word, or false) for one of the five toggles above now gets DISABLE in its script; 0.33.0 wrote ENABLE and its setup record held the word. A row that asked ENABLE, or none, renders as before, and no recorded campaign or golden render asked any of the five. To keep the old behaviour of a row, ask ENABLE (FR-349).
