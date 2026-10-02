<!-- Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md. -->

# The guides

Nine guides, The pyflightstream guides numbered 1 to 9, for the people who run studies with pyflightstream in a
workspace: eight slide decks and one cheatsheet, each written for one version of the package (its
title page says which), and the guide to the Python library itself.

| Guide | PDF | What it covers |
|---|---|---|
| 1 | `pyfts-guide-01-fts-overview.pdf` | read first: what FlightStream is and how a panel method solves steady, unsteady and rotating flows, the simulation workflow from geometry to post-processing, how pyflightstream carries that workflow in a workspace, and a map of guides 2 to 9 with the order to read them in |
| 2 | `pyfts-guide-02-workspaces.pdf` | the workspace tree, its input files, choosing a workflow and the quasi-steady rotor, running, what a run and its post leave, a Windows workstation and an HPC cluster kept together by sync, space on disk, version control |
| 3 | `pyfts-guide-03-gui-to-pyfs.pdf` | every step of a FlightStream GUI session, and the key that takes it in a workspace |
| 4 | `pyfts-guide-04-cheatsheet.pdf` | the cheatsheet, ten pages: every command and option of every console tool, and one page for each of the eight stages of the campaign workflow |
| 5 | `pyfts-guide-05-references.pdf` | the reference file: lengths, the moment point, aliases, frames, rotors and actuator discs |
| 6 | `pyfts-guide-06-solver-setup.pdf` | the setup file, its keys and the solver commands behind them |
| 7 | `pyfts-guide-07-pproc-definitions.pdf` | what every post-processing product, reduction and window means |
| 8 | `pyfts-guide-08-fsi.pdf` | fluid-structure interaction: the loop, the structural input, calibration, refusals, examples and limits |
| 9 | `pyfts-guide-09-python-environment-offline.pdf` | Python, a virtual environment and the package on a machine with no internet, Windows and Linux |

Each deck ends with its numbered references: the package's documentation
pages (https://nevesgeovana.github.io/pyflightstream/) and the textbooks and
papers behind every physical explanation it gives.

`pyflightstream_user_guide.tex` is the guide to the Python library: versions
and the evidence-backed command database, the script builder and its helpers,
recipes in Python, reading results, and the command-line tools. It is built
with `scripts/build-guide.ps1` and its PDF is not tracked.

## Building the guides

`latex-sources/build-all.ps1` (Windows) or `latex-sources/build-all.sh`
(Linux) compiles the nine guides and copies each PDF here, overwriting it; a
two-digit argument builds one guide. It needs `pdflatex` (MiKTeX or TeX Live)
with beamer, tcolorbox, listings, tikz, adjustbox, microtype and underscore.
The build refuses a source with an em or en dash, and prints the number of
overfull boxes per guide, which must be zero.

## The cheatsheet, guide 4

`latex-sources/04-cheatsheet/` is one document of ten pages, A4 landscape, for
the version `latex-sources/shared/info.tex` names:

- page 1 is every subcommand and every option of `pyfs-matrix`, by stage;
- page 2 is every other command-line tool, the console scripts and the
  `python -m` entries, each with every subcommand and option;
- pages 3 to 10 are the eight stages of the campaign workflow, one page each
  (the workspace and its inputs, the run matrix, the reference, setup and
  pproc artifacts, plan, run, collect and the records, post and products,
  maintenance): what the stage is for, its commands and options with one line
  each, the files it reads and writes, its common errors with their fixes, and
  a figure.

Tier-1 tests (`tests/tier1_offline/test_p0330_cheatsheet.py`,
`test_p0340_cheatsheet_by_stage.py` and `test_p0340_guides.py`) walk every
parser of every console script and refuse the sheet when a command or an
option is missing, when it names one no parser has, and when the compiled PDF
is not ten pages. Its PDF is `pyfts-guide-04-cheatsheet.pdf`, tracked here
beside the others; the build must report no overfull box, so each page keeps
its sheet.

The authorship and license of this folder are in `LICENSE-AND-AUTHORSHIP.md`.
