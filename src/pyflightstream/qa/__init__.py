"""Probe harness and physics regression tooling.

Pipeline role: produces the evidence behind the command database. Tier 2
probes (:mod:`pyflightstream.qa.probes`) execute each database command in
a minimal script on a licensed machine and classify it into four
outcomes: `verified`, `broken` and `removed` are promotable evidence,
and `unprobed` records why no judgment exists. A build whose solver
refuses the name is `removed` rather than `broken`, because the two
produce different refusals for a caller. A command that runs but does
nothing is `broken`, not `verified`;
:mod:`pyflightstream.qa.compat` writes the compat report under
``reports/compat/`` and promotes database statuses from it. Tier 3 is
here as well: the physics regression matrix
(:mod:`pyflightstream.qa.physics`) and the version-comparison drift
suite (:mod:`pyflightstream.qa.drift`), both run on the synthetic
geometry of :mod:`pyflightstream.qa.geometry` so no research geometry is
needed. The ``pyfs-qa`` CLI (:mod:`pyflightstream.qa.cli`) drives all
three.
"""

from pyflightstream.qa.compat import (
    COMPAT_SCHEMA,
    PROMOTABLE_OUTCOMES,
    Judgment,
    apply_compat,
    contradicting_evidence,
    read_compat_report,
    read_compat_reports,
    write_compat_report,
)
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    ProbeArtifacts,
    ProbeEnvironmentError,
    ProbeOutcome,
    ProbeResult,
    ProbeRun,
    ProbeSpec,
    Requires,
    dump_changed,
    dump_gained,
    file_effect,
    fsm_changed,
    fsm_gained,
    generate_probe_script,
    printed_line,
    probe_version,
    region_printed,
    unrecognised_commands,
)
from pyflightstream.qa.specs import PROBE_SPECS

__all__ = [
    "COMPAT_SCHEMA",
    "DEFAULT_ERROR_PATTERNS",
    "PROBE_SPECS",
    "PROMOTABLE_OUTCOMES",
    "Judgment",
    "ProbeArtifacts",
    "ProbeEnvironmentError",
    "ProbeOutcome",
    "ProbeResult",
    "ProbeRun",
    "ProbeSpec",
    "QaEvidenceError",
    "Requires",
    "apply_compat",
    "contradicting_evidence",
    "dump_changed",
    "dump_gained",
    "fsm_changed",
    "fsm_gained",
    "file_effect",
    "generate_probe_script",
    "printed_line",
    "probe_version",
    "read_compat_report",
    "read_compat_reports",
    "region_printed",
    "unrecognised_commands",
    "write_compat_report",
]
