# Migrating to 0.16.0

> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.

## Residual and status recovery

**THE RECORDED RESIDUAL WAS THE WRONG ROW UNTIL 0.16.0, so this
requirement does not hold over manifests written before it.** The log's
residual table is paged and the reader stopped at the first page, so a
run that outlasted its first page was judged on the residual it held at
that page's end. The consequence is not a wrong number but a wrong
STATUS, which is what this requirement guarantees, and there is a
measured instance: the point at `pfs0160/runs.json` recorded
`COMPLETED_MAX_ITER` with `iterations: 100` and residual `1.256467e-05`,
which is line 295 of its own log, while that log's last row is iteration
206 at `1.3470951E-6`. The run converged at 206 and the manifest says it
hit its cap. `COMPLETED_MAX_ITER` asserts the solver reached the
iteration limit, and this one did not.

## Re-derive historical iteration counts

So the rule is not a universal but a condition: AN ITERATION COUNT
RECORDED BEFORE 0.16.0 IS UNTRUSTWORTHY WHERE THE RUN OUTLASTED ITS FIRST
PAGE, which is 89 of the 95 recorded points. This requirement asked the
model to re-derive them from the logs or exclude them and say so.

## Repeated and empty sectional cuts

WHAT IT IS FOR. A run came back with fifty surface sections that say
nothing. Measured over the nineteen committed licensed runs of
`tests/tier3_licensed/`, which is the locator this sentence carried
nowhere while every other measured claim of this range names its
artifact (the verification lens at the release boundary, 2026-09-11): 19 of 19
declare twenty sections and write twenty blocks, 19 of the 20 identical,
and 11 of the 19 came back with all twenty EMPTY. So every sectional
result this package produced before 0.16.0 is one cut repeated, and more
than half are one EMPTY cut repeated.
