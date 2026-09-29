# Field operations: building a custom free stream

A row's `FREESTREAM` key names a file of the workspace's `inputs/freestreams/`
by its stem, and the run writes it as `SET_FREESTREAM CUSTOM` (see
[custom-field units and coverage](custom-field-units.md)). The field such a
file holds is often built out of other fields: a survey plane sampled by one
run, mirrored or moved to where another body sits, averaged over the steps of
an unsteady run, or corrected by a second survey. `pyfs-workspace field` does
these four operations and writes the result where a row can name it.

## The file forms

The extension of a field file states its form, as the matrix binding reads it:

| extension | form | content |
|---|---|---|
| `.txt` | STRUCTURED | a first line `Npts Mpts`, then Npts x Mpts rows |
| `.dat` | UNSTRUCTURED | one row per point, no header |

Every row is `x y z vx vy vz`. A custom free stream lies in ONE plane of
constant x of the global frame and states at least two distinct y and two
distinct z. The post's per-point field files (`fields/<point>_field_NN.inflow.dat`,
from a pproc `[[probes]]` entry with `reusable_inflow = true`, see
[sampled fields](sampled-fields.md)) are UNSTRUCTURED files of this form.

**Units.** Metres and metres per second in the global frame, read and written
as the files state them. Nothing is converted, rotated or interpolated. The
row's `FREESTREAM_UNITS` states the units of the result as it states those of
any file of the folder.

## The four operations

| command | result |
|---|---|
| `field mirror FIELD --plane y` | through the plane y = 0: each row `x y z vx vy vz` becomes `x -y z vx -vy vz` (`--plane x` and `--plane z` likewise) |
| `field move FIELD --source-point X Y Z --target-point X Y Z` | every position `p` becomes `(p - source) + target`, so the source point lands exactly on the target; the velocities are unchanged |
| `field subtract TOTAL OTHER --reference VX VY VZ` | `TOTAL - (OTHER - reference)`, point by point |
| `field time-mean FILES... [--last K]` | the mean of per-step fields of one unsteady run |

**mirror** keeps the row order, so a STRUCTURED grid keeps its header and its
neighbours.

**subtract** matches the two fields BY POSITION, not by row order, so a grid
mirrored or moved onto the other's points is matched; the result keeps
`TOTAL`'s positions and order. Two fields that are not one grid (a different
number of points, or a point of either with no point of the other within
`--tolerance`, 1e-6 m by default along each axis) are refused, naming both
files and the first point without a partner. `--reference` is a uniform
velocity, the free stream `OTHER` was solved in: `OTHER - reference` is then
the velocity `OTHER`'s body induces, and the result is `TOTAL` with that
induced velocity removed. `--reference` is REQUIRED, because a reference left
out would remove `OTHER`'s free stream from `TOTAL` as well. State `0 0 0`
only where `OTHER` is already induced-only (a field with its free stream
taken out): the result is then the plain difference `TOTAL - OTHER`.

**time-mean** reads the step from each file name
(`<point>_field_NN_step_<N>.inflow.dat`); a pattern such as
`fields/P1_field_01_step_*.inflow.dat` is expanded by the command itself, so it
works in a console that expands none. The steps must be equally spaced (the
mean of samples at unequal intervals is not the time mean over their span) and
every step must hold the same points in the same order. `--last K` keeps the
last K steps given.

## Preview, apply, overwrite

Every operation previews by default: it reads the inputs, computes the field,
checks that the free-stream reader would accept it, and says what it would
write. Only `--apply` writes. `--out STEM` names the result;
the form gives the extension:

```text
inputs/freestreams/<stem>.dat            (or .txt for a STRUCTURED result)
inputs/freestreams/<stem>.provenance.json
```

The provenance record states the operation, its parameters, every input file
with its sha256, the sha256 of the file written, and the units. An existing
file or record is replaced only with `--overwrite`, and a stem the folder
already holds in the other form is refused, since one stem names one file.
`--workspace` names the campaign workspace (the current directory by
default), as every command that names a workspace spells it. A refusal is
printed on stderr with exit status 2 and writes nothing.

## Per-step fields of an unsteady row

On an unsteady row, including one with no rotor, a pproc `[[probes]]` entry
with `reusable_inflow = true` becomes one fluid plot per point and velocity
component, which the solver records at every time step. The post then writes
one `fields/<point>_field_NN_step_<N>.inflow.dat` per step. The per-step
export window (`EXPORT_UNSTEADY_AFTER_ITER`) is not needed for them and does
not change them: the fluid plots sample every step of the run, and
`field time-mean --last K` chooses the steps averaged.

```toml title="inputs/pproc/p010.toml"
[groups]
"1" = "all"

[[probes]]
frame = "REFERENCE"
reusable_inflow = true
rectangles = [{origin = [2.0, -1.0, -1.0], along_u = [2.0, 1.0, -1.0], along_v = [2.0, -1.0, 1.0], points_u = 21, points_v = 21}]
```

## A worked example

A survey plane at x = 2 m is sampled beside a body in an unsteady run. The
field is wanted at a second position, mirrored through y = 0 and with its
origin point (2, -3, 0) m moved to (0, 0, 0), and with the velocity a second
body induces removed. The second body's own survey, on the same grid about
(0, 0, 0), was solved in a free stream of (40, 0, 0) m/s.

```text
pyfs-workspace field time-mean "post/m1/fields/P1_field_01_step_*.inflow.dat" --last 72 --out p1_mean --apply
pyfs-workspace field mirror inputs/freestreams/p1_mean.dat --plane y --out p1_mirrored --apply
pyfs-workspace field move inputs/freestreams/p1_mirrored.dat --source-point 2 3 0 --target-point 0 0 0 --out p1_moved --apply
pyfs-workspace field subtract inputs/freestreams/p1_moved.dat post/m1/fields/P2_field_01.inflow.dat --reference 40 0 0 --out inflow_a --apply
```

The mirror carries the point (2, -3, 0) to (2, 3, 0), which is why the move
starts there. A row then states `FREESTREAM: inflow_a`. Each intermediate file
carries its own provenance record, so the chain can be read back from the last
one to the first.

The same operations are functions of `pyflightstream.workspace.fields`,
whose parameters (the plane, the two points, the reference) are keyword-only:

```python
from pyflightstream.workspace.fields import Field, mirror_field, move_field, subtract_fields

survey = Field(
    form="UNSTRUCTURED",
    rows=(
        (2.0, -1.0, 0.5, 41.0, 0.5, 0.0),
        (2.0, 1.0, 0.5, 40.0, -0.5, 0.0),
        (2.0, -1.0, -0.5, 39.0, 0.0, 1.0),
        (2.0, 1.0, -0.5, 40.5, 0.0, -1.0),
    ),
)
moved = move_field(
    mirror_field(survey, plane="y"), source_point_m=(2.0, 0.0, 0.0), target_point_m=(0.0, 0.0, 0.0)
)
body = Field(form="UNSTRUCTURED", rows=tuple((*r[:3], 40.25, 0.0, 0.0) for r in moved.rows))
corrected = subtract_fields(moved, body, reference_m_s=(40.0, 0.0, 0.0))
assert corrected.rows[0] == (0.0, 1.0, 0.5, 40.75, -0.5, 0.0)
```

## What it does not do

It does not interpolate: a field is subtracted or averaged only over the
points both inputs hold. It does not replace points that lie inside a body,
where a survey carries no flow; the field is written as sampled. It does not
install anything into a row: a row names the result by its stem.
