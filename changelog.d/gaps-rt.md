## Added
- A pproc `[streamlines]` table traces surface friction lines and off-body streamlines (seed lines and tubes) on every point of a row, exports them, and the post writes a VTK polyline product of the off-body lines; the plan states the count per point (FR-460).
- The `unsteady` row key `SIXDOF: d<id>` frees a body to move under its loads from an input of `inputs/sixdof/`: families, body frame, mass and inertia, gravity, initial state, free degrees, external, spring and custom forces, and the trajectory export (FR-461).
- An FSI input with `mode = "external"` couples a fixed wing to a structural program of the user's own through the step `pyfs-fsi external`, which runs the program per coupling iteration and archives and validates every call (FR-462).
- The streamline and 6DOF commands a row reaches are refused at plan on a build where no licensed run verified them, naming the command.
## Migration
- Output names ending in `_sls.txt`, `_slo.txt` or `_trajectory_6dof.txt` are read as streamline and trajectory exports from 0.40.0 on; a row declaring its own outputs with those endings renames them.
