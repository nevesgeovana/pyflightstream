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
here as well: the physics judge, reductions and references
(:mod:`pyflightstream.qa.physics`), the version-comparison drift diff
(:mod:`pyflightstream.qa.drift`), and the driver that reads
both out of a campaign workspace (:mod:`pyflightstream.qa.matrix`): the
cases are rows of the workspace's physics matrix, run through the run
layer over the workspace's synthetic library, so no research geometry is
needed and no case is stated in Python (PFS-2031.17).
:mod:`pyflightstream.qa.reports` holds the report-naming and
never-overwrite rule all three writers share, so a run is refused before
a licensed seat is spent rather than after. The ``pyfs-qa`` CLI
(:mod:`pyflightstream.qa.cli`) drives all three.

The probe specification catalog (:mod:`pyflightstream.qa.specs`) is cut
into private modules that register into one shared table:
``qa._spec_kit`` holds the instruments and the registry,
``qa._spec_catalog_b``, ``qa._spec_ccs_noise``, ``qa._spec_ccs_mesh`` and
``qa._spec_t1`` hold the entries, and ``qa.specs`` imports them all and
re-exports ``PROBE_SPECS``.

One member of this package spends no seat at all and reads no report:
:mod:`pyflightstream.qa.cost` builds the wall-time cost view from
campaign manifests alone, points down and solver builds across, so a
build that got slower on the same points can be shown. FR-19 has
recorded the field; this is what reads it.
"""

# ``qa.matrix`` (the physics driver over a campaign workspace, PFS-2031.17)
# is NOT re-exported here on purpose: it imports the run and workspace
# layers at module level, and a bare ``import pyflightstream.qa`` would
# then pull both. Reach it as ``pyflightstream.qa.matrix``.

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

# Export the three series helpers together as the pre-flight surface.
# Compat's writer and readers also remain public here for compatibility;
# physics and drift writers are reached through their own modules.
# compat already imports run and numpy, so these imports add no dependency.
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
