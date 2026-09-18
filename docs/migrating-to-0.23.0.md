# Migrating to 0.23.0

This release changes the BYTES of every file the post stage writes, and renames
some of them. Read this before you upgrade a workspace you care about.

**You do not have to re-run anything.** Every change below is produced by

```
pyfs-matrix post --workspace <root>
```

over outputs you already collected, on Windows and on the cluster. There is one
exception and it is named in section 6.

---

## 1. No cell is ever blank again

A cell that does not apply to a row now reads `NA`.

```
before   9001,STEADY_WB,1,50.00000,2.52600,20.00000,9.15200,0.00000,0.00000,,-2.00000
after    9001,STEADY_WB,1,50.00000,2.52600,20.00000,9.15200,0.00000,0.00000,NA,-2.00000
```

A blank is ambiguous three ways: zero, not measured, or this column is not for
this row. Measured on a production super file, 50 of 628 columns in one row
were blank for the third reason alone.

**If you read with pandas, nothing changes.** Both `''` and `'NA'` are default
missing tokens for every column, so `read_csv` gave you `NaN` before and gives
you `NaN` now. Measured on pandas 3.0.5.

**If you parse by hand, this is the change.** The `csv` module gave you `""`
and now gives you `"NA"`. A reader that tested `cell == ""` must test for `NA`.
A reader that called `float(cell)` is unaffected: `float("")` raised before and
`float("NA")` raises now.

If `NA` is meaningful data in your own columns, pass `keep_default_na=False`
and name your own `na_values`.

**One token, not two.** The probes table's `STEP` column wrote `-` on a steady
row until this release and now writes `NA` like everything else. A reader
keying on `-` must change; one keying on `NA` already covers both.

**One exception, named rather than left to be found.** A run recorded before
0.16.0 names no probe-positions file, so that table's position and frame cells
are a value the package could not derive, and they read `NA` too. Refusing
those tables would take a product away from a campaign that already happened.

---

## 2. Every product says what it is a file OF

Every file the post stage writes now carries the whole flight condition
(`ALPHA`, `BETA`, `MACH`, `RE`, `VINF`, `ALT`, `J`) and the reference lengths
(`SREF`, `CREF`, `BREF`).

Before this release the sections, probes and reduction tables carried no
reference length at all, and the polar carried no `VINF` or `ALT`. A
coefficient beside no area is a number nobody can check, and a probe sample
with no condition is a table about nowhere.

**What this means for your reader:** these are NEW COLUMNS. A reader that
selects columns by name is unaffected. A reader that assumes a column COUNT, or
that reads by position, must be updated.

---

## 3. A polar group is NAMED, and your files are renamed for you

`GROUPS` takes one named input per group, and the product file carries that
name instead of `_g01`.

```
before   P0001-M150AL+000BE+000J+sweep_g01.csv
after    P0001-M150AL+000BE+000J+sweep_PUSHER.csv
```

**Your existing products are moved, not orphaned:**

<!-- skip: next -->

```python
from pyflightstream.workspace import rename_group_products

rename_group_products("<workspace root>", {1: "PUSHER", 2: "LIFT_L1"}, dry_run=True)
rename_group_products("<workspace root>", {1: "PUSHER", 2: "LIFT_L1"})
```

- **You supply the mapping** because nothing in a workspace records which group
  `_g03` was. A number you do not give is LEFT ALONE, never renamed on a guess:
  a product renamed to the wrong group is worse than one not renamed at all.
- **Ask what you left out, before you migrate**, which is while you can still
  act on it:

  ```python
  from pyflightstream.workspace import unmapped_group_numbers

  unmapped_group_numbers("<workspace root>", {1: "PUSHER", 2: "LIFT_L1"})
  # {3: [Path('.../P0001-M150_g03.csv')]}
  ```

  A number you forgot is otherwise indistinguishable from a number that was
  never there: you would see the products that moved and conclude you were done.
- **It refuses before it moves anything.** Every product is checked first and
  moved second, so a refusal saying nothing was moved is true of the folder.
  Two numbers you mapped to ONE name are refused too.
- **It archives before it moves, and deletes nothing.** A copy of each file
  lands under `archive/rename-groups-<stamp>/` first and stays there afterwards.
  That is the default; `archive=False` moves without a copy.
- **A destination that already exists is refused**, naming both paths, with
  nothing moved.
- Run it with `dry_run=True` first. It reports what would move and moves
  nothing, and those records name no archive, because none was written.

---

## 4. `_sections` says which iteration and which azimuth

The `POINT` column carried the polar's NAME, which the file name already
carries. It is replaced by `ITERATION` and `AZIMUTH`, the two things that
actually vary down the table.

`AZIMUTH` reads `NA` on a run with no rotor, and never `0`: zero is a real
azimuth a rotor row can hold.

---

## 5. A rotor now carries its INSTALLATION VECTOR

`axis` on a rotor block accepts a three-component vector as well as a letter:

```toml
[PUSHER]
kind  = "rotor"
axis  = [0.0, 0.199, 0.980]   # a shaft with pitch and toe already in the mesh
```

**Your existing references are untouched.** A letter keeps its exact meaning --
`Z` IS `(0, 0, 1)` -- and a rotor stating a letter takes the same code path it
always did, so the script it emits is unchanged.

