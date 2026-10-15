# Planar probe grids in a workspace

Use planar grids to prescribe each sample location instead of relying on
the solver's volume-section sampling. In a post-processing input, write:

```toml
[[probes]]
frame = "REFERENCE"
scale = "m"
parameters = ["VX", "VY", "VZ"]

[[probes.grids]]
frame = { origin = [0, 0, 2], x_axis = [1, 0, 0], y_axis = [0, 1, 0] }
u = { start = 0, stop = 1, count = 2 }
v = { start = 0, stop = 1, count = 2 }
```

This example emits four points two metres above the reference XY plane,
in u-major order. The workspace regression test plans this declaration and
checks all four coordinates. Run the ordinary `pyfs-matrix plan` command
before running the matrix. Grids use metres; the emitter converts them to
the simulation's length unit. The grid's explicit frame places it in the
reference frame, so the containing probe entry must name `REFERENCE`.

Each axis accepts `spacing` instead of `count`, or a count with
`distribution = "cosine"` or `"geometric"`. A geometric distribution also
states `ratio` and `cluster`. An optional grid `refinement` table states
`distance` in metres and integer `factor` for surface-adjacent refinement.

Declared points inside a closed body warn and remain in the survey. Added
refinement points inside the body are refused. Refinement needs a readable
surface mesh and the geometry extra. An open mesh cannot establish inside
versus outside and produces an explicit unchecked warning for declared points.

For a saved `wing.fsm`, export `wing.surface.stl` beside it on the licensed
machine, in the reference frame and the simulation's native length units.
Plan names that missing export and refuses; it never launches FlightStream
to obtain one. Use the same geometry revision for the saved simulation and
its exported mesh.
