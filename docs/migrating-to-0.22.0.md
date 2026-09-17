# Migrating to 0.22.0

0.22.0 changes one thing about your matrix, and it is a breaking change:

> **A row's rotor speed says how fast. The reference says which way.**

If none of your rows turns a rotor, nothing here applies to you and the upgrade
is a version bump.

## 1. What changed, and the defect it closes

Until 0.21.1 the reference's `rpm_sign` was copied into a case **only when the
row stated no speed of its own**. A row that stated `RPM` turned whichever way
its number was written, and the rotor block's declared hand was dropped in
silence — no refusal, no warning.

A rotor turning backwards converges and reports numbers. Nothing downstream
notices, and the results look like results.

From 0.22.0:

* a row's `RPM` and `ADVANCE_RATIO` are **magnitudes**; a negative one is
  refused by name;
* the hand of the rotation is **`rpm_sign` on that rotor's block** in the
  reference artifact, beside the axis, the origin and the blade count it already
  declares there;
* the sign is applied to **both** speed forms, the stated rev/min and the one
  derived from a ratio;
* it reaches the row **however the row names its rotor** — in a `MOTIONS`
  record, in the row's own `MOVING_BC_ALIAS` cell, or, on the pre-0.15.0
  spelling, through the boundary it turns when that boundary belongs to a
  declared block;
* the point **name** writes `RPM` as a magnitude, because the hand is a property
  of the ROTOR and naming it in the point would give one operating point two
  identities.

## 2. Correcting a row

Find any row whose rotor speed carries a sign:

```
... / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: -2400}
```

Write the speed positive, and put the hand on the block in the reference:

```toml
[PUSHER]
kind = "rotor"
axis = "X"
rpm_sign = -1        # which way this rotor turns
# ... origin, diameter and blade families as before
```

The row becomes `RPM: 2400`.

**Do not write `RPM_SIGN` on a row that names a rotor block.** It is refused,
whether or not it agrees with the block — a row that agrees today says nothing
when the reference is corrected tomorrow, and that silence is the whole defect.

**One exception.** A row using the pre-0.15.0 spelling — `ROTOR_AXIS` and
`MOVING_BOUNDARIES`, naming no block — has nowhere else to put the hand, so
`RPM_SIGN: -1` beside the speed is correct and is unchanged. If the boundary
that row turns is one of a declared block's own families, the block governs and
the row is refused for restating it.

## 3. A workspace whose rotor already ran

**Read this before running anything.** If a row of yours turned a rotor and the
reference declared a hand the emitted script did not carry, **the runs that came
out of it turned the wrong way**. They converged. They have tables. They are
wrong, and no file in the workspace says so.

So the first question is not how to rename those points. It is which of them are
still evidence.

1. For each rotor row, compare the sign the script actually carried against the
   hand you intend. The emitted script states it directly:
   `SET_MOTION_ROTOR_RPM <n> <rev/min>`.
2. **Where the sign is wrong, the point must be RE-RUN, not renamed.** Renaming
   files a wrong-direction result under the corrected point's identity, which
   launders bad evidence into a name that claims to be good. Correct the row and
   the reference, then:

   ```
   pyfs-matrix plan --workspace <root>
   pyfs-matrix run --workspace <root> --force-rerun <point or run_id>
   ```

   `--force-rerun` archives the record and that point's collected outputs and
   runs it again, leaving every point it does not name alone.
3. **Where the sign was already right**, the point is unaffected: its script,
   its outputs and its record all stand.

### If the point NAME changed

Only a row that wrote its hand into the number is affected: its points were
named `...RPM-2400` and the corrected row names them `...RPM02400`.

Those are exactly the points from step 2 — the ones whose rotor turned the way
the number said rather than the way the reference said. Re-run them; the new
name is written by the re-run. `pyfs-matrix rename` is for a workspace whose
points are still valid and whose NAMES moved, which is not this case: here the
values moved too, and `rename` refuses a matrix that changed since the run.

## 4. The order to do it in

1. Put `rpm_sign` on each rotor block of your reference artifacts.
2. Take the sign out of every row's `RPM` and `ADVANCE_RATIO`, and remove
   `RPM_SIGN` from any row that names a rotor block.
3. `pyfs-matrix plan --workspace <root>` — this refuses anything still wrong,
   by name.
4. Check the emitted sign for each rotor row against the hand you intend.
5. `--force-rerun` the points whose sign was wrong. Leave the rest.
6. `pyfs-matrix collect` and `pyfs-matrix post` as before.

## 5. What is not changed

`WALLTIME`, the HPC profile, the point-name scheme of 0.21.0, the sweep
vocabulary and every non-rotor row are untouched. A steady row does not read a
rotor speed at all.
