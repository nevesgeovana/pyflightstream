# RPT-028: the independent review findings, transcribed (2026-08-18)

Two independent reviews of this repository published finding
identifiers, and the code and tests cite them. `PYFS-nnn` comes from
REV-002, the current-state review of 2026-07-28; `REV010-nnn` comes from
REV-010, the review of the pushed commit of 2026-08-03. Both review
documents are held outside this repository and one of them is not in
English, so neither can be a target a reader here can open.

Until this report existed, 41 distinct identifiers were cited in `src/`
or `tests/` and exactly one of them, `PYFS-025`, was named anywhere
under `reports/`, in a sentence rather than a heading. Every other
citation sent a reader out of the repository, and one read-only survey
concluded from that dead end that the findings could not be worked. This
report is the target those citations resolve to, and
`tests/test_review_citations.py` is the tier-1 walk that keeps them
resolving: it collects every identifier of both series appearing under
`src/` and `tests/`, requires each to be named in a heading of a report
under `reports/`, and refuses when it collects nothing at all.

## What this report is, and what it is not

It is a paraphrase, one heading per finding, carrying three things: the
finding's statement in English, the severity the review published for
it, and the files in this repository that cite the identifier as of
2026-08-18. It is not the review documents. No sentence of either review
is reproduced; REV-002 is written in Portuguese and every statement
below is this repository's own English wording of what the finding says.

The severity vocabulary is the reviews' own, translated where it was not
in English: Blocker, High, Medium, and one Low to medium. Severity is
the reviewer's published judgment at the time of the review and is left
exactly as published, including where this repository later disagreed
with the priority or answered the finding in a different way than the
review proposed.

The citing files are a measurement of this tree on 2026-08-18, not a
promise about the future. A finding whose entry says nothing cites it
had no site under `src/` or `tests/` on that date. Line numbers are
deliberately absent: they rot, and the identifier is greppable.

What this report deliberately does NOT claim, per finding, is a
disposition. Whether a finding is closed is a question about the code,
and the honest answer to it is the guard that stands where the citation
is, not a word in a report. Where the citing sites are guards, they are
named below and a reader can open them.

## REV-002, 2026-07-28: 26 findings

### PYFS-001 (Blocker): a line break injects commands through the validated path

A string argument was type-checked and returned unexamined, rendering
was `str(value)`, and the script joins its lines with a newline, so a
newline inside an argument added solver commands through the validated
emission path without setting the raw provenance flag that exists to
mark unvalidated content.

Cited in `tests/test_script.py`.

### PYFS-002 (High): commands known to be broken are emitted with no refusal or warning

A command a probe had measured as broken on the target build was emitted
like any other, so a campaign could be built on a command the solver
does not honor with nothing said at build time and nothing recorded for
the reader of the run.

Cited in `src/pyflightstream/run/__init__.py`,
`tests/test_run_campaign.py`, `tests/test_script.py`,
`tests/test_script_helpers.py`.

### PYFS-003 (Blocker): two sweep points collide on one run identifier

The point tag formats at one decimal, so two sweep points whose values
differ in the second decimal produced the same tag, and the tag ends the
run identifier. Two points of one case then shared one manifest
identity, and nothing refused the sweep: the pre-flight reported both
points ready under the same identifier.

Cited in `src/pyflightstream/cases/__init__.py`, `tests/test_cases.py`.

### PYFS-004 (Blocker): a resumed campaign rewrites the inputs of runs it then skips

Preparation is not read-only: staging copies the input files. Deciding
which points still needed running AFTER preparing the case meant a
resume with nothing left to do still replaced the staged input while the
manifest kept the digest of the old one.

Cited in `src/pyflightstream/run/__init__.py`,
`tests/test_run_campaign.py`.

### PYFS-005 (Blocker): outputs escape the workspace and collapse onto one name

Output paths were not confined to the workspace and inputs and outputs
were distinguished by basename alone, so one point of a run could
overwrite another's output while the record listed both complete. The
same class reappears wherever a writer ends in an unconditional write.

Cited in `src/pyflightstream/post/writers.py`,
`src/pyflightstream/workspace/__init__.py`,
`src/pyflightstream/workspace/naming.py`,
`tests/test_silent_overwrites.py`, `tests/test_workspace.py`.

### PYFS-006 (High): the working folder is not immutable evidence for one run

