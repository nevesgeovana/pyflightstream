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
needed. :mod:`pyflightstream.qa.reports` holds the report-naming and
never-overwrite rule all three writers share, so a run is refused before
a licensed seat is spent rather than after. The ``pyfs-qa`` CLI
(:mod:`pyflightstream.qa.cli`) drives all three.

One member of this package spends no seat at all and reads no report:
:mod:`pyflightstream.qa.cost` builds the wall-time cost view from
campaign manifests alone, points down and solver builds across, so a
build that got slower on the same points can be shown. FR-19 has
recorded the field since the v0.3 line; this is what reads it.
"""

from pyflightstream.qa.compat import (
    COMPAT_SCHEMA,
    PROMOTABLE_OUTCOMES,
    Judgment,
    apply_compat,
    compat_report_paths,
    contradicting_evidence,
    read_compat_report,
    read_compat_reports,
    write_compat_report,
)

# THE THREE SERIES HELPERS ARE EXPORTED TOGETHER, which they were not
# until 2026-08-18: `compat_report_paths` was here and its two new
# siblings were not, while the release note presents the three as one
# family, so a reader taking that at its word met an ImportError on two
# of three. Importing `physics` and `drift` here costs no dependency
# this package did not already pull: `compat` reaches `run`, which
# reaches numpy, before any of this runs.
#
# WHAT THIS PACKAGE EXPORTS IS THE PRE-FLIGHT SURFACE, plus compat's
# writer and readers, which predate the rule and stay for compatibility
# within this cycle. `write_physics_report` and `write_drift_report` are
# reached through their own modules. The asymmetry is deliberate and is
# written down because it otherwise reads as meaning: the question a
# caller asks BEFORE spending a licensed seat is the one worth putting
# one import away, and a writer is reached from the module whose run
# object it takes.
from pyflightstream.qa.cost import (
    BuildComparison,
    BuildKey,
    CostCell,
    CostView,
    PointCost,
    PointKey,
    cost_rows,
    cost_view,
)
from pyflightstream.qa.drift import drift_report_paths
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import physics_report_paths
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
from pyflightstream.qa.reports import (
    refuse_existing_report,
    report_paths,
    resolve_report_date,
)
from pyflightstream.qa.specs import PROBE_SPECS

__all__ = [
    "COMPAT_SCHEMA",
    "DEFAULT_ERROR_PATTERNS",
    "BuildComparison",
    "BuildKey",
    "CostCell",
    "CostView",
    "Judgment",
    "PROBE_SPECS",
    "PROMOTABLE_OUTCOMES",
    "PointCost",
    "PointKey",
    "ProbeArtifacts",
    "ProbeEnvironmentError",
    "ProbeOutcome",
    "ProbeResult",
    "ProbeRun",
    "ProbeSpec",
    "QaEvidenceError",
    "Requires",
    "apply_compat",
    "compat_report_paths",
    "contradicting_evidence",
    "cost_rows",
    "cost_view",
    "drift_report_paths",
    "dump_changed",
    "dump_gained",
    "file_effect",
    "fsm_changed",
    "fsm_gained",
    "generate_probe_script",
    "physics_report_paths",
    "printed_line",
    "probe_version",
    "read_compat_report",
    "read_compat_reports",
    "refuse_existing_report",
    "region_printed",
    "report_paths",
    "resolve_report_date",
    "unrecognised_commands",
    "write_compat_report",
]
