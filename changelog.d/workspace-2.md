## Migration

- `--hpc` accepts a file extension like `--cost-file`; both
  selections are restored when a CLI invocation ends.
- Invalid cost references and curve entries, malformed HPC tables
  and quoted `export_log` booleans now raise named input refusals. Invalid
  UTF-8 in workspace settings, TOML artifacts and reference points names the file.
- Negative speed and nonpositive Reynolds constraints are refused;
  zero speed without a Reynolds constraint remains valid for hover.
- `subtract_fields` matches points one to one and refuses ambiguous
  matches with `WorkspaceError`, including under optimized Python.
- Missing FSI inputs list available ids, placeholder calibration
  cells beside no FSI input are ignored, and unity calibration preserves a
  stated shear modulus. Recomputed shear modulus records its origin.
- Rotor alias groups compare without case and cannot bypass the
  member agreement check; retired rotor-field refusals name `rpm_sign`.
- A failed job propagates its verdict to unmarked points. Point
  records retain their own iteration limits and residual notes.
- Group renaming works below an ancestor named `archive`; its
  archive stamps use the same local clock as other archive writers.
- A synchronization does not import another workspace's deletion
  notes. Renumbering refusal text names the other matrix as the remedy.
- Workspace settings parsers refuse abbreviated options. Archive
  help describes recorded simulations and states that status is not checked.
  Build-version refusals name the actual registry overlay. Script comparison
  places appended commands after the last executed line.
- Truncated Excel bridge records receive an error response,
  partial apply returns 1, and workbook edits preserve following cells and rows.
- Refinement preserves exact listed trailing edges, including wake
  gaps. A grid whose listed edges are not complete grid lines takes the remesh
  route under `auto`, or refuses an explicit `grid` request.
- Detected trailing-edge points require declared mesh units.
  Ambiguous sharp extremes require a family `trailing_edge_direction` vector
  in the refinement file, pointing from leading to trailing edge. Listed
  points keep precedence.
- Shared-edge targets are converted to metres when mesh units are
  declared; otherwise `shared_edge_target_mesh_units` replaces the misleading
  metre label. The internal remesh result uses the native-unit key.
  `refine.json` schema version is now 2; the audit schema remains 1.
- Refinement records retain every requested family, duplicate
  trailing-edge points are removed, frozen trailing edges remain labelled,
  and a missing remesh edge ratio is JSON null. A periodic body with unequal
  axial and circumferential factors is refused.
- `refine_mesh` accepts one family string, resolves a bare filename
  before choosing the output directory, wraps a missing OBJ as an input
  refusal, and attributes the rebuilt-neighbor warning to the caller.
- Setup inspection uses `cases.workflows.row_solver_setting` to
  report the same value and row provenance as the builder.
- Release decisions still required: flight-condition thermodynamic pins and
  whether a detected refinement edge must replace the output sidecar's solver
  detection route. These items are not claimed fixed here.