Every point of a case runs in the same simulation folder, and collection
asked only whether the declared output existed, never whether this run
produced it. A file left there by anything else was collected as this
point's evidence, and the point could be published as converged from a
solver that wrote nothing at all.

Cited in `src/pyflightstream/run/__init__.py`,
`src/pyflightstream/workspace/__init__.py`,
`tests/test_run_campaign.py`, `tests/test_workspace.py`.

### PYFS-007 (Blocker): a residual that is not a number is classified as converged

The worst residual was taken as the maximum of two components and only
then tested for being a number. Every comparison against a
not-a-number value is false, so the maximum returns its first argument
and a run whose pressure residual was unusable was assessed on the
velocity residual alone.

Cited in `src/pyflightstream/run/__init__.py`,
`tests/test_run_campaign.py`.

### PYFS-008 (High): early termination and non-convergence carry unsafe semantics

A solver that stopped before its iteration limit was read as having been
stopped by the convergence threshold, including in the case where the
run had forced all iterations and that threshold was therefore disabled.
The one mechanism that could legitimately have ended the loop was off,
and the stop was still recorded as a success.

Cited in `src/pyflightstream/run/__init__.py`, `tests/test_results.py`,
`tests/test_run_campaign.py`.

### PYFS-009 (High): parsers accept duplicate columns, truncate counts, and shift cells

Three defects of one family. A repeated column name built the row with
the later value winning, so a coefficient was published under another
coefficient's label. A declared count was truncated rather than refused,
so a malformed count passed a completeness check. And empty cells were
dropped before the fields were counted, so a hole in a row shifted every
value after it one column left and the row still passed its column
count.

Cited in `src/pyflightstream/fsi/loads.py`,
`src/pyflightstream/fsi/nodes.py`,
`src/pyflightstream/results/__init__.py`,
`tests/test_fsi_kinematics.py`, `tests/test_fsi_loads.py`,
`tests/test_results.py`.

### PYFS-010 (Blocker): far-field integrals discard missing samples silently

The array library sums floating point data with missing values skipped
by default, so a sample that did not converge was dropped from the sum
while its ring weight stayed in the geometry. The integral came back
smaller in exact proportion to how much data was missing, with nothing
saying so.

Cited in `src/pyflightstream/farfield/__init__.py`,
`tests/test_farfield.py`.

### PYFS-011 (Blocker): the harmonic path drops the Nyquist mode and contradicts the quadrature

The stored harmonics are capped so that what is kept is unaliased, which
is the right rule for storage and the wrong one for reconstructing a
product the grid already determines. The energy sum needs every order
the grid carries, the Nyquist order included, and that order is its own
conjugate partner for an even sample count, so weighting it like the
others double counts it.

Cited in `src/pyflightstream/farfield/__init__.py`,
`tests/test_farfield.py`.

### PYFS-012 (Blocker): the coupled state and its configuration accept non-finite values and are not bound to each other

Every domain check in the configuration is a comparison, and every
comparison against a not-a-number value is false, so a not-a-number
radius, chord, inertia or rotational speed passed each check by failing
to be caught by it. Bounds have the same hole from the other side: a
lower bound of zero accepts infinity. And a persisted state carried no
identity of the model that produced it.

Cited in `src/pyflightstream/fsi/config.py`,
`src/pyflightstream/fsi/driver.py`, `src/pyflightstream/fsi/state.py`,
`src/pyflightstream/probes/__init__.py`, `tests/test_fsi_config.py`,
`tests/test_fsi_driver.py`, `tests/test_fsi_sources.py`.

### PYFS-013 (High): a structural result that did not converge is still applied to the solver

A structural solve that ran out of budget returns its last iterate
rather than a solution, and a solve on a blade with no properties
returns deflections that are not numbers. Either could be relaxed,
written to the displacement interface file, and fed back to the solver
as though it were a converged structural answer.

Cited in `src/pyflightstream/fsi/centrifugal.py`,
`src/pyflightstream/fsi/config.py`, `src/pyflightstream/fsi/driver.py`,
`src/pyflightstream/fsi/nodes.py`, `src/pyflightstream/fsi/state.py`,
`tests/test_fsi_driver.py`, `tests/test_fsi_kinematics.py`.

### PYFS-014 (High): the executable that ran and the expected build are not bound to the campaign

The campaign did not tie the solver executable it invoked, and the
version and build it expected, to the run it recorded.

No site in `src/` or `tests/` cites this identifier as of 2026-08-18.

