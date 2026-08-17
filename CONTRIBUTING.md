# Contributing to pyflightstream

This project is written for engineers who use FlightStream, not only for
software developers. Every rule below exists to keep the code readable,
the evidence traceable, and the license clean.

## Setup

```
pip install -e .[dev,fsi,geom]
pre-commit install
pytest
```

The `fsi` and `geom` extras are part of the full Tier 1 suite (the FSI
and geometry-gate tests import them); the four platform legs of CI
install exactly this set.

**Budget roughly ten minutes for `pytest`**, measured 2026-08-12 at 659
seconds. Most of the growth is four vendored mutation batteries that run
every kit guard against the body it protects, and one of them, the push
gate's, is 244 seconds by itself: it drives sixteen cases and six mutants
as real hook processes against real throwaway repositories. The cost is
the fidelity. Two of those runs shell out per case, so the number moves
with the machine.

Tier 1 also runs a tree-wide forbidden-identifier scan
(`check_shipped_surface.py` against `.claude/shipped_surface.conf`). It
reads every tracked file, so a new file carrying an email address or a
user-profile path reddens CI rather than being noticed at review. If it
refuses something that is an identifier by design, the fix is an
exemption in that config with the reason written beside it, never a
narrowing of the scan.

`manual` and `plot` are deliberately NOT in it, and the omission is load
bearing rather than an oversight: those legs are what proves the package
works for a reader who installed it plainly. One CI leg,
`test-all-extras`, installs everything instead, so the assertions gated
behind those two execute somewhere.

Locally the command above skips exactly one test FOR A MISSING EXTRA,
the pdf reader's layout check; add `,manual` if you are touching
`pyflightstream.utils.manual` or that assertion never runs for you.
Other tests skip for reasons that have nothing to do with extras, so the
suite's skip count is larger than one and that is expected.
`plot` gates no assertion today and is in the all-extras leg so that the
first one added is executed rather than skipped. Adding it changes
nothing you can measure, because matplotlib is already installed
transitively: PyNiteFEA requires it, so the `fsi` extra brings it in
(measured against PyNiteFEA 3.0.0 on 2026-08-10).

Whichever you install, do not reach for an optional distribution without
a guard. `tests/test_extras_isolation.py` refuses it, and the refusal
names the form to use for the tree you are in. Its evidence is
`python scripts/prove_extras_isolation.py`, which re-runs the mutation
battery behind it. It EDITS THE WORKING
TREE and restores it, so run it on a clean checkout and read `git
status` afterwards; a full pass takes over ten minutes, so it takes a
label prefix to run one part. The match is a PREFIX and not a token, so
`M1` selects M1 and M10 through M18, eleven of the twenty mutants; `N1`
or `M2` selects one. Passing a label that matches nothing exits 1 and
prints every label there is, which is also how to list them. That guard exists because
an unguarded `import pypdf` reached the v0.7.0 tag past every reviewer
pass of that release, all of them reading in an environment that had it
(INC-20260810-2140-shared).

That incident produced a SECOND guard, the CI-green tag rule, and it is
no longer in this repository's own hands: it lives in the shared push
gate (`.claude/hooks/role_review_gate.py`, kit 0.2.18), and its evidence
is `.claude/hooks/ci_state_mutations.py`, run in tier 1 by
`tests/test_ci_state.py` with the refusal itself pinned by
`tests/test_push_gate.py`. The battery above was named
`prove_extras_and_ci_guards.py` and carried that half until 2026-08-11;
both were renamed and removed in the commit that vendored the shared
body.

## Hard invariants

The non-negotiable rules live in CLAUDE.md at the repository root. Read
them before your first change. In short: no manual text, no AGPL-derived
code, every command database change is evidence-backed, versions are only
added, English names everywhere, no notebooks in Git.

## How to add a command

Use the `add-command` skill (`.claude/skills/add-command/SKILL.md`) or follow
it manually: draft the YAML entry with layout, phase, typed args, one
evidence citation (manual_ref for the page that documents the command, or
probe_ref naming a committed report where no edition documents it), and
status `documented`; add emit-validation and golden
tests; open a pending-probe issue if no licensed machine is available. A
command becomes `verified` only through a committed Tier 2 probe report.

`pyfs-manual` does the reading half of that first step.

`sweep` is the form that matches the chapter rule in
`docs/srs/data-model.md`, which is that a chapter enters for every
registered edition at once. Given a `--editions` YAML manifest naming the
registered builds and their page ranges, it reports the commands no edition
has an entry for, with the page and the editions each one needs, and
`--by-section` groups them by chapter and `--fail-if-absent` makes a
residual fail rather than report. Use it for a coverage push:
`coverage`, below, answers the same question of ONE manual, and a command
absent from one edition may be recorded from another.

`sweep` reports a SECOND finding beside that one, and the two answer
different questions. The first asks which commands have no entry; the
second asks which commands an edition documents that its own build
cannot emit, which the first is structurally blind to because it
compares entry names. An entry that exists and carries no row for one
edition reads as covered, and on 2026-08-10 exactly that hid a command
three builds could not emit.

