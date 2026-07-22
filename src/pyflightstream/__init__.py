"""pyflightstream: version-aware, didactic Python driver for FlightStream.

The package automates the FlightStream panel-method solver through its
ASCII scripting interface. The FlightStream version is an explicit
input: every command emitted is validated against the per-version
command database in ``pyflightstream.commands``, where each entry
carries a manual page citation and, when probed on a licensed machine,
empirical evidence of its status. The script builder refuses at build
time what the solver would reject (or silently ignore) at run time.

Pipeline layers, dependencies flowing strictly downward:

- ``versions``: canonical 26.XXX version identifiers and ordering.
- ``commands``: the evidence-backed per-version command database.
- ``script``: the validating ASCII script builder.
- ``results``: anchor-based parsers for solver output files.
- ``cases``: simulation and campaign definitions.
- ``run`` and ``files``: execution, run manifest, managed file layout.
- ``post``: results into engineering data (sweep assembly, exports).
- ``qa``: probe harness and physics regression tooling.

Side packages follow the same downward-only rule:

- ``fsi``: the structural executable of the aeroelastic coupling loop.
- ``probes`` and ``farfield``: probe lattices for far-field surveys and
  the conservation ledgers computed on them.
- ``reference``: the command reference renderer behind ``help()``.

Where to start:

- :func:`pyflightstream.help` opens the offline HTML command reference,
  rendered from the installed command database.
- :func:`pyflightstream.overview` opens the offline HTML architecture
  overview, rendered from the live module docstrings.
- The published docs site carries the same reference and overview plus
  the compatibility matrix and worked examples.
"""

from importlib import metadata

try:
    __version__ = metadata.version("pyflightstream")
except metadata.PackageNotFoundError:
    # Source tree imported without an installation (for example a
    # checkout placed on sys.path): no distribution metadata exists, so
    # the version is honestly unknown instead of a stale hardcoded
    # string. Install the package (pip install -e .) to expose the real
    # version.
    __version__ = "0.0.0+uninstalled"

from pyflightstream.overview import overview  # noqa: E402
from pyflightstream.reference import help  # noqa: E402

__all__ = ["__version__", "help", "overview"]
