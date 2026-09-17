# Migrating to 0.22.0

0.22.0 changes one thing about your matrix, and it is a breaking change:

> **A row's rotor speed says how fast. The reference says which way.**

If none of your rows turns a rotor, nothing here applies to you and the upgrade
is a version bump.

## 1. What changed, and the defect it closes

Until 0.21.1 the reference's `rpm_sign` was copied into a case **only when the
row stated no speed of its own**. A row that stated `RPM` turned whichever way
its number was written, and the rotor block's declared hand was dropped in
silence -- no refusal, no warning.

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
* it reaches the row **however the row names its rotor** -- in a `MOTIONS`
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
whether or not it agrees with the block -- a row that agrees today says nothing
when the reference is corrected tomorrow, and that silence is the whole defect.

**One exception.** A row using the pre-0.15.0 spelling -- `ROTOR_AXIS` and
`MOVING_BOUNDARIES`, naming no block -- has nowhere else to put the hand, so
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
   pyfs-matrix plan <matrix> --workspace <root>
   pyfs-matrix run <matrix> --workspace <root> --force-rerun <point or run_id>
   ```

   `--force-rerun` archives the record and that point's collected outputs and
   runs it again, leaving every point it does not name alone.
3. **Where the sign was already right**, the point is unaffected: its script,
   its outputs and its record all stand.

### The point NAME changed for EVERY rotor point, including yours

**Read this even if your rotor was turning the right way.** `RPM` in a point
name is now written UNSIGNED and five digits wide, so the `+` is gone from every
rotor point that ever ran:

```
0.21.x   DP-M144RE438AL+000RPM+0800
0.22.0   DP-M144RE438AL+000RPM00800
```

That is not only the rows that carried a sign. A row that always stated
`RPM: 800` and always turned correctly has its folders, scripts and exports
under a name the workspace no longer computes.

**Two different cases, and they take opposite actions.**

**(a) The rotor was turning the RIGHT way.** The points are still evidence --
only the name moved -- so they are RENAMED, not re-run:

```
pyfs-matrix rename --workspace <root>
```

It reads the old name from the record and computes the new one from the row, so
it needs no version flag. Rehearse it first with `--dry-run` and read what it
says it will move.

**What is measured about that command, said exactly.** Its bridging of a
name-only change is measured end to end on a workspace that really ran: one pass
moved the datapoint folder and all seven files inside it, and the manifest with
them (`test_goal024_rename_command.py`, the name-only case). The `RPM` instance
is that same code path -- the rename compares the recorded name against the
computed one and branches on neither the field nor its width -- but this
release ships no case that exercises the `RPM` spelling specifically. Rehearse
before you apply.

**(b) The rotor was turning the WRONG way.** Those points are not evidence at
all, and `rename` will refuse them anyway, because correcting the row changes
the point's VALUES and a recorded point that is no longer a point of the row is
refused by name. Re-run them, as step 2 above says.

## 4. The order to do it in

1. Put `rpm_sign` on each rotor block of your reference artifacts.
2. Take the sign out of every row's `RPM` and `ADVANCE_RATIO`, and remove
   `RPM_SIGN` from any row that names a rotor block.
3. `pyfs-matrix plan <matrix> --workspace <root>` -- this refuses anything still wrong,
   by name.
4. Check the emitted sign for each rotor row against the hand you intend.
5. `--force-rerun` the points whose sign was wrong. Leave the rest.
6. Collect and post as before; neither stage changes in this release.

## 5. What is not changed

`WALLTIME`, the HPC profile, the sweep vocabulary and every non-rotor row are
untouched. A steady row does not read a rotor speed at all, and a point name
carrying no `RPM` field is written exactly as 0.21.0 wrote it.

The point-name scheme is NOT in this list: `RPM` lost its sign, which is section
3(a) above.
