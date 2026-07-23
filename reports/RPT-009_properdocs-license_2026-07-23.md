# RPT-009: ProperDocs license verification (NFR-02 gate for the docs toolchain)

Date: 2026-07-23. Evidence gathered from the installed package
metadata (`pip show` and the wheel `METADATA` and `LICENSE` files,
properdocs 1.6.7, accessed 2026-07-23) before adding `properdocs` to
the `[dev]` extra as the docs build tool, replacing the MkDocs CLI
after the green drop-in test of the same date (SRS NFR-02: dependency
licenses must be MIT-compatible).

## Finding

| Package | Version checked | License | Verdict |
|---|---|---|---|
| properdocs | 1.6.7 | BSD-2-Clause (`License-Expression: BSD-2-Clause`; wheel LICENSE headed by the MkDocs copyright, Tom Christie) | MIT-compatible |

## Notes

* ProperDocs is the community fork of MkDocs
  (<https://github.com/properdocs/properdocs>, docs at
  <https://properdocs.org/>) and keeps the upstream BSD-2-Clause
  license and copyright line, so the licensing position is identical
  to the MkDocs toolchain it replaces.
* The migration test (isolated worktree, 2026-07-23): strict build
  green on the unchanged sources, page set and rendered content
  identical to the stock MkDocs 1.6.1 build except the generator meta
  tag; the renamed `properdocs.yml` config is found with no
  legacy-filename notice; the `properdocs.structure.files` namespace
  serves the build hook.
* This check gates only the `[dev]` extra (docs tooling). The theme
  and nav plugins already in the extra (mkdocs-material,
  mkdocs-gen-files, and mkdocs-literate-nav, all MIT per their
  installed `License-Expression` metadata, checked 2026-07-23) are
  unchanged; the mkdocs library remains installed transitively
  through mkdocs-material during the ecosystem transition. The core
  runtime dependency set (NFR-06) is untouched.
