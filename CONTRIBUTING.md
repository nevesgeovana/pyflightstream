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
names the form to use for the tree you are in. That guard exists because
an unguarded `import pypdf` reached the v0.7.0 tag past every reviewer
pass of that release, all of them reading in an environment that had it
(INC-20260810-2140-shared).

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
