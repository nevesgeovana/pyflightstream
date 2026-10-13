# Migrating to 0.8.1

> Historical record assembled at 0.36.0 from the reference pages; frozen from now on.

## Historical row-key changes

- before v0.8.1: `VELOCITY`, `RPM`, `ROTOR_AXIS`, `ROTOR_ORIGIN`, `ROTOR_SHEDDING`, `BLADES`, `MOVING_BOUNDARIES`, `DELTA_TIME`, `TIME_ITERATIONS`, `WINDOW_DEGREES`, `WINDOW_STEPS`, `WINDOW_REVOLUTIONS`, `OUTPUTS`
- v0.8.1: `GEOMETRY`, `SYMMETRY`, `PERIODIC_COPIES`

## Reserved names and the byte-for-byte renders

**`REVOLUTIONS` AND `DELTA_THETA` ARE THE TWO TO CHECK FIRST**, because
they are ordinary words a rotor study is likely to have already used for
its own bookkeeping. A cell of yours spelling either is now the
package's, so rename yours or adopt the meaning.

The match is on the EXACT key, so a cell spelling it `SYMMETRY_TYPE` or
`N_REVOLUTIONS` is untouched. The rows of [the run matrix](workflow-run-matrix.md) use `FSM_FILE`, a key of
their own that nothing in the package reads; moving a row off `LEGACY`
is the moment to rename it to `GEOMETRY`, and a row that stays on
`LEGACY` keeps its recipe and its own key with nothing changed for it.

v0.9.0 added a larger upgrade risk than any name, the removal of the
`RE` and `MACH` columns, which is handled by
`pyfs-matrix upgrade <path> --in-place` and described on
[the flight-condition page](flight-conditions.md).

A row that names none of the reserved keys behaves as it did before. The [input glossary](inputs.md) lists both matrix homes and the package-reserved names.

Going forward, every workflow crossed with each case shape the suite renders and every
build it covers is pinned as a committed golden under
`tests/tier1_offline/goldens/workflows/` and compared byte for byte on every run of the
suite. On one of the workflow-and-build pairs, `steady` on FlightStream
25.000, the builder refuses instead of rendering, and both of that pair's
goldens pin the refusal text; the changelog's "Known gaps" says why.

Looking back, the same case shapes were rendered against a worktree
at the `v0.8.0` tag: every render came out byte for byte identical, and
the two refusals matched their text as well. That is the half the goldens
cannot prove on their own, since they were generated from this release.
The receipt is committed beside them.
