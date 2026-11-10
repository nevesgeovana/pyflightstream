Fix the IGES reader-profile distance check for surfaces with unequal parameter
ranges and for points near a parameter bound.

migration: No input change; valid boundary curves near parameter bounds no longer
fail the surface-distance check because of finite-difference scaling.

Measure shared cap boundaries at S8, including the corner-cap side edges, and
stop the run with `closure.cap_edge_gap` when the gap exceeds 0.005 mm.

migration: IGES export writes PREF 1 for requests for either model space (2)
or either space (3), with a warning naming the replacement.

The closure stage measures lifting models handed to it by preceding custom
stages through `RunContext.state["lifting_models"]`; absent models are built
once and retained for subsequent checks.

The geometry run exports the retained assembly faces, with one IGES and layout
sidecar per source piece and a manifest recording its generated version,
surface identity, kept-face ownership and measured trimmed areas. Lifting
skins, fillets and blisters carry their original bases and UV loops into the
assembly instead of sampled layout patches.

migration: S11 writes `manifest.json`, per-piece IGES and layout files, and
isolated face files for read-back checks beside the combined IGES.

S11.V checks manifest membership, piece versions and source identities against
the selected registry and the separately retained generation record.

migration: A configuration now refuses variants excluded by its own registry
entry, even when the variant exists elsewhere in the configuration file.
Applied-control variant export is recorded as waiting for G9, without
publishing clean geometry under the requested variant.

S11.R reimports every component and each isolated face in fresh kernel
processes, comparing face counts, sewn free edges and per-face trimmed areas.
It rejects a relative face-area difference above 1e-3 and component area
above the source area plus `acceptance.area_excess`.

migration: Read-back checks now have their own S11.R stage record and run-log
entries; `--until S11` stops after writing and does not claim read-back checks.

S11.S imports the combined file in one operation at each sewing tolerance,
1e-5 m and 5e-5 m. It reports introduced free edges against the input curves,
triple edges and new sub-5 mm slivers, listing the thin faces in each import.
Unassembled pieces now retain their original sliver count as well as their
free edges, so existing thin faces do not become export defects.

Source coverage checks the distance to kept faces in world space, respects
original trim exclusions and integrates cell areas against the kernel's
source area. It records covered, legitimately removed and missing areas,
including the largest missing region and its centroid.

migration: S10.D8b uses `acceptance.coverage_spacing` and reports
`coverage.area_sum` with a relative limit of 1e-3. A displaced face cannot
pass coverage merely because its parameter coordinates contain the source.

The export manifest uses `pyflightstream-geom-manifest/1`, with piece records,
file digests, parameter, surface and build identities, junction rows and
measured areas. Reimport fills its measured area; an unperformed measurement
stays null. Layout sidecars preserve the original base order and all source
trim loops, including those with no retained face.

migration: The provisional manifest's component mapping is now the specified
`pieces` list. Each piece has an integer `faces` count and a `face_records`
list containing its retained-face measurements.

S11 counts the faces actually emitted in every file and rejects solid
entities. S11.P measures reader compatibility, requires both boundary
curves with PREF 1 and parameter-space use 05, and compares the written
copies of each base at 1e-12. It independently verifies the sidecar's
original bases and loops against the generated source identity.

migration: Reader and shared-base checks have their own S11.P stage and log
record. `--until S11` performs the write audit; a complete run continues
through the profile, reimport and sewing audits.

S13.R stores the fitted defining sections as B-splines in resolved TOML,
reloads them in a pure regeneration, and compares every piece's bases and
trim loops with the independently retained source identities. This works
in a fresh process without a section refit. S13 independently identifies
written lifting pieces; unsupported component types are explicitly skipped.
Run reports retain the written surface and build identities.

migration: The regeneration and reverse identification checks have separate
S13.R and S13 records. Applied-control variants continue to wait for G9.

S12.C exercises the existing IGES converter and checks retained face counts.
S12.G grids the retained named faces through the existing mesher, checks its
CAD boundary audit, and records a boundary reference. S12 re-reads that mesh
to reject introduced open seams and triple edges, then finds each lifting
piece's upper trailing-edge rim from its sidecar roles.

migration: Reader conversion, gridding and the final audit have separate
records and named checks. This diagnostic grid uses 16 cells in each
structured direction and does not replace a user's production grid.
