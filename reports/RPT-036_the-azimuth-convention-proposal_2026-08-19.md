# RPT-036: the azimuth convention, as a proposal (2026-08-19, amended 2026-08-19)

> **Amended the same day, by the change that invalidated its premise.**
>
> This report was written stating that the propeller descriptor records
> `clockwise` or `counterclockwise`, and part 3 below rests on that
> two-word domain. Hours later `PFS-2009.02` checked the shipped
> vocabulary against a real campaign's library for the first time and
> found it refusing that campaign's own reference artifact: the sense was
> recorded in the vocabulary a vendor datasheet prints, where the blade
> nearest the fuselage travels, and two MEASURED signs had nowhere to
> live at all.
>
> Two consequences for this report, and the second is larger than the
> first.
>
> The descriptor now carries `blade_travel` beside `rotation`, so a
> reader arriving here holding an artifact in the published vocabulary
> finds a proposal that cannot decide their case. `rotation` itself is
> unchanged and part 3 still describes it correctly.
>
> AND THE DESCRIPTOR NOW CARRIES A MEASUREMENT OF A NEIGHBOURING
> QUANTITY, which is a weaker statement than the one this paragraph
> made until a review pass read it against itself.
>
> What it said: that the recorded signs are "the thing part 3 proposes
> to DERIVE", that half of question 3 is now built, and that a ruling
> could close part 3 by deletion. Then, four paragraphs on, that the two
> are different quantities and that the amendment does not conflate
> them. Both were published at once, which is the exact fault the same
> day's work corrected in the model docstring, the CHANGELOG and the
> plan item. Corrected here rather than defended:
>
> `rpm_sign_installed` and `rpm_sign_isolated` sign the ROTOR SPEED.
> `ROTATION_SENSE_SIGN` signs the AZIMUTH INCREMENT, which way round
> the disc the blades are numbered. Part 3 is about the second, so a
> recorded rotor-speed sign does not supersede it and cannot close it
> by deletion. What it does is nearer and worth the ruling anyway: a
> measured sign about the emitted rotor axis fixes the physical
> direction of rotation, and the azimuth increment follows from that
> IF blades are numbered with the rotation, which is a separate
> convention this report has not settled either.
>
> And nothing about the DATUM is built. Question 3 asks whether the
> descriptor should carry the azimuth zero per propeller;
> `AZIMUTH_BASIS` is still one library-wide table and no new field
> carries a datum.

A blade frame has to be placed somewhere, and placing it requires an
answer to a question nobody in this repository is entitled to settle:
where azimuth zero points, and which way azimuth grows.

This report states the convention `blade_frames` was built under
(PFS-2025.04), says exactly what it costs if it is wrong, and asks the
domain expert to confirm it or replace it. **It is a PROPOSAL and not a
finding.** No solver was run for it and it costs no licensed seat.

## Why this one is written down and other defaults are not

Most defaults taken under time pressure announce themselves: the wrong
one raises, or emits a line the solver refuses, or produces a number so
far out that a reader stops. This one does none of that.

A wrong azimuth datum rotates every blade frame by the same angle. The
geometry still loads, the motion still binds, the script still renders,
the solver still converges, and every coefficient that is not
phase-resolved is unchanged, because a rigid rotation of the frames
about the rotation axis leaves the total force alone. What changes is
the meaning of the per-blade quantities: blade 1 is no longer the blade
the descriptor calls blade 1, and every phase-locked reduction keyed to
blade index is keyed to the wrong blade.

So the failure mode is plausible numbers, and it survives review by
anyone who is checking that the run worked. That is the whole reason
this file exists.

## The proposal

Three parts, and each one is separately refusable.

**1. The in-plane pair is cyclic.** For a rotor axis of X the in-plane
pair is (Y, Z); for Y it is (Z, X); for Z it is (X, Y). The consequence
of choosing the cyclic order rather than any other is that the first
crossed with the second is the rotor axis itself, for all three, so the
blade frame comes out right-handed with its third axis along the
rotation without a special case anywhere.

**2. Azimuth zero lies along the first of each pair.** A rotor about Z
has its azimuth zero along +X; about X, along +Y; about Y, along +Z.

