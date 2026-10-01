# The PDF guides

The guides are LaTeX slide decks, numbered 0 to 7, for the people who run
studies with pyflightstream in a workspace. They are kept beside the code in
the [guide folder](https://github.com/nevesgeovana/pyflightstream/tree/main/guide),
with their sources, and this site links them rather than repeating them. Each
deck is written for one version of the package, and its title page says which.

| Guide | What it covers |
|---|---|
| [0, FlightStream overview](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-00-fts-overview.pdf) | Read first: what FlightStream is, how a panel method solves steady, unsteady and rotating flows, how pyflightstream carries the workflow in a workspace, and the order to read the other guides in |
| [1, Workspaces](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-01-workspaces.pdf) | The workspace tree and its input files, choosing a workflow, running, what a run and its post leave, a workstation and a cluster kept together by sync |
| [2, From the GUI to pyfs](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-02-gui-to-pyfs.pdf) | Every step of a FlightStream GUI session, and the key that takes it in a workspace |
| [3, References](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-03-references.pdf) | The reference file: lengths, the moment point, aliases, frames, rotors and actuator discs |
| [4, Solver setup](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-04-solver-setup.pdf) | The setup file, its keys and the solver commands behind them |
| [5, Post-processing definitions](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-05-pproc-definitions.pdf) | What every post-processing product, reduction and window means |
| [6, FSI](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-06-fsi.pdf) | Fluid-structure interaction: the loop, the structural input, calibration, refusals, examples and limits |
| [7, An offline Python environment](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-guide-07-python-environment-offline.pdf) | Python, a virtual environment and the package on a machine with no internet, Windows and Linux |

The [pyfs-matrix cheatsheet](https://github.com/nevesgeovana/pyflightstream/blob/main/guide/pyfts-cheatsheet-pyfs-matrix.pdf)
is one page, every subcommand and option of `pyfs-matrix` by stage, kept
beside the decks with its LaTeX source in the
[cheatsheet folder](https://github.com/nevesgeovana/pyflightstream/tree/main/guide/latex-sources/cheatsheet). The
[command-line reference](cli/index.md) gives the full text of each option.

On this site, the same workflow starts at [Getting started](getting-started.md)
for the workspace and at
[Your first session with the Python API](tutorial-python-api.md) for the
library.
