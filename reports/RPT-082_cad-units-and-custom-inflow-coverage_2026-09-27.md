<!--
GEOVERSE_HEADER
file_version: 1.1.1
file_role: measured-CAD-units-and-custom-field-report
last_modified_at: 2026-09-27T20:46:59.533Z
last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
dependencies: [RPT-070, RPT-077, docs/cad-inputs.md]
authority: pyflightstream
status: measured-limited-scope
confidentiality: public
change_summary: Include the executable example and continuation declaration tests.
revision_source: git
-->

# RPT-082: CAD units and custom-inflow coverage

The CAD route now accepts IGES and refuses STEP before script emission.
Custom fields retain their global physical orientation. Explicit SI inputs can
be prepared in native millimetre units; the comparison below measures that
conversion on one executable. Spatial diagnostics use conservative envelopes.

## IGES import and physical scale

Measured on FlightStream 26.124, build 8172026, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65`.
The control reused an existing wing IGES import and changed only its global
unit flag/name from millimetres to metres. Scale parameter 13 remained 1.0,
and all non-global IGES sections were byte-identical. The same coordinate
numerals therefore describe a physically larger body, not an equivalent input.

Both imports used MEDIUM tessellation, unreferenced patches enabled, and 80
curvature subdivisions. Every CAD body was converted to mesh. No solve ran.

| Observation | Source declares millimetres | Source declares metres |
| --- | ---: | ---: |
| Loaded / total CAD entities | 176 / 179 | 176 / 179 |
| Mesh vertices | 7,431 | 7,461 |
| Mesh triangles | 12,727 | 12,751 |
| X bounds, metres | 6.6928999023 to 106.6928984375 | 6692.8999023438 to 106692.8984375 |
| Y bounds, metres | -99.9998984375 to 0 | -99999.8984375 to 0 |
| Z bounds, metres | 2.2074873047 to 102.2244140625 | 2207.4873046875 to 102224.4140625 |

All six bounds follow the expected factor of 1000, with maximum absolute
comparison residual 1.46e-11 m. Both saved simulations identify metre units,
and the measured saved-mesh convention stores internal metre coordinates.
After conversion, setting the simulation length unit to METER does not call
for another multiplication of the mesh coordinates.

The boundary inventory was unchanged. Tessellation counts were not identical,
so this experiment does not establish point correspondence or mesh similarity.
It does not identify the three unreported entities or validate mesh quality.
The vendor manual (CAD pp.30 and 290) documents IGES import/conversion and
cautions that default tessellation generally needs further mesh preparation.

Exact input, script and output bytes are bound by the retained local execution
and analysis receipts. Public evidence anchor: analysis SHA-256
`7b9d34d4f457d6bf6e05fa909b9ac803ab65a634ed51d84b9dd9278cd4599310`.
Private CAD payloads and local filesystem paths are intentionally not distributed.

## Negative STEP controls

Two independently constructed STEP representations, faceted and analytic
planar BREP, each completed the import command but saved zero CAD entities
and an empty mesh. An exit code of zero and an import-completed log were
therefore insufficient acceptance. The current documented and measured route
is IGES; STEP is refused explicitly. These tests do not prove that every
possible STEP file fails in the native application.

## Offline route validation

Thirteen CAD tests passed, covering typed options, staged input paths,
conversion ordering, explicit FILE units, public example emission and the
STEP refusal. Before the restriction, both new STEP refusal regressions failed
because no exception was raised. These tests validate the Python contract;
they do not replace the native geometric measurements above.

## Uniform, sheared, and millimetre custom fields

Eight successful six-STEP controls used the same executable/build above and
one solver thread. The fixed wing used dt=0.02 s; the rotating case reused the
measured six-STEP rotor fixture with dt=0.00625 s and emitted -800 RPM.
Both ran at 30 m/s. These short controls test behavior, not convergence or
absolute aerodynamic accuracy.

| Comparison | Printed history values | Final load coefficient values | Result |
| --- | ---: | ---: | --- |
| Wing uniform CUSTOM versus CONSTANT | 72 | 18 | Exact equality |
| Rotor uniform CUSTOM versus CONSTANT | 1,956 | 36 | Exact equality |
| Wing shear versus CONSTANT | 60 of 72 changed | 14 of 18 changed | Field effect observed |
| Rotor shear versus CONSTANT | 1,654 of 1,956 changed | 26 of 36 changed | Field effect observed |
| Wing MM, native-scaled file versus METER | 72 | 18 | Exact equality |
| Wing MM, unscaled SI file versus METER | 27 of 72 changed | 10 of 18 changed | Negative unit control |

The uniform file contains 30 m/s in global X; shear varies X velocity as
30 + 2.5 z with z in metres. No vector or coordinate rotation is applied.
For the equivalent MM case, custom-file XYZ and velocity columns are multiplied
by 1000 along with the dimensional command quantities. The unsteady fluid-plot
VERTEX arguments stay in metres, following their separately measured contract.
The negative file leaves SI numerals unchanged in the MM simulation. Its maximum
sampled velocity difference is 29.970458 m/s. Outside its small numerical grid,
samples can return the uniform fallback; a plausible value alone is not a
coverage proof.

Equality means equality of every printed value, with matching named columns,
surfaces and actual STEP 1 through 6. It does not imply bitwise identity of the
internal solution or transfer the unit contract to another executable.
Public evidence anchor: comparison receipt SHA-256
`8e4903a3fd70bc64a572eb4ff58ddccfa951519a44d8577273ad8fec4efa2246`.
The reader verifies execution receipts, script/output hashes and printed build.
Two earlier MM scripts put the unit command inside an incomplete OPEN block;
their syntax failures are preserved and excluded from physical acceptance.

## Spatial bounds and offline coverage checks

The workflow records emitted surface transforms and the final motion ledger.
It computes a conservative body envelope after translations and rotations,
then includes complete rotary sweeps about known centers and axes. Partial
boundary selections retain both original and transformed boxes. Both angular
signs are included when calculating a static rotation envelope. These choices
can overestimate occupied space and do not establish a new rotation convention.

A grid-bounds exceedance warns explicitly. A contained envelope is recorded as
`within-grid-bounds`, not an interpolation or accuracy certificate: an external
YZ box alone cannot establish support inside an arbitrary unstructured field.
Unknown units, raw geometry commands, unreadable geometry or unsupported motion
produce an explicit unknown result. An undeclared legacy MM field is never
silently interpreted as SI.

Eight focused coverage tests verify translated and rotated envelopes, partial
selections, full rotary bounds, one-time MM conversion, unknown-transform
refusal, actual command-ledger integration and reset when opening a new model.
Fourteen explicit-unit tests verify source preservation, prepared-file hashes,
unit declarations, continuation identity, the executable example and refusal
after source changes. These are offline contract
tests; the native comparisons above provide the distinct measured field effect.
