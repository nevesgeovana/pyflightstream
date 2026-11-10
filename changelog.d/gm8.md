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
