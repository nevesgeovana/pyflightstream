## Fixed

- Refuse an existing sweep overlay without `--overwrite`, including disjoint `--only` selections. Authorized replacements retain the old overlay as `.previous` evidence and publish the new overlay atomically (FR-471 R9, FR-472 R7, PFS-2081.117, REL5-001).
- Sweep overlays support the same exported OBJ fallback as individual previews for quadrilateral saved meshes, preserving control-surface families and original angle ordinals (FR-472 R7, PFS-2081.118, REL5-002).
- The `strip_edges` documentation now describes shape and ends-option checks, trace-order coordinates that may be constant or descending, and nonfinite propagation (FR-451 R3, PFS-2081.119, REL5-003).
- Geometry preflight checks every promoted artifact, including scripts, logs and sidecars. Sweep variants remain staged until all solver runs, audits and the overlay succeed, preserving prior outputs on failure (FR-471 R9, FR-472 R7, SWEEP-01, SWEEP-02).