### PYFS-015 (High): the manifest does not reconstruct the invocation and does not protect every artifact

The record named the recipe by a dotted name but not which version of
that user code ran, did not carry the exact command line the executor
used, and left artifacts outside the set it digests.

Cited in `src/pyflightstream/run/__init__.py`,
`src/pyflightstream/workspace/__init__.py`,
`tests/test_run_campaign.py`.

### PYFS-016 (High): the models accept physically invalid bounds

A reference area or length of zero divides every coefficient by zero, a
negative one flips the sign of every coefficient in the report while the
run looks healthy, and an infinite one drives them all to zero. Zero and
negative iteration counts, zero and negative timeouts, a
not-a-number convergence threshold and zero threads were all measured
accepted.

Cited in `src/pyflightstream/cases/__init__.py`, `tests/test_cases.py`.

### PYFS-017 (High): post-release code identifies and packages itself as the previous release

The version a run records is read from installed distribution metadata,
which is a static string, so a development tree many commits past the
tag still recorded the tag. A campaign run from a working tree was
indistinguishable, in its own manifest, from one run against the
release.

Cited in `src/pyflightstream/run/__init__.py`,
`src/pyflightstream/workspace/__init__.py`,
`tests/test_run_campaign.py`.

### PYFS-018 (High): publication can happen without the quality gates of the same artifact

The publishing job was not made to depend on the jobs that test the
artifact being published.

No site in `src/` or `tests/` cites this identifier as of 2026-08-18.
REV010-016 restates the same question against the workflow files and is
cited.

### PYFS-019 (High): a registered version with zero commands is called supported

Every registered version was called supported by every public surface,
and the four states hiding under that word are far apart: build 26.000
constructed a script, was accepted by a campaign, and carried evidence
for none of the database's commands, so nothing whatsoever could be
built for it. The documentation said as much in a sentence; nothing said
it in a value a caller could read.

Cited in `src/pyflightstream/support.py`, `tests/test_support.py`.

### PYFS-020 (High): the implemented badge and the requirement index do not prove the traceability they claim

The published requirement index carried an identifier, a text and a
priority and nothing about status, evidence or verification method, and
coverage was measured by searching for an identifier anywhere under the
test tree, a number the generator's own field called an upper bound
rather than a measure.

Cited in `tests/test_requirements_index.py`, `tests/test_traceability.py`.

### PYFS-021 (High): the clean-room and role-review attestations are not auditable proof

The clean-room requirement said its provenance was verified by an
attestation recorded per change, and no per-change attestation of any
kind existed. The requirement's evidence line named a mechanism that had
never been built.

Cited in `tests/test_clean_room.py`.

### PYFS-022 (Medium): the requirement document, the changelog, the roadmap and the decisions drift internally

The requirement document states its own shape in several places and each
statement was maintained by hand. The visible instance was an index
announcing an identifier range ending two identifiers past the highest
requirement that existed.

Cited in `tests/test_srs_consistency.py`.

### PYFS-023 (Medium): the process depends on external records and carries hardcoded local configuration

Machine-specific literals reached tracked files, and part of the process
rested on records held outside the repository.

Cited in `tests/test_house_style.py`.

### PYFS-024 (Medium): continuous integration covers neither the Windows target nor the dependency and coverage envelopes

The integration jobs did not exercise the platform the tool is used on,
nor the lower and upper bounds of the dependency ranges the package
declares.

No site in `src/` or `tests/` cites this identifier as of 2026-08-18.

### PYFS-025 (Medium): dependency, extras and supply-chain governance is incomplete

Three unrelated failure types were raised for one condition, an optional
extra being absent: a bare import error, a bespoke class, and a third
type in a third module. A caller who wanted to handle a missing extra
had to know all three, and nothing checked that the remedy each one
printed was a remedy that works.

Cited in `src/pyflightstream/extras.py`,
`src/pyflightstream/probes/geometry.py`, `tests/test_extras.py`. This is
the one identifier of the 41 that `reports/` already named before this
report, in the license-evidence card
`reports/RPT-016_runtime-and-plot-licenses_2026-08-03.md`, in a sentence
rather than a heading.

### PYFS-026 (Low to medium): the example scripts are neither type-checked nor executed in continuous integration

The worked examples were in no integration step at all, so an example
could break with the interface it demonstrates and stay broken until a
reader tried it. They are the first code a new user runs.

Cited in `tests/test_examples.py`.

