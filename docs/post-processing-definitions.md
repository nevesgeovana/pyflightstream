<a id="post-processing-definitions"></a>

<h1>Post-processing definitions</h1>

**This page is the definition of record for every post-processing product this
package writes.** It exists because the definitions kept being re-explained in
conversation and re-derived from code, and a definition derived from code makes
the code its own specification. Where this page and the code disagree, **this
page is right and the code is a defect**.

Every definition below states the requirement a product is built to. None of
them was inferred from an implementation.

!!! note "For whoever maintains this package"
    Read this page before changing any reduction, any averaging window, or any
    product's column set. A reduction whose meaning you reconstructed from
    `cases/workflows/` is a reduction you are about to get subtly wrong: three of
    the definitions below were implemented as a declared field with no caller,
    which reads exactly like a finished feature.


<a id="contents"></a>

<h2>Contents</h2>

<a id="warnings-and-recorded-diagnostics"></a>

[Warnings and recorded diagnostics](definitions/warnings-and-recorded-diagnostics.md#warnings-and-recorded-diagnostics).

<a id="the-vocabulary"></a>

[The vocabulary](definitions/the-vocabulary.md#the-vocabulary).

<a id="what-every-product-states"></a>

[What every product states](definitions/what-every-product-states.md#what-every-product-states).

<a id="the-axes-of-a-steady-polar"></a>

[The axes of a steady polar](definitions/the-axes-of-a-steady-polar.md#the-axes-of-a-steady-polar).

<a id="the-drag-split-of-26125"></a>

[The drag split of 26.125, `CDV` and `CDP`](definitions/the-axes-of-a-steady-polar.md#the-drag-split-of-26125).

<a id="the-sections-table-and-which-row-is-which"></a>

[The sections table, and which row is which](definitions/the-sections-table-and-which-row-is-which.md#the-sections-table-and-which-row-is-which).

<a id="per-distribution-sectional-loads-and-cp-0250"></a>

[Per-distribution sectional loads and Cp (0.25.0)](definitions/the-sections-table-and-which-row-is-which.md#per-distribution-sectional-loads-and-cp-0250).

<a id="integrated-sectional-loads-since-0260"></a>

[Integrated sectional loads](definitions/the-sections-table-and-which-row-is-which.md#integrated-sectional-loads-since-0260).

<a id="the-probes-table"></a>

[The probes table](definitions/the-probes-table.md#the-probes-table).

<a id="the-reductions-of-an-unsteady-point"></a>

[The reductions of an unsteady point](definitions/the-reductions-of-an-unsteady-point.md#the-reductions-of-an-unsteady-point).

<a id="time_average"></a>

[time_average](definitions/time_average.md#time_average).

<a id="per_blade"></a>

[per_blade](definitions/per_blade.md#per_blade).

<a id="phase_locked"></a>

[phase_locked](definitions/phase_locked.md#phase_locked).

<a id="when-it-is-generated"></a>

[When it is generated](definitions/phase_locked.md#when-it-is-generated).

<a id="a-short-run-is-skipped-never-refused"></a>

[A short run is SKIPPED, never REFUSED](definitions/phase_locked.md#a-short-run-is-skipped-never-refused).

<a id="per_revolution"></a>

[per_revolution](definitions/per_revolution.md#per_revolution).

<a id="the-per-station-harmonics"></a>

[The per-station harmonics](definitions/the-per-station-harmonics.md#the-per-station-harmonics).

<a id="the-disc-maps"></a>

[The disc maps](definitions/the-disc-maps.md#the-disc-maps).

<a id="probe-parameters"></a>

[Probe parameters](definitions/probe-parameters.md#probe-parameters).

<a id="the-averaging-window"></a>

[The averaging window](definitions/the-averaging-window.md#the-averaging-window).

<a id="native-surface-flow-exports"></a>

[Native surface flow exports](definitions/native-surface-flow-exports.md#native-surface-flow-exports).

<a id="the-tecplot-surface-is-written-from-the-vtk-since-0280"></a>

[The Tecplot surface is written from the VTK](definitions/native-surface-flow-exports.md#the-tecplot-surface-is-written-from-the-vtk-since-0280).

<a id="native-nodal-strength-in-0290"></a>

[Native nodal strength in 0.29.0](definitions/native-surface-flow-exports.md#native-nodal-strength-in-0290).

<a id="the-strength-is-asked-for-since-0300"></a>

[The strength is asked for](definitions/native-surface-flow-exports.md#the-strength-is-asked-for-since-0300).

<a id="the-time-averaged-surface-is-the-packages-since-0280"></a>

[The time-averaged surface is the package's](definitions/native-surface-flow-exports.md#the-time-averaged-surface-is-the-packages-since-0280).

<a id="the-solvers-own-plots"></a>

[The solver's own plots](definitions/the-solvers-own-plots.md#the-solvers-own-plots).

<a id="the-boundary-layer-profile-is-not-produced"></a>

[The boundary-layer profile is not produced](definitions/the-boundary-layer-profile-is-not-produced.md#the-boundary-layer-profile-is-not-produced).

<a id="a-volume-section"></a>

[A volume section](definitions/a-volume-section.md#a-volume-section).

<a id="historical-native-volume-exports-027x-and-028x"></a>

[Historical native volume exports, 0.27.x and 0.28.x](definitions/a-volume-section.md#historical-native-volume-exports-027x-and-028x).

<a id="durable-execution-activity"></a>

[Durable execution activity](definitions/durable-execution-activity.md#durable-execution-activity).

<a id="the-additional-post"></a>

[The additional post](definitions/the-additional-post.md#the-additional-post).

<a id="the-unsteady-polar"></a>

[The unsteady POLAR](definitions/the-unsteady-polar.md#the-unsteady-polar).

<a id="the-mesh-face-count-since-0340"></a>

[The mesh face count](definitions/the-mesh-face-count-since-0340.md#the-mesh-face-count-since-0340).

<a id="rotor-coefficients"></a>

[Rotor coefficients](definitions/rotor-coefficients.md#rotor-coefficients).

<a id="where-an-unsteady-points-numbers-come-from"></a>

[Where an unsteady point's numbers come from](definitions/rotor-coefficients.md#where-an-unsteady-points-numbers-come-from).

<a id="etaw"></a>

[ETAW](definitions/rotor-coefficients.md#etaw).

<a id="the-in-plane-coefficients"></a>

[The in-plane coefficients](definitions/rotor-coefficients.md#the-in-plane-coefficients).

<a id="a-static-point"></a>

[A static point](definitions/rotor-coefficients.md#a-static-point).

<a id="tip-and-helical-mach-numbers"></a>

[Tip and helical Mach numbers](definitions/tip-and-helical-mach-numbers.md#tip-and-helical-mach-numbers).

<a id="what-the-package-does-not-judge"></a>

[What the package does NOT judge](definitions/what-the-package-does-not-judge.md#what-the-package-does-not-judge).

<a id="the-post-log-and-the-default-warning-rule-since-0260"></a>

[The post log and the default warning rule](definitions/what-the-package-does-not-judge.md#the-post-log-and-the-default-warning-rule-since-0260).

<a id="the-reducer-states-the-plotted-steps-it-reads"></a>

[The reducer states the plotted steps it reads](definitions/what-the-package-does-not-judge.md#the-reducer-states-the-plotted-steps-it-reads).

<a id="unread-residual-blocks-and-repeated-markers"></a>

[Unread residual blocks and repeated markers](definitions/what-the-package-does-not-judge.md#unread-residual-blocks-and-repeated-markers).

<a id="the-token-for-a-value-that-does-not-exist"></a>

[The token for a value that does not exist](definitions/the-token-for-a-value-that-does-not-exist.md#the-token-for-a-value-that-does-not-exist).

<a id="sampled-velocity-fields-and-reusable-inflow"></a>

[Sampled velocity fields and reusable inflow](definitions/sampled-velocity-fields-and-reusable-inflow.md#sampled-velocity-fields-and-reusable-inflow).

<a id="the-installed-frame-copy-of-a-product-table"></a>

[The installed-frame copy of a product table](definitions/the-installed-frame-copy-of-a-product-table.md#the-installed-frame-copy-of-a-product-table).

<a id="the-inflow-tools-products"></a>

[The inflow tools' products](definitions/the-inflow-tools-products.md#the-inflow-tools-products).

<a id="the-quasi-steady-rotor"></a>

[The quasi-steady rotor](definitions/the-quasi-steady-rotor.md#the-quasi-steady-rotor).

<a id="quasi-steady-wheel-corrections"></a>

[Quasi-steady wheel corrections](definitions/quasi-steady-wheel-corrections.md#quasi-steady-wheel-corrections).

<a id="the-acoustic-signals-product"></a>

[The acoustic signals product](definitions/the-acoustic-signals-product.md#the-acoustic-signals-product).

<a id="the-post-of-other-records-since-0320"></a>

[The post of other records](definitions/the-post-of-other-records-since-0320.md#the-post-of-other-records-since-0320).

<a id="posting-and-collecting-some-simulations-since-0330"></a>

[Posting and collecting some simulations](definitions/posting-and-collecting-some-simulations-since-0330.md#posting-and-collecting-some-simulations-since-0330).