`citations` is the one to run AFTER writing page citations, and the
step is not optional bookkeeping: it exists because ten citations were
found pointing at a document whose pagination had moved under them,
each at a real page of a real manual, so nothing looked wrong. Run it
over the whole manifest rather than the edition you just touched, since
a re-conversion of an OLD manual is what produced those ten. It is the
only subcommand that exits non-zero on a finding.

It also reports, per edition, how many rows it could re-read at all.
Most rows of the flagship build carry no page of their own, resting on
the entry's `manual_ref` instead, so a low figure or a zero there is the
shape of the database rather than a defect; the number is printed
because a count of editions read would hide it.

`scripts/chm_to_pdf.py` is the reading tool that is not a subcommand.
One install, 25.000, ships its manual only as a compiled help archive,
and this converts it to a pdf whose page numbers anyone can land on
again: the topic order comes from the archive's own table of contents,
the geometry is pinned, the timestamps the renderer embeds are
stripped, and the hash is printed. Ten committed citations depend on
that reproducibility, so re-render with a different renderer and expect
the page numbers to move. It needs the `[manual]` extra and an archive
extractor; its own docstring carries the two commands.

`scripts/prove_evidence_guards.py` is the mutation battery for the
evidence guards: it EDITS FILES UNDER `src/` one at a time, runs the
test written for each, and restores them, so run it from a clean tree
and check `git status` afterwards. A run killed mid-mutant is undone
by the next one, which refuses to continue until it has. Its sibling
`scripts/prove_extras_isolation.py` has the same hazard and both
share `scripts/_mutation_harness.py`.

`scripts/measure_probe_target_lines.py` derives how many probe
specifications emit an argument-bearing target line, a figure that
reached three committed artifacts in three readings before it was
derived; a tier 1 test pins its output.

`pyfs-manual register --editions <manifest> --fs-version <canonical>` is
the sixth subcommand and the only one that writes into the command
database.
It carries a build's documentation forward: for every command the new
edition describes exactly as its predecessor did, it writes a
`documented` row citing the new edition at the page it was found on. The
comparison is of what the editions SAY (placeholders, sample, parameter
table), never of the page number, because a reflow repaginates without
changing a word. Anything described DIFFERENTLY is reported and never
written, which is the line between carrying a reading forward and
inventing one. Dry run by default; `--write` writes, and
`--commands-dir` points it at a copy to rehearse against first.

The build must be BOTH a row of the manifest and a registered build.
The manifest deliberately does not resolve its labels, so an
unregistered build can be swept before it is added; writing is the one
thing that needs the stricter rule, since a row is keyed by the
canonical identifier. The transaction itself is
`pyflightstream.utils.database.register_edition`, not the argument
parser: it validates every chapter it would produce against the command
schema before a byte reaches the disk, exactly as `apply_compat` does,
and it is importable so it can be tested. Re-running it is a no-op that
says so rather than a refusal.

The QA geometry helpers are the maintainer-facing half of
`pyflightstream.qa.geometry`: `mean_edge_length` measures a mesh's local
face size, and the keyword-only `translation_m` and `name` on
`wing_triangles` and `generate_wing_stl` place and label a second copy
of a shape. They exist so a gap between two components can be expressed
as a RATIO of the local face length, which is the form the vendor's
caveat about proximity-based boundary-layer mapping is stated in. The
worked example is in `mean_edge_length`'s own docstring and is executed
by the docs run. Pass `name` whenever you write two copies of one shape:
the default solid label is derived from the aerofoil alone, so two
translated copies collide, and that made the loads parser refuse all
sixteen exports of a licensed run on 2026-08-17.

`scripts/gen_absent_commands.py <build>` writes the list of commands a
registered build cannot emit, into `tests/goldens/absent_on_<build>.txt`,
and a tier 1 test compares every such file against the database. Run it
in the same commit as any row you write for a build that inherits
nothing, because the file carries counts as well as names and both move.
26.123 is the first such build; the script takes any registered one.

`scripts/prove_alias_tally_guard.py` is the mutation battery for the
stale-tally guard. It restores, one at a time, the six committed
sentences that enumerated the builds sharing a vendor name before
2026-08-17, and requires the guard to deny each. Like the other
batteries it EDITS TRACKED FILES and restores them; unlike them it
checks a sha256 either side of every mutant, so a run that leaves the
tree changed fails rather than being noticed later.

**If you write one of these, do not anchor it on `git show HEAD:<path>`.**
That battery did, and it broke the day its own fix was committed: the
HEAD blob is the pre-fix text only while the fix is uncommitted, and
afterwards five of its six mutants wrote the file back exactly as it
already was, mutated nothing, and reported SURVIVED. It failed loudly,
which is the honest direction, but it failed reading as though the guard
had missed five real defects. Carry the pre-fix text as a LITERAL and
assert the live anchor is present and unique before replacing it; a
commit pin only moves the trap to the next rebase. And translate line
endings onto the target: two files here are CRLF on disk, and a
line-feed anchor silently matches nothing in them.

