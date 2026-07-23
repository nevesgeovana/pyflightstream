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

!!! decision "AD-03 No global mutable state"
    Script construction and every other stateful operation happen on
    objects; two scripts, two campaigns, or two workspaces never
    interfere through module state (PP-2).

!!! decision "AD-04 Explicit inputs, never guessed"
    FlightStream version and executable path are explicit inputs of a
    campaign. Nothing is read from environment variables or guessed
    from the filesystem.

!!! decision "AD-05 Optional heavy dependencies behind extras"
    The core runtime set stays minimal (numpy, pandas, PyYAML,
    pydantic, xarray). Structural analysis (`[fsi]`), geometry gating
    (`[geom]`), and plotting (`[plot]`) are optional extras with
    license evidence recorded before adoption; a missing extra fails
    with the didactic install hint, never an ImportError traceback.

!!! decision "AD-06 Domain structures in their domains"
    Tables are pandas; multidimensional labeled fields are xarray.
    The two never substitute for each other.

!!! decision "AD-07 Co-development with ITACA (2026-07-23)"
    pyflightstream and [ITACA](https://github.com/nevesgeovana/itaca)
    are sister libraries by the same author, born integrated: each may
    generate requirements for the other, and each documents awareness
    of the other's architecture (see the
    [sister library page](../sister-itaca.md)). The adapter that emits
    ITACA datasets lives here, behind a future optional `[itaca]`
    extra; ITACA stays solver-agnostic and never imports
    pyflightstream (its DD-22 and DD-23 record the same seam from the
    other side). AD-06 remains in force; it evolves per structure as
    ITACA capabilities land, each migration an evidenced change, never
    a wholesale replacement.

## Command-line surface

Four console entry points, one per operational concern: `pyfs-qa`
(evidence tiers 2 and 3), `pyfs-workspace` (workspace initialization),
`pyfs-matrix` (run-matrix conversion and pre-flight), and
`pyfs-fsi` (the coupling-loop executable). CLIs are thin argument
layers over the public Python API; execution paths always require the
explicit executable.
