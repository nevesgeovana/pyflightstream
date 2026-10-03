<!--
GEOVERSE_HEADER
file_version: 1.0.0
artifact_id: RPT-152
last_modified_at: 2026-10-03T17:25:47-03:00
last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
dependencies: [RPT-113, compare_lp.txt, lp.json, launch_record_ref.txt, launch_record_cand.txt, compare_lp.py]
authority: pyflightstream
status: bounded-evidence
confidentiality: public
change_summary: Record the licensed LP parity reproduction against 0.35.1 on build 8172026.
revision_source: git
-->

# RPT-152 - pyflightstream 0.36 licensed parity reproduction against 0.35.1 on FlightStream 26.124 (2026-10-03)

The report of arm LP of pyflightstream 0.36.0 (NFR-40): the three-point
campaign of RPT-113 run by released **0.35.1 from PyPI**, then by candidate
**rel/0-36 at `08b9004c42e802e9117d9c9bde49915b5352ac69`** (`0.36.0.dev0`).
The package route planned, ran locally, collected and posted both arms on
**FlightStream 26.124, build 8172026**, hidden, far field 5 layers, one solver
instance at a time. The retained comparison reports **PASS**. No solver was
run to write this report.

Only nondimensional results, counts and run times are stated. Private paths,
geometry identities and executable provenance remain outside the public tree
per NFR-31. Retained evidence is named by file name and exact-byte SHA-256 in
section 5.

## 1. The campaign and why it is the reference

This is the recorded campaign used by RPT-113, originating in RPT-094 and
RPT-095. It covers steady solves at three passage positions and an unsteady
march on one rotor. Here the reference is a new run by PyPI 0.35.1 itself.

| matrix | row | points per arm | run type and what it moves |
|---|---|---|---|
| `l1_g1.fs` | 9311 | 1 | qsteady_rotor, three passage positions, angle of attack 5 degrees, sections |
| `l1_g6.fs` | 9321 | 1 | unsteady_rotor, uniform custom free stream, one revolution in 36 steps |
| `l1_g6.fs` | 9322 | 1 | unsteady_rotor, constant control, one revolution in 36 steps |

Three passage positions belong to the one point of 9311. There are three
points per arm, six newly run points in total. Both arms use the same copied
campaign inputs and solver controls.

The preparation `README.md` describes an earlier snapshot and unresolved
environment setup. Both launch records also retain an older
`candidate_commit` field. The candidate identity stated here comes from the
installed package's recorded VCS provenance in `launch_record_cand.txt`,
which names `08b9004c`, and agrees with the completed receipt `lp.json`.
The preparation state is not the completed run's provenance.

## 2. How the comparison is read

Following RPT-113, a copy of the completed reference was posted again with
the candidate package, so both arms' post products use one post implementation.
The change from `repost_ref.py.orig` to `repost_ref.py` handles the junctions
the package makes under its simulation tree: it records their internal
targets without traversing them and recreates them inside the copy. A
junction whose target leaves the reference workspace is refused; symbolic
links remain refused. The reference run is preserved.

The comparator checks the three point identities, status, positive iteration
counts, step counts, all three quasi-steady clocking verdicts, build, launch
records and completion of the reference repost. It compares the union of
CSV products against a required historical inventory, so equal omissions
cannot remove a required table from the comparison.

Rule 9 accepts byte-identical files first. Otherwise it drops columns by
the recorded metadata-header substring rule and compares retained headers,
row counts and cells. Text must match exactly; numeric cells use exact
Decimal equality, allowing equivalent exponent formatting. Relative 1e-6
is only the diagnostic `WITHIN` category: it does not grant PASS.

The audit records these actual dropped columns, in both arms:

| tables | columns dropped |
|---|---|
| The two `campaign_sweep.csv` tables | `run_id`, `fs_version_requested`, `fs_version_reported`, `fs_build`, `package_version`, `wall_time_s` |
| The two SUPER polars of 9311 and the unsteady-average table of each of 9321 and 9322 | `walltime_s`, `walltime_margin_s`, `march_strategy`, `accept_unregistered_build`, `solver_run_time_s`, `solver_initialization_s`, `FS_BUILD`, `WALLTIME`, `NCPUS`, `run_id`, `fs_version_requested`, `fs_version_reported`, `fs_build`, `package_version`, `wall_time_s`, `SET_SOLVER_MODEL` |

These are the columns the rule actually removes, including configuration
and provenance fields as well as timing. The audit separately records
`march_strategy`: `NA` for 9311 and `actions` for 9321 and 9322 in both arms.

Before the verdict, `compare_lp.py` was aligned with the RPT-113 method in
three places, as its diff against `compare_lp.py.orig` records:

1. Skipped products are compared for equality between the arms instead of
   being required empty. An explicit incomplete-products flag still fails.
2. Each `campaign_sweep.csv` is read from the reference run tree when absent
   from the repost tree. The run writes this table; the repost copy leaves
   the old post directory out, and posting does not recreate it.
