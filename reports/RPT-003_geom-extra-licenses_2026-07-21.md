# RPT-003: geometry-engine license verification (NFR-02 gate for the [geom] extra)

Date: 2026-07-21. Evidence gathered from the installed package
metadata (`pip show`, versions below, accessed 2026-07-21) before
adding the `[geom]` optional extra required by the probe planner's
geometry gate (point-in-body culling and distance-to-surface queries
for the planar probe grids; SRS NFR-02: dependency licenses must be
MIT-compatible; engineering policy of 2026-07-21: public libraries
for generic needs).

## Finding

| Package | Version checked | License | Verdict |
|---|---|---|---|
| trimesh | 4.12.2 | MIT | MIT-compatible |
| rtree | 1.4.1 | MIT (`License-Expression: MIT`; wraps libspatialindex, MIT) | MIT-compatible |
| scipy | 1.18.0 | BSD-3-Clause | MIT-compatible |

## Notes

* scipy wheels bundle OpenBLAS (BSD-3-Clause), LAPACK (BSD-style),
  and the GCC runtime library (GPL-3.0 with the GCC Runtime Library
  Exception, the standard exception that permits redistribution with
  non-GPL code); all are redistribution-compatible with an MIT
  project and standard across the scientific Python stack.
* trimesh pulls only numpy by default; the containment and proximity
  queries used by `probes/geometry.py` additionally need rtree and
  scipy, which is why the extra pins all three explicitly instead of
  relying on trimesh's own optional extras.
* This check gates only the `[geom]` optional extra. The core runtime
  dependency set (NFR-06) is unchanged; without the extra, planar
  grids build and emit normally and only the geometry gate refuses,
  with a didactic message naming the extra.
