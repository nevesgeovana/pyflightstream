# Change log fragments

Each work package of a release writes its change log entries here, in a
file of its own, instead of editing `CHANGELOG.md` and the migration page.
Two packages merged one after the other then never touch the same lines,
and the release folds every fragment in one step.

## The fragment form

A package writes `changelog.d/<package>.md`, for example `changelog.d/B1.md`.
The file holds any of these sections, each optional, each at most once:

- `## Added`
- `## Changed`
- `## Fixed`
- `## Removed`
- `## Migration`

The text under a section is written exactly as it should read in the change
log: bullets, one entry per bullet. Nothing else is allowed in the file: text
before the first section, or a section with another name, is refused by the
assembler, naming the file and the line.

## Folding the fragments

    python scripts/assemble_changelog.py

folds every fragment into the `## [Unreleased]` section of `CHANGELOG.md`,
each section under the `### ` heading of the same name (created when absent),
appended in package order: `P0` first, then the other package names in
natural order (`A`, `B1`, `B2`, ..., `K`). The `## Migration` sections go, in
the same order, to the release's migration page (`docs/migrating-to-0.32.0.md`
unless `--migration-page` names another). The fragments are then deleted and
this file stays.

Running it again changes nothing: an entry already present under its heading
is not added twice, so a run interrupted before the deletion can be repeated.

This folder is not part of the installed package: the wheel carries only
`src/pyflightstream`.