Two things change for a rotor that states a VECTOR:

- every frame the package builds for it is built on the shaft rather than on
  the geometry's axes;
- the blade datum is refused by ANGLE when it lies within five degrees of the
  shaft. The old check compared two strings, so it caught `axis = Z, zero = Z`
  and was blind to a shaft one degree from its datum, which reports an azimuth
  that locates nothing.

**Not yet validated against a licensed run.** No run with pitch and toe exists
yet, so what is proved is that the letter path is unchanged and that a vector
spelling of a letter gives the same script. Whether the frames a TILTED shaft
produces match the hardware is owed to one licensed run at a known pitch.

---

## 6. The one thing `post` cannot give you

`submitted_by` in the provenance is a RUN-time fact. Nobody recorded it for the
simulations you already have, it cannot be recovered, and none is invented: for
those runs the field reads `NA`. It is filled from your next run onward.

---

## 7. New, and optional: three pproc tables

They ship together. A pproc that mentions none of them loads exactly as before.

```toml
[phase_locked]
min_revolutions      = 5
last_revolutions_avg = 2

[equations.CTX]
expression   = "CT * 2"
meshes_alias = "PUSHER"
frame        = "BODY"

[glossary]
CTX = "my own coefficient"
```

- `phase_locked` is generated when the matrix specifies AT LEAST
  `min_revolutions`. **Not reaching it does not refuse the polar**; it only
  means no phase-locked reduction.
- An equation points at an ALIAS and never at a mesh family, so every
  coefficient you derive carries `_<alias>`.
- `pyflightstream.post.write_pproc_guides` writes `VARIABLES.md`
  and `WRITING-EQUATIONS.md` into your pproc folder, generated from the code so
  they cannot go stale.

---

## 8. Everything else that moved

- **A rotor table** carries `J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW` per rotor,
  each suffixed with the rotor's alias.

  **ON A STATIC POINT EVERY ONE OF THEM READS `NA` EXCEPT `J`.** This page said
  `CT` and `CQ` were still written; a V&V round proved that false at every
  caller and the change log was corrected without this page following. The
  reason is the export rather than the package: it states coefficients
  normalised by the run's own dynamic pressure, which is zero at rest, so a
  hovering rotor's real thrust has been divided away before any of this is
  computed. `J` is a real `0.00000` -- at rest with a turning rotor the advance
  ratio genuinely is zero.
- **The rotor table names its alias on its first line**, alone, so a script
  that has loaded the file still knows which group it holds.
## The averaging window moves to the matrix row

**State it once, on the row, beside the clock that gives it a length.**

| column | run type | unit |
|---|---|---|
| `last_revs_avg` | `unsteady_rotor` | last revolutions, **accepts a float** |
| `last_iters_avg` | `unsteady` | last iterations |

It is the window the POLAR, the time average and `per_blade` all use. On a row
turning several rotors, `last_revs_avg` is a COUNT of revolutions: each rotor
converts it with its own revolution length, so a lifter and a pusher get
different spans from the same key and neither has the other's turn imposed on
it.

**`WINDOW_STEPS`, `WINDOW_REVOLUTIONS` and `WINDOW_DEGREES` are deprecated**,
due for removal at 0.26.0. A row stating one still binds and now WARNS, naming
the replacement. Degrees are revolutions over 360, so `WINDOW_DEGREES = 90` is
`last_revs_avg = 0.25`. A row stating both an old key and a new one gets the new
one.

## An unsteady point's POLAR changes shape, and so does its folder

**This is the migration fact most likely to surprise you**, so it is stated
before the reasoning.

An unsteady simulation used to write one polar per pproc group under
`polars/<sim>_<sweep>_<group>.csv`, plus the super file and, where asked, the
fixed-width `.dat`. It now writes **one table per simulation** instead:

    polars/<sim>_<sweep>_unsteady.csv

one row per point, and **the group polars, the super file and the `.dat` are not
written for that point**. Nothing is silently dropped: a simulation whose points
exported no plots records a skip naming the file.

**Its columns are the plot variables under the names the export prints them**,
not the twenty-four fixed coefficients of the steady polar. Nothing in this
package knows which plot label carries which coefficient, and a label the
package invented would not fail loudly -- it would write `NA` down a whole
column. A dictionary that maps the names is 0.24.0 scope.

**Why it changed:** asked whether the native coefficient export writes the time
average or the last time step, the owner answered the LAST TIME STEP. On an
oscillating rotor that is one instant of a cycle. The native export still ships,
as a health check, and the run assessor judges an unsteady point from the plots
history.

## Not in this release

Listed because an absence you discover is worse than one you are told:

- the super file in the fixed-width `legacy_polar` format,
- `per_blade` as one row per blade with the azimuths in columns,
- the `[phase_locked]` pproc table,
- the `[equations]` table and its `[glossary]`,
- the generated `VARIABLES.md` and `WRITING-EQUATIONS.md`.

**0.23.0 adds no pproc table at all**, so a pproc written for 0.22.0 binds
unchanged. Those three table names are refused BY NAME rather than accepted and
ignored: a refusal says the feature is not here, where silent acceptance would
let you write the table and get nothing back.