## REV-010, 2026-08-03: 19 findings

REV-010 reviewed the exact pushed commit rather than the commit
messages, and scored the 26 findings above as 9 closed, 16 partial and 1
open, against its own definition of partial: a guard added at one layer
while the same invariant was not centralized at the lowest shared
boundary. Several findings below are that measurement made specific.

### REV010-001 (Blocker): a result for a different flight condition can be marked converged

A loads export prints the conditions the solver actually ran, so those
printed values are the run's identity. The assessor took the case and
never read it, so the requested operating point was never compared with
the printed one. The tabular layer already had that comparison and the
assessor did not, so a result for the wrong flight condition could be
recorded as converged in the manifest and contradicted later by a helper
the manifest never consults.

Cited in `src/pyflightstream/results/conditions.py`,
`src/pyflightstream/results/tables.py`,
`src/pyflightstream/run/__init__.py`,
`src/pyflightstream/workspace/__init__.py`, `tests/test_conditions.py`,
`tests/test_run_campaign.py`.

### REV010-002 (Blocker): impossible counts and unknown solver modes become successful terminal states

Integrality was the whole guard on a parsed count, and a negative count
is a whole number: a negative iteration count printed in a loads footer
was read, believed and carried into a converged assessment. And every
printed solver mode that was not the steady one was treated as unsteady,
so a mode this package has never seen was judged by a rule that may not
apply to it.

Cited in `src/pyflightstream/results/__init__.py`,
`src/pyflightstream/run/__init__.py`, `tests/test_results.py`,
`tests/test_run_campaign.py`.

### REV010-003 (High): duplicate probe columns silently relabel physical fields

The loads parser had refused a repeated column name since PYFS-009 and
the probe parser had not. The reproduction is exact: a header rewritten
so one label appears twice returned the value of the missing column
under the surviving label.

Cited in `src/pyflightstream/results/__init__.py`,
`tests/test_results.py`.

### REV010-004 (High): public command emission serializes not-a-number and the infinities

Type checking a floating point argument accepts a not-a-number value,
because it is a floating point value, and rendering is a string
conversion, so the public emission call produced a solver line carrying
that word as an argument. The higher-level settings helpers guard
finiteness and the documented low-level call goes straight past them.

Cited in `src/pyflightstream/script/__init__.py`,
`tests/test_script.py`.

### REV010-005 (High): the probe lattice accepts non-finite and negative survey geometry

The same comparison hole as the scalar half of PYFS-012, in the sibling
nobody had looked at: every geometric check is an inequality, so a
not-a-number tip radius, station or ring edge passed each one by failing
to be caught by it, and the lateral cylinder had no domain check at all,
so a negative closure radius validated as geometry.

Cited in `src/pyflightstream/probes/__init__.py`, `tests/test_probes.py`.

### REV010-006 (Medium): two concatenated loads exports are accepted as one

The footer is located by a first-match search and the table reader stops
at the first closing separator, so a second, normally terminated export
appended to the file was invisible to every guard, including the
duplicate-total refusal that exists for exactly this class of confusion.
The caller received the first report with no indication that another one
existed.

Cited in `src/pyflightstream/results/__init__.py`,
`tests/test_results.py`.

### REV010-007 (High): sectional load counts are truncated from fractional values

The results parser had already centralized an exact count parser and the
structural loads reader kept its own truncating copy, so a declared
count of one hundred point nine became one hundred and then passed the
hundred-row completeness check. Malformed evidence read as complete
evidence.

Cited in `src/pyflightstream/fsi/loads.py`,
`src/pyflightstream/results/__init__.py`, `tests/test_fsi_loads.py`.

### REV010-008 (High): mid-span sectional loads are extrapolated over the whole blade

The resampling promised interpolation onto the structural axis and
nothing bounded how far the interpolation's endpoint behavior could
reach, so sections covering a fraction of the blade were spread across
all of it.

Cited in `src/pyflightstream/fsi/driver.py`,
`src/pyflightstream/fsi/loads.py`, `tests/test_fsi_loads.py`.

### REV010-009 (High): persisted coupled state is not bound to its physical configuration

The shape check answers whether the stored arrays fit the current
configuration, which is a different question from whether this model
produced them. The configuration digest that answers the second question
was already being computed for a log row and simply was not consulted
where it decides anything.

Cited in `src/pyflightstream/fsi/driver.py`,
`src/pyflightstream/fsi/state.py`, `tests/test_fsi_driver.py`.

