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
