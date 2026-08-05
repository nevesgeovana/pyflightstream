# RPT-012: CREATE versus CREARE bulk-separation spelling on 26.101 (PLN-015)

> **Version identifier renumbered, 2026-08-04.** This run is recorded here
> under **26.101**. It was made and first recorded as 26.100, the name this
> repository then gave vendor build 5012026. On 2026-08-04 the author added
> the earlier February 2026 build, which takes the earlier index 26.100 under
> the append-only ordering rule, so this build was appended as 26.101. The
> build number, the executable, the date and every measurement below are
> unchanged: only the label pointing at them moved. The report id keeps its
> original form because it is cited elsewhere.

Date: 2026-07-23. Licensed machine, FlightStream 26.101
(`FlightStream.exe`, solver build #5012026). Synthetic geometry only
(a generated NACA 0012 wing); no research geometry involved.

## Question

The 26.1 manual documents `CREATE_BULK_SEPARATION` in the function
header but spells the same command `CREARE_BULK_SEPARATION` in the
sample blocks (SRC-725 p.341). Which token does the 26.101 solver
accept? The question is unresolvable from the manuals alone (a
documentation typo and a parser token are independent facts), so it
needs a live run (PLN-015).

## Method

A controlled pair through the library's executor: an identical
model (NEW_SIMULATION, IMPORT of the wing STL, trailing-edge detect)
followed by the three-argument 26.101 form
`CREATE_BULK_SEPARATION sep1 -1 0.5`, run once with the header
spelling and once with only the command token changed to
`CREARE_BULK_SEPARATION`. Acceptance is read from the hidden-mode
`FlightStreamLog.txt` (written with the offending line on a script
error, absent on a clean run).

## Finding

* `CREATE_BULK_SEPARATION`: accepted. The script completed with no
  error log (return code 0, no `FlightStreamLog.txt`).
* `CREARE_BULK_SEPARATION`: rejected. The solver wrote
  `ERROR | Syntax | 'CREARE_BULK_SEPARATION sep1 -1 0.5' |
  Unrecognized command ... | Check command spelling and syntax.`

Conclusion: the sample-block spelling `CREARE` is a documentation
typo. The 26.101 solver accepts `CREATE_BULK_SEPARATION`, the
function-header spelling, which is the token the command database
already uses. No `CREARE` alias is warranted. The three-argument
26.101 form (name, num_boundaries, diameter; no SEPARATION_TYPE) is
accepted without the solver initialized.

Status note: this run confirms acceptance (the token is correct and
the command is not rejected), which is stronger than `documented` but
short of `verified`: an effect assertion (the separation model
actually applied to the boundaries) was not made, and the standard
compat harness cannot yet run on 26.101 (its PRINT sentinels and the
INITIALIZE_SOLVER prelude are not backfilled for that version, see
below). The database note is updated to cite this report; the formal
`verified` promotion waits on the 26.101 harness backfill.

## Side finding: INITIALIZE_SOLVER is version-sensitive (26.101 vs 26.120)

A first attempt placed the bulk-separation line after the 26.120
`INITIALIZE_SOLVER` multi-line form. On 26.101 the solver consumed the
following command line as an unexpected INITIALIZE_SOLVER argument
(`WARNING | Syntax | INITIALIZE_SOLVER | Unexpected argument
CREATE_BULK_SEPARATION ...`), meaning the 26.120 INITIALIZE_SOLVER
argument block does not parse identically on build 5012026. This
contradicts the "grammars identical" assumption of the 26.101 manual
backfill for this command specifically, and it blocks a standard
26.101 probe prelude. Establishing the correct 26.101 INITIALIZE_SOLVER
form (manual pass plus probe) is a prerequisite of any solver-tier
26.101 probing and is registered as a follow-up.
