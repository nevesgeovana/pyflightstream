# Architecture

The architectural requirements. The live, generated
[architecture overview](../architecture.md) renders the current state
from the module docstrings at every build; this chapter states the
rules that state must obey.

## The layered pipeline

Dependencies flow strictly downward; no module imports upward:

```
post   qa          engineering data | probe and regression evidence
run    workspace   headless execution | input library, run layout, manifest
cases              simulation and campaign definitions
script results     validating script builder | output parsers
commands           the evidence-backed per-version command database
versions           canonical version identifiers and ordering
```

Side branches follow the same downward-only rule: `fsi` (the
structural side of the aeroelastic loop), `probes` and `farfield`
(survey lattices and conservation ledgers), and the presentation layer
(`reference`, `overview`).

## Architectural rules

!!! decision "AD-01 Downward dependencies only"
    A module may import only from layers below its own. Upward
    imports are forbidden; where an upper-layer entry point is
    exposed from a lower-layer module for user convenience, the
    import is deferred and documented, and introducing a cycle is a
    defect.

!!! decision "AD-02 Single rendering sources"
    Anything presented in two places is rendered from one source: the
    command reference and compatibility matrix from the database, the
    architecture overview from the module docstrings, the docs
    example pages from the example scripts. Nothing generated is
    committed.

    One stated exception, and its condition:
    `reports/requirements-index.json` IS generated and committed,
    because its consumer is a dashboard outside this repository that
    cannot run a generator here and reads the file directly. The
    condition that makes it safe is that a Tier 1 test regenerates and
    compares, and a second test sweeps the SRS independently so a
    parser miss cannot pass as a clean regeneration. An exception
    without that pair is the staleness this decision exists to
    prevent.

!!! decision "AD-03 No global mutable state"
    Script construction and every other stateful operation happen on
    objects; two scripts, two campaigns, or two workspaces never
    interfere through module state (PP-2).

!!! decision "AD-04 Explicit inputs, never guessed"
    FlightStream version and executable path are explicit inputs of a
    campaign. Nothing is read from environment variables or guessed
    from the filesystem.

!!! decision "AD-05 Optional heavy dependencies behind extras"
    The core runtime set stays minimal; [NFR-06](nonfunctional-requirements.md)
    is its single home and this decision does not restate it.
    Structural analysis (`[fsi]`), geometry gating (`[geom]`), manual
    reading for the maintainer tool (`[manual]`, licence card
    `reports/RPT-017_manual-extra-license_2026-08-04.md`), and
    plotting (`[plot]`) are optional extras with license evidence
    recorded before adoption; a missing extra fails with the didactic
    install hint, never an ImportError traceback.

!!! decision "AD-06 One substrate for results (restated 2026-07-27)"
    Tabular results and multidimensional labeled fields rest on one
    substrate ([glossary](index.md#glossary)): the sister library's
    structures over NumPy. pandas and xarray leave the runtime set.

    This decision previously read "tables are pandas; multidimensional
    labeled fields are xarray, and the two never substitute". The
    author's decision of 2026-07-27 does not adapt that reading, it
    invalidates it: the package stops carrying its own table and
    labeled-field stack. The old text is recorded here rather than
    deleted, because a decision that changes content is only readable
    against what it replaced.

    Transition, stated because the code and this decision do not yet
    agree. pandas and xarray are still declared and still imported at
    three sites in `src/` (`results/tables.py`, `farfield/__init__.py`,
    `post/writers.py`, with the test suite as a fourth surface), and
    they stayed through v0.5.0, which shipped without the migration; the removal release number is NFR-06's to state and is unset, that release number
    being stated by [NFR-06](nonfunctional-requirements.md) as its home
    of record. There is no deprecation cycle in between and that is
    deliberate:
    [NFR-20](nonfunctional-requirements.md) governs from 1.0, so a
    consumer finds out on upgrade. The accepted cost is stated in the
    decision record, not softened here.

    Who "a consumer" means is worth naming, because the shorthand for
    this decision has been "the tidy table"
    ([glossary](index.md#glossary)) and that is the smaller half.
    `farfield` carries xarray in the SIGNATURES of its public ledger
    functions, so a rotor or far-field user is affected exactly
    as much as a table user. The changelog notice states both.

!!! decision "AD-07 ITACA as a core dependency (2026-07-23, restated 2026-07-27)"
    pyflightstream and [ITACA](https://github.com/nevesgeovana/itaca)
    are sister libraries by the same author, born integrated: each may
    generate requirements for the other, and each documents awareness
    of the other's architecture (see the
    [sister library page](../sister-itaca.md)). ITACA stays
    solver-agnostic and never imports pyflightstream (its DD-22 and
    DD-23 record the same seam from the other side), so anything
    crossing the seam takes generic arrays and never FlightStream
    probes.

    What changed on 2026-07-27: ITACA was a *future optional* `[itaca]`
    extra and becomes a *core runtime dependency*, because AD-06 now
    rests on it. Two things follow that are easy to get wrong.

    - This is a creation, not a promotion. No `[itaca]` extra has ever
      existed here; the string does not appear in `pyproject.toml`. A
      review pass that asserted otherwise was wrong.
    - The dependency's own metadata propagates to ours: its version pin
      form and its `requires-python` ceiling are governed by
      [NFR-22](nonfunctional-requirements.md), which is their single
      home.

    The direction is not a change of direction. The sister already
    recorded that this driver's pandas and xarray usage migrates to it;
    what the author changed is the pace and the granularity, from per
    structure to one move.

## Command-line surface

Five console entry points, one per operational concern: `pyfs-qa`
(evidence tiers 2 and 3), `pyfs-workspace` (workspace initialization),
`pyfs-matrix` (run-matrix conversion and pre-flight),
`pyfs-fsi` (the coupling-loop executable), and `pyfs-manual`
(reading a vendor manual against the command database, maintainer
tooling outside the run pipeline). CLIs are thin argument
layers over the public Python API; execution paths always require the
explicit executable.