3. The launcher recorded no exit code: PowerShell `ExitCode` was null and
   the records contain an empty `exit=`. Success is taken from three
   `CONVERGED` records in each arm with one solver at a time. The comparator
   still requires `DONE` and rejects recorded errors, refusals and RAM or
   timeout kills. No zero process exit code is claimed.

## 3. Results

| row | status, reference and candidate | iterations, reference and candidate | time steps, reference and candidate |
|---|---|---|---|
| 9311 | CONVERGED, CONVERGED | 61, 61 | not applicable in either arm |
| 9321 | CONVERGED, CONVERGED | 1048, 1048 | 36, 36 |
| 9322 | CONVERGED, CONVERGED | 1048, 1048 | 36, 36 |

All three clockings of 9311 are separately `CONVERGED` at 61 iterations in
both arms. The comparison has no failures.

| matrix | tables identical after rule 9 | tables within | tables differing or missing |
|---|---|---|---|
| `l1_g1.fs` | 15 | 0 | 0 |
| `l1_g6.fs` | 19 | 0 | 0 |
| total | 34 | 0 | 0 |

Every retained coefficient, section, pressure-coefficient, sectional-load,
harmonic, probe, per-revolution, phase-locked, time-average, rotor, reduction
and campaign table is identical. Of the 34 tables, 28 are byte-identical;
the remaining six are identical after the audited column removal.

The skipped-product maps are identical between the arms: zero entries for
the quasi-steady matrix and ten for the unsteady matrix, five per point.
Both unsteady points skip the same products for the same reasons:

- Section harmonics and disc maps lack the section time series from which
  the unsteady harmonics are fitted.
- Row-level phase-locked and per-blade reductions are skipped because the
  row names its rotors; each rotor has its own blade passage. The per-rotor
  phase-locked tables are present and compared.
- The per-rotor per-blade reduction lacks blade-family columns in the plots
  table. Obtaining them needs a new run with the corresponding plot groups.

These skips describe the campaign's available exports, not a difference
between versions. Equality of the skip maps does not demonstrate the
products that were skipped.

| arm | start, 2026-10-03 (UTC-03:00) | finish (UTC-03:00) | launcher wall time |
|---|---|---|---|
| reference 0.35.1 | 16:53:20.530 | 17:04:17.568 | 655.50 s |
| candidate at `08b9004c` | 17:04:56.385 | 17:17:52.499 | 774.41 s |

Wall times are the launch records' `wall_s` readings, not the elapsed
difference between their start and finish stamps. Each record reports a
maximum of one solver at once and no RAM or timeout kill. These two timings
do not establish a performance regression or its cause.

## 4. Verdict

**PASS for arm LP, NFR-40, on this campaign.** Candidate rel/0-36 at
`08b9004c` reproduces the PyPI 0.35.1 reference on 26.124 (build 8172026):
statuses, iterations, time steps and clocking verdicts agree; all 34 tables
are identical under rule 9; the skipped products agree.

The limits are one campaign, one rotor, three points, one solver build and
a Windows local run. This does not establish parity for every run type,
other builds, platforms or cluster execution, or for the skipped products.
Launch completion is supported by the converged records and monitoring;
the process exit codes were not recorded.

## 5. Retained evidence

The following files are retained outside the tree. SHA-256 is computed over
their exact file bytes (`hash_domain: exact-file-bytes`); the launch records
were not decoded and rewritten for hashing. Private paths and raw solver
products are not copied into this report.

| file | SHA-256 |
|---|---|
| `compare_lp.txt` | `37b1700584e47dd8ec9f6c1961e3c91ed0396d1fcd70c0f15760e6c6b75da898` |
| `lp.json` | `be26ce864eb9217422ac3c9127c59f92a69e9063eaaf24f0aa10f99e205d6dc2` |
| `launch_record_ref.txt` | `e441b74464fab697efa146b0754b003ec42cb813272d611c307584250ed2bdba` |
| `launch_record_cand.txt` | `8f647cbce13286e21bc2420648ce3ec47e2f9ea90a8d5b79bffc97264e0f262b` |
| `compare_lp.py` | `ae051f8f44f2db5252f15975101473f2fde1ec3f0ade7566c159ed02cf495a0c` |
| `compare_lp.py.orig` | `4dccddc5bb44efe411894cdb1836fc3916355633ec5baf544fcee7c430a7708d` |
| `repost_ref.py` | `b8ee8a463fc4da5c6ad191a0f00d8b714885781cd013295e97c9f0f1241dd4e2` |
| `repost_ref.py.orig` | `4d714ce3d25dba28b57d7b6e8332f340e8a41512666f030d80e1c2666efe6f36` |
| preparation `README.md` | `02335ba96f85f32ede184f6255d0dd580b9e0fda5e71a971bba90b5d0a7c0b9a` |
