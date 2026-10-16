<div class="docs-hero" markdown>

![Geoverse Goddess owl](assets/sticker.png){ .hero-owl .hero-owl-dark }
![Geoverse Goddess owl](assets/sticker_white.png){ .hero-owl .hero-owl-light }

# pyflightstream

pyflightstream builds and checks FlightStream solver inputs, manages workspace
campaigns, and reads recorded results.

</div>

<div class="grid cards" markdown>

-   :material-rocket-launch-outline: **Start**

    ---

    Create a workspace and render your first checked script without a solver.

    [:material-arrow-right: First success](getting-started.md#first-success-without-a-solver)

-   :material-console: **Command line**

    ---

    Plan a campaign, run it, and keep its inputs and results together.

    [:material-arrow-right: Workspace workflow](workspace-and-workflows.md)

-   :material-language-python: **Python**

    ---

    Build scripts, automate a study, or read recorded results in Python.

    [:material-arrow-right: Choose a task](python-api/index.md)

-   :material-compass-outline: **Concepts**

    ---

    Understand solver versions, supported builds, and what the evidence establishes.

    [:material-arrow-right: Versions and evidence](concepts/versions-and-evidence.md)

</div>

## Where to start

Start with a [solver-free first success](getting-started.md#first-success-without-a-solver):
create a workspace and render a checked script. No FlightStream installation,
license or geometry download is needed for those steps.

- **Command line:** [First campaign](getting-started.md) and the
  [workspace workflow](workspace-and-workflows.md). Planning is solver-free;
  execution needs a separately licensed FlightStream installation.
- **Python:** [Choose a task](python-api/index.md), then use the generated API
  reference for signatures. Script building and reading saved results are
  solver-free; launching FlightStream needs a license.
- **Contribute:** [Contributing guide](contributing.md) for installation,
  offline tests and the clean-room rules. Licensed tests are a separate tier.

## Choose a reading track

| Track | Start here |
|---|---|
| New to FlightStream | [New to FlightStream and the panel method](start/new-to-flightstream.md) |
| GUI user moving to a command line | [From the GUI to pyfs](gui-to-pyfs.md), then [First campaign](getting-started.md) |
| Python API user | [Choose the Python API or workspace](python-api/index.md) |
| Installer or cluster operator | [Install pyflightstream](install.md) |
| Post-processing analyst | [Post-processing artifact](pproc-artifact.md) |
| Rotor analyst | [Reference artifact](workflow-reference-artifact.md) |
| FSI user | [FSI in a workspace](fsi-workspace.md) |
| Existing workspace owner | [Upgrading](upgrading.md) |
| Troubleshooting | [Troubleshooting](troubleshooting.md) |
| Contributor | [Contributing guide](contributing.md) |
| Evaluator | [Versions, builds and evidence](concepts/versions-and-evidence.md) |

The [PDF guides](guides.md) add a structured walkthrough to the task pages.
The [workspace and workflow](workspace-and-workflows.md) page describes the
main campaign route. The website and its examples are the maintained technical
reference.

The [guide source folder](https://github.com/nevesgeovana/pyflightstream/tree/main/guide)
contains the LaTeX and figure sources; compiled PDFs are site downloads.

## Evidence discipline

See [Evidence discipline](srs/philosophy.md#evidence-discipline) for the rule
behind solver claims.
