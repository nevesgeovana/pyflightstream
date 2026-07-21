# HND-010: M3 opened with the probe harness and the pilot compat report (2026-07-21)

## 1. Context

M3 opening session (PLN-007) against STATUS.md. Delivered the Tier 2
probe harness under `qa/` end to end (generator, runner, compat
report writer, apply-compat, and the first `pyfs-qa` console entry
point), then ran the real pilot on the script_controls family with
the 26.120 executable from `_private/exe/`. The first compat report
is committed (`reports/compat/CMP-26120_2026-07-21`) and the three
pilot statuses are promoted to verified through apply-compat, each
citing the report. Suite at 135 tier 1 tests, ruff and format clean,
mkdocs strict build green.

## 2. Decisions

1. Probe anatomy: the target command sits between two sentinel PRINT
   markers, each followed by an EXPORT_LOG, so the exported log
   carries a region that belongs to the target alone; error patterns
   are scanned only inside that region, and startup noise never
   blames the command. `printed_line` discounts lines carrying
   `PRINT <marker>` so command echo could not fake a sentinel (the
   real 26.120 log turned out not to echo commands at all; messages
   print as lines of their own).
2. An effect assertion is mandatory: `ProbeSpec` refuses construction
   without one (a command that runs but does nothing is broken, not
   verified, SAD Section 11). STOP inverts the sentinel logic
   (`expects_halt`): the halt itself is the asserted effect.
3. A baseline probe (PRINT plus EXPORT_LOG plus CLOSE_FLIGHTSTREAM,
   the instrument set every probe relies on) runs first and aborts
   the whole run on failure: a dead license must never be recorded
   as broken commands. The baseline log also yields the solver
   identity line (version string plus build number, FR-18).
4. Real-run finding: a relative EXPORT_LOG path fails silently (the
   target folder does not exist under the execution directory), so
   probe scripts address logs and support files absolutely.
5. Real-run finding: after STOP the hidden solver idles and never
   exits; the halt evidence is the log pair (before present, after
   absent), never the process exit, and the halting probe carries a
   short timeout. A timeout outside a halt is recorded unprobed
   (inconclusive), never broken.
6. Compat reports are a YAML plus Markdown pair, stem
   `CMP-<version digits>_<date>`, one evidence line per command of
   the version view (112 lines: SONIC_VELOCITY is removed in 26.120
   and correctly outside the view). Reports are never overwritten.
7. apply-compat edits the chapter YAML line-level (flow-mapping
   version lines only), preserving comments and layout; a multi-line
   version entry is refused loudly, and every rewritten entry is
   re-validated against the command schema. Broken promotions carry
   a sanitized note from the probe detail.
8. First console entry point: `pyfs-qa` (probe, apply-compat) in
   pyproject `[project.scripts]`; convert-matrix CLI wiring is still
   pending (noted in STATUS at HND-009).

## 3. Changes persisted

* `src/pyflightstream/qa/probes.py`: ProbeSpec/ProbeResult/ProbeRun,
  ProbeOutcome, ProbeEnvironmentError, ProbeArtifacts with the
  sentinel-delimited region, generate_probe_script, probe_version
  with the baseline guard, PROBE_SPECS pilot family (PRINT, STOP,
  RUN_SCRIPT).
* `src/pyflightstream/qa/compat.py`: write/read_compat_report,
  apply_compat with schema re-validation.
* `src/pyflightstream/qa/cli.py` and the `pyfs-qa` entry point.
* `tests/test_qa_probes.py` (fake solver interpreter covering every
  classification path) and `tests/test_qa_compat.py` (hermetic
  chapter fixture); 18 new tests, suite at 135.
* `reports/compat/CMP-26120_2026-07-21.yaml` and `.md`: the first
  committed compat report (build #7012026; 3 verified, 0 broken,
  109 unprobed).
* `src/pyflightstream/commands/script_controls.yaml`: STOP, PRINT,
  RUN_SCRIPT promoted to verified for "26.120" citing the report
  (via apply-compat, invariant 3).
* `.gitignore` (probe_runs/ scratch), `pyproject.toml` (scripts
  section), STATUS.md, plan.csv (PLN-007 done, PLN-011 added), this
  handoff, logbook row.

## 4. Open questions and contradictions

New: whether M3 closes on the pilot report (the exit criterion reads
met: committed report, statuses promoted) or on the full sweep of the
remaining 109 commands; Geovana's call, recorded in STATUS. New: the
non-control families need probe preludes (minimal geometry or model
before the sentinels) and effect assertions per family; the
`ProbeSpec.prelude` seam exists but no prelude is written yet. New:
the error-pattern list is conservative and grows on real-log
evidence. Carried: SWEEPER chapter follow-up pass, xarray gate when
`post/` starts, SMI genericization, FR-18 string-only limitation.

## 5. Single highest-value next action

Extend `PROBE_SPECS` family by family toward full 26.120 coverage
(PLN-011), starting with file_io (EXPORT_LOG, OUTPUT_SETTINGS_AND_
STATUS, NEW_SIMULATION, SAVEAS, OPEN, CLOSE_FLIGHTSTREAM), whose
effects are file artifacts and need no geometry prelude; then design
the minimal-model preludes for the solver families and sweep, landing
a new dated compat report and promotions per batch.
