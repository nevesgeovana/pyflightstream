# Run and collection review fixes

- migration: Marking a whole steady simulation after marking one point now marks every remaining point and preserves the earlier point's reason.
- migration: Collecting selected simulations from an ended batch moves only those simulations. A later collection also moves completed simulations left in the batch after its last point finished.
- migration: An additional extraction already submitted is reported as SKIPPED with reason EXTRACTION_SUBMITTED and is excluded from the returned launched records. Collect it before requesting another extraction.
- migration: Failure to remove a completed local extraction's private copy is recorded as a note on the EXTRACTED result.
- migration: Invalid attribute and index access in scheduler submit placeholders returns a failed execution result before writing the descriptor, allowing other points to proceed.

The CLI scheduler regression now exercises the scheduler on Windows and isolates its selected profile. The mark-failed mutation test follows the per-point implementation. Command parsing, record marking, renaming and sweep collection retain their behavior while shared steps are factored into helpers to satisfy source limits.
