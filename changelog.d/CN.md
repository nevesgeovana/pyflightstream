### Added

- CCS mesh probes capture each loft immediately and judge normalized geometry against reference and unchanged control states, clearing every surface produced by each loft (FR-401).
- Wing refinement probes derive an interior span interval from their synthetic loft; relaxed trailing-edge deletion probes compare saved mesh state and report prelude failures explicitly. Licensed re-probing is still required before command verdicts change (FR-401).
