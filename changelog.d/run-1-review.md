## Migration

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
