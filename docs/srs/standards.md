# Standards alignment

The external standards and community practices this project aligns
with, each verified at its adoption date (initial review 2026-07-22;
later rows carry their own dates). Adopted means the
practice is in force; aspirational means it is on the adoption
backlog; considered means it was evaluated and deliberately not
adopted, with the reason recorded so the evaluation is not repeated.

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

The column is checked rather than trusted: `tests/test_claim_currency.py`
fails when a cell is empty, when it names a repository path the tree does
not hold, or when it names a CI command that no workflow runs.

| Practice | Reference | How it lands here | Enforced by |
|---|---|---|---|
| SemVer 2.0.0 | [semver.org](https://semver.org/spec/v2.0.0.html) | Package versioning, decoupled from FlightStream versions; at 0.x the API is unstable by SemVer item 4 | `tests/test_version_identity.py` |
| Keep a Changelog 1.1.0 | [keepachangelog.com](https://keepachangelog.com/en/1.1.0/) | CHANGELOG.md with a permanent Unreleased section (test-enforced), fed at every session close, promoted at release | `tests/test_metadata_currency.py` |
| Citation File Format | [citation-file-format.github.io](https://citation-file-format.github.io/) | CITATION.cff validated and tag-matched at release; Zenodo DOI per public release | `tests/test_metadata_currency.py` |
| numpydoc | [numpydoc.readthedocs.io](https://numpydoc.readthedocs.io/) | Docstring convention, with units and reference frames required (NFR-01) | seat: technical writer, charter `.claude/agents/tech-writer.md` |
| Docs as code | [Write the Docs guide](https://www.writethedocs.org/guide/docs-as-code/) | Docs in the repo, reviewed and shipped with the code change that makes them true (NFR-11) | `tests/test_claim_currency.py` |
| Executable documentation examples in CI | [Sybil](https://sybil.readthedocs.io/en/latest/) (chosen 2026-07-23 over plain pytest doctest: docs markdown examples are tested too) | `pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning` runs the docstring doctests and the README/docs code blocks in CI with warnings promoted to errors; `sybil` in the `[dev]` extra (shipped in v0.3.0) | `pytest src/pyflightstream README.md docs -W error::pyflightstream._errors.PyflightstreamWarning` |
| Single-source versioning (test-guarded) | [PyPA discussion](https://packaging.python.org/en/latest/discussions/single-source-version/) | `__version__` derives from installed metadata; a Tier 1 test asserts the version-bearing files agree; full VCS-derived versioning is on the backlog | `tests/test_metadata_currency.py` |
| Docs warnings as errors | [MkDocs strict mode](https://www.mkdocs.org/user-guide/configuration/#strict), inherited by [ProperDocs](https://github.com/properdocs/properdocs) (the maintained MkDocs fork, BSD-2-Clause; license evidence RPT-009) | `properdocs build --strict` in CI (migrated from MkDocs after a green drop-in test, 2026-07-23) | `properdocs build --strict` |
| Diataxis (as a map) | [diataxis.fr](https://diataxis.fr/) | Each fact has one owning home: reference pages are generated from the database and docstrings, explanation lives in this SRS and the architecture pages, how-to lives in examples and the user guide; other pages link instead of restating | convention |
| EARS-informed requirement wording | [alistairmavin.com/ears](https://alistairmavin.com/ears/) | New requirements use the EARS sentence shapes with stable IDs; the audit skill checks that every implemented requirement names its evidence | convention |
| Checklist design principles | [projectcheck.org](http://www.projectcheck.org/checklist-for-checklists.html) | Maintenance skills are structured around explicit pause points, DO-CONFIRM for audits, READ-DO for releases, few killer items per block | convention |
| ISO/IEC/IEEE 29148 (outline only) | [iso.org/standard/72089.html](https://www.iso.org/standard/72089.html) | This SRS borrows the information-item outline and the requirement-quality characteristics (singular, verifiable, unambiguous), not the process weight | convention |
| Decision records (pattern) | [Nygard ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions), [MADR](https://adr.github.io/madr/) | Decisions are numbered, dated, evidence-linked, and never rewritten; the existing session records (plan items, logbook decisions, handoffs) are the ADR store of this project rather than a parallel file set | convention |
| Role-based review (team-role model, adopted 2026-07-23) | [US-RSE](https://us-rse.org/) for the research-software-engineering standard; [AIAA G-077](https://arc.aiaa.org/doi/book/10.2514/4.472855) and [NASA-STD-7009](https://standards.nasa.gov/standard/NASA/NASA-STD-7009) for the V&V seat; [ISTQB](https://istqb.org/) for the QA seat; [Google SRE](https://sre.google/sre-book/release-engineering/) for release engineering; [JOSS](https://joss.readthedocs.io/en/latest/review_criteria.html) and [pyOpenSci](https://www.pyopensci.org/software-peer-review/) review criteria as the periodic audit layer | Five reviewer charters in `.claude/agents/` (architect, QA, V&V, technical writer, API designer) run by the `role-review` skill on every work item's diff before it closes (definition of done). Two mechanical refusals stand behind that habit rather than reminding anyone of it: the PreToolUse hook `.claude/hooks/role_review_gate.py`, wired in `.claude/settings.json`, DENIES a `git push` that carries no attestation covering every commit the push makes new plus each ref it sends; and the same hook denies while a blocking incident is open in the shared ledger located by `COORD_INCIDENT_LEDGER`, where an unset or unreadable variable denies too, since a guard that reads its own missing configuration as permission is not a guard (the variable's one home is the machine-configuration table in `CLAUDE.md`). The author keeps the non-delegable seats (product owner, domain expert, numerical analyst); the sister ITACA repository carries the same process | `.claude/hooks/role_review_gate.py` |

## Aspirational (adoption backlog, tracked as a plan item)

| Practice | Reference | Gate |
|---|---|---|
| VCS-derived version (single authority = the Git tag) | [setuptools-scm](https://setuptools-scm.readthedocs.io/en/latest/) / [hatch-vcs](https://github.com/ofek/hatch-vcs) | Build-backend change; the author decides the vehicle |
| Normative repo checks | [pyOpenSci packaging guide](https://www.pyopensci.org/python-package-guide/), [Scientific Python Development Guide](https://learn.scientific-python.org/development/), [sp-repo-review](https://github.com/scientific-python/repo-review) | The audit skill runs the checklist manually today; the mechanical runner is backlog |
| Supply-chain posture | [OpenSSF Best Practices](https://www.bestpractices.dev/en/criteria/0), [Scorecard](https://github.com/ossf/scorecard), [SPEC 8](https://scientific-python.org/specs/spec-0008/), [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) | PARTLY DELIVERED at v0.4.0, and kept on this table with the residual named rather than moved wholesale. In force: PyPI trusted publishing (OIDC, no stored token, mandatory, never a manual upload); every workflow action pinned by commit digest rather than by tag; least-privilege workflow permissions with the OIDC token requested only by the job that publishes; and a release that builds once, records the wheel SHA-256, tests THAT wheel on both platforms at both Python versions, and refuses to publish anything whose digest moved. Still aspirational: the OpenSSF Best Practices badge and a Scorecard run. Solo-maintainer subset only (code-review and branch-protection checks are accepted misses, documented) |
| Support-window policy | [SPEC 0](https://scientific-python.org/specs/spec-0000/) | NFR-22 is the requirement (tested range per dependency, pre-1.0 pin form, Python-ceiling propagation) and is pending; what stays aspirational on this row is aligning those windows with SPEC 0's published schedule |
| pyproject metadata completeness | [PyPA pyproject guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) | Classifiers and well-known URLs landed 2026-07-23 (audit); remaining: the SPDX license expression. THE DEFERRAL'S STATED REASON WAS CORRECTED 2026-08-20: this cell said the expression was deferred WITH the build-backend item, and the two are independent. Adopting PEP 639 needs a `setuptools>=77` floor bump and nothing else; the build-backend row is waiting on a decision that does not touch it. The fictional coupling is what kept a one-line edit deferred past setuptools' own published sunset of 2026-02-18, which has passed with the table form still warning rather than failing. What the migration DOES need is care rather than a gate: emitting `License-Expression` makes PyPI reject the upload while the license classifier is still present, so the classifier is deleted in the same commit, and doing half of it is the one way to turn a warning into a failed upload. Not attempted during a release week |
| pyOpenSci peer-review self-audit | [EiC checklist](https://www.pyopensci.org/software-peer-review/how-to/editor-in-chief-guide.html) | Run as self-audit; includes the generative-AI-use disclosure item, relevant to this project's AI-assisted sessions |

## Considered, not adopted

| Practice | Reason |
|---|---|
| [SPEC 1 lazy loading](https://scientific-python.org/specs/spec-0001/) | Explicitly not recommended at this project's size; import overhead is negligible. Decision recorded so the scan is not repeated |
| [repolinter](https://github.com/todogroup/repolinter) | Archived upstream (2026); its rule-set idea is subsumed by the pyOpenSci checklist and sp-repo-review |
| Full ISO 29148 process | Process weight disproportionate to a solo-maintained library; the outline and quality characteristics suffice |
| ADR file tooling (adr-tools) | Unmaintained; the pattern is adopted, the tooling is not, and the session records already store decisions |
| Full reproducible-builds | Bit-reproducibility is overkill at this size; clean-checkout CI builds and recorded tool versions cover the intent |

## Domain conventions

Aerodynamic symbols keep their standard names (CL, CDi, J, alpha,
beta); physics formulas carry Source lines in docstrings, enforced by
a schema test; axes and sign conventions are stated per function in
the numpydoc Parameters sections.
