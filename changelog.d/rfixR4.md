## Fixed

- OBJ-only deflection sweeps now retain solver meshes until the required sweep overlay is produced. Unreadable or empty selected surfaces give an explicit failure, and a previous overlay cannot appear current after a failed build (FR-470 R1, FR-472 R7, PFS-2081.108, REL4-001).
- Filtered sweeps keep the original one-based angle_deg positions in the overlay's variant cell labels, including the third angle and noncontiguous selections (FR-472 R7, PFS-2081.109, REL4-002).