Three more batteries follow that shape.
`scripts/prove_flow_mapping_guard.py` covers the rule that a YAML flow
mapping is rendered in exactly one place in the package, in both
spellings a Python source can write one, plus the parameter that used to
let a caller hand in a pre-rendered row.
`scripts/prove_report_date_guards.py` covers the rule that a compat
report's stem and body agree about its date, and its cross check shows
why that guard has two arms rather than one.
`scripts/prove_geometry_guards.py` covers the mesh face-length
measurement and the translated STL, both of which had tests that
survived sabotage before it was written.

The manifest names
paths of licensed manuals and is never committed (invariant 1);
`pyfs-manual sweep --help` prints an example row.

`surface` reads the same manifest and asks the other question: what each
build documents, and what changed between two of them. Use it when a
build arrives and you want to know what the vendor moved before you read
anything; `reports/RPT-024` is its committed output, and its last two
sections are regenerated by re-running it.

Then, given a manual pdf and its page ranges: `coverage` lists what that one
edition documents and the database does not, and `draft` renders entries for
those commands. It writes
only with `--write --out`. Read what it produces as a starting point and not
as evidence. It leaves `???` wherever no rule could read a value, which the
schema refuses on purpose, so an unreviewed draft turns the suite red rather
than becoming grammar the emitter validates other people's scripts against.
Each drafted entry also carries a `drafted:` line naming the tool and the
page; resolve the `???` values against the manual and delete that line in
the same edit.

## How to report a version break

Open an issue with: the FlightStream version (YY.XXX), the script excerpt
that fails, and the relevant log lines. This is exactly the evidence the
probe suite needs to reproduce and classify the break.

## QA tiers and what each proves

* Tier 1 (`pytest`, runs anywhere): the database is internally consistent,
  the emitter refuses invalid commands per version, parsers read the
  committed fixtures, generated scripts match the goldens.
* Tier 2 (`pyfs-qa probe`, licensed machine): each database command actually
  works in a given FlightStream version; results are committed under
  `reports/compat/` and promoted into the database by `pyfs-qa apply-compat`.
* Tier 3 (`pyfs-qa physics`, licensed machine): physics regression matrix
  with WARN and FAIL tolerance bands; reference updates demand a reason.

All three tiers are operational; `pyfs-qa cases` prints the Tier 3
matrix without running anything, and the committed reports live under
`reports/compat/` and `reports/physics/`.

Executable examples: the docstring doctests and the python code blocks
in the root README and `docs/` are run in CI so a stale example fails.
Run them locally the same way CI does (warnings promoted to errors):

```
pytest src/pyflightstream README.md docs -W error
```

The plain `pytest` above (Tier 1) does not collect these, so run this
command after editing a docstring example or a README/docs snippet.
`pip install -e .[dev,fsi,geom]` already pulls the runner (`sybil`).

## Style

* ruff handles lint and format; run `pre-commit run -a` before pushing.
* Docstrings: numpydoc convention; every parameter states units and, where
  it applies, the reference frame.
* Aerodynamic symbols keep their standard names (CL, CDi, J, alpha_deg);
  ruff N803/N806 are exempted for this reason.
* House style: no em or en dash characters in Markdown or docstrings
  (enforced by tests/test_house_style.py).

## AI-assisted development disclosure

This project is developed with AI assistance (Claude, working in
sessions directed by the author). The safeguards are process, not
trust: every command database change is evidence-backed (manual
citation or committed probe report; hard invariant 3), physics and
solver claims come from executed runs recorded under `reports/`,
role-based reviewer passes run on every work item's diff before it
closes, and the author keeps the non-delegable seats (product owner,
domain expert, numerical analyst). The clean-room rule extends to the
AI: it never reads the AGPL pyFlightscript package. Contributors are
welcome to use AI assistance under the same rules; you remain
responsible for what you submit.

## License note

MIT. Contributions must be original work or MIT-compatible. Contributions
derived from the AGPL pyFlightscript package are rejected, including
translations or close adaptations of its code.

## Clean-room provenance (SRS FR-08)

Every commit carries this trailer, as the last paragraph of its
message:

```
Clean-room: emitter specified from the official manual and probe evidence only; no code, structure or docstrings from the AGPL predecessor
```

`tests/test_clean_room.py` asserts it on every commit since its
baseline and fails the suite without it. Amending is banned in this
repository, so a commit that missed the trailer is corrected by a
follow-up commit that says so.

What the trailer is, and is not. It is a DECLARATION with an auditable
record of who made it: nothing can prove the absolute negative "the
predecessor was never read", and a mechanism that claimed to would be
worse than none. If you cannot make this declaration about a change, do
not make the commit.
