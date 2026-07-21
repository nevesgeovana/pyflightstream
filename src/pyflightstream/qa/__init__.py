"""Probe harness and physics regression tooling.

Pipeline role: produces the evidence behind the command database. Tier 2
probes (:mod:`pyflightstream.qa.probes`) execute each database command in
a minimal script on a licensed machine and classify it as verified or
broken (a command that runs but does nothing is broken, not verified);
:mod:`pyflightstream.qa.compat` writes the compat report under
``reports/compat/`` and promotes database statuses from it. Tier 3 (the
physics regression matrix, milestone M4) will land here too. The
``pyfs-qa`` CLI (:mod:`pyflightstream.qa.cli`) drives both.
"""

from pyflightstream.qa.compat import (
    COMPAT_SCHEMA,
    apply_compat,
    read_compat_report,
    write_compat_report,
)
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    PROBE_SPECS,
    ProbeArtifacts,
    ProbeEnvironmentError,
    ProbeOutcome,
    ProbeResult,
    ProbeRun,
    ProbeSpec,
    generate_probe_script,
    printed_line,
    probe_version,
)

__all__ = [
    "COMPAT_SCHEMA",
    "DEFAULT_ERROR_PATTERNS",
    "PROBE_SPECS",
    "ProbeArtifacts",
    "ProbeEnvironmentError",
    "ProbeOutcome",
    "ProbeResult",
    "ProbeRun",
    "ProbeSpec",
    "apply_compat",
    "generate_probe_script",
    "printed_line",
    "probe_version",
    "read_compat_report",
    "write_compat_report",
]
