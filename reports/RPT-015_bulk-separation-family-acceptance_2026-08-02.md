# RPT-015: the bulk-separation family is not a rename, and the old command is broken

> **Version identifier renumbered, 2026-08-04.** This run is recorded here
> under **26.101**. It was made and first recorded as 26.100, the name this
> repository then gave vendor build 5012026. On 2026-08-04 the author added
> the earlier February 2026 build, which takes the earlier index 26.100 under
> the append-only ordering rule, so this build was appended as 26.101. The
> build number, the executable, the date and every measurement below are
> unchanged: only the label pointing at them moved. The report id keeps its
> original form because it is cited elsewhere.

Date: 2026-08-02. Licensed machine, FlightStream 26.120 (build #7012026) and
26.121 (build #7262026). Synthetic geometry only: a generated NACA 0012
half-wing from `pyflightstream.qa.geometry`. No research geometry involved.

Run to answer the one item of RPT-014's rename checklist that is a physics
question rather than a naming one, on the author's instruction to prove it by
probe rather than decide it by reading. The answer is that the question was
posed on a false premise, and the checklist item is withdrawn rather than
answered.

## 1. Method

Identical script per case, differing in one line: `NEW_SIMULATION`, `IMPORT` of
the same STL, `AUTO_DETECT_TRAILING_EDGES`, the separation line under test,
`CLOSE_FLIGHTSTREAM`. The separation line is emitted through `raw()`, because
the 26.121 spellings are deliberately not yet in the database.

Acceptance is read as RPT-012 read it: the hidden-mode `FlightStreamLog.txt`
is written with the offending line on a script error and absent on a clean run.

A control that must be REJECTED ran in the same batch
(`CREATE_NOT_A_COMMAND_AT_ALL`), so a batch in which nothing was rejected could
not read as everything being accepted. It was rejected, with a distinct
message.

## 2. Results

| # | Build | Line under test | Outcome |
|---|---|---|---|
| 1 | 26.120 | `CREATE_BULK_SEPARATION` name FLAT_PLATE -1 diameter | rejected |
| 2 | 26.120 | `CREATE_BULK_SEPARATION` name FLAT_PLATE 1 diameter, index line | rejected |
| 3 | 26.120 | `CREATE_BULK_SEPARATION` name -1 diameter (the 26.1 three-argument form) | rejected |
| 4 | 26.120 | `CREATE_BULK_SEPARATION` name CYLINDRICAL -1 diameter | rejected |
| 5 | 26.120 | `CREATE_STRATFORD_BULK_SEPARATION` name -1 | **accepted** |
| 6 | 26.121 | `CREATE_BULK_SEPARATION` name FLAT_PLATE -1 diameter | rejected |
| 7 | 26.121 | `CREATE_STRATFORD_BULK_SEPARATION` name -1 | **accepted** |
| 8 | 26.121 | `CREATE_STRATFORD_BULK_SEPARATION` name 1, index line | **accepted** |
| 9 | 26.121 | `CREATE_CYLINDRICAL_BULK_SEPARATION` name -1 diameter | **accepted** |
| 10 | 26.121 | `CREATE_NOT_A_COMMAND_AT_ALL` (control) | rejected |

## 3. What this establishes

**`CREATE_STRATFORD_BULK_SEPARATION` is not new in 26.121.** It is accepted by
the 26.120 solver as well, on the same geometry and the same script, where no
manual documents it. The 26.121 edition documented a command that already
existed. So the premise of the rename question, that a new command appeared
alongside an old one vanishing, does not hold: nothing appeared.

**`CREATE_BULK_SEPARATION` does not work on 26.120 either.** Every documented
form was refused on the build whose own manual (SRC-003 p.342) documents it:
the four-argument form with all boundaries, the same with an explicit count and
index line, the three-argument 26.1 form that RPT-012 ran successfully on
26.101, and the CYLINDRICAL separation type. The command database records it
`documented` for 26.120, and that status is now contradicted by evidence.

This is a manual-versus-reality discrepancy of the "documented but broken"
kind, and it is older than the hotfix: it is a 26.120 defect that the 26.121
manual then papered over by dropping the command.

**So the checklist item is withdrawn, not answered.** There is no rename to
record. `CREATE_BULK_SEPARATION` is broken on 26.120 and 26.121; the Stratford
and cylindrical commands exist on both builds; and whether Stratford implements
the physics the old `FLAT_PLATE` argument selected is a question about a
command that never worked here, which makes it a question about the manual
rather than about a migration path for a user.

## 4. What this does NOT establish, stated so the table is not over-read

* **Acceptance is not effect.** As in RPT-012, a clean run shows the parser
  took the line, not that the separation model was applied to the boundaries.
  No effect assertion was made, and none of these statuses may be promoted to
  `verified` on this evidence.
* **The two refusal messages are not a reliable discriminator.** The solver
  distinguishes "Unrecognized command" from "Review command syntax and
  arguments", and `CREATE_BULK_SEPARATION` drew the second. That reads as "the
  command is known and the arguments are wrong", but the same message came back
  for a deliberately lower-cased token, so the message cannot separate an
  unknown command from a known one with bad arguments. The report therefore
  says "rejected" throughout and claims nothing about why.
* **Extra arguments are tolerated.** `CREATE_STRATFORD_BULK_SEPARATION` was
  accepted with a trailing diameter argument the manual does not give it, so
  acceptance does not confirm the documented arity either.
* **No status is promoted by this report.** It was produced by an ad-hoc probe
  script, not by the `pyfs-qa probe` harness, so it carries no
  `pyflightstream-compat-report` document and `apply-compat` cannot read it.
  Recording `broken` needs a harness spec and a run; that is registered rather
  than done here, because a status promoted outside the sanctioned write path
  is exactly what invariant 3 forbids.
