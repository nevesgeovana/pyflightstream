# Upgrading

Read the migration records for the releases between your installed version and the version you are adopting. Each record states the changes a workspace needs.

## 0.40.0 run corrections

These corrections change observable behavior in existing run workflows:

- A known simulation id containing an underscore takes precedence over a point
  alias. For example, if both `2006` and `2006_1` exist, `2006_1` selects the
  simulation with that id.
- A grouped point that its job never started is recorded as `FAILED_EXECUTION`
  even when the job left a shared native log.
- A grouped retry preserves failed records when scheduling refuses queued work
  or an already recorded sibling. With `--resume`, successful siblings stay
  recorded while failed points run again.
- `--hpc` and `--cost-file` selections end with their CLI invocation. A later
  command in the same Python process no longer inherits those selections.
- `show SIM --point VALUE` errors name the simulation and requested point and
  list recorded points with their aliases, including for an invalid numeric index.
  Continuation refusals for changed `FREESTREAM_UNITS` also name the point, prior
  run and both declarations.
- `mark-converged` refuses malformed manifest records and unknown statuses with
  a manifest error before archiving or changing a verdict. Restore or correct
  the manifest before retrying.
- Submit-command validation includes placeholders inside format specifications.
  A formatting failure for a point is recorded as its script failure instead of
  escaping as a Python traceback. Invalid native-log placeholders, including
  attribute and index access, and unreadable grouping blocks also produce named
  refusals.
- A relative local script is inspected from the solver's working directory.
  An unchanged `FlightStreamLog.txt` left by an earlier attempt is no longer
  returned as the new execution's log.
- Reconstruction finds inherited probe layouts under the simulation's
  `profiles/` folder. Existing matching files are no longer reported as missing.
- A timeout while reading a splash window's control text does not make the
  splash an error dialog. Readable dialog text and buttons still identify dialogs.

## Earlier releases

- [Migrating to 0.39.0](migrating-to-0.39.0.md)
- [Migrating to 0.38.0](migrating-to-0.38.0.md)
- [Migrating to 0.37.0](migrating-to-0.37.0.md)
- [Migrating to 0.36.0](migrating-to-0.36.0.md)
- [Migrating to 0.35.1](migrating-to-0.35.1.md)
- [Migrating to 0.35.0](migrating-to-0.35.0.md)
- [Migrating to 0.34.0](migrating-to-0.34.0.md)
- [Migrating to 0.33.1](migrating-to-0.33.1.md)
- [Migrating to 0.33.0](migrating-to-0.33.0.md)
- [Migrating to 0.32.0](migrating-to-0.32.0.md)
- [Migrating to 0.31.0](migrating-to-0.31.0.md)
- [Migrating to 0.30.0](migrating-to-0.30.0.md)
- [Migrating to 0.29.0](migrating-to-0.29.0.md)
- [Migrating to 0.28.0](migrating-to-0.28.0.md)
- [Migrating to 0.27.0](migrating-to-0.27.0.md)
- [Migrating to 0.26.0](migrating-to-0.26.0.md)
- [Migrating to 0.25.0](migrating-to-0.25.0.md)
- [Migrating to 0.24.0](migrating-to-0.24.0.md)
- [Migrating to 0.23.0](migrating-to-0.23.0.md)
- [Migrating to 0.22.0](migrating-to-0.22.0.md)
- [Migrating to 0.21.0](migrating-to-0.21.0.md)
- [Migrating to 0.19.0](migrating-to-0.19.0.md)
- [Migrating to 0.18.0](migrating-to-0.18.0.md)
- [Migrating to 0.17.0](migrating-to-0.17.0.md)
- [Migrating to 0.16.0](migrating-to-0.16.0.md)
- [Migrating to 0.15.0](migrating-to-0.15.0.md)
- [Migrating to 0.14.0](migrating-to-0.14.0.md)
- [Migrating to 0.13.0](migrating-to-0.13.0.md)
- [Migrating to 0.11.0](migrating-to-0.11.0.md)
- [Migrating to 0.10.1](migrating-to-0.10.1.md)
- [Migrating to 0.10.0](migrating-to-0.10.0.md)
- [Migrating to 0.8.1](migrating-to-0.8.1.md)
- [Migrating to 0.5.0](migrating-to-0.5.0.md)

[Release notes](release-notes.md) carry the earlier release records.
