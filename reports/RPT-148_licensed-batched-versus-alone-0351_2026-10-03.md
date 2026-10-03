# RPT-148 - Licensed batched versus alone comparisons for 0.35.1 (2026-10-03)

FlightStream 26.124, build 8172026; local execution, far field 5, one solver at a
time. The run windows below are local time (UTC-03:00) on 2026-10-03. This report
transcribes retained logs, diagnoses and comparison receipts; it does not rerun
the solver. Cases are identified by role only. Private paths and case identifiers
in the quoted evidence are replaced by file names and bracketed roles.

## Purpose

Record what the licensed comparisons establish about each grouped point relative
to the same point run alone, including the defects that motivated section reuse
(FR-362), collected solver identity (FR-366), acoustic polar isolation (FR-406),
and the coupled log split correction (FR-407). Cover time averaging (FR-402),
steady jobs (FR-403), and user actions (FR-405) without treating every window as
an equality result.

## Method

The package planned, ran, collected and post-processed the same points in alone
and grouped arms. Comparisons covered declared outputs, per-step exports and
post products as applicable, with exact numeric comparison (zero tolerance).
File counts below are file-pair comparisons, not counts of independent trials.
The user-action count includes both grouped and polar-sweep comparisons against
alone. The acoustic count excludes repeated record checks and control comparisons.

Sources are `lv_run1.log`, the diagnoses `tavg.md`, `steady.md`, `user_actions.md`
and `acoustic_fsi.md`, `lv_run.log`, the receipts `tavg.json`, `steady.json`,
`user_actions.json` and `acoustic.json`, and `lv_fsi_run.log`. The rule-9 header
classification is stated in `HARNESS2.md`. These are retained external evidence;
no source file is copied into this repository.

Execution metadata is excluded from equality: `run_id`, solver initialization
seconds (`solver_initialization_s`), and the rule-9 columns whose headers contain
`wall`, `elapsed`, `run_time`, `runtime`, `solver_time`, `cpu`, `timestamp`, `date`,
`started`, `ended`, `route`, `mode`, `march_strategy`, `job`, `batch`, `path`, `dir`,
`folder`, `host`, `version` or `build`. Physical `time_s`, step, iteration,
revolution, azimuth, coefficients and other quantities remain compared. Text
output headers omit date/time of day, path and software version/build metadata.
This does not waive the separate requirement to retain solver identity in the
collected record. The window-2 log predates the additional exclusions of `run_id`
and `solver_initialization_s`; the final steady and user-action receipts record
the comparison after those metadata differences were excluded.

## Results

### Window 1: 01:10-01:28, defects and the time-average control

A second polar opened after an acoustic polar in the same solver instance ended
the process. The diagnosis `acoustic_fsi.md`, lines 115-118, records return code
3221225477 with `timed_out: false`. Its captured `activity.log`, line 11, reads
(three nonblank stdout lines flattened by the diagnosis):

> Simulation file opened from following location: / [second acoustic polar model file] / 24 base region faces marked on surface Base

The first polar's two points completed; neither point of the second polar had a
final export. The recorded progress stopped at point 2, step 45, job count 90 of
138 expected steps. The opening and base-detection messages precede termination;
the evidence does not identify the faulting command or prove a crash at
`NEW_SIMULATION` itself. Planning each acoustic polar as its own job, with all
its points, avoids this measured failing transition (FR-406).

Restated steady points recreated sections that survived `REMOVE_INITIALIZATION`.
The comparison log records the doubled section products (file names reduced to
their role; the second row concerns another steady-job polar):

> `lv_run1.log:175`: DIFFERS: [steady polar, second point]_sections.csv: 20 rows against 10
>
> `lv_run1.log:176`: DIFFERS: [another steady-job polar, second point]_sections.csv: 20 rows against 10

The diagnosis `steady.md`, lines 138-143, traces both restated blocks to repeated
section creation; fresh-model points retained the expected section count.
Reusing the sections on restatement fixes that observed duplication (FR-362).
The same diagnosis records missing `fs_version_reported` and `fs_build` in all
six grouped records even though their loads headers contained version 26.1 and
build 8172026. The collected records had omitted solver identity (FR-366).

The time-averaged unsteady comparison in this window was equal. In particular,
the grouped and alone surface results were byte-identical. `tavg.json` retains
this window as its equality evidence, not the later near-equal result.

### Window 2: 02:36-03:02, 0.35.1.dev1 at e26a39c0