### REV010-010 (High): the coupled phase transition begins without the thrust-stability half of its own criterion

The acceptance model is two criteria, structural twist constant and the
integrated normal force stable between consecutive revolutions, and the
driver tested one. The force was written to the convergence log and
never compared, so the documented acceptance model was not the one the
code implemented.

Cited in `src/pyflightstream/fsi/config.py`,
`src/pyflightstream/fsi/driver.py`, `src/pyflightstream/fsi/state.py`,
`tests/test_fsi_driver.py`.

### REV010-011 (Medium): far-field coverage undercounts non-finite inputs

Values under a square root were masked when negative and the mask was a
comparison, so a not-a-number value was not masked and did not enter the
masked fraction, while the square root returned a not-a-number result
anyway. The coverage metadata overstated how much of the field the
evaluation had honored, which is the one thing it exists to report.

Cited in `src/pyflightstream/farfield/__init__.py`,
`tests/test_farfield.py`.

### REV010-012 (High): the Campbell sweep bypasses the validated rotational-speed domain

Each sweep point was built by copying the configuration with an updated
rotational speed, and that copy assigns without validating. The
configuration refuses a negative or non-finite rotational speed at
construction and the sweep walked straight past the guarantee, so both a
negative value and a not-a-number value reached the modal solve.

Cited in `src/pyflightstream/fsi/centrifugal.py`,
`tests/test_fsi_centrifugal.py`.

### REV010-013 (Medium): reconstruction from the manifest entry alone needs live workspace artifacts

A requirement promised that a run could be reconstructed from its
manifest entry alone, and the implementation needs artifacts that live
beside the entry rather than in it.

No site in `src/` or `tests/` cites this identifier as of 2026-08-18.

### REV010-014 (High): legacy manifest rows are stamped and rewritten as the current schema

The schema field defaulted to the current value, so a row written before
the field existed validated as a current-schema row. The branch that
should have refused to reconstruct such a row was unreachable: the
legacy row simply asserted the current layout and was reconstructed as
though it carried fields it does not have.

Cited in `src/pyflightstream/run/__init__.py`,
`src/pyflightstream/workspace/__init__.py`,
`tests/test_run_campaign.py`.

### REV010-015 (High): breaking behavior builds and imports as the previous release number

The project version had not moved while breaking removals had landed, so
the wheel exposed the new surface and identified as the old release.

Cited in `tests/test_deprecation_deadline.py`,
`tests/test_metadata_currency.py`, `tests/test_version_identity.py`.

### REV010-016 (High): publication is not coupled to the gates or to the exact wheel they tested

The publishing job depended only on the job that produced the artifact,
so a tag could publish while the quality suite was failing, and what
shipped had never been exercised: the integration workflow tests an
editable install of the source rather than the built artifact.

Cited in `tests/test_workflow_supply_chain.py`.

### REV010-017 (Medium): public and process documentation contradict current behavior

Six places where the documentation and the code disagreed, with one
pattern behind all six: a claim and its subject live in different files
with nothing comparing them. The published instance is a module removed
at v0.4.0 that three surfaces went on describing as surviving.

Cited in `tests/test_claim_currency.py`.

### REV010-018 (Medium): the review attestation is local, ignored by version control, and not auditable

The hook that writes the attestation says in its own body that the
attestation does not prove the reviewer agents ran, and the skill that
invokes it called the same file the mechanical proof that they did. Two
documents, one mechanism, opposite claims.

Cited in `tests/test_claim_currency.py`.

### REV010-019 (Medium): mutable workflow dependencies and broad permissions leave supply-chain risk

Every third-party action was referenced by tag, and a tag is mutable:
its owner can repoint it at new code, so build and release behavior
could change with no reviewed change in this repository. The release job
also installed whatever packaging tools happened to be current, which
can change what the artifact contains between two runs of the same
commit.

Cited in `tests/test_workflow_supply_chain.py`.

## Amendment rule

This is a narrative report in the series `reports/README.md` describes,
so it is amendable: an amendment is recorded in the title line above and,
where it retracts something, at the point in the body that it retracts.
What it may never do is restate a finding as something the review did
not say, because the identifiers below are cited from code that was
written to answer exactly what was said.

Adding a finding here is what makes a new citation legal. A citation of
an identifier this report does not head fails
`tests/test_review_citations.py`, and so does deleting this report.
