"""Refining, coarsening and auditing a panel mesh from its OBJ (FR-424 to FR-428).

A private package of the workspace layer. It imports nothing of ``run``; the
command layer reaches it only through ``refine_mesh`` and ``audit_mesh`` of
:mod:`pyflightstream.workspace`. Its modules, from the floor up:

- ``_geometry``: the thresholds the requirements name, each defined once, and
  the shared geometric primitives;
- ``_obj``: the OBJ and trailing-edge points files;
- ``_audit``: the audit of a level against its source (FR-426), which imports
  nothing of the refinement modules;
- ``_grid``: the structured grid of a family, recovered and resampled (FR-920, FR-921);
- ``_remesh_group`` and ``_remesh_pairs``: the group a remesh works on, and the
  pairing of its triangles into quadrilaterals;
- ``_remesh``: the remeshing of the other families, with conforming interfaces
  (FR-922, FR-933);
- ``_config``: the refinement file (FR-916, FR-917);
- ``_level``: the orchestration that writes a level (FR-424, FR-425).
"""
