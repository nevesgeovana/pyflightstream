# One row, one geometry, turned or moved

The row keys `ROTATE` and `TRANSLATE`, which turn or move part of the geometry for one row.

## One row, one geometry, turned

An installed rotor's incidence is a parametric study: the same mesh, the
blade and spinner families turned a few degrees in pitch or in toe, one
run per angle. A row states that turn in its cell
(PFS-2034.02, the design of 2026-09-09) and the geometry file stays what
it was:

```text
ROTATE: {ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}
```

`ROTATE` is a list of records with the `MOTIONS` grammar, braces around
each record, commas between them, `/` between the pairs inside. Each
record is ONE rotation and two records are two rotations in the order
written, so a pitch and then a toe is `{...}, {...}`. `ANGLE` is in
degrees; `AXIS` names a coordinate system and one of its axes, as
`PUSHER_SMRP-Y`, where the system is one the row's REFERENCE declares in
its `[[frames]]` table (above) or one the package creates itself (`MRP` on
every run type; and a rotor's own
`<ALIAS>_SMRP`, `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>`).

**`ALIAS` names what turns, and it is the same word a motion uses.** That
is the whole of the 0.15.0 change here: after it, every surface of this
package that names a group of boundaries names it by alias, and the
reference is the one place a study says what its groups are.

It names **exactly one** word the reference declares. Unlike
`MOVING_BC_ALIAS` it does not fall through to a bare label or a family:
a rotation carries the frames of the thing it turns, and those belong to
one rotor, so `ALIAS: PUSHER,LIFT_L1` is refused telling you to write one
record per alias, `{...}, {...}`. A word the reference does not declare
at all is refused naming it and listing the ones it does.

**EVERY FRAME THE ALIAS OWNS TURNS WITH IT**, which is why `AUX_FRAMES`
retires. A rotor's frames are placed FROM its hub, so turning the rotor
and leaving them behind was stating an incidence the axes never got, and
a row had to list them by hand to fix it. Turning `PUSHER` turns
`PUSHER_SMRP`, `PUSHER_RMRP` and every `PUSHER_RMRP<k>`, so the motion
created after it spins about the pitched axis and the blade loads a pproc
entry reads in those frames stay in the blade's own axes, with nothing
else to write. An alias that is not a rotor owns no frame and turns none.

`FAMILIES` is the 0.14.0 spelling of `ALIAS` and is REFUSED naming `ALIAS` as the word to write. A record stating `ALIAS` and
`FAMILIES` both is refused for a second reason: one rotation turns ONE
set.

`AUX_FRAMES` is **not deprecated and not removed**: it is no longer
NEEDED for a rotor, because the alias carries that rotor's frames, and it
still names any frame you want turned that the alias does not own. Naming
a frame the alias already carries costs nothing, since no frame turns
twice however many names it answers to.

**Migrating a `FAMILIES` record.** The key changes AND SO DOES THE VALUE:
`FAMILIES: Blade,S` becomes `ALIAS: PUSHER`, the rotor those families
belong to, not the list itself. The refusal names the words the
reference declares, so the value is in front of whoever reads it. A families list
spanning two rotors becomes one record per rotor. `ANGLE` and `AXIS` are
unaffected.

The rotation is emitted after every frame exists and before any motion is
created, on every run type. One row is one geometry, so the angles of a
study are one row each, and the sweep column keeps its meaning: the
reserved key `angle_sweep_deg` (the reserved-keys paragraph above) is
still read as a geometric rotation sweep of its own, and a row sweeping it
beside an aerodynamic axis is refused as it always was; it is not the way
to state the study's angles, `ROTATE` is.

A family the geometry lacks, a frame nothing defined, an axis token not of
the form `frame-axis`, a record missing one of its three keys or carrying a
key a rotation does not read, an angle that is not a number, and the key on
a `LEGACY` row (whose recipe reads its keys and reads no rotation) are each
refused at `pyfs-matrix plan` naming the row, and the first two name what
the case DOES define:

```text
case '1020' states ROTATE with 'NoSuchFamily', and the sidecar
30_BLADE.boundaries.toml beside 30_BLADE.fsm declares no boundary of that
name or family; it declares 'Blade1', 'S', 'N'. Write one of those, or a
family name (the label without its trailing number) to select every member
the file carries.
```

