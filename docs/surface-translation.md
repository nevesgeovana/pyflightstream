# Surface exports and native singularity strength

A workspace row requesting the Tecplot surface receives a package-written file.
The VTK export supplies panel values such as Cp and boundary-layer quantities.
A separate native Tecplot export supplies the nodal `Singularity_strength`.
No pressure-to-strength formula or cell-to-node interpolation is used.

The workflow acquires both files automatically, including each requested time
step. The retained native source ends in `_native_tecplot.dat`; it is a source
artifact, while the originally requested `.dat` is the translated product.
Both inputs are collected and hashed. No additional setup or export toggle is
needed beyond requesting the Tecplot surface.

## What the product contains

| Values | Association | Source |
|---|---|---|
| X, Y, Z | Node | VTK coordinates transformed into REFERENCE |
| Singularity_strength | Node | The same point or step's native Tecplot |
| Cp, pressure, BL and other selected fields | Cell/panel | Original VTK cell arrays |
| Velocity components | Cell/panel | VTK values with the measured loads-frame export transform undone |

The native export must match the VTK through a unique node bijection and the
complete polygon edge topology. Equal counts alone are insufficient. Ambiguous
nodes, changed topology, missing step sources, truncated files and nonfinite
native values are refused with an explicit reason. The match is made in the
loads frame the VTK was written in: the native nodes are carried into that
frame, and each loads axis allows half the single-precision spacing of the
written VTK coordinates along it plus the rounding of the carry, and never less
than 1e-6 of the native geometry's diagonal extent. The run record states those
per-axis tolerances and the frame they are measured in. Callers of the low-level API must provide the actual VTK loads
frame and sources in matching physical units.

For measured FlightStream exports, the VTK velocity convention includes the
loads-frame origin as well as its axes. The package retains that observed
convention rather than applying a generic vector rotation. This is an export
convention, not a statement that physical velocity depends on origin.

## Provenance and recovery

The product header records both source SHA-256 hashes and the loads frame.
The run record retains the node-matching evidence and output hash; the product
manifest identifies mixed nodal/cell association, and PROV links both sources.
A step never borrows strength from the final export.

An existing translated product is preserved. Its current sources, frame and
content hash must agree before it can be accepted as current. Frame comparison
uses the complete recorded values, not the rounded human-readable description. If an older
record lacks an output hash, expected bytes are reconstructed in a temporary
location and compared; matching headers alone do not prove valid data. A
conflicting or truncated product is reported without overwriting it.

Source and output byte identities use sha256, with canonical forms owned by
`pyflightstream._digest`. They hash exact file bytes, without adding filesystem
paths or timestamps; changing line endings therefore changes the digest.

A historical run without a native-source declaration keeps the earlier VTK-only
route and explicitly reports `Singularity_strength` as not carried. The
package does not invent the absent field or rewrite historical solver outputs.

## Direct API example

See [the executable example](examples/surface_with_native_strength.md). It
accepts the VTK, native source, new output path and recorded frame JSON. Normal
workspace execution performs the same acquisition and translation automatically.

Native acceptance uses a translated and Z-rotated saved surface and additional
Y-tilted, rotor and six-step exports on the measured build. Exact source and
executable hashes belong to the local acceptance receipts. These controls do
not establish every solver build or export convention.
