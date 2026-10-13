<!--
GEOVERSE_HEADER
file_version: 1.0.0
last_modified_at: 2026-10-13T14:35:00-03:00
last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
dependencies: [tests/tier1_offline/test_additional_post.py]
authority: pyflightstream
status: active
confidentiality: internal
change_summary: Restore public additional-post skip reasons removed with internal citations.
revision_source: git
-->

# Extracting more from a finished point: the additional post

A row may name a second post-processing artifact, `ADDITIONAL_PPROC: p<id>` in
its `VAR_NAMES_VALUES` cell. The row runs exactly as it
would without it: every point plans READY
, no builder reads the
key, so the run script is byte for byte the one without it
, and the run record
never carries it. Afterwards,
over the points the run recorded, one command extracts that artifact from each
point's final saved simulation, with no solve:

    VAR_NAMES_VALUES
    ADDITIONAL_PPROC: p002

    pyfs-matrix post extracted.fs --workspace. --additional-pproc

**What a reopened saved simulation gives back was measured, and the additional
post extracts exactly that.** The licensed probe T09 reopened two saved points
on 26.124 from a copy, with no solve, and compared every export with the run's
own:
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
,
writes a script under `sims/sim_<POL>/scripts/additional/<pid>/` and runs it in
that folder, one solver launch per point
. The script opens
the copy, creates the artifact's section distributions in the frames the run
created, updates
the sections and computes their sectional loads, exports the loads table, the
surface solution the artifact's `[exports]` selects (Tecplot unless it says
false, VTK and CSV where it says true), the sections, the sectional loads, the
log and, on an unsteady point, the plots history, and closes
. It never
solves, never saves and never writes a probe
. The copy is
removed afterwards and the original `.fsm` is hashed again; an extraction that
finds the original changed is recorded failed
.

**Where the record goes.** Each extraction is recorded in `additional.json` at
the workspace root, beside `runs.json`: the hash of the saved simulation it
opened, its script, the files it wrote and their hashes
. `runs.json` is
never written, so every point keeps the record its run wrote
. The post then
writes the products of every current extraction under
`post/<matrix>/additional/<pid>/`, marked with the pproc
; the
[definition of record](post-processing-definitions.md#the-additional-post)
says which.

**Who is extracted, and every reason a point is not.** A point is skipped by
name, with the path or the hashes involved, when:

- its row states no `ADDITIONAL_PPROC` (`NO_KEY`);
- its record names no `.fsm`, or the file it names is not there (`NO_SAVED_SIMULATION`)
;
- the file does not hash as its record says (`HASH_MISMATCH`, naming both digests);
- the same artifact was already extracted from the same bytes into files that
  still hash as recorded (`ALREADY_EXTRACTED`); an extraction whose
  file was changed since is extracted again, as the post, which withholds its
  products, asks
;
- the build the row names today is not the one the point ran on (`BUILD_CHANGED`)
: a saved
  simulation is reopened on the build that saved it;
- the run averaged its surface in time (`SURFACE_AVERAGED`): whether a
  reopened file gives back the average or an instant was not measured;
- the run's recorded script created other frames than the row creates today,
  or declared other boundaries (`SCRIPT_DRIFT`): a
  distribution would be cut in the wrong frame. Frames are compared by every
  line the script defines or moves one with, so a frame turned or moved since
  the run under its old name counts as another
.
  The run's boundaries are the names its record states or, when the record has no boundary names, the names of the geometry file whose sha256 the record carries
;
  a point whose names nothing on disk recovers, while the geometry declares
  names today, is skipped naming the file
;
- the point is still in a scheduler's queue (`NOT_FINISHED`), a continuation replaced it (`SUPERSEDED`)
,
  or its row is no longer active (`ROW_NOT_ACTIVE`).

**What the plan refuses, before a seat is spent.** An id the input library
lacks, naming the key and `inputs/pproc/<id>.toml`
.
An additional artifact declaring `[[probes]]` or a `[volume_section]`: probe
points updated or created after reopening differ from the run's
, and the
field off the body does not come back as the run left it. `[plots]` or
`[time_averaging]`, which fill during a march the extraction does not run.
`base_regions`, a mark made on a mesh before its solve. An `[exports]` turning
the sections or the sectional loads off, which the extraction always writes, or
turning on the probe points, the force distribution or a solver plot, which it
never writes
.
The key on a `LEGACY` row, whose recipe creates its frames by rules of its own
. And a row on a build other
than 26.124, the one build  measured
.

**An unsteady point gives one instant.** The saved simulation of an unsteady
run holds its LAST instant, so what the extraction gives there is that
instant and not the run's per-step history. `pyfs-matrix plan` warns naming such
rows,
the extraction warns per point and says so in its record, and the plots
history it exports is the run's own
.

**The command line.** `--additional-pproc` needs the matrix, since the key is
read from its rows, and takes
`--fs-version`, `--fs-exe`, `--local` and `--recipe` as `run` does; each of
those four is refused without it
. It prints
one line per point, extracted, failed or skipped with its reason, then posts
.
A failed extraction exits 2, and `--strict` exits 3 when a point was skipped for
a reason that asks something of you; a row without the key, an extraction
already done and a continued run ask nothing
.

**The executor is the one `run` would build**, so `--local` means the same
thing. A submitting workspace records each extraction as
`SUBMITTED`. The scheduler receives a separate working directory and a verified
copy of the saved simulation. `pyfs-matrix collect --workspace <workspace>` waits for stable
declared exports, checks the original simulation, script and private-copy hashes,
translates the surface outputs, then records `EXTRACTED` and removes the copy.
Submission alone never means extracted
. Repeating the request while it is pending
does not submit another job. The original run manifest stays unchanged
.

**On a cluster whose profile states `[log] export_log = false`** the extraction
scripts carry no `EXPORT_LOG`, whether the plan is built for `--local` or for a
submission, since the build there aborts at it either way
. The
extraction writes its declared log from what the solver printed, as a run
kept local does, and with nothing printed the log is not required; the
extraction record's `note` says which
.

**A rerun or a continuation archives the extraction with its run**, since
`additional/` sits inside the point's own folder. The old extraction is then
stale, the post skips it under its own key and retires none of the run's
products for it, and the next `--additional-pproc` extracts the new run
.
