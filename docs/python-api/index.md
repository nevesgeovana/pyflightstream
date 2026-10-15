# Python API or workspace

Use the workspace when a study fits the supplied run types and should be
declared in a run matrix. Use the Python API when application code must build
scripts, compose custom workflows, or integrate execution and results into a
larger Python program.

The package layers and their responsibilities are described in the generated
[architecture overview](../architecture.md). Start with the
[Python tutorial](../tutorial-python-api.md), then see
[Python in a loop](in-a-loop.md) for repeated planning and result collection.
The generated [API reference](../api/index.md) documents public names, and the
[route map](../workspace-route-map.md) links capabilities to workspace tasks.

## Choose a task

| Task | Start with | Read the result |
|---|---|---|
| Build a validated solver script without launching it | [First Python session](../tutorial-python-api.md), `pyflightstream.script.Script` and `pyflightstream.script.helpers` | [Command reference](../reference/index.md) and [build compatibility](../builds.md) |
| Plan or run a workspace campaign | [Python in a loop](in-a-loop.md), `pyflightstream.workspace` and `pyflightstream.run` | [Planning and cost](../workflow-plan-and-cost.md); use `pyfs-matrix plan` for the CLI route |
| Read existing solver exports | `pyflightstream.results` in the [API reference](../api/index.md) | [Post-processing definitions](../post-processing-definitions.md) for units, frames and missing values |
| Rebuild products from recorded runs | [Additional post](../workflow-additional-post.md), `pyflightstream.post` | [What every product states](../definitions/what-every-product-states.md); use `pyfs-matrix post` for the CLI route |
| Inspect and recover a workspace | [Replay a recorded run](../tutorial-replay.md), `pyflightstream.workspace` | [Restore and rebuild](../restore-and-rebuild.md) |

The generated reference is the canonical home of each symbol's signature and
docstring. These task links explain when to use it without copying that reference.

## Three different kinds of confidence

**API stability** describes whether a Python interface may change. The reference
states each module's maturity. **Solver compatibility** describes the command
evidence for a particular FlightStream build; consult [builds](../builds.md).
**Physical validation** describes comparisons for a particular flow, geometry
and numerical setup. A stable API or an accepted command does not validate a
physical result. Experimental FSI and far-field paths retain the limitations on
their task pages even when their scripts build successfully.
