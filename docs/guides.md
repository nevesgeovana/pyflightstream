# PDF guides and the website

The PDF guides provide a linear walkthrough. The website provides linked
reference pages and runnable examples. Use both when a task benefits from a
guided sequence and a precise reference.

| Guide | What it covers |
|---|---|
| [1, FlightStream overview](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-01-fts-overview.pdf) | Overview: what FlightStream is, how a panel method solves steady, unsteady and rotating flows, how pyflightstream carries the workflow in a workspace, and the order to read the other guides in |
| [2, Workspaces](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-02-workspaces.pdf) | The workspace tree and its input files, choosing a workflow, running, what a run and its post leave, a workstation and a cluster kept together by sync |
| [3, From the GUI to pyfs](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-03-gui-to-pyfs.pdf) | Every step of a FlightStream GUI session, and the key that takes it in a workspace |
| [4, Cheatsheet](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-04-cheatsheet.pdf) | Ten pages: every command and option of every console tool, then one page for each of the eight stages of the campaign workflow, with its commands, the files it reads and writes, its common errors and a figure |
| [5, References](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-05-references.pdf) | The reference file: lengths, the moment point, aliases, frames, rotors and actuator discs |
| [6, Solver setup](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-06-solver-setup.pdf) | The setup file, its keys and the solver commands behind them |
| [7, Post-processing definitions](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-07-pproc-definitions.pdf) | What every post-processing product, reduction and window means |
| [8, FSI](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-08-fsi.pdf) | Fluid-structure interaction: the loop, the structural input, calibration, refusals, examples and limits |
| [9, An offline Python environment](https://nevesgeovana.github.io/pyflightstream/downloads/pyfts-guide-09-python-environment-offline.pdf) | Python, a virtual environment and the package on a machine with no internet, Windows and Linux |

The PDFs are built from the sources in `guide/` and published as site downloads
with each tagged release. Check the version printed in a guide before applying
its examples to an installation. The website
is the maintained source for technical details and code examples.

Start with [a solver-free first success](getting-started.md#first-success-without-a-solver),
then use Guide 2 for the workspace, Guide 5 for the
[reference artifact](workflow-reference-artifact.md), Guide 6 for
[setup standards](setup-standards.md), and Guide 7 alongside the
[post-processing definitions](post-processing-definitions.md).
