# The reference artifact

What a reference artifact holds beyond the three lengths, the study's vocabulary it declares, and the surfaces of a study of several models.

## What a reference artifact holds beyond the three lengths

The two reference files of [the input library](workflow-input-library.md) carry only the lengths the sweep table needed. A
reference artifact also carries a FOURTH length for a propelled
configuration, the moment point, and a `[rotor]` block. This is
`inputs/references/r003.toml` in full, the same artifact the [input library's listing](workflow-input-library.md)
summarises by its first three lengths:

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
ONE field, the position (the unsteady run types create the
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

See [The four rotor facts](mesh/reference.md#the-four-rotor-facts-a-reference-artifact-once-carried) for the hand, speed magnitude and retired fields.

## The reference declares the study's vocabulary

This artifact is where a study says what its boundaries are
CALLED, and it is the first thing to write when you set a workspace up: the
rows that come later cite these names and nothing else. Three tables carry
it, and the paragraphs above them are written for a configuration with ONE
rotor.

 [aliases] a name for a set of boundaries; a member
 may be another alias, resolved to the end
 [[frames]] the custom coordinate systems, moved here
 from the setup preset
 [<ROTOR>] kind = "rotor" one block per rotor, and the block's NAME
 is an alias over everything it owns

A fourth kind of block sits beside them: `[<DISC>] kind =
"actuator"`, an actuator disc a row names by its block's name
([One row, one actuator disc](workflow-row-flow-inputs.md#one-row-one-actuator-disc)).

ONE WORD, AND IT IS ROTOR. The block, the key, the frame, the point and
the probe scale all say it, because a propeller is a rotor and so is a
lift fan: the general word is the one that never has to be changed again
when the aircraft does. Every spelling this replaced is refused naming
what to write instead, so a file using a retired spelling stops rather than
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

Nothing in the package reads the recorded rotor block except its `position`:
the two unsteady run types turn it into a coordinate system
named `<ALIAS>_SMRP` for the rotor it belongs to, the frame the reference probe lines and rotor plots are
defined in, and the frame a rotor row turns about unless it states
`ROTOR_ORIGIN`. The rest of the block, `radius_m` (optional and checked against the diameter when stated) and `n_blades`,
stays recorded and changes no emitted script. See [The four rotor facts](mesh/reference.md#the-four-rotor-facts-a-reference-artifact-once-carried) for the retired fields and their replacement.

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

## One setup for every model of a study

A study of several models of one aircraft, a wing-body and a wing-body-tail
say, cites one setup, one pproc and one reference from the rows of every
model. The setup and the pproc name the surfaces of the largest model; the
reference declares them as the STUDY'S SURFACES, in a top-level `[study]`
table with one key, `surfaces`:

```toml title="inputs/references/r010.toml"
area_m2 = 10.0
chord_m = 1.2
span_m = 8.0

[aliases]
airframe = ["Wing", "Body", "Base"]
tail = ["HTail", "VTail", "TailBase"]

[study]
surfaces = ["Wing", "Body", "Base", "HTail", "VTail", "TailBase", "Sting"]
```

The study's vocabulary is the `surfaces` list, the names of the reference's
aliases (a rotor block's own name included) and every alias member, followed
to the end. A name is in the vocabulary when, case folded, it equals one of
those, or is a family word (the label without its trailing number) that one
of them answers.

On a row whose reference declares the vocabulary, each cited name is read
against the row's model:

| the name | on the row |
|---|---|
| selects a boundary of the model (by name case folded, by a family the model carries, or through an alias some member of which resolves) | read as without `[study]` |
| selects nothing on the model, and the vocabulary holds it | SKIPPED on this row, and said |
| selects nothing on the model, and the vocabulary does not hold it | a misspelling: the row is BLOCKED at plan |

The keys read this way are the setup's `delete_surfaces`,
`analysis_families`, `vorticity_drag_families`, `axial_separation_families`
and the `boundary` of each `base_region_operations` entry, and the pproc's
`base_regions` and the members of each `[groups]` entry. A skip is key by key:
`delete_surfaces` does not remove the name, and a list every name of which is
skipped emits no `DELETE_SURFACES`; the three `*_families` keys leave it out of
the emitted selection; a `base_region_operations` entry whose `boundary` is
skipped is not emitted; `base_regions` emits no
`DETECT_BASE_REGIONS_BY_SURFACE` for it; a `[groups]` member is left out of its
group. The words `all`, `each` and `each_blade` are never skipped, refused or
said. Every other input that cites a name keeps its own reading: the pproc's
`[[sections.distributions]]` and `[[plots.groups]]` entries, the members of
`[aliases]`, the row cells `ROTATE`, `TRANSLATE`, `MOVING_BOUNDARIES` and a
row's own `BASE_REGIONS`, the boundaries sidecar and the refinement file.

**Every skip is said, once.** The plan prints one WARNING per artifact, key and
name, whatever the number of rows and points: it names the artifact (its id
and file), the key (with the group of a `[groups]` member, or the position of a
`base_region_operations` entry), the name, the reference whose vocabulary
holds it, and every row whose model lacks it. A skip changes no plan status.
Each point's run record lists the skips of its row in `skipped_names`, one
`{artifact, key, name}` entry per skip in plan order; a point that skipped
nothing records no such field.

**A misspelling is refused.** A name that selects nothing on the row's model
and that the vocabulary does not hold BLOCKS the row at plan, at either value
of `--ignore-missing-families`, with a text naming the artifact, the key, the
name, the row and its geometry, the reference and the names of its
vocabulary, and saying to correct the name or to add it to the reference's
`[study] surfaces`.

Three refusals stay as they are, even where the vocabulary holds every name:

- a `*_families` key every cited name of which selects nothing on the row is
 refused, because an empty selection is the solver's every-boundary default,
 a different selection and not a smaller one;
- a pproc none of whose groups selects a boundary of the row's model is
 refused;
- a skip in `base_regions`, or of a `create` entry of
 `base_region_operations`, on a row whose setup addresses a
 `base_region_operations` entry by an `index` other than `all`, is refused
 naming the skipped name and the indexed entry, because the skip renumbers
 the base regions that index counts.

`--ignore-missing-families false` turns every skip into a refusal of the row,
naming the key, the name and the flag, on every key above, whether or not the
reference declares the vocabulary.

A reference without `[study]` declares no vocabulary, and every row citing it
plans, emits, records and refuses as it does without the table. A row whose
model carries every name its setup and pproc cite emits the same script with
or without the table. A `[study]` table stating another key, or a `surfaces`
that is empty or not a list of names, is refused naming the reference file and
the table; a top-level table named `study` that states a `kind` is a block, as
any other table with a `kind`. From Python, the declared surfaces are the
field `ReferenceArtifact.study`.
