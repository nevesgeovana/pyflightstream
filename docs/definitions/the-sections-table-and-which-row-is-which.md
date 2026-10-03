## The sections table, and which row is which

`sections/<point>_sections.csv` is ONE export of the solver holding EVERY
distribution the pproc declares, the wing in `XZ` and each blade in its own
frame, one after another with no marker between them. Each row leads with:

| column | what it is |
|---|---|
| `POL` | the polar of the point, as the matrix names it |
| `STEP` | on an unsteady point, the run's last TIME STEP, from the run record: the export is written when the march ends, and its own header counts the solver's inner iterations, not steps ([RPT-053](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md)). On a steady point, the solver iteration the export states. One name across every table |
| `FAMILY` | the geometry families of the row's distribution, joined by `+` |
| `PLANE` | the cutting plane of that distribution |
| `ROTOR` | the rotor whose blades those families are; `NA` for a surface no rotor owns |
| `AZIMUTH` | where the block's blade is at `STEP`, in degrees, wrapped to one turn: the block's OWN blade when it cuts the families of one blade of its rotor, else where BLADE ONE OF THAT ROTOR is; `NA` without a rotor |

`AZIMUTH = (blade1.azimuth_deg + sense * STEP * 360 / steps_per_revolution) mod 360`,
with the datum, the sense of rotation (the sign of the rotor's speed) and the
steps per revolution all taken from THAT rotor. Two rotors at two speeds have
two azimuths at one step, and a wing has none. A block that cuts the
families of ONE blade of its rotor (the rotor's `families_blades`, blade `n`
from 1, expanded through the aliases) states THAT blade's azimuth, `AZIMUTH`
above placed `(n - 1) 360 / B` ahead (0.31.0,
`pyflightstream.post.axes.placed_blade_azimuth_deg`, the one home), whatever
the sense of rotation: the sense turns the clock, not the blades' places on
the disc. So the four blade blocks of a four-blade rotor read four azimuths a
quarter turn apart, in the sections table and in the sections series alike.
A block over several blades, over the rotor's general families, or of a rotor
whose record states no blade grouping keeps blade one's azimuth. The sections of a quasi-steady
WHEEL point hold every clocking, and there a block of one blade states where
THAT blade is at its clocking ([The quasi-steady rotor](the-quasi-steady-rotor.md#the-quasi-steady-rotor)).

The run records which distribution is which, because the script states
surfaces by index and nothing at post can name them. A historical record with no section layout states `NA` in all four, and so does a record whose blocks do not add
up to the rows the export holds: a row given its neighbour's family is worse
than a row given none.

**It is one instant.** On an unsteady point this table is the distribution at
`STEP`, not an average over the window, and its `products.json` entry says
`"kind": "instant"`. The history is `series/<point>_sections_series.csv`,
which carries the same identity on every row.

The sections table of an additional post holds the run's rows first and the
additional pproc's after them; [The additional post](the-additional-post.md#the-additional-post) says
how each is named.

### Per-distribution sectional loads and Cp (0.25.0)

For every point, post also writes one file per `[[sections.distributions]]`
entry for each export:

- `sections/<point>_sloads_<name>.csv`, from the sectional loads export;
- `sections/<point>_cp_<name>.csv`, from `EXPORT_ALL_SURFACE_SECTIONS`.

`<name>` preserves the entry's `families` word (including an alias such as
`blades`); a list joins its words with `-`, for example `Blade1-Blade2`.
Filename-invalid characters become `_`, and trailing spaces and dots are
removed. Names that collide after sanitization, including differences only in
case, receive `_<k>`, the entry's 1-based pproc position. If that creates another
collision, the same position suffix is applied again until names are unique.
All planes and expanded blade/rotor blocks of one entry share its one file.
On a quasi-steady WHEEL point each file holds every clocking, with a
`CLOCKING` column after the export's own columns and the azimuth of each
block's blade at that clocking, as the sections table does
([The quasi-steady rotor](the-quasi-steady-rotor.md#the-quasi-steady-rotor)).

With `EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_AFTER_ITER`, each file holds
**every available stamped step**, in ascending order. Without per-step exports,
it holds the end-of-run export, with `STEP` interpreted as in the existing
sections table above. The existing end-of-run table and combined
`series/<point>_sections_series.csv` remain available.

Rows lead with `POL, STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`, then the
shared condition block, then the export's columns. Sectional loads retain
`Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment`. Cp carries `SECTION`, the export's
1-based cross-section index, followed by its twenty printed columns:
`Section_direction_value, X, Y, Z, nx, ny, nz, L, Cp, Mach, vx, vy, vz, vtot,
Cp_ref, Theta, CF, Delta*, Delta, H`. There is one row per step, section and
chordwise station, in the export's station order. Unknown time or identity
values read `NA`.

The recorded `sections_layout` assigns sections to blocks. New records also
retain each block's pproc entry position and original `families` selection;
editing the pproc cannot reassign those recorded blocks. For a 0.24.0 layout,
the recorded pproc must match each block unambiguously by families, plane,
frame and count. That match reads the geometry's boundary names
where they are known, for a block recorded in a common frame (see *The
geometry's names* under the integrated loads below): a block whose only
possible emitter is an entry citing a word nothing resolves, such as a rotor's
name with no rotor definition in hand, is that entry's, and the split file is
named after it. In a frame spelt like a rotor's, where the names settle
nothing because this match holds no rotor definition, where the names leave
no single owner, where two boundaries carry one name, or where no file carries
the recorded hash, the recorded cuts decide as before and the rows are kept. An
ambiguous match is a named skip. A missing recorded layout can
be recovered in memory from the exact hash-verified saved script, the recorded
geometry's boundary order, and a uniquely matching recorded pproc. Only explicit
append-only distribution commands with known frame identities qualify. The
manifest and original exports remain unchanged. A changed or missing script,
ambiguous selection, section deletion, unknown frame, or continuation without its
predecessor layout retains the named refusal in `products.json`.
A layout whose counts disagree with an export is likewise refused for that
export kind, rather than assigning rows to guessed distributions.

**The empty layout is a layout.** A run whose script adds or
removes no surface section records `sections_layout = []`, which is every
steady point of a pproc declaring no distribution: its sections exports state
`Number of Surface Sections: 0`. With no distribution declared and none
created there is nothing to split and nothing is named as skipped
(`test_a_steady_row_that_created_no_distribution_is_not_refused_a_split`); a
declared entry the geometry left out gets its named skip as above
(`test_an_entry_the_geometry_leaves_out_is_named_as_such_not_as_a_missing_layout`).
A continuation records the layout of the run it continues, whose saved
simulation it reopens
(`test_a_continuation_records_the_layout_of_the_run_it_continues`). A record with no layout at all is given the
empty one when its recorded script is on disk, its bytes hash as the record's
`script_sha256` says, and it carries none of `NEW_SURFACE_SECTION_DISTRIBUTION`,
`CREATE_NEW_SURFACE_SECTION`, `DELETE_SURFACE_SECTION` and
`DELETE_ALL_SURFACE_SECTIONS`; that is read off the script and needs no new
run (`test_an_old_record_takes_the_empty_layout_its_script_proves`). A record
whose script creates a section or no longer hashes as recorded, and a continuation whose record has no layout, are not given it, and their split stays
refused (`test_an_old_record_whose_script_creates_a_distribution_keeps_the_refusal`,
`test_an_old_record_whose_script_no_longer_hashes_keeps_the_refusal`,
`test_an_old_continuation_keeps_the_refusal`).

Each manifest entry states `distribution` (1-based), `families` (the original
alias/selection), and `steps_tabled`. A pproc entry with no recorded blocks
gets a named skip rather than a guessed share of another entry's rows.
Missing exports and missing stamped steps
are named skips. A section without chordwise stations contributes no Cp rows;
a distribution with no stations at a step is named as a skip. A malformed
export skips that kind's split files; the other kind remains available.

<a id="integrated-sectional-loads-since-0260"></a>

#### Integrated sectional loads

Set `integrate = true` beside `families`, `planes` and `count` in the desired
`[[sections.distributions]]` entry. The default is `false`. Omitted or false,
the sectional CSV holds the seven export columns and the context written by
0.25.1, behind the `POL` column every table opens with, with no
additional column. This is a post-processing
choice in the pproc, so it also applies when posting existing recorded exports.
The current entry must match each recorded block uniquely by families, plane,
frame and count; reordering entries cannot move an integration request to
another block. Recorded entry positions still own the split files. An ambiguous
or missing match warns by point, file and block and records an `#integration`
skip, keeping the file's original columns. All blocks in one file must request
integration for that file to gain integrated columns.

The effective matrix pproc supplies integration requests only; legacy ownership
still resolves through the recorded pproc. Section selectors, including `each`,
use the same expansion as the export builder, resolving current aliases through
the live reference to the recorded boundary families, including rotor names and
aliases of rotor names. An expanded emission's family set must equal the recorded
block's set.

**The geometry's names.** Each run records `inventory`, the
geometry's boundary names in the solver's order as the script read them at
`OPEN`. When the record carries no inventory, the post reads the names
from the mesh block of the geometry file whose sha256 the record carries in
`inputs_sha256`: the simulation's own staged copy first, then the library's
file of that name. The hash, never the name, says the file is the one that
ran, and it is computed from the file each time its names are read, before
and after the read, never remembered: a geometry changed or deleted since the
run recovers nothing, nor does one changed while its names are read, and the
`<stem>.boundaries.toml` sidecar is not read for it, because nothing hashed
it. The names settle a selection ONLY for a block recorded in a common frame,
or where the live reference's rotor definitions are in hand (integration
alone ever has them). A block recorded in a frame spelt like a rotor's
(`<alias>_RMRP`, `<alias>_RMRP<n>`, `<alias>_SMRP`, `<alias>_SMRP_ORIGINAL`)
may be an expanding entry's emission, and the builder resolved that entry
against the reference's rotor families, never over the names alone:
`Blade1` on `RMRP` asks for the rotor owning Blade1, and `Blade` for every
rotor with a Blade family. With no rotor definition in hand such a block is
matched as without the names, below, as in 0.26.0. No block records which
entry emitted it, so a user's own frame spelt like a rotor's (`X_RMRP`) is
read that way too, and two entries on it stay refused by name. A run that
turned a rotor is matched as without the names in any frame unless the
rotor definitions are in hand, because the builder reads a word naming a
rotor as that rotor's families before any stem: a rotor `Prop` beside
boundaries Prop1 and Prop2 is not the stem `Prop`. Where the
names are read, a selection is read by the export builder's own expansion
over them, for integration and for the ownership of a legacy layout alike:
a family stem, a numbered name, `all` and the aliases resolve as they
did at export, and an `all` block (recorded as an empty family list) is the
whole inventory. So `families = "Blade"` integrates a recorded Blade1 and
Blade2 block where the geometry carries no third blade and no boundary named
`Blade`, and is refused, by name, where it carries either. Names that give
one name to two boundaries settle nothing: the builder leaves that name out
of its labels, so the rest no longer say what `all` or a stem selected, and
the record is read as one without the names. A word that
resolves to nothing over the names and that no alias or rotor definition in
hand names (a rotor's name with no rotor definition) leaves its entry a
possible owner of every block of its frame kind, plane and count, so the
integration match is refused by name; for the ownership of a legacy layout
that same entry owns a block by elimination, when every other entry either
did not emit it by the builder's reading or could not have. An entry citing
a frame whose `_ORIGINAL` twin the run holds emits into both frames, so over
the names it stays a possible owner of a block on the twin beside the entry
citing the twin, and the integration match there is refused by name.

**Without the names** (a run that opened no geometry declaring them, an
older record whose geometry is gone or changed, or names that give one name
to two boundaries), ownership of a legacy layout
(a name and a grouping for raw files, no number added) resolves the recorded
pproc's selectors over the recorded cuts, the only evidence there is, a
family stem and a numbered name included. Integration is never matched that
way, whoever asks, because the post cannot tell a recorded specification
from a current one (two resolutions of one artifact id compare equal after an
edit, and a recorded entry may have emitted nothing): a selector is knowable
only by exact recorded boundary names, by aliases and by the live reference's
rotor definitions, whose members count even when they have no sectional
block; without the geometry's names layout silence never proves a family
absent, and any other word (a family stem, an unrecorded name, a
whole-geometry selector) leaves membership uncertain, establishes no
integration match and keeps the raw columns with a named skip. `each` and
`each_blade` still identify one known family per block without claiming a
complete inventory.
In a common frame, `["Wing", "Tail"]` describes one combined block,
so it cannot integrate separate recorded Wing and Tail blocks; both keep their
raw columns with a named warning. Where no rotor definition reaches the match
(a legacy layout, or a reference without rotors), the recorded frame names
carry the builder's grouping, because they name the rotor: `<alias>_RMRP`,
`<alias>_SMRP` with its `_ORIGINAL` twin (one emission turned, one group), and
`<alias>_RMRP<n>` for one blade; a frame either specification in hand cites
literally (a user's own `X_RMRP`) names no rotor whatever it is called, unless
a recorded frame no specification cites literally establishes the same rotor
(the rotor's `ROTOR_RMRP` cited by an entry over its hub stays the rotor's
while `ROTOR_RMRP1` is recorded); even then a literally cited frame can hold
any family, so it never supplies a sibling's missing family and a block
recorded in it is that literal entry's, never an expanding entry's; uncertain
membership keeps the raw columns. A block of any other kind than the entry's
frame expands per, a common frame included, is not that entry's emission and
cannot stand as a sibling of one. On an expanding frame (`LOCAL_AXIS`, `RMRP`,
`SMRP`) a recorded block is an entry's emission when it is exactly the selected
families recorded in its group, every other selected family is recorded in a
sibling group of the same kind (another rotor, another blade) or, for a
`LOCAL_AXIS` entry, in its own rotor's frame (the hub and spinner the builder
leaves out of a cut), and a per-blade block is one blade; two blocks recorded in
one group came from two entries and a combined entry owns neither, and a
selected family recorded only in a common frame leaves the block unmatched. If the effective pproc cannot be
resolved, complete recorded layouts and available stamped exports still supply
their histories. Integration and products needing that specification are named
skips in `products.json` and `post.log`.

```toml
[[sections.distributions]]
families = "blades"
frame = "LOCAL_AXIS"
planes = ["XZ"]
count = 50
integrate = true
```

The same `sections/<point>_sloads_<name>.csv` gains these columns, in this order
immediately after `Moment`:

| column | token in `_tokens.py` | unit | definition |
|---|---|---|---|
| `Strip_length` | `STRIP_LENGTH` | m | positive length of this station's strip |
| `Fx_int` | `FX_INT` | N | `Fx * Strip_length` |
| `Fz_int` | `FZ_INT` | N | `Fz * Strip_length` |
| `My_int` | `MY_INT` | N m | `Moment * Strip_length`, about this station's quarter chord |

**Strip rule.** For strictly monotonic exported offsets `s[0] ... s[n-1]`,
the interior boundaries are `(s[i-1] + s[i]) / 2`. The outer boundaries are
`s[0]` and `s[n-1]`. Endpoint lengths are half their one adjacent interval;
each interior length is half the distance between its two neighboring stations.
Thus the strips tile exactly the first-to-last station interval with no gap,
overlap or extrapolation to a geometric root or tip. Decreasing offsets retain
their order and use positive lengths. The nominal `count` spacing is never
used. Each recorded block (one plane, frame and family selection) is integrated
independently at each exported STEP, including blocks sharing a distribution
file. Original rows, axes, STEP and AZIMUTH are preserved. These are instants,
with no temporal average or revolution envelope.

**Moment-point decision, 2026-09-23.** `My_int` reports the integral of the
export's `Moment` about the local quarter chord `(X_QC, Z_QC)`. SRC-751,
the registered 26.123 manual, p.253 (Sectional Load Distributions), explicitly
identifies Xqc and Zqc as the 25% chord coordinates used for the CM reference.
Its pp.370-371 document computing and exporting the same sectional loads.
The recorded export
`tests/tier1_offline/fixtures/fsi/FS_SurfaceSection_Loads_call0002.txt` carries
`Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment`; its Newtons/Newton-Meter footer
states the computation units. The line-density interpretation is supported
by the force-integral comparison in RPT-006. Multiplying the moment density
by the strip length preserves that moment point and the export's sign and
section-plane axes. For an XZ cut in a blade's own frame this is its My.
For another cut plane it retains the export's plane-normal moment component
under the same column name. No transfer to an elastic axis, hub or global MRP
is applied. A sum of these local moments is not a moment about one common point.

**Integration never blocks post.** A block with fewer than two stations,
non-monotonic or repeated Offset, or a non-finite sectional value cannot be
integrated. Overflow in the integration is handled the same way. Post writes
the entire distribution file with its original columns, omitting all four
added columns, even when other blocks or steps in that file are valid. A
`PyflightstreamWarning` names the point, output file, source step/block and
reason. Other distribution files and Cp products continue normally.

---
