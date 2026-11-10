Control-stage kernel support now splits imported faces along their own parameter
lines while retaining existing trims, and measures minimum clearance between
trimmed face sets with the native kernel distance operation.

The provisional geometry stages facade also supplies a pinned-skin partition:
stationary and moving pieces share the original skin through iso trims, with
separate exact boundary-matched closure bases. Physical gaps, motion and the
control-surface command are not supplied by this partition helper.

Migration: none for existing callers; two kernel adapter operations are additive.

Control sub-step checks measure written/read face counts, sewn free and triple
edges at 0.01 mm, native clearance to hosts, and named slot openings. Post-cut
checks accept named junction lengths and clean-reference lengths; their shared
trimmed-assembly integration remains pending.
Each F check has its own stage-table row and runner callback. Supplied control
boundaries produce stage records and geom-run.log lines; a failed check stops
the runner before the next sub-step.

Resolved plain-flap and aileron entries now produce stationary iso trims,
closed moving pieces, span gaps and rigid deflections in the placed component
frame. F0, F1, F2 and F4 read and measure those files; applied-controls.json
carries the numerical bases and trims for subsequent export integration.

The add-control-surface verb and API now apply plain controls to normalized
polynomial IGES skins. Native iso splitting retains source trims and unrelated
components; new boundary closures and rigid motions produce separate named
pieces. The returned record reports sewn closure and the input digest.

Configured body hosts now feed F3 automatically. Native face-set distances
and the source-file digests appear in the stage record and run log. Applicable
F5/F6 waits remain incomplete until the trimmed assembly boundary is supplied.

Combined checks now include one angle choice from every control, so a second
control cannot disappear from an otherwise closed main/control configuration.

Explicit exposed roots map eta into the planform semispan. Named engine
bounding sections split a control into closed inboard and outboard pieces;
missing bounds retain one piece with a recorded warning. Host-derived limits
without a measured boundary refuse instead of using an invented station.

Stated Fowler entries now construct a square cove, an elliptic nose and a
closed nested flap. Cove faces split at every skin span knot. Each deployed
flap uses one rigid pivot-axis rotation and translation; gap and overlap are
measured on the polynomial section curves at 49 span stations. Exterior
identity is measured outside the nose and lip gap bands. The single cove p3
station specifies a constant normalized roof-wall height over the span.

Fowler cove bays, nesting, motion laws and retracted exterior each have a
separate stage record and run-log entry. The imported-skin edit also builds
the cove and nose, preserving source trims on the retained exterior faces.

F7 builds the requested registry variant automatically, retaining all selected
components and all angle combinations of the active controls. A standalone
vertical surface receives a planar root cap; its measured area and the
combined files' sewn free and triple edges appear in the F7 record.

Fowler measurements now inspect the actual applied bases. A changed flap
position, altered exterior, reduced nesting clearance or missing cove bay
fails its own check. A failing nesting check stops at FW2 before motion-law
records are written. The strict 0.01 percent chord law threshold is recorded.

F7 applies configured host junctions using exact restricted control faces
and the existing measured assembly operations. Junction lengths and the
assembly sub-step records accompany each angle combination; sewn closure
alone cannot stand in for a junction that was never formed.

Imported-control validation preserves caller tables. A swapped file/table
input raises InputValueError, and unknown nested keys remain visible in
the returned warnings without being removed from the caller's data.

For example, apply a stated Fowler entry to a normalized polynomial skin
whose lower trailing edge is u=0, leading edge u=0.5 and upper trailing edge
u=1, with v running along the span. This entry is exercised by the public
edit regression test:

```toml
[[control]]
name = "flap"
kind = "fowler"
eta = [0.2, 0.7]
chord_ratio = 0.25
gap_span = 0.01
deflection_deg = [0, 15]
cove = {wall_x = 0.72, lip_x = 0.94, p3 = {eta = 0.45, z_over_c = 0.035}}
nose = {kind = "elliptic", radius = 0.01}
nested_dz_pct = -0.2
clearance_pct = 0.1
kinematics = [{deflection_deg = 15, pivot_x = 0.75, pivot_z = -0.1, gap_pct = 2.0, overlap_pct = 1.0}]
```

Read the entry with `tomllib` and pass its `control` list to
`workspace.geometry_pipeline.add_control_surfaces("panel.igs", "panel", entries, "fowler.igs")`.
The returned record includes the Fowler measurements and warnings; the output
contains separately named main and angle alternatives. Registry variants
select the active controls and F7 checks each angle combination separately.
