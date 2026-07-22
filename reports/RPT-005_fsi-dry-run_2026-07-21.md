# RPT-005: WP1 FSI dry run on FlightStream 26.120 (2026-07-21)

The WP1 dry run of the M6 FSI line (DLV-007 Section 7), executed on
the licensed local machine with FlightStream 26.120 build 7012026 and
the `pyfs-fsi` dummy executable. Vehicle: the shareable generic-blade
case 9002 flow (HND-022) shortened to half a revolution (18 unsteady
steps at 10 deg per step, rpm 472.83, PERIODIC 6, one meshed blade),
with the aeroelastic coupling attached. Four runs, evidence-driven:

| Run | Change | Outcome |
|---|---|---|
| 1 | 9002 flow plus the SET_MOTION_FSI pair (SRC-003 pp.335-336, manual-exact grammar) | Script abort: `SET_MOTION_FSI_STRUCTURAL_NODES` unrecognized by build 7012026 |
| 2 (probe) | Minimal script with `SET_MOTION_FSI_EXECUTABLE` alone | Unrecognized as well: the whole pp.335-336 family is not implemented in this build |
| 3 | Aeroelastic Coupling Toolbox family (SRC-003 pp.375-376) | Coupled loop closed: 18 executable calls, 1 per time step; no loads file yet (post-processing script had an inline-path syntax error) |
| 4 | Post-processing export path on its own line | Complete: loads file produced and archived at every call, no errors |

## Findings (the DLV-007 Section 3 open questions, closed)

1. Command family: the implemented scripting interface is the
   Aeroelastic Coupling Toolbox family (`ASSIGN_AEROELASTIC_*`,
   `IMPORT_AEROELASTIC_STRUCTURAL_NODES`,
   `SET_AEROELASTIC_WORKING_DIRECTORY`,
   `SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND`,
   `SET_AEROELASTIC_POST_PROCESSING_SCRIPT`,
   `SET_AEROELASTIC_ITERATIONS`, `SET_AEROELASTIC_COUPLING_IN_UNSTEADY`,
   `EXECUTE_AEROELASTIC_ANALYSIS`, `DELETE_AEROELASTIC_STRUCTURAL_NODES`,
   `AEROELASTIC_RBF_TYPE`), new in 26.1 per the release notes and
   documented at SRC-003 pp.375-376 and p.345. The
   `SET_MOTION_FSI_EXECUTABLE` / `SET_MOTION_FSI_STRUCTURAL_NODES`
   pair of the motion chapter (pp.335-336) is rejected as
   unrecognized despite manual-exact grammar: stale manual section,
   candidate broken (PLN-019).
2. Call convention: the executable is invoked bare, no arguments,
   once per time step (`SET_AEROELASTIC_ITERATIONS 1`), with the
   working directory of the process equal to the directory set by
   `SET_AEROELASTIC_WORKING_DIRECTORY`. Console output of the
   executable is captured into `FSI_output.txt` there (empty for the
   file-only dummy).
3. Loads export cadence and content: `FS_SurfaceSection_Loads.txt`
   is produced by the user-supplied post-processing script that
   FlightStream runs between FSI iterations, before the executable
   (`UPDATE_ALL_SURFACE_SECTIONS`, `COMPUTE_SURFACE_SECTIONAL_LOADS
   NEWTONS`, `EXPORT_SURFACE_SECTIONAL_LOADS` with the path on its
   own line). Fresh content each step, verified by the advancing
   `Current solver iteration number` header line (154, 504, 722 at
   calls 2, 10, 18) and differing data rows.
4. Header and units: the file carries the standard FlightStream
   output header with units in the labels (`Freestream velocity
   (m/s)`, `Reference area (m^2)`), so the WP2 SI assertion anchors
   on labeled values exactly like the existing `results/` parsers;
   the force units are chosen by the post-processing script itself
   (NEWTONS). Data table: `Offset, Chord, X_QC, Z_QC, Fx, Fz,
   Moment` per section, moments about the quarter chord, which is
   the pitch axis reference of DLV-007 Section 4.3.
5. File formats: the structural node import is three comma separated
   columns X,Y,Z per node (11 nodes on the blade pitch axis imported
   cleanly, coordinate system selectable at import); `FSIDisp.txt`
   is comma separated `dx,dy,dz` per node in import order (SRC-003
   pp.273-274). The dummy now writes commas.
6. Blade identification: closed by the author's standing modeling
   convention (2026-07-21, confirmed on a legacy multi-boundary SMI
   propeller run in her research archive): every blade is meshed as
   its own geometry family (boundary), and each blade gets its own
   section distribution targeting that boundary's surface index in
   the blade's rotating frame. The export is one flat table with the
   families concatenated in creation order, block sizes equal to
   each family's section count (verified in the legacy export, three
   families of 50, and in this run's fixtures, two families of 50);
   offset and chord discontinuities at the block boundaries give the
   parser a cross-check. Attribution is therefore bookkeeping owned
   by the code that creates the distributions, the same
   single-source-of-truth discipline as FSI-R14, not label parsing.

## Committed fixtures (`tests/fixtures/fsi/`)

`FS_SurfaceSection_Loads_call0002.txt` and `_call0018.txt` (early and
late step), `FSIDisp.txt`, `structural_nodes.csv`,
`fsi_postproc_script.txt`, and the sanitized `pyfs_fsi_calls.log`
(run-folder paths replaced by `C:\runtime`). All from the synthetic
generic blade; no research geometry involved. Committed fixtures are
whitespace-normalized by the repository hooks (trailing whitespace
stripped), the same discipline as the earlier real-output fixtures;
the parser anchors on labels and delimiters, never on trailing
spaces.

## Pending

* Formal Tier 2 promotion of the aeroelastic family (verified) and
  the SET_MOTION_FSI pair (broken) through the validity sweep
  machinery: PLN-019.
* `FSLoadDistributions.txt` (raw grid-node forces): its export
  toggle is documented only in the Toolbox GUI settings (SRC-003
  p.273); not needed for the DLV-007 contract, not pursued.
* 26.100 support for the family is unprobed (the family is new in
  26.1; both local builds print 26.1).
