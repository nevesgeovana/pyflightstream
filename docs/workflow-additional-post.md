# Extracting more from a finished point: the additional post

A row may name a second post-processing artifact, `ADDITIONAL_PPROC: p<id>` in
its `VAR_NAMES_VALUES` cell (G12). The row runs exactly as it
would without it: every point plans READY
(`test_g12_a_row_stating_additional_pproc_plans_ready`), no builder reads the
key, so the run script is byte for byte the one without it
(`test_g12_the_key_changes_no_byte_of_the_run_script`), and the run record
never carries it (`test_g12_the_run_record_never_carries_the_key`). Afterwards,
over the points the run recorded, one command extracts that artifact from each
point's final saved simulation, with no solve:

    VAR_NAMES_VALUES
    ADDITIONAL_PPROC: p002

    pyfs-matrix post extracted.fs --workspace . --additional-pproc

**What a reopened saved simulation gives back was measured, and the additional
post extracts exactly that.** The licensed probe T09 reopened two saved points
on 26.124 from a copy, with no solve, and compared every export with the run's
own ([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md)):
a steady half wing-body and an unsteady pusher rotor. The total loads, the
surface solution (to the byte), every surface section, a distribution defined
after reopening included, and the unsteady point's force-plot history came back
identical. The sectional loads came back zero until computed again and
identical once computed, because the file stores the sections and not their
loads. The probe points off the body did not come back: updated or created
after reopening, they differ from the run's, by up to 4 percent in speed. The
file of an unsteady point holds its last instant. One build and two geometries
were measured; the
[definition of record](post-processing-definitions.md#the-additional-post)
tables the result export by export.

**What it does, per point.** It copies the point's `.fsm` into
`sims/sim_<POL>/datapoints/DP-<point>/additional/<pid>/` and checks that the
copy hashes as the run record says before anything is launched
(`test_g12_a_copy_that_does_not_hash_as_recorded_fails_and_launches_nothing`),
writes a script under `sims/sim_<POL>/scripts/additional/<pid>/` and runs it in
that folder, one solver launch per point
(`test_g12_the_extraction_lands_in_additional_and_is_hashed`). The script opens
the copy, creates the artifact's section distributions in the frames the run
created (`test_g12_the_distributions_cite_the_frames_the_run_created`), updates
the sections and computes their sectional loads, exports the loads table, the
surface solution the artifact's `[exports]` selects (Tecplot unless it says
false, VTK and CSV where it says true), the sections, the sectional loads, the
log and, on an unsteady point, the plots history, and closes
(`test_g12_the_additional_script_renders_its_committed_bytes`). It never
solves, never saves and never writes a probe
(`test_g12_the_additional_script_never_solves_and_never_saves`). The copy is
removed afterwards and the original `.fsm` is hashed again; an extraction that
finds the original changed is recorded failed
(`test_g12_an_original_that_changes_during_the_extraction_fails_it`).

**Where the record goes.** Each extraction is recorded in `additional.json` at
the workspace root, beside `runs.json`: the hash of the saved simulation it
opened, its script, the files it wrote and their hashes
(`test_g12_the_extraction_lands_in_additional_and_is_hashed`). `runs.json` is
never written, so every point keeps the record its run wrote
(`test_g12_the_original_run_record_and_manifest_are_untouched`). The post then
writes the products of every current extraction under
`post/<matrix>/additional/<pid>/`, marked with the pproc
(`test_g12_additional_products_are_marked_with_the_pproc`); the
[definition of record](post-processing-definitions.md#the-additional-post)
says which.

**Who is extracted, and every reason a point is not.** A point is skipped by
name, with the path or the hashes involved, when:

- its row states no `ADDITIONAL_PPROC` (`NO_KEY`,
  `test_g12_a_row_without_the_key_is_skipped_naming_why`);
- its record names no `.fsm`, or the file it names is not there
  (`NO_SAVED_SIMULATION`,
  `test_g12_a_point_whose_saved_simulation_is_absent_is_skipped_naming_the_path`);
- the file does not hash as its record says (`HASH_MISMATCH`, naming both
  digests,
  `test_g12_a_point_whose_saved_simulation_does_not_match_its_record_is_skipped_naming_both_hashes`);
- the same artifact was already extracted from the same bytes into files that
  still hash as recorded (`ALREADY_EXTRACTED`,
  `test_g12_an_extracted_point_is_not_extracted_twice`); an extraction whose
  file was changed since is extracted again, as the post, which withholds its
  products, asks
  (`test_g12_an_extraction_whose_file_changed_is_extracted_again`);
- the build the row names today is not the one the point ran on
  (`BUILD_CHANGED`, `test_g12_a_point_whose_build_changed_is_skipped`): a saved
  simulation is reopened on the build that saved it;
- the run averaged its surface in time (`SURFACE_AVERAGED`,
  `test_g12_a_run_that_averaged_its_surface_in_time_is_skipped`): whether a
  reopened file gives back the average or an instant was not measured;
- the run's recorded script created other frames than the row creates today,
  or declared other boundaries (`SCRIPT_DRIFT`,
  `test_g12_a_row_whose_frames_changed_since_the_run_is_skipped`,
  `test_g12_a_point_whose_boundaries_moved_since_the_run_is_skipped`): a
  distribution would be cut in the wrong frame. Frames are compared by every
  line the script defines or moves one with, so a frame turned or moved since
  the run under its old name counts as another
  (`test_g12_a_frame_turned_since_the_run_under_the_same_name_is_skipped`).
  The run's boundaries are the names its record states or, when the record has no boundary names, the names of the geometry file whose sha256 the record carries
  (`test_g12_an_older_record_is_held_to_the_boundaries_its_geometry_hash_recovers`);
  a point whose names nothing on disk recovers, while the geometry declares
  names today, is skipped naming the file
  (`test_g12_an_older_record_whose_boundaries_no_hash_recovers_is_skipped_naming_why`);
- the point is still in a scheduler's queue (`NOT_FINISHED`,
  `test_g12_a_point_still_in_a_queue_is_skipped`), a continuation replaced it
  (`SUPERSEDED`,
  `test_g12_a_run_a_continuation_replaced_is_skipped_and_the_continuation_extracted`),
  or its row is no longer active (`ROW_NOT_ACTIVE`,
  `test_g12_a_point_whose_row_is_no_longer_active_is_skipped`).

