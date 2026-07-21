# HND-005: M2 files workspace and local executor (2026-07-21)

## 1. Context

Same-day continuation after HND-004, on Geovana's instruction to
proceed to `files/` and the local executor (SAD Sections 6 and 7,
PLN-005). Delivered and green locally: 82 tier 1 tests (up from 63),
ruff check and format clean, mkdocs strict build.

## 2. Decisions

1. The exact headless invocation was pinned from the manual before
   coding (paraphrased, cited): command-line script execution is
   `--script <file>` (SRC-003 p.279); the windowless mode is the
   `-hidden` flag, and in hidden mode an abnormal termination writes
   `FlightStreamLog.txt` into the command execution directory
   (p.280). LocalExecutor therefore runs the process inside the
   simulation folder and captures that file; the argv lives in one
   method (`_argv`) that Tier 2 probing can later verify.
2. The manifest generalizes the SAD Section 7 example field
   `geometry_sha256` into `inputs_sha256`, a name-to-hash mapping,
   because staging handles several input files and Section 6 says
   staging records hashes of the inputs (Claude; noted here, not a
   STATUS deviation since the SAD is a local design document).
3. Refusal semantics for destructive file management: `archive_sim`
   and `clean_sim` refuse when `runs.json` is missing, when it has no
   record of the sim, or when the folder is absent; `collect_outputs`
   refuses on a missing declared output and names
   FAILED_INCOMPLETE_OUTPUT in the message, tying it to the campaign
   status the loop will assign (PP-5).
4. The executor returns a typed `ExecutionResult` and never raises on
   solver failure; deciding a manifest status is the campaign loop's
   job, keeping "no silent skip" in exactly one place. Construction
   fails fast on a missing executable (explicit `fs_exe`, nothing
   from the environment, SAD Section 5).
5. Subprocess handling is tested without FlightStream through a
   FakeSolver subclass that swaps only the argv for a Python
   one-liner: return codes, hidden-mode log capture, timeout kill,
   and working directory are exercised for real (Tier 1 compatible).
6. gh authentication: the GH_TOKEN-via-`git credential fill` export
   is blocked by the Claude Code permission classifier (twice, even
   under explicit instruction); recorded in the STATUS open question.
   Resolved the same day: Geovana ran the persistent browser login
   in-session (`! "/c/Program Files/GitHub CLI/gh.exe" auth login
   --web`; the `!` prefix runs bash, not PowerShell). With gh
   working, CI evidence for this day's sessions: HND-004 close run
   29849504057 success, HND-005 close run 29850366257 success. The
   STATUS open question is closed.

## 3. Changes persisted

* `src/pyflightstream/files/__init__.py`: WorkspaceError, RunStatus
  (six terminal statuses), RunRecord (pydantic, extra forbidden),
  CampaignWorkspace (sim_dir naming guard, create_sim, stage_inputs
  with sha256, write_script with sha256, collect_outputs,
  read_manifest, append_record with atomic replace and unique run_id,
  archive_sim, clean_sim).
* `src/pyflightstream/run/__init__.py`: ExecutionResult,
  ExecutorConfigurationError, Executor protocol, LocalExecutor
  (documented argv, timeout, log capture, no shell).
* `tests/test_files.py` (13 tests) and `tests/test_run.py` (6 tests),
  including a builder-to-manifest flow test recording the raw_flag
  (FR-07).
* STATUS.md (current focus; gh open question updated), plan.csv
  PLN-005 note, this handoff, logbook row.

## 4. Open questions and contradictions

Carried over: SWEEPER chapter follow-up pass, xarray gate at post/
time, SMI genericization. Updated: gh auth (see decision 6). New:
none.

## 5. Single highest-value next action

The `cases/` SIM model (SAD Section 5: SimCase, SweepAxis,
ReferenceData, SolverSettings, Campaign with explicit fs_version and
fs_exe; campaign.toml persistence) and the campaign loop
(`run_campaign`) mapping executor outcomes into the six manifest
statuses with CampaignErrors aggregation; then the loads parser
(results/, anchor-based) to reach the M2 exit criterion.
