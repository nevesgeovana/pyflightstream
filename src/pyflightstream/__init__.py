"""pyflightstream: version-aware, didactic Python driver for FlightStream.

The package automates the FlightStream panel-method solver through its ASCII
scripting interface. The FlightStream version is an explicit input: every
command emitted is validated against the per-version command database in
``pyflightstream.commands``.

Pipeline layers, dependencies flowing strictly downward:

- ``versions``: canonical 26.XXX version identifiers and ordering.
- ``commands``: the command database and per-version registry.
- ``script``: the validating ASCII script builder.
- ``results``: anchor-based parsers for solver output files.
- ``cases``: simulation and campaign definitions.
- ``run`` and ``files``: execution, run manifest, managed file layout.
- ``post``: results into engineering data (sweep assembly, PLTET, exports).
- ``qa``: probe harness and physics regression tooling.
- ``fsi``: seam for the future fluid-structure interaction coupling.

Milestone M0: skeleton only; functionality arrives from milestone M1 on.
"""

__version__ = "0.0.1.dev0"
