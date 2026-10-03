## The additional post

A scheduler submission is recorded as SUBMITTED, with no completed outputs.
Collection requires stable exports and unchanged source/script hashes before
recording EXTRACTED. Native scheduler logs remain native when EXPORT_LOG is
disabled; scheduler acceptance text is never presented as a solver log.

A row that names a second pproc, `ADDITIONAL_PPROC: p<id>`, has that pproc
extracted from each recorded point's final saved simulation by
`pyfs-matrix post <matrix> --additional-pproc`, with no solve (`test_g12_the_extraction_lands_in_additional_and_is_hashed`,
`test_g12_the_additional_script_never_solves_and_never_saves`). This section
defines what comes back and what the products of it are.

**What a reopened saved simulation gives back.** Measured by the licensed probe
T09 on 26.124, on two saved points (a steady half wing-body and an unsteady
pusher rotor) reopened from a copy with no solve, against the run's own exports
([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md)):

| export | reopened, with no solve |
|---|---|
| total loads | identical |
| surface solution | identical bytes |
| surface sections, a distribution created after reopening included | identical |
| sectional loads | identical once computed after reopening, and zero until then: the file stores the sections and not their loads, so the extraction computes them every time |
| plots history of an unsteady point | identical |
| probe points, off the body | NOT identical: updated or created after reopening, they differ from the run's, by up to 4 percent in speed and 0.094 in Cp |

The saved file of the unsteady point is its last instant. Only 26.124 was
measured, so a row on another build stating the key is refused at plan
(`test_g12_a_row_on_another_build_is_refused_naming_rpt062`). The field off the
body (probe points and a volume section), the plots of a march and a surface
averaged in time are refused in an additional pproc for the same reason:
nothing measured says a reopened file gives them back
(`test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062`,
`test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused`).

**One instant on an unsteady point.** The saved simulation of an unsteady run
is its LAST instant, so every table of an unsteady extraction is one instant
and not the run's history: the sections table's `STEP` is the run's last time
step and its entry says `"kind": "instant"`
(`test_g12_an_unsteady_extractions_sections_table_is_the_last_instant`), and
the post log says it once per extraction
(`test_g12_an_unsteady_extraction_is_one_instant_in_the_post_log`). The plots
history the extraction exports is the run's own, so the plots tables and the
reductions over it are the run's history read under the additional pproc.

**The products.** Written by the post under `post/<matrix>/additional/<pid>/`,
beside the run's own and never over them, by the builders the run's products
use: the additional pproc's group polars on a steady point, one sections table
per point, and on an unsteady point the plots tables and their reductions.
Each table opens with `POL`, the polar of the point the extraction was taken
from, like every table of the run's own.
Every entry of `products.json` for them carries
(`test_g12_additional_products_are_marked_with_the_pproc`):

| key | meaning |
|---|---|
| `pproc` | the ADDITIONAL pproc id, not the one the row ran with |
| `additional` | always `true`, written `"additional": true`; a reader that takes every entry as a product of a run filters on it |
| `extraction` | the extractions the file holds, each `<point run id>/additional/<pid>` |
| `derives_from` | the points those extractions were taken from |

and no `runs`, which names run ids everywhere else in the index. The surface
exports and the plots history of an extraction are indexed as the solver wrote
them, in the point's `datapoints/DP-<point>/additional/<pid>/`, with the same
marks.

**Which rows the sections table holds.** A reopened sections export carries the
distributions the run created FIRST and the additional pproc's after them
(RPT-062). The table keeps every row: the layout the extraction records is the
run's own blocks followed by the new ones, numbered on after the run's and
marked with the pproc, so `FAMILY` and `PLANE` say which row is which, and the
extraction's `leading_sections` counts the run's rows at the head
(`test_g12_the_additional_sections_table_holds_the_run_rows_then_the_additional_ones`).
A layout whose counts do not add up to the export states `NA`, as on the run's
own table.

**Which frames and boundaries it cites.** The extraction cites the frames and
the boundaries the saved simulation holds, which are the run's. A frame is the
run's only while the row creates it today exactly as the run's recorded script
did, in every line a script defines or moves a frame with: its index and name,
its origin and three axes, and every later turn, move, copy or deletion. A
point whose row creates a frame differing in any of them, a frame turned under
its old name and place included, is skipped `SCRIPT_DRIFT` naming the line
(`test_g12_a_frame_turned_since_the_run_under_the_same_name_is_skipped`,
`test_g12_a_frame_moved_after_it_was_placed_differs_by_the_move`), since a
distribution cited in it would be cut in the frame the file holds and not the
one the pproc means. The boundaries are the run's and never today's file's:
the names the run's record states or, when the record has no boundary names, the
names read by the geometry's hash as the post's own tables read them (*The
geometry's names*, above). A point whose row declares the boundaries in another order today is
skipped `SCRIPT_DRIFT` naming both orders
(`test_g12_an_older_record_is_held_to_the_boundaries_its_geometry_hash_recovers`),
and so is one whose names nothing on disk recovers while the geometry declares
names today
(`test_g12_an_older_record_whose_boundaries_no_hash_recovers_is_skipped_naming_why`):
an index read off today's file would cut whichever surface holds that index in
the saved one, under the name the pproc asked for.

**When an extraction stops counting.** Only a CURRENT extraction has products:
its point is a record the post admits, the point's saved simulation still
hashes as the one the extraction opened, in the point's record and as the file
on disk, and every file the extraction wrote is on disk and hashes as recorded
(`test_g12_an_extraction_of_another_state_of_the_point_is_stale`). A saved
simulation deleted or replaced under a record nobody rewrote leaves every
extraction of it stale, named by the path
(`test_g12_an_extraction_whose_saved_simulation_left_the_disk_is_stale`). A
point that ran again, by a forced rerun or a continuation, archives its folder
with the extraction in it; the old extraction is then stale, the post skips it under
`additional/<pid>/runs/<extraction id>` and never under the run's own key, so
no product of the run is retired for it, and a previous additional product
nothing current supplies is archived like a refused table. The next
`--additional-pproc` extracts the point again
(`test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product`). The
extraction pass reuses an extraction by the same test of its files, so one
whose file was changed or truncated since is extracted again by the next
`--additional-pproc` rather than called already extracted, and its products
come back
(`test_g12_an_extraction_whose_file_changed_is_extracted_again`).

---
