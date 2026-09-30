# Migrating to 0.32.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. The package's dependencies
and extras are the ones 0.31.0 declared.

Most of what changes is in how a workspace is kept: what a sync copies, what
is archived before a record is rewritten, and the two ways back to a lost
`runs.json`. The post gains a way to read another manifest, the console moves
its warnings to the end, and a few products gain files or columns. The
sections are in the order of their impact on an existing workspace; each
names what a script of yours must allow.

## A sync skips archive folders unless asked

`pyfs-matrix sync` no longer copies archive folders: every file under a folder
named `archive` (`post/<matrix>/**/archive/<stamp>/`, an `archive/` inside a
simulation) is skipped and counted in the preview. Add `--include-archives` to
bring them as before (FR-223).

`sync --restore` is off by default: a sync never writes a record it did not
merge unless asked (FR-221).

One matrix stem in both the workspace root and `inputs/matrices/` is read once
when the two files are identical, where `sync` refused it and the plan refused
every POL of it; with different content `sync` and `plan` refuse naming both
paths, and `post` warns naming both and falls back to the run records. Keep
one copy, or make the two identical (FR-224).

## Records are archived before they are rewritten

`products.json` is now archived rather than removed when a post rebuilds: the
previous file goes to `post/<matrix>/archive/<stamp>/products.json`.
`storage_management.json`, `additional.json` and `plan.json` are archived on
every rewrite, so `archive/` and `post/<matrix>/archive/` grow by one small
copy per write (FR-291, FR-292, FR-293). A copy that fails is warned and never
blocks the write (FR-294). A script that deletes or lists `archive/` will meet
these files.

## A lost runs.json: restore, then rebuild

A lost or overwritten `runs.json` has two ways back, and they are kept apart:
`pyfs-matrix restore runs --apply` puts back an archived copy exactly, and
`pyfs-matrix rebuild --apply` makes records again from `sims/` only where no
archive holds them, each marked `REBUILT`. Without `--apply` both preview.
`restore` also takes `storage`, `products`, `plan` and `additional`, the copies
the archiving above keeps. Never run `pyfs-matrix run --resume` on a
simulation a rebuild refused: with no record the resume runs it again
(FR-210, FR-211).

## The post and the collect read another manifest

`post` and `collect` take `--runs NAME`, which 0.31.0 did not have, to read
another manifest of the workspace root; the products of such a post are in
`post/<matrix>@<stem>/`, beside `post/<matrix>/`, which it never writes
(FR-230, FR-231).

A post from the simulation folders is `pyfs-matrix post <matrix> --from-sims`,
its products in `post/<matrix>@sims/` under the point names and the
`<code>+sweep` token the records were assembled with; a steady point with no
log export reads `FAILED_INCOMPLETE_OUTPUT` there and is still posted with a
warning, and a record assembled this way has no rotor block, so its rotor
tables are named skips (FR-232).

## The console: an opening block, progress, and warnings at the end

Standard output and exit codes do not change. Standard error gains a titled
opening block before a command's first line, and its warnings move to the end
of its output under `Warnings (<count>)` (FR-200, FR-201). A script that read
a warning from the middle of standard error reads it at the end.

The long commands print progress lines on standard error while they work, and
write `logs/<command>-<stamp>.log` in the workspace; the folder `logs/` already
holds `activity.log`, and nothing else is written elsewhere (FR-202, FR-203,
FR-204).

## Values that changed in the products

`J` of `_qs_avg.csv` and `_qs_positions.csv` was `NA` and now holds the rotor's
advance ratio where the row requested none; a reader that took `NA` there for
"no advance ratio" reads the number (FR-285).

A native strength matched at a point far from the origin, printed at limited
digits, may now match where it was refused as ambiguous or missing (FR-281,
FR-282).

A wheel row that opens a `.fsm` now shows its chord-based `k` in the plan, and
its warning, where it showed k per metre of chord (FR-274).

## New files beside the products and the records

A quasi-steady wheel point and an `unsteady_rotor` point that cut sections now
also write disc map files beside `sections/<point>_harmonics.csv` and register
them in `products.json` with `kind` `disc_map` (FR-270). Nothing existing
changes; a consumer that lists `sections/` will see the new files.

A record written by 0.32.0 may list files under `<point>_acoustic_section/`
among its outputs, with their sha256, and a reader of `outputs` meets them as
files of a subfolder of the datapoint folder; `classify_outputs` leaves them
and `<point>_acoustic_signals.txt` out of every export kind (FR-268).

The provenance record of a field written with a fluctuation report carries a
`sidecars` list; records written without one are unchanged (FR-250).

## Inputs a row or a call states

A relaxed trailing-edge specification passed to `parse_relaxed_trailing_edge`
or to `cases.workflows.rotor_relaxed_trailing_edges` is read as the manual
writes it. Four numbers are `u`, `v1`, `v2` and the direction; write three
(`0.5;0.1;0.9`) for a specification stating no direction. A text with five
numbers is refused. `RelaxedTrailingEdge(fields=...)` takes the three values
(FR-244).

A setup that states `slipstream_wake_stabilization` no longer gets the
recorded-only warning; the value is emitted for each rotor motion, and an
ENABLE on a row that states no blade count is now refused (FR-277).

`field time-mean` accepts `--fluctuation`, `--fluctuation-only` and `--vinf`;
without them it behaves as before (FR-250).

## Links into the documentation

A link or a bookmark to a section of `workspace-and-workflows.md` that moved
now lands on that page, the index of the Workflows group. Follow the table on
[that page](workspace-and-workflows.md) to the page that holds the section;
the anchor of every section is unchanged, so `<page>.md#<section>` works on the
new page. The links inside the documentation were updated.
