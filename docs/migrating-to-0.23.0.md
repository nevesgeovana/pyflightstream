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
  each suffixed with the rotor's alias. `ETA` and `ETAW` read `NA` on a static
  point, where they are `0/0`; `CT` and `CQ` are still written.
- **The rotor table names its alias on its first line**, alone, so a script
  that has loaded the file still knows which group it holds.
- **`per_blade` is ONE window**, one row per blade, with each blade's start and
  end azimuth in columns. It averaged each blade over its own passage before,
  which mixed a real azimuthal difference with a difference in when each blade
  was sampled.
- **An unsteady POLAR and rotor table are the plots averaged** over the same
  window `per_blade` uses.
- **The native coefficient export stays as a health check.** It is only the
  last iteration, which on an oscillating rotor is one instant of a cycle, so
  the POLAR no longer reads it and the run assessor judges from the plots
  history instead.
- **The super file takes a format**: `csv` as before, or `legacy_polar`. Both
  carry the same columns.
