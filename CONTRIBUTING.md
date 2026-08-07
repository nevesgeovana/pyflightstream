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
and geometry-gate tests import them); CI installs the same set.

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

`pyfs-manual` does the reading half of that first step, given a manual pdf
and its page ranges: `coverage` lists what an edition documents and the
database does not, and `draft` renders entries for those commands. It writes
only with `--write --out`. Read what it produces as a starting point and not
as evidence. It leaves `???` wherever no rule could read a value, which the
schema refuses on purpose, so an unreviewed draft turns the suite red rather
than becoming grammar the emitter validates other people's scripts against.
Each drafted entry also carries a `drafted:` line naming the tool and the
page; resolve the `???` values against the manual and delete that line in
the same edit.

## How to report a version break

Open an issue with: the FlightStream version (26.XXX), the script excerpt
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
