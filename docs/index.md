# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. MIT licensed.

Status: v0.4.0 is the current release on PyPI; the changelog records what each
release adds. Five command-line tools ship with the package: `pyfs-qa`
(probes, physics regression, drift), `pyfs-workspace` (campaign
workspace init), `pyfs-matrix` (run-matrix convert and pre-flight),
`pyfs-fsi` (the aeroelastic coupling executable), and `pyfs-manual`
(maintainer tool: compares a vendor manual against the command
database, needs the `[manual]` extra).

## The idea in one paragraph

FlightStream is scripted through ASCII command files, and the solver is
under active development, with intermediate hotfix builds consolidating
user requests into stable releases; the command set evolves with it. This
package makes the FlightStream version an explicit input. A per-version command
database, with a manual page or probe-report citation on every entry and
empirical probe evidence for every verified status, backs a script builder
that refuses to
emit anything invalid for the requested version. Old versions are only ever
added, never dropped.

## The documentation

* [Software Requirements Specification](srs/index.md): the living SRS,
  from the founding requirements to the usage-feedback line, each with
  origin, status, and evidence.
* [Architecture overview](architecture.md): the layered pipeline and one
  section per subpackage, generated at every docs build from the live
  module docstrings. `pyflightstream.overview()` renders the same page
  offline.
* [Getting started](getting-started.md): install, pick a version, build a
  script, declare and pre-flight a campaign, read the results. Half an hour,
  and no solver until the last step.
* [Replaying a recorded run](tutorial-replay.md): what the manifest keeps,
  how to rebuild the exact invocation from it, how to tell whether the
  evidence still matches, and what a record cannot give you.
* [Command reference](reference/index.md): generated from the database at
  every docs build, one page per manual chapter, with per-version evidence
  for every command. `pyflightstream.help()` renders the same database
  offline.
* [Compatibility matrix](compatibility.md): every command against every
  registered FlightStream version, generated from the same database. Cells
  are filled only by evidence: for `documented`, the manual page or a
  committed probe report where no edition documents the command; for
  `verified` and `broken`, a committed probe report. Empty cells are
  honest gaps awaiting backfill.
* [House conventions](conventions.md): the naming and nomenclature rules
  the library holds itself to, generated from `reference.CONVENTIONS`,
  the same source as the offline `help()` section.
* [Mesh inputs and GUI-only operations](mesh-inputs.md): the supported
  workflow when a step exists in the GUI but has no scripting command,
  the canonical mesh input routes, and the mesh format policy.
* [Sister library (ITACA)](sister-itaca.md): the co-development model,
  the division of labor, and the cross-requirement convention shared
  with the ITACA analysis library.

## Evidence discipline

The three QA tiers behind the statuses:

* Tier 1 runs in CI without the solver: schema integrity, builder
  goldens, parser fixtures.
* Tier 2 probes command validity on a licensed machine; reports live
  under `reports/compat/` and statuses are promoted only from them.
* Tier 3 runs a physics regression matrix and a cross-version drift
  suite; reports live under `reports/physics/`.

The [campaign from a run matrix](examples/campaign_matrix.md) example
already walks the run-matrix to `campaign.toml` to pre-flight path
end to end; the LaTeX user guide (`guide/`) covers the full workflow.

## Planned next

* Campaign tutorial page: the workspace input library, pre-flight,
  and resumable sweeps as a narrated docs-site walkthrough.
