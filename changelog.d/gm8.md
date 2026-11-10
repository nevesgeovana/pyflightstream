Fix the IGES reader-profile distance check for surfaces with unequal parameter
ranges and for points near a parameter bound.

migration: No input change; valid boundary curves near parameter bounds no longer
fail the surface-distance check because of finite-difference scaling.

Measure shared cap boundaries at S8, including the corner-cap side edges, and
stop the run with `closure.cap_edge_gap` when the gap exceeds 0.005 mm.
