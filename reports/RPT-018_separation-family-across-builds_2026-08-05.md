# RPT-018: the flow-separation family across four builds, and a delete command the manual names wrong

Date: 2026-08-05. Licensed machine, FlightStream 26.100 (build #2122026),
26.101 (build #5012026) and 26.121 (build #7262026). Synthetic geometry only:
a generated NACA 0012 half-wing from `pyflightstream.qa.geometry`. No research
geometry involved.

Run before entering the flow-separation family into the command database,
because the February manual (SRC-741 p.339) documents that family under two
different names in one block and reading cannot decide which the solver
expects. The answer turned out to be neither of the two readings, and the run
also settled what happened to the family in the later builds.

## 1. Method

Identical script per case, differing in one line: `NEW_SIMULATION`, `IMPORT` of
the same STL, `AUTO_DETECT_TRAILING_EDGES`, the line under test,
`CLOSE_FLIGHTSTREAM`. The line under test is written directly rather than
emitted, because the commands are not in the database yet, which is the whole
reason for the run.

Acceptance is read as RPT-012 and RPT-015 read it: the hidden-mode
`FlightStreamLog.txt` is written on a script error and absent on a clean run.

Each of the three batches carries two controls, and both are load-bearing. A
control that must be REJECTED (`CREATE_NOT_A_COMMAND_AT_ALL`) means a batch in
which nothing was rejected cannot read as everything being accepted; a control
that must be ACCEPTED (`SET_VISCOUS_EXCLUDED_BOUNDARIES`, in the database and
documented in all four editions) means the converse. Both behaved as required
in all three batches.

45 runs. The full result set, per case, is the run record described in section
6.

## 2. What the manual says, and why it cannot be read

SRC-741 p.339 documents the Valarezo criterion boundary list in one block whose
three parts do not agree with each other:

* the function header of the setter spells it `SET_VALAREZO_SEPARATION_BOUNDARIES`;
* the sample beneath that header spells it `SET_VALAREZO_CRITERION_BOUNDARIES`;
* the function header of the matching delete spells it
  `DELETE_VALAREZO_CRITERION_BOUNDARIES`.

Two spellings, and the manual uses each of them as a header, so the RPT-012
precedent (header wins over sample, because the sample had a one-letter typo)
does not resolve it.

## 3. Results

### 3.1 The Valarezo pair, on 26.100

| Line under test | Documented as | Outcome |
|---|---|---|
| `SET_VALAREZO_SEPARATION_BOUNDARIES -1` | function header | **accepted** |
| `SET_VALAREZO_CRITERION_BOUNDARIES -1` | sample | rejected, unrecognized |
| `DELETE_VALAREZO_CRITERION_BOUNDARIES` | function header | rejected, unrecognized |
| `DELETE_VALAREZO_SEPARATION_BOUNDARIES` | nowhere | **accepted** |

So the family is spelled `SEPARATION` throughout, and the manual is wrong
twice: once in a sample, which is the RPT-012 pattern, and once in a function
header, which is not. **The delete command the manual documents does not
exist, and the delete command that exists is documented nowhere.**

### 3.2 The rest of the February family, on 26.100

Accepted: `SET_AXIAL_SEPARATION_BOUNDARIES` in both the `-1` form and the
count-plus-index-line form, `DELETE_AXIAL_SEPARATION_BOUNDARIES`,
`SET_CROSSFLOW_SEPARATION_BOUNDARIES` in both forms,
`DELETE_CROSSFLOW_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_DIAMETER`,
`SET_CROSSFLOW_SEPARATION_AXISYMMETRIC`, `DELETE_VISCOUS_EXCLUDED_BOUNDARIES`,
`LAMINAR_SEPARATION`.

Rejected as unrecognized: the whole May family, that is
`CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION` and
`DELETE_SEPARATION`. The February build knows none of them.

### 3.3 The February family on the later builds, and the third verdict

The February commands are neither accepted nor unrecognized on 26.101 and
26.121. The solver recognizes each of them, writes a deprecation warning
naming the command, and then fails the script:

> WARNING, Deprecation, `SET_AXIAL_SEPARATION_BOUNDARIES`, command is
> deprecated, replacement none, update the script to use the replacement
> command.

Paraphrased; the replacement field is literally empty in the message, so the
solver announces a replacement it does not name. Measured for
`SET_AXIAL_SEPARATION_BOUNDARIES`, `SET_VALAREZO_SEPARATION_BOUNDARIES`,
`SET_CROSSFLOW_SEPARATION_BOUNDARIES`, `SET_CROSSFLOW_SEPARATION_DIAMETER` and
`SET_CROSSFLOW_SEPARATION_AXISYMMETRIC` on 26.101, and for the first three on
26.121.

`SET_VALAREZO_CRITERION_BOUNDARIES` is unrecognized on the later builds too,
which is the fourth independent statement that this name has never existed.

### 3.4 The May family, and the two commands that outlived both

`CREATE_AIRFOIL_SEPARATION` (both forms), `CREATE_AXIAL_VORTEX_SEPARATION` and
`DELETE_SEPARATION` are accepted on 26.101 and on 26.121.

`DELETE_VISCOUS_EXCLUDED_BOUNDARIES` and `LAMINAR_SEPARATION` are accepted on
all three probed builds. Both are documented in all four editions and neither
was in the database.

## 4. What this establishes

**The database can now record the February family under names the solver
answers to**, which is what the run was for.

**The three verdicts are the solver's own, not this repository's reading.**
Unrecognized, deprecated-and-refused, and accepted are distinguished by the
solver's message category, so "the command is gone" and "the command was never
there" are different findings here rather than the same silence. The
distinction matters for the database: a command the solver still knows and
refuses is a removal the vendor made deliberately, while an unrecognized name
in a manual is a documentation defect.

**The February family did not survive undocumented.** This is the opposite of
what RPT-015 found for `CREATE_STRATFORD_BULK_SEPARATION`, which the 26.120
solver accepted although no manual of that build documents it. Absence from a
manual is therefore not evidence in either direction, and each case has to be
probed.

## 5. What this does NOT establish, stated so the table is not over-read

* **Acceptance is not effect.** As in RPT-012 and RPT-015, a clean run shows
  the parser took the line. It does not show the separation model was applied
  to the boundaries, and none of these commands prints anything on success:
  stdout for the accepted cases carries no warning, no deprecation notice and
  no error, and is otherwise indistinguishable from the same script without
  the line. An effect-asserting probe needs an instrument that exposes the
  separation assignment, which is the work registered as
  `PLN-20260805-1520-separation-probe-specs`.
* **This report promotes no status.** It is an ad-hoc probe, not a run of the
  Tier 2 harness, so under CLAUDE.md invariant 3 it cites no database status
  and every entry it supports stays `documented`. The same rule applied to
  RPT-015.
* **The deprecation verdict was measured on two builds, not four.** 26.120 was
  not in this batch; its behavior is inferred from 26.101 and 26.121 bracketing
  it, which is an inference and is not recorded as evidence anywhere.
* **The count-plus-index-line form was probed for the axial and cross-flow
  setters only.** The Valarezo setter was probed in the `-1` form alone.
* **`SET_VISCOUS_EXCLUDED_BOUNDARIES` served as a control, not as a subject.**
  Its acceptance on three builds is a fact this run happens to carry, and it is
  used here only to show each batch could tell accepted from rejected.

## 6. Reproducing this

The run scripts are generated, not committed: one directory per case under a
scratch root, each holding `case.txt`, the solver stdout, and
`FlightStreamLog.txt` where one was written. The three executables are the
licensed installs under `_private/exe/`, which never enter Git. Regenerating
the batch needs the licensed machine; the method is fully described in
section 1 and is three lines of setup plus the line under test.

Both installs used here check out an EDU feature set rather than full Altair
units, which is stated because a licence tier can in principle change what a
command is permitted to do. It does not change what the parser recognizes,
which is all this report measures.
