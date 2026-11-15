# Post-processing outputs

<a id="pproc-outputs"></a>

`pyfs-matrix post` writes the files below to `post/<matrix>/`, one folder per kind of
product. Every table opens with the same [run block](../definitions/the-run-block.md#the-run-block),
so a file names its condition, and
[`products.json`](products-json.md) states the unit and the frame of every column once.
Steady, unsteady and unsteady-rotor points write the same files under the same names: a
steady value and a window average are told apart by `RUN_TYPE` in the run block, never by
the name.

In the table, `X` marks what a pproc can ask for and `[X]` the default. A file is written
**per point** when it holds one point of a polar, **per family** when its rows or files
are one per family of the geometry, and **per polar** when one file holds every point of
the polar.

## The outputs

| File | Folder | Description | Per point | Per family | Per polar |
| --- | --- | --- | --- | --- | --- |
| [FAM-DIM](fam-dim.md) | `polars/` | dimensional forces and moments per family, solver frame | | | [X] |
| [FAM-ACOEF](fam-acoef.md) | `polars/` | airframe coefficients per family, frames W, S, B, R&lt;id&gt; | | | [X] |
| [FAM-RCOEF](fam-rcoef.md) | `polars/` | rotor families: T, Q, P and propeller coefficients | | | [X] |
| [group files](group-files.md) | `polars/` | a group (declared, ROTOR, AIRFRAME, TOTAL) | | | [X] |
| [plots history](time-history.md) | `time_history/` | one row per step, unsteady | [X] | | |
| [phase_locked](phase-locked.md) | `reductions/` | one row per azimuth, per rotor | [X] | | |
| [per_revolution](per-revolution.md) | `reductions/` | one row per complete revolution, drift, per rotor | [X] | | |
| [harmonics](harmonics.md) | `reductions/` | per-station harmonics, last revolution | [X] | | |
| [disc maps](disc-maps.md) | `reductions/` | disc maps of a rotor | [X] | | |
| [probes](probes.md) | `probes/` | probe tables only | [X] | | |
| [series](series.md) | `series/` | the per-step exports of a point: loads, sections, probes | [X] | | |
| [far field](farfield.md) | `farfield/` | Trefftz-plane, balance and rotor-section tables | [X] | | |
| [sections](sections.md) | `sections/` | sectional loads, rows by FAMILY and FAMILY_ID | [X] | X | |
| [Cp](cp.md) | `sections/` | surface Cp, rows by FAMILY and FAMILY_ID | [X] | X | |
| [sampled field](fields.md) | `fields/` | VTK and Tecplot of the field at the probe positions | [X] | | |
| [inflow](inflow.md) | `fields/` | reusable inflow for another run | [X] | | |
| [averaged surface](averaged-surface.md) | `surfaces/` | window-averaged surface, Tecplot and VTK | [X] | | |
| [streamlines](streamlines.md) | `streamlines/` | off-body streamlines, VTK | [X] | | |
| [settings](settings.md) | `settings/` | solver-settings codes and codebook of the matrix | | | [X] |
| [products.json](products-json.md) | root | the tree, and the units and frames of every column | | | [X] |

For sections and Cp the pproc may ask per point, per family or both with
`[sections] split`; never per polar. The files in a folder that no longer belongs to the
tree are named in [the migration record](../upgrading.md#0580-post-tree).

## The tree

```text
post/<matrix>/
  polars/        FAM-DIM-P<POL>.csv  FAM-ACOEF-P<POL>.csv  FAM-RCOEF-P<POL>.csv
                 P<POL>-<GROUP>-DIM.csv  P<POL>-<GROUP>-ACOEF.csv  P<POL>-<GROUP>-RCOEF.csv
  time_history/  <point>_plots.csv
  reductions/    <point>_phase_locked[_<ALIAS>].csv  <point>_per_revolution[_<ALIAS>].csv
                 <point>_harmonics.csv  <point>_disc_<ROTOR>_<QUANTITY>.csv
  probes/        <point>_probes.csv  <point>_probes_history.csv
  sections/      <point>_sections.csv  <point>_cp.csv  (or <point>_FAM-<FAMILY>_sections.csv)
  series/        <point>_loads_series.csv  <point>_sections_series.csv  <point>_probes_series.csv
  farfield/      <group>_trefftz.csv  <group>_ledgers.csv  <group>_rotor_sections_<ROTOR>.csv
  fields/  surfaces/  streamlines/  settings/  provenance/
  products.json  post.log  post.log.json
```

`<POL>` is the matrix row's polar as the matrix writes it. A polar file holds every point
of the polar; the point's condition is in its run block, so no sweep or Mach token is in
the name.

<a id="joining-polars"></a>

## Joining polars

Each polar's `TOTAL` group files are complete: every point of the polar, the run block
first. Several polars share the run block's columns, so they join by stacking their rows.
With the standard library:

```python
import csv
from pathlib import Path

def join(files):
    """Stack the rows of several files that share one header."""
    header, rows = None, []
    for name in files:
        with open(name, newline="", encoding="utf-8") as stream:
            table = list(csv.reader(stream))
        if header is None:
            header = table[0]
        elif table[0] != header:
            raise ValueError(f"{name} has another header than the first file")
        rows.extend(table[1:])
    return header, rows

header, rows = join(sorted(Path("post/study/polars").glob("P*-TOTAL-ACOEF.csv")))
```

A file with another header (a polar with a different rotor count, say) is refused by name
instead of joined into a table whose columns mean different things. The key of a row is
`POL`, `POINT_ID` and, in a family file, `FAMILY_ID`.

## Definitions

The definitions of record are the pages of the post-processing definitions. The products
use these:

- Frames and signs: [axes and signs](../definitions/axes-and-signs.md#axes-and-signs), with
  the wind, stability, body and rotor frames and the sign of every coefficient.
- The run block: [the run block](../definitions/the-run-block.md#the-run-block), with the
  advance ratio and speed of the clock rotor.
- Coefficients: [airframe coefficients](../definitions/airframe-coefficients.md#airframe-coefficients)
  and [rotor coefficients](../definitions/rotor-coefficients.md#rotor-coefficients).
- Tables: [the sections table](../definitions/the-sections-table-and-which-row-is-which.md#the-sections-table-and-which-row-is-which),
  [the probes table](../definitions/the-probes-table.md#the-probes-table),
  [the reductions of an unsteady point](../definitions/the-reductions-of-an-unsteady-point.md#the-reductions-of-an-unsteady-point)
  and [the averaging window](../definitions/the-averaging-window.md#the-averaging-window).
- Derived polars: [the derived polars](../definitions/polar-derivatives.md#polar-derivatives).
- The missing value: [the token](../definitions/the-token-for-a-value-that-does-not-exist.md#the-token-for-a-value-that-does-not-exist).

The index of every definition is [Post-processing definitions](../post-processing-definitions.md).