**What the plan refuses, before a seat is spent.** An id the input library
lacks, naming the key and `inputs/pproc/<id>.toml`
(`test_g12_an_additional_pproc_the_library_lacks_is_refused_at_plan_naming_the_key`).
An additional artifact declaring `[[probes]]` or a `[volume_section]`: probe
points updated or created after reopening differ from the run's
([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md),
`test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062`), and the
field off the body does not come back as the run left it. `[plots]` or
`[time_averaging]`, which fill during a march the extraction does not run.
`base_regions`, a mark made on a mesh before its solve. An `[exports]` turning
the sections or the sectional loads off, which the extraction always writes, or
turning on the probe points, the force distribution or a solver plot, which it
never writes
(`test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused`).
The key on a `LEGACY` row, whose recipe creates its frames by rules of its own
(`test_g12_the_key_on_a_legacy_row_is_refused`). And a row on a build other
than 26.124, the one build RPT-062 measured
(`test_g12_a_row_on_another_build_is_refused_naming_rpt062`).

**An unsteady point gives one instant.** The saved simulation of an unsteady
run holds its LAST instant (RPT-062), so what the extraction gives there is that
instant and not the run's per-step history. `pyfs-matrix plan` warns naming such
rows (`test_g12_plan_warns_that_an_unsteady_rows_additional_post_is_one_instant`),
the extraction warns per point and says so in its record, and the plots
history it exports is the run's own
(`test_g12_an_unsteady_point_is_one_instant_and_says_so`).

**The command line.** `--additional-pproc` needs the matrix, since the key is
read from its rows (`test_g12_the_additional_post_needs_the_matrix`), and takes
`--fs-version`, `--fs-exe`, `--local` and `--recipe` as `run` does; each of
those four is refused without it
(`test_g12_a_flag_of_the_additional_post_without_it_is_refused`). It prints
one line per point, extracted, failed or skipped with its reason, then posts
(`test_g12_the_cli_post_additional_pproc_prints_each_point_and_exits`).
A failed extraction exits 2, and `--strict` exits 3 when a point was skipped for
a reason that asks something of you; a row without the key, an extraction
already done and a continued run ask nothing
(`test_g12_the_cli_exits_2_on_a_failed_extraction_and_counts_under_strict_a_skip_that_asks`).

**The executor is the one `run` would build**, so `--local` means the same
thing. A submitting workspace records each extraction as
`SUBMITTED`. The scheduler receives a separate working directory and a verified
copy of the saved simulation. `pyfs-matrix collect <workspace>` waits for stable
declared exports, checks the original simulation, script and private-copy hashes,
translates the surface outputs, then records `EXTRACTED` and removes the copy.
Submission alone never means extracted
(`test_submitted_extraction_waits_then_collects_without_mutating_original`). Repeating the request while it is pending
does not submit another job. The original run manifest stays unchanged
(`test_submitted_extraction_waits_then_collects_without_mutating_original`).

**On a cluster whose profile states `[log] export_log = false`** the extraction
scripts carry no `EXPORT_LOG`, whether the plan is built for `--local` or for a
submission, since the build there aborts at it either way
(`test_an_additional_post_planned_for_a_submission_exports_no_log`). The
extraction writes its declared log from what the solver printed, as a run
kept local does, and with nothing printed the log is not required; the
extraction record's `note` says which
(`test_an_additional_post_under_local_exports_no_log_on_such_a_machine`,
`test_an_additional_post_writes_the_printed_output_as_its_log`).

**A rerun or a continuation archives the extraction with its run**, since
`additional/` sits inside the point's own folder. The old extraction is then
stale, the post skips it under its own key and retires none of the run's
products for it, and the next `--additional-pproc` extracts the new run
(`test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product`).
