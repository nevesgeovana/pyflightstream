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
