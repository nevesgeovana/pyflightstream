"""Refining, coarsening and auditing a panel mesh from its OBJ (FR-424 to FR-428).

A private package of the workspace layer. It imports nothing of ``run``; the
command layer reaches it only through ``refine_mesh`` and ``audit_mesh`` of
:mod:`pyflightstream.workspace`. Its modules, from the floor up:

- ``_limits``: every numerical threshold, defined once;
- ``_obj``: the OBJ and trailing-edge points files;
- ``_audit``: the audit of a level against its source (FR-426), which imports
  nothing of the refinement modules;
- ``_grid``: the structured grid of a family, recovered and resampled (FR-424 R6, R7);
- ``_remesh``: the remeshing of the other families, with conforming interfaces
  (FR-424 R8, FR-425 R2);
- ``_config``: the refinement file (FR-424 R2, R3);
- ``_level``: the orchestration that writes a level (FR-424, FR-425).
"""
