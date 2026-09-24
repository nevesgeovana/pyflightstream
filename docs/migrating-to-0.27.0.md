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

If you read a steady probe export made before 0.27.0 from a pproc with more
than one line, keep only its first N-th rows: they are the declared lines, in
declaration order, and the other blocks repeat them value for value (measured
on a 26.124 export of three lines). An export from a pproc with one line is
unaffected.

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
