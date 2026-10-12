## Fixed

- Surface parsing reports out-of-range VTK polygon integers as malformed
  output, so translation records the problem instead of aborting with an
  uncatalogued overflow.
- Reusing a surface translation without a native source verifies its data
  against a fresh translation as well as checking its source and frame.

## Migration

- Out-of-range VTK polygon integers raise `MalformedOutputError` instead of
  `OverflowError`.
- Existing surface translations with matching provenance headers but changed
  or truncated data are preserved and reported as problems. They are no longer
  recorded as successfully written.
