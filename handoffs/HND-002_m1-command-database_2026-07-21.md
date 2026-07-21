# HND-002: M1 executed, versions and command database (2026-07-21)

## 1. Context

Objective as stated against STATUS.md: plan and execute M1 (versions
module, command database schema and loader, core steady command set,
tier 1 tests), incorporating the author's new standing decision to
prefer existing public libraries over in-house implementation. All of
M1 was executed in this session. The manual (SRC-003 v26.12) was read
in the page ranges mapped by the workspace deep review (workspace
TSR-003) and 113 commands were drafted as paraphrases with page
citations. The tier 1 suite (27 tests) is green locally and in CI,
which is the M1 exit criterion.

## 2. Decisions

1. Engineering policy: prefer existing public libraries for generic
   needs, MIT-compatible licenses, domain logic in-house (decided by
   Geovana; recorded in CLAUDE.md).
2. pydantic is the validation backend of the command database schema
   and entered runtime dependencies (decided by Geovana among options
   presented).
3. Evidence-strict statuses: M1 entries carry documented for 26.120
   only, citing the v26.12 manual; 26.000/26.100 wait for release
   notes review or backfill probing, already planned for v0.2+
   (decided by Geovana).
4. All four extra command families enter M1: actuator disc, probes
   and sections, motion definitions, SWEEPER (decided by Geovana).
   Delivering them as complete chapters grew the set from the ~40
   estimate to 113 entries (proposed by Claude, recorded as a
   deviation in STATUS.md and plan.csv).
5. Schema vocabulary extensions on manual evidence: param_lines
   layout (SRC-003 p.279), int_list and float_list argument types,
   control phase exempt from ordering, ArgSpec.required flag
   (proposed by Claude, evidence cited in the code docstrings).
6. Hotfix builds inherit the base release record until probe evidence
   overrides it, implemented in CommandEntry.status_in per SAD
   Section 2 (implementation decision by Claude).

## 3. Changes persisted

* `CLAUDE.md`: Engineering policy section (commit a86600d).
* `pyproject.toml`: pydantic added to runtime dependencies (a86600d).
* `src/pyflightstream/versions.py` and `tests/test_versions.py`:
  FsVersion, ordered registry, aliases, UnknownVersionError (1a0957d).
* `src/pyflightstream/commands/__init__.py` and
  `tests/test_command_db.py`: pydantic models, CommandRegistry,
  VersionView with CommandNotInVersionError messages per SAD Section
  4.1, evidence rules at model level (eed59dc, extended in 7097196
  and 2f5aa44).
* 16 chapter YAML files, 113 entries, all documented for 26.120 with
  page citations; SONIC_VELOCITY records the p.328 removal
  (7097196 batch A, 58f1ed5 batch B, 2f5aa44 batches C and D).
* `.pre-commit-config.yaml`: ruff hook pinned to the CI ruff
  generation after a local versus CI format disagreement (5233956).
* Tests: 27 tier 1 tests green; ruff check and format clean; mkdocs
  build strict green; CI run 29845795014 success.
* plan.csv PLN-001 to PLN-004 done with evidence; STATUS.md milestone
  table, current focus (M2), open questions, recorded deviations.

## 4. Open questions and contradictions

* SWEEPER grammars come from the worked example (p.406) and the
  Script Index (p.383); the Sweeper Toolbox chapter (pp.264-279) is
  not deep-reviewed and may widen the argument specifications.
* xarray gate (PLN-006) still waits for the `post/` work at M2.
* SMI genericization and the persistent gh auth browser flow carry
  over unchanged from HND-001.

## 5. Single highest-value next action

Start M2 (PLN-005): the Script builder with validating emit and phase
ordering, consuming the layouts, phases, and typed args now recorded
in the database, with golden-script snapshots as the tier 1 anchor.

## 6. Addendum, same day

After the close above, Geovana asked for a user-facing HTML reference
and agreed to deliver it immediately as PLN-010 layer 1:
`pyflightstream.help()` in `src/pyflightstream/reference.py` renders
the database into one self-contained HTML page (stdlib only,
html.escape plus webbrowser) and opens it; version filter honors
hotfix inheritance and keeps removed commands visible. CommandEntry
gained a loader-supplied `chapter` field for grouping. At M5 the same
renderer feeds the mkdocs command reference (note added to PLN-009).
Four tier 1 tests added; suite at 31 green.
