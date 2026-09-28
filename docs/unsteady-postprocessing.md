# Unsteady plots and surface averages

A pproc section distribution enables its final Cp plot on an unsteady run. The
plot is saved once after the march; per-STEP actions do not repeatedly save it.
Residual and load plots retain the samples actually exported by the solver.

```toml
[[sections.distributions]]
families = "all"
frame = "REFERENCE"
planes = ["XZ"]

[exports]
plot_sections_cp = true
plot_residuals = true
plot_loads = true
```

The section Cp file contains pairs of abscissa and Cp columns. Multiple curves
can share a section label. It is a plot product, not a substitute for the loads
table. Setting an export to false suppresses that plot. Asking for the Cp plot
without any section distribution remains invalid.

A native control ([RPT-083](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)) measured this final export on FlightStream
26.124, build 8172026. Thirty nonempty curves were exported after twelve time
steps; the nine printed final load coefficients matched the baseline exactly.
This evidence does not establish the same behavior on other builds.

Surface averages use every STEP in the requested inclusive window. The same
cell identity is followed through the window; the final STEP supplies geometry.
A matching native Tecplot auxiliary source supplies real nodal
Singularity_strength, averaged separately from the VTK cell variables. Both
source hashes and the per-STEP geometry/topology matching are retained.
Missing native samples do not borrow values from the final export. Cell Cp is
never relabeled as nodal Cp or singularity strength.

The 26.122 rotor control compared native nodal Cp, Vx and speed over STEPs 7 to 12,
a window starting after the first export. Applying the package reducer directly
to those native nodal histories matched the native averaged nodal quantities
within 1.3e-15 scaled error. This diagnostic does not interpolate the product
cell Cp into nodal Cp. A separate comparison retains cell-to-cell association.

Native Singularity_strength, CF and boundary-layer exports in this control
retained their final instantaneous values. The package still computes their
actual temporal means from each selected STEP; those different statistics are
not declared equivalent. The average uses the last **selected** STEP geometry,
without averaging X, Y or Z coordinate fields.

Walltime rescue writes the declared instantaneous outputs and then calls
CLOSE_FLIGHTSTREAM. The measured 26.122 control ended at STEP 16 without an
external kill. Both residual and load plots contain 1,128 finite inner-iteration
samples, numbered 1 to 1,128. The separate aggregate unsteady plot contains STEPs
1 to 15: its last completed sample precedes the stop. Export filenames identify
the rescue step; they do not promise that every history includes that step.
The original files remain unchanged, and missing samples are never fabricated.

A named WALLTIME diagnostic refuses the surface-average product. Native Cp,
Vx and speed retained the STEP 16 instantaneous state instead of the requested
mean of STEPs 2 to 3. The product stays refused until that discrepancy is
resolved. Independent arithmetic checks verify the package reducer on
the recorded per-STEP fields, but do not establish native equivalence for this
run type. STOP-in-action and runtime iteration-count controls failed to stop
normally; neither behavior is used as a successful walltime implementation.
