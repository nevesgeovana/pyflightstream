# Phase B workspace routes

- Direct-morphing structural products use the recorded applied station
  displacements, with a matching configuration digest, instead of refusing
  every direct-morphing point.

- An explicit exploratory `[noise]` request writes compact loading-noise observer
  signals from recorded quasi-steady wheel loads, labelled as unvalidated.

- `[products].polar_axes` selects wind or stability force coefficients as `CD`,
  `CY` and `CL`, retaining the explicit frame columns and naming the selection.

- Coupling projects spatial-cut loads using applied station slope and twist
  before elastic-axis moment transfer, including relaxed direct-morphing state.

- Coupled polar and rotor tables include each blade's last recorded tip deflection
  and twist; missing structural values remain `NA`.

- Located post-processing declarations accept `attach = "space" | "body"`.
  Coupled rows refuse unmeasured body attachment and warn about surface taps
  that remain at declared spatial locations.

- `plan --inflow-fft` writes per-point blade-view harmonic tables at the resolved
  advance ratio, including variance shares and effective reduced frequency.

- `pyfs-workspace geometry trailing-edge` extracts a mesh's trailing-edge midpoint
  file with explicit axis, hub and length unit.

- `pyfs-workspace calibrate` derives a sector-offset calibration from two recorded
  rotor points, preserving the existing evidence checks and unvalidated status.

- FSI workspace inputs can stage a checked frozen displacement file and explicitly
  allow configuration changes through the existing coupling driver controls.

- Workspace post tables recorded force-distribution and surface CSV exports,
  preserving force units and explicitly unstated scalar identities.

- Workspace post writes mapped structural deflection, twist and available
  coupling history from admitted coupled points, with input-digest checks.

- Planar probe grids are declared in `[[probes]]`, with reference-frame placement,
  axis distributions and near-surface refinement checked during plan. Saved
  simulations require a separate surface mesh export before this route plans.

- Calculated FSI sections accept unit-chord airfoils or NACA four-digit contours.

- Coupled plans report effective station properties, natural frequencies and
  rotational excitation warnings before a licensed run.
