<!--
GEOVERSE_HEADER_BEGIN
file_version: 1.0.2
file_role: cad-input-route-documentation
last_modified_at: 2026-09-27T19:57:09.644Z
last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
dependencies: [pyflightstream.cases.CadImportOptions]
authority: pyflightstream
status: draft
confidentiality: public
change_summary: Document explicit CAD conversion and its native validation limits.
revision_source: git
GEOVERSE_HEADER_END
-->

# CAD geometry inputs

A workflow can import IGES (`.igs` or `.iges`) through the native CAD importer,
then convert selected CAD bodies into a surface mesh. STEP (`.step` or `.stp`)
is refused before script emission: native controls produced empty geometry,
and the documented importer route is IGES.
The source CAD file is staged and hashed using the same geometry path as a
saved simulation or raw mesh.

Create a boundary sidecar beside the CAD file:

```toml
boundaries = ["Wing"]

[import]
units = "FILE"

[import.cad]
tessellation_density = "MEDIUM"
unreferenced_patches = true
num_curvature = 80
body_index = -1

[trailing_edges]
detect = "auto"
```

The boundary inventory must describe the converted mesh in native order.
Inspect that conversion before assigning physical boundary conditions.
`body_index = -1` converts every CAD body; a positive value selects one
native CAD body. `num_curvature` is the subdivision count around a full
circle, not an edge length. Density accepts LOW, MEDIUM or HIGH.

`units = "FILE"` explicitly uses the source CAD metadata. The native
IMPORT_CAD command has no units argument. A raw-mesh value such as
MILLIMETER would otherwise be silently discarded, so this combination is
refused. The workflow sets the simulation display/command length unit to
METER after conversion; that command alone does not prove the converted
body's physical scale. Check a known source dimension in the converted
mesh before running a physical case.

Existing `[[import.operations]]` run after conversion in the stated order.
For CAD, translation vectors are in metres; scale factors are dimensionless.
Geometry operations precede setup operations as for raw meshes. The
trailing-edge file route cannot validate a CAD tessellation offline, so use
explicit detection or convert to a mesh and validate its edge points.
Loading a saved solver initialization during CAD conversion is refused.

In the GUI this corresponds to importing CAD, choosing tessellation,
converting the CAD body to mesh, inspecting dimensions and boundary names,
then marking trailing edges. Python users can run
`examples/cad_import.py` to emit a complete script without launching the
solver.

The command route was exercised on one IGES wing with FlightStream 26.124,
build 8172026. Changing only the source unit metadata from millimetres to
metres, while retaining the geometry numerals, increased every physical mesh
bound by a factor of 1000 (maximum comparison residual 1.5e-11 m). The saved
mesh used metres in both cases. Do not scale its coordinates again merely
because the source IGES declared millimetres.

This is a measured unit-metadata effect for one model, not completeness for
arbitrary CAD assemblies or mesh-quality validation. The tessellation changed
from 7,431 vertices/12,727 triangles to 7,461 vertices/12,751 triangles; native
tolerances can depend on physical scale. Both imports loaded 176 of 179 entities.
Preserve importer warnings and inspect omitted entities. The vendor manual
(26.124, CAD pp.30 and 290) also states that default CAD tessellation usually
needs mesh cleanup before analysis; conversion success does not establish
that the resulting mesh is suitable for a solve.

Existing OBJ/STL sidecars retain their original unit and operation semantics.
No CAD options are applied to those files; supplying them is an error.
