## `per_blade`

Each blade is a family row of the polar files, so the `per_blade` table is no longer
written. A blade declared in a rotor is a row of
[`FAM-ACOEF`](../pproc/fam-acoef.md) with its airframe coefficients and of
[`FAM-RCOEF`](../pproc/fam-rcoef.md) with its rotor loads and loadings, keyed by
`FAMILY` and `FAMILY_ID`, and the rotor as a whole is the group of its own
[group files](../pproc/group-files.md).

**The window is shared by every blade of a rotor.** Averaging each blade over its
own passage would put each in a different part of the history, so a difference
between two blades would mix a real azimuthal difference with a difference in when
each was sampled. Every family of a point is averaged over the one window of the
row, and that window is stated in the [run block](the-run-block.md#the-run-block).
On a multi-rotor row the window is counted in the revolutions of the clock rotor.

The public Python helper `ReductionPlan.blade_windows()` has a separate contract: it
partitions the last revolution into disjoint, inclusive blade-passage windows. Those
windows sample different parts of the history, so differences between their means can
include temporal variation. It remains available for that quantity and does not define
the shared averaging window of the polar files.

The blades of a rotor are the `families_blades` of its block in the reference
artifact, in the order of the frames' right-hand rule about the rotor shaft,
independently of the sign of the speed. Planning checks readable blade centroids
against that order and refuses a mismatch.

Where a blade's own azimuthal variation is wanted, the
[`phase_locked`](phase_locked.md#phase_locked) table is one row per azimuth of the
revolution, and the [per-station harmonics](the-per-station-harmonics.md#the-per-station-harmonics)
fit it per station.
