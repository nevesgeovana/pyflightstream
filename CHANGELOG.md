# Changelog

All notable changes to pyflightstream. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/) and are decoupled from
FlightStream versions.

## [Unreleased]

### Changed -- BREAKING, and it changes the run-matrix file format

- **The `RE` and `MACH` columns are REMOVED. A row states its whole flow
  condition in one `FLIGHT_CONDITION` cell** (PFS-2027.01). The run
  matrix goes from sixteen columns to fifteen.

  **What to do if you have a matrix.** Nothing is guessed and nothing is
  silently reinterpreted: `read_matrix` RECOGNISES a file written under
  either older layout and refuses it naming the converter. Run:

  ```python
  from pyflightstream.cases.matrix import upgrade_matrix
  upgrade_matrix("your_matrix.fs", in_place=True)
  ```

  It folds `RE` and `MACH` into one cell reading
  `MACH:<mach>, REmi:<re>` and leaves every other byte, separator and
  line ending exactly as it is. The conversion is LOSSLESS by
  construction: the two columns carried exactly the two quantities those
  two keys carry, in exactly those units, so the values move across
  verbatim -- `0.20` keeps its trailing zero. A file written before
  v0.8.0 needs both stages and gets both from the same call: it gains
  the `WORKFLOW` cell and then the fold.

  **Why the columns went rather than gained a neighbour.** A flight
  condition is a SET OF CONSTRAINTS on one flow state, and which
  quantity gets solved for follows from which keys are present. Keeping
  `RE` and `MACH` as mandatory columns beside a cell that can also state
  them would have meant two homes for the same two numbers, and a reader
  would have had to look in both to know what was actually solved. One
  home per question, and no precedence rule to learn.

  The accepted keys are `MACH`, `TASmps`, `REmi`, `ALTFT` and `dISA`,
  and the set is CLOSED: an unrecognised key is refused naming it and
  listing the accepted set, which is the difference between a typo that
  costs a message and a typo that costs a campaign. Keys match
  case-insensitively; a duplicated key is refused rather than taking the
  last one, because these are constraints on one state and a silently
  dropped constraint changes what is solved.

  **What this release does not yet do.** `TASmps`, `ALTFT` and `dISA`
  parse, and a row carrying one is then REFUSED at conversion naming the
  resolver that will accept it. Solving for the unknown a constraint set
  leaves needs the reference length, and that resolver is the next item.
  Refused rather than ignored, deliberately: a constraint read and then
  dropped would be solved at a condition nobody asked for.

### Added

- **A standard atmosphere the package computes itself** (PFS-2027.03), as
  a floor module below every layer: ISA temperature, pressure, density,
  speed of sound and Sutherland viscosity, with an ISA deviation that
  moves temperature and leaves pressure alone. That last point is the
  convention worth writing down, because the other reading -- shifting
  pressure too -- is what a reader who has not met "ISA+5" will assume,
  and it is asserted rather than left to be inferred.

  It is NOT in `utils`, and the reason is the package's declared
  architecture rather than a preference: `utils` is a side branch outside
  the pipeline, and putting the atmosphere there would have created the
  first pipeline-to-`utils` dependency in the one module family whose
  position in the layer rule is undefined.

  The constants are ISO 2533:1975 and the viscosity law is White's
  Sutherland form, both cited in the module. The tier-1 test asserts
  against the values the standard DEFINES -- sea level, the tropopause,
  and the top of the isothermal layer -- and checks the quantities the
  standard does not tabulate at every boundary by derivation instead,
  because this repository holds no copy of ISO 2533 and a test that
  restated a remembered table figure would reproduce the very defect the
  item exists to retire. Sea-level density is derived rather than
  stored, and reproducing the standard's 1.225 kg/m3 to 1e-8 is what
  checks the three constants behind it together.

  It computes; it does not emit. `script.helpers.atmosphere` remains the
  emitter and remains one.

### Fixed

- **A commit that missed its clean-room trailer can now be corrected,
  which is what three documents already said and none could do.** The
  Tier 1 provenance guard is a WALK over every commit since its
  baseline, so the remedy printed by the guard itself, by
  `CONTRIBUTING.md` and by the control plane's commit-message hook -- "a
  commit that missed it is corrected by a follow-up commit that says so"
  -- could never clear it: a follow-up adds a commit to the population
  and removes nothing from it. The named mechanism did not exist, which
  is the same defect class FR-08 was reworded for in the first place.

  A later commit now declares on an earlier one's behalf with a
  `Clean-room-for` trailer naming its full hash, beside the unchanged
  `Clean-room` declaration. It is an exemption and deliberately the
  in-band kind: it lives in the history it describes, carries the full
  declaration rather than a waiver token, and is signed by its own
  author and date. The alternatives were moving the baseline, which
  un-checks every commit before it, and rewriting history, which is
  banned here.

  The follow-up is held to every rule a first-hand declaration is held
  to, each with its own test: the declarer must itself declare, must
  name a commit git can resolve, must name one inside the range under
  review, must come after the commit it covers, and may not name itself.

  Measured twice before it was believed: 2026-08-09, when a release
  commit could not be tagged until its message was rewritten, and
  2026-08-24, when a thirteen-line `.gitignore` change turned CI red on
  `main` and no follow-up could clear it.

## [0.8.1] - 2026-08-22

### Fixed

- **A matrix row can name its geometry, and the workflow opens it**
  (PFS-2025.02.01, PFS-2025.02.02). Until this release it could not, and
  the consequence was that the workflow capability v0.8.0 introduced, a
  run type the package builds itself off the matrix `WORKFLOW` column,
  could not be used at all: a case CARRYING a geometry rendered byte for byte identically
  to one that did not, because nothing in the matrix reader assigned the
  field and neither workflow builder read it. The run layer was already
  doing its half, staging the file and hashing it into the record, and
  the value was prepared and read by nobody.

  `GEOMETRY: <stem>` in `VAR_NAMES_VALUES` resolves against
  `inputs/geometries/` the way `REF`, `SET` and `ENTRY` already do, and
  is refused with the available stems and the row's own identifier when
  the id is not staged. Both builders emit `OPEN` first, before anything
  else, on the STAGED path, so the file the manifest hashed and the file
  the solver read are the same bytes.

  A WORKFLOW opens a saved simulation, a `.fsm`, and nothing else; a
  recipe of your own receives whatever the library staged and imports it
  declaring the units itself. Another suffix is REFUSED naming the
  suffix and the documented route, and the refusal is a decision rather
  than a gap: importing a raw mesh needs the row to declare its UNITS,
  and a silently defaulted unit is the same class of failure this
  release exists to remove.

  **If your `VAR_NAMES_VALUES` cells already spell `GEOMETRY`,
  `SYMMETRY` or `PERIODIC_COPIES`, the package now reads them.** That is
  the only upgrade risk in this release: those three names were yours
  before it and are the package's now. Rename your key, or stage the
  file the id names. The match is on the exact key, so a cell spelling
  it `SYMMETRY_TYPE` is untouched. A row carrying a geometry under a key
  of its own, `FSM_FILE` being the common one, is unaffected and also
  unread: rename it to `GEOMETRY` when you move the row off `LEGACY`, or
  keep the recipe. `upgrade_matrix` deliberately does NOT rewrite it,
  because a `LEGACY` row's recipe may still be reading that key.

  **WORSE THAN THE GAP WAS ITS SHAPE, and that is why this is a patch
  rather than a 0.9.0 item.** Every other limit in this capability
  refuses early and names itself. This one did not refuse at all: the
  script built, the campaign ran, and the solver solved whatever it
  already had in memory. No refusal anywhere, and the numbers wrong with
  nothing said, which is the failure this package exists to stop.

- **A row declares its symmetry, so a periodic sector is no longer solved
  as a one-bladed rotor** (PFS-2025.02.03). `SYMMETRY` and, where the
  mode needs it, `PERIODIC_COPIES` come off the row. The accepted modes
  are read from the command database for the row's own build rather than
  from a list written in this package, so a build that spells the
  argument differently reports no accepted set instead of pretending one.

  This is not a convenience. Symmetry was fixed at `NONE`, so a sector
  ran as a one-bladed rotor and the run COMPLETED: the numbers were
  wrong and nothing said so.

- **A matrix that names none of the three keys behaves exactly as it did**,
  and that is now measured rather than promised: every workflow crossed
  with two case shapes and every build it covers, 28 renders, is
  committed under `tests/goldens/workflows/` and compared byte for byte
  on every run of the suite. The one build whose grammar the steady
  builder cannot express is pinned as its REFUSAL text, so that wording
  is fixed too, and the set of pairs allowed to refuse is declared as
  data: an unexpected refusal aborts the generator instead of being
  written as evidence that the tree then accepts.

  The claim is measured rather than asserted, and it was not before: a
  QA pass inserted one extra emitted line into the steady builder, which
  changes the bytes of every geometry-less steady script on every build,
  and the whole tier 1 suite stayed green. It does not now; the same
  mutant fails every steady render on every build that renders one.

  Both halves of the claim are measured, because they are two claims.
  The goldens are generated from THIS release, so on their own they can
  only pin what happens from here. The backward half was measured
  separately and once: the same four case shapes, rendered on all 28
  combinations against a worktree at the `v0.8.0` tag, come out byte for
  byte identical, and the receipt is committed beside the goldens.

- **A campaign no longer fails when the workspace root is relative**, and
  this one was found by the review of the fix above rather than by a
  user. `pyfs-matrix run` and `plan` default `--workspace` to `"."`, and
  `CampaignWorkspace` kept the root exactly as given, while the solver
  runs with its working directory set to the simulation folder. Both the
  script's path and the geometry path the script names were therefore
  spelled from the caller's directory and re-resolved from the solver's,
  one level too deep, so the documented default invocation died with a
  `FileNotFoundError` naming a script that was sitting right there. It
  failed for EVERY row, with or without a geometry.

  The root is now resolved once, at construction, which is the one place
  that covers every path derived from it rather than the three boundaries
  that hand something to the solver today. `CampaignWorkspace.root` is
  therefore absolute even when the caller passed a relative path;
  `RunRecord.script_path` stays relative to the simulation directory, so
  manifests written by earlier releases still read. `RunRecord.cwd` and the SCRIPT PATH inside
  `RunRecord.argv` now carry absolute paths under a relative root, where
  they previously carried the caller's spelling; older rows read
  unchanged. `argv[0]` is the executable as the campaign declared it and
  is unchanged.

  `run.export_surface_mesh` and `run.check_solver_identity` had the same
  defect and no workspace to inherit the fix from, since a caller hands
  each of them a directory directly. Both now resolve their own working
  directory, and with it every path they build from it, including the
  ones that become script text. The second is the sharper of the two: it
  writes its log path into an `EXPORT_LOG`, so a relative working
  directory left the log where nothing read it, no build number was
  parsed, and the identity check WARNED instead of raising. A campaign
  aimed at the wrong FlightStream build proceeded, and the warning said
  the build number could not be read from the solver.

  `LocalExecutor._argv` deliberately does NOT resolve. It did for one
  commit, on the argument that every caller passes through it, and CI
  showed what this Windows-primary machine could not: `Path("C:/runs/x")`
  is absolute here and RELATIVE on Linux, so resolving rewrote it against
  the working directory and broke the documented headless mechanism on
  half the platforms. What a relative path means there is the caller's
  business and is unchanged.

  Every guard in the suite had built its workspace on an absolute
  temporary directory, where a path spelled from the caller and one
  spelled from the solver are the same string, which is why 3143 tests
  passed over a shipped default that could not work.

### Known gaps

A row's `REF` code still changes no emitted line, so coefficients come
out against solver defaults rather than the campaign's areas and lengths;
the solver model and the fluid state are still decided in the builders;
and `BLADES` divides the averaging window and configures no rotor. Where
those belong, a row or a solver-setup preset, is an open design question
and not an oversight: a fluid and a solver model are campaign-wide
conditions rather than case identity.

A workflow row that names no `GEOMETRY` opens nothing and says nothing,
which is what keeps every earlier matrix rendering as it did, and which
means a row migrated off `LEGACY` while keeping its own `FSM_FILE` key
is accepted in silence.

`covered_builds` reports FlightStream 25.000 as covered by `steady`,
because that build's database carries every command the workflow always
emits, while `initialize_solver` refuses that edition's grammar outright.
The refusal is loud and arrives before the script is written and before
any solver is started, so no seat is spent and no numbers are produced.
(A row naming a `GEOMETRY` does emit its `OPEN` first and then refuses;
the script is discarded either way, which is why the guarantee is worded
about the solver rather than about the first emission.) The
over-approximation is pinned as a golden and registered rather than
hidden.

### API surface delta

- **Added** to `pyflightstream.cases.workflows`: `GEOMETRY_VARIABLE`,
  `SYMMETRY_VARIABLE`, `PERIODIC_COPIES_VARIABLE`, `SIMULATION_SUFFIX`
  and `accepted_symmetry`.
- **Added** to `pyflightstream.workspace.inputs`: `is_valid_artifact_id`,
  which publishes the input-library id shape rule. It exists because two
  layers now need to ask it, and reaching for the private pattern across
  a module boundary is a layer crossing a tier 1 guard refuses.
- `GEOMETRY_VARIABLE` is DEFINED in `cases.workflows`, beside the other
  cell keys, and re-exported from `pyflightstream.workspace.matrix`,
  where the resolver that reads the cell lives. Both import paths work,
  neither is deprecated, and the second is the one the resolver's own
  documentation names.
- `accepted_symmetry` returns `tuple[str, ...] | None`. `None` means the
  build does not express symmetry through an argument of that name; an
  empty tuple would mean it declares one that is not an enumeration.
  Both mean "this build cannot judge a mode", so a caller tests
  truthiness unless it needs to tell the two apart.
- Nothing was removed, renamed or deprecated.

### Documentation

- `docs/workspace-and-workflows.md` gained the three keys, the reserved
  names, the `.fsm`-only narrowing and the two limits above, and lost a
  claim that no unsteady rotor case had run on a licensed solver, which
  the QA physics suite's own PHY-05 contradicts.
- `docs/mesh-inputs.md` says which of its two canonical routes a workflow
  takes, since the refusal cites that page and its canonical section read
  as permission for the route just refused.
- `examples/campaign_matrix.py` no longer tells the reader that a matrix
  row cannot name a geometry. It was true when it was written and shipped
  unchanged through v0.8.0; the key that falsifies it and the correction
  land together here, and a currency guard now holds it.

## [0.8.0] - 2026-08-20

**26.122 answers for 84 commands, and the vendor's build fixes the
rotor morphing defect.** 26.122 was `operational` purely by inheritance from
26.120 with nothing measured on it; a Tier 2 run now promotes 84
statuses and a Tier 3 run passes 30 of 30 metrics against the stored
references, inside the WARN and FAIL bands
(`reports/physics/PHY-26122_2026-08-11_rotor.yaml`). Separately, the FlightStream defect RPT-007 recorded on 26.120,
where an imposed FSIDisp deformation was silently dropped for a
boundary attached to a rotary motion definition, is measured fixed in
26.122 and NOT fixed in 26.121 (RPT-025). Two-way rotor FSI is
unblocked on 26.122 and still NOT VALIDATED: that report says an
imposed deformation reaches the mesh, not that the morphing is
correct, and no coupled acceptance run has been made against a build
where it applies.

Read the Tier 3 pass with its scope. The first run
(`reports/physics/PHY-26122_2026-08-11.yaml`) covered PHY-01 and
PHY-02, both static rigid wings, which look at nothing the build was
measured to have changed; `PHY-05` and `PHY-06` were pinned to 26.120
for a reason that never covered later builds, and they are widened here
and run, which is where 20 of the 30 metrics come from. And read the pass itself
precisely: all thirty metrics reproduce the 26.120-seeded references to
the last stored digit, float artefacts included, which demonstrates
ABSENCE OF DRIFT and not sensitivity to what this build changed. RPT-025
remains the only discriminating measurement, and its own finding that
all three builds give byte-identical rigid coefficients is why a rigid
matrix could not have discriminated.

### API surface delta

**The propeller reference admits the vocabulary a real campaign uses**
(PFS-2009.02). `PropellerReference` gains THREE optional fields and
`rotation` itself is unchanged, still `clockwise` or `counterclockwise`
viewed from behind the aircraft.

`blade_travel` records the SAME physical fact in the vocabulary a vendor
datasheet prints, `inboard_up` or `inboard_down`, naming where the blade
nearest the fuselage travels in the aircraft body frame. Case, hyphens
and spaces are folded, so a datasheet's `inboard-up` is read as written;
it is the one field in the model whose value is transcribed off paper. It is a separate field rather
than two more values of `rotation` because the two vocabularies are not
interchangeable: this one is side-independent, so the left and the right
propeller of a symmetric pair carry the same word, and converting it to
a viewed-from-behind sense needs to know which side the propeller is on.
Keeping them apart also keeps `rotation` a two-value `Literal`, so a
downstream exhaustive match over it stays exhaustive.

`rpm_sign_installed` and `rpm_sign_isolated` each record a measured sign,
plus or minus one, for the installed and the isolated meshes of the
configuration. Both are closed to coercion as well as to value, so `true`
and `1.0` are refused rather than read as `1`, and the model validates on
assignment, so the domain holds after loading and not only at it.

THE SENSE DOES NOT DETERMINE THE SIGN OF THE ROTOR SPEED, which is why
the two fields exist and why they are not derived. Going from a published
sense to the number a motion command takes needs the rotor axis, the side
of the aircraft and the handedness of the mesh actually loaded; the
installed and isolated meshes of one aircraft may be opposite hands and
then take opposite signs for the same published sense, which the one
campaign this vocabulary has been checked against was. A campaign
that established its signs by measurement records them, so a later run
reproduces the measurement rather than re-deriving it. Absence means not
established and must not be read as plus one.

Read that against `script.helpers.ROTATION_SENSE_SIGN`, which DOES derive
a sign from a sense and is not contradicted: it signs the AZIMUTH
INCREMENT, which way round the disc the blades are numbered, and that is
a different quantity from the sign of the rotor speed.

NOTHING IN THE PACKAGE READS THE PROPELLER BLOCK, the signs included and
`rotation`, `blade_travel`, `radius_m`, `n_blades` and `position` too.
The block is recorded, and setting any of it changes no emitted script on
its own. The artifact also does not reach a recipe: `resolve_matrix`
narrows it to the reference area and length the case carries, so a recipe
that wants a sign reads it from the workspace or the resolved matrix it
closes over, and `case.reference.propeller` does not exist. That absence
is now guarded by a test rather than only stated
(`test_no_module_outside_the_model_reads_the_propeller_block`).

Purely additive to the propeller block: its content validates unchanged.
The FILE still needs the kind letter this release introduced, so a
pre-0.8.0 library is migrated with `migrate_input_ids` before any of it
resolves.

`script.helpers.blade_frames` refuses an unknown sense with a message
that now ROUTES the other vocabulary rather than treating it as a typo:
a caller passing `inboard_up` or `inboard_down` is told that this is the
same fact in the vocabulary a datasheet prints, that `blade_travel`
records it, and that converting it here would need the side of the
aircraft, which is not among the function's arguments.

THE CHANGE CAME FROM A MEASUREMENT RATHER THAN FROM A DESIGN REVIEW, and
that is worth the sentence. The shipped input vocabulary had never been
checked against a real campaign's library; checked for the first time on
2026-08-19, it REFUSED that campaign's own reference artifact, on all
three counts at once. The same walk also showed why this release's
kind-letter break is right: that library's references and setups folders
each held a `003.toml` and its matrix named `003` in both columns, so a
number mistyped between REF and SET resolved to another artifact's file
with no signal at all.

**BREAKING, manifest schema.** `workspace.MANIFEST_SCHEMA` moves from
`pyfs-manifest/1` to `pyfs-manifest/2`, because
`script.BrokenCommandUse.source_version` stopped being optional and the
ABSENCE of that key therefore changed meaning.
`workspace.KNOWN_MANIFEST_SCHEMAS` is new and lists every stamp this
version can still READ, so a manifest written under the earlier schema
keeps loading rather than being refused for having been written before
the rule existed.

**BREAKING, waiver records** (PFS-2012.03).
`script.BrokenCommandUse.source_version` is REQUIRED. It names the build
whose database record says the command is broken, which is the build the
cited probe report was run on; the optional form allowed a waiver that
cites a report without saying which build it rests on, and a waiver whose
evidence cannot be located is a waiver nobody can check.

**BREAKING, run matrix** (PFS-2009.08.03). A matrix with an active row
whose `FS_BUILD` cell strips to empty, run or planned with a campaign
default that also strips to empty, raises `MatrixError` naming every such
row by row number and POL, and naming the option that supplies the
default. It is refused BEFORE the matrix is bound, so no campaign is
built, no executable is resolved and no executor is constructed.

**BREAKING, input-library ids** carry a kind letter, and the migration is
now a call rather than a rename by hand:
`workspace.migrate_input_ids(inputs_dir, matrices, apply=False)` renames
every artifact to its lettered form AND rewrites the `REF`, `SET` and
`ENTRY` cells of every matrix it is given, in the same call. A rename
that would land on an existing file, and a matrix that does not exist,
are refused before anything moves. `cases.matrix.rewrite_codes` is the
byte-for-byte rewriter under it and `cases.matrix.CODE_COLUMNS` names the
three columns that carry a library id (PFS-2009.03).

**BREAKING, and it is the one to read if you script `pyfs-matrix`:**
`parse_run_loads` and `sweep_table` already required a constructed
workspace as of this cycle; `run.cli`'s `run` subcommand now writes its
sweep table through `results.tables.write_table` rather than
`DataFrame.to_csv`, so a frame that cannot say what produced its numbers
is refused rather than written (PFS-2014.03).

**New catalogued exceptions:** `results.UnsupportedResultTypeError` and
`script.entities.ScriptDeclarationTypeError`, both keeping `TypeError` as
their second base (OPS-2009.01.08), and `post.writers.OutputExistsError`,
raised where a writer refuses to overwrite (PFS-2011.02).

**New catalogued warning categories:** `PyflightstreamWarning` and
`PyflightstreamDeprecationWarning`, in the shared-vocabulary module below
every layer. The first keeps `UserWarning` as its base and the second
keeps `DeprecationWarning` as a second base, so every filter and every
`except` a caller already wrote selects exactly what it selected. The
catalogue covers exceptions AND warnings, and both join it.

**New record fields:** `RunRecord.fs_version_source`, which says whether
a point's solver build was chosen FOR THE ROW or inherited from the
campaign default (`None` on a record that predates the field), and
`RunRecord.velocity_requested_m_s`, the free-stream velocity in m/s the
case asked for, where `None` means none was requested and is not zero.

**New elsewhere:** `cases.matrix.MatrixRow.row_number`, the row's 1-based
position among the file's DATA rows, assigned before the activity filter;
`results.to_table` now tabulates an unsteady plot report.

**BREAKING, and it is the release's headline: the verified run-matrix
layout is SIXTEEN columns** (PFS-2025.12.01). `WORKFLOW` joins the
pipe-delimited format between `RUN` and `VAR_NAMES_VALUES` and names the
workflow type that builds the row's script. It is a column of its own
rather than a pair inside `VAR_NAMES_VALUES`, because that cell is where
free case data lives and a type competing with it would be
indistinguishable from a user's own key.

A FIFTEEN-column file is RECOGNISED rather than merely rejected
(PFS-2025.12.02): the reader names it as a matrix written before v0.8.0
and names the call that fixes it, and nothing parses after that.
`pyflightstream.cases.matrix.upgrade_matrix(path, in_place=True)` adds
the column and leaves every other byte alone (PFS-2025.12.03). The
refusal messages count the width from the column list rather than
writing the number, so the next column cannot leave a stale figure in a
message.

**BREAKING: a workspace input id declares its kind** (PFS-2009.01,
PFS-2009.03). A reference, setup or group id now begins with a letter
(`r`, `s`, `e`), so a number mistyped between the `REF`, `SET` and
`ENTRY` cells of a run matrix is refused instead of resolving to another
artifact's file. The refusal names the id, the letter, the file to rename
and the matrix cell to change in the same edit. An existing library needs
its files renamed; the letter is part of the id, not a prefix the library
adds or strips.

**New module `pyflightstream.cases.workflows`** (PFS-2025.02), with
`WORKFLOWS`, `workflow_names`, and `WorkflowCoverageError` in the
exception catalog, deriving from `PyflightstreamError` and keeping
`RuntimeError` as its standard-library base.

**BREAKING: a case cannot ask for a geometric sweep and an aerodynamic sweep
at once** (PFS-2025.17, PFS-2025.17.02). A case declaring a multi-value
`angle_sweep_deg` beside a multi-point sweep is REFUSED at load time, through
both doors: `campaign.toml` and the run matrix. A file that loaded before this
release and asks for both will now stop, which is the whole point of the
change.

The reason is identity, not taste. The two sweeps MULTIPLY, into runs the case
never names, and the products cannot be told apart: a run is identified by its
aerodynamic point alone, so every geometry in the product would produce the
same `run_id` and the same output file names. Silently writing one over
another is the failure this refuses.

The refusal teaches both shapes rather than only refusing, and they are the
two things a user might mean. A rotation held FIXED across an aerodynamic
sweep is `angle_deg = <angle>`, one value, which costs one campaign. A sweep
OF the geometry is one case per geometry, each with its own `sim_id` and its
own single-valued angle.

`pyflightstream.cases` gains `ROTATION_SWEEP_KEY`, `ROTATION_OFFSET_KEY`,
`geometric_sweep_values` and `multiplied_sweep`, and the limit is stated where
a user meets it, at the declaration site, rather than in a page they would
have to already know to consult.

**BREAKING FOR AN INSTALL FOOTPRINT, not for any code: `trimesh` becomes a
RUNTIME dependency** (PFS-2025.20, PFS-2025.20.02), pinned `>=4.12,<6`. It was
previously behind the `[geom]` extra and is now installed by `pip install
pyflightstream` with nothing named. Cost, measured rather than assumed: ONE new
distribution and 3.89 MiB, and the hard dependency it drags is `numpy>=1.21`,
which this package already requires. A fresh install resolves 5.0.0, not the
4.12.2 a development tree happens to carry, which is why the envelope declares
both ends and a test asserts the installed version falls inside it.

Read that against `NFR-06`, which says the runtime dependency count does not
grow, because this release AMENDS it rather than quietly stepping over it. The
reason is recorded with the amendment: extracting a trailing edge is on the
default path of a rotor campaign, and a capability gated behind an extra makes
the library promise what a default install cannot do. The rejected candidates
are recorded too. `meshio` was refused on the committed weight budget, at five
new distributions and 12.26 MiB against limits of one and five, one of them a
syntax highlighter; `numpy-stl` was refused on capability and explicitly NOT
measured, since it reads STL where this package's seam is OBJ and it supplies no
face adjacency at all; an in-house reader was refused on the standing
engineering policy that prefers a public library for a generic need.

A BASE INSTALL CAN NOW MARK A TRAILING EDGE END TO END, and two independent
proofs say so rather than one (PFS-2025.20.03): a CI job that installs `[dev]`
alone, and an in-suite child interpreter whose meta-path REFUSES `scipy`,
`rtree`, `PyNite`, `pypdf` and `matplotlib` and then runs the whole route.

**BREAKING FOR A CONSTRAINT, and it is a constraint being LIFTED: one run
matrix may now name several solver builds** (PFS-2009.05). A matrix whose
active rows named two `FS_BUILD` values was refused outright, on the ground
that a campaign binds to exactly one installation. It runs now, and each
point's record names in `fs_exe` and `fs_exe_sha256` the executable ITS OWN
ROW asked for, with its script emitted under that build's declared version.

The version is a DECLARATION and never an inference, which is why
`inputs/executables.toml` grew a second entry shape rather than the code
growing a guess:

```toml
"26.120" = "C:/builds/26120/FlightStream.exe"
"26.123" = { path = "C:/builds/26123/FlightStream.exe", version = "26.123" }
```

A bare path means exactly what it has always meant and declares no version, so
every registry written before this release is byte-identical in behaviour; the
table declares the version that build's scripts are emitted under. An unknown
key inside the table is REFUSED naming itself and listing the keys that are
read, because a silently ignored `verison` is how a run gets emitted under the
wrong version while the file looks correct. The declared version is checked
against the version registry when the file is READ, so the refusal points at
the file that is wrong rather than at the first emission that fails.

One asymmetry is deliberate and documented at the call: a registry entry never
overrules the caller's `default_fs_version` for a row that names NO build. A
silent row falls back to the campaign default, as it always has.

`pyflightstream.workspace` gains `resolve_build` and `RegisteredBuild`, and
`CampaignWorkspace.resolve_build` beside the unchanged `resolve_executable`.
`ResolvedMatrix` gains `builds` beside an unchanged `fs_exe`.

READ THE RESIDUAL WITH IT, because it is stated rather than left to be found:
the PRE-FLIGHT still plans under one version. `plan_matrix` has no executor and
`run_matrix` pre-flights before its executors exist, so a two-build matrix is
planned against `default_fs_version` and run against each row's own. Both
docstrings say so. Closing it means constructing executors ahead of the
pre-flight, which would trade away pre-flighting away from the licensed
machine.

**New module `pyflightstream.workspace.trailing_edges`** (PFS-2025.16,
PFS-2025.20). It extracts a trailing edge from a mesh and writes it as the NODE
LIST both documented marking routes consume, through
`workspace.wake_edges.write_node_file`, which already existed and needed no
change. The criterion is the AFTMOST POINT OF EACH CHORDWISE SECTION in the
rotor frame, computed here rather than delegated: a dihedral-angle threshold is
the crease criterion, which is exactly what this capability exists to escape,
because a strongly twisted blade has a trailing edge that is not a crease.
READ THE FRAME PRECISELY, because it is the one thing here a reader can act
on wrongly. The rotor frame is where the CRITERION is computed: the axis and
the hub define the spanwise and tangential directions that decide which end of
a section is aft. The COORDINATES returned are selected mesh vertices, never
transformed, so they are an `(n, 3)` array in the MESH's own reference frame
and length units. The unit is declared once, at `write_node_file`, because a
mesh file does not carry one.

`pyflightstream._mesh` is where the mesh library is imported, through ONE lazy
accessor, on the precedent `_digest.py` set: it sits below every layer rather
than becoming a third hand-rolled copy of the same import guard.

**New public names in `pyflightstream.workspace`:**
`CampaignWorkspace.open`, `check_unique_stems`, `STEM_REGISTERED_KINDS`,
`expand_group`, `CampaignWorkspace.expand_group`, `reference_points`,
`reference_point`, `ReferencePoints`, `check_reference_point_names`,
`extract_trailing_edge`, `TrailingEdge`, `write_trailing_edge_node_file`,
`resolve_build`, `RegisteredBuild` and `CampaignWorkspace.resolve_build`.
`DEFAULT_SECTIONS` and `MINIMUM_SECTION_VERTICES` stay reachable as
`pyflightstream.workspace.trailing_edges.*` rather than at the package,
deliberately: they are the extraction's own tuning constants and not part
of the promise the package namespace makes.
`RunRecord.broken_commands` is annotated `list[BrokenCommandRecord]`,
a new `TypedDict` mirroring the script-layer record field for field.

**In `pyflightstream.results`:** `write_table`, `DATA_ORIGIN_CODES`,
`REDUCTION_CODES`, `REDUCTION_WINDOW_CODES`, `REDUCTION_WINDOW_COLUMN`,
`origin_code`, `reduction_code`, `reduction_for_solver_mode`,
`window_for_reduction`, `EXPORT_CONVERSIONS`, `ExportConversion`,
`export_conversion` and `require_export_parser`; `sweep_table` gains
`require_loads`; `PROVENANCE_COLUMNS` widens from two labels to three.

**In `pyflightstream.script`:** `helpers.blade_frames`,
`helpers.AZIMUTH_BASIS`, `helpers.RotationSense`,
`helpers.ROTATION_SENSE_SIGN`, `helpers.rotate_surfaces`,
`helpers.unsteady_action`, `helpers.mark_wake_edges`,
`UnsteadyActionUse`, `Script.unsteady_actions`, `Script.pending_actions`
and `Script.registry`. `RotationSense` is the SINGLE HOME of the sense
vocabulary: `workspace.inputs.PropellerReference.rotation` imports it
rather than restating the two words, which is a downward import the
layer rule permits, and a test refuses a second declaration.
In `pyflightstream.workspace.wake_edges`,
`write_node_file` and `node_file_units`.

**In `pyflightstream.cases`:** `DerivedFrom`, `Campaign.derived_from`,
`Campaign.is_derived`, `derived_body_sha256`, `stamp_derived_campaign`,
`ExportWindow`, `export_window`, `ReductionPlan` and `reduction_plan`.

**`pyfs-matrix run`, a third subcommand** (PFS-2025.09), taking a matrix
all the way to manifest records and a sweep table. `--workflow CODE=NAME`
maps an FS_SCRIPT code onto a run type, `--sweep-csv` names the table,
and `--resume`, `--workspace` and `--fs-exe` behave as on `plan`.

**`results.tables.to_csv` refuses a table carrying no `data_origin`,
`reduction` or `reduction_window`**, raising `MalformedOutputError`. Every table this package
builds carries them, so a caller passing a parsed result is unaffected; a
caller passing a hand-built frame is not.

**The run matrix is split across the layers it actually uses**
(OPS-2007.01, PFS-2009.05). `pyflightstream.cases.matrix` now holds the
reader and the converter and nothing that plans or runs: `MatrixError`,
`MatrixRow`, `read_matrix`, `to_campaign`, `convert_matrix`, and the names
the sixteenth column brought with it (`CODE_COLUMNS`,
`DEFAULT_VERSION_OPTION`, `LEGACY_WORKFLOW`,
`refuse_silent_rows_without_default`, `rewrite_codes`, `upgrade_matrix`,
`workflow_types`). `ResolvedMatrix` and `resolve_matrix`
moved to the new `pyflightstream.workspace.matrix`, which is where the
input library they bind against lives; `plan_matrix` and `run_matrix`
moved to the new `pyflightstream.run.matrix`, which is where the campaign
loop they compose lives. No shim and no re-export: import from the new
module. Nothing about the matrix format, the flags, the records or the
behaviour moved with them.

The reader used to reach up into both layers through five imports written
inside its function bodies plus two under `TYPE_CHECKING`, which recorded
the dependency while hiding it from every module-level reader. The count
is now zero at every level and a tier-1 test holds it there.

**`pyfs-matrix` is the same command from a different module.** The
console entry point is now `pyflightstream.run.cli:main`, and
`pyflightstream.cases.cli` is REMOVED. The command name, both
subcommands, every flag and every line of output are unchanged, so
nothing a user writes changes; what moved is the dotted module path. A
command line that plans a campaign composes the workspace input library
with the campaign pre-flight, so it belongs at or above both, and it sat
two layers below what it drove. It moved in the SAME change as the
reader, because in between the tree carries a module-level cases-to-run
import and no commit could be green on its own.

**BREAKING: `parse_run_loads` and `sweep_table` require a constructed
`CampaignWorkspace`** (OPS-2009.02.05). Both used to accept the campaign
root as a path as well and build the workspace themselves, which made the
results layer import the execution layer above it. The import was
deferred to call time, which changed nothing about the direction and only
hid it from a module-level reader, so the convenience is gone rather than
blessed as an exception. Write `sweep_table(CampaignWorkspace(root))`
instead of `sweep_table(root)`. Passing a path now raises
`MalformedOutputError` with the import line and the corrected call in the
message; it is a catalogued class keeping `ValueError` as its second
base, so an existing `except ValueError` still catches. Every shipped
example and doc page already passed a constructed workspace.

**BREAKING: `post.write_vtk_points` and `post.write_tecplot_points` take
a required keyword-only `provenance` and return `(output, record)`**
(PFS-2012.11, FR-31), rather than a single path. New public names:
`post.OutputProvenance`, `post.settings_records`,
`post.writers.provenance_path`, `post.writers.PROVENANCE_SCHEMA` and
`post.writers.PROVENANCE_SUFFIX`.

**`InputArtifactError` is defined in `pyflightstream._errors`, below every
layer** (OPS-2007.02.01). Both bases and all three attributes (`kind`,
`artifact_id`, `available`) are unchanged, and it is still imported from
`pyflightstream.workspace` and `pyflightstream.exceptions`, which resolve
to the same object; nothing a user catches changes. It moved because more
than one layer names it, and an exception type is vocabulary rather than
behaviour: leaving it in the layer that raises it made the layers that
catch it reach upward for the name alone.

**`SimCase` gains an optional `fs_build`; `pyflightstream.run` gains
`SolverBuild`** (PFS-2009.05), and `run_campaign` and `plan_campaign`
take a `builds` mapping from that id to a `SolverBuild`.

**New modules on the affirmed public surface:**
`pyflightstream.post.reductions`, `pyflightstream.post.settings_table`,
`pyflightstream.post.unsteady`, `pyflightstream.run.cli`,
`pyflightstream.run.matrix`, `pyflightstream.workspace.matrix`,
`pyflightstream.workspace.trailing_edges` and
`pyflightstream.workspace.wake_edges`. **Removed:**
`pyflightstream.cases.cli`.

**New public names elsewhere:** in `pyflightstream.script.helpers`,
`RelaxedTrailingEdge`, `parse_relaxed_trailing_edge`,
`resolve_shedding_direction`, `RELAXED_SHEDDING_DIRECTIONS`,
`DEFAULT_SHEDDING_DIRECTION` and `RotationSense`; in
`pyflightstream.cases.workflows`, `ROTOR_SHEDDING_VARIABLE`,
`rotor_shedding_direction` and `rotor_relaxed_trailing_edges`; in
`pyflightstream.cases`, `ROTATION_SWEEP_KEY`, `ROTATION_OFFSET_KEY`,
`geometric_sweep_values` and `multiplied_sweep`;
`pyflightstream.results.parse_unsteady_plots`
and `UnsteadyPlotsReport`; in `pyflightstream.qa.compat`,
`EXECUTABLE_BASELINE_REPORT`, `read_executable_baseline`,
`classify_executable`, `ExecutableIdentity`, `ExecutableVerdict`,
`licence_sensitive_candidates`, `LicenceCandidate` and
`MEASURED_STATUSES`. `ProbeRun` and `PhysicsRun` gain `fs_exe_sha256`;
`DriftRun` gains `fs_exe_sha256s`. `COMPAT_SCHEMA` is unchanged at
`pyflightstream-compat-report/1`.

**Changed shape, not a new name:** `pyflightstream.utils.manual.citation_reach`
returned two-slot lists and now returns mappings keyed by
`CITATION_REACH_OUTCOMES`. A caller reading the old shape by index must
move to the keys.

`pyflightstream.fsi.config_hash` is RENAMED `config_sha256`, and so are its
two package exports, the `FsiState.config_sha256` field and the
`check_state_matches_config(config_sha256=...)` keyword (OPS-2009.01.14).
The name now states the algorithm, matching `RunRecord.script_sha256` and
`outputs_sha256`, so a reader meeting the value in a saved state or a
convergence log can tell what it is without opening the code. An approved
public break for 0.8.0 under NFR-20's pre-1.0 clause: there is no shim and
no deprecation warning, because `_deprecations.DEPRECATED_MODULES` models
module shims only and a function-name row there fails tier 1.

`pyflightstream.qa` gains eight names, all new and none renamed or removed
(PFS-2018.02): `BuildComparison`, `BuildKey`, `CostCell`, `CostView`,
`PointCost`, `PointKey`, `cost_rows` and `cost_view`, from the new
`pyflightstream.qa.cost`. The physics report schema is unchanged at
`pyflightstream-physics-report/1`; an earlier reading of this work would
have bumped it to `/2`, which would have made every committed
`reports/physics/PHY-*.yaml` unreadable through `read_physics_report`, and
`tests/test_qa_cost.py` now guards that it stays put.

`scripts/gen_requirements_index.py` takes its inputs as arguments,
`collect(srs_dir)`, `traceability(ids, tests_dir)` and
`build(srs_dir, tests_dir)`, so a deliberately malformed page can be fed to
it in a test (OPS-2005.09). The command line is unchanged and still writes
`reports/requirements-index.json`. A new `MalformedRequirementPageError`
carries every problem found rather than the first.

One new module, `pyflightstream.qa.reports`, exporting `report_paths`,
`refuse_existing_report` and `resolve_report_date`, all three re-exported
from `pyflightstream.qa`:
the one home of the report-naming and never-overwrite rule the three
evidence writers share, including the build key each of them used to
derive for itself. Each series keeps a helper of its own that calls it,
so a writer and the pre-flight protecting it ask one question rather
than two that agree by coincidence: `compat_report_paths`,
`physics_report_paths` and `drift_report_paths`, all three new in this
cycle and all three re-exported from `pyflightstream.qa`. Each resolves
its version through the registry before naming anything, so asking with
a vendor release name cannot predict a stem the writer will not produce,
and `resolve_report_date` refuses a date that is not `YYYY-MM-DD` rather
than putting it in a file name.

Other new public names in `pyflightstream.qa`: `ProbeOutcome.REMOVED`,
`unrecognised_commands`, `read_compat_reports`, `contradicting_evidence`,
`Judgment` and `PROMOTABLE_OUTCOMES`. In `pyflightstream.qa.physics`,
`PhysicsCase` and `case_table`, which were reachable as the element type
of two exported inventories and as the function this release breaks, and
were missing from the module's own list. In `pyflightstream.qa.geometry`:
`mean_edge_length`. One new keyword argument: `reports_dir` on
`apply_compat`; `translation_m` on `wing_triangles` and
`generate_wing_stl`, and `name` on `generate_wing_stl` alone, all
keyword-only. `wing_triangles` returns an array and has no solid to name.

New public names in `pyflightstream.utils.manual`, the maintainer reading
layer: `EditionDelta`, `EditionVerdict`, `documentation_delta`,
`read_edition` and `insert_version_row`, which are what `pyfs-manual
register` is built on, plus `Reachability`, which was reachable as the
return type of an exported function and was missing from the subpackage's
own list. One new module, `pyflightstream.utils.database`, exporting
`register_edition` and `Registration`: the registration transaction,
which was written inside the argument parser and is now importable and
testable. One new command-line surface: the `register` subcommand of
`pyfs-manual`.

**Incompatible changes: four, and ONE of them is quiet.** The first
breaks loudly, the second is the quiet one, and the third replaces a
quiet success with a loud refusal.

- `PhysicsCase.versions` is now `PhysicsCase.minimum_version`, and its
  type changed from a tuple of canonical identifiers to `str | None`.
  `PhysicsCase` is public API (`pyflightstream.qa.physics` is an affirmed
  public module), so this is a break, and it is a LOUD one:
  `PhysicsCase(versions=...)` is a `TypeError` and `case.versions` an
  `AttributeError`. No shim: the deprecation regime binds from a stable
  release and the ledger covers modules rather than fields, so a pre-1.0
  minor may rename with this line.
- `case_table()` now emits the key `minimum_version` where it emitted
  `versions`. This is the quiet one and it is why the key moved rather
  than keeping its name: the VALUE became a sentence when the field
  became a minimum, so `if "26.123" in row["versions"]` stopped being a
  membership test over identifiers and became a substring test over
  English, answering False for 26.123 and True for 26.120. A missing key
  raises; a changed meaning does not.
- `run_physics` and `run_drift` now REFUSE a build on which any requested
  case has no command evidence, where they used to run the supported
  subset and report success. `pyfs-qa physics --fs-version 26.100` used
  to run four cases and write a report; it now exits 2 and names the
  runnable subset. Pass `cases=` (or `--cases`) to ask for a subset
  deliberately.

A FOURTH, and it is the cheapest one on this list: FIVE boolean
arguments became keyword-only. `half` on `wing_triangles`,
`generate_wing_stl` and `build_phy02_script`, and `include_smi` on
`registered_cases` and `case_table`. On `build_phy02_script` THREE
MORE parameters moved with it, `stl_path`, `loads_name` and
`log_name`, none of them boolean: `half` sat immediately after
`version`, so the star had to go there and swept the rest of the
signature. It is the only one of the five with collateral, its
sibling `build_phy01_script` still takes those three positionally,
and every in-tree caller of both already used keywords. The count read four until the fifth
signature was found by a review pass, in the same module as two of the
others; a sweep that stops at the sites review named is not a class fix,
which is this repository's own rule and is why the number is stated
rather than the word. `wing_triangles(spec, True)` was legal and read as nothing
in particular; so did `case_table(True)`. The debt is paid in the window
this release already opens rather than in the next one, because paying it
later would be a SECOND break for the same callers and for the same
functions, three of which are being broken here anyway. Every caller in
this repository, in its tests, its scripts and its one shipped example,
already passed these by keyword, so nothing in the tree moved.

**Deprecations: ONE, and this line said "none" until 2026-08-20.**
`plan_matrix(fs_version=...)` and `run_matrix(fs_version=...)` are
deprecated in favour of `default_fs_version` (PFS-2009.08.01). The old
spelling still works and warns with `PyflightstreamDeprecationWarning`.

The rename is not cosmetic: beside a per-row `FS_BUILD` column,
`fs_version` reads as an OVERRIDE of that column, and it is the opposite,
the version that rows naming NO build fall back to. The `pyfs-matrix
--fs-version` command-line flag is unaffected and keeps its spelling.

The removal release is not named, because NFR-20 does not bind before 1.0
and the number is the author's call. That this line is the one a
downstream reader greps to decide whether an upgrade breaks them is why
it is corrected here rather than at the next release: publishing it false
costs the reader the whole warning window the shim exists to buy.

### Added

- **Five parsers for the six exports that had none, each written against
  a real observed file** (PFS-2014.02). Five functions rather than six
  because `parse_surface_sections` answers for both surface-section
  commands, on the evidence below. `parse_force_distributions`,
  `parse_off_body_streamlines`, `parse_surface_sections` (which answers
  for BOTH surface-section commands, on the evidence that the two
  captures carry the same banner, count label, twenty-column header and
  `Edges=` block structure), `parse_sweep_spreadsheet` and
  `parse_solver_analysis_csv`. With them: `ExportSolution`, the solution
  block all four text formats print identically, plus one typed report
  per format and the record types `OffBodyStreamline` and
  `SurfaceSection`; the column pins `FORCE_DISTRIBUTION_COLUMNS`,
  `OFF_BODY_STREAMLINE_COLUMNS`, `SURFACE_SECTION_COLUMNS`,
  `SWEEP_COLUMNS` and `SOLVER_ANALYSIS_CSV_COLUMNS`; and
  `SOLVER_ANALYSIS_CSV_FIELD_UNSTATED`. `to_table`, `to_csv` and
  `write_table` accept all five.

  **THE CSV'S FOURTH COLUMN IS NOT LABELLED, deliberately.** That export
  writes no header at all, so the columns cannot be read from the file.
  The first three are settled by MEASUREMENT rather than inference:
  column one takes exactly the seven cosine-spaced chordwise node
  stations of the captured mesh, column two exactly its seven spanwise
  stations, and column three the NACA 0012 half-thickness at each, so it
  is a node-based export as the entry's note says. The fourth is a
  pressure coefficient and not a pressure in the units the call names,
  which the surface-section export from the same run confirms. WHICH
  coefficient cannot be settled: that run set the reference velocity
  equal to the free-stream velocity, so `Cp` and `Cp_ref` are identical
  to seven digits and the two tokens are indistinguishable from the
  numbers. So the column is `scalar`, the caller may declare the token,
  and the table carries `scalar_field` with the word `UNSTATED` where
  nobody said. A word rather than an empty cell, because an empty cell
  reads back as NaN.

  Two further readings are recorded in the code rather than smoothed
  over. Every streamline in the captured file declares 31 points and
  writes 30; nothing settles what the extra one is, so the declared
  count is recorded verbatim and never equated with the rows, and a test
  pins the off-by-one as a measurement so a build that changes it goes
  red rather than silent. A section declaring zero edges is RETURNED as
  an empty section rather than refused, because the file declares it.

- **A completed sweep leaves its table beside its runs without anyone
  asking** (PFS-2014.03). `run_campaign` writes `post/campaign_sweep.csv`
  at the end of its third pass, one row per point, with the integrated
  forces and, for an unsteady point, the solver's own time average with
  the window token beside it, so no row is ambiguous about what produced
  its numbers.

  TWO THINGS ABOUT WHEN IT IS WRITTEN, because both are the point rather
  than details. It is written BEFORE `CampaignErrors` is raised, so a
  campaign whose every point failed still leaves the table this exists to
  leave. And a failed write costs the campaign nothing: it is reported as
  a warning naming the exception, the target and the call that rebuilds
  the table, because a sweep that ran is not undone by a table that did
  not.

- **The two field writers and the coupling drivers refuse a silent
  overwrite** (PFS-2011.02). The VTK and Tecplot point writers refuse an
  existing path naming the file, with `overwrite=True` the only way
  through; a script emitting the same probe export path twice is refused
  naming BOTH call sites rather than the second one; and `coupling_step`
  refuses a run folder that holds a convergence log with no state beside
  it, naming the log. Each refusal names what to do instead.

- **An explicit classification of every export command, with the debt
  named one file at a time** (PFS-2014.02). `results.EXPORT_CONVERSIONS`
  says which exports read and tabulate, which formats are deliberately
  outside the default conversion set, which carry the export phase and
  write no file at all, and which are debt; `require_export_parser`
  refuses each missing one BY NAME rather than in the aggregate.

  READ THE COUNT WITH IT. **Ten of the eleven default-set exports now
  read and tabulate**, up from four, and the eleventh is not an omission:
  `EXPORT_BL_VELOCITY_PROFILE` is the one format nobody has observed,
  because IT IS INTERACTIVE. It opens a modal window carrying a plot and
  a Done button, and script processing stops there until a person
  dismisses it, even under `-hidden` with both standard streams
  redirected. That was measured on 26.122 and recorded in
  `reports/RPT-027` on 2026-08-17; `reports/RPT-037` adds that it happens
  on 26.123 too, across three unattended runs that returned nothing on a
  mesh which solves in two seconds. Its classification note now carries
  that reason in place of "no observed export captured", which had come
  to read as though nobody had tried. No status moved: `broken` travels
  only through the sanctioned probe path, and in any case "opens a
  window" is not the claim "the solver rejects it".

  Every new parser is written against a REAL observed export, captured on
  a licensed solver and committed as a fixture. The captures are
  deliberately small: the same wing at 6 by 6 panels writes the same
  FORMAT in a few kilobytes, where the mesh a physics reference wants
  produces a 508 KiB force distribution. A parser is pinned by the shape
  of a table, its header, its terminator and its column names, and none
  of those vary with panel count; no coefficient in any of those fixtures
  is evidence of anything.

- **A Tier 1 guard binding the examples run's promotion to the categories
  the package actually raises.** It derives the six command homes from
  the tracked tree rather than listing them, asserts they all spell the
  SAME filter, drives a warning of each kind through a real pytest under
  both the shipped filter and the narrowed one, and refuses a narrowed
  filter while any warning site still names a foreign category. The
  ordering rule is enforced rather than described.

- **`results.to_table` refuses an unsteady plot export whose plot name
  collides with a provenance column.** Plot names are the user's own, so
  stamping the provenance over one would have replaced a column of
  physical numbers with a constant token and left a table that still
  writes and still looks right.

- **A workflow: a run type the package builds by itself** (PFS-2025.02),
  named by the run matrix's `WORKFLOW` column and resolved by TABLE
  LOOKUP, never by import. Two types ship: `steady`, one point of a
  polar, and `unsteady_rotor`, a rotor coordinate system, one rotary
  motion at the row's RPM about the row's axis, and a physical time
  loop. The matrix reader asks the registry for the accepted set at call
  time rather than keeping a second list, so a type cannot exist in one
  place and not the other.

  **A workflow declares the commands it always emits and DERIVES the
  solver builds it covers from the command database** (PFS-2025.18).
  Asked for a build outside that range it refuses BEFORE emitting its
  first line, naming the build received, the covered builds in release
  order, and the commands whose absence excludes it. It refuses about
  the ENVIRONMENT rather than about an argument, which is why its
  standard-library base is `RuntimeError`; that choice is the lane's
  default and is a public contract callers catch on, so it is a marked
  proposal until the author rules.

- **`pyfs-matrix run` takes a matrix from trigger to reductions**
  (PFS-2025.09). **IT REVERSES A DECISION RECORDED IN THE TOOL ITSELF**,
  whose docstring said there was deliberately no run subcommand, because
  the solver-quality judgment and the recipe registry are code and not
  command-line strings. The lane built it under that reading and does not
  own it: the reversal is the author's to confirm.

- **The window the expensive exports and the unsteady reductions apply
  over, counted BACKWARDS from the end of the run** (PFS-2025.08). State
  it in degrees of rotor rotation, in solver steps or in revolutions; the
  record carries the form you wrote beside every form it derived, so a
  later reader can tell which was which. An angular window with no rotor
  speed or no time step is refused naming what is missing rather than
  assuming a default.

  `reduction_plan` says which windows the four reductions of one unsteady
  rotor case are taken over (PFS-2025.06): the export window for the time
  average, one blade passage for the phase-locked average, and one window
  per blade of the last revolution for the per-blade split. The raw
  series is FIRST in the list and is never replaced by a reduction.

- **One motion-following coordinate system per rotor blade**
  (PFS-2025.04), placed arithmetically at 360/N from a first blade that
  must lie on a quadrant, each with its x axis radial and its z axis
  along the rotor axis. THE AZIMUTH DATUM IS A NAMED TABLE rather than
  arithmetic scattered through the emitter, because it is the one
  convention on this release whose wrong value produces plausible numbers
  rather than a failure: a wrong datum rotates every blade frame and
  every phase-locked reduction keyed to blade index. The table is the
  lane's proposal and the author's to rule on; changing it is one edit
  and not a search.

- **`rotate_surfaces` rotates existing mesh surfaces about an axis of a
  named coordinate system** (PFS-2025.14), choosing between the two
  spellings from the script's own build, because the capability changed
  name and grammar at 26.122. Selecting a component turns all N blades in
  one call.

- **`unsteady_action` registers an action the solver runs after each
  unsteady time step** (PFS-2025.07), so sections come out mid-run rather
  than by stopping and restarting. The record it returns carries the
  command's recorded evidence status on that build and whether it was
  inherited, so a caller can tell a measured capability from an inherited
  one without leaving the call.

- **`mark_wake_edges` marks wake edges from an imported node list**
  instead of by the angle criterion (PFS-2025.13), and refuses on a build
  that does not document the import, naming the build, the route and the
  angle criterion it will NOT substitute unasked.
  `wake_edges.write_node_file` writes the list the import reads, from an
  `(n, 3)` array plus a declared length unit, refusing an empty list, a
  wrong shape, a non-finite coordinate, an unrecognised unit token and an
  existing destination (PFS-2025.16.02). Whether the solver ACCEPTS the
  layout is open until a committed probe report says so.

- **A campaign file the package generated says so in the file**
  (PFS-2009.07.01). A generated `campaign.toml` carries a table naming
  the matrix it came from, the moment it was written and two digests, so
  a copy carried out of its folder still says where it came from.
  Running an EDITED derived campaign is refused naming the matrix
  (PFS-2009.07.02); with no matrix, an authored campaign is the source
  and is treated as one (PFS-2009.07.03), which is what keeps the
  refusal from catching every hand-written campaign in existence.

- **The pre-flight groups the matrix by build and checks each build
  once** (PFS-2009.09.01), and a row whose build fails identity stops the
  campaign BEFORE a seat is spent (PFS-2009.09.02). It composes the
  identity machinery that landed the day before rather than writing a
  second one.

- **Named reference points, declared once** (PFS-2025.15). `ARP` is the
  airframe reference point and the engine one is `ERP`, or `ERP1` through
  `ERPn` with more than one propulsor; a name outside the convention is
  refused. A named boundary group expands to `{name}1` through `{name}N`
  over its members' 1-based positions in declared order (PFS-2025.03), so
  a blade group resolves identically on every re-resolution.

- **An input library in which two files answer to one id is refused when
  the library OPENS** (OPS-2005.08.05), naming the stem and the full path
  of every file carrying it, rather than lazily at the resolution that
  happens to hit it. `CampaignWorkspace.open` is the validating
  constructor and `check_unique_stems` is the same rule as a callable.

- **Every table the results layer builds carries `data_origin`,
  `reduction` and `reduction_window`** (PFS-2014.05, and the window at
  PFS-2014.03), so a reader can tell a direct integration from a time
  average, AND over what window, with the one file in hand. `data_origin`
  is `raw` for anything read off a solver export and `reduced` for
  anything post-processing produced; `reduction` is `none`,
  `time_average` or `unknown`; `reduction_window` is `not_applicable`
  where nothing was averaged, `not_printed` where the solver averaged and
  its spreadsheet printed no window, and `unknown` where the solver mode
  itself never printed, so whether anything was averaged is unknown too.
  `results` gains `REDUCTION_WINDOW_CODES`, `REDUCTION_WINDOW_COLUMN` and
  `window_for_reduction` as public names, and `PROVENANCE_COLUMNS` widens
  from two labels to three: a consumer that UNPACKED the pair breaks on
  the widening, which is why it is announced here rather than noticed
  later. THE VOCABULARY IS THE AUTHOR'S CALL and this is the lane's
  default: a failed row with no loads report says `unknown` rather than
  `none`, because `none` would assert a direct integration that never
  happened. The published integer codes are APPEND ONLY: a published
  integer never changes meaning, because a file written last month is
  read with today's table.

- **An explicit classification of every export command the database
  carries** (PFS-2014.02). The debt is ENUMERATED rather than described,
  so the acceptance's own sentence can be checked against it. THE COUNTS
  ARE NOT REPEATED HERE and this bullet used to carry them: it said four
  parsed and seven owed, which was the census when the classification
  landed and not the one this release ships. `EXPORT_CONVERSIONS` owns
  that fact and the parsers entry above states the release's own figures;
  a second home for a count is how the two came to disagree inside one
  section.

- **`sweep_table(..., require_loads=False)`** returns the identity rows it
  has already assembled, with a warning, where it used to raise because
  no run yielded a coefficient table (PFS-2014.03). The default is
  unchanged. It exists so a campaign whose points all failed can still
  leave a table a colleague can open.

- **A campaign can send some of its cases to a different solver build**
  (PFS-2009.05). A case naming a build is RECORDED against that build's
  executable, its sha256 and its version, and its script is emitted under
  that build's version, so a study across two installations no longer has
  to lie about which one produced a point. A case naming no build runs
  and records exactly as before. A case naming a build the mapping does
  not carry is refused before anything is staged, rather than falling
  back to the campaign's executable, because that fallback is the record
  this exists to prevent. The build's version is DECLARED in
  `SolverBuild` and never inferred from an executable path or a build id.

  THAT SEPARATE DECISION WAS TAKEN LATER IN THIS SAME RELEASE, and this
  paragraph said the opposite until 2026-08-20. It read "the run matrix
  still refuses a second `FS_BUILD` value", which was true when the
  campaign-level capability landed and stopped being true when
  PFS-2009.05 closed. The rule that was missing is now the registry's
  second entry shape: a build's version is DECLARED beside its path in
  `inputs/executables.toml`, never mapped from the build id. See the
  multi-build matrix entry above, which is the successor to this
  sentence.

- **A tier-1 layering guard with an EMPTY permitted set** (OPS-2007.02.03).
  Any import inside a function body that resolves to a module in a higher
  layer now fails the suite, with no allowlist, no per-module skip and no
  exception list, because deferring an import to call time does not
  change its direction. Layer rows are read from
  `pyflightstream.overview`, the single home of the stack, so the guard
  spells no layer name of its own. It deliberately does not fire on a
  side branch with no layer row, on a same-layer import, or on a
  standard-library or third-party one, and each of those shapes is
  measured rather than asserted in prose.

- **Every table the results layer returns pins its complete column set**
  (OPS-2009.01.03). The loads frame, the probe-point frame and the sweep
  table each carry a label-to-meaning literal beside the run row's, so a
  column added, dropped or renamed is a deliberate two-file edit. The
  loads frame was pinned only at its first four and last two columns, the
  sweep table only by three per-name lookups, and the probe-point frame
  was compared against the report it was built from and therefore could
  not fail at all. Column ORDER is still not part of the NFR-19 promise
  and is not asserted.

- **`pyflightstream.results.parse_unsteady_plots` reads the unsteady plot
  export** (PFS-2015.02.02), the only file this package reads that
  carries one row per TIME STEP rather than one converged state. The
  report gives the plot names in file order, the step count and one array
  per column, resolved by label through `series()`; the column ORDER is
  data and not a contract. It refuses a duplicated or unnamed column, a
  cell that is not a solver-printed number and a row narrower or wider
  than the header, each naming the step and the column it read, and it
  refuses a probe export outright rather than reading a table of
  positions as a history.

  READ THE GROUNDING WITH IT, because it decides what the parser can be
  trusted for. No export of that command exists in this repository: the
  row and column meaning is the manual's, the DELIMITER is documented
  nowhere and is assumed to be a comma because every other table export
  of this solver uses one, and the committed fixture is SYNTHETIC and
  says so in its own first line. A file delimited some other way is
  refused by the anchor rather than misread. The command's database entry
  stays at `documented` and a real export is owed before the parser can
  be called verified.

- **`pyflightstream.post.unsteady`, the per-timestep reader and the
  blade-passage average** the post layer's own docstring had advertised
  since v0.5.0 without having (PFS-2015.01, FR-20).
  `read_timestep_series` reads the frames of an animation export back as
  one ordered series, in either of the two data filetypes that command
  documents. It takes the order from EVIDENCE and never from a file name:
  the caller declares that the sequence is already in solver order, or
  each frame carries its own solution time, and it REFUSES when it has
  neither, saying that settling the vendor's frame naming needs one
  licensed run and a committed probe report. `blade_passage_average`
  averages a declared window of solver steps and is the only
  implementation of that average in the release; `passage_windows` hands
  out the successive passages so a phase-locked reduction composes it
  rather than duplicating it.

- **`pyflightstream.post.reductions`, the writing seam** that holds the
  rule a reduction never overwrites the file it came from and the time
  series keeps its own dedicated file (author's rule of 2026-08-16).
  `write_series` writes the history; `write_reduction` refuses a
  destination equal to any file the reduction read, refuses an average
  whose series file is missing or is not beside it, and refuses an
  existing destination. The rule lives at the seam rather than in a
  workflow, so a caller who bypasses the workflow cannot obtain an
  average with no history beside it.

- **Every post-processing file carries the settings that produced it**
  (PFS-2012.11, FR-31). Every file either flow-visualization writer
  produces is now accompanied by `<name>.provenance.json`, carrying the
  run identity, the campaign, the FlightStream version and the COMPLETE
  solver-flag record: all 65 flags, each with its value, its provenance
  and its citation, with a flag nobody has established for that build
  present and named `unknown` rather than omitted. A post-processing file
  previously had to be joined back to `runs.json` to learn what produced
  it, and a file that needs another file is not self-contained: delete
  `runs.json` and the numbers survived while their meaning did not.

  The record's suffix is APPENDED rather than substituted (`ring.vtk` is
  described by `ring.vtk.provenance.json`), because two exports of one
  survey share a stem and a stem-named record would be one file
  describing both. The no-silent-overwrite refusal covers the record as
  well as the data file, and neither is written when either is refused.

- **`pyflightstream.post.settings_table` and the page that freezes it,
  `docs/settings-codebook.md`** (PFS-2012.12). An OPTIONAL all-numeric
  projection of a solver-setup snapshot, for tools that cannot read
  strings, tidy by default and wide on request. Every column is numeric
  and no column carries two meanings: the value columns hold values only,
  and unknown is expressed by the provenance code with the value columns
  empty, because a sentinel may only appear in a column whose domain the
  library controls. A caller may ask for empty CODE cells to be filled;
  asking to fill a value column is refused, naming the flags whose legal
  range contains the fill. A list-valued flag contributes its length and
  the file's own legend says the form is lossy. Every file names the
  codebook version that wrote it, and reading a file written under
  another one is refused rather than silently reinterpreted. It is lossy
  by construction and never replaces the full record.

- **`docs/workspace-and-workflows.md`, the page a newcomer reads**
  (PFS-2025.21, NFR-01d). It explains what a workspace is and what the
  path from a filled-in run matrix to results actually does, in plain
  language before any signature, and then walks that path end to end.
  Every artefact on it is LIFTED from the test suite rather than written
  for the page: the matrix is a committed fixture byte for byte, and the
  input library, the recipe, the call and the four run identifiers are
  those of an executed test. A tier-1 guard holds the two together, so
  the page cannot drift from the suite without the suite going red. It
  also states plainly what is NOT built. That clause used to end
  "including that there is no workflow object in the package", which
  stopped being true LATER IN THIS SAME RELEASE, when `cases.workflows`
  shipped `Workflow` and `WORKFLOWS`; the entry further down recording
  that the page corrected itself is the surviving statement, and this
  one no longer contradicts it. The "Planned next" bullet on the
  documentation home page that promised this walkthrough is retired
  against it.

- **`SET_OUTLET_TRAILING_EDGES`, the 26.123 spelling of
  `SET_OUTFLOW_TRAILING_EDGES`** (PFS-2026.05). The newest edition
  renames the command in the chapter body and in the Script Index alike,
  with no transitional spelling documented, so a script written for
  26.122 stops working on the build issued after it. The database carries
  both names rather than one name with an alias field, and the old one
  gains a `removed` row on 26.123 naming the successor: emitting it there
  is refused with the successor's name and the page of the edition that
  documents it. Nothing was probed; the row counts a document.

- **QA reports identify the executable by its hash as well as by its
  name** (PFS-2026.17). The compat, physics and drift writers put the
  digest in the YAML beside `fs_exe` and in the rendered Executable row,
  and write it as null rather than omitting it when no digest was
  measured. The vendor installer gives four registered builds one file
  name and three more another, so a report naming one could not say which
  binary produced it. The 27 committed compat reports are untouched and
  never back-filled: a digest nobody measured cannot be recovered from a
  basename.

- **The identity question a replacement executable answers before any
  seat is spent** (PFS-2026.15). `classify_executable` and the baseline
  in `reports/RPT-032_executable-identity-baseline_2026-08-19.md`, the
  digests of the nine executables in hand, measured by hashing files with
  no solver started. An unchanged binary transfers its evidence untouched
  and spends nothing; an unknown one authorises the identity-only probe
  and nothing else; a printed build number that disagrees with the
  registry refuses with both numbers.

- **`licence_sensitive_candidates`, deriving the command rows a licence
  change could falsify for one build** (PFS-2026.16). A licence changes
  what the solver permits, so it can only falsify evidence that came from
  RUNNING the solver; a `documented` row rests on a manual page and is
  not a candidate. The function proposes candidates grouped by the
  chapter split and deliberately writes no membership: which of them a
  licensed seat is spent re-measuring is the author's judgement.

- **`tests/test_release_readiness.py`, a tier-1 guard that refuses a
  0.8.x release while 26.123 is unevidenced** (PFS-2026.14), naming that
  build as the release's LAST step rather than as one item among many. It
  requires four committed artefacts to be PRESENT and asserts no
  threshold on the number of commands absent on that build, which it
  prints instead. The `release` skill's first pause point carries it.

- **A licence-evidence card for every distribution the `[dev]` extra
  installs** (OPS-2009.02.01, PFS-2022.01.03),
  `reports/RPT-033_development-tool-licences_2026-08-19.md`, closing the
  gap RPT-016 registered in its own verdict on 2026-08-03. Each card
  names the version read, the metadata FIELD it was read from, the value
  found, the SPDX identifier and the MIT-compatibility verdict. Nine
  distributions publish a PEP 639 `License-Expression`; two publish none,
  and their MIT identifiers are recorded as readings of the legacy
  `License` field rather than flattened, because a published expression
  and a sentence somebody read are not the same grade of evidence. Every
  identifier is permissive and MIT-compatible (NFR-02). RPT-016 is
  deliberately unedited: it is what the closure is checked against.

  The guard that holds it, `test_every_development_tool_has_a_license_card`,
  reads the dev list live from `pyproject.toml` and requires each
  distribution to have a card SECTION of its own, a heading whose text
  normalises to the distribution's name. It is deliberately NOT the
  substring shape of the two coverage tests beside it, and the difference
  was MEASURED rather than argued: run over `dev`, a substring sweep is
  green today with zero cards written, because RPT-016's gap paragraph
  enumerates the uncarded names in order to say they have no card. A
  check satisfied by the sentence saying the work is undone reports the
  gap closed.

- **A stated weight budget for a mesh reader, and three candidates
  measured against it** (PFS-2025.20.01),
  `reports/RPT-034_mesh-reader-weight-budget_2026-08-19.md`. Three
  limits, each anchored to a repository fact that PREDATES the
  measurements: at most 5 MiB added, at most one new transitive runtime
  distribution, and an SPDX identifier read from installed metadata that
  is permissive and MIT-compatible. Measured in clean per-candidate
  environments: one candidate adds five distributions and 12.26 MiB and
  fails two limits, one adds a single distribution and 3.89 MiB and meets
  all three, and a NumPy-only in-house reader meets the numbers and is
  refused by the standing engineering policy instead. Coverage against
  the solver's eleven import file types is recorded per candidate and is
  deliberately not a limit. The card does not decide whether a reader
  becomes a required dependency: NFR-06's table governs that, and it is
  the author's.

- **`reports/RPT-035_mesh-reader-licence_2026-08-19.md`**, the NFR-02
  card a mesh reader would need to become a REQUIRED runtime dependency
  rather than an optional extra. It does not replace RPT-003, which is
  the adoption-time card for the `[geom]` extra; it measures the
  different surface a promotion exposes, the reader's transitive closure
  with no extras bracket. The delta a promotion adds is one distribution
  under one permissive licence. It also records that the reader publishes
  no PEP 639 `License-Expression`, so its identifier is a reading of the
  legacy field, which is worth naming where a dependency reaches every
  user with no opt-in.

- **`pyflightstream.qa.cost`, a wall-time cost view built from campaign
  manifests alone** (PFS-2018.02). `cost_view()` returns a `CostView` with
  sweep points down and solver builds across, so the same points measured
  on two builds are read side by side; `cost_rows()` is the long form, one
  row per recorded run, carrying `fs_build` and `fs_exe_sha256` as columns.

  A COLUMN IS THE PAIR, build string and executable sha256, so two
  executables reporting the same vendor build number stay two columns. A
  run recorded with no `wall_time_s` is reported as absent, `None`, never
  as zero and never as a floating-point NaN: `results.tables.run_table`
  maps the same missing field to NaN because its substrate is a numeric
  frame, and this reader deliberately does not, so a caller who sums a
  column meets a `TypeError` rather than a total that is silently short.
  `CostView.compare()` pairs only the points BOTH builds timed and names
  the rest as unpaired, so a total is never a sum over two different sets
  of work.

  `pyfs-qa cost <campaign-root>` prints that table from a campaign's
  `runs.json` with a legend mapping each column label back to its full
  build and executable hash; `--compare BASELINE,CANDIDATE` prints the
  per-point and overall ratio over the points both builds timed. It starts
  no solver and needs no licensed machine, which is now true of four of
  the seven `pyfs-qa` subcommands. The page a reader meets it on is
  `docs/solver-cost.md`, whose worked example is executed by the docs
  suite.

- **`pyflightstream._digest` states this package's hashing rule as data
  rather than as prose** (PFS-2012.10). `ALGORITHM` (sha256),
  `EXCLUDED_FROM_EVERY_DIGEST` (wall-clock timestamps, elapsed and wall
  time, absolute paths, the machine and environment, staging order) and
  `CANONICAL_FORMS`, which names the exact byte string every
  digest-computing module of the package feeds to the hash. A new tier-1
  guard walks the package for every `hashlib` constructor call and fails
  when a module hashes without declaring its canonical form, or when a
  second algorithm appears. The rule was previously written nowhere, which
  is why NFR-15 CARRIED a `pending` badge; a private module gains
  no public API, so this is an internal guarantee behind a public claim
  rather than a new public surface.

  THE AUTHOR'S SEAT RULED INSIDE THIS CYCLE and this bullet published the
  pre-ruling state until 2026-08-20. It said the NFR-15 sentence was a
  marked proposal awaiting her, and that NFR-15 therefore carried a
  `pending` badge. She rewrote the statement on 2026-08-19 and the
  requirement is `implemented`, citing `_digest` and
  `tests/test_digest.py`, on the ground that the rule is DATA in that
  module rather than prose about it. A reader following this bullet to
  NFR-15 was being sent for the opposite of what they would find.

- **The two independent reviews are transcribed into a committed report**
  (OPS-2005.11), `reports/RPT-028_independent-review-findings_2026-08-18.md`,
  one heading per finding carrying its statement, the severity the review
  published for it and the files that cite it. 41 identifiers of the
  `PYFS-nnn` and `REV010-nnn` series were cited in `src/` and `tests/` and
  exactly ONE, `PYFS-025`, was named anywhere under `reports/`, in a
  sentence rather than a heading. Every other citation resolved only into
  review documents held outside this repository, and one read-only survey
  had already concluded from that dead end that the findings could not be
  worked. The report heads all 45 findings of both reviews rather than
  only the cited 41, so a citation added later resolves without amending
  it.

- **`tests/test_review_citations.py`, a tier-1 walk that holds those
  citations to the report.** Every `PYFS-nnn` and `REV010-nnn` identifier
  appearing in a `.py` file under `src/` or `tests/` must be named in a
  HEADING of a report under `reports/`, so a deleted report or a renamed
  identifier turns the suite red instead of leaving the citation pointing
  outside the repository. A mention is not a heading and a line inside a
  code fence is not a heading, on the same reasoning as the probe-citation
  walk that requires a cited report to name the command it backs. The walk
  REFUSES when it collects zero identifiers, which is how this class of
  walk otherwise dies silently: an empty collection satisfies every
  per-identifier assertion ever written.

- **A tier-1 house-style guard refuses a NEW citation of a private ledger
  identifier** in any file the style walk reaches (OPS-2010.15). This
  remote is public and the records those identifiers name are not: the
  plan ledger and the design documents are local-only, and the incident
  ledger and the coordination hub are other repositories, so a committed
  sentence citing one sends its reader to a document that does not exist
  for them. The guard counts occurrences per unit against a committed
  inventory (`tests/data/private_id_inventory.py`) and fails four ways: a
  count above its row, a unit with occurrences and no row, a count BELOW
  its row (lower the row in the same commit), and a row over a unit now
  clean or no longer walked. Report identifiers, SRS requirement
  identifiers and plan node identifiers stay legal, because they resolve.
  No identifier is checked against a ledger: the ledgers live outside this
  repository and CI cannot reach them, so what is checked is the shape.

- **`reports/RPT-029_mypy-exemption-recount_2026-08-18.md`, the
  type-checker exemption re-count at 0.8.0.dev0** (OPS-2006.11.01). It
  carries the per-module and per-error-code tables with every
  `ignore_errors` override off, the reproduction command, the dependency
  versions the count depends on, the delta against 2026-08-03, and the
  finding that 275 errors sit on only 99 distinct source lines with six
  lines producing 73 of them, so the grind should be sized by LINES rather
  than by errors. The report was amended before it was ever committed,
  by its own reproduction rule: mypy walks the filesystem, the tree moved
  under the first measurement, and the module total is the
  re-measurement.

- **Four tier-1 tests in `tests/test_traceability.py` hold the records of
  that re-count to each other and to the package.** The module total every
  record states is compared against the tracked `.py` files under
  `src/pyflightstream` on every run, the unclean count is compared against
  the number of `ignore_errors` overrides that actually exist, and a
  record stating the measurement twice with different numbers is reported
  as stating none. The 53 in the old records went stale in silence because
  no guard compared any written record against the tree.

- **FlightStream 26.123 is registered, measured and `operational`, and it
  is the first build here that INHERITS NOTHING.** Vendor hotfix build 3 of the 26.12 release,
  delivered 2026-08-16 and registered 2026-08-17. The two hotfixes
  before it descend from 26.120, on evidence rather than on the last
  digit, and the default is right for them. The author's instruction for
  this one is the opposite, and the reason is a number rather than a
  preference: with descent on, a build issued the day before would have
  answered for the 363 commands 26.120 can EMIT without one page of its
  own manual being read or one line being run, and the compatibility
  matrix would have printed a full column on the strength of it.

  **What that costs a caller, stated plainly because it is a refusal
  surface.** Until a row exists for a command on 26.123, `Script.emit`
  REFUSES it, exactly as it refuses a command a build never had. All 414
  entries start in that state and the enumeration is committed as
  `tests/goldens/absent_on_26123.txt`, with its own counts in its header,
  so the gap is a number a reader can check rather than an impression.
  Every row written from here shrinks that file, and a tier 1 test
  compares it against what the emitter actually does. Regenerate it with
  `python scripts/gen_absent_commands.py 26.123`.

  Its support level is DERIVED and not declared, and it moved twice in
  one day for that reason: `registered` while no command answered for it,
  then `documented` once the pass below wrote its rows. Its `build` and
  `prints` come from `reports/compat/CMP-26123_2026-08-17_identity.yaml`,
  and the order those were established in is the registry's own
  chicken-and-egg: the two fields are admitted only from a committed
  report's `solver_identity`, and the run that writes one refuses an
  unregistered version, so the row was written with both unset and they
  followed. That report is also the first in this corpus to record the
  executable by a version-named name, `FlightStream_26123.exe`, rather
  than the installer's name which four builds share.
- `scripts/gen_absent_commands.py`, which writes the same enumeration for
  any registered build. General rather than named for this one, because
  the question arrives again with the next build the author decides
  should inherit nothing.
- **`pyfs-manual register`, which carries a build's documentation forward
  from a reading rather than a copy.** It compares a new edition against
  the one before it command by command and writes a `documented` version
  row for every command both editions describe IDENTICALLY: same
  signature placeholders, same sample block, same parameter table. Dry
  run by default, like `draft`.

  **It compares what the edition SAYS, never which page it says it on**,
  and that is the difference that matters. A local reflow moves a run of
  commands back by one page without changing a word, so a rule keyed on
  the page number drops every one of them; THREE of 26.123's commands
  are in exactly that position, and all three carry it in their rows. Commands the new edition describes
  DIFFERENTLY are reported and never written, because those are a reading
  somebody owes.

  On 26.123 it wrote **369 of the 371 commands SRC-751 documents**. The
  two it left are each their own work: `SET_SCENE_CONTOUR`, which the
  edition describes differently, and `SET_OUTLET_TRAILING_EDGES`, which it
  documents and this database does not carry. It also NAMES the two
  commands the new edition stops documenting, `TRAILING_EDGES_IMPORT` and
  `SET_OUTFLOW_TRAILING_EDGES`, separately from the commands neither
  edition documents: each of those two owes a reading before anything is
  written for it. 26.123 moves from `registered` to `documented` and
  `tests/goldens/absent_on_26123.txt` shrinks from 414 entries to the
  count its own header states. The digit is not repeated here: it was
  written as 45 and the golden says 43, which a release audit found on
  2026-08-20 in the third of five places that stated it.
- **26.123 is MEASURED, and reaches `operational` on the same day it was
  registered.** A Tier 2 probe run promotes 85 statuses, 84 verified and
  one broken (`reports/compat/CMP-26123_2026-08-17_full-sim.yaml`). Read
  it against 26.122's 83 and 1: one more verified, the extra being
  `SET_INVISCID_LOADS` which was unprobed there, and nothing 26.122
  verified is unverified here, so the newer build refuses nothing the
  older one accepted. The single broken command is
  `NEW_OFF_BODY_STREAMLINE`, which aborts script processing on 26.120,
  26.121, 26.122 and now this build, each on its own evidence rather than
  by inheritance.

  284 rows stay unprobed and the two reasons are the standing debts
  rather than this build's: 261 have no probe specification at all, and
  23 ran without abort or logged error while no instrument can observe
  their effect.
- **A change the vendor described directly is MEASURED, and no
  edition's text carries it**
  (`reports/RPT-027_boundary-layer-across-a-proximity-gap_2026-08-17.md`).
  Read the wording: what was measured is the integrated viscous DRAG in
  the configuration the vendor's caveat describes. That the mechanism is
  the boundary-layer mapping he named is his explanation for why the drag
  should move, and the report lists it as NOT established, because the
  instrument that would show the mechanism itself opens a modal window.
  Two copies of one wing at two gap widths expressed as a ratio of the
  measured local face length, with `SOLVER_PROXIMAL_BOUNDARIES` on and
  off, steady and unsteady, on both builds: sixteen cases. The question
  came from the vendor describing the change to the author directly, so
  this is a measurement of something volunteered rather than a gap found
  by audit.

  At two face lengths of separation the proximity setting changes the
  viscous drag by NOTHING, to every printed digit, on both builds and in
  both modes, which is the vendor's own caveat behaving as stated. At a
  quarter of a face length it changes it by 75 to 84 percent, depending
  on the build and the mode. And the two builds differ far more where
  that mapping engages than anywhere else measured: 26.123's total `CDo`
  is 32 percent lower at the narrow gap, steady and unsteady agreeing to
  two significant figures, against a few tenths of a percent at the wide
  gap.

  Read three limits with it. A lower viscous drag is a DIFFERENT answer,
  not a better one, and nothing here judges which is right. Two gap
  ratios were run, so the regime's boundary is bounded and not located.
  And the wide-gap control is not the smallest movement between these
  builds: the same day's drift run moved three viscous drag coefficients
  by 1.8, 2.2 and 9.0 percent on cases with no gap in them at all.
- **`EXPORT_BL_VELOCITY_PROFILE` cannot be used in an unattended run**,
  measured rather than inferred. It opens a modal window with a plot and
  a Done button, and script processing stops until somebody dismisses it,
  under `-hidden` with both streams redirected. Its entry records the
  behaviour and its status is unchanged: that is a fact about the
  interface rather than a refusal by the solver, and a status comes from
  a committed probe report.
- `qa.geometry.mean_edge_length`, and keyword-only `translation_m` and
  `name` arguments on `wing_triangles` and `generate_wing_stl`. Two components at a
  controlled gap need the offset in the MESH: translating one with a
  solver command would put the transform under test as well.
- **`pyfs-qa probe`, `physics` and `drift` all refuse an existing report
  BEFORE they start the solver.** The refusal itself is unchanged and
  correct, a report is evidence and is never overwritten; it was asked
  after the run. A full campaign on 26.123 executed 111 command probes
  over five minutes of licensed solver and then the write refused on a
  stem that already existed, so a licence checkout was spent and
  discarded on a collision knowable from the command line. The repair
  first reached `probe` alone and the other two kept the defect, where
  it was worse: the whole Tier 3 matrix could run and then die on an
  uncaught `FileExistsError`, which probe at least caught and printed.
  Three copies of one rule is why a repair could reach one of them, so
  the rule now lives in `pyflightstream.qa.reports` and all three ask it
  first; the identical command refuses in under a second saying
  `nothing run`. The date is resolved once per run and handed to the
  writer, so a matrix started before midnight cannot check one stem and
  write another.
- `ProbeOutcome.REMOVED`, promotable like any other outcome. A build
  that does not carry a command used to record `broken`, which is a
  different claim. Both refuse at build time, so the difference is
  WHICH refusal: `broken` keeps the command in the version view and
  raises `BrokenCommandError`, whose message says the solver accepts
  the line and would return numbers nothing marks as wrong, and which
  `allow_broken` waives. Both halves are false for a build that does
  not carry the command, and a waiver would emit a line the solver
  rejects outright. The signal is the solver's own refusal naming that command,
  measured rather than paraphrased (RPT-026), read from the crash log
  the harness had never opened.
- A supersession check in `apply_compat`. Re-running the sanctioned
  write path on an older report used to revert a status a later run had
  already moved, with a citation that agreed with itself and every
  guard green (`PLN-20260804-1500`). A tier 1 guard asserts the same
  invariant over the committed database.

### Changed

- **A citation re-check records how each row it SAW ended, not only how
  many it saw and how many it read** (OPS-2003.10.02).
  `utils.manual.citation_reach` returns the four outcomes named by the
  new `CITATION_REACH_OUTCOMES` (`no_note`, `no_page`, `removed`,
  `checked`) plus `range_cited`, and `pyfs-manual citations` prints the
  four per edition.

  The four PARTITION the rows seen, which is the point: the report used
  to print the whole difference between seen and checked as one
  unexplained gap, and attributing all of it to one reason is the mistake
  the counter's own comment warns about. `range_cited` is a stated subset
  of `checked` and never an addend, and a row whose edition the manifest
  does not list is counted in none of them, because the run has no
  reading to check it against; those builds keep their own line.
  Separating the outcomes corrected a published number immediately: of
  26.120's 381 rows, 359 carry no note at all and 4 carry a note with no
  page of its own, where one sentence had covered both.

- **`pyflightstream.post`'s module docstring stops advertising what the
  layer does not have** (PFS-2015.01, NFR-11). It had claimed the layer
  "performs blade-passage averaging for unsteady runs" while importing
  that name raised `ImportError`, and announced a `ResultArray` facade as
  planned. The averaging now exists; the facade does not, and the
  docstring says so in its own section rather than describing it as
  forthcoming.

- **One type-checker exemption is REMOVED, the first this project has
  been able to remove on evidence.** `pyflightstream.results.tables` was
  exempt and is now clean: deleting `_as_workspace` took the module's
  last type error with it, measured with every override off. The
  `[tool.mypy]` header has promised since 2026-08-03 that an exemption is
  removed as its module is typed and never added, and this is that
  direction happening rather than being restated. The re-count moves with
  it: mypy recount 2026-08-24: 276 errors in 20 of 74 modules, where the
  tree carried 275 in 21 of 64 two days before, and the four records that
  state it move together because a tier-1 guard compares them.

  It was re-measured a THIRD time on 2026-08-20, when this release's last
  two modules landed and the module-total guard went red exactly as
  designed. `scripts/mypy_recount.py` emits every figure the report
  states from ONE run now, so the failure that started this, a sentence
  retyped while the tool output beside it was not, cannot be repeated by
  hand.

- **The FSI persisted state and its convergence log name the digest
  `config_sha256` rather than `config_hash`** (OPS-2009.01.14). A
  `state.json` written by an earlier release STILL LOADS: `FsiState`
  carries `validation_alias=AliasChoices("config_sha256", "config_hash")`
  with `populate_by_name=True`, so the legacy key is accepted on the way
  in and only the new name is written on the way out, and a resumed run
  migrates its own run folder on its first write.

  Without that alias the rename would have been silently DESTRUCTIVE
  rather than merely breaking, because the model forbids extra keys: the
  old key would not have been ignored, it would have been refused, and the
  whole state file with it.

  One consequence worth planning for: a run resumed into an EXISTING
  `fsi_convergence_log.csv` keeps that file's old header word, because the
  header is written only when the file is absent. The column order, the
  column count and the meaning of every column do not move. The three
  committed `reports/fsi/*_convergence.csv` keep the old header as
  historical evidence.

- **`scripts/gen_requirements_index.py` refuses a malformed requirement
  page instead of publishing it**, exits non-zero and writes nothing
  (OPS-2005.09). Four shapes: a requirement box with no `srs-` badge,
  which used to default to `implemented` and so published a requirement
  nobody has built to an external dashboard as done and mandatory; a badge
  token outside implemented/pending/deferred/deprecated; a repeated
  identifier; and a `!!! requirement "` header the box pattern cannot
  read, which produced no entry at all while its body was absorbed into
  the previous requirement. The first three name the page and the
  identifier; the fourth names the page and the line number. The emitted
  payload is unchanged: the same 96 requirements, byte for byte.

- **The push-gate suite says WHICH refusal fired** (OPS-2006.08). A deny is
  not one outcome: the gate brackets a sub-kind because the remedies
  differ, `[review]` meaning run the reviewers, `[ledger]` meaning repair
  infrastructure, `[config]` meaning export one variable, `[gate]` meaning
  the gate itself crashed and fell closed.

  Measured rather than argued: a copy of the gate was sabotaged with one
  statement, `raise RuntimeError` at the top of `main`'s try block, so
  every push denied through the fail-closed arm with no check in the body
  reached, and 21 of the file's 69 cases STILL PASSED. Fifteen of those 21
  exist to assert a REFUSAL. One passed on a substring collision rather
  than on a bracketless assertion: the case pinning that a deletion deny
  does not prescribe pushing the ref looks for "author decision", and the
  fail-closed message ends "an author decision, not a workaround".

  Every refusal case now names its sub-kind, and the check reads the
  bracket that OPENS the message and compares it for equality rather than
  searching the reason for a substring. `[gate]` is refused everywhere
  except in the one case that is about the fail-closed arm, so the rule
  holds for cases that name no expectation at all. Against the same
  sabotage the file now fails 65 of 74, and the survivors are the cases
  that read text rather than drive the gate. The gate's message prefix and
  the incident-ledger environment variable are READ out of the gate body
  instead of mirrored: a rename in the kit used to leave the suite
  stripping a variable nothing reads, which silently pointed every hook
  subprocess at the author's real ledger with nothing going red. A new
  partition guard fails when a sub-kind arrives in a re-vendored body that
  no case pins and no declaration excuses. Test-only: no public name, CLI,
  extra or behavior moves.

- **The `[tool.mypy]` header comment no longer states the 2026-08-03
  measurement as though it were current** (OPS-2006.11.01). It records the
  first measurement as history and the re-count beside it, and it
  separates the two kinds of number: the error total is a DATED
  measurement that moves with the code and with numpy's, xarray's and
  pandas' own stubs, while the module total is re-counted from the tracked
  tree on every test run. No override was added and none was removed,
  which is the measurement rather than restraint: the set of modules that
  report an error with the overrides off is exactly the set the overrides
  name.

- **The `pyflightstream.versions` module docstring no longer calls itself
  "the lowest layer"** (OPS-2005.12), which stopped being true once the
  base-exception module was recorded below it. It now reads "the bottom of
  the pipeline proper, above only `_errors`". This is a user-visible
  documentation change rather than an internal comment: that sentence is
  published verbatim on the generated architecture page.

- **Four writers stopped replacing a file without saying so**
  (PFS-2011.02, FR-33c, FR-33b, FR-29). PYFS-005 records the class: one
  point of a campaign overwrote another's output while the run record
  listed both complete, which cost licensed solver time and could have
  published a report from one point counted twice. The guard written
  afterwards covered the surface where it was found; three others took a
  caller-chosen path with no case and no manifest to key on.

  EACH SURFACE REFUSES DIFFERENTLY, because the signal is different in
  each, and that is the whole content of the change rather than an
  inconsistency. `post.writers.write_vtk_points` and
  `write_tecplot_points` ended in a plain file write, so the signal is
  that the destination exists; both gain `overwrite=False` and raise the
  new `OutputExistsError`. `script.helpers.export_probes` asks the SOLVER
  to write, so nothing exists yet at script-build time and the signal is
  that this script already asked for that path; the register lives on the
  `Script` because the collision is between two CALLS and only the script
  sees both, and the refusal names BOTH call sites, since one naming only
  the second sends the reader to the line they do not need to change.
  `fsi.driver.coupling_step` APPENDS by design, so neither the log's
  presence nor its absence is the signal: it is the PAIR, a convergence
  log with no `state.json` beside it, which is a previous run's history
  in a folder being reused.

  `OutputExistsError` is new in `pyflightstream.exceptions` and keeps
  `FileExistsError` as its second base, so an existing handler around a
  write catches what it always did. The evidence writers under `qa` keep
  raising the builtin for the same situation, deliberately: that predates
  the catalogue's reach, and a new raise site takes the catalogued type.

  `script.helpers.export_results` is a fourth writer of the same shape
  and is deliberately NOT covered: the item names three surfaces, and
  widening a guard beyond them would put a decision nobody made into the
  tree.

- **`collect_outputs` refuses a source that escapes the run** (PFS-2011.01
  and PFS-2011.03, FR-28 and FR-29, one piece of work). Collection MOVES,
  and the method moved any path it was handed: naming
  `sims/sim_OTHER/raw/loads.txt` as an output took another run's
  collected evidence into this simulation's `raw/`, and both manifests
  then named a file only one of them had.

  The rule is on RESOLVED paths and never on the declared string, which
  is why it is not the check in `naming.py`: that one refuses any
  ABSOLUTE path, and every production caller here passes absolute paths,
  so reusing it would have refused the normal case. A produced path that
  resolves INSIDE the campaign root must resolve inside this
  simulation's own folder and not under one of its four managed
  subdirectories; the refusal names the ROLE of the folder it landed in,
  and names the simulation a file belongs to when it belongs to one.

  Two acceptances are deliberate and are stated in the docstring rather
  than left to be discovered. A source OUTSIDE the campaign root still
  collects: that is the ordinary case, since the solver's working
  directory is not managed by this class. And an unmanaged subfolder of
  the simulation, `sim/out/`, still collects, because nothing here owns
  it and moving a file out of it destroys no record. A blunt "under the
  simulation" rule would have refused that one.

  The check runs before the collision pre-scan and therefore before any
  move, so a refusal leaves every source exactly where it was. The
  summary line now says collection MOVES, which a reader has had to infer
  from the collision message until now.

- **One owner for the checksum that decides whether two runs used the
  same inputs** (PFS-2012.02, NFR-07). The sha256 behind that claim was
  written in FOUR places: a chunked read in `workspace`, a second in
  `run` differing only in its failure policy, and two inline text hashes,
  one in `run` and one in `qa.probes`. Nothing stopped two of them
  diverging and nothing would have noticed if they had; the manifest
  would simply have said two identical runs were different, or two
  different runs the same. And the run layer reached ACROSS A LAYER
  BOUNDARY for `workspace._sha256`, an underscore-private name, rather
  than write a fifth.

  `pyflightstream._digest` is now the one home, below every layer exactly
  as `_errors` is and for the same reason: it imports nothing from the
  package, so every layer may use it and none imports another to get it.
  It exports `file_sha256`, which RAISES, `optional_file_sha256`, which
  answers `None`, and `text_sha256`. The two file functions differ only
  in their failure policy and the policy is carried by the NAME, because
  a caller who picks the wrong one gets either a run that dies on a
  provenance field or a manifest that silently records nothing.

  The VALUE did not move: one fixture hashes identically through the old
  chunked read and the new owner, which matters because every committed
  manifest records digests written by the old one. No public signature
  moved either, and the module is private, so nothing is added to the
  surface. A FOURTH caller the plan had not named, in the resume
  comparison, was found by the linter when the upward import went and
  takes the raising form.

- A compat report's `summary` now carries one key per outcome, derived
  from the enum, so `removed` appears beside the other three. Readers
  keying on the old three names are unaffected.
- An abort caused by a command OTHER than the probed one now records
  `unprobed` naming the offender, where it previously recorded the
  probed command `broken`.

- `AIR_ALTITUDE` is emittable on 26.122. It had inherited `broken` from
  26.120, where the solver reads its `METERS` argument as feet, and the
  first probe on this build reads the 5000 m standard-atmosphere
  density correctly, so the builder no longer refuses it there. This is
  the one caller-visible change to what a 26.122 script may emit
  (`reports/compat/CMP-26122_2026-08-11_full.yaml`, read with
  `CMP-26122_2026-08-11_full_erratum_2026-08-11.md` beside it: the
  report's own note for this command carries a sentence that is false
  on this build, and the report is evidence and is never edited).
- `PHY-05` and `PHY-06` are registered for 26.121 and 26.122, not
  26.120 alone. Their pin cited a backfill owed for EARLIER builds,
  which never applied to later ones.

- **Process only, no package change: the CI-green tag rule moved from a
  repository-owned hook into the shared push gate.** Ten kit bodies were
  re-vendored (kit 0.2.18/0.2.19/0.2.15/0.2.11/0.2.10/0.2.5, per file),
  and `.claude/hooks/ci_release_gate.py`, its wiring in
  `.claude/settings.json`, `tests/test_ci_release_gate.py` and that
  hook's mutation battery were deleted in the SAME commit, never before
  it and never after. Two new vendored files sit beside the gate,
  `ci_state.py` and `ci_state_mutations.py`, because the 0.2.18 gate runs
  the first as a subprocess and treats its absence as a refusal.
  `scripts/prove_extras_and_ci_guards.py` is renamed
  `scripts/prove_extras_isolation.py`, having lost the half it was named
  for. Contributor-visible: the mutation battery's path and its label
  prefixes changed (`BM*` are gone); the gate's hook timeout in
  `.claude/settings.json` is 90 seconds rather than 30, because the
  vendored body budgets 50 seconds of CI work and a hook the harness
  kills emits no decision at all.
- **Every skill now declares `side-effects:`, and none carries
  `disable-model-invocation`.** The author retired the human-only flag at
  kit 0.2.19 on 2026-08-11, across all skills with no exception,
  including `release` and the three that spend a licensed solver seat.
  Six skills that had declared nothing (`add-command`, `audit`,
  `derive-requirements`, `handoff`, `plan`, `role-review`) now do; the
  guard's own measurement went from `4 declaring, 6 undeclared` to zero
  undeclared, over a population it derives at run time. The end-state
  count is deliberately not quoted here: it was ten when this was
  written and eleven a few hours later, when the vendored
  `version-control` skill arrived.
- **`PYFS_INCIDENT_LEDGER` is retired**, and a fresh clone now sets four
  machine-configuration variables rather than five. The 0.2.11
  incident-analyst charter reads `COORD_INCIDENT_LEDGER` like everything
  else, so the old name had no consumer left. CLAUDE.md keeps a
  retirement notice so a machine that already exports it learns why to
  stop.
- CLAUDE.md gains an `## Execution rules` section (pointers, not
  reasoning) and a pointer to `BRF-082`, whose wording lives in
  `.claude/skills/role-review/SKILL.md`: the adversarial pass runs BEFORE
  a completion claim rather than as a review round after it.
- **Process only, no package behaviour change: the shared process kit is
  fully vendored.** Twenty-four further artifacts arrived on 2026-08-11,
  taking the drift manifest from 11 rows to 35, each pinned to its own
  `body-sha256` at mixed kit versions from 0.1.0 to 0.2.22. Two kit
  artifacts are absent BY DECISION
  and not by omission: the `release_caller.yml` and `release_gate.yml`
  workflow templates, declined because this repository's `release.yml` is
  a single workflow that has published v0.4.0 through v0.7.0.
  Contributor-visible: a `version-control` skill is now available, and
  `CLAUDE.md` gains a `## The vendored process kit` section recording
  which checkers are wired and the reason beside every one that is not.
- **A second PreToolUse hook now refuses two shell shapes.** The kit's
  `execution_guard.py` (0.2.22) denies a status-bearing command (`pytest`,
  `mypy`, `ruff`, `git push`, or a `check_*.py` / `*_mutations.py`
  script) piped into a line filter (`head`, `tail`, `wc`,
  `Select-Object`, `Measure-Object`, `select`, `measure`), and a heredoc
  whose body carries a backslash or a control byte. Both denies name a
  category (`[piped-status]`, `[heredoc-content]`) and a remedy, and
  neither can block a push. Contributor-visible because it changes what
  a shell command may look like; the arms, the remedies and the one
  known false positive are in `CLAUDE.md` under `## The second PreToolUse
  hook: the execution guard`.
- Tier 1 now runs a tree-wide forbidden-identifier scan and four vendored
  mutation companions, and takes roughly ten minutes rather than six. The
  single largest term is the push gate's own companion at 244 seconds.
- Every `subprocess.run` under `src/` and `scripts/` now passes an
  explicit `env=`. The value is `os.environ.copy()` in each case, which
  is exactly what an omitted `env=` gave, so no child's environment
  changed; what changed is that the inheritance is a decision at the call
  site. Found by the newly vendored `check_spawn_env.py`, which is wired
  in tier 1 over those two trees; the 24 unguarded spawns under `tests/`
  are pinned as a ratchet rather than silently excluded.

### Fixed

- **The FR-39 TypeError tranche is EMPTY, not merely smaller**
  (OPS-2009.01.08). Three raise sites on the public path raised a bare
  `TypeError`, so `except PyflightstreamError` caught none of them: two
  in `results.to_table` and one in the entity registry. All three now
  raise a catalogued class keeping `TypeError` as its second base, and
  both ratchet rows came out in the same edit that re-based their raises.
  It is the first tranche this ratchet has emptied rather than shrunk,
  and the ratchet's own header now counts 13 entries over 16 raises
  rather than 15 over 19.

  The decision that had deferred it stopped being open on 2026-08-17,
  when the first non-ValueError base entered the table and made its shape
  a precedent rather than new ground.

- **The examples run promotes only THIS package's warnings**
  (OPS-2006.02.02), and the two halves landed in one change because
  either alone is worse than neither. Eleven `warnings.warn` sites are
  retagged onto the package's own categories, the ratchet that recorded
  them is empty, and the six command homes are narrowed from a bare
  `-W error` to the package category. Narrowing first would have stopped
  catching ours; retagging first would have left a dependency's
  deprecation still able to redden the build.

  `VersionMismatchWarning` settled four of the eleven sites at once by
  being re-parented, keeping `UserWarning` in its MRO. A strict expected
  failure stood in the suite saying it would turn into a failure on the
  day the narrowing landed; it did, and it is gone.

  WORTH KNOWING BEFORE YOU COPY THE FILTER: `python -W
  error::pyflightstream...` does not work and fails SILENTLY. The
  interpreter parses its own `-W` before this package is importable,
  prints `Invalid -W option ignored` and promotes nothing at all.
  `pytest -W` parses later and does work, which is why every promotion
  home here is a pytest command line and why the category lives in a
  module that imports nothing.

- **A campaign with a failing point left no sweep table at all**
  (PFS-2014.03). The command line caught the after-the-loop failure with
  the refusals that fire BEFORE the campaign ran and returned without
  writing, so every point that did run lost its evidence with the exit
  status. The two are separate arms now: a run that executed and had
  failures still writes its table and still reports the failure. It also
  passes `require_loads=False`, the keyword written for exactly the
  condition it was printing "sweep table not written" over.

- **The reader weighed fewer axes than the assessor** (OPS-2009.01.13).
  The table reader compared only the point's own axes, so a requested
  free-stream velocity the assessor checks was invisible to it. The
  requested velocity now joins the axes, with `setdefault` and not
  assignment, because the point's own value wins over the case default
  and a plain assignment would have reversed that precedence silently.

- **An example run's warnings are read off stderr rather than promoted.**
  The run checked the exit status only, so an example that started
  warning kept exiting 0 and the reader met the warning before anyone
  here did.

- **The solver-setup provenance snapshot read the PACKAGED command
  database rather than the one its script was built with** (PFS-2012.05),
  so a run manifest could carry an availability, a default or an evidence
  sentence from a database no line of the script was ever checked
  against. `build_setup` now takes the registry and the settings helper
  passes the script's own, and `Script.registry` exposes it so a caller
  can ask the same question the script answered.

- **A fixture library staged six files no id could ever reach.** The
  builder behind the workspace walkthrough wrote both the bare
  three-digit codes and the new letter-prefixed ones, so the bare files
  sat on disk unreachable under the id rule that landed with them. Found
  by the page-currency guard over that builder rather than by any test of
  the library, and only because that guard asserts its collection is
  non-empty BEFORE it compares: its first version matched a literal path
  spelling out of the source text, and the rewrite to a loop left it
  matching nothing while every artefact was still staged. It now RUNS the
  builder and reads what lands on disk, so it survives any rewriting of
  how the paths are spelled, which is the only thing that ever broke it.

- **A refusal that used to name what is available named nothing.** The
  structured `available` attribute is populated on a not-found refusal
  and empty on a refusal about the id's own shape, which is about what
  the caller wrote rather than about what the library holds. Both
  branches are now pinned and the class docstring states the difference,
  because an empty tuple would otherwise be read as an empty library.

- **Every byte of a vendored process-kit file is now pinned, its
  provenance header included** (OPS-2013.30). Only the BODY was hashed
  before, and the header was reached by three assertions that each read
  one field, so an arbitrary extra line above the END KIT PROVENANCE
  marker, a `contact:` field carrying a personal address for instance,
  passed the body hash, all four field assertions and the header parser.
  That is in exactly the directory where a vendored kit body once
  published a personal name, address and user-profile path on this public
  remote.

  `tests/test_kit_drift.py` now carries a header sha256 pin per manifest
  row, asserts that the two tables carry the same keys in both directions,
  asserts that the header and body regions are exact COMPLEMENTS so the
  coverage claim is a measurement rather than a claim, and proves the
  refusal with a mutation: the same vendored file with one injected
  contact line fails the header pin while its body sha256 still matches.
  No test enumerates permitted header keys or line shapes, because the
  headers are not uniform and a shape rule would be a whitelist of prose.

- **The last vendored provenance note stops pointing at a kit directory
  retired on 2026-07-27** (OPS-2013.04). `.claude/tools/check_incidents.py`
  now names the live kit path, which is the prescribed per-copy restamp of
  an unhashed header line and leaves the pinned body untouched, and
  `tests/test_kit_drift.py` records that target. Two new guards keep it:
  one forbids the retired path in any provenance note whatever the
  manifest says, one forbids pinning it in the manifest. Both are needed
  because the kit README still prescribes the OLD wording, so a re-vendor
  performed to its letter reproduces the stale pointer while updating the
  manifest row in the same edit.

- **The user guide guard covers all six objects the guide hands the
  reader, not three** (OPS-2005.05). `campaign` joins the objects whose
  taught attributes are held against the real class, and any pydantic
  model's fields count as known, which is what makes `Campaign.fs_exe`
  visible at all since it is absent from `dir(Campaign)`. A second half
  checks that every class name the guide names in a code span resolves in
  one of the modules the guide's own import lines name, plus
  `pyflightstream.exceptions` and `pyflightstream.qa.geometry`:
  `CampaignWorkspace` and `RunRecord` are taught that way and carry no
  dotted usage at all, so renaming `RunRecord` used to leave the whole
  module green.

- **The premise of the exemption re-count item is recorded as false rather
  than worked around** (OPS-2006.11.01). `pyproject.toml` carries 21
  `ignore_errors` blocks and the test module's inventory carries 21 names,
  `pyflightstream.workspace.inputs` and `pyflightstream.workspace.naming`
  among them in BOTH, so nothing was excused without being recorded.
  RPT-029 cites the lines and a test asserts it.

- A probe detail carrying a backslash reached the rewritten chapter
  unescaped, because the `note` key was interpolated between two
  literal quotes while every other key went through the module's
  renderer. A Windows path in a solver message therefore either aborted
  a whole promotion or, where the backslashes happened to precede valid
  YAML escapes, wrote a silently corrupted note and reported success.
  Shipped since v0.4.0; no committed row carries the corruption
  (`INC-20260811-1511-both`). There is now one emitter and its escaper
  has exactly one caller, both asserted.
- `apply_compat` is all-or-nothing across chapters. A refusal raised
  while rewriting chapter n used to leave chapters 1..n-1 promoted on
  disk, under a message naming one command in one file, while the
  docstring said nothing was written.
- Three reachable inputs escaped both the documented `QaEvidenceError`
  and the CLI's trap as Python stacks: a mistyped report path, an
  unparsable report, and an unparsable file anywhere in
  `reports/compat/`. A rewritten entry that fails the command schema
  now refuses in the same type rather than surfacing pydantic's.
- The probe specification for `SET_MOTION_START_TIME` created a rotary
  motion, which that command refuses by design, so the abort it was
  recorded for was the probe's and not the solver's.

  NOT RESOLVED BY THAT FIX, and stated here because the guide says so
  and this file said the opposite: the command is still recorded
  `broken` on 26.101, 26.120 and 26.121, and 26.122 inherits 26.120, so
  the emitter refuses it on four builds TODAY. The corrected
  specification is measured to run on all four
  (`reports/compat/CMP-26101_2026-08-11_starttime.yaml` and the same
  stem for 26120 and 26121, plus the 26.122 full report), and an
  `unprobed` result cannot demote a `broken` one through the sanctioned
  write path. Lifting the refusal needs a demotion path that does not
  exist yet (`PLN-20260811-1300`).

- **A compat report carried `date: null` in its body while its own file
  name carried the date**, and 85 database rows cite it
  (`INC-20260817-2210-pyflightstream`). The cause was a transient state
  of the same session: the date defaulting moved into the path helper
  while the refusal was being hoisted ahead of the solver, and the probe
  run landed in the window before it was restored beside the writer.
  Deleting exactly one line from the current writer reproduces both
  committed files byte for byte, which also rules out a hand edit. Three
  guards now hold it: the writer is called with NO date and the stem, the
  body and the rendered header are required to agree; the path helper is
  required to default the same way, because the mirror-image mutation
  corrupts the pre-flight rather than the file; and every committed compat
  report is walked and its body date required to equal the date in its
  stem. The report itself stays as it is, on the author's decision of
  2026-08-18, with an erratum beside it and a single named exemption in
  the walk; `reports/compat/README.md` gained the report-level erratum
  contract that shape needs.

- **The refusal that protects a licensed seat was decorative for two of
  the three evidence writers.** `physics` and `drift` predicted their
  report name from a series prefix and a build key the CLI pasted
  together itself, while each writer pasted the same thing together a few
  hundred lines away; the two agreed by coincidence and nothing tied
  them. Measured by sabotage: changing `write_physics_report`'s own
  prefix from `PHY` to `PHZ` left forty-five tests green while the
  pre-flight silently inspected a name nothing would ever write, which is
  the incident the pre-flight exists to prevent, one field over. The
  build key is derived in one place now, each series has a helper its
  writer and the CLI both call, and each writer's output path is asserted
  against that helper rather than against a literal.

- **The date was resolved twice per run**, once for the pre-flight and
  once inside the writer, so a Tier 3 matrix started at 23:59 cleared the
  collision check against one day and wrote under the next. The failure
  is a MISSED refusal, so its cost is the licensed seat. Each command
  resolves it once and hands it to its writer.

- **A library refusal told a Python caller to pass `--smi-root`**, a flag
  that exists only on a command line the library knows nothing about. The
  same class was corrected at two sites on 2026-08-17 and this one, one
  screen below a corrected sibling, was missed. The rule is mechanical
  now and carries no exemption list: a refusal raised outside a CLI that
  names `--some-flag` must also name `some_flag`.

- **Two mutation batteries and a reproducibility script reported success
  they had not earned.** `prove_alias_tally_guard.py` still read a kill
  off any non-zero exit, so pytest's collection error, usage error and
  no-tests-selected all scored as the guard denying; since its selector
  is a long node id, renaming the guard would have printed "6 of 6
  mutants killed" and exited 0 while judging nothing. It takes the shared
  three-valued verdict now and an inconclusive stops the run.
  `restate_26123_notes.py`'s reach floor short-circuited on zero
  recognised rows, which is exactly the post-restatement shape it was
  written from, and its own docstring documented a `--dry-run` its parser
  rejects.

- **Two published reproduction commands exited 2 for anyone who tried
  them**: the version registry's own command for the seventeen-page
  edition delta omitted its required `--editions`, and the restate
  script's docstring named a flag that does not exist. Both were found by
  a reader trying the command. Every published `scripts/*.py` invocation
  in the tree is now checked, statically and without executing anything,
  against the target script's own parser.

### Documentation

- **`docs/workspace-and-workflows.md` no longer says there is no workflow
  object, because there is one** (PFS-2025.10, PFS-2025.21). The page
  explains what a workflow IS before it shows a signature, carries the
  committed workflow matrix byte for byte, shows the one-line terminal
  command, and states the assessor's swept-row limitation plainly. Its
  "what does not exist yet" section was rewritten so nothing on it is
  false. The page was written the day before the capability landed and
  would have become a lie in one commit; a tier-1 guard is what made that
  impossible rather than merely unlikely.

- **The user guide's curated-helper count is a digit rather than a
  word.** The set passed twenty when the rotor emitters landed, and the
  guard that holds the guide to the module reads one word at a time, so a
  two-word number could never be read through it. The guard's own message
  named the remedy and the guide takes it; the word table deliberately
  stops at twenty and says why.

- **A trailing-edge parameter's fifth field is READ, RESTATED and
  reachable from a rotor row** (PFS-2026.06). The newest edition gives
  the relaxed trailing-edge component parameter an integer shedding
  direction, axial by default and azimuthal otherwise.
  `script.helpers.parse_relaxed_trailing_edge` reads a specification in
  either shape, `RelaxedTrailingEdge.render()` writes it back, and
  `cases.workflows.rotor_relaxed_trailing_edges` restates a rotor case's
  specifications in the direction its `ROTOR_SHEDDING` cell asks for.

  READ THE BOUNDARY WITH IT, because this bullet said the opposite half
  of it until 2026-08-20 and both halves are true. NO SCRIPTING COMMAND
  on any registered build takes the direction, so the emitted script is
  byte-identical with and without the cell, and no status, manual
  reference or version row moved. And THIS PACKAGE STILL WRITES NO
  COMPONENT FILE: the restated specifications are returned as text for
  the caller to write where their geometry keeps them. Whether the
  package should own that file is a product-owner question and is still
  open.

  The four-field form is not silently widened. A specification parsed
  with four fields renders with four, and asking for the axial direction
  on one that leaves the field unwritten returns it unchanged, because
  writing the 0 would hand a five-field specification to a build that
  reads four. A direction a row invents is refused before the first
  emission, naming the case, the key, the value and both accepted
  directions.

- **`reports/compat/README.md` gained three sections** (PFS-2026.15,
  PFS-2026.16, PFS-2026.17): which binary produced a report and why the
  committed corpus can no longer answer that, what a digest does NOT
  answer (the licence), and the identity check a replacement executable
  goes through before it spends a seat.

- **The command database's version metadata records what a licence tier
  could falsify**, beside the version rows it is about, and records the
  two statements the newest manual edition WITHDREW (PFS-2026.10,
  PFS-2026.16): the claim that at higher control-surface deflection
  angles the solver captures the tip vortices directly, printed twice in
  the previous edition and in neither place now, and the guidance to set
  the wake decay constant to zero for marine applications. Nothing in
  this repository asserted either as current, which is recorded as a
  measurement with its exclusions rather than as a reassurance.

- **Two new committed reports** (PFS-2026.08, PFS-2026.15). RPT-031
  records the search of the 26.123 scripting reference and Script Index
  for the command that sets the aeroelastic coupling tolerance: the
  answer is that NO such command is documented, with nine candidates
  rejected and a reason for each, and the modal-representation claim
  measured as absent from all nine manual editions. The chapter header
  that asked for that search is updated to cite it, so the file no longer
  asks for work already done. RPT-032 records the digests of the
  executables in hand as the baseline a replacement is compared against.

- **The three skills that spend a licensed solver seat carry an
  identity-first step** for a REPLACEMENT executable of an
  already-registered version (PFS-2026.15), a case that previously fell
  between all three.

- **`RPT-024`'s Script Index caution is amended with a DIRECTION rather
  than a correction.** It recorded only that the index UNDER-reports; the
  newest edition lists a command in its Script Index that its chapter
  body no longer prints at all, which is the mirror failure. The rule
  does not change and the body is still what is read; what changes is
  that a disagreement between the two is not by itself evidence of which
  one moved.

- **The getting-started page gains the time-resolved history section**,
  with an executed example, and states plainly that the file's shape is
  documented and not yet OBSERVED.

- **`docs/solver-cost.md`, a new page explaining what a run cost and how
  to show that a build got slower** (PFS-2018.02), with a worked example
  the docs suite executes, so it cannot rot into a lie. It says in plain
  words the three numbers the view refuses to invent: an untimed run is
  absent rather than zero, a column is a build AND an executable, and a
  comparison counts only work both builds did.

- **The Role-based review row of `docs/srs/standards.md` names the two
  mechanical refusals the project already relies on** (OPS-2005.07,
  closing OPS-2005.23 against the same edit). The PreToolUse hook denies a
  `git push` carrying no attestation over every commit the push makes new
  plus each ref it sends, and the same hook denies while a blocking
  incident is open in the shared ledger, whose one home stays the
  machine-configuration table in `CLAUDE.md`. The row previously stopped
  at the five reviewer charters, so the SRS published a WEAKER discipline
  than the one this changelog had already announced.
  `tests/test_claim_currency.py` holds the row per clause, so a gate
  described as a reminder fails tier 1.

- **The Adopted table of `docs/srs/standards.md` gains an `Enforced by`
  column on all 14 rows** (OPS-2005.08.01), with a lead paragraph defining
  the three answers it accepts: a repository path or a CI command, a named
  review seat with its charter, or the literal word convention for a
  practice nothing mechanical refuses. Five of the fourteen say so on
  purpose. `tests/test_claim_currency.py` fails when a cell is empty, when
  it names a repository path the tree does not hold, or when it names a CI
  command that appears in no workflow, and it resolves the column BY LABEL
  rather than by position.

- **The published layer map records `_errors`** (OPS-2005.12,
  OPS-2006.02.01). The generated architecture page and the SRS
  architecture chapter now carry `pyflightstream._errors`, the
  base-exception module, as the row below `versions`. It imports nothing
  from the package and most of the package imports it, and it appeared in
  none of the places the layering was stated. The page also renders that
  module's own docstring as its own section, so a reader asking why one
  module sits outside the pipeline gets the answer from the module rather
  than from prose about it.

  Four tier-1 guards now derive every prose restatement of the layer stack
  from the single home of it, the layer data in `pyflightstream.overview`,
  and fail naming the one file that disagrees: the fence in the SRS
  architecture chapter, that chapter's side-branch paragraph, the layout
  rule in `CLAUDE.md`, and the layer diagram in the user guide. The guards
  write out no layer name of their own, so they are a check rather than a
  fifth copy to drift, and the guide is covered for the first time by
  anything at all, since it is not built by CI.

- **The print-precision premise behind the operating-point tolerances
  cites its source** (OPS-2009.01.01). `results.conditions.FIELD_BINDINGS`
  and the `tolerance` attribute of `ConditionCheck` name the committed
  export the three-decimal print width was read from, state that this is
  ONE measured build rather than a solver guarantee, and say that beyond
  that file the threshold is project-chosen and claims nothing about the
  export. RPT-006 is cited as corroboration of the header's three-decimal
  print for a different header quantity, not as a second reading of these
  three fields. Five tests read the citation out of the source, open the
  export it names and assert the printed width against each tolerance, so
  the premise fails the suite instead of quietly becoming a recollection.
  No tolerance value and no behaviour changed.

- **The deprecation ledger's comment stops saying there is nothing to
  track** (PFS-2021.01.01). It said an empty tuple meant the package made
  no deprecation promises. TWO are live and neither is a module shim,
  which is all that tuple can hold: the
  `analysis_setup(vorticity_drag_boundaries=...)` parameter warning, and
  the dry-run rename that the v0.5.0 notes recorded as announced and not
  landed, and that is still unlanded. The comment now names both with the
  line and the quoted text of each, says the tuple models module shims
  only, and records no removal version, that being the author's call while
  NFR-20 does not bind before 1.0.

- **The FSI package no longer cites a private tracking identifier** for
  the unverified status of the structural model's primary sources
  (PFS-2017.01.02). `fsi/centrifugal.py` and the FSI README now say in
  plain words that the primary sources have not been independently checked
  against the formulas implemented here, and that the formulas should be
  read as transcribed from the coupling plan and believed correct rather
  than as verified against the papers. The identifier's only home was
  another repository and no committed report carries it, so a reader
  following it reached nothing. Every `Source:` citation is unchanged, and
  a new tier-1 table pins the primary source each of the fourteen FSI
  physics functions names, so a future rewording cannot quietly drop one.

- **`CLAUDE.md`'s machine-configuration table no longer claims
  documented-here-only enforcement for the shared-ledger tree variable**
  (OPS-2013.03, OPS-2013.29). It names `tests/test_snap_skip_status.py`,
  which measures the vendored snapshot tool against a sandboxed copy in a
  child environment with the variable cleared: green that an unconfigured
  tree is really skipped and that `log` refuses one on stderr with a
  nonzero status, and, until the kit promotion landed later in this same
  cycle, a strict expected failure that `snapshot` exited 0 having taken
  nothing.

  THE PROMOTION LANDED, so all three arms are ordinary passing cases now:
  the 0.2.25 kit body was vendored on 2026-08-20, and vendoring it turned
  the three strict markers into XPASS in one run, which is what the
  strictness was for. **A BEHAVIOUR CHANGE TRAVELS WITH IT and it is not
  only a bug fix**: on a machine that has never set
  `COORD_SHARED_LEDGER_TREE`, the no-argument `snap.sh` now exits 1 every
  time, because a skipped tree reaches the aggregate status instead of
  being swallowed. Nothing in either repository reads that status, so
  nothing breaks; the alternative was a recovery tool reporting a snapshot
  of the shared incident ledger it had not taken. Set the variable, or
  call `snap.sh pyflightstream` by name. The same section now says
  to check the process ENVIRONMENT as well as `.claude/settings.local.json`
  before concluding the shared tree is unconfigured, because a user-scope
  export satisfies a bash script just as well and leaves that file with no
  row.

- The two Tier 3 WARNs on 26.123, both `CDo` and both on SMI cases, gain
  a committed triage (`reports/physics/TRI-26123-CDo_2026-08-18.md`).
  Eleven of the thirty-eight metrics moved, `CDo` is the only one that
  moved OUT of band, every `CDo` METRIC moved and all three moved down,
  and both exceedances sit below their fail bands. On the author's
  decision the references stay untouched and the warns stand. The 26.123
  side turns out to be REPRODUCED already, by two independent executions
  of 2026-08-17 that agree on all thirty-eight metrics, because
  `pyfs-qa drift` runs its own physics for each build; the rerun owed is
  26.122's alone, and is registered rather than implied.

- **A guard added the day before was vacuous, and its own predicate was
  satisfied by the defect.** The rule "a library refusal naming
  `--some-flag` must also name `some_flag`" derived the parameter by
  de-hyphenating the flag, and for any flag without an internal hyphen
  that string is a SUBSTRING OF THE FLAG: `"cases"` is in `"--cases"`.
  Of the three raise sites it walks it genuinely checked one, the site
  the same commit had just repaired. It now asks for the two shapes this
  package actually uses, `parameter (CLI: --flag)` and `parameter=`, and
  it is driven by fixtures as well as by the tree, so it has a red case
  that does not move when the source does.

- **The FR-02c rewording silently dropped a normative sentence from the
  published requirements index.** `gen_requirements_index.py` publishes a
  requirement's FIRST paragraph as its statement, and the rewrite opened
  a second paragraph above the shadowing rule. The statement is one
  paragraph again and the requirement text says why the break matters.

- Two requirement texts move, both on the author's ruling of 2026-08-18.
  FR-02c stops enumerating the builds that share a vendor name, an
  enumeration that had gone stale twice by construction and was removed
  from six other homes on 2026-08-17 for that reason. NREQ-05 stops
  saying it excludes NOTHING, which was true of the eight editions swept
  on 2026-08-08 and stopped being true when SRC-751 was registered
  documenting a command the database does not carry; the corrected
  wording separates an exclusion from a dated debt.

- One count was wrong in two places and right in two others. 369 database
  rows carry 26.123; 85 cite the probe report, 84 `verified` and one
  `broken`; and 368 carry the restated note, because `apply_compat`
  overwrites the note for a broken outcome instead of carrying it
  through. The restate script said 85 in its docstring and 84 in its
  code, twenty-six lines apart.

## [0.7.0] - 2026-08-11

**Eight builds, and every command every one of them documents.** A
FlightStream build is registered, 26.122, and every command any of the
eight registered editions documents now has an entry: `pyfs-manual
sweep` reports zero absent, which it has never done for more than the
newest four builds before.

READ THAT CLAIM AT THE LEVEL IT IS MEASURED AT, because the first
version of this paragraph did not. Zero absent is a statement about
ENTRY NAMES. Ten readings across four commands are deliberately
withheld, so `IMPORT_CAD` and `CAD_CREATE_IMPORT_CURVE_CCS` cannot be
emitted on three builds and `NEW_OFF_BODY_STREAMTUBE` and
`SET_SCENE_CONTOUR` cannot on two, even though those manuals document
them: each of those editions writes the command in a LAYOUT a version
row cannot express, and a row that ignored the difference would emit
the newer shape under the older edition's citation. The entries say so and
`PLN-20260810-1200` holds the schema decision. The sweep now reports
that second measure beside the first, so the gap is named by the tool
rather than by this sentence alone.

### API surface delta

New public names: `pyflightstream.utils.stale_citations`,
`pyflightstream.utils.StaleCitation`,
`pyflightstream.utils.unreachable_commands`,
`pyflightstream.utils.UnreachableCommand`, the three protocols
`pyflightstream.utils.RegistryLike`, `CommandEntryLike` and
`VersionRowLike`, `pyflightstream.utils.manual.citation_reach`, the
`pyflightstream.utils.manual.Reachability`, the `pyfs-manual
citations` subcommand, seven keyword arguments on
`pyflightstream.script.helpers.solver_settings`, one (`sonic_velocity`)
on `pyflightstream.script.helpers.atmosphere`, and the `source` field on
`pyflightstream.utils.Edition` with the matching `source:` key in the
edition manifest, which is what lets a citation be checked against the
document it names.

Behaviour changes a caller can see. `atmosphere` takes `sonic_velocity`
and reads its script's version to decide which five fluid properties
FLUID_PROPERTIES wants, so it serves the three pre-26.100 builds it had
stopped serving. Its `altitude_units` defaults to None instead of
`"METERS"`, so an omission can be told from an explicit pass: nothing
changes on the seven builds that take a units token, which still emit
METERS when nothing is given, but 25.000 takes no token and reads the
bare AIR_ALTITUDE value in FEET (SRC-749 p.286), so there the helper
REQUIRES `altitude_units='FEET'` and refuses silence. The same call is
metres on the other seven, a factor of 3.28, which is the one silence
worth refusing. `initialize_solver` refuses at entry on 25.000 rather
than dying inside the binder on a keyword the caller never typed: that
edition's grammar takes ten arguments and this helper's parameters do
not map onto it. The refusal for a command
with no evidence lists builds by reachability and marks inherited ones,
so it no longer hides the newest build; and `pyfs-manual sweep` reports
a second finding, and `--fail-if-absent` gates on the row-level measure
alone: a name with no entry is unreachable too, so one term covers both
and the other could not have been falsified by any test.

Incompatible changes: none for a released signature. Deprecations:
none.

### Added

- **FlightStream 26.122 is registered**, vendor build 8092026, the day
  after it was issued. It is the second hotfix of the 26.12 release and
  says so from evidence rather than from its index: the vendor sells it
  as 26.12, its executable is named for 26.12, its solver prints 26.1
  like the other two, and the three build numbers are one release six
  weeks apart. Its manual documents the largest scripting surface of the
  eight editions, 372 commands. Read its `operational` level with its
  evidence: it reaches that level entirely on records inherited from
  26.120, because no command has been probed on this build.
- **Ten commands the 26.122 edition is the first to document**, among
  them `ROTATE_SURFACE`, `SOLVER_TIME_AVERAGING`,
  `SET_NEW_UNSTEADY_SOLVER_ACTION`, `EXPORT_BL_VELOCITY_PROFILE` and
  `SET_ACTUATOR_WAKE_TYPE`. Two of the ten stand where a command this
  edition stops printing stood, and neither pair is a plain rename:
  `ROTATE_SURFACE` takes six arguments, five on the command line and the
  surface indices on the next, where `SURFACE_ROTATE` is a keyword block
  of eight, and the two options
  `SPLIT_VERTICES` and `ADAPTIVE_MESH` have no equivalent in the newer
  form. Both superseded commands carry a `removed` row for 26.122 naming
  its successor.
- **Sixteen commands only the pre-26.100 editions document**, which
  closes the last gap in coverage. Three are version stories rather than
  disappearances: `SET_SOLVER_MODEL` becomes an argument of
  `INITIALIZE_SOLVER` in the edition that drops it,
  `SOLVER_UNINITIALIZE` and `REMOVE_INITIALIZATION` are exactly
  complementary across the eight editions, and the `PHYSICS` block
  becomes the two standalone autodetection commands at 26.000. That last
  one explains a gap this repository had already measured and misread:
  the two 25 builds are not missing trailing-edge autodetection, they
  spell it as one block.
- **Nineteen per-version argument grammars** for the three pre-26.100
  editions, read page against page. `FLUID_PROPERTIES` takes a sonic
  velocity and no specific heat ratio on all three; `INITIALIZE_SOLVER`
  has a different argument list on each of them.
- **`pyfs-manual citations`**, which re-reads every version row's cited
  page against the edition it names and exits non-zero when one does not
  hold. It exists because ten citations were found pointing at a
  document that had moved underneath them, each at a real page of a real
  manual, and nothing re-checked a citation once written.
- **Seven solver-setup flags** on `solver_settings`, for the
  settings-family commands only the older editions document:
  `solver_model`, `valarezo_criterion`, `crossflow_separation_cp`,
  `wake_relaxation`, `wake_streamwise_agglomeration`,
  `adverse_gradient_boundary_layer` and `vortex_ring_normalization`.

### Changed

- **A per-version argument override now states only its difference.**
  Unstated fields are filled from the base argument of the same name, so
  changing one field no longer means restating every other field of
  every argument. That restating is how a second field changes by
  accident: writing this release's overrides lost a list separator and
  an entity citation, which is the same defect this repository already
  had a test for. Writing `cites: null` still clears an inherited value,
  since inheritance reads the raw file where an unstated field and one
  stated at its default are distinguishable.
- **A `removed` row's citation no longer counts as manual coverage.** An
  absence is read across a whole chapter, so one such note marked every
  page of an edition as cited and the published coverage section went
  from a page-by-page gap listing to "every page is cited".
- The steady-polar example's version-awareness section now shows the two
  refusals that differ, a command a build does not carry and a command
  it carries with a different argument list, replacing a claim about
  26.0 having no recorded evidence that stopped being true.

### Fixed

- Ten version rows citing pages of the 25.000 manual were five or six
  pages off, from the conversion of that edition being corrected after
  the rows were written.
- **Three builds could not emit a command their own manuals document.**
  `EXPORT_ALL_SURFACE_STREAMLINES` had no row for 25.000, 25.100 or
  26.000 while its two family siblings on the same manual pages did, and
  the coverage sweep reported zero absent throughout, because it
  compares entry names and an entry missing one edition's row reads as
  covered.
- **26.122 would have emitted two commands the build before it has a
  negative record for.** Inheritance runs from the base release rather
  than from the sibling hotfix, so a `removed`-on-a-run record and a
  `broken` record on 26.121 were both overturned by 26.120's
  `documented` one.
- The README's opening example promised a refusal it no longer made and
  printed nothing, and CI could not see it: an example whose only claim
  is that something is refused goes green the day the refusal stops
  firing. It asserts now, and CONTRIBUTING states the limit.
- A note on `SET_SOLVER_MODEL` said the successor takes the same four
  tokens. It takes six, of which one is shared.
- **`atmosphere` serves the three pre-26.100 builds again.** Those
  editions take a sonic velocity and no specific heat ratio on
  `FLUID_PROPERTIES`, so entering their grammar closed both doors on
  them at once: passing the five newer properties was refused by the
  binder for a keyword the edition does not have, and omitting one was
  refused by the helper, which quoted a page of a different edition.
  The helper reads its script's version now and takes a new
  `sonic_velocity` keyword. The 25 series is the series registered so
  published work can be reproduced, so the curated path has to serve it.

### What the review changed

Reviewer passes over four rounds read this work, and the entries above
are what survived them. The count is deliberately not given: it was
written three times in this release at two different numbers and no
scope, and an unanchored count is worse than none. Four findings are
worth a reader's attention because they were wrong in ways nothing
mechanical could see.

The completeness claim was measured by a tool that cannot measure it.
`pyfs-manual sweep` compares entry NAMES, so an entry carrying no row
for one edition read as covered, and it reported zero absent while
three builds could not emit a command their own manuals document. The
sweep now reports both halves, and the completeness gate reads the
row-level one.

Four `removed` rows said the 26.122 edition does not print a command
while that edition's Script Index names it. The body does not, the
index does, and the body is what a script is written from, so the
conclusion stands and the citation did not. Each row states both
sources now. Measuring it inverted something worth knowing: the three
commands still emitted for that build are absent from the body AND the
index, while the four refused are absent from the body and present in
the index.

And two curated helpers stopped serving three builds the moment their
grammar was entered. `atmosphere` is fixed on both halves of its
signature; the second half was found only because a reviewer
parametrised over the builds instead of testing the one that changed.

The fourth is this release's own tag, and it is recorded here because
the fix ships inside the artifact. A tier 1 test imported the `[manual]`
extra with no guard, so the suite failed on the four platform legs and
on the coverage job, five of the run's eight checks, and the v0.7.0 tag
was pushed anyway, fifteen seconds after the branch, while seven of
eight jobs were still running. Nothing was published: `release.yml`
binds publishing to its gates and they held. Release process only; no
runtime change.

The account first written into the fixing commit was wrong, and the
correction is the useful part: the defect was NOT visible only in a
wheel environment, it was red in the ordinary matrix too, and the real
failure was a tag that did not wait for an answer CI was still
computing. The first red conclusion landed a minute and a half after the
tag, the last four minutes after it.

Both causes now carry a guard rather than a sentence:
`tests/test_extras_isolation.py` refuses an unguarded import of any
distribution a CI job may lack, `.claude/hooks/ci_release_gate.py`
refuses a version-tag push while that commit's CI is red, pending,
absent or unreachable, and a third guard, the `test-all-extras` CI leg,
installs all five declared extras so an assertion gated behind one is
executed somewhere rather than skipped everywhere
(INC-20260810-2140-shared).

One thing a reader comparing the tag to this section would otherwise
have to infer: the `v0.7.0` tag is MOVED onto the corrected commit
before publication. The first tag of that name published nothing, and
0.7.0 ships from this tree rather than from the commit that tag
originally pointed at.

### Known gaps

- **Three commands the 26.122 edition stops printing are still
  emitted for it.** That build inherits from its base release 26.120,
  and `CREATE_BULK_SEPARATION`, `SURFACE_DELETE` and `SURFACE_CLEARALL`
  have no record on the builds inheritance reaches past. Not that they
  have no successor and no measurement, which an earlier draft said and
  this repository's own files refute three times over: `DELETE_SURFACES`
  is recorded as replacing two of them and RPT-015 measured 26.121
  rejecting the third. The four that ARE refused
  are refused on stronger evidence, and the split is not a rule anyone
  chose: it is what the available evidence happens to look like. One
  probe run of seven names settles it (`PLN-20260810-1600`, and the
  licensed-evidence queue in `docs/srs/roadmap.md`).
- **Nothing has been probed on 26.122 at all.** It derives
  `operational` entirely on inherited records; the README row says so.
  The same is true of 25.000, 25.100 and 26.000, so four of the eight
  registered builds rest on manual evidence or on inheritance and no
  COMMAND has been measured on any of the four. Each has met a solver:
  an identity probe read its banner, which is where its build number
  comes from and is all it claims.
- **`initialize_solver` does not serve the three pre-26.100 builds.**
  Their INITIALIZE_SOLVER takes a different argument set, and this
  release fixes only `atmosphere`, the other helper the same gap hit.
  The refusal names the page and points at `script.emit`.

## [0.6.0] - 2026-08-09

**Seven builds, every one of them identified.** Three more FlightStream
builds are registered and every registered build now carries the vendor
build number its solver prints, read from a committed report. The three
that joined are the ones the author's published work was run on, so a
reader reproducing any of it has an identifier that resolves to a number
they can check against their own install.

Getting there meant finding out why three installs had looked broken.
They were not: the package was calling them with a command line they do
not accept, and a FlightStream build given a script argument it does not
recognise starts, checks out its licence, receives no script, and waits.
That reads as a hang with a clean licence and an empty log, which is why
two wrong diagnoses were written down before the right one. The fix is
one dash instead of two, measured across all seven builds.

The rest of the release follows from having seven readable builds. A
generated page maps what a solver prints onto the identifier to pass,
because a release name does not identify a build: the vendor ships two
builds as "26.1" and two more as "26.12". A new `pyfs-manual surface`
reports what each build documents and what changed between them, and
RPT-024 is its first output: the scripting surface grew from 272
commands to 364, unevenly, with 75 arriving in a single step.

### API surface delta

New public names: `pyflightstream.run.SCRIPT_ARGUMENT`,
`pyflightstream.run.describe_invocation`,
`pyflightstream.run.ExecutionResult.diagnosis`,
`pyflightstream.versions.FsVersion.prints`,
`pyflightstream.reference.markdown_build_table`,
`pyflightstream.utils.edition_surfaces`,
`pyflightstream.utils.surface_changes`,
`pyflightstream.utils.SurfaceChange`, and the `pyfs-manual surface`
subcommand. Incompatible changes: none for callers; the solver command
line changes, see below. Deprecations: none.

### Added

* **Three more FlightStream builds are registered, and every registered
  build now carries its vendor build number.** 25.000 (build 12162024,
  December 2024), 25.100 (build 5062025, May 2025) and 26.000 (build
  10202025, October 2025) join the registry at `registered` level. They
  are there for reproducibility rather than coverage: published work was
  run on the 25 series, and a reader of it needs the identifier to exist
  and to resolve to a build number they can check against their own
  install.

  Read their POSITION rather than assuming it. They precede every build
  the registry had, so they were inserted at the FRONT. The rule that
  versions are only added and never dropped is about dropping, not about
  the end of the list: the list is ordered by RELEASE order, so a build
  obtained later can belong earlier in it.

  The canonical scheme generalises from `26.XXX` to `YY.XXX` in the same
  change, which is what it always meant; the major was written as a
  literal while 26 was the only one registered. No identifier was
  reassigned. SRS FR-02a and BRF-19 carry the amendment.

* **`pyfs-manual surface` reports what each build documents and what
  changed between builds.** The sibling of `sweep`, off the same edition
  manifest: `sweep` asks what the database is missing, `surface` asks
  what each build documents so two builds can be compared. RPT-024 is
  its first output and is regenerated rather than maintained.

  The measurement, since it is the answer to "what changed between the
  builds I ran my research on": the scripting surface grew from 272
  commands to 364 across the seven builds, and 75 of that arrived in one
  step, 26.000 to 26.100, essentially the whole CAD and cross-section
  family at once. The step to watch is 26.100 to 26.101, which gained 35
  and lost 16 between two builds the vendor ships under the SAME release
  name.

  Lost means the newer manual stops printing the command, never that the
  solver stopped accepting it; those are different facts and only a
  probe separates them. The report says so rather than letting a reader
  infer a removal, and it lists names rather than only counts, because
  the counts cannot see that the four `CREATE_NEW_MOTION_*` commands of
  25.000 are one renamed `CREATE_NEW_MOTION` in 25.100 rather than four
  removals and one addition.

  The reading is cross-checked against the command database: for all
  four builds the database records, every command the manual documents
  has an entry, which is what makes the page ranges trustworthy.

* **A generated "Which build do I have" page.** The vendor ships two
  builds as "26.1" and two more as "26.12", so a paper recording
  "FlightStream 26.1" has not said which solver produced its numbers.
  The page maps the release name and build number a solver prints onto
  the canonical identifier to pass, and it is generated from the
  registry at docs build time so it cannot drift from it. It shows the
  two fields separately rather than the banner line, because that line
  is not byte-identical across builds: the 25.0 solver writes a NUL byte
  into it where the newer builds write a space.

  The registry gained a field for this and the reason is the sharper
  half of the release. `FsVersion.prints` records the release name the
  solver STATES ABOUT ITSELF, which is not the name the vendor sells the
  build under and may not be derived from it: 26.120 and 26.121 are sold
  as "26.12" and both binaries print "26.1". A first draft of the page
  keyed the column on the sold name, which would have sent the owner of
  either build to a row naming a different solver. It is recorded from a
  committed report's `solver_identity`, like the build number, and a
  tier 1 guard cross-checks it against the banners in those reports.

* **`pyfs-qa probe --identity-only`.** Judges no command: it runs the
  baseline, captures the solver's identity banner, and writes the report
  pair. That is how a newly registered build gets its build number into
  a committed report, which is the only place the registry accepts one
  from. Registering the three new builds is what it was built for, and
  it reads a build in about a second.

* **The probe baseline can run on a build that records no command.**
  Such a build has no grammar of its own for the three instruments, so
  the baseline borrows it from the newest build that records all three
  and reports the build unusable if the borrowed grammar does not work
  there. Without this the three builds registered in this release could
  not be probed at all, since a baseline needed a row and a row needed a
  probe. What the report does not yet say is that the borrowing
  happened, which is registered as PLN-20260809-2410.

### Fixed

* **The solver command line was version dependent and hardcoded as if it
  were not, which made three builds look broken.** The executor passed
  the script argument with two dashes, the spelling SRC-003 documents.
  The 25 series does not recognise it: the 25.0 manual documents the
  one-dash form. `pyflightstream.run.SCRIPT_ARGUMENT` is now the
  one-dash form, which RPT-023 measured working on all seven registered
  builds.

  The failure mode is the part worth publishing. A build given the
  spelling it does not know does not refuse it. It starts, prints its
  banner, checks out its licence successfully, receives no script, and
  waits for a user. Under `-hidden` with the standard streams redirected
  there is no console for it to report on, so the Fortran runtime raises
  `severe (30)` on `CONOUT$` and opens a modal dialog that no timeout can
  answer. What the harness sees is a clean licence checkout, an empty
  log, and a wall-clock time equal to its own timeout. Two diagnoses
  were written down before the right one, one of them naming a licence
  seat that was never held.

* **Every report derives its executor line instead of restating it.**
  That sentence sat as six literals across the three report writers, one
  machine-readable and one rendered each, and nothing would have noticed
  them disagreeing with the code: changing the argument would have left
  forty reports describing an invocation the package no longer made. It
  comes from `describe_invocation()` now, and a tier 1 guard compares
  the flags in the sentence with the flags the executor passes, as whole
  tokens. The first version of that guard asked whether each flag
  appeared in the sentence and a wrong sentence satisfied it, because
  `-script` is a substring of `--script`.

* **A failed solver run now says what the solver said.** Four sites
  composed `log_text or stderr or return code` by hand and all four
  omitted the same field: standard output, which the executor captures
  on every run and which nothing in the package read. A fifth, the
  timeout branch, discarded even those and recorded only "timed out and
  was killed".

  That is what made this release's own defect cost a day. Everything the
  harness reads is written by the solver AFTER it accepts a script, so
  every failure BEFORE that point looks identical; the baseline refusal
  told the operator the environment was unusable and offered the licence
  checkout as one of three candidate causes, while holding unprinted the
  line saying the checkout had succeeded. About a dozen licensed solver
  launches went into the licence hypothesis.

  `ExecutionResult.diagnosis()` is now the single composer, reporting
  the outcome and every non-empty channel, and the refusal quotes it
  instead of naming suspects it cannot rank. A tier 1 AST guard refuses
  any module outside the composer's home that reads two or more captured
  channels in one expression, which guards the shape rather than the
  five sites (INC-20260809-2230).

* **A stale editable install no longer stamps the wrong version into
  evidence.** Every compat, drift and physics report records
  `package_version` from the installed metadata, which for an editable
  install is whatever was recorded the last time the project was
  installed rather than what the source says today. That gap put
  `package_version: 0.5.0` into seven identity reports produced by the
  0.6.0 tree, one of them for a build the published 0.5.0 could not have
  driven at all. The reports were not rewritten, the writer refusing to
  overwrite evidence and rightly so; a tier 1 guard now fails when the
  installed metadata disagrees with the source tree, before a licensed
  run is spent, and names the one-line remedy.

* **The compatibility matrix and the offline `help()` page define their own
  cells.** Both carried a definition of the empty cell and of the
  inheritance mark and left the four status words to be inferred from
  their names. A legend now names all five, what each rests on, and what
  `Script.emit` does with it, which is the half no status name carries:
  three of the five are REFUSALS, each with a different exception class.
  Both layers render one tuple, so they cannot come to disagree, and the
  per-chapter reference pages stop restating the definitions and link to
  it instead.

  The reasoning worth keeping is about the guard rather than the text.
  The first version of it let eight of nine mutants through: every check
  was a search for a fragment ANYWHERE on the page, so the two columns
  could be swapped between `documented` and `verified`, the named
  exception class could be the wrong one, and the two non-refusing rows
  were proven by an `except Exception` that read an argument refusal as
  a successful emission. An emitter that could emit nothing at all left
  the file green. The guards now locate a row and assert inside it, tie
  each cell's opening clause to whether the model refuses that status
  without a committed report, and prove emission by emitting. Eleven of
  thirteen mutants die; the two that live are inversions of explanatory
  prose and are registered rather than papered over.

## [0.5.0] - 2026-08-09

**The command database is complete.** Every command that any of the four
registered FlightStream manual editions documents is in it, 388 entries,
and every entry carries a version row for each edition that documents the
command. Before this release the database held 147 commands and answered
for a curated subset of the solver; it answers for the whole scripting
surface now, and all four registered builds derive the `operational`
support level, which is checked by building a minimal end-to-end workflow
for each of them.

The rest of the release follows from that. Reading the command pages of
four editions found the ways a manual contradicts itself, and each
one is recorded on the entry it affects rather than smoothed over: a
sample copied from the neighbouring command, a heading and a table
disagreeing about an argument count, one command documented on two pages
where only one says anything, and a value set that gained a token between
builds. Where a page could not settle a question, the solver was asked on
a licensed machine and the answer is a committed report.

### API surface delta

* **Eighteen commands verified through the saved-state instrument, and
  four reverted to unobservable WITH their measurement.** 26.121 goes
  from 66 verified to 84: the full run of the same day recorded 66
  (`CMP-26121_2026-08-08_full`) and the saved-state run added 18
  (`CMP-26121_2026-08-08_savedstate2`). New public assertion `qa.fsm_changed`
  (`RPT-022`), for the
  commands whose effect is real and has no distinctive value to search
  for: a toggle writes T or F and a binding writes an index of 1, which
  match everywhere, so what it asserts is that the saved state MOVED.

  The four that came back broken were triaged rather than recorded, and
  none of them is broken: an actuator appears to be enabled at creation,
  the constant free-stream form is the documented solver default, every
  boundary appears pre-selected for analysis, and a clean synthetic wing
  has no wake termination nodes to detect. Each keeps an unobservable
  record whose note is now a measurement instead of a guess.

  BOTH SAVED-STATE ASSERTIONS COMPARED SETS OF LINES AND BOTH WERE WRONG
  FOR IT. The simulation file is positional and most of its lines are
  short tokens, so a line that genuinely changed from `0` to `1`
  contributes nothing to a set difference. Two commands that had really
  written to the state were recorded broken under that reading. They
  read a positional diff now.

* **Four chapter questions measured, and one was a command the emitter
  was building and the solver rejects** (`RPT-021`).

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` IS REMOVED ON 26.121. It is
  documented by the 26.101 and 26.120 editions and by neither
  neighbour; with no 26.121 row the registry handed it 26.120's
  evidence by hotfix inheritance, so a caller on that build got a
  validated script the solver refuses with an unrecognised command. The
  row is `removed` now, promoted from the run rather than read off the
  hotfix edition's silence, and a caller on 26.121 gets a refusal naming
  the build instead of a line the solver rejects. Second measured
  counter-example to that inheritance after `AIR_ALTITUDE`, and the
  first where the inherited evidence was optimistic.

  That row also needed a citation kind the database did not have.
  `ProbeOutcome` has no `removed` member, so the harness records a build
  that lacks a command as `broken`, which claims something else, and the
  guard that checks a status against its own compat yaml therefore had
  nothing to open. `VersionStatus` gains `probe_ref`, a committed
  narrative report of a run, admissible for `removed` and REFUSED for
  every other status: `verified` and `broken` stay checkable against
  harness output, because a guard whose population quietly shrinks
  reports green either way.
  `PLN-20260809-0300-the-harness-has-no-removed-outcome` carries the
  harness change that retires the field.

  `CREATE_NEW_BASE_REGION` GAINS `CUSTOM`: the solver accepts either
  that or `USER` there, while `SET_BASE_REGION_CP` accepts `CUSTOM`
  alone. The two pages disagreed and both are right about their own
  command; the manual is merely incomplete about the creator.

  DELETING A COORDINATE SYSTEM RENUMBERS the ones above it, so a frame
  index recorded before a delete means something else after it. Nothing
  in the library emits that delete and the entry states the safe
  pattern; what to do in `EntityRegistry` is a design decision left
  registered (`PLN-20260808-2100`).

  Two judgements this sweep took on reasoning were confirmed by
  measurement: `SURFACE_ROTATE` takes the sample's `SURFACES` and
  refuses the table's `SURFACE`, and `CAD_CREATE_MIRROR_CURVE`, the
  sample's spelling, is not a command.

* **26.100 IS OPERATIONAL, and it was the DATABASE holding it back, not
  the solver.** A per-edition sweep found 122 pairs of (command, manual
  edition) that an edition documents and this database had no version
  row for, so the emitter refused a command the caller's own manual
  prints and nothing distinguished that from the command not existing.
  Forty of them were on the February build, which is why its minimal
  end-to-end workflow could not be built. All four registered builds now
  derive `operational`.

  WHAT 122 COUNTS, since a reader comparing it against the diff will
  otherwise reach for the wrong number: pairs, not commands. One command
  documented by three editions and carrying a row for none of them is
  three pairs, and the backfill wrote 124 version rows, the two over
  being the per-version grammars written the same day. The count of
  distinct COMMANDS touched is smaller than 122 and is not the figure
  this stanza is about.

  EVERY PAIR WAS READ ON ITS PAGE, and four of the 122 turned out to
  differ, each now carrying its own per-version grammar rather than a
  copied row:

  - `NEW_SURFACE_SECTION_DISTRIBUTION` on 26.100 and 26.101 takes six
    keywords, not seven. The optional `INCLUDE_SYMMETRY` reached this
    database from a PROBE of a working 26.120 script and is first
    documented in 26.121, so a copied row would have offered older
    builds a keyword no evidence places in them.
  - `SET_TRAILING_EDGE_TYPE` on 26.100 closes its type set at three
    tokens; `VORTEX_SHEDDING` first appears in the May edition.
  - `SOLVER_PROXIMAL_BOUNDARIES` on 26.121 documents a second call form
    the older editions do not print, a count of -1 selecting every
    boundary and taking no index lines, so that row declares the
    sentinel and makes the list optional.
  - `NEW_CCS_WING_CONTROL_SURFACE` on 26.100 and 26.101 takes eight
    arguments and not ten: `SPACE` and `AXIS` arrive with 26.120, so
    spanwise placement is parametric only on the older builds.

* **The saved simulation is an instrument, and forty commands stop being
  unobservable** (`RPT-020`, `RPT-022`). The compat reports called their effects
  "stored in binary form"; the .fsm is sectioned TEXT and carries them.
  `ProbeSpec.save_state` brackets the target with SAVEAS and the new
  `qa.fsm_gained` asserts a distinctive value appears on a line the
  target added or changed. Eighteen commands verified on 26.121 with it across the two saved-state
  runs, eight of them through `fsm_gained`,
  among them the actuator axis, radius, rpm and swirl, and the frame
  origin and axes.

  It reads the DIFF rather than the whole file, because the first
  version did the latter and marked a working command BROKEN: the token
  it searched for also occurred somewhere innocent in the before-state.

  THE SOLVER NORMALISES A COORDINATE-SYSTEM AXIS WHATEVER THE FLAG SAYS.
  Found because the instrument reported `SET_COORDINATE_SYSTEM_AXIS`
  broken and the diff disagreed: a direction passed with the normalise
  flag FALSE is stored divided by its magnitude, to all seventeen
  digits. A direction cannot carry a scale.

* **MEASURED: a keyword block is read by NAME, not by position**
  (`RPT-019`, closing `PLN-20260808-2200`). Every `keyword_block` entry
  in the database fixes an order and nothing had ever asked whether the
  solver reads it. On the 26.121 build, the same five `FLUID_PROPERTIES`
  keyword lines in documented, transposed and fully REVERSED order leave
  the identical solver state, which a positional reader could not do.

  So the order an entry fixes is cosmetic, the
  `STABILITY_TOOLBOX_NEW_COEFFICIENT` table-versus-sample disagreement
  has no consequence, and the database-wide audit that a positional
  answer would have forced is not owed. The residual is in the report:
  one command, one build, and a parser being uniform over its own
  grammar is an inference.

  A GRAMMAR FACT FELL OUT OF BREAKING IT. A keyword block is terminated
  by a BLANK LINE; without one the solver reads the next command as a
  keyword line, and the error names that following command rather than
  the block. The emitter has always written the separator, which is why
  no script this library builds had ever hit it and why nothing asserted
  it. A tier-1 guard does now, proven by removing the separator.

* **The emitter has ONE way to know what an index cites, where it had
  two** (`PLN-20260807-1410`, the author's decision of 2026-08-08). An
  argument declares `cites` on its own entry, and the two global maps
  from argument NAME to entity kind are gone.

  They were already the fallback rather than the rule, and a fallback
  quietly covering 101 arguments is not a fallback. A name is a guess
  about an argument; a declaration is the argument saying so, which is
  why the maps could not carry `index`, a spelling that means a surface
  in one chapter and a section in three others. All 101 now declare it,
  including three that declare it on a per-version grammar rather than
  the default one.

  The visible gain is in the database rather than in the code: reading
  an entry now tells you whether its index is resolved and range
  checked, where before you had to know the map. The tier-1 closure
  guard lost one of its three ways to be satisfied, found the three
  per-version sites the bulk pass had missed, and was re-proven by
  mutation.

* **What the five reviewer passes changed, because two of it is
  user-visible.** `read_editions` is renamed `read_edition_manifest`
  before anyone depends on it, `Edition` is keyword-only (its two page
  ranges are the same type, so positionally they are interchangeable and
  a swap reads the Script Index as the scripting reference with nothing
  able to detect it), `sweep_editions` takes `recorded` by keyword and a
  `reader` for its one pdf dependency, and the manifest refuses an
  unknown key, a missing manual and a bad row before any manual is
  opened.

  THE SNAPSHOT NOW REPORTS THREE MORE SOLVER DEFAULTS.
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation` and
  `jet_wake_decay_normalized_length` had their manual defaults written in
  prose; they are `default` and `default_ref` fields now, so a caller who
  leaves them unset gets the documented value and its page in
  `SolverSetup` rather than an `unknown`. A default the database records
  is a default the snapshot reports.

  `ArgSpec.on_command_line` gained a third refusal: an OPTIONAL argument
  cannot sit on the command line, where arguments are positional and
  unnamed, because omitting it would shift the ones after it into its
  place and the solver would read the line without complaint. Both
  current users are required, so the gap was latent, and it is the same
  failure class the field was added to prevent.

**INCOMPATIBLE CHANGES, first because they are what an upgrade can
break.** Five, all of them from earlier in this development cycle and
each explained in its own stanza below.

* `resolve("26.1")` RAISES `AmbiguousVersionAliasError` where it
  returned 26.100. The vendor shipped two releases under that one name,
  so the alias no longer identifies a build; pass a canonical
  identifier, `"26.100"` or `"26.101"`, and the refusal names both.
* `FsVersion(...)` refuses construction at a hotfix index, one whose
  last digit is not zero, unless the call states `inherits_base`.
  Whether a build carries its base release's command evidence is a fact
  about two vendor builds, and defaulting it let a hand-built version
  inherit a whole command set by omission. Registered builds are
  unaffected: `resolve` fills the field from the registry.
* `SWEEPER_SET_VELOCITY_SWEEP`'s file path moved from the second
  positional argument to the third. Pass it as `filename=`.
* `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` rather than a `SET` with a count
  of zero and an empty payload line, which the solver misread.
* A database entry with an inline list argument may no longer declare a
  separator other than `space`, and an `on_command_line` argument may no
  longer be optional or be preceded by a keyword line; the load refuses
  each. Both reach an entry author rather than a caller, and no shipped
  entry breaks.
* `Script.emit` refuses a payload count with no payload under it, on any
  command whose list argument is optional, unless the count is the
  documented all-entities `-1`. One grammar in the database allowed the
  refused shape (`SOLVER_PROXIMAL_BOUNDARIES` on 26.121) and it rendered
  a count line the solver would have followed by reading the NEXT
  commands as its data.

**Deprecations: none.**

**ONE THING THE v0.4.0 NOTES PROMISED FOR THIS RELEASE AND THIS RELEASE
DOES NOT DO.** Those notes announced the dry-run rename, breaking and
with no alias: `plan_matrix` to `dryrun_matrix`, `plan_campaign` to
`dryrun_campaign`, and `pyfs-matrix plan` to `pyfs-matrix dryrun`. It
has not landed. Nothing in the deprecation ledger held it, so no guard
noticed, and it surfaced in this release's own documentation review.

Said plainly rather than quietly carried forward, because an announced
break that does not arrive is a promise a reader planned around. The
three names are unchanged and keep working. The rename moves to the
next minor and is registered as `PLN-20260809-0200` with the ledger
entry it should have had.

**The public surface ADDED, in one place.** A new console script,
`pyfs-manual`, with the subcommands `coverage`, `draft` and `sweep`,
behind a new optional extra `[manual]` (pypdf). A new subpackage,
`pyflightstream.utils`, exporting `Edition`, `SweptCommand`,
`sweep_editions`, `read_edition_manifest`, `Coverage`, `ManualCommand`,
`ManualDraftError`, `TypeRule`, `TYPE_RULES`, `coverage_against`,
`parse_script_index`, `parse_signatures`, `propose_layout`,
`propose_type`, `read_pdf_pages`, `render_chapter`, `render_entry`,
`sample_contradiction` and `write_chapter`.

`helpers.solver_settings` gains TEN keyword parameters
(`kutta_joukowski_lift`, `print_rotor_induced_velocities`,
`adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
`rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
`jet_wake_decay_normalized_length`, `wake_decay_constant`,
`solver_stabilization`, `disable_ref_velocity`). `ArgSpec` gains the
fields `on_command_line`, `cites`, `all_sentinel` and `fixed_length`.
The database gains two evidence citations: `probe_ref` on an ENTRY, for
a command the solver accepts and no edition documents, and `probe_ref`
on a VERSION ROW, for a measured removal, admissible there for `removed`
alone. `qa` gains `fsm_gained`, `fsm_changed` and
`ProbeSpec.save_state`. `script.solver_setup` gains the four separation
models `AirfoilSeparation`, `AxialVortexSeparation`,
`CylindricalBulkSeparation` and `StratfordBulkSeparation`. The version
registry gains `inherits_base` and the registered version 26.101.

The stanzas below give the reasoning per chapter.

* **The tail entered: 28 commands across 21 sections, and THE SWEEP
  REACHES ZERO.** Every command that any of the four registered manual
  editions documents is now in the database: 388 entries, of which 387
  cite a manual page and one rests on a committed probe report
  (`DELETE_VALAREZO_SEPARATION_BOUNDARIES`, which the solver accepts and
  no edition names). Emittable per version at this release: 345 on
  26.100, 363 on 26.101, 363 on 26.120, 368 on 26.121.

  MEASURED ON 2026-08-08 against the four editions of the maintainer's
  own manifest: `pyfs-manual sweep` reports 0 absent. State it as a
  measurement of that date rather than as a property CI holds, because
  the manifest names licensed manual paths and cannot be committed, so
  no test in this repository can re-run it. What CI does hold is that
  every entry carries exactly one evidence citation. The sweep also now
  takes `--fail-if-absent` for a maintainer who wants the check to fail
  rather than to report.

  **Two more keyword parameters on `helpers.solver_settings`:**
  `solver_stabilization` and `disable_ref_velocity`, the latter on a new
  `bare_request` flag kind for a command that takes no argument at all,
  where False is the ABSENCE of the request rather than a way to ask for
  the opposite.

  Three commands exist in one edition only, which is the clearest
  evidence this sweep produced that the scripting surface is moving in
  both directions: `DISABLE_ACTUATOR` and `EXECUTE_SOLVER_SWEEPER` in
  the February edition alone, `DISABLE_SOLVER_REF_VELOCITY` in the
  26.121 hotfix alone. `EXECUTE_SOLVER_SWEEPER` does in one 21-parameter
  command what the later `SWEEPER_` family splits across ten, so that
  family was redesigned rather than extended.

  `CAD_CREATE_MIRROR_CURVES` HAS TWO SPELLINGS: the heading and the
  Script Index say CURVES and the sample beneath the heading says
  CURVE, in all four editions. The heading is recorded, and the
  reasoning is the reverse of this database's usual preference for
  samples: a sample is the stronger source for an ARGUMENT because the
  vendor ran the line, but a sample with the wrong NAME is a sample of
  nothing. `PLN-20260808-2300` carries the probe.

  Two chapters are worth naming for what they lack. Boundary Layer
  Transition Trips is ONE COMMAND AND IT IS A DELETE: no edition
  documents creating a trip, so a script can remove them and never add
  one. And `SET_PLOT_TYPE` prints `RESIDUALS` twice in its value list in
  every edition, so it takes 23 tokens rather than the 24 rows printed.

* **Coordinate Systems, both streamline families and the Stability and
  Control Toolbox entered: 19 commands, all four chapters complete.**
  Database 341 to 360; emittable per version 280, 307, 340, 345. Nine
  older entries across the frames and streamlines chapters get their
  missing edition rows in the same pass, the streamlines header having
  deferred the whole on-body family to the cases that would exercise it.

  `NORMALIZE_COORDINATE_SYSTEM` takes the index its sample passes,
  against a heading with no placeholder and a table reading N/A: the
  same shape as the February edition's `ENABLE_ACTUATOR` and read the
  same way. It is also the one command in its chapter that accepts frame
  1, every other requiring an index above the reference frame.

  `MIRROR_COORDINATE_SYSTEM` DUPLICATES AND THEN MIRRORS, which the
  manual states in a parameter row rather than in the command's
  description. Reading the name alone suggests the frame is mirrored in
  place, which is a different result for everything already pointing at
  it.

  `STABILITY_TOOLBOX_NEW_COEFFICIENT`'s keyword order follows its two
  printed samples, which agree with each other and not with the
  parameter table above them. That raised a question no chapter had
  asked: every keyword_block in the database fixes an order and nothing
  has tested whether the solver reads order at all
  (`PLN-20260808-2200`). `STABILITY_TOOLBOX_SETTINGS` carries a unit
  trap worth naming: its `UNITS` argument selects per-radian or
  per-degree OUTPUT, while `ANGULAR_RATE_INCREMENT` is an input the
  manual gives in rad/s regardless, so reading one as governing the
  other is a factor of about 57 in every dynamic derivative.

  Two further probes registered: what a deleted coordinate system does
  to the indices above it, which matters here because the builder TRACKS
  frames and would be wrong if the solver renumbers
  (`PLN-20260808-2100`).

* **The Advanced Settings and Inlets and Outlets chapters entered: 15
  commands, both complete.** Database 326 to 341; emittable per version
  253, 280, 321, 326.

  **Eight new keyword parameters on `helpers.solver_settings`:**
  `kutta_joukowski_lift`, `print_rotor_induced_velocities`,
  `adaptive_field_grid_refinement`, `jet_wake_filaments_grid_induction`,
  `rotor_induced_velocity_blending`, `wake_numerical_relaxation`,
  `jet_wake_decay_normalized_length` and `wake_decay_constant`, each with
  a snapshot flag. Not optional extra work: every command of a settings
  family is a snapshot flag, and the tier-1 guard refused the chapter
  until the model matched, so these arrived with the commands instead of
  a release later.

  ADVANCED SETTINGS IS THE CHAPTER WHERE THE EDITIONS DISAGREE ABOUT
  WHAT EXISTS, so its version rows differ per command. Four commands are
  absent from the February edition. `SET_WAKE_DECAY_CONSTANT` exists in
  the 26.121 hotfix alone, so it cites SRC-740 rather than the flagship,
  and its unit of 1/m is DERIVED from the manual's formula and printed
  nowhere: the constant is 19.1 over a characteristic length in metres,
  and a value computed with that length in other units gives a wake
  decaying orders of magnitude too fast or not at all, with nothing in
  the number to reveal which.

  `SET_JET_WAKE_FILAMENTS_GRID_INDUCTION` is documented by 26.101 and
  26.120 and dropped by the hotfix that follows, the only such command
  in the sweep. It entered with no 26.121 row and deliberately not a
  `removed` status, since a document going quiet is not a statement
  about a solver, and so it emitted on that build by inheritance from
  its base release. `PLN-20260808-2000` carried the probe that settled
  it, and the probe ran later the same day: the build does not have the
  command. What the row says now, and why a measured removal cites its
  run differently from a read one, is under the chapter-questions entry
  above.

  Inlets and Outlets is asymmetric and the asymmetry is the manual's: an
  inlet takes a custom velocity profile from a file and an outlet cannot,
  in any edition, so a case needing a non-uniform exhaust has no scripted
  way to ask for one. A test asserts the absence, the natural reading of
  a symmetric chapter being that the missing command was overlooked.

* **The Acoustics Toolbox and Base Regions chapters entered: 18
  commands, both complete.** Database 308 to 326; emittable per version
  243, 266, 307, 311.

  `ACOUSTIC_SOURCES` is a SETUP command in a post-processing toolbox,
  because the manual states it must be enabled before solver
  initialization; enabling it afterwards costs a whole unsteady run and
  produces no sources. `CREATE_ACOUSTIC_SECTION` creates and exports in
  one call, which is why its path names a folder: one VTK file per
  observer per time step, a count no edition warns about.

  `SET_BASE_REGION_BENDING_ANGLE` IS DOCUMENTED ON TWO PAGES AND ONLY
  ONE SAYS ANYTHING. The Base Regions chapter prints its heading with
  nothing beneath it; p.284 gives it a table, a range and a sample
  passing a value. Recorded from p.284. An empty heading is read as a
  bare command only where nothing in the manual argues with it, which is
  the rule the Scenes chapter rests on, and here the same manual argues
  with it 33 pages earlier.

  THE USER-SPECIFIED PRESSURE MODEL IS SPELLED TWO WAYS TWO COMMANDS
  APART: `USER` on `CREATE_NEW_BASE_REGION` and `CUSTOM` on
  `SET_BASE_REGION_CP`, in all four editions, both described as the
  model under which the caller's CP applies. Each entry records its own
  page and refuses the other's, because a keyword is emitted literally
  and accepting both would rest on a guess that one of the two pages is
  wrong. `PLN-20260808-1900` carries the probe.

  `SET_BASE_REGION_CP`'s CP is optional and its own page PROVES it, by
  printing a second sample that passes only the model. Its sibling makes
  the same claim about the empirical model in prose and prints no short
  sample, so there the argument stays required: a sample settling an
  arity question rather than contradicting one is rare enough in this
  manual to act on. And `REMESH_BASE_REGION` spells its growth scheme
  numerically, 1 and 2, where the three CCS chapters spell the same two
  schemes as words.

* **The Mesh Wrapper chapter entered: 11 commands, and NREQ-05 now
  excludes nothing.** The author's decision of 2026-08-08. This was the
  last family the scope excluded, so the non-requirement is narrowed to
  an empty set rather than retired, the two narrowings together being
  the record of a scope decision reversing itself. Database 297 to 308;
  emittable per version 225, 248, 289, 293.

  The wrapper builds one clean watertight surface over a set of input
  surfaces, which is what a dirty import needs before a panel method can
  run on it; `WRAPPER_EXECUTE` performs it and everything else
  configures it.

  **New public field: `ArgSpec.on_command_line`.** A keyword_block whose
  LEADING arguments sit on the command's own line, which the emitter
  could not express and which `WRAPPER_EDIT_LOCAL_CONTROL` needs. The
  attempt to spell it with `joins_previous` was refused by the schema,
  correctly: that flag appends to the line the PRECEDING ARGUMENT wrote,
  and in first position there is none. Two new refusals hold the shape,
  a list cannot take it and it must lead. An excluded family hiding a
  missing emitter capability is itself an argument against excluding
  families.

  `num_surfaces` is the FOURTH spelling in the database for a count of
  surfaces, after `surface_count`, `surfaces` and `boundaries`. All four
  are the manual's own on their own pages and the entries go on
  mirroring them; the tier-1 guard over the count-name set is what
  reported this one, before the entry could ship a count nothing
  compares against its list.

* **The Scenes and Scene Settings chapters entered: 18 commands, both
  complete.** Scenes had held ONE command, `CHANGE_SCENE_TO_PLOTS`,
  drafted under a rule that only entered commands with observed
  scripted use; that rule is gone with this sweep and the entry's three
  missing edition rows are backfilled in the same pass. Database 279 to
  297; emittable per version 214, 237, 278, 282, the 26.100 and 26.101
  figures gaining nineteen rather than eighteen because the backfill
  closes one older entry as well.

  Twelve of the thirteen Scenes commands take nothing at all, eleven of
  them printed as a signature heading with no table, no sample and no
  prose. That is the manual stating the command takes nothing, and it is
  read as such here because no edition contradicts it anywhere, which is
  precisely what distinguishes it from the February edition's
  `DISABLE_ACTUATOR`, where the same empty shape sits beside a sample
  passing an index.

  Scene Settings is six keyword blocks over the colour scale, every one
  selecting its target with the same first keyword. `CUT_OFF_MODE`'s
  `OFF` is quoted in the database because YAML 1.1 reads the bare word
  as the boolean false; the schema refuses a non-string enum value, so
  the mistake is loud, and a test now pins the token.
  `SET_SCENE_COLORMAP_CUSTOM_RANGE` HAS NO SAMPLE OF ITS OWN IN ANY
  EDITION: all four print one whose first line names the neighbouring
  command while its keyword lines are this one's, so the sample is not a
  runnable call of either.

* **The CCS Fuselage Mesh and CCS Body of Revolution Mesh chapters
  entered: 20 commands, both chapters complete.** The two remaining
  parametric component definitions beside the wing, each with its own
  grid controls (subdivisions, growth scheme and rate, periodicity, and
  the per-direction reset), axial refinement zones, relaxed
  trailing-edge boundaries, and the export that writes the lofted
  component to a file. Entered from all four editions in one pass, every
  signature identical across them. Database 259 to 279; emittable per
  version 195, 218, 260, 264.

  THE TWO COMPONENTS DO NOT SHARE A SECOND DIRECTION. A fuselage is
  AXIAL and RADIAL, a body of revolution AXIAL and AZIMUTH, and the two
  chapters are otherwise line for line the same commands. That makes a
  value carried across from one to the other the easy mistake and an
  invisible one, since both words are plausible for a body of
  revolution, so the enums are stated per chapter and a test emits each
  one against the other's token.

  `EXPORT_FUSELAGE_CCS_FILE` and `EXPORT_REVOLVE_CCS_FILE` ARE RECORDED
  FROM THEIR HEADING AGAINST TWO SOURCES THAT SAY OTHERWISE. The heading
  prints six placeholders, the parameter table documents four, and the
  sample is the neighbouring create command's with the name swapped.
  The revolve page proves the copy: its sample passes a frame index, an
  axis and two angles that appear nowhere in the export's own signature.
  The wing sibling prints the same six and documents all six, so these
  tables are missing rows rather than describing a shorter command. The
  solver has not been asked, and `PLN-20260808-1730` carries the probe.

* **`pyfs-manual sweep`, and the four-edition worklist becomes a
  committed tool rather than a session's scratch script.** New public
  names in `pyflightstream.utils`: `Edition`, `SweptCommand`,
  `sweep_editions` and `read_edition_manifest`, the last renamed from
  `read_editions` before release. `coverage` answers what ONE
  manual documents and the database does not; no sweep asks that
  question. A command absent from one edition may be recorded from
  another, and a command the database lacks must be entered for every
  edition documenting it at once, so both halves need the union of the
  registered builds and neither is obtainable by reading four
  single-edition reports side by side.

  The editions come from a YAML manifest, `--editions`, which is not
  committed and cannot be: it names the paths of licensed manuals
  (invariant 1). Registering a new build is adding a row to it. `index`
  is optional, because it supplies the section label only and skipping
  an edition for want of one would silently drop a whole build from the
  union; a sweep of NO editions raises instead of reporting the entire
  database absent, which is a configuration error wearing the costume of
  a catastrophic finding. `--by-section` groups by the chapter that
  documents each command, largest first, which is the order the
  remaining work is done in.

* **The CCS Wing Mesh chapter entered: 11 commands, the chapter
  complete.** The parametric wing definition that a mesh is lofted from,
  so everything here configures a definition rather than acting on an
  existing mesh: the per-direction grid (subdivisions, growth scheme and
  rate, periodicity, and the reset), the spanwise refinement zones, the
  morphing control surface and the flap cove, and the export that writes
  a lofted wing to a file instead of into the simulation. Entered from
  all four editions in one pass under the rule below. Database 248 to
  259; per version 118, 166, 238, 242.

  `NEW_CCS_WING_FLAP_COVE` REACHED THE DATABASE ONLY BECAUSE A PAGE WAS
  READ. It carries a signature heading in every edition and no Script
  Index row at all, and the coverage sweep was index-driven, so it
  reported the command as covered and would have gone on doing so
  indefinitely. A false absent is visible the moment someone looks for
  the command; a false covered is invisible by construction. The sweep
  now walks chapter bodies (`PLN-20260808-1200`), and the two
  measurements agreeing on a total of 140 turned out to be a
  coincidence, the index-driven set carrying one false positive and
  missing one command.

  `COVE_TYPE` is an index and not a word, 1 for a blended Bezier cove
  and 2 for a rectangular one, among a family whose every other shape
  argument is a token. `U00` and `U01` are upper- and lower-surface slot
  locations, which is a different pairing from the `U0` and `U1` of the
  two control-surface commands on the same page. And the -1 that deletes
  every refinement zone or control surface is recorded in the notes
  rather than declared as `all_sentinel`: those objects belong to the
  parametric definition and not to the loaded geometry, so the builder
  tracks neither and there is no inventory for a sentinel to be read
  against.

* **The author's decisions of 2026-08-08 on what this sweep owes the
  older builds, and what it does not.** A chapter now enters for every
  registered version in one pass, which is written into the
  chapter-entry guidance in `docs/srs/data-model.md`. The entries still
  documented in an edition they carry no row for, counted in the
  2026-08-07 stanza below, drain as the sweep reaches their chapters
  rather than as a task of their own, so the number falls without a
  separate push. Named rather than left to be discovered, because until
  it reaches zero a caller on 26.100 or 26.101 still meets a refusal for
  a command their own manual describes.

  Applying that rule to this commit closed ten of them at once. The
  whole Aeroelastic Coupling Toolbox carried a 26.120 row alone while
  its 26.101 and 26.121 pages had just been read here, so the rule was
  broken by the commit that introduced it; the rows are written with
  their own pages (SRC-725 pp.374-375, SRC-740 pp.378-379), the
  grammars being identical across the three editions that carry the
  chapter. 26.101 goes 145 to 155.

  Not changed, each deliberately: argument names go on mirroring each
  manual page rather than being harmonised; the count spelled
  `surfaces` stays, being the house spelling on eight commands and not a
  slip in one; the positivity bounds the manual states on the spring
  force stay unenforced; and the emitter's two argument-name maps were
  to stay beside the `cites` declaration rather than be replaced by it.
  THAT LAST DECISION WAS REVERSED THREE DAYS LATER and the maps are
  gone, which is the stanza at the top of this release; the reasoning
  that kept them, recorded here as it was taken, is what the reversal
  had to answer.

  One decision could not be carried out as taken.
  `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS` was to have its lower bound
  enforced, and reading the page to do it showed the manual does not say
  WHICH value of 1 it forbids: the sentence sits on the count row and
  its gloss describes the reference index, the sample satisfies both
  readings, and the three editions that carry the chapter word it
  identically. Enforcing
  the wrong one would refuse a valid script, so nothing is enforced and
  `PLN-20260808-1100` carries the probe. The entry's note, which had
  stated one reading as fact, now states the ambiguity.

* **Fourth round, and the sweep itself verified clean.** An independent
  seat read all four editions page by page and confirmed the fifteen
  boundary indices: nine state an all-form, six state none, no edition
  disagrees with another. What the round found was around it.

  `Script.resolve_boundary(-1)` had started raising. It is a public
  method resolving a citation with no command attached, so the generic
  all-boundaries form is right there; it was passing through the
  per-kind default that the round before had deleted. The call site now
  states -1 explicitly, and the docstring says why that differs from
  `emit`, where six commands refuse it.

  `SURFACE_ROTATE`'s own all-form was unreachable. Its page states -1 in
  the COUNT row and the index line then has nothing to list, but the
  list was required, so the documented call was refused outright and an
  empty list emitted a stray blank line into the keyword block.

  Three of the nine declared sentinels were pinned only by a literal in
  the test inventory, which is not a guard: editing the declaration and
  the literal together left the suite green with the documented all-form
  refused. All nine are asserted behaviourally now. The
  undeclared-inventory branch was untested the same way, and every
  negative count, not only -1, was bypassing the count-versus-list
  check.

  Two claims corrected: the `all_sentinel` docstrings still taught the
  per-kind default in both homes, and the closure guard's docstring
  called the vocabulary closed when it is a heuristic over name stems,
  which a QA pass demonstrated by getting seventeen invented spellings
  past it. The stems were widened with all seventeen and the claim now
  matches what it measures. The goldens are compared for carriage
  returns directly, since `read_text` had been hiding exactly what the
  LF pin was added to prevent.

* **The same inversion, found a THIRD time, and now fixed at its root.**
  `-1` was still the all-boundaries default for every entity of that
  kind, so the six surface commands whose page states no all-form
  accepted it anyway: `SURFACE_RENAME` renamed all surfaces to one name,
  `SURFACE_MIRROR` mirrored them, and the refusal text OFFERED `-1` on
  pages that never mention it. The two earlier rounds each moved this
  rule somewhere better without asking whether the default itself was a
  claim, and it is one.

  There is no per-kind default now. Absent means the page states no
  all-form and every non-positive index is refused. SRC-003 pp.307 and
  309-313, SRC-741 p.305 and SRC-740 p.315 were read command by command:
  nine boundary indices state one and declare it, six state none and
  declare nothing. Both halves are asserted, so a rule that simply says
  yes or simply says no fails.

  The refusal wording moved with it. A command with no all-form says so
  rather than naming a value the solver was never told to accept, which
  is where the original defect did its damage.

* **The three declarations below, reviewed in turn, and the round found
  the repair less finished than it looked.** Three of its four new
  guards were untested, and the QA pass measured all three mutations
  surviving a green suite: deleting every `cites:` declaration, deleting
  the whole `fixed_length` refusal, and deleting the backfilled version
  rows. Each is now asserted as behaviour and each mutation is caught.

  `all_sentinel` was not self-sufficient. It reached the emitter only
  because a name map happened to resolve the spelling beside it, so
  renaming that map row would have made the sentinel inert and silent,
  which is the class of defect the field was added to end. It now
  requires `cites:`, and the database is refused at load without it.

  The list path still hardcoded `-1` for every entity kind, which is the
  per-family rule the change below removed from the scalar path and left
  standing next to it. A list of frames or motions has no documented
  all-form at all. Both paths now read the argument.

  The sentinel was also swallowed whenever no boundary inventory had
  been declared. An inventory bounds an index from above; being 1-based
  bounds it from below, and that half needs no inventory, so `-1` on a
  zero-sentinel command emitted silently on any script that had not
  called `declare_existing`.

  The precedence rule was written out four times, once per
  scalar-or-list branch in each of two paths; it is now
  `_reference_kind`, consulted by both.

* **A guard now closes the argument vocabulary, and it found five gaps
  the review did not.** An index argument whose name says it cites
  something must declare what it cites, be a spelling the emitter
  already resolves, be a count, or be listed as an index of an object
  the entity tracker does not model (CAD bodies, curves, sections,
  trailing edges). Running it first reported `DELETE_SURFACES`, both
  surface-section distributions, `ROTATE_COORDINATE_SYSTEM`'s second
  frame and the aeroelastic structural frame: all confirmed against the
  manual and now declared. The Mesh Operations chapter header states the
  rule, since mirroring the manual's own argument spellings is what
  makes the declaration necessary.

* **Three facts an argument used to only describe, it now declares, after
  the review of the four chapters above found each one wrong in the
  emitter.** `ArgSpec` gained `all_sentinel`, `cites` and `fixed_length`.

  The all-surfaces sentinel was fixed per ENTITY KIND at `-1`, and the
  two `TRANSLATE_SURFACE` commands document zero. So the emitter refused
  the documented `0` and accepted the meaningless `-1`, exactly
  inverted, and its refusal message steered the caller to `-1`. The
  notes said so in prose, and the test asserted the prose on the
  reasoning that "nothing can refuse it, since both are valid
  integers". That reasoning was the defect: the sentinel is a
  per-command fact, so the argument carries it.

  Which entity an index cites was inferred from the ARGUMENT NAME, and
  the Mesh Operations chapter mirrors each manual page's own spellings.
  Five of them reached neither map, so `SURFACE_DELETE` accepted a
  declared label and `SURFACE_INVERT` did not, and `SURFACE_COMBINE`'s
  index list and `TRANSLATE_SURFACE_BY_FRAME`'s two frames were range
  checked against nothing. The name map stayed at this point for a
  spelling that means one thing database-wide, and could not be extended
  to `index`, which is a surface here and a section or separation index
  in three other chapters. An argument that needs it now says what it
  cites, and the map itself was deleted later in this release.

  `SET_MOTION_6DOF_ACTIVE_VARIABLES` writes six toggle lines with no
  count before them, and a short payload made the solver read the next
  command as data. The length is declared and a short or long one is
  refused, naming the corruption rather than the arity.

  The count-spelling guard was blind in the same way and the QA pass
  proved it: renaming a real count to `surface` left the whole suite
  green while the emitter stopped comparing the count to its list. The
  exemption now reads the argument's declaration, not its name.

* **Corrected: `solver_settings(thin_boundaries="all")` was refused, and
  the refusal recommended a call that failed again.** `SET_THIN_BOUNDARIES
  -1` marks every mesh boundary thin and takes no index line; the helper
  rejected the bare label and suggested `["all"]`, which then failed as
  an unknown boundary label. The keyword now has three distinct states,
  documented together: absent leaves the solver's list alone, `"all"`
  emits the `-1` form, and the empty sequence erases.

* **Corrected: nine commands the manual documents in the February and
  May 2026 builds carried no row for them,** so the emitter refused them
  on builds whose manual describes them. Six in Motion Definitions
  (boundaries, moving frames, coordinate system, start time and the two
  rotor commands), the two FSI seam commands, and four in Solver
  Settings. This was a pre-existing gap rather than one the sweep
  introduced, and it is not the whole of it: **117 entries are still
  documented in an edition they carry no row for**, all of them 26.100
  and 26.101. Registered as `PLN-20260807-1400`; whether early-build
  parity is a v0.5.0 goal is the author's call.

  Database 248 entries, unchanged by this pass; per version 26.100 106,
  26.101 145, 26.120 227, 26.121 231. The figures previously recorded
  here for 26.120 and 26.121 were wrong before the gap was closed, not
  because of it.

* **Solver Settings is complete.** Three commands remained:
  `SET_SURFACE_ROUGHNESS`, whose height is in NANOMETRES and not the
  metres every other length in this helper takes, and the
  `SET_THIN_BOUNDARIES` and `DELETE_THIN_BOUNDARIES` pair, absent from
  the February 2026 build. Both reach `solver_settings()` as new
  keywords, which the snapshot guard required rather than suggested:
  every command of the settings families must carry a FlagSpec or the
  provenance record silently lags the database.

  A fourth name looks absent and is not. Every edition's Script Index
  spells `CREATE_STRATFORD_BULK_SEPARATION` as
  `CREATE_STARTFORD_BULK_SEPARATION`, and the command is recorded under
  the spelling its chapter body and sample use, which RPT-015 measured
  the solver accepting. A coverage sweep driven from the index will keep
  reporting the misspelling as a gap, and a test now says so.

* **Motion Definitions is complete: 17 commands entered.** The 6DOF
  family (mass and inertia, gravity, initial conditions, active
  variables, the external, custom and spring forces, the trajectory
  export), the custom motion table, and the five kinematic commands
  that exist in the February 2026 build alone. Database 228 to 245.

  THREE COORDINATE SYSTEMS APPEAR IN THAT CHAPTER and no argument name
  distinguishes them: `SET_MOTION_GRAVITY` reads the REFERENCE system,
  the 6DOF initial conditions and forces read the BODY frame, and the
  February kinematic family reads the MOTION DEFINITION system. A
  script setting gravity and an initial velocity writes two vectors
  into two different frames, and the notes are the only place that is
  said.

  `SET_MOTION_CUSTOM_TABLE` takes its TYPE before the motion id, the
  only command in the chapter that does not open with the id.
  `CREATE_NEW_6DOF_SPRING_FORCE` is the third of the five wrapped
  signatures and declares eleven arguments, three of them lengths that
  are not interchangeable. `SET_6DOF_MOTION_SYMMETRY_LOADS` prints a
  shorter name in its sample than in its heading; the heading is
  recorded, on the measured record that a heading has won every case a
  solver has settled. The chapter header, which said the 6DOF family was
  pending, now records the chapter complete and carries the
  three-coordinate-system warning; chapter headers render live in the
  overview, so the stale text was public.

* **Corrected: `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION` had one
  grammar and the manual has two.** The February 2026 edition takes two
  arguments and later editions three, the blade count arriving with the
  rotary motion, and the entry carried the three-argument form with a
  26.120 row alone. The February grammar was neither recorded nor
  reachable.

* **The Mesh Operations chapter entered: 22 commands, the whole chapter
  bar one already present.** Everything that moves, copies, cuts,
  selects or deletes a mesh surface between import and solver
  initialization. Database 206 to 228.

  Two things in that chapter are not uniform and both are recorded
  because nothing else would carry them. The all-surfaces sentinel is
  `-1` on most commands and **zero** on `TRANSLATE_SURFACE_IN_FRAME` and
  `TRANSLATE_SURFACE_BY_FRAME`, which the manual states per command and
  never contrasts, so a script reaching for `-1` out of habit translates
  surface `-1` rather than every surface. And `SURFACE_MIRROR`'s
  `MIRROR_PLANE` is an INDEX, 1 for YZ, 2 for XZ and 3 for XY, the only
  plane argument in the database that refuses the two-letter token every
  neighbouring command takes.

  Two version stories the manual tells by omission rather than
  statement. `SELECT_GEOMETRY_BY_ID` is the February spelling of
  `SURFACE_SELECT_BY_ID`, and each carries only the editions that
  document it, so emitting the wrong one for a build is refused.
  `SURFACE_DELETE` and `SURFACE_CLEARALL` are documented in three
  editions and replaced by `DELETE_SURFACES` in the fourth; neither is
  `removed`, because a removal here means a manual stating one. The
  emitter still accepts both for 26.121 through hotfix inheritance,
  which is per version and cannot be denied per command
  (PLN-20260807-1010), and a test pins that permissive behaviour so the
  fix cannot land quietly.

  `SURFACE_ROTATE`'s surface keyword is spelled `SURFACE` in its table
  and `SURFACES` in its sample. A keyword is emitted rather than
  matched, so unlike a value set this cannot accept both. Both spellings
  are printed, the table's and the sample's; the SAMPLE's is used,
  because the sample is the only runnable line on the page, and
  PLN-20260807-1000 carries the probe.

* **The CAD chapters entered the database: 42 commands across all four
  registered builds, and CAD Create is COMPLETE.** Six CAD body commands
  in `cad.yaml`, and 36 in `cad_create.yaml`: the pane settings and the
  basic shapes, the virtual curve constructors with their index and
  delete commands, the three file importers, the three cross-section
  commands that cut curves out of an existing mesh body, the curve
  transforms, and the three loft commands that turn curves into a mesh
  boundary. With `SWEEPER_SET_MACH_SWEEP` and the flow-separation
  family, the database went from 147 entries at v0.4.0 to 206. Every
  entry carries its own page per edition rather than one citation
  reused, and every command emits on all four builds.

  One command was held back at this point in the cycle: the CAD Create
  mirror, whose name the manual spells one way in its heading and
  another in the sample beneath it. IT ENTERED LATER IN THIS SAME
  RELEASE, under the heading's spelling `CAD_CREATE_MIRROR_CURVES`,
  which the Script Index agrees with; the sample's singular was then
  measured not to be a command at all (RPT-021). The stanza on the tail
  of the sweep carries it.

  Facts the argument names do not carry, which is why these were read
  one at a time rather than pattern-matched:
  `CAD_CREATE_CURVE_ARC` takes NINE coordinates whose FIRST triple is
  the arc's ORIGIN and not a vertex on it; the three curve index
  commands take -1 for every curve; `CAD_CREATE_PROJECT_CURVE` reads its
  PLANE in the frame it names and its projection VECTOR in the global
  reference frame, so a script using a local frame projects along the
  wrong direction with nothing to object;
  `CAD_CREATE_PROJECT_MULTI_CURVE`'s two indices are not
  interchangeable, the first being projected and the second a guide; and
  `CAD_CREATE_REORDER_CURVES` takes a SIGNED axis, six tokens rather
  than three, where every other axis argument in the family takes a bare
  letter. `CAD_CREATE_AUTO_CROSS_SECTIONS` and
  `CAD_CREATE_REVOLVE_MESH_FROM_CCS` each declare EIGHT arguments and a
  signature parser reports seven, because their manual headings wrap and
  the eighth placeholder sits alone on the second line; both samples pass
  eight tokens, which is what settles it. `LOFT_TYPE_U` and
  `LOFT_TYPE_V` mean chordwise and spanwise on the wing loft and radial
  and axial on the other two, so a value carried across means something
  else. And `CLOSE_ENDS` is documented as OPEN or CLOSED on all three
  lofts while all three of their printed samples pass `TRUE`: the table's
  pair and the printed token are all accepted, because refusing either
  side would refuse something the manual states. `FALSE` is NOT among
  them, and was until the review caught it: it is the value set of the
  neighbouring `MARK_TRAILING_EDGES` argument, pasted across.

  `CAD_CREATE_CURVE_EXPORT_CCS` carries phase `geometry` despite its
  name, following `EXPORT_SURFACE_MESH`: a phase is the position the
  ordering rule assigns, and filing a curve export under `export` would
  let a script emit it once and then refuse every remaining CAD Create
  command.

  Not entered at this point: the CAD Create mirror, whose name the
  manual spells two ways, the heading and the Script Index together
  against the sample. It entered later in the same release under the
  heading's spelling, and the sample's spelling was measured not to be a
  command (RPT-021).

* **The Sweeper Toolbox chapter was drafted from a worked example and
  has been redrafted from the reference pages, which changes what the
  emitter accepts.** The example at SRC-003 p.406 exercises two of the
  three sweep modes and three of the four sweep axes, so every gap
  followed from it: `UNIFORM` was missing from all three enumerations,
  `SWEEPER_SET_MACH_SWEEP` was missing entirely, and the velocity axis
  could take a file where the angle axes could take a list, an asymmetry
  the manual does not have. The reference pages give all four axes one
  parameter table, word for word.

  New command: `SWEEPER_SET_MACH_SWEEP`. New accepted mode on all four:
  `UNIFORM`, which takes start, stop and INCREMENT (the parameter table
  labels the triple STEPS, and the Mach sample passes 0.05 there, which
  no count can be). Every axis now takes the value list inline or a file
  path, whichever the caller has.

  Consequence for the caller: `script.emit("SWEEPER_SET_AOA_SWEEP",
  "UNIFORM", [-10.0, 20.0, 1.0])` used to be refused as an unknown mode
  and now emits. No script the emitter accepted before renders
  differently, but the velocity axis gained the inline value list its
  three siblings already had, so its `filename` moved from the second
  positional to the third: a positional `emit("SWEEPER_SET_VELOCITY_SWEEP",
  "CUSTOM", path)` now binds the path to `values` and is refused. Pass
  it as `filename=`. The
  curated `sweep()` helper still covers the CUSTOM subset and says so
  in its docstring, with the extension registered.

* **Eight commands became available on 26.101, and two on 26.121, that
  the database was silent about.** The whole Sweeper family gains a
  26.101 row, `AEROELASTIC_RBF_TYPE` gains 26.101 and 26.121, and
  `CREATE_NEW_MOTION` gains 26.100 and 26.101. Emitting any of them for
  those builds raised `CommandNotInVersionError` before; the manual
  documents them and now the database does.

* **`CREATE_NEW_MOTION` carries a per-version vocabulary.** The February
  2026 build names the first motion type `EUCLIDEAN` and every later
  edition names it `ROTARY`, and the two are not one capability
  relabelled: four commands that configure the February form exist in no
  later edition and two that configure the later one exist in no earlier
  edition. Emitting `ROTARY` on 26.100 is now refused with the February
  token list.

* **A refusal about a per-version grammar cites that version's page.**
  It used to cite the entry-level one, so the refusal above would have
  listed February's tokens beside a page number from the current manual.
  An error message naming the wrong page is worse than one naming none,
  because the reader goes and reads it.

* **`CAD_BODY_ROTATE` accepts the axis index as well as the letter.**
  Its parameter table names only X, Y or Z, in every edition, and the
  sample printed beneath that same table passes `2`, also in every
  edition, so the declared set refused the manual's own call. Pass the
  index as the string `"2"`.

* **`parse_signatures` reads a signature heading that WRAPS.** Five
  commands continue their placeholders onto a second line, identically
  in all four registered editions, and the parser reported every one of
  them short: `CREATE_NEW_RECTANGLE_VOLUME_SECTION` by three arguments,
  the other four by one. A short signature is the worst output this
  module has, because the draft it feeds LOADS: the schema accepts an
  entry with fewer arguments, the emitter then accepts a call with fewer
  tokens, and the solver reads the line differently with nothing between
  them to object. The rule is strict about what continues a heading, a
  line of placeholders and nothing else, so a following heading cannot
  donate its arguments to the command above it.

  No committed entry was wrong: the two affected commands already in the
  database were hand-authored from the page rather than from the parser,
  which is the argument for reading the page that this session has now
  made twice.

* **New public function `pyflightstream.utils.sample_contradiction`**,
  and `render_entry` now writes `???` for a type the manual's own sample
  refuses instead of writing the type. Drafts of commands whose
  parameter table and sample disagree no longer load.

* **New public property `CommandEntry.citation`**, the entry's evidence
  citation whichever kind it carries. A message built from `manual_ref`
  alone printed an empty pair of brackets for an entry resting on a
  probe report.

* **An inline list argument may no longer declare a separator other than
  `space`.** The inline renderer joins with a space and never consulted
  the field, so the two SWEEPER sweep commands spent a release declaring
  `comma` and rendering spaces: right by accident, and unreadable as a
  statement of the grammar. The database now refuses the declaration at
  load time rather than ignoring it. Other layouts honour the field and
  are unchanged.

* **Corrected: the registered scripting-reference page range of two
  manual editions.** SRC-003 was recorded as pp.286-371 against a
  measured pp.281-376, and SRC-740 was short by the same five pages at
  each end. The published manual-coverage page listed ten real reference
  pages as uncited and described 22 in-chapter citations as material
  beyond the reference chapter. A tier-1 guard now fails when an
  evidence citation falls outside its edition's registered range, which
  needs no pdf: both facts are committed.

* Deprecations: none.

* **New database field `probe_ref`, and the first command recorded on
  one.** Until now every entry needed a manual page, which refused a fact
  this repository holds evidence for: RPT-018 measured
  `DELETE_VALAREZO_SEPARATION_BOUNDARIES` accepted on 26.100 while the
  name SRC-741 p.339 prints for the same erase is unrecognised, and
  RPT-015 measured `CREATE_STRATFORD_BULK_SEPARATION` accepted on a build
  whose manual does not mention it. Such a command could not be recorded,
  so the user was pushed to `Script.raw()`, the one emission path with no
  validation at all.

  A committed probe report may now stand where the page would, and the
  entry says which report. Exactly one citation per entry, enforced by
  the model and by a walk over the files: neither is an assertion, both
  leaves a reader unable to say which the entry rests on. A tier-1 guard
  checks that a cited report exists AND names the command, the same rule
  the status citations carry, because a citation pasted from a sibling is
  the defect this database has already produced once.

  It does not relax the status rules. `verified` and `broken` still come
  only from a compat report applied by `pyfs-qa apply-compat` (invariant
  3); `probe_ref` records that a command EXISTS, which is a different
  claim from how it behaves.

  Consequence for the caller:
  `solver_settings(valarezo_separation_boundaries=[])` emits the erase
  again. It was REFUSED between 2026-08-05 and 2026-08-06, which was the
  right answer to a database that could not hold the working name and the
  wrong one once it could.


* **The flow-separation family is in the database, across all four
  registered builds, and `solver_settings()` emits every command of
  it.** That includes the Valarezo erase, whose working spelling is the
  one RPT-018 measured rather than the one SRC-741 prints; the helper
  refused that keyword for one day, between the probe and the
  `probe_ref` field that let the working name be recorded at all, and
  the entry above is the same change seen from the database side.
  Sixteen commands entered, the sixteenth being the probe-backed erase
  named below: the per-mechanism boundary lists of
  26.100 (axial, Valarezo criterion, cross-flow, each a SET and a
  DELETE, plus the cross-flow diameter and its axisymmetric toggle), the
  named assignment models of 26.101 and later
  (`CREATE_AIRFOIL_SEPARATION`, `CREATE_AXIAL_VORTEX_SEPARATION`,
  `DELETE_SEPARATION`), the 26.121 split of the bulk model
  (`CREATE_CYLINDRICAL_BULK_SEPARATION`,
  `CREATE_STRATFORD_BULK_SEPARATION`), and the two members documented in
  every edition and recorded in none of them,
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES` and `LAMINAR_SEPARATION`.

  Four new public models, one per assignment command:
  `AirfoilSeparation`, `AxialVortexSeparation`,
  `CylindricalBulkSeparation`, `StratfordBulkSeparation`, exported from
  `pyflightstream.script.solver_setup` beside the existing
  `BulkSeparation`. Eleven new `solver_settings()` keywords carry them
  and the 26.100 lists. Every keyword whose command belongs to ONE
  generation is version-gated: a 26.100 keyword on a 26.101, 26.120 or
  26.121 script refuses naming the command, and the reverse too.
  `laminar_separation` is the exception and is not a gap, its command
  being documented in all four editions. The database records the two
  generations on disjoint builds; RPT-018 measured part of that
  disjointness, five of the eight February commands on 26.101 and three
  on 26.121, and none of them on 26.120, which sits between two measured
  builds by inference.

  **A probe decided the names rather than a reading, and it had to.**
  The February manual documents the Valarezo pair under two spellings,
  one in a function header and one in a sample, so the RPT-012 rule
  (the header wins) had nothing to decide between. On the licensed
  February build the solver accepts `SET_VALAREZO_SEPARATION_BOUNDARIES`
  and does not recognise `SET_VALAREZO_CRITERION_BOUNDARIES`, and the
  delete is the reverse of what the manual says: the documented
  `DELETE_VALAREZO_CRITERION_BOUNDARIES` is unrecognised while an
  undocumented `DELETE_VALAREZO_SEPARATION_BOUNDARIES` works. The
  database records the documented name with the contradiction on it, and
  the working name has an entry of its own, resting on that report
  through `probe_ref`: it was unrecordable for one day, which is the
  entry above.
  Full method and results in
  `reports/RPT-018_separation-family-across-builds_2026-08-05.md`.

* **Behaviour change: `solver_settings(viscous_excluded=[])` now emits
  `DELETE_VISCOUS_EXCLUDED_BOUNDARIES`.** It used to emit
  `SET_VISCOUS_EXCLUDED_BOUNDARIES 0` followed by an empty index line,
  which asks the parser to read a line carrying nothing. The empty
  sequence is the erase for the viscous exclusion list and for two of
  the three 26.100 separation lists; omitting the keyword, or passing
  None, still leaves the list as the script found it. A caller who
  wanted the old emission was writing a malformed script.

  Three empty sequences are REFUSED rather than acted on, and the
  message says why in each case. `valarezo_separation_boundaries=[]` would emit
  the one name in this family the solver does not recognise, so it
  names `Script.raw()` and the spelling that works. An empty sequence of
  assignment models (`airfoil_separation=[]` and its three siblings)
  emits nothing, which would be a third meaning for `[]` in one
  signature and the only silent one; it names `delete_separations`,
  which is how the solver erases. And an assignment model whose own
  `boundaries` is empty would emit the count 0 followed by an empty
  index line, the malformed shape the viscous-exclusion refusal was
  written for, reached through a different keyword. That refusal covers
  `bulk_separation` too, which routed onto the shared renderer in this
  release: it had its own emission block predating the renderer and was
  the one assignment keyword the refusal did not reach.

  A single assignment model may be passed where a sequence is expected,
  since `bulk_separation` takes one and the habit crosses over; it used
  to die on `object of type CylindricalBulkSeparation has no len()`.
  `delete_separations` reads its `"all"` sentinel case-insensitively and
  refuses any other string didactically, where `"ALL"` reached a `<`
  comparison and raised a bare `TypeError`. `AxialVortexSeparation.frame`
  accepts a declared coordinate-system LABEL as well as an index, like
  every other frame citation in the library.

* **New registry field `inherits_base`, and a build that stopped
  inheriting.** A hotfix build falls back to its base release's command
  evidence, which is right for a real hotfix and was applied on the
  strength of the identifier alone: last digit not zero meant hotfix.
  The 2026-08-04 renumbering put the February 2026 build at 26.100 and
  appended the May build as 26.101, so that rule made the May release a
  hotfix of the February one. It inherited eight February-only commands,
  and `Script(version="26.101")` emitted lines that solver reports as
  deprecated and refuses.

  Inheritance is now stated per build in `commands/_meta.yaml` with the
  reason beside it, and the silent default is gone from four places
  rather than one, each closed after the previous close was measured
  incomplete by the next review round. The registry refuses to load a hotfix index that states
  nothing. **`FsVersion` refuses to be BUILT as one**, which is a
  breaking change to a public constructor: `FsVersion(canonical="26.121",
  alias="26.12", index=4)` raised nothing before and raises
  `UnknownVersionError` now, because `Script` accepts an `FsVersion` and
  the field default made the original defect reachable through the
  documented public surface. And **`resolve()` reconciles an `FsVersion`
  argument against the registry** instead of handing it back, so a
  hand-built object cannot state a wrong descent for a REGISTERED build
  either. And **the REGISTRY answers, in the layer that reads the
  fact**: `CommandEntry.evidence_in` asks the ordering authority rather
  than the object it is handed, so a caller cannot assert a descent in
  either direction, and a canonical the registry has never heard of
  inherits nothing. An unregistered `26.122` used to receive the whole
  26.120 command view while the string `"26.122"` raised for not being
  registered, so the two documented input types of one parameter
  disagreed about whether a build exists. A synthetic version still
  resolves and still sees its own direct records, which is what this
  package's own fixture registries need.

  `bulk_separation` refuses on a build whose grammar drops
  SEPARATION_TYPE, naming that build, both manual editions and the
  `Script.emit` escape. The binder's generic message named an argument
  the caller never typed and cited the 26.120 page to somebody whose
  grammar is documented at SRC-725 p.341.

  26.121 still inherits from 26.120, which is a genuine hotfix pair.

* **New subpackage `pyflightstream.utils`, and its first member
  `utils.manual`**: read a FlightStream manual and report what the
  command database does not record. Point it at a new build's manual and
  it returns the vendor's own Script Index, each command's page,
  signature and sample, and the three-way difference against the
  database (absent, recorded, recorded-but-undocumented).

  ```python
  from pyflightstream.utils import read_pdf_pages, parse_signatures, coverage_against
  ```

  **It proposes and does not write, and the reason is measured rather
  than cautious.** Checked against the 147 entries this database held
  when the tool was written, authored by hand from these same manuals
  (162 since the flow-separation family landed), it reproduces 77
  percent of their argument lists. The remaining quarter are not parser
  bugs: a variable-length list is one `int_list` argument in the database
  and N lines in the manual's sample, a keyword block has no inline
  signature at all, some commands document alternative forms in one
  sample, and the manual names arguments `value` where the database names
  them `layers`. Every layout proposal carries the sentence saying what
  it was read from, so a reviewer can disagree cheaply.

  New optional extra `[manual]` (pypdf, BSD-3-Clause, license card in
  `reports/RPT-017`). Maintainer tooling: no run path imports it, and the
  parsing half needs nothing, because it takes text. Only the pdf reader
  needs the extra.

  **New console script `pyfs-manual`**, the fifth, with two subcommands
  at this point in the cycle; `sweep` joined later and the shipped CLI
  has three.
  `coverage` reports what a build's manual documents and the database
  does not. `draft` renders entries for those commands, and **writes
  nothing unless `--write` is passed with `--out`**; without a
  destination it refuses rather than guessing where to put a draft.

  A drafted entry writes `???` wherever no rule reads a value: every
  phase whose section is unmapped, and every argument type the parameter
  table does not decide (see the entry below, which added that reading;
  before it, every type was unanswered). That
  is deliberate and it is the safety property: the database schema
  refuses `???`, so an unreviewed draft turns the suite red instead of
  quietly becoming grammar the emitter validates other people's scripts
  against. Each also carries a `drafted:` line naming the tool, the
  manual and the page, so one grep finds every machine-drafted entry.

  New public exception `utils.ManualDraftError`, in the catalog and
  keeping `ValueError` as its second base. It refuses a request to draft
  a `verified` or `broken` status: those are promoted from a committed
  probe report by `pyfs-qa apply-compat`, never from a page citation
  (invariant 3).

  **`utils.manual` now reads the manual's parameter table, which is
  where argument types live**, and proposes them: new public
  `propose_type`, and a new `ManualCommand.parameters` field carrying
  the table. Every argument used to draft as `???`, because the
  signature line and the sample block say nothing about a type.

  The rules are public DATA rather than control flow: `TYPE_RULES` and
  its element type `TypeRule`, both exported from
  `pyflightstream.utils`. The ORDER of that table is the specification,
  each row carrying a docstring and the four whose position has been
  wrong once saying why they sit where they do, and the tests pin every
  adjacent pair. Three review rounds each found one rule in
  the wrong place while the order lived in a chain of ifs, and each fix
  was invisible on a revert.

  `Coverage` and `ManualDraftError` are exported from
  `pyflightstream.utils`, which the entry above announced and the
  subpackage did not do: `Coverage` is the return type of a public
  function and could not be named to annotate a variable, and
  `ManualDraftError` was importable only from its own module.

  `read_pdf_pages` takes its page range keyword-only and refuses a range
  it cannot honour. A reversed pair read no pages and `coverage_against`
  reports an empty manual as one that documents nothing, which is a
  confident answer produced by a typo; a first page of zero indexed the
  pdf at -1 and keyed the manual's LAST page as page 0, so a drafted
  entry cited `p.0`. Reaching past the end now refuses too, naming the
  page count, which is also the cheapest sign of the wrong edition.

  `pyfs-manual draft` spells the version flag `--fs-version`, as every
  other CLI of this package does; `--version` is what a reader expects
  to print the package's own version. Every argument is checked before
  the manual is opened, so `--write` without `--out` refuses in a second
  rather than after two full pdf reads on a 400-page document, and a
  malformed page range exits 2 with the flag named instead of raising a
  raw `ValueError`.

  Measured against 148 arguments this repository typed by hand: **57
  percent agreed, 43 percent proposed nothing, none disagreed.** The
  third number is the one to hold. A rule that cannot read a type
  returns None and the draft still writes `???`, so a tranche is still a
  person's work; the failure that matters is a wrong type, because that
  one loads and then validates other people's scripts. The one
  disagreement found while measuring is pinned as a test: matching the
  toggle tokens case-insensitively read the ordinary words "enabled" and
  "disabled" out of a sentence about boundaries and proposed an enum for
  a count.

* **Breaking, and it can affect a script you already wrote:
  `resolve("26.1")` now raises `AmbiguousVersionAliasError` where it
  returned 26.100.** Two registered builds carry that vendor name since
  the February 2026 install was registered, exactly as 26.120 and 26.121
  have shared "26.12" all along. The refusal names both candidates; pass
  the canonical identifier. No deprecation cycle is possible for this:
  the name stopped being unique because the vendor shipped another build
  under it, not because this package renamed anything.

  Read the general lesson rather than only the instance: a vendor
  release name is unique only until the vendor reuses it, so a script
  that passes one is correct until it silently is not. Canonical
  identifiers are the stable input.
* **New registered version: 26.101**, the May 2026 build (vendor build
  5012026). Purely additive, and no version was dropped (CLAUDE.md
  invariant 4).
* **26.100 now names the FEBRUARY 2026 build** (vendor build 2122026,
  read from the solver's own identity line). Its 38 records did not
  disappear: they describe the May build, which was appended as 26.101,
  and they moved there with it. It began this release with no command
  evidence of its own and holds 11 entries since the flow-separation
  family landed, so its derived support level is `documented` rather
  than `registered`. It reaches `operational` later in this same
  release, at 345 emittable commands, which is the per-edition residual
  stanza above.

### Changed

* **Every committed report of a 26.1x run had its version LABEL
  corrected, and nothing else.** Eleven reports recorded runs of vendor
  build 5012026 under the name 26.100, which this repository reassigned
  on 2026-08-04 when the earlier February build took that index under
  the append-only ordering rule. The build number, the executable name,
  the date, the measurements and the outcomes are byte-identical; each
  report carries a note saying so, and each keeps its original id
  because ids are cited elsewhere. The `fs_exes` field of the drift
  reports confirms the reattribution independently: they ran
  `FlightStream.exe`, which is the executable of the install now named
  26.101.
* The `26.100` manual edition is now SRC-741 (Altair FlightStream User
  Guide, February 2026, 396 pages). SRC-725 moves to 26.101, which is
  the edition every existing SRC-725 citation was read from, so no page
  citation changed meaning.

## [0.4.0] - 2026-08-04

### API surface delta

* **Incompatible change, numerical: `farfield.plane_integral` returns
  NaN where it used to return a finite number.** This is the one entry
  in this release that changes an EXISTING result rather than refusing a
  new input, so it is stated here rather than only among the fixes.

  It inherited xarray's `skipna=True`, so an absent sample left the sum
  while its ring weight stayed in the geometry. Flux, force, torque and
  energy shrank in exact proportion to how much data was missing, with
  no warning, no flag and no non-zero status. A 0.3.0 result computed
  over a complete lattice is unaffected; one computed over an incomplete
  lattice was wrong and now says so.

  **How to tell whether your existing evidence is affected**, because
  "recompute everything" is not a triage:

  ```python
  from pyflightstream.farfield import sample_coverage

  # Same integrand you would pass to plane_integral. Returns the finite
  # fraction of the (r, psi) samples, per remaining dimension, so a
  # sweep answers per plane rather than once for the whole array.
  coverage = sample_coverage(integrand)
  bool((coverage == 1.0).all())   # True: nothing changed for this data
  ```

  Where the coverage is 1.0 the old number and the new number agree and
  no action is needed, and that half is exact. Anywhere below 1.0 the old
  number was low by the AREA-WEIGHTED share of the missing samples, which
  the coverage number bounds but does not quantify: `plane_integral`
  weights each sample by its annulus area, so a sample missing at the tip
  costs far more of the integral than one missing at the hub. Coverage
  tells you WHICH planes are affected; recompute to learn by how much.
  The NaN is not a regression, it is the first time the gap was visible. `sample_coverage` is new in this
  release for exactly this question, and it reports per plane rather
  than one number for the sweep, so one dead probe is distinguishable
  from a half-empty lattice.
* **New public names: `script.ScriptLineBreakError`,
  `farfield.sample_coverage` and `fsi.state.check_state_matches_config`,
  and `Script.comment()` renders differently.** All three names and the
  rendering change come from the blocker fixes, and they are listed here
  because this section is where a reader scans for what the surface did.

  `ScriptLineBreakError` subclasses `CommandArgumentError` and is raised
  when a text or path argument contains a line terminator, which used to
  become a line boundary and turn the text after it into the next
  command with `raw_flag` still False. `Script.comment()` now prefixes
  EVERY physical line of a multi-line comment, so a comment can no
  longer end and a command begin inside what was written as prose. If
  you passed multi-line text through a text argument and relied on it
  splitting, `Script.raw()` is the sanctioned route and still sets the
  flag.

  Seven refusals are new in the blocker fixes below, and they are not
  every refusal this release adds; the entries above carry more. A line
  terminator in a text
  argument, a non-finite scalar or list value in an FSI configuration, a
  probe lattice outside its documented domain, an out-of-domain Omega in
  a Campbell sweep, a duplicate column in a parsed table, trailing
  content after an export block, and a solver mode the package has not
  been taught. Each replaces a path that previously produced a result.
* **FR-37 closes as covered and the terminal-status set stays closed at
  six** (SRS 1.13.0). The requirement collided with FR-46, which closes
  the set at the six values `RunStatus` carries: FR-37 asked for a status
  distinct from a COMPLETED one, and a run reaching its iteration cap
  lands in `COMPLETED_MAX_ITER`. The author resolved it in FR-46's favour
  and the requirement is RESTATED rather than merely declared satisfied:
  it now asks for a status distinct from the CONVERGED one, which is what
  this library guarantees. Two of the six give it, `COMPLETED_MAX_ITER`
  for a run that reached its cap and `FAILED_INCOMPLETE_OUTPUT` for one
  whose loop did not complete. Requirement text and docstrings only; no
  runtime change, and no status value was added, removed or renamed.
* **New public names: `commands.Evidence` and
  `CommandEntry.evidence_in`.** The compatibility matrix showed 76 of
  147 cells for 26.121 as though that build had been probed, and it had
  not.

  A hotfix build inherits its base release's evidence until a probe on
  the hotfix overrides it. That default is right and it is not what
  changed. What changed is that the inheritance was INVISIBLE:
  `status_in` returned the base record with nothing saying it had, so an
  inherited cell and a directly probed cell were indistinguishable, and
  each inherited cell carried a citation to a report run on the OTHER
  build.

  It mattered because a hotfix had already been measured changing a
  command: `AIR_ALTITUDE` is broken on 26.120 and verified on 26.121. So
  the inherited answer was known to be falsifiable at the moment it was
  being published as fact.

  ```python
  evidence = entry.evidence_in(resolve("26.121"))
  evidence.record      # the VersionStatus, as status_in returns
  evidence.source      # "26.120" when it came from the base release
  evidence.inherited   # True: an assumption, not a measurement
  ```

  `status_in` is unchanged in behaviour and is now implemented on top of
  `evidence_in`, so the two cannot drift. Prefer `evidence_in` wherever
  the answer reaches a person or a report.

  The published matrix marks every inherited cell and its per-version
  summary gains an **Of which inherited** column, which reads 76 for
  26.121 and 0 everywhere else. A tier-1 guard asserts that the marked
  set and the inherited set are the same set, in both directions:
  showing an assumption as a measurement and showing a measurement as
  an assumption are the same defect pointing opposite ways.

  Not changed, and measured rather than assumed: `version_support`
  counts 69 probed commands for 26.121 of which 68 were probed on that
  build, so its overstatement is one command and its level is unaffected.
* **New public name: `workspace.collection_name`.** It answers one
  question, "what name does this declared output take once collected",
  and it exists because two layers were answering it differently.

  **Behaviour change, and it moves a refusal earlier.** Three campaigns
  used to plan as `READY` and fail at collection, which is after the
  solver has run:

  ```python
  case.outputs = ["loads.txt", "loads.txt"]      # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # one point
  case.outputs = ["a/loads.txt", "b/loads.txt"]  # two points of one case
  ```

  Collection moves every declared output into `raw/` under its BASE
  name, so all three collide there. The plan-time check keyed on the
  declared string, where `a/loads.txt` and `b/loads.txt` differ, and it
  skipped a repeated name carrying the same point tag as itself, which
  is what let the first case through. So the cheap boundary passed what
  the expensive one refused, and the difference was paid in licensed
  solver time.

  This contradicted two statements this project publishes: the case
  model says a case whose points would render the same output name is
  blocked before it runs, and the entry below says every collision is
  refused before anything moves. Both are now true.

  A declared name with a directory part is still legitimate; it simply
  does not make two outputs differ, and the refusal says so.

* **The run matrix collects its outputs, honours its HIDDEN column, and
  says when an override overrules a row.** **Breaking**: a matrix row
  that declares no outputs is now refused. Found by running the
  author's own research campaign, not by a review.

  Three defects, one theme: *the matrix states a fact, a function
  parameter states the same fact, and the parameter wins silently.*

  **Outputs, the one that lost work.** `to_campaign` never set
  `outputs`, so every matrix-driven case carried the empty default and
  the collection step had nothing to look for. With the standard
  `LoadsAssessor`, which the README and the guides tell you to pass, a
  point lands `FAILED_INCOMPLETE_OUTPUT` *after* the solver has run.
  Measured: a thirty-minute unsteady run completed, the solver wrote
  all eight expected files into the run folder, and the point was
  recorded as a failure with the files sitting beside it.

  A row declares them in `VAR_NAMES_VALUES` as
  `OUTPUTS: loads.txt, loads_cp.txt`, **comma**-separated, because the
  slash already separates the `KEY:VALUE` pairs. A row that declares
  none is refused before the solver starts, since a refusal costs
  nothing and the silent empty list cost half an hour.
  `convert_matrix` carries them into `campaign.toml`, so FR-11 stays
  lossless.

  **HIDDEN.** The column existed and was read into the `matrix_hidden`
  variable and never acted on, so a row saying `0` (show the window)
  ran headless because `run_matrix(hidden=...)` defaulted to `True`.
  The parameter now defaults to `None`, meaning the row decides; an
  explicit `True` or `False` still wins.

  **The override.** The explicit `fs_exe` override is the only way to
  run a `MANUAL` row, so it has to win, and it used to win silently
  over a row naming a real build: a row saying `FS_BUILD 26.121` ran on
  the 26.120 executable and was recorded as having requested 26.120.
  It warns now, naming the builds it overruled.

  **Why tier 1 never saw any of it.** The one end-to-end matrix test
  passed a stub assessor that returns `CONVERGED` without reading a
  file, the fixture recipe exported a literal instead of
  `case.outputs[0]`, and the stub solver wrote a fixed name regardless
  of what the script asked for. All three are corrected, and the test
  now asserts the collected files and their hashes.
* **Announced for v0.5.0, breaking, with no alias: the dry-run pair is
  renamed.** No change in this release; this notice is what makes the
  direct break available, the same way the v0.3.0 notes made this
  release's tabular renames available.

  ```python
  dryrun_matrix(...)     # was plan_matrix
  dryrun_campaign(...)   # was plan_campaign
  ```

  `plan_matrix` reads as "plan what is in the matrix" and the function
  dry-runs it: it resolves, validates, builds every script and checks
  the geometry, executing nothing. The prose has called that a
  pre-flight all along, so the divergence was already here.

  `preflight_*` was considered and rejected, because *pre-flight* is
  already the name of a different thing: the solver-identity check
  runs the solver once, lazily, to read which build is installed.
  Collapsing the two under one public name would erase exactly the
  distinction "executes or does not execute" that the rename exists
  to carry.

  `dryrun` is the verb; **`plan` stays the noun**. `CampaignPlan`,
  `PointPlan`, `PlanStatus`, `plan.json` and `write_plan` are
  unchanged, because what the action returns and writes *is* a plan.
  The old names used the noun as a verb.

  Both are renamed rather than only the matrix one: the matrix
  delegates to the campaign, so renaming one would move the asymmetry
  somewhere deeper and less visible.

  **The CLI follows**: `pyfs-matrix plan` becomes
  `pyfs-matrix dryrun`. A library function and the console subcommand
  that fronts it carrying different verbs would put one fact in two
  homes on the surface a user types.
* **Every public refusal the guard reaches now carries the package's
  base exception** (SRS FR-39, whose first clause was false in 70
  places; 24 named sites remain, see the end of this entry).
  **Widening only**: every new class keeps its standard-library base,
  so an existing `except ValueError` or `except RuntimeError` catches
  exactly what it caught before, and `except PyflightstreamError` now
  catches these too.

  FR-39 has read *implemented* since 2026-07-27 and its two guards
  inspect exception CLASSES, never a `raise` statement. An independent
  review found three public functions raising a bare `ValueError`;
  walking the tree found **70 sites across 11 modules**; widening the
  walk to the modules that declare no `__all__` found 46 more; and
  widening it again to reachability, because a bare raise inside a
  module-private helper that a public function calls reaches the caller
  exactly as an exported one does, found 21 more. Nine
  catalogued classes are added for the conditions that had no home:

  * `results.MalformedOutputError`, the sibling of
    `IncompleteOutputError` for a file that is whole and still cannot
    be read as itself (a duplicated column, a second concatenated
    export, an impossible count).
  * `results.FieldNotInExportError`, for a field name absent from an
    export's columns; `KeyError` stays as its second base.
  * `probes.ProbeGeometryError`, shared by the cylindrical lattice, the
    planar grids and the geometry gate.
  * `cases.CampaignConfigError`, for a campaign or recipe that cannot
    be used as written.
  * `farfield.FarfieldInputError`, for fields a reduction cannot
    integrate.
  * `qa.QaEvidenceError`, for a committed QA artifact that cannot be
    read as the evidence it claims.
  * `extras.UnknownExtraError`, for a name used as an extra that this
    package does not have.
  * `commands.CommandDatabaseError`, for a command database that cannot
    be read as the evidence record it claims to be.
  * `fsi.errors.FsiInputError`, for a coupling input a run cannot use.
    Written with the submodule because that is where it is reachable:
    the `fsi` package root re-exports no exception at all, and making
    this one the first is a convention decision left to v0.5 rather
    than taken here by a one-line paste. Both classes are also
    re-exported from `pyflightstream.exceptions`, as every catalogued
    class is.

  New `pyflightstream.probes.errors`, `pyflightstream.qa.errors` and
  `pyflightstream.fsi.errors` hold one shared class each, because the
  package `__init__` imports the submodules that raise them.

  A third guard walks every exported public name, and every
  module-private helper an exported one calls, for bare
  standard-library raises. It is the one that measured 70 when the
  review had reported three. **It does not make the headline
  universally true, and this note says so rather than leaving the SRS
  to say it alone**: 24 sites are exempt by name in a ratchet, three
  `TypeError` raises needing a base this catalogue does not have
  (`PLN-20260803-2340`) and the 21-site reachability tranche deferred
  to v0.5 (`PLN-20260804-0130`). The list is the debt, it is countable,
  and any site the walk reaches that is not on it fails today. SRS
  FR-39 carries the residual and the two measured limits of the walk's
  own reach.
* **The FSI and probe paths are declared experimental, behind an
  explicit boundary** (author's decision, 2026-08-03; REV010-017).
  Documentation only.

  The README gains a **Capability status** table saying, per
  capability, what is supported, what is experimental, what is not
  validated, and what evidence stands behind each. Experimental means
  the interface may change without NFR-20's deprecation window and
  that the evidence is narrower than the supported rows: replaying
  archived fixtures shows the machine runs, not that its physics is
  right for a case nobody has measured. The rotary two-way coupling
  is listed as **not validated**, which `reports/RPT-007` and the
  roadmap's M6 row have said since 2026-07-21 and which no page a
  reader lands on repeated.
* **Six documentation claims corrected, and guarded** (REV010-017,
  REV010-018).

  `pyflightstream.files` was removed at v0.4.0 and three surfaces
  still described it as surviving. NFR-18 said "the manifest carries
  no version field today" while the field had been live since
  `c7cfdad`, so it now reads **implemented**. The README said the
  worked examples reach "coupled aeroelastic runs" and no example
  calls the coupling driver. The index generator documented three
  emitted fields while writing six. NFR-25's evidence line still named
  `require_extra` after the rename to `missing_extra`. And the
  role-review skill called the attestation "the mechanical proof that
  the real agents ran", which the hook implementing it explicitly
  refuses to claim about itself: the `passes` field is recorded and
  never checked, the file is local and gitignored, and any process
  that can write it clears the gate.

  New `tests/test_claim_currency.py` compares each of these claims
  with its subject, so the next drift fails tier 1 instead of waiting
  for a reader.
* **The far-field coverage metric counts what it says it counts**
  (REV010-011). **Breaking** for readers of `masked_fraction`, whose
  value changes when inputs are non-finite.

  `irreversible_deficit` masked on `radicand < 0`, and every
  comparison against NaN is False, so a NaN radicand was neither
  masked nor counted while `sqrt` returned NaN anyway. For radicands
  `[-1, NaN, 1]` two of three outputs were NaN and `masked_fraction`
  reported 1/3, overstating how much of the field the evaluation had
  honored, which is the one thing the metric exists to prevent.

  The dataset now carries `negative_radicand_fraction` (a physical
  statement about the solution: the local state is unreachable on an
  isentropic rothalpy-conserving streamline) and
  `invalid_input_fraction` (a statement about the input), with
  `masked_fraction` their non-overlapping union.
* **NFR-07 says what the implementation delivers** (REV010-013).
  Requirement text only; no code change.

  It promised inputs and invocation "reproducible from its manifest
  entry alone", while `RunRecord` stores hashes and paths rather than
  content and `reconstruct()` requires the workspace and refuses when
  the staged script is absent. The implementation was sound under a
  "manifest plus preserved artifacts" contract, which is what the code
  docstrings had said all along; the requirement now says it too. The
  entry alone identifies and verifies the artifacts by hash and states
  when one is missing or changed.
* **FSI state and loads are bound to the physical model they belong
  to** (REV010-008, REV010-009, REV010-010). **Breaking** for runs
  that were relying on any of the three.

  `FsiState` gains `config_hash`, and a resume across a different
  configuration is refused. Shape compatibility is not physical
  identity: a state saved at `stiffness_scale_factor=1` was accepted
  by a configuration with 999, because blade and station counts
  survive a change of stiffness, mass, rotational speed, offsets or
  relaxation policy. Pass `allow_config_change=True` to carry the
  memory across deliberately. The shape check still runs first, so a
  moved station keeps its specific message.

  `to_elastic_axis` now requires the sections to **cover** the
  configured blade, not merely to fit inside it. `numpy.interp`
  extrapolates constantly from the endpoints, so sections covering
  `[0.8, 1.2] m` were spread across a blade spanning `[0.25, 1.85] m`
  and the structural model received an applied load over a domain the
  evidence never measured, while the logged integral covered only the
  measured interval. The allowed margin is 5% of span at each end,
  calibrated from the committed WP1 export, whose real margins are
  2.49% and 2.31%.

  Phase 3 now requires **both** of its documented criteria before
  phase 4 begins: tip twist settled *and* integrated normal force
  stable between revolutions, the latter against the new
  `PhaseSchedule.thrust_tolerance_fraction` (default 0.02).
  `RevolutionSample.total_normal_force_n` carries the force that was
  previously computed, written to the convergence log, and never
  compared with anything. The configuration docstring had described
  this two-criterion model all along.
* **Publication is coupled to the gates, and to the exact wheel they
  tested** (REV010-016, REV010-019). Release process only; no runtime
  change.

  `publish` depended on `build` alone, so a tag could publish while CI
  was failing, and what shipped had never been exercised: CI installs
  the source in editable mode and tests that instead. The release
  workflow now builds once, records the wheel's SHA-256, installs
  **that wheel** into clean jobs on Linux and Windows at both declared
  Pythons, runs the tier-1 suite and the executable examples against
  it, runs the lint, type, coverage and docs gates, and re-checks the
  digest immediately before publishing. `publish` waits for all of it.

  Every action in all three workflows is pinned by commit digest: a tag
  is mutable and can be repointed at new code with nothing appearing in
  this repository's diff. The release build installs pinned `pip`,
  `build` and `twine` rather than whatever is current. The docs
  workflow no longer grants `pages: write` and `id-token: write` at
  workflow scope, where the dependency-installing build job also
  received them; only `deploy` asks for them.

  New `tests/test_workflow_supply_chain.py` holds all of this as
  repository guards, so a regression fails tier 1 rather than waiting
  for a reviewer to notice.
* **The development tree no longer identifies as the last release**
  (REV010-015). `pyproject.toml` and `CITATION.cff` read
  `0.4.0.dev0`; the release commit sets `0.4.0`.

  HEAD was 66 commits past `v0.3.0` and carried landed v0.4.0 breaking
  removals while every identity still said `0.3.0`, so two
  behaviorally incompatible artifacts answered to one number and no
  bug report, manifest, cached environment or citation could tell them
  apart. A wheel built from this tree now reports `0.4.0.dev0`,
  verified on the built artifact rather than on source metadata.

  New `tests/test_version_identity.py` refuses the combination that
  causes it: a **final** version and a non-empty `Unreleased`
  changelog section may not coexist. It is deliberately conditional.
  The obvious form of this check, "the version must name the current
  commit", is red on every ordinary commit because ordinary commits
  are not tagged, and a suite that is red by construction is worse
  than no suite (`PLN-20260803-1650` recorded that trap before the
  guard existed).

  Choosing the versioning **scheme**, a static development version as
  now or a VCS-derived one such as `setuptools_scm`, remains the
  author's release-time decision and is not made here.
* **A historical manifest row is no longer rewritten as current**
  (REV010-014). **Breaking**: `RunRecord.manifest_schema` is
  `str | None` with default `None`, and `reconstruct` refuses a row
  that carries no schema.

  `manifest_schema` defaulted to `MANIFEST_SCHEMA`, so reading a
  historical manifest stamped every row in it with a positive claim
  about a layout that never described it, and `append_record`
  re-serialized the validated models back to disk, persisting the
  claim: appending one run rewrote each older row with more than
  twenty defaulted fields. `None` now means "predates the field",
  which is a different fact from "asserts the current schema".

  `CampaignWorkspace.read_raw_manifest()` is new and returns the rows
  as written, with nothing defaulted; `append_record` writes through
  it, so existing rows are carried across byte for byte. Migrating a
  manifest is a separate, deliberate act rather than a side effect of
  recording the next run.

  **Correction to the record.** The commit message of `4beb710`
  (v0.4.0 development, pushed) states that this default became `None`
  in that commit. It did not: the only change that commit made to
  `workspace/__init__.py` was an `__all__` sort-order move, and the
  default was still `MANIFEST_SCHEMA` until the present change. The
  claim described work that was intended and not done. History is not
  being rewritten, so the correction is recorded here and in the plan
  ledger instead.
* **An ambiguous export is refused instead of resolved by position**
  (REV010-003, REV010-006). **Breaking** for files that were being
  silently half-read.

  `parse_probe_points` did not require unique header names, while
  `ProbePointsReport.field` returns the first tuple index of a name and
  `fields()` collapses duplicates into one key. A header rewritten from
  `Mach, Cp_ref` to `Cp_ref, Cp_ref` was accepted and
  `field("Cp_ref")[0]` returned the Mach value. The loads parser has
  refused this since PYFS-009; both call the shared
  `results.reject_duplicate_columns` now, which also compares case
  folded, so `Cp_ref` and `CP_REF` no longer count as different fields.

  Two concatenated exports were accepted as one: the software footer is
  located with a first-match search and the table helper stops at the
  first closing separator, so a second complete export was invisible
  even to the duplicate-`Total` guard that exists for this class of
  confusion. `results.reject_trailing_export` refuses a second footer
  in both parsers, because which export a file is evidence of must not
  be decided by position.
* **Non-finite values are refused at the choke points that emit and
  place geometry** (REV010-004, REV010-005, REV010-012). **Breaking**
  for code that passed NaN or an infinity into any of the three.

  `Script.emit` type checked a FLOAT and NaN *is* a float, so
  `emit("SOLVER_SET_CONVERGENCE", math.nan)` rendered
  `SOLVER_SET_CONVERGENCE nan`. `SolverSettings` guards finiteness one
  layer up; `emit` is a documented public interface that goes past it.
  Scalars and every element of a FLOAT_LIST are checked now.

  `ProbeLattice` gains `allow_inf_nan=False`, which is not redundant
  with its validator but what makes it work: every check there is an
  inequality and every inequality against NaN is False, so a NaN tip
  radius, station or ring edge passed by not being caught. The lateral
  closure cylinder gains the domain checks it never had, a positive
  radius and strictly increasing stations.

  `campbell_sweep` built each point with `model_copy(update=...)`,
  which assigns without validating, so a negative or non-finite Omega
  reached the modal solve although `FsiConfig` refuses both at
  construction. Each sweep point is validated through that same model
  now, before the first solve rather than after two of them.
* **A result is now bound to the operating point it claims**
  (REV010-001; independent review REV-010 of commit `4beb710`).
  **Breaking**: a collected export whose printed conditions disagree
  with the requested point is `FAILED_INCOMPLETE_OUTPUT` instead of
  `CONVERGED`.

  `LoadsAssessor` received the `SimCase` and never read it. A valid,
  complete, genuinely converged export printing `alpha=2 deg` was
  accepted as the evidence of a point requesting `alpha=0 deg`, and
  the manifest recorded `CONVERGED` for the wrong engineering case.
  Nothing about such a file is malformed, which is why no parser guard
  could see it. The comparison existed in the tabular layer, which the
  manifest never consults, so the status was authorized long before
  anything disagreed.

  New `pyflightstream.results.conditions` holds the comparison once:
  `bind_conditions`, `ConditionBinding`, `ConditionCheck` and the
  `FIELD_BINDINGS` table (alpha and beta in deg, free-stream velocity
  in m/s, each with a tolerance that is print resolution rather than
  an allowance for drift). Both consumers call it: the assessor before
  a status is decided, and `run_table`/`parse_run_loads` when reading
  a recorded run back.

  `Assessment.conditions` and `RunRecord.conditions` persist the
  decision on **every** outcome: axis, requested, reported, deviation,
  tolerance, unit and whether it was accepted. `None` means an
  assessor that does not compare, including every row written before
  the field existed; an empty list means the comparison ran with
  nothing to compare. A reader must be able to tell "checked and
  agreed" from "never checked".
* **An impossible count and an unrecognized solver mode are no longer
  successful outcomes** (REV010-002, REV010-007; independent review
  REV-010 of commit `4beb710`). **Breaking** for anything that fed the
  parsers malformed exports and got a number back.

  `parse_count` refused a fractional count and accepted `-1`, which is
  a perfectly whole number and not a possible iteration. It takes a
  `minimum` now, defaulting to 0 for iteration NUMBERS and passed as 1
  where the field is a requested budget, because a solve of zero
  iterations did not produce the export the number is printed in.

  The loads assessor tested for `"steady"` and let every other value
  fall through to the unsteady branch, which returns
  `COMPLETED_MAX_ITER` with no error: a mode this package has never
  seen became a successful terminal state. The vocabulary is now
  explicit as `results.SOLVER_MODES`, `results.classify_solver_mode`
  answers whether a printed mode is one of them, and an unrecognized
  one is `FAILED_INCOMPLETE_OUTPUT` before any judgment rule is
  chosen, including the residual path. The printed string stays on the
  report as evidence; only the judgment changed.

  `fsi/loads.py` kept its own `int(parse_number(...))` after the
  results parser had already centralized the exact form, so a declared
  `100.9` sections truncated to `100` and then agreed with the 100 rows
  below it. Both sites use the shared parser now. That is the review's
  own diagnosis of this repository's recurring shape: a guard added at
  one layer while the same invariant stays false at another.
* **FR-08's evidence line names a mechanism that exists** (SRS FR-08,
  reworded; new `tests/test_clean_room.py`). No runtime change.

  The requirement said clean-room provenance "is verified by the
  contribution attestation recorded per change". Measured: 200 commits,
  0 `Signed-off-by` trailers, no per-change attestation of any kind.
  The evidence line named an artifact that had never been in this
  repository.

  Every commit now carries a `Clean-room` trailer, and a tier-1 test
  asserts it for every commit since a stated baseline, with the
  declaration's text pinned so it cannot degrade to a bare "yes". The
  push gate is deliberately NOT cited as the evidence: it records that
  a review happened, says so about itself, and is silent on
  provenance, so pointing FR-08 at it would be a second overclaim
  narrower than the first.

  The limit is stated in the requirement rather than left to a reader:
  nothing can prove "the predecessor was never read". What a process
  can preserve is a declaration and an auditable record of who made it.
* **Two guides join the docs**: [Getting
  started](docs/getting-started.md), which goes from `pip install` to a
  read result with the solver appearing only at the last step, and
  [Replaying a recorded run](docs/tutorial-replay.md), which is what
  the manifest keeps, how to rebuild the exact invocation from it, how
  to tell whether the evidence still matches, and what a record cannot
  give you.

  Sybil gains its `SkipParser` on the docs tree so a page can hold an
  illustrative block that needs a licensed solver or a populated
  workspace, marked and still syntax highlighted. Every block NOT
  marked is executed, so the default stays "checked".
* **The v0.4.0 tabular renames and the keyword-only conversion have
  landed** (PLN-067; SRS NFR-20's accepted consequences). **Breaking**,
  directly, with no aliases and no warning release, exactly as the
  v0.3.0 notes announced them:

  ```python
  to_table(result)                                        # was to_dataframe
  run_table(record, *, loads=None)                        # was run_frame
  sweep_table(workspace, *, loads_file=None)              # was sweep_frame
  parse_run_loads(workspace, record, *, loads_file=None)  # name unchanged
  plan_campaign(campaign, workspace, *, recipes=None, write_plan=True)
  ```

  The word "frame" carried the pandas sense on the public surface while
  this package writes about aerodynamic reference frames in the same
  sentence. The run row's `frame` COLUMN keeps its name, and that is the
  point: once the functions stop using the word, the column means what
  it says.

  `plan_campaign` joins the same window. Its selectors become
  keyword-only, matching `run_campaign` and killing the `write_plan`
  boolean trap: `plan_campaign(campaign, workspace, None, False)` said
  nothing about which False that was.

  No deprecation cycle, per DEP-1: NFR-20's policy takes effect at 1.0,
  so nothing before it owes a warning release.
* **`pyfs-qa` speaks `--fs-version` like every other console command.**
  **Breaking**: `--version` becomes `--fs-version` on `probe` and
  `physics`, and `--versions` becomes `--fs-versions` on `drift`.

  `--version` collides with the convention where it prints the tool's
  own version, and `--versions` differed from its sibling by one letter.
  `pyfs-matrix` already used `--fs-version`, so this is the odd one out
  joining the rest rather than a new convention.
* **The requirement index says how each requirement is verified, and a
  test can now declare which requirement it falsifies** (SRS NFR-13,
  partially delivered and still pending; NFR-25 moves to implemented).
  No runtime change.

  The index published `id`, `text` and `priority`, so a consumer could
  not tell an implemented requirement from a pending one nor find what
  backs either. It now carries `status`, `evidence` and a
  `verification` method, where the distinction that matters is `test`
  (something fails when the requirement stops holding) against `review`
  (a human checks it and nothing fails). The generated
  `reports/requirements-index.json` is the home of record for that
  distribution; the four numbers are deliberately not copied here,
  because a hand-copied count beside a generated artifact is the exact
  drift this bullet is about, and it drifted within this same Unreleased
  block when NFR-18 moved from pending to implemented.

  A `requirement` pytest marker declares that a test falsifies a
  requirement. Every marker must resolve to a live identifier, and the
  covered set is a ratchet. NFR-13 stays **pending** on purpose: 96
  requirements exist and 8 are marked. Marking one on a test that does
  not actually falsify it would be worse than leaving it unmarked,
  because the index would then count a trace that is not one.
* **The package is type checked, and the worked examples run**
  (SRS NFR-27, new; NFR-01d's evidence line corrected). No runtime
  change; `mypy` joins `[dev]` and a `types` job joins CI.

  The four `examples/*.py` were in no CI step. NFR-01d's evidence line
  said they ran under Sybil, and Sybil runs docstring doctests and
  markdown code blocks: the first code a new user runs was the code
  nothing checked. A tier-1 test now runs each one and holds each to
  the extras it declares, so an example that reaches into `[fsi]`
  without saying so fails here rather than in a reader's base install.

  The type check is a **ratchet**, and the measurement is why: the
  first run reported 223 errors in 21 of 53 modules. Those 21 are
  exempted by name, the other 32 are held clean, and a newly dirty
  module fails. The exemption list is the debt, written down.
  `py.typed` is deliberately not shipped: it would tell every
  downstream checker to trust annotations that 223 errors say are not
  trustworthy, and PEP 561 is promised nowhere here, so nothing is
  broken by the absence.
* **Every optional extra refuses the same way, and every dependency
  has a license card** (SRS NFR-02; new public
  `pyflightstream.extras` with `MissingExtraError`, `EXTRAS` and
  `missing_extra`). **Breaking within 0.x** for one narrow clause: the
  `[fsi]` import gate raised a bare `ModuleNotFoundError` and now
  raises `MissingExtraError`, which is an `ImportError` but not a
  `ModuleNotFoundError`.

  Three gated paths raised three different types with three
  hand-written remedy strings, so handling "an extra is missing" meant
  knowing all three, and nothing checked that the remedy printed was
  the remedy that works. There is one type now, and its `remedy` is
  composed from the extra's own name rather than typed, so a message
  cannot name an extra that does not exist.
  `GeometryEngineMissingError` becomes a SUBCLASS rather than
  disappearing: the geometry gate is the one extra whose absence is
  recoverable, so a caller has a reason to single it out.

  The license half: `reports/RPT-016` cards the five runtime
  dependencies and `[plot]`, which had none. The runtime set is the one
  that reaches every user. `xarray` is Apache-2.0, the only non-BSD,
  non-MIT term in it, and the card states why that is accepted rather
  than leaving a reader to re-derive it. Tests now hold the coverage:
  every extra's distributions and every runtime dependency must be
  named in a committed report.
* **The SRS stops being the only judge of its own shape** (SRS
  FR-43, new and deferred; a new `tests/test_srs_consistency.py`). No
  runtime change.

  The document stated its own shape in several places, each maintained
  by hand: the chapter list's identifier range, the acceptance mapping,
  the roadmap backlog. One parser now derives the set and the tests
  assert the prose against it, so a claim about the requirement set can
  no longer be true only on the day it was written.

  It found a seventh drift instance on its first run, past the six the
  review listed: the acceptance mapping recorded an accepted item
  against `FR-43` and no such requirement had ever been written. FR-43
  is added rather than the mapping row removed, because deleting the
  row would hide an acceptance. Its band stays unnamed and the
  requirement is `deferred`: the sister library computes the imbalance
  and returns no acceptance criterion, and setting the number is the
  numerical-analyst seat.
* **A recorded run reconstructs from the manifest alone** (new
  `run.reconstruct()` and `run.Reconstruction`; `RunRecord` gains
  `manifest_schema`, `fs_exe`, `fs_exe_sha256`, `argv`, `cwd`,
  `timeout_s`, `recipe`, `recipe_sha256` and `script_path`;
  `ExecutionResult` gains `argv`, `cwd` and `timeout_s`). Additive.

  NFR-07 promised that the record plus the staged inputs reproduce the
  run. The record held 17 fields and none of them was the command line,
  the working directory, the effective timeout, the executable, or the
  identity of the recipe that built the script, so "reproduce" meant
  re-deriving all of it from executor code that may have changed since.

  `reconstruct()` returns the invocation, the script text, and a
  per-artifact verdict on whether each file still hashes to what the
  record says, with `faithful` as the summary. It refuses a record
  written under a manifest schema it does not know, and one whose
  script is gone, rather than rebuilding something that is not the run.

  `recipe_sha256` is the one that needed a decision: a recipe is user
  code resolved by a dotted name and editable between two runs that
  record the same name, so the name says which function and the hash
  says which version of it. A callable with no retrievable source
  records None, because hashing the repr would make two identical runs
  look different.
* **An unconverged twist iterate is no longer flown.** **Breaking
  within 0.x**: the FSI driver raises the new `TwistIterationError`
  where it used to write the displacements.

  `solve_rotating_static` returns its last iterate whatever happens,
  and above tolerance that iterate is not a solution: the twist was
  still moving when the solve budget ran out. The driver read
  `result.solution` and never `result.twist_residual_rad`, so those
  deflections went into `FSIDisp.txt`, the solver flew a blade shape
  the structural model never settled on, and the only trace was a
  `logger.warning` nobody reads in a batch run. The refusal sits one
  line above the write, because the write is the irreversible act.

  `RotatingSolution` gains `tolerance_rad` and a `converged` property,
  and the convergence log gains `twist_residual_rad` and
  `twist_tolerance_rad` beside the inner-solve count it already
  carried. Phase 1 leaves both cells empty rather than zero: no solve
  ran, and a zero would read as a perfectly converged iteration.
* **CI runs on Windows for the first time, and the coverage floor of
  SRS NFR-16 exists.** No public API change; both are build and
  process.

  NFR-05 has always said Windows is the primary execution target,
  because FlightStream runs on Windows, and CI ran on `ubuntu-latest`
  alone: the platform every user is on was the one platform nothing
  tested. The test job is now two platforms by the two declared Python
  bounds, four legs, with `fail-fast` off so a failure on one leg does
  not hide the others. The docs build and the repository guards moved
  to their own Linux-only jobs, because they test the repository rather
  than the package on a platform.

  NFR-16 has been pending since 2026-07-27 with its floor deliberately
  unnamed until a first measurement. Here it is, whole tier 1 suite:
  6774 statements with 515 missing, 2058 branches with 213 partial, a
  branch-mode total of **90.69%**. The floor is set below that, at 87, in
  `pyproject.toml` where the tool reads it, and it moves as a ratchet
  in a commit that explains it. The margin absorbs the difference
  between the Windows measurement and the Linux enforcement.
* **`RunRecord` records which commit of this package ran**
  (`package_commit`, `package_dirty`), from the new public
  `run.package_vcs_state()`. Additive.

  `package_version` reads the installed distribution's metadata, a
  static string, so every commit between two tags reports the earlier
  tag: measured at 28 commits and 85 files past `v0.3.0` with every
  identity still `0.3.0`. A campaign run from a development tree was
  indistinguishable, in its own manifest, from one run against the
  release. Both fields are None together for a wheel install, and None
  means "not knowable here" rather than "clean".

  The rest of that finding is a versioning-scheme change (a dev version
  carrying the sha, and a guard refusing a final version string off a
  tag). It is release mechanics and is registered, not taken here.
* **Six ways a malformed solver export produced a plausible number are
  refused.** **Breaking within 0.x** for a file with any of them; every
  one used to parse clean and return a number, which is why none was
  noticed.

  * A repeated column in the loads header. Measured: a header naming
    `CL` twice built the row with `CL` winning twice, so the report lost
    `CDi` entirely and published `CDi`'s value under `CL`.
  * A second `Total` row, and a repeated surface name. The later row
    replaced the earlier in silence, so which total the run produced
    was not determined by the file.
  * A fractional value in an iteration field. `int(parse_number(...))`
    truncated, so a printed `312.9` became `312`, and 312 is a
    perfectly ordinary count. The new `results.parse_count` refuses it
    and names the field.
  * An unrecognised token for a printed solver flag. The reading was
    `token.upper().startswith("T")`, so `yes`, `0` and `banana` all
    read as OFF with the same confidence as a real `F`. The tokens are
    now enumerated. A flag read wrongly as off is worse than an
    unreadable one, and `LoadsAssessor` now depends on this exact flag.
  * A residual-history counter that repeats or decreases. `[1, 2, 1574,
    2]` parsed clean, and that shape is two logs concatenated. The
    convergence judgment reads the LAST row, so the run would be judged
    on a residual from an earlier iteration of a different solve.
  * An interior empty cell in an FSI row. Both readers dropped empty
    cells BEFORE counting them, so `1,,2,3` passed the three-field
    check as the triple `(1, 2, 3)` with every value after the hole
    shifted one slot left. The single TRAILING separator the solver
    writes is still accepted, because that is the file format rather
    than a hole, and both cases are tested.
* **A file that was already in the simulation folder is no longer
  collected as a point's evidence.** **Breaking within 0.x**: a point
  whose declared outputs already exist when it starts is refused
  (`FAILED_INCOMPLETE_OUTPUT`) instead of running.

  Every point of a case shares one folder and collection asked only
  whether the declared output existed. Measured with a solver that
  wrote nothing at all: the point was published `CONVERGED`, its record
  named `raw/loads_a+00.0.txt` as its evidence, and that file held
  whatever had been left in the folder. Nothing distinguished the
  record from a real one. The remedy the refusal names is to archive
  the simulation or remove the leftover.
* **`RunRecord` carries a sha256 per collected output**
  (`outputs_sha256`), keyed by the same relative name as `outputs`.
  Additive; empty on manifests written before v0.4.0. Inputs have
  carried a hash since the first manifest and outputs carried a name
  and nothing else, so evidence edited, truncated or replaced after the
  run still matched its record.
* **Archiving a simulation twice refuses instead of replacing the first
  archive.** The archive name derives from the sim id, so the second
  render collides; the zip was opened truncating and the source folder
  deleted afterwards, so both copies of the earlier run were gone and
  nothing was raised. The operation that exists to preserve a run was
  the one that lost it. The refusal names the remedy: move the existing
  archive, or give the workspace an archive template that
  distinguishes the runs.
* **A run that forced all its iterations is no longer called CONVERGED
  for stopping early.** **Breaking within 0.x**: with
  `SOLVER_SET_FORCED_ITERATIONS` enabled, no declared solver log, and
  an iteration counter below the requested budget, `LoadsAssessor` now
  returns `FAILED_INCOMPLETE_OUTPUT` where it returned `CONVERGED`.

  The no-log judgment infers convergence from an early stop, and that
  inference holds only while the convergence threshold is what can stop
  the solver. Forcing all iterations turns the threshold off, so an
  early stop means the opposite. `LoadsReport.forced_iterations` was
  parsed and never consulted, so a run that stopped at 312 of a forced
  500 was published converged, indistinguishable in the manifest from
  one that genuinely met the threshold at 312.

  Narrow on purpose, and the three unchanged cases are tested as
  controls: an unforced early stop is still `CONVERGED`, a forced run
  that reaches its budget is still `COMPLETED_MAX_ITER`, and a footer
  that does not print the line at all still gets the count judgment,
  because not knowing is not the same as knowing it was forced.

  The status is a constrained choice rather than the right name for it,
  and the assessor's docstring says so: the terminal set is closed at
  six (SRS FR-46), and the author resolved on 2026-08-03 that it stays
  closed. FR-37 is restated
  to ask for a status distinct from the CONVERGED one, which is what the
  library guarantees, and closes as covered (SRS 1.13.0).
* **"Supported" was one word covering four states, and is now four
  named values** (SRS FR-49, new). New public names at the top of the
  package: `SupportLevel`, `support_table()`, `version_support()`,
  `support_level()`, plus the `pyflightstream.support` module with
  `minimal_workflow()`, the `VersionSupport` record those functions
  return, and the two data members a caller reads rather than
  reconstructs, `SUPPORT_LADDER` and `MINIMAL_WORKFLOW_COMMANDS`.
  Purely additive.

  ```python
  >>> import pyflightstream
  >>> pyflightstream.support_level("26.000")
  <SupportLevel.REGISTERED: 'registered'>
  ```

  Registering a version made every public surface call it supported.
  26.000 is registered, is accepted by `Script(version="26.000")` and
  by a campaign, and carries evidence for zero of the database's
  commands, so nothing whatever can be built for it. The README said so
  in a sentence; nothing said it in a value a caller could read.

  The levels ascend `registered`, `documented`, `verified`,
  `operational`, and every one is derived from the command database
  rather than declared in a file, for the same reason a command status
  is: a hand-set level outlives the fact behind it. Today that reads
  26.000 registered, 26.100 documented, 26.120 and 26.121 operational.

  `operational` is the level that claims a user can get from geometry
  to a loads file, and its claim is checked by performing it:
  `minimal_workflow(version)` builds the shortest complete script, and
  a tier 1 test builds it for every version reported operational. The
  README's version table is pinned to the derived values by a test, so
  the published claim and the computed fact cannot drift.
* **A command a probe measured broken is refused at emission, and the
  way through is recorded** (SRS FR-48, new). **Breaking within 0.x**:
  a recipe that emitted `AIR_ALTITUDE`, `NEW_OFF_BODY_STREAMLINE`,
  `SET_MOTION_START_TIME` or `SWEEPER_REF_VELOCITY_SAME` against a
  version whose record is `broken` now raises `BrokenCommandError`
  where it used to build a script.

  `broken` is the one status backed by a probe that WATCHED the command
  fail, and it was the one status the emitter did not act on. The
  consequence is not a crash. An absent command produces no run at all;
  a broken one produces a complete run with wrong numbers in it. On
  26.120 the solver reads AIR_ALTITUDE's METERS argument as feet
  (`reports/compat/CMP-26120_2026-07-23_pln012.yaml`), so
  `atmosphere(script, altitude=1000.0)` would have asked for 1000 in
  whatever unit the solver defaulted to, and written a manifest
  calling the script fully validated. The measurement is at one
  altitude only: at 5000 the default read as feet.

  ```python
  script.allow_broken("AIR_ALTITUDE", reason="reproducing a 2026-07 run")
  helpers.atmosphere(script, altitude=1000.0)
  ```

  The waiver emits the command and records it through the new exported
  type `script.BrokenCommandUse`, one instance per waived command:
  `script.broken_commands`
  and the new `broken_commands` field of `RunRecord` carry the command,
  TWO versions, the committed report, the recorded observation, the
  justification and the script line the first waived emission rendered.
  The two versions are `version`, the build the script targeted, and
  `source_version`, the build whose record is broken and therefore the
  build the cited report was run on; they differ exactly when a hotfix
  inherits its base release's record, and reading either as the other is
  the defect this release is named for.

  The same promise `raw_flag` makes for unvalidated
  text, for a case that is worse, because a raw line at least looks
  unusual. `reason` is required; it is the only field nothing
  automated can supply.

  Registered on the script rather than passed per call, so it reaches
  the curated helpers without every helper growing an argument, and a
  waiver for a command that is not broken in the target version is
  accepted and records nothing: AIR_ALTITUDE is broken in 26.120 and
  verified in 26.121, and one recipe is meant to run against both.

  Two of this repository's own goldens were pinning the mistake and
  were corrected in the same change, which is the part worth reading
  before dismissing this as defensive: the actuator polar golden pinned
  `altitude=1000.0` on 26.120, and the rotor unsteady golden pinned
  `SET_MOTION_START_TIME`, at which the solver ABORTS script
  processing, so everything after it never ran. The altitude rendering
  is still pinned, on 26.121, where the command is recorded verified.
  Not "where the hotfix fixed it": RPT-014 refuses that attribution in
  its own words, because three variables separate the two runs (the
  build, the harness and the session file) and the disambiguating
  probe has not been made.
* **A truncated evidence note now says that it is truncated.** The
  `note` a compat promotion writes into the command database is capped
  at one line, and the cap used to cut mid-word with nothing to show
  for it: AIR_ALTITUDE's read "reports the 5000 m standa", losing the
  measured diagnosis that followed. The cut is now made at a word
  boundary and marked `[...]`, because that note is what the new
  `BrokenCommandError` shows the caller, and a refusal that looks like
  a corrupt database is a refusal that gets worked around.

* **Research geometry can no longer enter the repository unnoticed**
  (SRS NFR-14, which was pending). A tier-1 guard walks every tracked
  path and fails on any geometry or mesh extension outside a small
  allowlist of provably synthetic fixtures, and a `forbid-geometry`
  pre-commit hook refuses the same class at commit time.

  This closes the one breach this project calls irreversible: a push
  publishes, and deleting the file afterwards does not unpublish it from
  any clone that already fetched. It was enforced by discipline alone
  until now, and discipline was measured to be all there was: a 37 kB
  mesh added under `examples/` and staged passed the entire tier-1 suite
  and the CI guard job, which looks only for pdf, notebook and
  `_private/` paths.

  The suffix set is derived rather than invented: `IMPORT`'s
  `file_type` enum in the command database, plus the saved simulation
  `.fsm`, plus the CAD interchange formats research geometry arrives in.
  Stated as a residual rather than hidden: the guard keys on extension,
  so geometry carried in a generic container (a node list in a `.csv`)
  is outside it, and NFR-08 stays a discipline for that.
* **`PyflightstreamError` is the package base exception, and every
  CATALOGUED exception descends from it** (SRS FR-39, which was pending
  on exactly this clause). Read that word before relying on the
  sentence: a residual of bare standard-library raises survives. Every
  site the guard's walk reaches is named in the ratchet in
  `tests/test_exceptions_catalog.py`, which is the single home of that
  list; SRS FR-39 states the walk's reach and the count, and at least
  one site sits outside the walk. One except clause
  catches the catalog:

  ```python
  from pyflightstream.exceptions import PyflightstreamError
  ```

  Purely additive, and deliberately so: every type keeps the
  standard-library base it already had as a second base, so
  `UnknownVersionError` is still a `ValueError`, `WorkspaceError` still
  a `RuntimeError`, `OptionError` still a `KeyError`. No `except` clause
  that worked before stops working, and a table in
  `tests/test_exceptions_catalog.py` pins each of those builtin bases so
  a later edit cannot quietly move one.

  The base parents the exceptions and not `VersionMismatchWarning`,
  which is a warning: it stays in the catalog, because the catalog
  covers exceptions and warnings alike, and it stays out of the
  hierarchy, because calling it an `Error` would mislead whoever reads
  the traceback. Two separate guards now run: one fails when a class
  does not join the catalog, one fails when it joins the catalog
  without joining the hierarchy.

  Why it lands before any renaming: a name is the dispatch key only
  while there is no base to catch. With the base in place, renaming a
  leaf stops costing a deprecation cycle, so the naming questions the
  API vocabulary review raised get answered later and more cheaply.
  The cause-versus-rule split in the current names is therefore left
  open on purpose, not overlooked.
* House conventions gain two entries, in the same `CONVENTIONS` home
  that feeds `help()` and the docs site: **diagnostics are nouns and
  validators say `check_`** (`sample_coverage` beside `check_recipe`),
  and **a validator takes the values it compares where the object would
  reverse the dependency direction**. The second is a layering rule
  wearing a naming hat: `check_state_matches_config` takes two integer
  counts rather than the config object, so `fsi.state` keeps its import
  surface to pydantic, and those counts are keyword-only because
  same-typed scalars transpose silently. Both halves that can be checked
  mechanically now are: a `check_` function returning a value fails the
  suite, and so does `fsi.state` importing `fsi.config`.
* **FlightStream 26.121 is registered, and the vendor name "26.12" stops
  resolving.** The vendor ships the hotfix build under the same release
  name as 26.120, so that name now identifies two registered builds.
  `versions.resolve` refuses it with the new
  `AmbiguousVersionAliasError` (catalogued, carrying `alias` and
  `candidates`) naming both candidates, instead of returning one of
  them. Every caller that passed the vendor name must pass a canonical
  identifier: `Script(version="26.120")`, `--fs-version 26.120`,
  `fs_version = "26.120"`.

  Incompatible by intent, and the alternative was worse: `resolve`
  matched canonical-or-alias and returned the first hit in release
  order, so once 26.121 was registered the vendor name would have
  handed back the pre-hotfix solver silently. A caller who wrote the
  vendor name meaning "the current 26.12" would have got the build
  before the hotfix, with no error anywhere. The refusal is loud; the
  old behaviour was not.

  Resolution also matches canonical identifiers across the whole
  registry before considering any alias, so an entry can no longer be
  shadowed by an earlier one carrying its canonical as an alias.
  Registered versions are now 26.000, 26.100, 26.120, 26.121; the last
  digit indexes vendor hotfix builds, so 26.121 is hotfix build 1 of
  the 26.12 release (SRS FR-02c, new).
* **A campaign pointed at the wrong FlightStream installation now stops
  before its first point**, not after its last. `run.check_solver_identity`
  is new and public: it runs the cheapest possible script (a sentinel, a
  log export, and close), reads the build number out of the exported
  log, and refuses when it is not the build the campaign's version
  declares. `run_campaign` calls it once, lazily, just before the first
  point that will really execute, so a resume with nothing pending still
  spends no solver process, and takes `preflight=False` to skip it.

  Layered rather than sole. A mismatch is refused there on positive
  evidence; an identity the check cannot read warns and falls through to
  the parse-time comparison below, because refusing on an unreadable log
  would make the guard's own failure mode "no campaign runs at all".
  Nothing is checked, and no solver process spent, for a version with no
  registered build.
* **A run can now tell which solver build actually produced it.** The
  registry records each version's vendor build number (`FsVersion.build`,
  new, read from `commands/_meta.yaml`), and parsing a loads or probe
  export compares it against the build the output printed, warning when
  they differ.

  This is the run-time half of the alias refusal above, and without it
  that refusal was only half a guard: it settled which build the run
  ASKED for and could not show which one ran. The version string cannot
  show it either, because 26.120 and 26.121 both print "26.1" and they
  carry different records, `AIR_ALTITUDE` being the measured case. So a user
  who took the refusal seriously, moved to 26.121 and left `fs_exe`
  pointing at the 26.120 install got no warning at all, on exactly the
  command whose units defect that build carries.

  Build numbers are evidence, not configuration: each is taken from a
  committed report's `solver_identity` for its own version, and a
  tier-1 guard fails if a registered build appears in no such report.
  26.000 has none registered, because no committed report records one;
  there the version-string check remains, unchanged.
* `pyfs-qa probe`, `physics` and `drift` now refuse an unresolvable
  `--fs-version` (`--fs-versions` on `drift`) with the library's own message on stderr and exit code 2,
  instead of a traceback. Both refusals it covers are ordinary user
  error: an unregistered identifier, and a vendor name shared by several
  builds. A wrapper keying on the exit code sees 2 where it used to see
  1.
* **The 26.121 manual edition is registered as SRC-740**, a separate
  source rather than a re-issue of SRC-003, and the edition entry says
  why: its scripting reference is shifted by three pages throughout, so
  an SRC-003 page number does not address the same page in it.

  Two of the commands it documents join the database with a 26.121
  status only, so a 26.120 script still refuses them:
  `DELETE_SURFACES` (p.315) and `NEW_UNSTEADY_SOLVER_SURFACE_PROBE`
  (p.350), the latter being where the six boundary-layer parameters
  enter the unsteady vocabulary. `UNSTEADY_SOLVER_NEW_FLUID_PLOT` gains
  a 26.121 grammar override for the same six values SRC-740 adds to its
  `PARAMETER` enum.

  `DELETE_SURFACES` is registered narrow, with the single index its
  parameter table declares, because one of its samples passes three
  bare integers under a multiple-surface heading and the two readings
  delete different surfaces.

  The other four are **not** landed, and the reason is worth stating:
  they belong to the settings families, where a command is not
  registered by a database entry alone. A tier-1 guard requires every
  such command to carry a snapshot flag and a keyword on the public
  `solver_settings()` helper, because a solver setting the snapshot
  does not know is a run whose manifest describes the solver state
  incompletely. They are backed out rather than shipped half-wired.
* `UNSTEADY_SOLVER_DELETE_ALL_PLOTS` joins the command database
  (`documented`, SRC-003 p.347). It was documented in the 26.12 manual
  and never registered; the gap surfaced while diffing the 26.121
  manual against the database.
* Solver toggles read the solver's own vocabulary as well as Python
  booleans: `ENABLE` and `DISABLE` (any case) are accepted by every
  helper argument and every `cases.SolverSettings` field that switches a
  flag, resolved before the helper emits anything, and stored and
  snapshotted as bools. New public module
  `pyflightstream.script.toggles` (`resolve_toggle`,
  `SOLVER_TOGGLE_WORDS`, the `Toggle` annotation), used by both the
  helpers and the case models so the vocabulary has one home, plus
  `cases.SolverToggle`, the annotated field type any settings model can
  reuse.
* `LoadsAssessor()` now takes no argument by default and reads the
  case's first declared output as the loop rendered it for that point,
  which is what a swept case needs; naming the file explicitly still
  works.
* Incompatible changes: a toggle value in neither vocabulary is refused
  where a truthy string used to pass silently (a helper call passing
  `'yes'`, and a settings file or preset whose flag reads `"true"`,
  `"on"`, `"1"` or `0`, which pydantic's lax bool parsing used to
  accept); a multi-point case whose declared output names lack the
  `{point}` placeholder is refused, because those points would
  overwrite each other's evidence; and a recipe reference whose
  callable does not take `(case, script)` is refused at resolution
  instead of raising a bare `TypeError` once per point.
* `solver_settings(vorticity_drag_boundaries=...)` is optional again
  (a relaxation, so no caller breaks). Omitted on a script that has not
  selected yet, it emits no selection command and the snapshot records
  the flag as `default` with an empty selection and its citation, or as
  `unknown` on a FlightStream version where the command has no recorded
  evidence; omitted on a second settings call of the same script, the
  selection of the earlier call stands, in the script and in the
  snapshot. An empty sequence is refused.

### Removed

* **`pyflightstream.files` and `pyflightstream.cases.matrix_legacy` are
  gone**, on the horizon their own deprecation-ledger entries recorded:
  `removal_version="0.4.0"`, set when they were introduced in v0.3.0.
  Import `pyflightstream.workspace` and `pyflightstream.cases.matrix`
  instead; `LegacyMatrixError` was already `MatrixError` and `LegacyRow`
  already `MatrixRow` through the shim, so only the module path moves.

  Kept rather than extended because NFR-20 says a promise already
  recorded is kept regardless of version, and because the deadline guard
  would otherwise have turned the suite red at the release commit's
  version bump, which is the worst moment to discover a removal window.
  The deprecation ledger is now empty and the machinery stays: the
  policy binds from 1.0 and the next shim registers there.

### Added

* **The user guide is refreshed for 26.121, and a guard now keeps it
  current.** Six claims went stale when the 26.121 onboarding landed
  and nothing caught any of them: the guide is neither built nor
  executed by CI, so every claim in it was true only until the next
  licensed session moved the evidence underneath it.

  Corrected: the version diagram, which drew three nodes ending at
  26.120 beside a listing that printed four; the pinned refusal
  transcript, which listed two recorded versions where the library
  prints three; AIR_ALTITUDE, which the guide called broken without
  saying on which build, when in fact the vendor hotfix fixes it and the
  probe on 26.121 promoted it to verified; SET_MOTION_START_TIME, which
  said "await re-probe" after the re-probe had run and found the same
  abort; and the pitfall table, which now names the builds each finding
  applies to and gained the SWEEPER_REF_VELOCITY_SAME row it was
  missing.

  The AIR_ALTITUDE entry is the one with user consequence, so it now
  carries the number: on 26.120, 5000 METERS produced 1.056 kg/m^3, the
  5000 ft standard state, where 0.736 is correct. A density 43 percent
  high with no error, and the hotfix digit in the version identifier is
  what lets the database say the two builds disagree.

  The counts are gone rather than corrected (author's decision,
  2026-08-03). "144 commands" was wrong by three, and the plan item
  recording that it was wrong was itself wrong by two the day after it
  was written. The compatibility matrix generates the current numbers on
  every docs build, and the guide points at it.

  `tests/test_guide_currency.py` is the guard, and it is a different
  failure class from `test_guide_api_names.py`: that one checks the
  names the guide teaches, this one the facts it states. No
  hand-written command count, the curated-helper count equal to what the
  module defines, every registered version mentioned, every pinned
  transcript equal to what the library prints, every pitfall row naming
  the builds the database calls broken, and every broken command having
  a row at all. That last one closes the hole the others leave: a
  missing row is invisible to a check that reads the rows present, and a
  missing row is what happened. Six mutants, one per original stale
  claim, all caught.
* **A tracked file may no longer name the workspace container's
  absolute path.** CLAUDE.md has always said machine configuration is
  never a literal path in a committed file; a tier-1 guard now holds
  it, alongside the email-address and user-profile-path checks that
  landed on 2026-07-28.

  Not an absolute-path shape, which was measured to be the wrong guard:
  32 tracked files match one and 30 of them are illustrative solver
  paths in examples, goldens and fixtures (`C:/cases/wing.fsm`). The
  guard keys on the container directory's name, which is what separates
  a path that teaches from a path that leaks, and is the same on any
  clone. The two files that carry it today are hash-pinned vendored kit
  bodies this repository cannot edit, so they are allowlisted by name
  with their kit rows, the allowlist itself is checked for stale
  entries, and the fix is routed to the level that owns those bodies.
* **FlightStream 26.121 is onboarded with solver evidence, not just
  registration**: `reports/compat/CMP-26121_2026-08-02_full.yaml` is a
  licensed tier-2 run of 109 probe specifications against solver build
  #7262026, and 68 statuses are promoted from it.

  One command changed for the better: `AIR_ALTITUDE` was `broken` on
  26.120 because its `METERS` argument read as ignored (5000 m gave the
  5000 *foot* standard density, 1.056 kg/m^3, observed twice on the
  pre-hotfix build); on 26.121 the same assertion observes
  0.736 kg/m^3, the 5000 m value. Anyone setting altitude in metres on
  26.120 was solving at the wrong density, silently, and that half
  stands on the 26.120 evidence alone.

  One changed the other way: `SWEEPER_REF_VELOCITY_SAME` ran without a
  script abort on 26.120 and aborts on 26.121.
  `NEW_OFF_BODY_STREAMLINE` and `SET_MOTION_START_TIME` are broken on
  both builds.

  Attribution is deliberately withheld, because three things differ
  between the two runs and not one: the solver build, the probe harness
  (0.0.1.dev0 to 0.3.0, with the specifications changing inside that
  window), and the session file. The run establishes what was observed
  on each build, not what the vendor changed. The disambiguating run,
  this harness against the 26.120 executable, was not made.
* `reports/RPT-015_bulk-separation-family-acceptance_2026-08-02.md`:
  the bulk-separation family probed on both builds, because RPT-014's
  rename checklist held one item that was a physics question rather than
  a naming one. It turned out to rest on a false premise and is
  withdrawn rather than answered.
  `CREATE_STRATFORD_BULK_SEPARATION` is **not new in 26.121**: the
  26.120 solver accepts it too, where no manual documents it, so the new
  edition documented an existing command rather than introducing one.
  And `CREATE_BULK_SEPARATION`, which the database records as
  `documented` for 26.120, is **refused by the 26.120 solver in every
  documented form**, including the three-argument one RPT-012 ran
  successfully on 26.100. No status moves on this report: it came from
  an ad-hoc probe rather than the harness, so `apply-compat` cannot read
  it, and a status promoted outside that path is what invariant 3
  forbids. Registered instead.
* `reports/RPT-014_26121-manual-diff-and-probe_2026-08-02.md`: the
  26.121 onboarding record. It documents that the hotfix carries its own
  manual edition (413 pages against 410, every scripting-reference
  citation shifted by +3) while the vendor release-notes PDF is
  byte-identical between the two installs and documents none of it; the
  six commands the new edition adds and the three it drops; two
  signature changes on commands already in the database; four defects in
  the vendor's own document; and the human decision checklist for three
  suspected renames, one of which (`FLAT_PLATE` bulk separation to
  Stratford) is a physics question and not a naming one.
* User guide section on migrating a loose script builder to the
  `ScriptRecipe` protocol: the before and after of
  `build(workdir) -> Script` becoming `build(case, script) -> None`,
  with the five moves it takes (do not create the Script, open
  `case.geometry` so the run identity is the staged file, read the
  point from the case, export the rendered `case.outputs` names, and
  give the function an importable address). This is the path of
  everyone arriving from a driver script, and it was documented
  nowhere (feedback channel item 4, PLN-074).
* House conventions gain "Toggles read both vocabularies", rendered in
  `help()` and on the docs site from the same `CONVENTIONS` home.
* House conventions page on the docs site
  (`reference.conventions_markdown`, the same source as the offline
  `help()` conventions section), wired into the generator and nav.
* Automated PyPI release through trusted publishing (OIDC):
  `.github/workflows/release.yml` builds, checks the tag against the
  `pyproject.toml` version, and publishes from the GitHub `pypi`
  environment on a `v*` tag, so no API token is stored in the
  repository (mirrors the ITACA release workflow). Development process:
  a mandatory role-review push/release gate now blocks a `git push`
  until the specialist reviewer agents have run and attested every
  commit the push would make new, plus the ref being pushed, and denies
  any push while the incident ledger shared with ITACA has an open
  blocking incident for this repository; a new `incident-analyst`
  charter owns the structural-cause analysis, and `tests/test_push_gate.py`
  pins the gate's decisions (`.claude/` hooks, agents and skills;
  internal tooling, not a package surface).
* Development process: the session documents (state file, handoffs,
  logbook, inbox, progress reports) moved out of the repository-local
  private tree into the coordination hub, where they gain version
  control, and are located by a new `PYFS_SESSION_ROOT` environment
  variable read by the `handoff`, `plan`, `audit` and
  `derive-requirements` skills. Unlike the two existing
  machine-configuration variables it is documented as stop-on-unset
  rather than skip-on-unset, because a session that cannot find its
  state file would otherwise close by writing its record nowhere. The
  plan ledger and the design documents deliberately did NOT move: a
  repository's own plan and architecture are its own facts. Two new
  tier-1 guards came with it, `tests/test_env_contract.py` (the
  documented variables and their consumers agree, and no skill prints
  the bash-form variable as a path, which in PowerShell expands to
  nothing silently) and a house-style check that no committed file
  re-hardcodes a migrated session path; `tests/test_plan_checker.py`
  now also pins the plan checker's exit taxonomy, seven tests over the
  six documented outcomes plus the usage branch that shares an exit code
  with one of them, including two weaknesses recorded rather than hidden
  (an empty ledger directory exits zero, and a DELETED exemption list
  stays silent while every legacy id fails at once) (`.claude/` skills
  and `CLAUDE.md`; internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored from
  0.2.2 to 0.2.3 for the plan checker and its mutation companion, a
  promotion this repository's own adoption review produced and then ran
  three days behind. The hardening it brings is that a `legacy_ids.txt`
  which exists but cannot be read is now a named `CONFIG ERROR` at exit
  2 before validation, instead of being swallowed into an empty
  exemption set and reported as 88 ledger defects pointing at the one
  fix the plan rules forbid. Also recorded, because the drift test's
  green is easy to over-read: that test detects a hand-edit and cannot
  detect falling behind, which is why the lag was invisible. The drift
  test also gained pins on the two provenance-header fields that sit
  outside the body hash and that no assertion previously reached: the
  `note:` target of each vendored copy, and the `canonical-source:`
  line, which is where a copy records that its body was built for the
  kit rather than adapted from the AGPL predecessor (`.claude/tools/`,
  `tests/test_kit_drift.py`; internal tooling, not a package surface).
* Documentation and process: the push gate is re-vendored from the kit at
  0.2.16, alone, to close a FAIL-OPEN it carried at 0.2.4
  (`INC-20260802-1450-shared`). `_strip_heredocs` removes heredoc bodies
  before tokenizing so a commit message that merely describes a push is
  not misread as one; its opener pattern matched anywhere in a line,
  including inside a quoted commit message, and when no matching
  delimiter ever arrived it dropped every remaining line. A real push on
  the next line went with them, and the gate returned without requiring
  an attestation, reading the ledger, or checking for a release tag. Not
  a weaker refusal: no refusal, reachable in two lines of ordinary shell
  with no heredoc anywhere in them. Measured here against the deployed
  0.2.4 body before it was replaced: three reduced reproductions each
  produced no decision at all while a bare unattested push denied; on the
  0.2.16 body all four deny, and neither pinned heredoc behaviour moved.
  The cases are now permanent in `tests/test_push_gate.py` and were
  proven by mutation, failing on the 0.2.4 body restored from git.
  TWO THINGS RIDE THIS VENDOR that are not the heredoc fix, both from kit
  0.2.8, and both change behaviour. The incident-ledger variable the gate
  reads is renamed from `PYFS_INCIDENT_LEDGER` to
  `COORD_INCIDENT_LEDGER`, retiring the last per-repo difference between
  a vendored body and its master; `PYFS_INCIDENT_LEDGER` stays live for
  the `incident-analyst` agent, whose charter is a hash-pinned body on a
  kit row NOT taken here, so a clone now sets both to the same directory.
  And an unset variable now DENIES a push where it used to mean the check
  did not apply, which sounds like a courtesy to a fork and was measured
  to be something else: the level that writes the incidents pushed past a
  blocking incident of its own authorship, on a variable name that had
  never existed. Order matters on a fresh clone and is the reverse of the
  obvious one: export the variable BEFORE this body is in place, since a
  PreToolUse hook without its configuration denies every command. The
  rest of the kit is deliberately NOT adopted; see below (`.claude/`,
  `CLAUDE.md`, `tests/`; internal tooling, not a package surface).
* Measured and NOT adopted, recorded so the gap is a decision rather than
  a discovery: against kit master 0.2.17 on 2026-08-02, six of the nine
  kit artifacts this repository vendors are behind their masters and the
  kit manifest carries 25 further rows never vendored here, an adoption
  surface of 31 artifacts. Only the push gate was taken, because it alone
  was blocking. The earlier estimate of "17 findings across 8 files" was
  measured against kit 0.2.7 in July and is superseded by this one
  (`tests/test_kit_drift.py` records the same numbers next to the pins;
  internal tooling, not a package surface).
* Documentation and process: the shared process kit is re-vendored to
  0.2.4 for the push gate, the incident-analyst charter and the private
  snapshot tool, a promotion whose reason is privacy rather than
  behaviour. `.claude/tools/snap.sh` is tracked and this remote is
  public, and its hashed body set the snapshot repositories' git
  identity from a personal name and a personal email address and located
  the shared ledger at an absolute path under a personal user profile.
  The 0.2.4 body reads the ambient git configuration with a neutral
  fallback and locates the shared tree through a new
  `COORD_SHARED_LEDGER_TREE`; three occurrences of a personal first name
  in the gate's deny messages and one in the analyst charter now read
  "the author", as do one line each in the `handoff` and `plan` skills.
  No allow or deny decision changed, which was verified per replacement
  rather than assumed: each sits inside a deny message string, none in a
  condition, a return value, a constant set or a comparison. Removing
  the identifiers from HEAD stops them spreading and does not unpublish
  them; they remain in this repository's published history, and the
  address is in the author metadata of every commit already on the
  remote. Two things arrived with the promotion and are recorded rather
  than smoothed. The new variable is documented in `CLAUDE.md`, which is
  the only place it CAN be documented because the body that introduced
  it is hash-pinned. And the 0.2.4 body's claim that an unset variable
  skips the shared tree is false once the snapshot repository exists,
  where it instead reports a snapshot it did not take; that is a kit
  defect, registered against the coordination level that owns the
  master, with the interim mitigation in `CLAUDE.md`
  (`.claude/`, `CLAUDE.md`, `README.md`, `tests/`; internal tooling, not
  a package surface).

  **The push-gate half of this promotion is superseded within the same
  release.** The entry above re-vendors the gate alone to 0.2.16 to
  close a fail-open the 0.2.4 body carried, so the gate this release
  ships is 0.2.16 and not the 0.2.4 described here. The other three
  artifacts of this bullet, the analyst charter, the snapshot tool and
  the skill wording, are still at 0.2.4. Both entries stay: this one
  records why the privacy promotion happened, the other why the gate
  moved again, and a reader arriving at either needs the pointer.
* The rule that machine-specific values never appear in a committed file
  stops being prose. A tier-1 guard now fails on an email address or a
  user-profile path in any TRACKED file, scanning `git ls-files` rather
  than Markdown and Python only, which is how the file that leaked sat
  outside every house-style guard by file type. The author's name is
  deliberately NOT guarded: it is published on purpose in `LICENSE`,
  `CITATION.cff`, `pyproject.toml`, the SRS and the guide, and guarding
  a string that is meant to be published would need an allow-list long
  enough to be its own defect. The guard carries its own falsification,
  asserting that it fires on both shapes and stays quiet on the
  impersonal forms the tree legitimately holds (a reserved
  documentation domain, a loopback address, a forge no-reply sender, and
  an action version pin, which is the mail shape without a dotted
  top-level domain). Separately, `tests/test_env_contract.py` now reads
  the vendored shell tools and the `COORD_` prefix, closing the two
  independent reasons a new machine variable stayed invisible to the
  guard built for exactly that (`tests/test_house_style.py`,
  `tests/test_env_contract.py`; internal tooling, not a package
  surface).
* SRS 1.2.0 to 1.3.0: the author's Phase 4 acceptance batch, landed in full.
  NFR-19 (result column-schema stability), NFR-20 (deprecation policy),
  NFR-22 (dependency version envelope, with the pre-1.0 pin form and
  the Python-ceiling propagation), NFR-23 (layering guard) and NFR-24
  (software jargon glossed) are added; two of them were sharpened by
  seat answers the same day, so NFR-20 now states as the author's own
  decision that within 0.x a break lands only in a MINOR release and a
  patch never changes the public surface, which is what lets a user
  write a version specifier against a 0.x package, and NFR-19 states
  that its column schema lives in the `results/tables.py` docstrings and
  that no rendered API reference is planned. AD-05, AD-06 and AD-07 are
  restated; the glossary gains the software terms NFR-24 requires.

    Phase 5 consolidation, same day: the batch is now written in full
    rather than in part. Twenty-six identifiers are added, covering the
    far-field ledgers (FR-38), the public exception hierarchy (FR-39),
    the options registry (FR-40), the ITACA adapter (FR-41), the
    reference-frame and sign conventions (FR-42), the console
    entry-point contract (FR-44), the strict manifest record (FR-45),
    the closed terminal-status set (FR-46), the probe-data export
    writers (FR-47), the public test-support assertions (FR-48),
    traceability closure (NFR-13), a confidentiality commit guard
    (NFR-14), manifest hash canonicalization (NFR-15), a coverage floor
    (NFR-16), one float-comparison convention (NFR-17), a manifest
    schema version (NFR-18), the support window (NFR-21), the
    optional-dependency error shape (NFR-25), and one term per level for
    the unit of work (NFR-26), plus the accepted splits of FR-02, FR-22,
    FR-30, FR-31, FR-33 and NFR-01 into singular claims that a single
    test can falsify. Ten requirements are reworded to say something
    checkable: FR-06 drops "no hidden logic" for a property of the
    emitted script, FR-08 names the attestation that verifies it rather
    than implying a test that cannot exist, FR-10 scopes "forever" to
    the external format and stops an unknown column being dropped
    silently, FR-11 replaces "lossless" with a reverse conversion, FR-20
    loses its status narration, FR-26 states its metric and that its
    bands are measured, FR-31 adds the per-version completeness
    confirmation, NFR-07 scopes reproducibility to the inputs and names
    the solver determinism boundary it does not control, and NFR-08
    defines "aggregated" as a line rather than a judgment.

    Two of her acceptances contradict each other and the SRS says so
    rather than silently picking one: FR-46 closes the terminal-status
    set at six values and FR-37 asks for a status the set does not
    contain as written. Resolved on 2026-08-03: the set stays closed at
    six and FR-37 is restated to ask for a status distinct from CONVERGED,
    which two of the six give.

    The
  user-facing consequences are in Deprecated below.

* The requirement set is published as a machine-readable index at
  `reports/requirements-index.json`, generated from `docs/srs` by
  `scripts/gen_requirements_index.py` and checked against it by a Tier 1
  test, carrying each requirement's id, statement and mandatory or
  deferred priority plus the two traceability counts (how many
  requirement ids any test cites, over the total). It exists because the
  external dashboard that consumes those numbers was maintaining them by
  hand and had fallen behind the SRS. New public page: the
  [acceptance mapping](https://nevesgeovana.github.io/pyflightstream/requirement-mapping/),
  which records which accepted item became which identifier, including
  the twenty-four that arrived without an identifier of their own.

### Deprecated

Keep a Changelog's sense of the word, soon-to-be removed, and NOT the
runtime-warning sense: nothing below emits a warning, because the
policy that would require one takes effect at 1.0 (SRS NFR-20). This
section is the notice, and for the removals it is the only one there
will be.

* **pandas and xarray leave the runtime dependencies at v0.5.0, and
  ITACA becomes a core dependency in their place** (SRS AD-06 and
  AD-07, the author's decision of 2026-07-27). Nothing changes in this
  release: both are still declared, still imported, and everything
  works exactly as it does today.

    What actually breaks at v0.5.0, stated in full rather than by its
    most visible case. The tabular layer (`results.tables`) stops
    returning pandas DataFrames. AND the far-field and plot-writer
    surface goes with it: `farfield` takes and returns
    `xarray.Dataset`/`DataArray` in the signatures of some fifteen
    public functions (`lattice_dataset`, `mass_closure`, `shaft_torque`,
    `azimuthal_harmonics` and the rest of the ledgers), and
    `post.writers` consumes those structures. A rotor or far-field user
    is affected as much as a table user.

    What survives: the column NAMES and their units are unchanged (SRS
    NFR-19); the container type is what changes. What to do if that is
    not your schedule: pin `pyflightstream<0.5` and stay on the
    pandas/xarray surface.

* **The tabular layer rename has LANDED**, so the forward notice that
  stood here is now a record rather than a warning. What it announced
  is in this release's API surface delta above; the notice as it was
  written stands unaltered in the v0.3.0 notes, which is where a reader
  looking for the warning they were given will find it.
* **Erratum to the 0.3.0 notes**, which said the ITACA data adapter
  "is declared as a pyflightstream `[itaca]` extra". It was not: no
  such extra was ever added to `pyproject.toml`, and none will be.
  ITACA arrives as a core, non-optional dependency instead (AD-07).
  A released entry is never rewritten, so that one carries a
  supersession note in place and the correction itself lives here,
  which is what this file already does for three 0.3.0 entries.

### Fixed

* **`pyfs-qa apply-compat` could not promote the first probe run of a
  newly registered FlightStream version**, which is the one run a
  version onboarding exists to produce. It rewrote an existing
  single-line version entry and refused when the command had none, but
  a version starts life recorded only in `commands/_meta.yaml`, so on
  its first run every judged command has no line to rewrite. The whole
  run was unpromotable, and the only route left was a hand edit, which
  invariant 3 forbids. It now inserts the entry at the version's release
  position among the lines already there. A command whose version block
  holds no single-line entry to pattern on is still refused loudly.
* **Two commands were emitted with no count-versus-list check at all,
  which the solver turns into a corrupted script rather than an error.**
  A command that declares how many indices follow makes the solver read
  that many tokens; a count disagreeing with its list therefore makes it
  consume the next command line as data. The check keyed on the
  argument's NAME against a hand-kept set, because the vendor spells the
  count differently per command, so `UNSTEADY_SOLVER_NEW_FORCE_PLOT`
  (count spelled `boundaries`) and `ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS`
  (spelled `num_index`) escaped it entirely: `boundaries=3` with two
  indices rendered without complaint.

  Both names join the set, and the class is closed rather than the two
  instances: a tier-1 guard now walks the whole database and fails on
  any integer argument that introduces a list from outside the known
  set, so the next new spelling fails the suite instead of shipping
  unchecked. Found while diffing the 26.121 manual; the second instance
  was found by the guard, not by reading.
* **The eight blocker findings of the independent review are fixed, and
  every release up to and including v0.3.0 carries all of them.** They
  are one class in eight places, which is why they are listed together:
  a step that reduced, rendered or resumed its input before validating
  it, and so produced a plausible result from data that could not
  support one. **None of them raised, warned, set a flag or returned a
  non-zero status**, so a user of 0.3.0 cannot tell the failing case
  from the correct one from the library's own output. Each fix is at
  the structural cause and carries a guard proven by mutation against
  the pre-fix body.

  * *Command injection through any string or path argument.* A newline
    inside an emitted argument became a line boundary, so the text
    after it became the next command while `raw_flag` stayed False, the
    flag whose only job is to record that a script holds something
    unvalidated. `comment()` had the same hole. Text arguments now
    refuse a line terminator (new `ScriptLineBreakError`, subclassing
    `CommandArgumentError`), `comment()` prefixes every physical line,
    and `emit()` re-checks the rendered block so a future argument type
    cannot reopen it. `Script.raw()` remains the sanctioned route for
    unvalidated text, and still sets the flag.
  * *A NaN residual published as CONVERGED.* `max(velocity, pressure)`
    was tested for NaN after the fact, but every comparison against NaN
    is False, so `max` returned the other column: a NaN pressure
    residual was swallowed and the point converged on a residual that
    is not the one that decided it. An infinite residual reported
    `COMPLETED_MAX_ITER`, a status asserting the solver merely ran out
    of iterations. Both are now `FAILED_DIVERGED`.
  * *Missing far-field samples became a physical reduction.*
    `plane_integral` inherited xarray's `skipna=True`, so an absent
    sample left the sum while its ring weight stayed in the geometry,
    shrinking flux, force, torque and energy in exact proportion to how
    much data was missing. It now propagates NaN, and the new
    `farfield.sample_coverage` reports the finite fraction so the
    result is diagnosable rather than merely opaque.
  * *A cross-check that could not fail.* The harmonic transverse-flux
    path summed azimuthal orders up to `n/2 - 1`, omitting Nyquist, so
    on the one signal class where the two documented-independent paths
    disagree the check returned zero. It now sums the true half-band
    with Nyquist counted once.
  * *`resume` corrupted the manifest it protects.* Inputs were staged
    before the already-recorded test, so a resume with nothing to do
    called the solver zero times and still replaced the staged input
    while the manifest kept the old hash. Pending points are now
    decided before anything is prepared, and a partial resume whose
    input changed is refused.
  * *Declared outputs could leave the run, and collisions destroyed
    data.* An output name such as `../outside.txt` skipped validation
    entirely and was then collected with a MOVE, taking a file the run
    did not own. Two outputs, or two staged inputs, sharing a base name
    silently overwrote each other while the manifest recorded both.
    Names are now contained, and every collision is refused before
    anything moves.
  * *Two sweep points could share one `run_id`.* Point tags format at
    one decimal, so alpha 1.01 and 1.04 collide; nothing refused it and
    the duplicate surfaced only when the second point tried to record,
    leaving a half-executed campaign. Ambiguous sweeps and duplicate
    `sim_id`s are refused at load. The tag format is deliberately
    unchanged: it is run identity and appears in every existing
    manifest.
  * *An all-NaN blade passed every structural check.* Each validator is
    a comparison, and NaN fails them all, so it satisfied
    increasing-radii, positive-chord, positive-stiffness and
    nonnegative-inertia at once. Non-finite values are now refused
    first. Separately, a resumed FSI `state.json` was validated for
    types but never for shape, so a run resumed on memory from a
    differently shaped blade; new `fsi.state.check_state_matches_config`
    refuses it.

  Incompatible by intent: input that used to be accepted and produce a
  wrong answer is now refused. If a campaign, blade configuration or
  recipe starts failing to load, the refusal names the value and what
  it would have produced.
* The author's given name no longer ships inside the wheel. It sat in
  the `reason:` field of `qa/references/PHY-06.yaml`, which is declared
  package data, so it travelled to every machine that installed the
  library. The field itself is kept, including the probe reports it
  cites, which are the provenance that makes the reference defensible;
  only the attribution is rewritten. The name stays where it is
  authorship rather than incident (`LICENSE`, `CITATION.cff`, `README`,
  the docs), and a tier-1 guard now scopes the refusal to `src/`.
* The role-review push gate no longer lets a release reach PyPI with no
  release attestation. Its release detection was a denylist of exact
  option spellings (`--tags`, `--follow-tags`) plus a version-tag
  pattern that did not accept the `refs/tags/vX` form, so
  `git push --follow-tag origin main` (git accepts any unambiguous
  option prefix) and `git push origin HEAD:refs/tags/vX` both cleared as
  ordinary branch pushes and, with the branch already pushed and
  review-attested, shipped the tag with no release attestation into the
  live trusted-publishing workflow. The hardened gate and multi-ref
  attestation writer were promoted from the sister library as one
  matched change: option handling is now a fail-closed allowlist that
  denies any leading-dash token it cannot prove ref-neutral, release
  classification reads both sides of a refspec, push scope is resolved
  per ref (and per the remote the command would actually use), the
  repository identity for the incident query comes from
  `pyproject.toml` rather than the checkout folder, and
  `write_attestation.py` validates the pass names and covers every named
  ref in one run so a branch-and-tag release is attestable. Both
  original inputs were reproduced allowing against the pre-port gate and
  denying against the ported gate. `tests/test_push_gate.py` grows to
  the sister library's end-to-end case set and a new
  `tests/test_write_attestation.py` pins the writer. Incident
  INC-20260724-0839-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* The push gate no longer falsely blocks a commit whose message is a
  heredoc that mentions a push. The gate's `_strip_heredocs`, which is
  meant to drop heredoc bodies before tokenizing, carried a stray
  U+0001 control byte at the end of its opener regex (invisible in an
  editor), so the pattern matched nothing, the stripper was dead, and
  the body was tokenized: a routine `git commit` documenting a push was
  denied. The byte is removed and a test pins all three delimiter
  forms. Same control-byte class as INC-20260724-0410-shared. Incident
  INC-20260724-0912-pyflightstream (`.claude/` hooks; internal tooling,
  not a package surface).
* A settings preset written in the solver's own words no longer fails
  to convert, and the same words can no longer invert a run in silence.
  `viscous_coupling = 'DISABLE'` in a settings file was refused with a
  bool-parsing message that named neither the vocabulary nor the
  translation; passing the same string to `solver_settings` emitted
  `ENABLE`, because a non-empty Python string is truthy and the toggle
  renderer only tested truthiness. Both directions of the vocabulary now
  live in one place (`script.toggles.resolve_toggle`), the helpers read their
  toggles before the first emission, and a word in neither vocabulary is
  refused naming the helper and the argument. Every release up to and
  including v0.3.0 is affected: a toggle passed as `'DISABLE'` emitted
  ENABLE, and the solver-setup snapshot recorded the inverted value as
  if it had been chosen. Runs whose recipes passed Python booleans are
  unaffected; to check an archived campaign, read the toggle lines of
  the rendered scripts under the managed simulation folders, or the
  `solver_setup` block of `runs.json`. Incident
  INC-20260723-2027-pyflightstream (feedback channel item 2, PLN-074).
* A swept case no longer loses the evidence of every point but the
  last. All points of a case run in the same simulation folder and are
  collected into `raw/` under their own names, so a declared output
  without the `{point}` placeholder was written, collected, and
  overwritten once per point, while the manifest listed the surviving
  file for all of them. The campaign loop now renders every point's
  output names before running the case and blocks it when two points
  would write the same one, so the check judges the actual collision
  rather than the presence of a particular placeholder (any template
  that distinguishes the points passes, and `{mach}`, which does not,
  is caught). The campaign example and the guide teach
  `outputs = ["loads_{point}.txt"]` with the recipe exporting
  `case.outputs[0]`, and `LoadsAssessor()` finds the loads table by
  content, so per-point evidence and convergence judgment are no longer
  exclusive. Incident INC-20260723-2113-pyflightstream.
* The user guide's flagship campaign listing imported `LoadsAssessor`
  from `pyflightstream.results`, where it does not exist; the guard
  below now checks every `from pyflightstream... import ...` line the
  guide teaches.
* The user guide taught `case.staged_geometry`, which `SimCase` never
  had: the campaign loop stages the geometry and rewrites
  `case.geometry`. A reader copying the campaign recipe got an
  `AttributeError` on their first point. Both occurrences corrected, and
  `tests/test_guide_api_names.py` now asserts that every `case.`,
  `helpers.` and `script.` name the guide teaches exists, and that every
  import line it shows resolves, so an unexecutable sample cannot ship
  again. Incident INC-20260723-2041-pyflightstream (PLN-084).
* `solver_settings(vorticity_drag_boundaries=...)` is optional again,
  and the guard that made it mandatory in v0.3.0 is gone: it stated the
  inverse of the manual page it cited. Boundaries left off the vorticity
  CDi list use the solver's surface pressure integration, a complete
  induced-drag calculation; the zero-drag pitfall happens the other way
  around, to a bluff body without a user-defined trailing edge that is
  put *on* the list, which also made the guard's suggested remedy
  (`"all"`) the very trap it claimed to prevent (SRC-003 p.202).
  Omitting the argument now emits no selection command and the
  solver-setup snapshot records the flag as a `default` with an empty
  selection and the citation, so the manifest still says which
  boundaries used vorticity integration (none). An empty sequence is
  refused (the same refusal now guards the deprecated `analysis_setup`
  keyword) with a message pointing at the omission that means the
  solver default. This restores the pre-v0.3.0 reproduction path (a
  legacy setup that never sets the list), which the guard had broken.
  The documentation carrying the inverted claim moved with it: the
  helper docstrings, the user guide (including the pitfalls slide),
  SRS FR-22 and its revision history, the command-database note, the
  examples, and the api-designer reviewer charter, which cited the
  guard as a didactic precedent (PLN-075).
* The deprecated `analysis_setup(vorticity_drag_boundaries=...)` no
  longer leaves the solver-setup snapshot describing a script that was
  never built: it now restamps the induced-drag record it overrides,
  records resolved boundary indices like the settings path rather than
  raw labels, and resolves and emits before touching the snapshot, so a
  bad label leaves the script, the deferred selection, and the record
  untouched. The corrected snapshot is `script.solver_setup`; a
  snapshot returned by an earlier `solver_settings` call is frozen at
  its own state. `Script` declares `solver_setup` and its induced-drag
  state as real attributes instead of carrying them as patched-on
  names.
* CI lint stage restored to green: the `ruff` dev dependency is pinned
  to `0.15.22` (matching the pre-commit hook) and Markdown files are
  excluded from ruff via `extend-exclude`. An unpinned ruff had begun
  reformatting the Python code samples inside `fsi/README.md` (an
  illustrative developer README, not a `.py` source the formatter
  owns), failing `ruff format --check`. The pin restores the known-good
  formatter and keeps CI, the hook, and developer machines identical;
  the `*.md` exclude makes the formatter's scope version-independent for
  any later ruff (PLN-024).
* Role-review gate before lane D caught residual user-guide staleness
  the v0.3.0 refresh missed: the Tier 2 pitfalls slide still listed
  `NEW_SURFACE_SECTION_DISTRIBUTION` as broken (it was promoted to
  verified in the licensed session), the install slide said "not yet
  on PyPI", the runtime-dependency list omitted xarray, and `post`
  and `fsi` were called reserved seams though both shipped; all
  corrected. The `NEW_SURFACE_SECTION_DISTRIBUTION` database note
  dropped its pending-re-probe language now that the re-probe decided,
  the `campaign_matrix` example's licensed `run_campaign` call names
  the required `assess`, and the `[plot]` extra records its
  matplotlib license note.
* Post-release front-page currency: README and the docs home announce
  v0.3.0 as public (they lagged at v0.2.0), the SRS roadmap moves the
  v0.3.0 release to Delivered, the standards page moves the Sybil
  executable-examples row to Adopted, the README DOI badge points at
  the Zenodo concept DOI, the CHANGELOG gains its `[Unreleased]` and
  `[0.3.0]` link references, and the user guide architecture labels
  use `workspace` (not the deprecated `files`).

## [0.3.0] - 2026-07-23

The v0.3.0 line: the usage-feedback workstreams (PLN-022) triaged from
the author's first outside-the-repo use of 0.2.0, delivered 2026-07-22,
plus the protocol and library-review adoptions of the ultraplan week.

### API surface delta

* New public names: the `workspace` package (renamed from `files`);
  `options` (plus top-level `get_option`, `set_option`,
  `reset_option`, `describe_option`, `option_context`); `exceptions`
  (the 25-class catalog); `testing` (`assert_records_close`,
  `assert_scripts_equal`); `overview()`; `solver_settings`,
  `SolverSetup`, `script_from_setup`; `cases.matrix` (`MatrixError`,
  `MatrixRow`, `resolve_matrix`, `plan_matrix`, `run_matrix`,
  `convert_matrix`, `to_campaign`); the pandas tables (`to_dataframe`,
  `to_csv`, `run_frame`, `sweep_frame`); `reference.CONVENTIONS`;
  `EntityRegistry`; the `pyfs-workspace` and `pyfs-matrix` CLIs.
* Incompatible changes: `solver_settings` requires
  `vorticity_drag_boundaries` (superseded: the requirement rested on a
  misread of SRC-003 p.202 and was removed, see Unreleased); the
  behavior selectors of `help`, `overview`, `run_campaign`,
  `register_option`, and `read_matrix` are keyword-only;
  `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` are renamed (import shims kept
  through v0.4.0); converted campaigns carry `matrix_*` variable keys
  (were `legacy_*`).
* Deprecations: `pyflightstream.files` and
  `pyflightstream.cases.matrix_legacy` (removal v0.4.0,
  deadline-guarded); the `analysis_setup(vorticity_drag_boundaries=...)`
  path toward `solver_settings`.
* Removed: none (the `Legacy*` names survive as shim aliases).

Known gaps named for the next window: the formal `verified`
promotions of the version-sensitive commands (PLN-015) and the
aeroelastic family (PLN-019), and the unsteady-chapter backfill of
PHY-05/06 across versions.

### Added

* `workspace` package (renamed from `files`): the campaign workspace
  now organizes inputs as well as outputs, with a declarative
  input-artifact library under `inputs/` (references, solver-setup
  presets, boundary groups, geometries, profiles, and an executables
  registry by build id with an explicit-override rule), output naming
  templates (`NamingTemplate`, output-only by design: the manifest
  stays the sole identity authority and no parse-back API exists),
  `CampaignWorkspace.init()` behind the new `pyfs-workspace` CLI,
  campaign pre-flight (`plan_campaign`, zero solver time), and
  resumable incremental sweeps (`run_campaign(resume=True)`).
* Entity label registry in the script builder: frames, actuators,
  motions, and boundaries can carry user labels; every entity-citing
  argument accepts index or label; `declare_existing` accepts named
  boundary inventories; boundary range checks apply once declared.
* Solver-setup provenance: `solver_settings` becomes the single entry
  point for all 28 commands of the runtime, solver, and advanced
  settings families and returns a `SolverSetup` snapshot recording
  every flag's effective value with provenance (explicit,
  evidence-backed default, or unknown, never guessed); the snapshot
  rides the run manifest and `script_from_setup` regenerates the
  script from it.
* Tabular results layer on pandas: `to_dataframe`/`to_csv` for every
  parser, `run_frame` (one wide row per run), and `sweep_frame` (the
  whole sweep from the manifest).
* The run matrix as a first-class interface: `resolve_matrix`,
  `plan_matrix`, and `run_matrix` bind the matrix columns to the
  workspace input library; new `pyfs-matrix` CLI (convert, plan);
  the matrix fixture grows to eight rows.
* Two-level help: `pyflightstream.overview()` renders the
  architecture from the live module docstrings (docs Architecture
  page from the same source), and the command reference gains a
  manual-coverage section with explicit gap notes.
* `pyfs-qa cases`: the Tier 3 physics registry printed as a numbered
  test matrix.
* Command schema: optional evidence-cited default metadata.
* Deprecation ledger (`pyflightstream._deprecations`): every shim's
  removal promise recorded as a concrete version, with a Tier 1
  deadline guard that fails the suite when a shim survives past its
  recorded removal version or its warning stops citing it. Both live
  shims (`files`, `cases.matrix_legacy`) are registered with removal
  at v0.4.0, and their warnings now state that exact version instead
  of "a future minor release".
* `pyflightstream.options`: the declared-knob registry in the pandas
  `register_option` model (D1 adoption), with per-key validators,
  `option_context`, and `describe_option`. Keys are exact by design
  (never pattern-matched) and refusals follow the openmdao message
  contract (unknown keys list every registered key; rejected values
  name the option, the value, and the accepted form). First
  registered knobs: `qa.scratch_root`, `qa.probe_timeout_s`,
  `qa.case_timeout_s`; the `pyfs-qa` CLI scratch and timeout defaults
  now read from them. `get_option`, `set_option`, `reset_option`,
  `describe_option`, and `option_context` are re-exported at the
  package top level (pandas-style access); path options accept
  `pathlib.Path`.
* The public import surface is now affirmed by test (scipy
  `_public_api` model): `tests/test_public_api.py` declares every
  public module; a new module must join the list consciously or carry
  a leading underscore, deprecated modules are documented by the
  ledger alone, and every public module must import cleanly (or
  refuse with the install remedy) and carry its pipeline docstring.
  Lazy loading deliberately not adopted (D3 resolution).
* Tier 1 wording pins for the main didactic refusals
  (`tests/test_error_messages.py`, xarray pattern): versions,
  `solver_settings` (mandatory vorticity selection with the
  zero-induced-drag cause, mode regime, unsteady time stepping),
  workspace input library (id model, empty-library remedy, available
  ids listing), and the run-matrix reader (verified codes and layout).
  A refactor that keeps the exception type but drops the explanation
  now fails the suite. The mandatory-selection pin is superseded in
  Unreleased by the empty-selection refusal (SRC-003 p.202).
* `pyflightstream.exceptions`: single public catalog of all 25
  exception and warning classes (pandas errors model); completeness
  is test-asserted mechanically, so a new exception class must join
  the catalog in its defining commit. Structured refusals:
  `UnknownVersionError` now carries `version` and `known`,
  `InputArtifactError` carries `kind`, `artifact_id`, and
  `available`, so callers react without parsing messages.
* `pyflightstream.testing`: public assertions with quantified
  violation reports under the golden philosophy split;
  `assert_records_close` (count, violating keys, worst offender) and
  `assert_scripts_equal` (first differing line, total differing
  count, exact by policy).
* House conventions get a single home: `reference.CONVENTIONS`
  (naming, unit suffixes, keyword-only selectors, refusal style)
  rendered by `pyflightstream.help()` with a tier 1 adherence audit
  (`tests/test_conventions.py`) sweeping the code against the
  mechanical rules.
* Test-isolation hygiene: an autouse fixture snapshots every
  module-level registry and cached mutable default (physics and SMI
  cases, probe specs, derived flag map, sweep codes, entity nouns,
  the cached command database and manual-edition map) before each
  test and restores it after, so a mutating test cannot leak state;
  the inventory lives in one place in `tests/conftest.py` and the
  mechanism is itself tested.

### Changed

* `solver_settings` now requires `vorticity_drag_boundaries`
  (breaking; forgetting the selection silently zeroes the
  induced-drag accounting. Superseded: that rationale states the
  inverse of SRC-003 p.202, the requirement was removed in Unreleased,
  and boundaries left off the list keep the solver's surface pressure
  integration) and emits `SOLVER_MINIMUM_CP -100` by
  default when the flag is not passed, retiring the earlier
  reference-velocity workaround for rotor Cp clipping (override by
  passing the parameter). The PHY references were re-validated under
  the emitted default on a licensed 26.120 machine (build 7012026):
  all 30 metrics reproduce bit-identically, so no reference value
  changed (report
  `reports/physics/PHY-26120_2026-07-23_reseed-cp100-2026-07-23.md`).
* The run-matrix vocabulary drops the word "legacy" everywhere users
  see it: `LegacyMatrixError` and `LegacyRow` are renamed
  `MatrixError` and `MatrixRow`, and `to_campaign`/`convert_matrix`
  now preserve the matrix codes as `matrix_*` case variables
  (previously `legacy_*`; campaign files converted earlier keep their
  old keys and stay loadable, test-pinned). `read_matrix` makes
  `active_only` keyword-only, matching the rest of the module.
* Behavior-selecting arguments are keyword-only where the naming
  conventions already claim it (breaking, inside the unreleased v0.3
  window): `help(version, *, path, open_browser)`,
  `overview(*, path, open_browser)`, `run_campaign(campaign,
  executor, workspace, *, assess, recipes, resume)`, and
  `register_option(key, *, default, doc, validator)`. Positional
  calls to these selectors now raise `TypeError`.
* The motivation narrative (README, docs home, SRS introduction, user
  guide) now frames version drift as the natural counterpart of an
  actively developed solver whose team is responsive and consolidates
  user requests through intermediate hotfix builds into stable
  releases, instead of reading as criticism of the changelog; the
  documented facts and citations are unchanged.
* The docs toolchain migrated from MkDocs to ProperDocs, the
  maintained fork (license evidence RPT-009), after a green test:
  drop-in at the config and CLI level, with strict build and an
  identical page set and content on the same sources. The config
  file is renamed `properdocs.yml`, CI builds with
  `properdocs build --strict`, and the `[dev]` extra gains
  `properdocs` (the material theme and the nav plugins keep their
  mkdocs package names during the ecosystem transition; the build
  hook now imports from the `properdocs` namespace).

### Deprecated

* `pyflightstream.files`, in favor of `pyflightstream.workspace`: the
  shim re-exports everything with a DeprecationWarning until its
  recorded removal at v0.4.0 (deprecation ledger, deadline-guarded).
  The `analysis_setup(vorticity_drag_boundaries=...)` path is
  deprecated toward `solver_settings`.
* `pyflightstream.cases.matrix_legacy`, in favor of
  `pyflightstream.cases.matrix`: the shim re-exports everything until
  its recorded removal at v0.4.0 (deprecation ledger,
  deadline-guarded), keeping `LegacyMatrixError` and `LegacyRow` as
  aliases of the renamed classes. Both shims attribute their
  DeprecationWarning to the importing line on Python 3.12+, so plain
  script runs see it too.

### Fixed

* `__version__` now derives from the installed metadata (the
  published 0.2.0 wheel answered `0.0.1.dev0`), and the package
  docstring no longer describes the M0 skeleton.
* The public documentation caught up with the code after a full
  staleness audit: README rewritten to the released state, docs home
  updated, all three examples rendered on the site, CONTRIBUTING
  setup corrected.
* `pyflightstream.exceptions` now imports on a base install without
  the `[fsi]` extra: `StaleLoadsError` moved to `pyflightstream.fsi.state`
  (still re-exported by `fsi.driver`) so the catalog no longer pulls
  PyNite through the FSI modules on import.

### Evidence (licensed 26.1x session, 2026-07-23)

* `NEW_SURFACE_SECTION_DISTRIBUTION` moves broken to verified on
  26.120: the phase and `INCLUDE_SYMMETRY` grammar correction is
  confirmed by a re-probe (`CMP-26120_2026-07-23_pln012`);
  `AIR_ALTITUDE`, `SET_MOTION_START_TIME`, and
  `NEW_OFF_BODY_STREAMLINE` are re-confirmed broken.
* The bulk-separation spelling is resolved (`RPT-012`): the 26.100
  solver accepts `CREATE_BULK_SEPARATION` and rejects the manual
  sample-block spelling `CREARE` as unrecognized, so the database
  keeps the header spelling and no alias is added.
* Two research findings backing future features: `EXPORT_SURFACE_MESH`
  OBJ writes one named object block per boundary from the source mesh
  solid name (`RPT-010`, a fsm-to-obj boundary inspector is feasible),
  and the settings-and-status export exposes only the steady-mode
  default, not the wake and viscous toggles (`RPT-011`, their
  provenance stays honestly unknown).

### Added (documentation and process)

* Executable documentation examples in CI (Sybil): the docstring
  doctests and the python code blocks in the root README and `docs/`
  run as a CI step with warnings promoted to errors, so a stale
  example fails the build; `sybil` joins the `[dev]` extra. Three
  path-scoped Sybils leave the default `pytest` run untouched;
  CONTRIBUTING documents the local command. The README quickstart and
  the four example blocks execute green on 3.11 and 3.12.
* The user guide (`guide/`) is refreshed to the v0.3 surface
  (PLN-030): version 0.3.0, sixteen curated helpers (with
  `start_solver` and `coordinate_frame`), 144 commands, the current
  26.120 evidence counts, the `workspace` import path, and a
  four-tool command-line cheat sheet (`pyfs-qa` including `cases`,
  `pyfs-workspace`, `pyfs-matrix`, `pyfs-fsi`).
* New worked example `examples/campaign_matrix.py` (rendered on the
  docs site): the campaign side end to end without a license, run
  matrix to `campaign.toml` to a zero-solver `plan_campaign`
  pre-flight reporting the ready sweep points.
* Mesh inputs and GUI-only operations policy page in the docs
  (PLN-028): the supported GUI-once-then-script workflow when a step
  has no scripting command, the two canonical mesh input routes
  (geometry meshed inside FlightStream carried as a saved `.fsm`
  artifact, or a direct OBJ mesh), and the mesh format policy (OBJ
  as the reference format; further formats only ever behind a
  project-owned adapter).
* The Software Requirements Specification is published as a living
  document in the docs (`docs/srs/`): founding requirements with
  implementation statuses, the usage-feedback requirements, explicit
  non-requirements, architectural rules, standards alignment with
  verified references, and the roadmap.
* Documentation-currency policy (SRS NFR-11) with Tier 1 guards:
  version-bearing metadata files must agree, the changelog always
  carries its Unreleased section, SRS requirement ids never repeat.
* CONTRIBUTING discloses the AI-assisted development model and the
  process safeguards around it (evidence discipline, role-based
  review, the author's non-delegable seats, the clean-room rule
  extended to the AI), per the pyOpenSci disclosure item.
* README opens with status badges and a runnable quickstart snippet
  (validated build plus the didactic version refusal), and its
  feature list caught up with the cycle (options registry, exceptions
  catalog, testing assertions); live counts now stay with the
  generated compatibility matrix instead of hardcoded prose.
* Published package metadata completed per the PyPA well-known
  guidance (audit 2026-07-23): trove classifiers (beta status,
  science audience, Python versions, physics topic) and the
  Documentation, Changelog, and Issues project URLs join the
  Repository link.
* The documentation site is published to GitHub Pages on every push
  to main (`nevesgeovana.github.io/pyflightstream`), so the generated
  command reference, compatibility matrix, and architecture pages are
  reachable without a local build. The unused `mkdocstrings[python]`
  dev dependency was dropped (it was never wired into the build; the
  offline `help()` and `overview()` remain the docstring surface).
* Repository top level reduced to the public essentials: the
  author's session records left Git versioning (history preserved),
  and a `deprecated/` folder now groups discontinued public items.
* Role-based review process: five reviewer charters in
  `.claude/agents/` (architect, QA engineer, V&V engineer, technical
  writer, API designer) and the `role-review` skill that runs the
  applicable passes on a work item's diff before it closes, per the
  team-role model adopted 2026-07-23; the definition of done cites
  the passes, the author keeps the non-delegable seats (product
  owner, domain expert, numerical analyst), and the standards
  alignment chapter records the model's public anchors.
* Co-development with the sister library ITACA (AD-07): the two
  libraries may generate requirements for each other, the docs gain
  the sister library page describing the division of labor and the
  cross-requirement convention, and the future data adapter is
  declared as a pyflightstream `[itaca]` extra (superseded: no such
  extra was ever added to `pyproject.toml` and none will be; ITACA
  arrives as a core dependency, see Unreleased) (ITACA stays
  solver-agnostic and never imports this package).

## [0.2.0] - 2026-07-22

First public release (PyPI and Zenodo). Milestones M6 (FSI) and M7
(far-field probes) landed between the tags, together with the Tier 3
matrix growth and a round of solver findings, every one backed by a
committed report.

### Added

* `fsi` subpackage (optional `[fsi]` extra, PyNiteFEA): validated
  `FsiConfig` with canonical hashing; sectional loads parser with the
  SI assertion, family-per-blade attribution with geometric
  cross-checks, and the pitch-axis to elastic-axis moment transfer;
  PyNite beam of the (w, theta) blade with exact massless-DOF
  condensation and clamped-beam benchmarks; centrifugal terms
  (tension through P-Delta, propeller moment with inner twist
  iteration) with the Campbell/Southwell verification; twist encoded
  as three-node differential translations with the exact inverse;
  node file, ordering map, and FSIDisp writer/reader from one
  generator, embedding sections at the local blade angle on spinning
  blades; four-phase coupling driver (wake, averaged relaxed
  coupling, convergence watch, unrelaxed recording) with atomic
  state, per-call freshness assertions, frozen replay mode, and a
  hash-carrying convergence log; `pyfs-fsi` executable dispatching
  between the coupled driver and the interface-evidence dummy.
* `probes` and `farfield` (far-field extraction line): serializable
  cylindrical lattice with version-aware emission; planar Cartesian
  probe grids on explicit frames with element-size and
  cosine/geometric distributions; geometry gate (optional `[geom]`
  extra) with containment culling, boundary-layer band refinement,
  and a wall standoff margin; single quadrature, azimuthal FFT
  harmonic spine, and the conservation ledgers with the synthetic G0
  gate in Tier 1; probe-export parser with the row-order contract
  check; `run.export_surface_mesh` pre-processing; `post` VTK and
  Tecplot probe-data writers.
* `qa`: PHY-05 (generic-blade unsteady periodic propeller) and
  PHY-06 (steady-versus-unsteady polar trend, 16 metrics) in the
  Tier 3 matrix with a per-version evidence gate; the `BladeSpec`
  generic propeller blade generator (public analytic shape laws).
* Command database grown from 116 to 144 entries: motion, unsteady
  solver, scenes, and advanced-settings backfill from the
  case-reproduction run; the mesh-import family; the Aeroelastic Coupling
  Toolbox family; per-version argument grammars
  (`versions.<v>.args`) with hotfix inheritance for the 26.1/26.12
  manual delta.
* Examples: FSI Campbell diagram and the wing static deflection
  worked cases; the beamer user guide source under `guide/`.

### Changed

* Two emission phases corrected on reproduction evidence
  (`SET_ANALYSIS_SYMMETRY_LOADS` and
  `NEW_SURFACE_SECTION_DISTRIBUTION` are in-solve consumers and
  precede `START_SOLVER`).
* `xarray` promoted to a runtime dependency (the far-field ledgers
  live on labeled arrays).

### Evidence

* FSI interface established on 26.120 build 7012026
  (`reports/RPT-005` to `RPT-007`): the implemented scripting
  interface is the Aeroelastic Coupling Toolbox family (the manual's
  `SET_MOTION_FSI` pair is unrecognized, candidate broken); the
  sectional loads export carries line densities and a three-decimal
  time-increment header (both folded back as code); the coupled loop
  ran 54/54 and 90/90 calls with the full phase machine and frozen
  replay reproducing held deformations to 5e-6.
* Probe round trip on 26.120 (`reports/RPT-004`): imported probe
  count and row order preserved exactly; boundary-layer export
  columns are geometric (erratum), motivating the standoff margin.
* PHY-05 bit-identical to its shareable-case baseline; PHY-06 polar
  trend 16 pass with monotonic steady-versus-unsteady deltas.

### Known limitations

* Two-way rotor FSI is blocked on FlightStream 26.120 build 7012026:
  the solver silently does not apply `FSIDisp.txt` morphing to
  boundaries attached to a rotary motion, while a motionless boundary
  morphs correctly with the same command sequence
  (`reports/RPT-007`; vendor report prepared). The coupling loop
  mechanics, the structural side, and the motionless path are fully
  functional.

## [0.1.0] - 2026-07-21

First tagged release, private phase. Everything below landed between
the repository seeding and this tag (milestones M0 through M5).

### Added

* `versions`: canonical 26.XXX version scheme with the ordered
  registry in `commands/_meta.yaml` as the only ordering authority;
  display aliases; registered manual editions (SRC-003 for 26.120,
  SRC-725 for 26.100).
* `commands`: version-aware command database, 116 commands drafted
  from the manual with a page citation each, typed argument
  specifications, script layout grammars, emission phases, and
  per-version evidence statuses (documented, verified, broken,
  removed) enforced at load time; hotfix builds inherit their base
  release record.
* `script`: builder with validating emit against the per-version
  database view, phase ordering, five layout renderers, and curated
  workflow helpers with a cross-reference ledger.
* `files` and `run`: managed campaign workspace with staging hashes
  and an append-only run manifest; local headless executor using the
  documented `-hidden --script` invocation.
* `cases`: SIM campaign model with TOML loading, recipe registry,
  campaign loop with six run statuses, and the pipe-delimited
  15-column run-matrix reader with lossless code preservation and
  TOML round-trip conversion.
* `results`: loads and residual-history parsers with sanitized
  fixtures from real 26.120 output; version cross-check recording the
  solver-reported version and build verbatim.
* `qa`: three-tier evidence harness. Tier 2 probe suite (109 specs)
  with committed compat reports and status promotion only through
  `pyfs-qa apply-compat`; Tier 3 physics regression matrix (PHY-01
  wing polar, PHY-02 symmetry equivalence) against banded references,
  plus the cross-version drift suite with the local-only SMI class
  behind an explicit `--smi-root`; `pyfs-qa` CLI with probe,
  apply-compat, physics, drift, and update-reference.
* `reference`: single rendering source for the command reference.
  `pyflightstream.help()` writes a self-contained HTML page offline;
  the mkdocs site renders the same database into a per-chapter
  command reference and a version compatibility matrix at build time
  (nothing generated is committed).
* Docs site (mkdocs-material, strict): generated reference and
  matrix, evidence-discipline overview, and the steady polar example
  rendered from its percent-format source.
* `examples/steady_polar.py`: synthetic NACA 0012 wing, one
  version-validated script per angle, the didactic refusal for a
  version without evidence, optional solver execution behind an
  explicit executable path; executed on 26.120 build 7012026 with
  lift slope 4.83 per rad against the finite-wing anchor 5.03.

### Evidence

* 26.120 (build 7012026): 64 commands verified, 4 broken, full
  physics matrix 10 pass (`reports/compat/CMP-26120_2026-07-21_full`,
  `reports/physics/PHY-26120_2026-07-21_full`).
* 26.100 (build 5012026): 28 commands documented from the 26.1 manual
  (SRC-725), one removal; first real cross-version drift 17 pass
  1 warn (`reports/physics/DRF-26100-26120_2026-07-21_complete`); the
  warn triaged as a deterministic solver change between builds
  (`reports/physics/TRI-SMI01-CMy_2026-07-21`).
* 26.000: registered, no recorded evidence yet (honest empty column;
  backfill planned for v0.2+).

[Unreleased]: https://github.com/nevesgeovana/pyflightstream/compare/v0.8.1...HEAD
[0.8.1]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.8.1
[0.8.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.8.0
[0.7.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.7.0
[0.6.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.6.0
[0.5.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.5.0
[0.4.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.4.0
[0.3.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.3.0
[0.2.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.2.0
[0.1.0]: https://github.com/nevesgeovana/pyflightstream/releases/tag/v0.1.0
