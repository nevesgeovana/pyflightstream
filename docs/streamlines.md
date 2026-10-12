# Streamlines from the pproc artifact

A `[streamlines]` table in a pproc artifact traces streamlines on every point of
every row that names the artifact: surface friction lines on the body, and
off-body streamlines seeded along lines or in tubes. The solver traces them
after the solve (after the time march on an unsteady row), the run collects the
solver's export files, and the post writes a VTK polyline file of the off-body
lines that opens beside the surface VTK.

No row key, no run type and no Python are involved: the table is read through
the `PPROC` column like `[sections]` and `[[probes]]`.

## The table

```toml
# inputs/pproc/p030.toml
[streamlines]
surface = true              # surface friction lines, and their export
direction = "downstream"    # every off-body line: "downstream" or "upstream"
length_m = 6.0              # or: unrestricted = true (until it leaves the domain)
vtk = true                  # the package VTK polyline product (default true)

# A seed line: count streamlines, evenly from start to end.
[[streamlines.lines]]
frame = "MRP"               # a frame the run creates, or REFERENCE
start = [-0.5, 1.90, -0.10]
end = [-0.5, 1.90, 0.10]
count = 20
scale = "m"                 # or "rotor_radius", as [[probes]] reads it

# A tube of radial * circular streamlines about one axis of a frame.
[[streamlines.tubes]]
frame = "PROP_SMRP"
axis = "X"
origin = [-0.3, 0.0, 0.0]
radius = 0.9
radial = 4
circular = 12               # 48 streamlines
scale = "rotor_radius"
```

| key | meaning |
|---|---|
| `surface` | Trace the surface friction lines (where the flow separates and attaches) and export them. |
| `direction` | Which way every off-body line propagates; left out, the solver's own default. |
| `length_m` | How far every off-body line propagates, in metres. |
| `unrestricted` | Propagate every off-body line until it leaves the domain. Not together with `length_m`. |
| `vtk` | Write the VTK polyline product of the off-body lines. |
| `[[streamlines.lines]]` | `frame`, `start`, `end` (three numbers each), `count` (two or more), `scale`. |
| `[[streamlines.tubes]]` | `frame`, `axis` (`X`, `Y` or `Z` of that frame), `origin`, `radius`, `radial`, `circular`, `scale`. |

A seed line's vertices are carried into the reference frame by where the run
placed the named frame; a tube is placed in its frame directly.

## What the plan says

`pyfs-matrix plan` states, per point, how many off-body streamlines it traces:
every line's `count` plus every tube's `radial * circular`.

## What a point leaves

| file | written by | content |
|---|---|---|
| `<point>_sls.txt` | the solver | the surface friction lines, as the solver exports them |
| `<point>_slo.txt` | the solver | the off-body lines, one block per streamline |
| `post/<matrix>/streamlines/<point>_off_body.vtk` | the post | one polyline per off-body streamline, with `Mach`, `Cp_ref`, `vtot`, `Cp` and the vector `velocity` per point |

Both solver files are among the row's declared outputs, collected and hashed in
the run record like every export. The VTK positions are in the simulation's
length unit and the analysis frame the export names, as the solver's own surface
VTK is.

The surface friction lines are kept as the solver's file only: their export
grammar has not yet been measured on a licensed run, so the post writes no VTK
from them and says so in `post.log`.

## What is refused

- `length_m` together with `unrestricted = true`, which the manual gives as
  alternatives without saying what the solver does with both.
- A table that traces nothing, and `direction`, `length_m` or `unrestricted`
  without a seed line or tube.
- A seed line of one streamline: the single seed command aborts the solver on
  the current builds, so a line of two or more is the remedy.
- Off-body lines or tubes on a `qsteady_rotor` row, where the blade is held still
  and the free stream turns about the shaft: what the solver traces through that
  rotor-fixed field is unmeasured. Surface lines stay allowed there.
- `[streamlines]` on a row that couples a structure (`FSI`), whose exports run in
  the aeroelastic post-processing script.
- A frame the run does not create.
- A build on which a streamline command is still recorded from the manual only,
  with no licensed run behind it: the plan names the command.

## In an additional pproc

An additional pproc (`ADDITIONAL_PPROC`) may state `[streamlines]`. The
extraction deletes the streamlines the saved simulation carries, traces the
table's, and the post writes a WARNING per extraction in `post.log`: a reopened
simulation may trace differently from the run, since off-body flow values did
not come back identical after reopening.
