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

## `time_average`

One average of the whole point over one window. It is what a POLAR row of an
unsteady point is built from.

**One window per point.** Not one per rotor, because a point has one history.

---

## `per_blade`

!!! warning "NOT YET THE CODE as of 0.23.0 (marked 2026-09-18)"
    This section is the definition 0.24.0 implements. What 0.23.0 writes is
    the ONE shared window below and ONE ROW for it:
    `probes/<point>_per_blade.csv` (or `..._per_blade_<ALIAS>.csv`) carries no
    row per blade and no start and end azimuth columns. The definition stands;
    the code is behind it.

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

---

## `phase_locked`

!!! warning "NOT YET THE CODE as of 0.23.0 (marked 2026-09-18)"
    This section is the definition 0.24.0 implements. What 0.23.0 writes under
    this name is the averaging window cut into consecutive blade passages, one
    row per passage. It does not average across revolutions at a fixed azimuth
    and it is not tabulated from 0 to 360. The definition stands; the code is
    behind it.

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

### When it is generated

!!! warning "NOT YET THE CODE as of 0.23.0 (marked 2026-09-18)"
    This section is the definition 0.24.0 implements. **Do not write the
    `[phase_locked]` table in a 0.23.0 pproc: it is refused by name and the
    artifact does not load.** In 0.23.0 no minimum is read, so nothing gates
    the reduction on the revolutions a row turns. The definition stands; the
    code is behind it.

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
Absent is not zero.

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

**Why the native export is not the source.** It states the **last time step
only**, which on an oscillating rotor is one instant of a cycle. It still ships,
as a health check.

**Why the columns are not renamed.** Nothing in this package knows which plot
label carries which coefficient, and a label invented by the package does not
fail loudly -- it writes `NA` down a whole column. A dictionary from plot names to
a downstream tool's names is **0.24.0** scope; it lives in the pproc, and
undeclared, the names pass through exactly as printed.

---

## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, one table per rotor, every column suffixed
with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

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
