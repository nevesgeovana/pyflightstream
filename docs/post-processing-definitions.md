# Post-processing definitions

**This page is the definition of record for every post-processing product this
package writes.** It exists because the definitions kept being re-explained in
conversation and re-derived from code, and a definition derived from code makes
the code its own specification. Where this page and the code disagree, **this
page is right and the code is a defect**.

Every definition below is the product owner's, in her own words, with the date
she gave it. Nothing here was inferred from an implementation.

!!! note "For whoever maintains this package"
    Read this page before changing any reduction, any averaging window, or any
    product's column set. A reduction whose meaning you reconstructed from
    `workflows.py` is a reduction you are about to get subtly wrong: three of
    the definitions below were implemented as a declared field with no caller,
    which reads exactly like a finished feature.

## Contents

- [The vocabulary](#the-vocabulary)
- [What every product states](#what-every-product-states)
- [The axes of a steady polar](#the-axes-of-a-steady-polar)
- [The sections table, and which row is which](#the-sections-table-and-which-row-is-which)
- [`time_average`](#time_average)
- [`per_blade`](#per_blade)
- [`phase_locked`](#phase_locked)
- [The averaging window](#the-averaging-window)
- [The unsteady POLAR](#the-unsteady-polar)
- [Rotor coefficients](#rotor-coefficients)
- [What the package does NOT judge](#what-the-package-does-not-judge)
- [The token for a value that does not exist](#the-token-for-a-value-that-does-not-exist)

---

## The vocabulary

| term | meaning |
|---|---|
| **revolution** | one full turn of a rotor, `60 / rpm` seconds, `60 / (rpm * dt)` solver steps |
| **blade passage** | one revolution divided by the blade count |
| **azimuthal position** | where a blade is in its turn, 0 to 360 degrees |
| **window** | an inclusive, 1-based range of solver steps that a reduction averages over |
| **SMRP** | a rotor's own static moment reference point, `<ALIAS>_SMRP` |
| **MRP** | the global moment reference point of the aircraft |
| **alias** | the name of a rotor, and of the integration group built from its families |

---

## What every product states

Every table the post stage composes states the condition it is a table OF, in
one block, in this order:

<!-- condition-columns: ALPHA, BETA, MACH, RE, VINF, VREF, ALT, RHO, TEMP, MU, J, SREF, CREF, BREF -->

| column | unit | what it is |
|---|---|---|
| `ALPHA`, `BETA` | deg | the angles the solver REPORTS it ran at, as the row wrote them |
| `MACH` | - | the Mach number of THAT point |
| `RE` | millions | the Reynolds number the solver reports |
| `VINF` | m/s | the free-stream velocity the solver reports |
| `VREF` | m/s | the solver's REFERENCE velocity, which is what it normalises a coefficient by |
| `ALT` | ft | the altitude the row states; `NA` where it states none |
| `RHO` | kg/m3 | the air density the run resolved for that point |
| `TEMP` | K | the air temperature the run resolved for that point |
| `MU` | Pa s | the dynamic viscosity, written in scientific notation |
| `J` | - | the advance ratio the row REQUESTED; `NA` on a row that turns no rotor |
| `SREF`, `CREF`, `BREF` | m2, m, m | the reference area, chord and span |

**Why the block is this long.** A coefficient is a force divided by
`1/2 rho V^2 S`. A file that states the coefficient and the area, and neither the
density nor the velocity it was divided by, is a number nobody can take back to a
force or compare with another campaign. `ALT` does not stand in for the density:
a row may pin the density directly, and then the altitude says nothing about it.

**Which velocity normalised what.** The solver normalises by `VREF`. The steady
polar's twenty-four coefficients are the solver's own, so they are by `VREF`. The
plots table, every reduction of it and the unsteady polar are rescaled to the
free stream by `(VREF / VINF)^2`, so they are by `VINF`. The rotor table takes
the export back to Newtons with `VREF`, which undoes the solver's own division,
and its coefficients are by `rho n^2 D^4` and carry no velocity at all. With both
velocities in the row, a reader can tell which one a number used; the post stage
also WARNS, naming the point, when the two differ.

**`SREF` and `CREF` are checked against the export.** The solver divides by the
area and the length of the project file it opened, and the loads export prints
both. The package sets neither: it states the reference artifact's. Where the
two differ by more than the export's printed precision, the simulation gets NO
product and `products.json` names both numbers, because a table stating one
area beside coefficients divided by another is wrong by a constant factor that
nothing in it shows.

The steady polar already carries `ALPHA`, `BETA`, `MACH` and `RE` among its
twenty-four, so it states the rest of the block beside them. The plots table
`probes/<point>_plots.csv` states NO condition, on purpose: it is the export's own
header, and the reductions read every column of it back as a plotted quantity.

---

## The axes of a steady polar

The loads export states ONE force and ONE moment per surface, in the
geometry's own frame: **x aft, y right, z up**. Every axis column of a steady
polar row is that pair, summed over the group's surfaces and turned.

| columns | axes | how |
|---|---|---|
| `CDB, CYB, CLB, CRB, CMB, CNB` | body: forward, right, down | half a turn about y. `CDB` IS the export's `Cx` and `CLB` its `Cz` |
| `CDS ... CNS` | stability | body axes turned by `-alpha_s` about y |
| `CDW ... CNW` | wind | stability axes turned by `beta_w` about z |

Drag opposes +x and lift opposes +z of each system; the side force keeps its
sign. The moment turns as ONE vector in one length and only then is
normalised: `CR` and `CN` by the span, `CM` by the chord. Under sideslip that
is what moves pitch into roll by the ratio of chord to span.

**The angles that turn the axes are read off the velocity the solver flies.**
The solver turns sideslip about the body z axis first and incidence second,
so it flies `V (cos a cos b, cos a sin b, sin a)`, and
`alpha_s = atan2(w, u)`, `beta_w = asin(v / V)`. They equal the written
`ALPHA` and `BETA` whenever either is zero and differ at second order
otherwise: at `ALPHA 4, BETA 2` they are 4.0024 and 1.9951 degrees. The
`ALPHA` and `BETA` columns stay what the row wrote.

**`CDW` is the drag the solver integrates.** The wind-axis drag of the
export's own vector equals its `CDi + CDo`, which the recorded exports
confirm to their printed precision, under sideslip too. `CD0` and `CDI` are
those two integrals as the solver states them.

**`CLW` is NOT the solver's `CL`.** The `CL` an export prints sits about 0.13
per cent above the wind-axis lift of the vector printed beside it; the cause
is not known. The polar states the vector's, so that every column of a row
comes from one source and `CDB`, `CLB` agree with the `Cx`, `Cz` of the
export. A table written before 0.24.0 used the solver's `CL`, so its `CLS`
and `CLW` are higher by that much.

---

## The sections table, and which row is which

`sections/<point>_sections.csv` is ONE export of the solver holding EVERY
distribution the pproc declares, the wing in `XZ` and each blade in its own
frame, one after another with no marker between them. Each row leads with:

| column | what it is |
|---|---|
| `STEP` | on an unsteady point, the run's last TIME STEP, from the run record: the export is written when the march ends, and its own header counts the solver's inner iterations, not steps. On a steady point, the solver iteration the export states. One name across every table |
| `FAMILY` | the geometry families of the row's distribution, joined by `+` |
| `PLANE` | the cutting plane of that distribution |
| `ROTOR` | the rotor whose blades those families are; `NA` for a surface no rotor owns |
| `AZIMUTH` | where BLADE ONE OF THAT ROTOR is at `STEP`, in degrees, wrapped to one turn; `NA` without a rotor |

`AZIMUTH = (blade1.azimuth_deg + sense * STEP * 360 / steps_per_revolution) mod 360`,
with the datum, the sense of rotation (the sign of the rotor's speed) and the
steps per revolution all taken from THAT rotor. Two rotors at two speeds have
two azimuths at one step, and a wing has none.

The run records which distribution is which, because the script states
surfaces by index and nothing at post can name them. A run recorded before
0.24.0 states `NA` in all four, and so does a record whose blocks do not add
up to the rows the export holds: a row given its neighbour's family is worse
than a row given none.

**It is one instant.** On an unsteady point this table is the distribution at
`STEP`, not an average over the window, and its `products.json` entry says
`"kind": "instant"`. The history is `series/<point>_sections_series.csv`,
which carries the same identity on every row.

---

## `time_average`

One average of the whole point over one window. It is what a POLAR row of an
unsteady point is built from.

**One window per point.** Not one per rotor, because a point has one history.

---

## `per_blade`

!!! note "The code since 0.24.0"
    0.23.0 wrote the ONE shared window below and ONE ROW for it, the time
    average's shape under the per-blade name. Since 0.24.0
    `probes/<point>_per_blade_<ALIAS>.csv` is one row per blade with its start
    and end azimuth, as defined here.

> "O per-blade vai seguir a media olhando para a variável que fala de export
> after x revs." -- 2026-09-17
>
> "faz sentido sempre olhar a ultima janela convergida" -- 2026-09-17
>
> "Nao importa que as blades estão em posições azimutais diferentes, nos podemos
> ter uma coluna que mostra a posição azimutal de inicio e fim de cada para a
> mesma janela" -- 2026-09-17

**ONE window, shared by every blade.** One row per blade, and each row carries
the **start and end azimuth of that blade** over that one shared window.

**Why one window and not one per blade.** Averaging each blade over its own
passage puts each blade in a different part of the history, so any difference
between two blades mixes a real azimuthal difference with a difference in WHEN
each was sampled -- and nothing in the file says which is which. With one window,
the azimuth columns carry the difference explicitly and the reader can see it.

**The window is the same one the unsteady plots use.** Her words, 2026-09-18:
*"a media per_blade usa a mesma info de last_revs e last_iters que o unsteady
plots"* -- so it comes from `LAST_REVS_AVG` or `LAST_ITERS_AVG` on the matrix
row, and not from a derivation of its own. One window per point, stated once,
shared by the POLAR and by this table.

Averaging from step one mixes the transient with the answer.

**The rows.** Each row leads with `REDUCTION`, `ROTOR`, `BLADE`, `FAMILY`, the
window (`FIRST_STEP`, `LAST_STEP`, `STEPS`), `AZIMUTH_START`, `AZIMUTH_END`,
then the condition block and the moment point.

- **A blade's columns are the plots named for its family.** A plot is
  `<parameter>_<group>` and a group cut per blade is named for the blade's
  family, so blade one's are `CL_MRP_Blade1`, `FX_LOCAL_Blade1`. The row carries
  them with the family removed, `CL_MRP`, `FX_LOCAL`, so two blades line up
  under one heading. A pproc gets them with `families = "each"` or
  `frame = "LOCAL_AXIS"` over the rotor.
- **The azimuths are where that blade IS at the window's first and last step**,
  by the formula of the sections table: blade one's datum, plus the blade's
  position times `360 / blades`, plus the rotor's sense times the step times
  `360 / steps_per_revolution`, wrapped. `blades` is the ROTOR's count, so a
  periodic sector carrying two blades of four spaces them a quarter turn apart.
  Without the rotor's clock they read `NA`; the averages are written all the same.
- **Which families are a rotor's blades** is the `families_blades` of its block
  in the reference artifact; a run made since 0.24.0 also records them. A row
  that states its rotor with flat keys and cites no block has no per-blade
  table, and `products.json` says why.

---

## `phase_locked`

!!! note "The code since 0.24.0, where the pproc declares `[phase_locked]`"
    0.23.0 wrote the averaging window cut into consecutive blade passages, one
    row per passage, under this name. Since 0.24.0 a pproc that declares the
    `[phase_locked]` table gets the table defined here. **A pproc that does not
    declare it still gets the passage series**, so a workspace that never asked
    for the table reads the file it has always read.

> "a ideia do phase-locked é olhar a mesma posição azimutal de varias voltas e
> voltar um resultado que traz a media vs posição azimutal. Dessa forma, seria
> 5*iter linhas se tiver 5 blades." -- 2026-09-17
>
> "Phase_locked é quando você pega por exemplo três revoluções e faz a media para
> cada ponto azimutal, ou seja, cada ponto azimutal vai ter 3 datapoints para a
> media. Depois disso, você escreve o resultado final tabelado por posição
> azimutal de 0 a 360. Você faz isso para cada blade isoladamente usando o SMRP,
> e depois faz isso para cada alias usando o MRP global. Tudo num mesmo arquivo
> com `_{alias/blade_name}_{SMRP ou MRP}`." -- 2026-09-18

**It is an average ACROSS revolutions at a FIXED azimuth.** It is not a series
of consecutive passages, and that distinction is the whole content of this
section.

The operation, step by step:

1. Take the last `last_revolutions_avg` revolutions.
2. For **each azimuthal position**, average the samples at that position across
   those revolutions. With three revolutions, every azimuthal position has
   **three datapoints** entering its mean.
3. Write the result **tabulated by azimuthal position, 0 to 360**.
4. Do this **for each blade on its own, about that rotor's `SMRP`**.
5. Then do it **for each alias, about the global `MRP`**.
6. Put all of it in **one file**, with columns suffixed
   `_{alias or blade_name}_{SMRP or MRP}`.

**The row of this product is an azimuthal position.** Not a passage, not a
revolution, not a blade.

**How the file carries it.** `probes/<point>_phase_locked[_<ALIAS>].csv` leads
with `REDUCTION`, `ROTOR`, `AZIMUTH`, `STEP`, `REVOLUTIONS`, the steps the
revolutions span (`FIRST_STEP`, `LAST_STEP`, `STEPS`), the condition block and
the moment point, then the plotted columns under the names the export prints.

- **The rows are the azimuthal positions of the rotor's LAST revolution**, one
  per solver step of it, sorted from 0 towards 360. `AZIMUTH` is where BLADE ONE
  is, by the formula of [the sections table](#the-sections-table-and-which-row-is-which),
  and `STEP` is the step of the last revolution that azimuth falls on.
- **A blade's column is tabulated by THAT blade's azimuth.** A column ending in
  a blade family of the rotor is sampled where that blade, which sits its
  position times `360 / blades` after blade one, is at the row's azimuth, so two
  blades line up azimuth for azimuth. Every other column, a rotor's total or the
  aircraft's, is tabulated by blade one's azimuth.
- **The suffix is the plot's own.** A plot is `<parameter>_<group>` and the pproc
  names the group, so `_{alias or blade_name}_{SMRP or MRP}` is what a group
  named `PUSHER_SMRP` or cut per blade prints; the package renames nothing.
- **`REVOLUTIONS` is how many samples entered the mean**, `last_revolutions_avg`
  exactly when that is a whole number.
- **Between two steps the history is read linearly.** One revolution earlier is
  a whole number of steps earlier only when `steps_per_revolution` is whole, and
  a blade's offset only when it divides by the blade count. Where both hold,
  every sample is a row of the history and nothing is interpolated.
- **Without blade one's datum or the rotor's signed speed no azimuth can be
  stated**, and the table is a named skip: declare the rotor in the reference
  and have the row cite it. A depth under one revolution is a named skip too.

### When it is generated

!!! note "The code since 0.24.0"
    0.23.0 refused the `[phase_locked]` table by name. Since 0.24.0 it binds, and
    `pyfs-matrix post` reads it again from the pproc as it stands, so the gate
    and the depth can be edited with no solver re-run.

> "no arquivo de pproc o usuário fala o número mínimo de revs total e revs usadas
> para media. Se a especificação da matriz bater esse número mínimo, o
> phase_locked é gerado" -- 2026-09-17
>
> "Escreve last_revolutions_avg e lembra que o critério é o min_revolutions.
> Sendo igual ou maior, o phase-locked é gerado" -- 2026-09-17

```toml
[phase_locked]
min_revolutions      = 4.0   # the minimum TOTAL revolutions, for it to exist
last_revolutions_avg = 2.0   # how many revolutions enter each azimuthal mean
```

- The criterion is `min_revolutions`, and **equal or greater generates it**.
- What is compared against it is **what the matrix specification states** -- the
  revolutions the ROW turns -- and not the length of the exported window.
- `last_revolutions_avg` may not exceed `min_revolutions`: a reduction may not
  average over more history than it required in order to exist.

### A short run is SKIPPED, never REFUSED

> "não ter o rev min não recusa a polar, só não gera o phase_locked" -- 2026-09-17

A run that turns fewer revolutions than the minimum loses **this reduction and
nothing else**. Its POLAR, its per-blade table and every other product are
written as usual. Taking a product away from a campaign that already ran is
never the answer to a threshold not being met.

**A pproc that says nothing about `phase_locked` gets one as it always did.**
Absent is not zero: nothing gates it, and it is the passage series it has
always been.

---

## The averaging window

> "o window como argumento opcional, pode ser em numero de iterações ou last
> revs" -- 2026-09-18
>
> "fica na matriz e é input obrigatorio de unsteady_rotor, para unsteady apenas,
> fica last_iters_avg. Eu quero isso na matriz por conversar diretamente com
> setup temporal." -- 2026-09-18

| column | run type | required | unit |
|---|---|---|---|
| `LAST_REVS_AVG` | `unsteady_rotor` | **yes** | last revolutions, **accepts a float** |
| `LAST_ITERS_AVG` | `unsteady` | yes | last iterations |

**The key is written in UPPER CASE, exactly as the table spells it**, like every
other key of a matrix row. `VAR_NAMES_VALUES` keys are matched on the exact
spelling: a lower-case `last_revs_avg` on a workflow row is refused as a key of
no run type, and where that check does not run it is not read at all, so the
window it meant to state is not applied.

**It lives in the MATRIX, not in the pproc**, because it converses directly with
the temporal setup: `DELTA_TIME`, `TIME_ITERATIONS` and `RPM` are all on the same
row. Putting it in the pproc would separate the window from the quantities that
define it.

`WINDOW_STEPS` and `WINDOW_REVOLUTIONS` are **retired** -- they were the same idea
under another name in another place, and two spellings of one idea are how two
published numbers come to disagree.

**How the retirement is carried out, as of 0.23.0.** `WINDOW_STEPS`,
`WINDOW_REVOLUTIONS` and `WINDOW_DEGREES`, all three, are DEPRECATED rather than
refused: a row stating one still binds, with a warning that names the
replacement, until 0.26.0 removes them. What such a row binds is the
`time_average` window and the passages cut from it, and NOT the unsteady POLAR:
a row that states neither `LAST_REVS_AVG` nor `LAST_ITERS_AVG` has its polar
read from the native export.

---

## The unsteady POLAR

> "A POLAR do unsteady sempre vai vir do unsteady plots, alem de ter a media
> temporal" -- 2026-09-18
>
> "despega daqueles nomes da polar, escreve o nome das variaveis como elas vieram
> no unsteady plots" -- 2026-09-18

- The POLAR of an unsteady point is the **plots history, time-averaged** over the
  window, and it does **not** read the native coefficient export.
- **Its columns are the plot variables under the names the export prints them.**
  It does not carry the steady polar's fixed 24 coefficient columns.
- The flight-condition and reference-length columns are still added, because
  those come from the workspace and not from the export.

- **The file is `polars/P<sim>_<name>_uns_avg.csv`**, one per simulation and one
  row per point. Every file under `post/` comes from a sweep, so the name says
  what the file IS, the average of the unsteady history, and carries the `P`
  every per-point product carries. It was `<sim>_<name>_unsteady.csv` in 0.23.0.
- **Each row opens with `FIRST_STEP`, `LAST_STEP`, `STEPS`**, the window THAT
  point was averaged over, so the file says on its own that it is an average and
  over what. The condition block follows, then `XMOM`, `YMOM`, `ZMOM`, because
  the plots carry moments and a moment states nothing without its point.
- **The super file's content is ADDED to this table**, after the plot columns:
  the matrix row's cells, the record's scalars, each rotor's speed, the solver
  flags. The super file is what the polar does not have; for an unsteady point it
  is not a second file.
- **The axis coefficients follow the plot columns**, the eighteen of the steady
  polar in the order `CDW .. CNW`, `CDS .. CNS`, `CDB .. CNB`. Their source is
  the plots of the GLOBAL `MRP` frame: the six components `FX, FY, FZ, MX, MY,
  MZ` of a plot group the pproc declares with `frame = "MRP"`, in Newtons and
  Newton metres, averaged over the row's window like every other column, divided
  by `1/2 RHO VINF^2 SREF` (and by `CREF` for the moments) of THAT row, and
  turned as [the axes of a steady polar](#the-axes-of-a-steady-polar) are. A
  rotor's own frame is never the source: its axes are not the geometry's. With
  several global-frame groups each block takes its group's name, `CLW_TOTAL`,
  `CLW_AIRFRAME`.
- **A pproc that plots those six for no global-frame group gets one added by
  the run**, `MRP_TOTAL`, over every boundary, where the run has an `MRP` frame.
  A pproc that already plots them is left as it is, to the byte. A run made
  before 0.24.0 without such plots has no axes block, and `products.json` says
  so under `polars/<file>#axes`; the block is never a column of `NA`.

**Why the native export is not the source.** It states the **last time step
only**, which on an oscillating rotor is one instant of a cycle. It still ships,
as a health check.

**Why the columns are not renamed.** Nothing in this package knows which plot
label carries which coefficient, and a label invented by the package does not
fail loudly -- it writes `NA` down a whole column.

**The `[names]` dictionary (0.24.0).** A downstream tool may read other names, so
the pproc may state a dictionary, from a plot column AS THE EXPORT PRINTS IT to
the name the reader wants:

```toml
[names]
CL_MRP_TOTAL = "CL_TOTAL"
FX_HUB_PUSHER = "FX_PUSHER"
```

- It renames columns of the unsteady polar and of the averaged reductions
  (`time_average`, and the passage series). The plots table
  `probes/<point>_plots.csv` stays as the export prints it, because it is the
  source the others are read from; the per-blade and azimuthal tables carry
  columns that are no longer the export's own names and are not renamed.
- Undeclared, every name passes through exactly as printed.
- The axes and the `[equations]` read the export's names; the dictionary is
  applied last, to the heading alone.
- **The whole dictionary applies or none of it does.** An entry naming a column
  no plot of the point prints, or giving a column a name the table ALREADY
  carries, leaves every column under the export's name and is said in
  `products.json` (`polars/<file>#names`, `probes/<point>#names`) and as a
  warning. It never becomes a column of `NA`.
- **`CL` is taken.** The unsteady polar carries the native export's last-step
  `CL`, `CDi`, `CDo`, `Cx` and the rest in its setup content, as a health
  check, so a plot column cannot be renamed to one of those; `CL_TOTAL` can.
- Two entries giving one name, or a name that is not one word, are refused when
  the pproc is read.

---

## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, one table per rotor, every column suffixed
with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

### Where an unsteady point's numbers come from

A steady point's row is built from the loads export. **An unsteady point's row
is the average of the PLOTS history over the row's window**, the same window the
unsteady polar and the reductions use, because the loads export of an unsteady
run states the last time step, one instant of a cycle.

- **The history is the rotor's own six components in the global `MRP` frame**,
  `FX, FY, FZ, MX, MY, MZ` in Newtons, over the rotor's own families, general
  and blades. It is found through the pproc: a `[[plots.groups]]` entry with
  `frame = "MRP"` whose families are exactly the rotor's, whatever it is
  called. Where the pproc plots none, the run adds one itself, `ROTOR_<ALIAS>`.
- **A group in a rotor's own frame is never the source.** Its force is stated in
  axes that turn with the rotor and its moment is already about the hub. A
  group that merely shares the alias's name over other families is not one either.
- **A row that states a window never holds an instant.** A point whose history
  does not cover the window, or holds no such columns, is LEFT OUT of the table
  and named in `products.json`, as the unsteady polar beside it does. The
  table's manifest entry states `source` and `window`.

Until 0.24.0 the history was looked for under `FX_<alias>`, a name no run
printed, so every unsteady rotor table silently held the last time step.

### `ETAW`

> "é a rotação por alpha. `[Fx_rotor_axis Fy_rotor_axis Fz_rotor_axis] *
> rotação^T(eixo motor -> eixo corpo airframe) * rotação(alpha) = Fx_W`" and
> "tem beta tambem, olha o standard do AIAA para rotação de eixos" and "sim,
> continua sendo uma eficiencia" -- 2026-09-18

1. Take the full force vector in the rotor frame, `[Fx, Fy, Fz]_rotor`.
2. Carry it to the airframe body frame by the **transpose** of the
   rotor-to-body rotation.
3. Carry it to wind axes by the **AIAA** rotation, with **alpha and beta**.
4. Take the **X** component: `Fx_W`.
5. `ETAW = J * CTW / CP`, where `CTW = Fx_W / (rho n^2 D^4)` -- the wind-axis
   force nondimensionalised exactly as the thrust is, entering the same
   efficiency where `CT` enters. It stays **dimensionless**.

**It reduces to `ETA` when the shaft lies along the stream**, which is what makes
the column readable beside `ETA`. A caller that states no wind-axis force gets
`NA`, never the old cosine: publishing the superseded number under the corrected
name would leave a reader unable to tell which of the two they hold.

**It is two rotations on a vector, never the cosine of a scalar angle.** A cosine
discards the components that are not along the axis, which is exactly what the
rotation chain preserves.

### A static point

Every rotor coefficient reads `NA` on a static point except `J`, which is a real
`0.00000`. The export states coefficients normalised by the run's own dynamic
pressure; at `V = 0` that pressure is zero and the rotor's real thrust has been
divided away before the package sees it. **No rotor coefficient is recoverable
from a static point whatever the package does**, which is also why a hover figure
of merit cannot be offered: it needs a force the run does not state.

---

## What the package does NOT judge

> "a convergencia temporal do unsteady vai ficar a cargo do usuario em analise a
> posteriori" and "O pacote apenas diz se as iterações numericas dentro do ultimo
> passo no tempo convergiu" -- 2026-09-18

The package asserts **one** thing about an unsteady point's convergence: whether
the **numerical iterations within the last time step** converged.

It does **not** judge whether the time history has settled. There is no settle
tolerance, no convergence criterion over the history, and no point is failed for
one. **That judgement is the user's, made afterwards from the history.**

This is stated here rather than left out, because "the package does not check
this" is exactly the kind of thing a reader assumes the other way round.

---

## The token for a value that does not exist

Every product writes **`NA`**. Not a zero, and not a blank.

- **Not a zero**, because zero is a value a row can genuinely have -- an advance
  ratio at rest is exactly zero and is a measurement -- so a zero written for
  "no value" is a number a reader would believe.
- **Not a blank**, because a blank is indistinguishable from a value that went
  missing, from a column that never applied, and from a writer that stopped
  halfway.

The token lives in one place, `pyflightstream._tokens.NOT_APPLICABLE`, below
every layer. **Readers still accept `-`**, which is what files written before
0.23.0 carry.
