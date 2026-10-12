## Fixed

- Correct indexed mesh boundary lookup, station roundoff handling, odd-grid harmonic coverage, phase origins, and right-handed in-plane moments.
- Preserve requested post-processing diagnostics in quiet mode and require meaningful scales for aerodynamic counts.
- Preserve manual chapter bytes during version insertion and recover registration writes without overwriting unrelated temporary files.
- Require complete probe execution evidence, correct surface-section export filenames, and use the configured probe timeout in the Python API.
- Tighten release fragment folding, directed parity exceptions, mutation verdicts, and temporary mutation byte restoration.

## Migration

- Invalid expression arity and non-real powers now raise named errors; non-finite seconds and invalid harmonic cutoffs are refused.
- Indexed boundary tokens match case-insensitively but never expand silently to a family. Use the bare family name to select all members.
- Harmonic reductions include the highest supported order on odd grids and account for the grid phase origin. Z-axis moments now follow the right-handed cross product; previously computed values change sign.
- `to_counts` and `spurious_diagnostic` require explicit `s_ref`. Density, freestream speed, and area must be finite and positive; hover has no freestream-based count normalization.
- `post --diagnostics` writes its requested data in quiet mode. Axial station requests tolerate floating-point roundoff but refuse absent stations by name.
- `qa.probe_timeout_s` supplies the Python probe API default. The unused `qa.case_timeout_s` option is removed. Missing probe END sentinels cannot establish verification.
- `EXPORT_SURFACE_SECTIONS` requires an index and a filename on the following line. Its unsupported 26.125 verified status is withdrawn to documented pending a new complete probe.
- Registration refuses missing manual paths, non-string build labels, and null sources before writing. Version insertion preserves final terminators. Draft rendering honors phase, parameter-prefix, quoted enum, and probe-reference metadata.
- Removed commands identify the earliest later build where available. Changelog folding requires an explicit migration page, including its Python API; SRS and changelog folding compare whole entries and reject conflicting duplicates.
- Parity exceptions are limited by release and their stated change direction. Empty change blocks no longer pass by vacuous matching. Published-release checks use the newest release tag.
- Maintainer scripts now refuse empty manual conversion, malformed total-load exports, inconsistent type-check counts, and inconclusive mutation runs. Equal-date evidence is refused when ambiguous; root-relative exclusions and generated-script imports are resolved consistently.
- The unused impersonal sweep script is removed. Note restating refuses absent commands and already-first labels; the commit-message scissors boundary is honored.
