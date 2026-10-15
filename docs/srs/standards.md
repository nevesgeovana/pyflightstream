# Standards alignment

Current standards and community practices used by contributors. The table
states how each practice applies and what checks it.

## Adopted

The Adopted table describes each row twice, because in one prose column
a practice held by a Tier 1 test and a practice held by habit read
exactly the same.
**How it lands here** says what the practice means in this repository.
**Enforced by** says what refuses a breach, and it is one of three
closed forms:

- a repository path or a CI command, which is the mechanical answer: a
  Tier 1 test module, a hook, or a step a continuous-integration
  workflow runs;
- a named review seat with its charter, which is a reader's judgement
  on every work item's diff rather than a program's;
- the literal word convention, which says on purpose that nothing
  refuses a breach and that the practice is held by review alone.

The column is checked rather than trusted: `tests/tier1_offline/test_claim_currency.py`
fails when a cell is empty, when it names a repository path the tree does
not hold, or when it names a CI command that no workflow runs.

| Practice | Reference | How it lands here | Enforced by |
|---|---|---|---|
| SemVer 2.0.0 | [semver.org](https://semver.org/spec/v2.0.0.html) | Package versioning, decoupled from FlightStream versions; at 0.x the API is unstable by SemVer item 4 | `tests/tier1_offline/test_version_identity.py` |
| Keep a Changelog 1.1.0 | [keepachangelog.com](https://keepachangelog.com/en/1.1.0/) | CHANGELOG.md with a permanent Unreleased section (test-enforced), fed at every session close, promoted at release | `tests/tier1_offline/test_metadata_currency.py` |
| Citation File Format | [citation-file-format.github.io](https://citation-file-format.github.io/) | CITATION.cff validated and tag-matched at release; Zenodo DOI per public release | `tests/tier1_offline/test_metadata_currency.py` |
| numpydoc | [numpydoc.readthedocs.io](https://numpydoc.readthedocs.io/) | Docstring convention, with units and reference frames required (NFR-01). The SHAPE is mechanical: ruff's pydocstyle rules run with `convention = "numpy"` over `src/`, so a missing or malformed docstring fails CI. Whether the units and the reference frame are actually stated is a reader's judgement and nothing refuses a breach of it | `ruff check .` |
| Docs as code | [Write the Docs guide](https://www.writethedocs.org/guide/docs-as-code/) | Docs in the repo, reviewed and shipped with the code change that makes them true (NFR-11) | `tests/tier1_offline/test_claim_currency.py` |
| Executable documentation examples in CI | [Sybil](https://sybil.readthedocs.io/en/latest/) (chosen 2026-07-23 over plain pytest doctest: docs markdown examples are tested too) | `pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning` runs the docstring doctests and the README/docs code blocks in CI with warnings promoted to errors; `sybil` in the `[dev]` extra | `pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning` |
| Single-source versioning (test-guarded) | [PyPA discussion](https://packaging.python.org/en/latest/discussions/single-source-version/) | `__version__` derives from installed metadata; a Tier 1 test asserts the version-bearing files agree; full VCS-derived versioning is on the backlog | `tests/tier1_offline/test_metadata_currency.py` |
| Docs warnings as errors | [MkDocs strict mode](https://www.mkdocs.org/user-guide/configuration/#strict), inherited by [ProperDocs](https://github.com/properdocs/properdocs) (the maintained MkDocs fork, BSD-2-Clause; license evidence RPT-009) | `properdocs build --strict` in CI (migrated from MkDocs after a green drop-in test, 2026-07-23) | `properdocs build --strict` |
| Diataxis (as a map) | [diataxis.fr](https://diataxis.fr/) | Each fact has one owning home, and other pages link instead of restating. The navigation has eight reader sections; the Python API and command-line references are generated from the docstrings and argument parsers | convention |
| EARS-informed requirement wording | [alistairmavin.com/ears](https://alistairmavin.com/ears/) | New requirements use the EARS sentence shapes with stable IDs, and an implemented requirement names its evidence in its own Origin line, which is what `tests/tier1_offline/test_traceability.py` reads | convention |
| Checklist design principles | [projectcheck.org](http://www.projectcheck.org/checklist-for-checklists.html) | The maintenance procedures a release follows are structured around explicit pause points, DO-CONFIRM for an audit and READ-DO for a release, with few killer items per block; `CONTRIBUTING.md` is the public statement of them | convention |
| ISO/IEC/IEEE 29148 (outline only) | [iso.org/standard/72089.html](https://www.iso.org/standard/72089.html) | This SRS borrows the information-item outline and the requirement-quality characteristics (singular, verifiable, unambiguous), not the process weight | convention |
| Decision records (pattern) | [Nygard ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions), [MADR](https://adr.github.io/madr/) | Decisions are numbered, dated, evidence-linked and never rewritten. The public store is this SRS, whose requirements carry their Origin and date, together with CHANGELOG.md; the maintainer's working records are kept outside this repository and are not part of the published specification | convention |
| Role-based review (team-role model, adopted 2026-07-23) | [US-RSE](https://us-rse.org/) for the research-software-engineering standard; [AIAA G-077](https://arc.aiaa.org/doi/book/10.2514/4.472855) and [NASA-STD-7009](https://standards.nasa.gov/standard/NASA/NASA-STD-7009) for the V&V seat; [ISTQB](https://istqb.org/) for the QA seat; [Google SRE](https://sre.google/sre-book/release-engineering/) for release engineering; [JOSS](https://joss.readthedocs.io/en/latest/review_criteria.html) and [pyOpenSci](https://www.pyopensci.org/software-peer-review/) review criteria as the periodic audit layer | Five reviewer seats (architect, QA, V&V, technical writer, API designer) read every work item's diff before it closes, which is part of the definition of done. The owning seat keeps the non-delegable seats: product owner, domain expert, numerical analyst. This row answers `convention` deliberately and the honesty is the point of the column: the review passes are a working practice of this project's maintainer and nothing in this repository refuses a change that skipped one. What IS mechanical is stated in the rows around it, and none of it is a substitute: CI runs the suite, the type check and the two lint legs on every push, and a release is built and published only from a tag whose workflow legs are green | convention |

## Domain conventions

Aerodynamic symbols keep their standard names (CL, CDi, J, alpha,
beta); physics formulas carry Source lines in docstrings, enforced by
a schema test; axes and sign conventions are stated per function in
the numpydoc Parameters sections.