| Kind | Points | Polars | Compared files | Verdict |
|---|---:|---:|---:|---|
| A time-averaged unsteady polar set | 4 | 2 | 216 | Not equal in window 2; window 1 equal |
| Steady and quasi-steady polars | 6 | 3 | 87 | Equal; zero differences in the final receipt |
| Unsteady polars with user actions | 5 | 3 | 92 | Equal; all checks hold in the final receipt |
| Acoustic polars | 4 | 2 | 104 | Equal; 4 of 4 identical |

The time-average count is 32 declared outputs, 180 per-step files and 4 averaged
products. One second point differed by at most `1.1e-19` at its last step, 45,
also in its final surface exports. The grouped job scripts in windows 1 and 2
were byte-identical. The receipt attributes this to grouped run-to-run noise;
the measured bound is not exact equality in window 2. The averaged products
themselves were byte-identical (`lv_run.log:725-734`), but the complete comparison
was `FR-402 VERIFICATION: NOT EQUAL` (`lv_run.log:735-736`, exit 1).

The steady count is 54 declared outputs and 33 post products. The user-action
count is 80 declared outputs and 12 polar products across the grouped and
polar-sweep arms, with no per-step files. The final receipts for steady, user
actions and acoustics each record equal coefficients and maximum absolute
difference zero. The original log's steady and user-action comparison exits
were 1 because it still compared `run_id` and `solver_initialization_s`; those
exits are not rewritten as successes here.

The coupled comparison exposed a collection defect: grouped records were
`COMPLETED_MAX_ITER` or `FAILED_INCOMPLETE_OUTPUT` where the alone records were
converged, despite equal solver outputs. Log splitting had cut at a setup reset
between initializations. Commit 2a848c3e corrects that split by retaining a reset
only when both the preceding solver-mode line and following symmetry line
identify initialization. This correction was included in the next window.

### Window 3: 03:28-03:37, 0.35.1.dev2 at ae2fec53: equal

The coupled set contained 5 points in 3 polars: 4 coupled-wing points and one
uncoupled control. Both execution arms exited 0 and ran at most one solver at a
time (`lv_fsi_run.log:7-19`). The comparison checked 16 files for each coupled
point and 10 for the control, 74 file pairs in total.

The first pass of the comparison reported the four coupled points DIFFERENT,
`FSI: 1 of 5 identical`, exit 1 (`lv_fsi_run.log:21-29, 521-529`): its CSV rule
refused each point's coupling convergence log because the file opens with comment
lines that are not CSV rows (row 1 had 1 cell where 2 were expected). Those four
logs are byte-identical between the grouped and the alone arm. The comparison was
corrected to treat byte-identical files as equal before parsing them, and re-run on
the same workspaces: every record is equal in status (CONVERGED), iteration count,
time steps and residual (`lv_fsi_compare2.log:256, 310, 364, 418, 464`), each
convergence log is byte-identical (`lv_fsi_compare2.log:232, 286, 340, 394`), and
the verdict is `FSI: 5 of 5 identical`, exit 0 (`lv_fsi_compare2.log:2-6, 494-500`).
The window-3 result is **equal**: grouped coupled points reproduce the points run
alone after the log-split correction of window 2.

## Addendum, release review of 2026-10-03: solver identity readback (FR-366)

Added after the first transcription, at the release review; the window 3 section
above was revised at the closing push review, after the comparison correction it
describes. After the FR-366 correction every grouped record checked carries the solver
identity, `fs_version_reported` 26.1 and `fs_build` 8172026, as its alone
counterpart does. Window 2: 29 of 29 grouped records, namely 4 time-averaged, 10
with user actions (5 in the batch arm, 5 in the polar-sweep arm), 6 steady, 4
acoustic and the 5 coupled records whose status window 3 corrected (the PROVENANCE
lines of `lv_run.log`, first at 110-111). Window 3: 5 of 5
(`lv_fsi_compare2.log:254-255` and the other PROVENANCE lines). The equality method
excludes version and build columns, so this readback, not the equality verdict, is
the evidence for FR-366.

## Limits

These measurements apply to the retained cases on 26.124 (8172026), far field 5,
and the named development revisions. Metadata exclusions are part of the
comparison definition, not proof that entire records or files are byte-identical.
The acoustic termination is localized to opening/setup of the next polar, not
to a proven individual command. Section persistence is supported by the saved
scripts and doubled products, not a separate isolated solver experiment.
The time-average repeat retains its failing exact verdict; the coupled first
pass is kept with the reason it failed. No requirement status is promoted from implemented to verified by this
report.
