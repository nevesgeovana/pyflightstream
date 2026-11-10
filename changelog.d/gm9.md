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
