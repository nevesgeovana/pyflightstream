<!--
GEOVERSE_HEADER
file_version: 1.0.0
artifact_id: migration-0290
last_modified_at: 2026-09-27T19:06:07.787Z
last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementer}
dependencies: [pyflightstream]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Explain input preservation, explicit standards, post associations and optional integrations.
revision_source: git
-->

# Migrating to 0.29.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. Solver operations still use
the selected build's command evidence.

## Setup files and their guide

Run `pyfs-matrix plan` with `--setup-guidelines` to write
`inputs/setups/SETUP_GUIDELINES.md`, or `--setup-standards` to write the complete
`s9XX` presets. Supply the target `--fs-version`. These options are independent
and may be combined. The directory remains plural: `inputs/setups`.

Existing differing files are preserved. Review the reported created, unchanged
and preserved files; generate into a separate workspace to compare new
definitions with custom presets. No matrix is silently switched to a new setup.
The guide names each study's baseline, physical assumptions and unavailable
controls. A complete preset is not a validation of every physical model for
your geometry. See [setup standards](setup-standards.md).

Inspect a matrix with `pyfs-matrix inspect-setups` to see resolved settings and
their source, including boundary selections and raw commands. Preserve custom
setup files and compare the inspection before starting a campaign. Steady
workflows default to a cold start; request warm continuation explicitly when
that is the intended study.

## Surface and sampled-field products

New Tecplot surface requests retain a native auxiliary export named
`*_native_tecplot.dat`. The requested surface keeps the VTK panel quantities
and adds actual nodal `Singularity_strength` after matching coordinates and
polygon topology. A reader must respect the file's variable associations:
strength is nodal, while Cp and the other VTK panel fields are cell-centred.
Both source hashes and the recorded loads frame are retained.

Keep the auxiliary files when moving or collecting a run, including their
per-STEP copies. A missing step never borrows the final source. Historical
records without an auxiliary declaration retain their earlier VTK-only route
and explicit missing-strength statement. Existing translated outputs are
preserved and checked against their sources, full frame record and content
hash. See [surface translation](surface-translation.md).

Probe surveys and volume sections can produce package-written VTK and Tecplot
velocity fields, with positions, components, units and source evidence stated
in the product. Their topology is a vertex cloud; no volume cells are invented.
Reusable inflow additionally requires a suitable global YZ survey. Old records
without sufficient placement or motion evidence remain explicitly unsupported
for that derived product. See [sampled fields](sampled-fields.md).

Select `products.boundary_layer_integrals` and
`products.boundary_layer_velocity_profile` independently in pproc. The first
reads VTK cell quantities at actual configured section cuts. The second stays
refused on builds without positive unattended-profile evidence; it never
substitutes an integral table. See [boundary-layer products](boundary-layer-products.md).

Final section Cp plots are available after supported unsteady marches, once
at the end. Surface averaging continues to use the complete recorded STEP
window and each STEP's own sources. See [unsteady plots and averages](unsteady-postprocessing.md)
for the difference between native fields that are averaged and native fields
that retain their final instant.

## Logs and recovery

Normal output reports the active stage and final outcome. Post warnings are
recorded while terminal warnings remain off by default; use
`--pproc-warnings` to show them. `post --diagnostics` writes the complete
Markdown diagnostic report without changing existing product or CSV bytes.
Keep `post.log.json` with the other execution records. Errors stay visible.

Continuation and collection verify the recorded scripts and input/output
identity rather than guessing missing state. See
[continuation and recovery](continuation-recovery.md) before reusing a run that
stopped early or was submitted elsewhere.

## Optional FSI and Excel inputs

FSI setups live under `inputs/fsi/f<>.toml`. They can use supplied complete
stiffness/mass distributions or calculate homogeneous solid-section properties
from geometry and one cited material. Calibration factors default to unity;
matrix values override file factors once. The unscaled and effective values
and factor origins remain in provenance. See [FSI in a workspace](fsi-workspace.md).

The optional Excel workbook embeds the reviewed VBA and a Dictionary of column
names. Read and Write create a preview; Apply or Cancel is explicit. Existing
ASCII schemas, custom cells and formulas, leading-zero IDs and recovery copies
are preserved. Desktop Excel applies its normal macro policy. Workbook creation
does not launch Excel or change trust settings. See
[Excel matrix synchronization](excel-matrices.md).
