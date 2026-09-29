<!-- Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md. -->

# The guides

Eight slide decks, The pyflightstream guides numbered 0 to 7, for the people who run studies with pyflightstream in a
workspace, each written for one version of the package (its title page says
which), and the guide to the Python library itself.

| Guide | PDF | What it covers |
|---|---|---|
| 0 | `pyfts-guide-00-fts-overview.pdf` | read first: what FlightStream is and how a panel method solves steady, unsteady and rotating flows, the simulation workflow from geometry to post-processing, how pyflightstream carries that workflow in a workspace, and a map of guides 1 to 7 with the order to read them in |
| 1 | `pyfts-guide-01-workspaces.pdf` | the workspace tree, its input files, choosing a workflow and the quasi-steady rotor, running, what a run and its post leave, a Windows workstation and an HPC cluster kept together by sync, space on disk, version control |
| 2 | `pyfts-guide-02-gui-to-pyfs.pdf` | every step of a FlightStream GUI session, and the key that takes it in a workspace |
| 3 | `pyfts-guide-03-references.pdf` | the reference file: lengths, the moment point, aliases, frames, rotors and actuator discs |
| 4 | `pyfts-guide-04-solver-setup.pdf` | the setup file, its keys and the solver commands behind them |
| 5 | `pyfts-guide-05-pproc-definitions.pdf` | what every post-processing product, reduction and window means |
| 6 | `pyfts-guide-06-fsi.pdf` | fluid-structure interaction: the loop, the structural input, calibration, refusals, examples and limits |
| 7 | `pyfts-guide-07-python-environment-offline.pdf` | Python, a virtual environment and the package on a machine with no internet, Windows and Linux |

Each deck ends with its numbered references: the package's documentation
pages (https://nevesgeovana.github.io/pyflightstream/) and the textbooks and
papers behind every physical explanation it gives.

`pyflightstream_user_guide.tex` is the guide to the Python library: versions
and the evidence-backed command database, the script builder and its helpers,
recipes in Python, reading results, and the command-line tools. It is built
with `scripts/build-guide.ps1` and its PDF is not tracked.

## Building the decks

`latex-sources/build-all.ps1` (Windows) or `latex-sources/build-all.sh`
(Linux) compiles the eight decks and copies each PDF here, overwriting it; a
two-digit argument builds one deck. It needs `pdflatex` (MiKTeX or TeX Live)
with beamer, tcolorbox, listings, tikz, adjustbox, microtype and underscore.
The build refuses a source with an em or en dash, and prints the number of
overfull boxes per deck, which must be zero.

The authorship and license of this folder are in `LICENSE-AND-AUTHORSHIP.md`.
