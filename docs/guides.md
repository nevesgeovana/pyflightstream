# The PDF guides

The guides are nine documents, numbered 1 to 9 (eight LaTeX slide decks and the cheatsheet), for the people who run
studies with pyflightstream in a workspace. They are kept beside the code in
the [guide folder](https://github.com/nevesgeovana/pyflightstream/tree/main/guide),
with their sources, and this site links them rather than repeating them. Each
deck is written for one version of the package, and its title page says which.

| Guide | What it covers |
|---|---|
| [1, FlightStream overview](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-01-fts-overview.pdf) | Read first: what FlightStream is, how a panel method solves steady, unsteady and rotating flows, how pyflightstream carries the workflow in a workspace, and the order to read the other guides in |
| [2, Workspaces](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-02-workspaces.pdf) | The workspace tree and its input files, choosing a workflow, running, what a run and its post leave, a workstation and a cluster kept together by sync |
| [3, From the GUI to pyfs](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-03-gui-to-pyfs.pdf) | Every step of a FlightStream GUI session, and the key that takes it in a workspace |
| [4, Cheatsheet](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-04-cheatsheet.pdf) | Ten pages: every command and option of every console tool, then one page for each of the eight stages of the campaign workflow, with its commands, the files it reads and writes, its common errors and a figure |
| [5, References](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-05-references.pdf) | The reference file: lengths, the moment point, aliases, frames, rotors and actuator discs |
| [6, Solver setup](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-06-solver-setup.pdf) | The setup file, its keys and the solver commands behind them |
| [7, Post-processing definitions](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-07-pproc-definitions.pdf) | What every post-processing product, reduction and window means |
| [8, FSI](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-08-fsi.pdf) | Fluid-structure interaction: the loop, the structural input, calibration, refusals, examples and limits |
| [9, An offline Python environment](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-09-python-environment-offline.pdf) | Python, a virtual environment and the package on a machine with no internet, Windows and Linux |

The cheatsheet, guide 4, is kept beside the others with its LaTeX source in the
[cheatsheet folder](https://github.com/nevesgeovana/pyflightstream/tree/main/guide/latex-sources/04-cheatsheet). The
[command-line reference](cli/index.md) gives the full text of each option.

On this site, the same workflow starts at [Getting started](getting-started.md)
for the workspace and at
[Your first session with the Python API](tutorial-python-api.md) for the
library.