A rotor row that turns its blades and does not name the frame they spin
about among the auxiliaries (`<ALIAS>_SMRP` on a flat row, one per rotor and so
on for the records of a `MOTIONS` row) is accepted and WARNS naming the
frame: the blades turn and the axis stays, which is a physics call the row
may mean, so it is not refused.

What the solver does with the rotated mesh is the measurement of the seat
run the reference study books (PFS-2034.05): the package emits the rotation the
manual documents, citing a frame the manual's own sample cites, and the
run record is where the accepted geometry will be read from.

## One row, one geometry, moved

A study that moves a part of the aircraft, a rotor aft along its hub or a wing
down the body, states the move in its row, with the grammar a turn uses:

```text
TRANSLATE: {DISTANCE: 0.05 / AXIS: PUSHER_SMRP-X / ALIAS: PUSHER}, {DISTANCE: -0.02 / AXIS: PUSHER_SMRP-Z / ALIAS: PUSHER}
```

Each record is ONE translation, and two records are two, in the order written.
`DISTANCE` is in **metres**, as `ANGLE` is in degrees, and it moves the alias
along ONE axis of the named frame, so a diagonal is two records. `AXIS` names a
coordinate system and one of its axes exactly as a rotation's does, and `ALIAS`
names exactly one word the reference declares. `AUX_FRAMES` names frames the
alias does not own that move with it: `MRP`, to keep the moments about the same
point of the moved part.

**EVERY TRANSLATION COMES BEFORE EVERY ROTATION**, so a row that states both
places the part and then turns it about its frame where the frame now is:

```text
TRANSLATE: {DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: airframe / AUX_FRAMES: MRP} / ROTATE: {ANGLE: 2 / AXIS: MRP-Y / ALIAS: airframe / AUX_FRAMES: MRP}
```

**THE FRAMES THE ALIAS OWNS MOVE WITH IT**, as they turn with it: moving
`PUSHER` moves `PUSHER_SMRP`, `PUSHER_RMRP` and every `PUSHER_RMRP<k>`, each
once, so the motion created after it is placed about the moved hub; that it
spins there has not been run on the solver.
`PUSHER_SMRP_ORIGINAL` keeps the hub as it stood before the row moved or turned
anything, one copy for both, and a post-processing entry naming the moved hub
is written in both frames.

**A MOVED SET COMES AWAY FROM WHAT IT TOUCHES.** Each surface is moved with its
vertices split from its neighbours, so every vertex of the set moves exactly
once and every other surface stays where it was (RPT-048, on 26.123). Moving
the whole aircraft leaves it whole. Moving a wing alone leaves the body whole
and the wing root no longer joined to it: that was observed on the saved mesh
and not solved, and whether such a model is acceptable is the study's call.

A frame moves to an ABSOLUTE origin, which the package computes from where its
script placed the frame, reading that origin in metres: a frame is placed in the
simulation's length unit, so a translation is right only on a simulation whose
length unit is metres. A frame it cannot place is refused by name rather than
moved to a guess, and the axis of a frame it cannot orient is refused the same
way: a blade frame is turned into place, so move along its hub frame instead.

One row is one position, so a translation is not swept; the positions of a
study are one row each, beside an aerodynamic sweep if the row has one. The
refusals are a rotation's, at `pyfs-matrix plan` and naming the row: a key a
translation does not read (`UNITS` and `FAMILIES` included), a missing
`DISTANCE` or `AXIS`, no alias, a distance that is not a finite number, an axis
token of another shape, an alias the reference does not declare or a list of
them, a frame nothing defines, an axis of zero length, and the key on a
`LEGACY` row.

**A row's move is not the geometry's.** A raw mesh's own scale, rename,
mirror, translation and rotation, the ones that make the file into the body,
are declared once in its sidecar as `[[import.operations]]` and applied right
after the import, before any frame exists, for every row that names the file
([mesh inputs](mesh-inputs.md#the-mesh-operations-of-an-import)). `TRANSLATE`
and `ROTATE` are the study's moves, per row, after the frames, and they act on
the body those operations left.
