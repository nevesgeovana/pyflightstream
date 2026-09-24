# Migrating to 0.27.0

This release takes the basic steps of a FlightStream session through pyfs and
fixes inputs and outputs that were wrong. Nothing is removed, and recorded run
manifests are read without rewriting them. What changes for you is what some
products hold, and what a few files say.

## 1. A steady probe export holds each declared line once (B04)

A pproc declaring N probe lines gave N squared `NEW_PROBE_LINE` commands on a
steady row: three lines of eleven points exported 99 points where 33 were asked
for, as N repeated blocks of the declared lines. From 0.27.0 each line is
emitted once.

The repetition was of the LINES of one probe entry: rectangles and circles
were emitted once, point by point. So for an export made before 0.27.0 from a
pproc whose only probe entry declares lines and nothing else, keep its first
N-th rows: they are the declared lines, in declaration order, and the other
blocks repeat them value for value (measured on a 26.124 export of three
lines). For any other layout (several entries, or lines beside a rectangle or
a circle) do not cut the file: rerun the point, or rebuild the post from a
0.27.0 run. An export from an entry with one line is unaffected.

## 2. An induced drag the solver did not compute is `NA` (B03)

A boundary on the vorticity induced-drag list (`SET_VORTICITY_DRAG_BOUNDARIES`)
without a defined trailing edge is not computed, and the export prints its
`CDi` as zero. A polar group holding such a surface summed that zero. From
0.27.0, when the point's run record puts a surface on the list and its printed
`CDi` is exactly zero, the group's `CDI` is `NA`, and so is every axis column
the export's x force reaches at that point's angles (`CDB`, `CDS`, `CDW`; `CLS`
and `CLW` off zero incidence; `CYW` under sideslip). `post.log` names the
surfaces. The fixed-width custom polar writes the same missing value as `nan`.

If a table of yours now shows `NA` where it showed a number, the surface is on
the list without a trailing edge: give it one, or leave it off the list, which
is what the manual prescribes for a bluff body. A trailing-edged surface whose
induced drag rounds to zero at the printed precision reads `NA` too; raise
`SET_SIGNIFICANT_DIGITS` to narrow that band.

## 3. `post.log` logs the package's own warnings only (R01)

Each post now collects the package's warnings in a sink of its own thread, so
two posts running in two threads of one process no longer write each other's
warnings. A warning raised during a post by code outside pyflightstream is no
longer written to `post.log`; it still reaches your warning filters, and
pyflightstream's own warnings are logged as before.

## 4. The moments of the unsteady step exports are about the moment point (B05)

The loads frame and the moments model were emitted after `START_SOLVER`, so
every step export an unsteady row wrote during the march stated its moments
about the reference frame's origin, while the final export stated the row's
moment point. Both are now emitted before the solve, on every run type, and
are init-phase commands: a script of yours that places either after
`START_SOLVER` is refused. A loads series (`series/<point>_loads_series.csv`)
made before 0.27.0 from an unsteady row states its moment columns about the
reference origin; its forces are right, so rebuild it from a rerun if you
need the moments. In your own scripts, call
`analysis_setup(loads_frame=..., moments_model=...)` before `start_solver`,
and the analysis selections (`load_units`, `boundaries`, `inviscid_only`)
in a second call after it.

## 5. `post.log.json` beside `post.log`, and a WARNING line names its own point (R02)

The top of each matrix's products folder holds a third loose file,
`post.log.json`, beside `post.log` and `products.json`. It carries the same
header and records as the log, one per WARNING line, each with `point`,
`product`, `message` and `remedy`. `products.json` names it under a new key,
`log_json`, and `log` still names `post.log`. A check that lists that
folder's loose files or the manifest's keys will see one more of each. A
rebuild archives it with the log.

A warning that names its own point and product is now logged under them:
`WARNING point=camp/sim_7001/AL-020 product=available-exports: ...` where
0.26.0 wrote `WARNING point=campaign product=stage: point=camp/sim_7001/AL-020
product=available-exports: ...`. A warning that names none still reads
`point=campaign product=stage`. An interrupted post's line ends `Remedy:
correct the stated input and post again.` If you parse `post.log`, read
`post.log.json` instead: it holds the same records as fields.