**3. Positive azimuth follows the recorded sense of rotation.**
`PropellerReference.rotation` records `clockwise` or `counterclockwise`,
and since 2026-08-19 the descriptor ALSO carries `blade_travel`, the
same fact in the vocabulary a vendor datasheet prints. This proposal is
about `rotation` alone: `blade_travel` is side-independent, so the left
and the right propeller of a pair carry the same word and it resolves to
a viewed-from-behind sense only once the side is known. The proposal
maps `counterclockwise` to the
mathematically positive sense about the rotor axis as the frame points
it, so blade k sits at `anchor + k * 360/N`, and `clockwise` to the
negative one.

Part 3 is the weakest of the three and is the one most likely to be
wrong. The descriptor states its sense **as seen from behind the
aircraft looking forward**, which is a statement about a viewing
direction and not about the sign of a rotation vector. Whether
`counterclockwise` seen that way is positive about +X, about -X, or
about whichever way the rotor axis argument happens to be given, is
exactly the substitution this repository cannot make on its own.

## Where the convention lives in the code

One table, one reader, and both are named so that changing the answer is
one edit rather than a search:

| Name | File | What it decides |
|---|---|---|
| `AZIMUTH_BASIS` | `src/pyflightstream/script/helpers.py` | the datum and quadrature vector of each rotor axis, which is parts 1 and 2 |
| `ROTATION_SENSE_SIGN` | same file | which recorded sense signs the azimuth increment, which is part 3 |
| `azimuth_basis()` | same file | the only reader of the table |

`tests/test_script_helpers.py::test_the_azimuth_datum_is_one_named_table_and_changing_it_is_one_edit`
substitutes a different datum for the Z axis and asserts that the
emitted radial direction follows it. STATED EXACTLY, because this
paragraph claimed more until a review pass measured it: that case proves
the Z path of `blade_frames` READS the table. It would not notice a
second datum decision in another helper, or in the X or Y path, which is
what "changing it is one edit" needs.

The claim is true today and the mechanism is now the one that carries
it: `test_the_azimuth_datum_has_exactly_one_reader_in_the_package`
asserts that no module outside `azimuth_basis()` reads `AZIMUTH_BASIS`,
by parsing rather than by grepping, and fails with the reader that
appeared.

## What is NOT proposed here

The anchor restriction is the author's own instruction and is not part
of this proposal: the first blade must lie at 0, 90, 180 or 270 degrees,
the other blades are placed arithmetically at 360/N from it, and nothing
computes a centroid or reads a mesh. A first blade measured anywhere
else is refused, with the measured angle named.

Nothing here is a claim about the solver. `CREATE_NEW_COORDINATE_SYSTEM`
and `EDIT_COORDINATE_SYSTEM` are the commands the placement emits and
their evidence is unchanged by this report.

## The question, in the form an answer can take

1. Is the cyclic in-plane pair the right one, or does a rotor about Z
   take its azimuth zero somewhere other than +X?
2. Does `counterclockwise` in a propeller descriptor mean the
   mathematically positive sense about the rotor axis as passed, or
   about the axis pointing aft, or something the descriptor should state
   separately?
3. Should the descriptor carry the datum itself, per propeller, instead
   of the library carrying one convention for every rotor?
4. ADDED 2026-08-19, and CORRECTED the same day, because the first
   wording asked whether a recorded rotor-speed sign should supersede
   the azimuth-increment derivation, which conflates the two
   quantities this report exists to keep apart. As it should have been
   asked: the descriptor now records a MEASURED rotor-speed sign per
   mesh family, which fixes the physical direction of rotation about
   the emitted axis. Should the azimuth increment be REACHED from that
   measurement, rather than derived from the published sense, for a
   descriptor that carries one? Answering yes needs a second
   convention stated as well, that blades are numbered with the
   rotation rather than against it, and it would leave
   `ROTATION_SENSE_SIGN` as the fallback for descriptors that record
   no measurement.
5. And, if a descriptor carries `blade_travel` and no `rotation`, what
   does the library do? Today `rotation` is required and `blade_travel`
   is optional, which is a decision this widening took by default
   rather than by ruling.

A yes to all of 1 and 2 closes this report with no code change. A no to
either is one edit in the table above plus one test expectation.

## Status

Open. The code is built under the proposal, the item is `implemented`
and deliberately not `evidenced`, and nothing downstream should read the
per-blade azimuth as settled until this is answered.
