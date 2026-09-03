"""pyflightstream: version-aware, didactic Python driver for FlightStream.

The package automates the FlightStream panel-method solver through its
ASCII scripting interface. The FlightStream version is an explicit
input: every command emitted is validated against the per-version
command database in ``pyflightstream.commands``, where each entry
cites either the manual page documenting its command or a committed
probe report measuring that the solver accepts one no edition
documents, and carries empirical evidence of its status once probed on
a licensed machine. The script builder refuses at build
time what the solver would reject (or silently ignore) at run time.

Pipeline layers, dependencies flowing strictly downward:

- ``versions``: canonical YY.XXX version identifiers and ordering.
- ``commands``: the evidence-backed per-version command database.
- ``script``: the validating ASCII script builder.
- ``results``: anchor-based parsers for solver output files.
- ``cases``: simulation and campaign definitions.
- ``run`` and ``workspace``: execution, run manifest, and the managed
  workspace (input-artifact library plus run layout). The old
  ``files`` name was a deprecation shim and was removed at v0.4.0.
- ``post``: results into engineering data (sweep assembly, exports).
- ``qa``: probe harness and physics regression tooling.

Side packages follow the same downward-only rule:

- ``fsi``: the structural executable of the aeroelastic coupling loop.
- ``probes`` and ``farfield``: probe lattices for far-field surveys and
  the conservation ledgers computed on them.
- ``reference``: the command reference renderer behind ``help()``.
- ``utils``: maintainer tooling outside the run pipeline entirely,
  imported by nothing a campaign executes (reading a vendor manual
  against the command database).

Cross-cutting support modules, importable from any layer:

- ``options``: the declared, validated machine and QA knobs
  (``get_option``/``set_option`` also re-exported here at top level).
- ``exceptions``: the single catalog of every exception and warning.
- ``testing``: public assertions with quantified violation reports.

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

# The post layer registers the products stage a campaign leaves after
# collection (PFS-2029.15.03); importing it here, above every layer, is
# what puts the stage in the workspace registry the run layer reads.
import pyflightstream.post  # noqa: E402, F401
from pyflightstream.options import (  # noqa: E402
    describe_option,
    get_option,
    option_context,
    reset_option,
    set_option,
)
from pyflightstream.overview import overview  # noqa: E402
from pyflightstream.reference import help  # noqa: E402

# Support levels are exported at the top because the question they
# answer ("is my FlightStream version actually usable here?") is the
# first one a new user asks, and until FR-49 the package answered it
# only by implication: every registered version was called supported,
# including 26.000, which carries evidence for no command at all.
from pyflightstream.support import (  # noqa: E402
    SupportLevel,
    support_level,
    support_table,
    version_support,
)

__all__ = [
    "SupportLevel",
    "__version__",
    "describe_option",
    "get_option",
    "help",
    "option_context",
    "overview",
    "reset_option",
    "set_option",
    "support_level",
    "support_table",
    "version_support",
]
