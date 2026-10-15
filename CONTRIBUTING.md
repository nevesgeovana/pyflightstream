# Contributing to pyflightstream

Contributions should make the package useful to engineers, keep numerical
claims traceable to evidence, and preserve the clean-room license boundary.

## Setup and checks

```text
pip install -e ".[dev,fsi,geom]"
pre-commit install
pytest
```

The fsi and geom extras are needed for the complete offline suite. Add manual
when changing manual-reading tools and plot when running plotting examples.
Guard optional imports at the operation that needs them. [Test tiers](https://nevesgeovana.github.io/pyflightstream/tiers/)
explains what offline and licensed tests establish.

Run affected subject tests while developing. Each tier-1 file belongs to one
sorted package in tests/tier1_offline/packages.json. Use `pytest -m pkg_post`
to select a package, substituting its name. Preserve behavioral cases when
consolidating tests. A regression must fail on the unfixed behavior.

```text
ruff check .
ruff format --check .
mypy
pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning
properdocs build --strict
```

The last pytest command executes docstrings and Markdown Python examples;
plain pytest does not. Public workflows need worked examples. Mark examples
requiring a solver explicitly. Offline execution does not validate physics.

CI runs on pushes and manual dispatch, skipping docs-only pushes and dry-run
branches and cancelling superseded runs. Release requires concluded green main
CI at its exact SHA; dispatch CI for a docs-only candidate. Branch coverage
runs on the version tag against the built wheel. Docs deploy on version tags.

## Repository layout

| Folder | Purpose |
|---|---|
| src/pyflightstream/ | Package modules and evidence-backed command database |
| tests/tier1_offline/ | Offline behavior and structural checks |
| tests/tier2_validity/ | Licensed command-validity tests |
| tests/tier3_licensed/ | Synthetic campaign workspace and result checks |
| docs/ | Website sources; API and CLI references are generated |
| examples/using-CLI/, examples/using-API/ | Matching runnable workflows |
| guide/ | LaTeX, figures and attribution; PDFs are build artifacts |

Do not commit licensed manuals, local installation paths or research data.
Select solver executables explicitly or through workspace configuration.
Solver subprocesses inherit the ambient licensing environment.

## Hard invariants

These numbers are stable because source and tests cite them.

1. **No proprietary text.** Paraphrase manual facts and provide a locator.
2. **No AGPL-derived code.** Specify the emitter from official manuals and
   probe evidence only. Include the clean-room trailer in every commit.
3. **Evidence before a claim.** Command rows carry citations. Promote statuses
   from recorded evidence, never by hand.
4. **Versions are only added.** Preserve the registered version order.
5. **No proprietary content, research geometry, employer names or predecessor
   toolchain names** in shipped content.
6. **English names everywhere**, including code, tests and documentation.
7. **Downward dependencies.** Follow the architecture's layer ranks.
8. **Didactic refusals.** State the given value, accepted input and available
   remedy, with context a caller can use.
9. **No notebooks in Git.**

Geometry, spreadsheet and identifier guards protect the shipped surface.
Intentional exceptions need a reason in the applicable allowlist.

## Add or update a solver command

Write its YAML layout, phase, typed arguments, status and evidence locator.
Use manual_ref for documented grammar or probe_ref for measured behavior.
Add emit-validation and golden tests. Verification needs a licensed result
for the relevant build.

Use `pyfs-manual sweep` for an editions manifest, coverage for one manual,
draft for entries requiring review, and citations to check page locators.
Resolve every draft placeholder before acceptance. The manifest names licensed
files and remains local. Use each command's --help for required arguments.

`pyfs-manual register` previews unchanged grammar carried to a registered build;
--write applies it. Rehearse with --commands-dir pointing at a copy. Changed
grammar needs review. When a build inherits no evidence, regenerate its absent
command list with scripts/gen_absent_commands.py and run the database tests.

See [versions and evidence](https://nevesgeovana.github.io/pyflightstream/concepts/versions-and-evidence/) and
[build support](https://nevesgeovana.github.io/pyflightstream/builds/) for the two status ladders.

## Style and mutation tests

Use Ruff, numpydoc docstrings with units and reference frames, and standard
aerodynamic symbols. Markdown and docstrings use neither em nor en dashes.

Mutation tools use _mutation_harness.apply_mutant and verify byte-exact
restoration. Each mutant changes a unique live anchor and must be detected by
the behavior test. Keep defect text as a literal, preserve line endings and
run destructive batteries on a clean copy.

## Report a version break

Include the canonical build, minimal script excerpt and diagnostic. Exclude
proprietary geometry and manual text. Distinguish planning, stub execution
and actual solver execution.

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

## License and clean-room provenance

Contributions must be original or MIT-compatible. Code derived from the AGPL
pyFlightscript package, including translations and close adaptations, is not
accepted. Every commit ends with this exact final paragraph:

```text
Clean-room: emitter specified from the official manual and probe evidence only; no code, structure or docstrings from the AGPL predecessor
```

Amending is prohibited. Correct a missing declaration in a follow-up commit:
its final paragraph names `Clean-room-for: <full commit hash>` followed by the
same Clean-room line. The referenced commit must precede the declaration and
belong to the checked range. Declare only what you can support.

## Release notes

Write user-visible changes in CHANGELOG.md's Unreleased section. Format changes
and migration instructions have one home, docs/upgrading.md.
