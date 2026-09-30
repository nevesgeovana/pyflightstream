# The reference artifact

What a reference artifact holds beyond the three lengths, and the study's vocabulary it declares.

## What a reference artifact holds beyond the three lengths

The two reference files of [the input library](workflow-input-library.md) carry only the lengths the sweep table needed. A
reference artifact also carries a FOURTH length for a propelled
configuration, the moment point, and a `[rotor]` block. This is
`inputs/references/r003.toml` in full, the same artifact the listing
above summarises by its first three lengths:

```toml
area_m2 = 10.0
chord_m = 1.2
span_m = 8.0
rotor_diameter_m = 2.0

[moment_point]
x_m = 0.3
y_m = 0.0
z_m = 0.0

[rotor]
radius_m = 1.0
n_blades = 3
pitch_deg = 0.0
toe_deg = 0.0

[rotor.position]
x_m = 0.0
y_m = 0.0
z_m = 0.0
```

`rotor_diameter_m` SITS WITH THE OTHER LENGTHS AND NOT IN THE
`[rotor]` BLOCK, which is the natural-looking home and the wrong one.
The recorded rotor block is recorded metadata of which this package reads
ONE field, the position, since 0.11.0 (the unsteady run types create the
rotor hub frame there); the diameter is a DIVISOR of published numbers,
exactly like the area and the chord. It is what an advance ratio is a ratio against, so a
row stating `ADVANCE_RATIO` and a reference without this field is
refused naming the field to add, and it is what the rotor
coefficients normalise on. It is optional, because a configuration with
no rotor has no diameter and a placeholder would be worse than
nothing.

`[rotor.position]` is the hub position in the simulation geometry
frame, in m, and it defaults to the origin if you leave the table out,
which is a default and not a measurement.

THE SENSE OF ROTATION AND THE SIGNS OF THE ROTOR SPEED ARE NOT HERE since
v0.11.0 (PFS-2029.08). Until 0.10.1 the block carried `rotation`,
`blade_travel`, `rpm_sign_installed` and `rpm_sign_isolated`; no emitter
read them, and the two signs named a configuration, installed against
isolated, which is a property of the mesh a ROW opens and not of
reference data several rows share. From 0.11.0 to 0.21.1 a row stated the
sign, in `RPM_SIGN` beside `ADVANCE_RATIO` or inside the `RPM` value;
since 0.22.0 the hand is `rpm_sign` on the rotor's OWN block, which is
per-rotor rather than per-configuration and so answers the installed and
isolated case the four fields were reaching for. An artifact still
carrying any of the four is refused naming the row keys;
`pyfs-matrix upgrade --inputs` strips them. The measured argument behind
the signs, and the derivation from a published sense to a sign, are on
[the mesh inputs page](mesh-inputs.md).

## The reference declares the study's vocabulary

Since 0.15.0 this artifact is where a study says what its boundaries are
CALLED, and it is the first thing to write when you set a workspace up: the
rows that come later cite these names and nothing else. Three tables carry
it, and the paragraphs above them are written for a configuration with ONE
rotor (FR-59, FR-60, FR-72).

    [aliases]                  a name for a set of boundaries; a member
                               may be another alias, resolved to the end
    [[frames]]                 the custom coordinate systems, moved here
                               from the setup preset
    [<ROTOR>] kind = "rotor"  one block per rotor, and the block's NAME
                               is an alias over everything it owns

Since 0.27.0 a fourth kind of block sits beside them: `[<DISC>] kind =
"actuator"`, an actuator disc a row names by its block's name
([One row, one actuator disc](workflow-row-flow-inputs.md#one-row-one-actuator-disc)).

ONE WORD, AND IT IS ROTOR. The block, the key, the frame, the point and
the probe scale all say it, because a propeller is a rotor and so is a
lift fan: the general word is the one that never has to be changed again
when the aircraft does. Every spelling this replaced is refused naming
what to write instead, so a file written before 0.15.0 stops rather than
running under a word that means something else now.

A rotor block states `alias` (optional, and equal to its name), the hub
as `x_m`, `y_m`, `z_m`, then `axis`, `rpm_sign`, `diameter_m`,
`families_general`, `families_blades` and `blade1`. **The blade count
is the length of `families_blades`** and nothing else, so a row states
no count and a sector mesh carrying one blade of four still reduces
over four.

**`diameter_m` is per rotor, and it is what an advance ratio resolves
against for a motion citing that block.** The top-level
`rotor_diameter_m` above still answers for a row that names no
alias; it is one number for a whole configuration, so it cannot answer
for a second rotor of another size, which is why the length moved into
the block.

`RPM_SIGN` on a row likewise answers only where no alias is cited: a
record naming a rotor takes the sign from its block, and a record
stating both is refused naming both.

Nothing in the package reads the recorded rotor block except its `position`,
since 0.11.0: the two unsteady run types turn it into a coordinate system
named `<ALIAS>_SMRP` for the rotor it belongs to, the frame the reference probe lines and rotor plots are
defined in, and the frame a rotor row turns about unless it states
`ROTOR_ORIGIN`. The rest of the block, `radius_m` (optional since
0.11.0, and checked against the diameter when stated) and `n_blades`,
stays recorded and changes no emitted script. The four rotor facts the
block carried until 0.10.1, `rotation`, `blade_travel`, `rpm_sign_installed`
and `rpm_sign_isolated`, are refused since 0.11.0 (PFS-2029.08): the row
states the rotor speed's sign and axis, `pyfs-matrix upgrade --inputs`
strips them, and the argument behind them is on
[the mesh inputs page](mesh-inputs.md).

AND THE ARTIFACT DOES NOT REACH A RECIPE, which is worth knowing before
you write one. `resolve_matrix` narrows this artifact to the reference
area and length the case needs, and a recipe is called with the case and
the script, so `case.reference.rotor` does not exist. The full
artifact survives in the resolved matrix, keyed by the REF code of the
row, so a recipe that wants a sign reads it from the workspace or the
resolved matrix it closes over:

<!-- skip: next -->
```python
from pyflightstream.workspace.matrix import resolve_matrix

resolved = resolve_matrix(
    "matrix_registry.fs",
    workspace,
    name="matrix",
    fs_version="26.120",
    recipes={"003": "steady"},
)


def recipe(case, script):
    # The ROW's code, not a literal: a case carries the codes of the row
    # it came from, so this reads the artifact that row named.
    reference = resolved.references[case.variables["matrix_ref"]]
    rotor = reference.rotor
    if rotor is None:
        raise ValueError(
            f"{case.sim_id}: this recipe places a probe line per blade and the "
            "reference artifact describes no rotor"
        )
    blades = rotor.n_blades   # the RESOLVED count, one under a periodic sector
```

The guard on the way to `blades` is the point rather than ceremony:
`rotor` is `None` for any reference artifact that describes no
rotor, and a recipe that assumes one writes a script the solver
cannot run. The rotor speed and its sign are the ROW's (`RPM`,
`ADVANCE_RATIO`, `RPM_SIGN`), read through `rotor_speed(case)` rather
than from the artifact, so a recipe that emits a rotor motion reads the
row exactly as the built-in `unsteady_rotor` workflow does.
