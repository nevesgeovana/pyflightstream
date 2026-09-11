"""Tier 3 physics regression: the judge, the reductions, the references, the report.

Pipeline role: the physics cases are judged here. A case is a set of
metrics reduced from solved points (:func:`phy01_metrics`,
:func:`phy02_metrics`, :func:`phy05_metrics`, :func:`phy06_metrics`),
compared against a committed reference inside WARN and FAIL bands
(:func:`compare_metrics`), and written as a dated ``PHY-*`` report pair
under ``reports/physics/`` (:func:`write_physics_report`). References
live as package data in ``qa/references/`` and change only through
:func:`update_reference`, which demands a reason string; a reference
update never shares a commit with code changes (SAD Section 11).

WHERE THE CASES ARE STATED, since 0.13.0 (PFS-2031.17, the design decision B of
2026-09-08 in design study 66): as rows of a run matrix in a campaign
workspace, built by the package's own workflows, and nowhere in Python.
``tests/tier3_licensed/matriz_physics.fs`` states them: row 5001 is
PHY-01, 5002 and 5003 are PHY-02, 5005 is PHY-05 and 5006 is PHY-06, each
row's preset written to emit exactly the lines the hand-built script
emitted. :mod:`pyflightstream.qa.matrix` is the driver that runs that
matrix through the run layer, reduces the records with the functions
here and writes the report; ``pyfs-qa physics --workspace <root>`` is
its command line. Until 0.13.0 this module built every case as a script
in Python (``build_phy01_script`` and its siblings) and ran it itself;
those builders retired with the decision, because two builders of one
case drift apart and the diff of their scripts was the only thing that
said so (RPT-042 is the measurement that the workflow reproduces every
coefficient inside the reference bands).

What a case measures, kept here because the reductions carry it. PHY-01
is the wing polar of a synthetic NACA 0012 rectangular wing of aspect
ratio 8: the total lift coefficient per angle, the lift slope and the
induced drag at the reference angle. Physical anchor: finite-wing theory
puts the lift slope near 2*pi / (1 + 2/AR) = 5.0 per radian, so a grossly
wrong slope points at a broken import or symmetry setup rather than at
solver drift. PHY-02 is the symmetry equivalence: the open-root half wing
under MIRROR symmetry with symmetry loads enabled must reproduce the
full-span coefficients on the same full planform reference area. PHY-05
is the rigid unsteady periodic propeller after a revolution and a half.
PHY-06 is the time march of the static wing against its own steady polar.

The SMI class (FR-27) is the local-only pair over the research
simulation files, whose geometry never enters Git (CONTRIBUTING.md
invariant 5). It keeps its script builder, its metric specifications and
its references here, and has no runner since 0.13.0: it runs again when
it is a row of a private workspace, which is the next release's work.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import numpy as np
import yaml

from pyflightstream._errors import PyflightstreamError
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import WingSpec
from pyflightstream.qa.reports import (
    refuse_existing_report,
    report_paths,
    resolve_report_date,
)
from pyflightstream.run import (
    ExecutorRecord,
    describe_invocation,
)
from pyflightstream.script import Script
from pyflightstream.versions import known_versions

PHYSICS_SCHEMA = "pyflightstream-physics-report/1"
REFERENCE_SCHEMA = "pyflightstream-physics-reference/1"

__all__ = [
    "Verdict",
    "MetricSpec",
    "ReferenceBand",
    "CaseReference",
    "PointResult",
    "CaseResult",
    "PhysicsRun",
    "PhysicsEnvironmentError",
    "PHYSICS_CASES",
    "SMI_CASES",
    # PUBLIC BECAUSE THE CHANGELOG BREAKS THEM. `PhysicsCase` is the
    # element type of the two exported inventories above, so a caller
    # holding `PHYSICS_CASES["PHY-01"]` could not annotate it or build
    # one; `case_table` is the function whose key this release renames.
    # `PhysicsCase` and `case_table` were announced as public breaks
    # while being absent from this list, which also kept them outside the
    # FR-39 bare-raise walk in `tests/tier1_offline/test_exceptions_catalog.py`, since
    # that walk follows `__all__` where a module declares one.
    "PhysicsCase",
    "case_table",
    # `registered_cases` was already here and is listed beside them
    # because it is the third half of the same inventory surface; the
    # comment above covered two names and sat over three until
    # 2026-08-18.
    "registered_cases",
    "build_smi_script",
    # The reductions, exported since 0.13.0 because the workspace driver
    # and the tier-3 test both call them: they are the one statement of
    # what each case measures now that no script builder carries it.
    "phy01_metrics",
    "phy02_metrics",
    "phy05_metrics",
    "phy06_metrics",
    "smi_metrics",
    "compare_metrics",
    "load_reference",
    "update_reference",
    "physics_report_paths",
    "write_physics_report",
]


class PhysicsEnvironmentError(PyflightstreamError, RuntimeError):
    """The physics run cannot start as configured.

    Raised before any row runs: a workspace without the physics matrix,
    rows naming two builds, or a row naming a case the registry does not
    know must surface immediately, not after minutes of solver time.
    """


class Verdict(enum.StrEnum):
    """Judgment of one measured metric against its stored reference.

    ``PASS``: inside the WARN band. ``WARN``: outside WARN but inside
    FAIL; the metric moved and deserves triage, the suite keeps going.
    ``FAIL``: outside the FAIL band; a physics regression, a database
    error, or a stale reference (the triage of the run-physics skill).
    ``NO_REFERENCE``: no stored reference yet; the measured value is
    reported so :func:`update_reference` can seed one.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NO_REFERENCE = "no_reference"


@dataclass(frozen=True)
class MetricSpec:
    """Declaration of one case metric and its default tolerance bands.

    Attributes
    ----------
    name : str
        Metric identifier, for example ``"CL_a4"``.
    description : str
        What the metric measures, with units where applicable.
    kind : str
        ``"rel"``: bands are fractions of the reference magnitude,
        for O(1) coefficients. ``"abs"``: bands are absolute half
        widths in the metric's own unit, for near-zero metrics whose
        relative error is meaningless (a symmetric section's CL at
        zero incidence, for example).
    warn : float
        Default WARN half width used when seeding a reference.
    fail : float
        Default FAIL half width; must exceed ``warn``.
    """

    name: str
    description: str
    kind: str = "rel"
    warn: float = 0.02
    fail: float = 0.05

    def __post_init__(self) -> None:
        """Reject band declarations that could never judge coherently."""
        if self.kind not in ("rel", "abs"):
            raise QaEvidenceError(
                f"metric {self.name}: kind must be 'rel' or 'abs', got {self.kind!r}"
            )
        if not 0 < self.warn < self.fail:
            raise QaEvidenceError(
                f"metric {self.name}: bands need 0 < warn < fail, got {self.warn}, {self.fail}"
            )


@dataclass(frozen=True)
class ReferenceBand:
    """Stored reference value of one metric with its tolerance bands.

    Attributes mirror :class:`MetricSpec` bands; ``value`` is the
    accepted metric value the bands center on.
    """

    value: float
    warn: float
    fail: float
    kind: str

    def judge(self, measured: float) -> Verdict:
        """Judge a measured value against this band."""
        deviation = abs(measured - self.value)
        scale = abs(self.value) if self.kind == "rel" else 1.0
        if deviation <= self.warn * scale:
            return Verdict.PASS
        if deviation <= self.fail * scale:
            return Verdict.WARN
        return Verdict.FAIL


@dataclass(frozen=True)
class CaseReference:
    """The committed reference of one physics case.

    Attributes
    ----------
    case_id : str
        Case identifier (``PHY-01`` .. ``PHY-06``).
    fs_version_basis : str
        Canonical FlightStream version the reference values came from.
    updated : str
        ISO date of the last reference update.
    reason : str
        The reason string recorded by :func:`update_reference`.
    metrics : dict of str to ReferenceBand
        Reference value and bands per metric.
    """

    case_id: str
    fs_version_basis: str
    updated: str
    reason: str
    metrics: dict[str, ReferenceBand]


@dataclass(frozen=True)
class PointResult:
    """One solved sweep point of a physics case.

    Attributes
    ----------
    alpha_deg : float
        Angle of attack in degrees, positive nose up.
    total : dict of str to float
        The Total coefficient row of the loads spreadsheet (CL, CDi,
        and companions), analysis-frame coefficients.
    iterations : int
        Solver iteration counter at export.
    converged : bool
        Whether the solver stopped below its iteration limit (the
        steady-mode convergence signal of the M2 assessor).
    label : str
        Point identifier shown in reports; distinguishes points that
        share an angle, such as the full and half models of PHY-02.
        Empty defaults to the angle itself.
    """

    alpha_deg: float
    total: dict[str, float]
    iterations: int
    converged: bool
    label: str = ""


@dataclass(frozen=True)
class CaseResult:
    """Everything one physics case produced in one run.

    Attributes
    ----------
    case_id, title : str
        Case identity.
    geometry : str
        One-line description of the generated geometry.
    points : tuple of PointResult
        Solved sweep points, in sweep order.
    metrics : dict of str to float
        Measured metric values.
    verdicts : dict of str to Verdict
        Judgment per metric (``NO_REFERENCE`` when no reference file
        exists yet).
    reference : CaseReference or None
        The stored reference used, when one exists.
    error : str or None
        Failure description when the case aborted; a failed case
        reports instead of raising so one broken case cannot hide the
        others' evidence.
    """

    case_id: str
    title: str
    geometry: str
    points: tuple[PointResult, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    reference: CaseReference | None = None
    error: str | None = None


@dataclass(frozen=True)
class PhysicsRun:
    """One complete Tier 3 physics run on a licensed machine."""

    version: str
    fs_exe_name: str
    package_version: str
    results: tuple[CaseResult, ...]
    solver_identity: tuple[str, ...] = ()
    #: Lowercase hexadecimal sha256 of the executable's bytes, or
    #: ``None`` when it was not measured. The name does not identify the
    #: binary: the vendor installer calls four registered builds
    #: ``Flightstream_2612.exe``, so a committed report naming one can
    #: mean any of them and a publication citing it cannot say which.
    fs_exe_sha256: str | None = None
    #: How the solver was called, read off the first point that ran
    #: (PFS-2012.04); None when no point reached the solver, and the
    #: report then states the asserted sentence and says so.
    executor: ExecutorRecord | None = None
    #: One sentence naming what the run read, ``"<matrix> in workspace
    #: <name>"``, written into the report so a reader can find the rows
    #: the cases came from. The workspace is named by its directory and
    #: never by its path: a report is committed, and a machine's path is
    #: not (the container-directory guard of the house style).
    source: str | None = None

    def verdict_counts(self) -> dict[str, int]:
        """Count metric verdicts over every case, for the summary line."""
        counts = {verdict.value: 0 for verdict in Verdict}
        for result in self.results:
            for verdict in result.verdicts.values():
                counts[verdict.value] += 1
        return counts


# --------------------------------------------------------------------------
# The reductions: what each case measures, from its solved points
# --------------------------------------------------------------------------

#: The wing the PHY-01, PHY-02 and PHY-06 references were recorded on: a
#: NACA 0012 rectangular wing of chord 1 m and span 8 m. The workspace
#: rows open a saved simulation of the same planform (``12_WING_PHY.fsm``,
#: whose provenance record names the spec it was meshed from); this
#: constant is what a maintainer script generates the STL from.
PHY01_WING = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=25, n_span=40)
PHY01_ALPHAS_DEG = (0.0, 2.0, 4.0, 6.0)
PHY01_ITERATIONS = 500
PHY01_CONVERGENCE = 1.0e-5
PHY02_ALPHA_DEG = 4.0

#: The four aggregated coefficients PHY-05 and the SMI class judge.
_TOTAL_METRIC_NAMES = ("CL", "CDi", "CDo", "CMy")


#: Names 0.13.0 removed from this module (PFS-2031.17, the CHANGELOG entry
#: marks them BREAKS): each ran the physics cases through a recipe path
#: that no longer exists, so no shim could answer for them. An import
#: of one is refused with the release and the call that replaced it,
#: rather than with a bare name error.
REMOVED_IN_0_13_0: frozenset[str] = frozenset(
    {
        "build_phy01_script",
        "build_phy02_script",
        "build_phy05_script",
        "build_phy06_unsteady_script",
        "run_physics",
        "run_drift",
    }
)


def __getattr__(name: str) -> object:
    if name in REMOVED_IN_0_13_0:
        raise ImportError(
            f"{__name__}.{name} was removed in 0.13.0 (PFS-2031.17): the physics cases "
            "are rows of a campaign workspace now. Call "
            "pyflightstream.qa.matrix.physics_from_workspace(root) or "
            "drift_from_workspace(root, ...), with root the workspace (CLI: --workspace) "
            "of pyfs-qa physics and pyfs-qa drift.",
            name=name,
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def phy01_metrics(points: list[PointResult]) -> dict[str, float]:
    """Reduce the PHY-01 sweep points to the case metrics.

    The lift slope comes from a least-squares line over the whole
    sweep, in per-radian units so it lands next to the finite-wing
    anchor 2*pi / (1 + 2/AR).
    """
    metrics: dict[str, float] = {}
    for point in points:
        tag = f"a{point.alpha_deg:g}"
        metrics[f"CL_{tag}"] = point.total["CL"]
    alphas_rad = np.radians([point.alpha_deg for point in points])
    lifts = [point.total["CL"] for point in points]
    metrics["CL_slope_per_rad"] = float(np.polyfit(alphas_rad, lifts, 1)[0])
    reference_point = next(point for point in points if point.alpha_deg == 4.0)
    metrics["CDi_a4"] = reference_point.total["CDi"]
    return metrics


def phy02_metrics(full: PointResult, half: PointResult) -> dict[str, float]:
    """Reduce the PHY-02 pair to the equivalence metrics.

    Both models use the full planform reference area, so the mirrored
    half must reproduce the full-span coefficients; the deltas are the
    physics content and sit near zero, hence absolute bands.
    """
    return {
        "CL_full_a4": full.total["CL"],
        "CL_half_a4": half.total["CL"],
        "delta_CL_a4": half.total["CL"] - full.total["CL"],
        "delta_CDi_a4": half.total["CDi"] - full.total["CDi"],
    }


def phy05_metrics(point: PointResult) -> dict[str, float]:
    """Reduce the PHY-05 final step to the four aggregated coefficients.

    The propeller's evidence is the Total row at the last of its 54
    steps: the blade sector's lift (near zero, the loads balance around
    the disc), the axial force coefficient (negative, a net thrust), the
    viscous drag and the pitching moment. The tier-3 test carried this
    selection inline until 0.13.0; it lives here so the driver and the
    test reduce the same way.
    """
    return {name: point.total[name] for name in _TOTAL_METRIC_NAMES}


def phy06_metrics(steady: list[PointResult], unsteady: list[PointResult]) -> dict[str, float]:
    """Reduce the two polars of PHY-06 to the equivalence metrics.

    Per angle, the unsteady-final minus steady deltas of CL, CD (CDi +
    CDo; the loads Total row carries no combined column) and CMy, then
    the least-squares lift and pitching-moment slopes of each polar in
    per-radian units, which is what :func:`_phy06_metric_specs`
    declares. The two polars are matched BY ANGLE, not by position: a
    march at an angle the steady polar did not solve is refused rather
    than paired with whatever sat at the same index.

    Parameters
    ----------
    steady : list of PointResult
        The steady polar, the PHY-01 row's points in the workspace.
    unsteady : list of PointResult
        The unsteady-final polar, the PHY-06 row's points, at the same
        angles.

    Raises
    ------
    QaEvidenceError
        When the two polars do not solve the same angles. A ``ValueError``
        by base, per FR-39, so a caller's ``except ValueError`` catches it.
    """
    by_alpha_steady = {point.alpha_deg: point for point in steady}
    by_alpha_unsteady = {point.alpha_deg: point for point in unsteady}
    if set(by_alpha_steady) != set(by_alpha_unsteady):
        raise QaEvidenceError(
            "PHY-06 pairs the unsteady march with the steady polar at the same angles; "
            f"steady solved {sorted(by_alpha_steady)} deg and unsteady "
            f"{sorted(by_alpha_unsteady)} deg. The steady polar is the PHY-01 row, so "
            "both rows sweep the same SWEEP_VALUES."
        )
    alphas = sorted(by_alpha_steady)
    metrics: dict[str, float] = {}
    for alpha in alphas:
        tag = f"a{alpha:g}"
        s, u = by_alpha_steady[alpha].total, by_alpha_unsteady[alpha].total
        metrics[f"delta_CL_{tag}"] = u["CL"] - s["CL"]
        metrics[f"delta_CD_{tag}"] = (u["CDi"] + u["CDo"]) - (s["CDi"] + s["CDo"])
        metrics[f"delta_CMy_{tag}"] = u["CMy"] - s["CMy"]
    alphas_rad = np.radians(alphas)
    for label, series in (("steady", by_alpha_steady), ("unsteady", by_alpha_unsteady)):
        lifts = [series[alpha].total["CL"] for alpha in alphas]
        moments = [series[alpha].total["CMy"] for alpha in alphas]
        metrics[f"CL_slope_{label}_per_rad"] = float(np.polyfit(alphas_rad, lifts, 1)[0])
        metrics[f"CMy_slope_{label}_per_rad"] = float(np.polyfit(alphas_rad, moments, 1)[0])
    return metrics


@dataclass(frozen=True)
class PhysicsCase:
    """One entry of the physics case registry.

    Attributes
    ----------
    case_id, title : str
        Identity shown in reports.
    metric_specs : tuple of MetricSpec
        Declared metrics with the default bands used at reference
        seeding time.

        NO RUNNER, since 0.13.0. The entry used to carry the callable
        that built and ran the case's scripts; a case is a row of the
        workspace matrix now, and :mod:`pyflightstream.qa.matrix` maps
        the row to the reduction by the case id the row's DESCRIPTION
        names (PFS-2031.17).
    minimum_version : str, optional
        Earliest canonical identifier this case's command set has
        evidence for. None means every registered version.

        A MINIMUM AND NOT AN ENUMERATION, since 2026-08-17, and the
        difference is that an enumeration excludes the newest build every
        time. The two unsteady cases were pinned to 26.120 alone, then to
        a tuple naming 26.120, 26.121 and 26.122, and the pin's own
        stated reason was a backfill owed for builds EARLIER than 26.120:
        a minimum, written as a list. So every arriving build fell
        outside it until somebody appended it by hand, which happened to
        26.121 and 26.122 on 2026-08-11 and to 26.123 on 2026-08-17. The
        intent is unchanged and the decay is gone.
    """

    case_id: str
    title: str
    metric_specs: tuple[MetricSpec, ...]
    minimum_version: str | None = None

    @property
    def specs_by_name(self) -> dict[str, MetricSpec]:
        """The metric specifications keyed by metric name."""
        return {spec.name: spec for spec in self.metric_specs}

    def supports(self, canonical: str) -> bool:
        """Whether the case's command set has evidence for ``canonical``.

        ``minimum_version`` is None for cases whose commands are
        evidenced on every registered version; otherwise the case
        supports that build and every build after it.

        AFTER is read from the ordering authority's list position and
        NOT from the identifier, because the identifier does not encode
        release order: 26.100 is the February 2026 build and 26.101 the
        May one, which string comparison happens to get right, and the
        25 series was registered later and belongs at the FRONT, which it
        does not.
        """
        if self.minimum_version is None:
            return True
        order = [version.canonical for version in known_versions()]
        if canonical not in order or self.minimum_version not in order:
            return False
        return order.index(canonical) >= order.index(self.minimum_version)


PHY06_ALPHAS_DEG = (0.0, 2.0, 4.0, 6.0)


def _phy06_metric_specs() -> tuple[MetricSpec, ...]:
    """Declare the PHY-06 polar-equivalence metrics.

    Per sweep angle, the steady-versus-unsteady deltas of CL, CD
    (CDi + CDo; the loads Total row carries no combined column), and
    CMy must sit near zero: the time march of the static wing
    asymptotes to the steady solution at every incidence, which is
    the per-alpha trend confirmation. The two lift slopes then pin
    the trend itself against the finite-wing anchor
    2*pi/(1 + 2/AR) = 5.0 for AR 8, and the two pitching-moment
    slopes pin the CMy trend without an analytic anchor.
    """
    specs: list[MetricSpec] = []
    for alpha in PHY06_ALPHAS_DEG:
        tag = f"a{alpha:g}"
        specs.append(
            MetricSpec(
                f"delta_CL_{tag}",
                f"CL(unsteady) - CL(steady) at {alpha:g} deg",
                kind="abs",
                warn=0.005,
                fail=0.02,
            )
        )
        specs.append(
            MetricSpec(
                f"delta_CD_{tag}",
                f"CD(unsteady) - CD(steady) at {alpha:g} deg (CD = CDi + CDo)",
                kind="abs",
                warn=0.001,
                fail=0.004,
            )
        )
        specs.append(
            MetricSpec(
                f"delta_CMy_{tag}",
                f"CMy(unsteady) - CMy(steady) at {alpha:g} deg",
                kind="abs",
                warn=0.005,
                fail=0.02,
            )
        )
    specs.append(
        MetricSpec(
            "CL_slope_steady_per_rad",
            "least-squares lift slope of the steady polar, 1/rad "
            "(finite-wing anchor 2*pi/(1 + 2/AR) = 5.0 for AR 8)",
        )
    )
    specs.append(
        MetricSpec(
            "CL_slope_unsteady_per_rad",
            "least-squares lift slope of the unsteady-final polar, 1/rad; "
            "must match the steady slope inside the band",
        )
    )
    specs.append(
        MetricSpec(
            "CMy_slope_steady_per_rad",
            "least-squares pitching-moment slope of the steady polar, 1/rad",
        )
    )
    specs.append(
        MetricSpec(
            "CMy_slope_unsteady_per_rad",
            "least-squares pitching-moment slope of the unsteady-final polar, 1/rad",
        )
    )
    return tuple(specs)


PHYSICS_CASES: dict[str, PhysicsCase] = {
    "PHY-01": PhysicsCase(
        case_id="PHY-01",
        title="NACA wing polar (synthetic NACA 0012, AR 8)",
        metric_specs=(
            MetricSpec(
                "CL_a0",
                "total CL at 0 deg; 0 by symmetry, so the band is absolute",
                kind="abs",
                warn=0.005,
                fail=0.02,
            ),
            MetricSpec("CL_a2", "total CL at 2 deg incidence"),
            MetricSpec("CL_a4", "total CL at 4 deg incidence"),
            MetricSpec("CL_a6", "total CL at 6 deg incidence"),
            MetricSpec(
                "CL_slope_per_rad",
                "least-squares lift slope over the sweep, 1/rad "
                "(finite-wing anchor 2*pi/(1 + 2/AR) = 5.0 for AR 8)",
            ),
            MetricSpec(
                "CDi_a4",
                "induced drag coefficient at 4 deg",
                warn=0.05,
                fail=0.15,
            ),
        ),
    ),
    "PHY-02": PhysicsCase(
        case_id="PHY-02",
        title="Half versus full symmetry equivalence (NACA 0012, AR 8)",
        metric_specs=(
            MetricSpec("CL_full_a4", "total CL of the full-span baseline at 4 deg"),
            MetricSpec(
                "CL_half_a4",
                "total CL of the mirrored half model at 4 deg, symmetry loads enabled",
            ),
            MetricSpec(
                "delta_CL_a4",
                "CL(half) - CL(full) at 4 deg; zero in exact equivalence",
                kind="abs",
                warn=0.005,
                fail=0.02,
            ),
            MetricSpec(
                "delta_CDi_a4",
                "CDi(half) - CDi(full) at 4 deg; zero in exact equivalence",
                kind="abs",
                warn=0.0005,
                fail=0.002,
            ),
        ),
    ),
    "PHY-05": PhysicsCase(
        case_id="PHY-05",
        title="Rigid unsteady periodic propeller (generic BladeSpec blade)",
        metric_specs=(
            MetricSpec(
                "CL",
                "total CL of the blade sector at the final step; near zero "
                "as the loads balance around the disc, so the band is absolute",
                kind="abs",
                warn=0.002,
                fail=0.01,
            ),
            MetricSpec(
                "CDi",
                "total axial force coefficient (negative: net thrust) at the final of 54 steps",
                warn=0.01,
                fail=0.03,
            ),
            MetricSpec(
                "CDo",
                "total viscous drag coefficient at the final step; near zero",
                kind="abs",
                warn=0.0005,
                fail=0.002,
            ),
            MetricSpec(
                "CMy",
                "total pitching moment coefficient at the final step",
                warn=0.01,
                fail=0.03,
            ),
        ),
        minimum_version="26.120",
    ),
    "PHY-06": PhysicsCase(
        case_id="PHY-06",
        title="Steady versus unsteady polar equivalence (NACA 0012, AR 8)",
        metric_specs=_phy06_metric_specs(),
        minimum_version="26.120",
    ),
}


# --------------------------------------------------------------------------
# SMI drift class: local-only cases over the research geometry
# --------------------------------------------------------------------------
#
# The SMI simulation files live under _private/geometry/smi/ and never
# enter Git (CONTRIBUTING.md invariant 5); the committed reports carry the
# aggregated Total coefficients plus the sha256 of the opened file, never
# the geometry itself. Reference values use the unit reference area and
# length convention (coefficients scale consistently on both sides of any
# comparison, which is all drift needs). The class has no runner since
# 0.13.0 (PFS-2031.17): the hand-built run machinery retired with the
# PHY builders, and an SMI case runs again as a row of a private
# workspace whose recipe emits this script.

SMI_ALPHA_DEG = 2.0
SMI_VELOCITY_M_S = 30.0


def _smi_metric_specs(kind: str) -> tuple[MetricSpec, ...]:
    """Build the four aggregated-coefficient specs of one SMI case.

    Band kind is a per-case calibration decided from the first 26.120
    measurement (PHY-26120_2026-07-21_smi): the isolated body's
    coefficients sit near zero, where only absolute half widths make
    sense, while the full configuration's unit-reference coefficients
    are O(1..100), where the same absolute width would be absurdly
    tight and relative bands say what the research means by drift.
    """
    if kind == "abs":
        bands = {
            "CL": (0.005, 0.02),
            "CDi": (0.002, 0.01),
            "CDo": (0.002, 0.01),
            "CMy": (0.005, 0.02),
        }
    else:
        bands = {name: (0.005, 0.02) for name in _TOTAL_METRIC_NAMES}
    descriptions = {
        "CL": "aggregated total lift coefficient at 2 deg (unit reference area)",
        "CDi": "aggregated induced drag coefficient at 2 deg",
        "CDo": "aggregated viscous drag coefficient at 2 deg",
        "CMy": "aggregated pitching moment coefficient at 2 deg (unit reference length)",
    }
    return tuple(
        MetricSpec(name, descriptions[name], kind=kind, warn=bands[name][0], fail=bands[name][1])
        for name in _TOTAL_METRIC_NAMES
    )


def build_smi_script(
    version: str,
    fsm_path: str | Path,
    loads_name: str,
    log_name: str,
) -> Script:
    """Build the one-point script an SMI drift case runs.

    Opens the local simulation file and applies the minimal steady
    setup the M2 pipeline shaped and the M3 preludes proved on this
    corpus: constant free stream, sea-level ISA through
    FLUID_PROPERTIES (AIR_ALTITUDE is broken on 26.120), steady
    incompressible initialization over every boundary, and a converged
    solve at the fixed comparison point.

    Parameters
    ----------
    version : str
        Target FlightStream version, canonical identifier (26.120); a
        vendor release name works only where it names exactly one
        registered build.
    fsm_path : str or Path
        Local .fsm file; must be absolute (the solver runs inside the
        case scratch directory).
    loads_name, log_name : str
        Output file names, written into the working directory.

    Returns
    -------
    Script
        The validated script, ready to render.
    """
    script = Script(version=version)
    script.comment(
        f"SMI drift point, alpha {SMI_ALPHA_DEG:+.1f} deg, unit references "
        "(Tier 3, SAD Section 11; geometry local only)"
    )
    script.emit("OPEN", str(fsm_path))
    script.emit(
        "FLUID_PROPERTIES",
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.7894e-05,
        specific_heat_ratio=1.4,
    )
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("SET_SOLVER_STEADY")
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_AOA", SMI_ALPHA_DEG)
    script.emit("SOLVER_SET_VELOCITY", SMI_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_VELOCITY", SMI_VELOCITY_M_S)
    script.emit("SOLVER_SET_REF_AREA", 1.0)
    script.emit("SOLVER_SET_REF_LENGTH", 1.0)
    script.emit("SOLVER_SET_ITERATIONS", PHY01_ITERATIONS)
    script.emit("SOLVER_SET_CONVERGENCE", PHY01_CONVERGENCE)
    script.emit("START_SOLVER")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", loads_name)
    script.emit("EXPORT_LOG", log_name)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def smi_metrics(point: PointResult) -> dict[str, float]:
    """Reduce one SMI point to its aggregated coefficient metrics."""
    return {name: point.total[name] for name in _TOTAL_METRIC_NAMES}


def _smi_case(case_id: str, title: str, band_kind: str) -> PhysicsCase:
    """One SMI entry; the title names the local simulation file the case opens."""
    return PhysicsCase(case_id=case_id, title=title, metric_specs=_smi_metric_specs(band_kind))


#: The two local cases: ``28_B.fsm`` (SMI-01) and ``31_WBH_IH0.fsm`` (SMI-02),
#: each opened by :func:`build_smi_script` at the fixed comparison point.
SMI_CASES: dict[str, PhysicsCase] = {
    "SMI-01": _smi_case(
        "SMI-01",
        "SMI isolated body (28_B, smallest corpus file)",
        band_kind="abs",
    ),
    "SMI-02": _smi_case(
        "SMI-02",
        "SMI full configuration (31_WBH_IH0, wing-body-tail)",
        band_kind="rel",
    ),
}


def _references_dir() -> Path:
    """Return the packaged reference directory (working tree when editable)."""
    return Path(str(resources.files("pyflightstream.qa"))) / "references"


def load_reference(case_id: str, references_dir: str | Path | None = None) -> CaseReference | None:
    """Load the committed reference of one case, when it exists.

    Parameters
    ----------
    case_id : str
        Case identifier, for example ``"PHY-01"``.
    references_dir : str or Path, optional
        Alternative directory, used by tests; defaults to the package
        data directory ``qa/references/``.

    Returns
    -------
    CaseReference or None
        The stored reference, or None before the first seeding.
    """
    directory = Path(references_dir) if references_dir else _references_dir()
    path = directory / f"{case_id}.yaml"
    if not path.is_file():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != REFERENCE_SCHEMA:
        raise QaEvidenceError(
            f"{path} is not a physics reference (expected schema {REFERENCE_SCHEMA!r})"
        )
    metrics = {
        name: ReferenceBand(
            value=float(body["value"]),
            warn=float(body["warn"]),
            fail=float(body["fail"]),
            kind=str(body["kind"]),
        )
        for name, body in document["metrics"].items()
    }
    return CaseReference(
        case_id=document["case"],
        fs_version_basis=str(document["fs_version_basis"]),
        updated=str(document["updated"]),
        reason=str(document["reason"]),
        metrics=metrics,
    )


def compare_metrics(
    measured: dict[str, float], reference: CaseReference | None
) -> dict[str, Verdict]:
    """Judge every measured metric against the stored reference bands.

    A metric missing from the reference (new metric, old reference)
    judges ``NO_REFERENCE`` rather than guessing a band.
    """
    if reference is None:
        return {name: Verdict.NO_REFERENCE for name in measured}
    return {
        name: (
            reference.metrics[name].judge(value)
            if name in reference.metrics
            else Verdict.NO_REFERENCE
        )
        for name, value in measured.items()
    }


def registered_cases(*, include_smi: bool = False) -> dict[str, PhysicsCase]:
    """Return the case registry, optionally including the SMI class.

    Parameters
    ----------
    include_smi : bool, keyword-only
        Include the SMI class, whose geometry is local and never
        committed. The SMI cases join only when the caller can
        provide that root; they never run implicitly (CONTRIBUTING.md
        invariant 5). Keyword-only since 2026-08-18: a bare ``True``
        in a call read as nothing in particular.

    Returns
    -------
    dict of str to PhysicsCase
        The registry, keyed by case id, in registry order.
    """
    if include_smi:
        return {**PHYSICS_CASES, **SMI_CASES}
    return dict(PHYSICS_CASES)


def case_table(*, include_smi: bool = False) -> list[dict[str, str | int]]:
    """Return the Tier 3 registry as a table, one line per case id.

    Formalizes the test-matrix policy: every physics validation is a
    matrix line with a numeric id (``PHY-NN`` for the shareable class,
    ``SMI-NN`` for the local-geometry class). The registry itself is
    that matrix; this view makes it inspectable, without running
    anything, from Python or from ``pyfs-qa cases``.

    Parameters
    ----------
    include_smi : bool, keyword-only
        Include the SMI class lines; like the runs themselves, they
        never appear implicitly (CONTRIBUTING.md invariant 5).

    Returns
    -------
    list of dict
        One mapping per registered case, in registry order, keyed
        ``case_id`` (the matrix line id), ``title``, ``metrics`` (how
        many metrics the case declares), and ``minimum_version`` (the
        version gate: ``"all registered"`` when the case's command set
        has evidence everywhere, else the minimum build and after).

        THE KEY WAS ``versions`` AND ITS VALUE WAS A LIST OF CANONICAL
        IDENTIFIERS, and the rename is the point rather than tidiness.
        The value became a sentence when the field behind it became a
        minimum, and a key that keeps its name while its value stops
        being a list is the one break in that change that a caller
        cannot see: ``if "26.123" in row["versions"]`` was a membership
        test over identifiers and became a SUBSTRING test over English,
        which answers False for 26.123 and True for 26.120, silently and
        differently per build. The missing key is the loud break, which
        is what a break should be.

        The gate renders as a minimum for the same reason the field
        became one: a list here is a list somebody has to extend by
        hand, and a reader comparing it against their own build learns
        nothing about a build registered after the list was written.
    """
    rows: list[dict[str, str | int]] = []
    for case in registered_cases(include_smi=include_smi).values():
        rows.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "metrics": len(case.metric_specs),
                "minimum_version": (
                    "all registered"
                    if case.minimum_version is None
                    else f"{case.minimum_version} and after"
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Report and reference update
# --------------------------------------------------------------------------


def physics_report_paths(
    out_dir: str | Path,
    *,
    version: str,
    date: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where a physics report for one build WOULD be written.

    The counterpart of :func:`pyflightstream.qa.compat.compat_report_paths`
    for the ``PHY`` series, and it exists for the same reason: a caller
    must be able to ask the question BEFORE it spends a licensed solver
    seat. Compat had this helper from 2026-08-17 and physics did not, so
    ``pyfs-qa physics`` had to rebuild the stem from the series prefix
    and the build identifier itself. Two expressions that agree today are
    not one rule, and the day this one changes the pre-flight inspects a
    name nothing writes.

    Parameters
    ----------
    out_dir : str or Path
        Target directory, normally ``reports/physics/``.
    version : str, keyword-only
        Version identifier, as :attr:`PhysicsRun.version` carries. A
        vendor release name is resolved through the registry, and an
        ambiguous one is refused here rather than after a seat is spent.
    date : str, optional, keyword-only
        ISO date stamped into the stem; defaults to today. A caller that
        will also write the report should resolve the date once and pass
        it here AND to :func:`write_physics_report`, so a run crossing
        midnight cannot check one stem and write another.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order. Neither is
        created and the directory is not made.

    Examples
    --------
    Ask before spending a licensed seat, which is the whole reason
    this function exists:

    >>> from pyflightstream.qa import physics_report_paths, refuse_existing_report
    >>> yaml_path, md_path = physics_report_paths(
    ...     "reports/physics", version="26.123", date="2026-08-17", label="example"
    ... )
    >>> yaml_path.name
    'PHY-26123_2026-08-17_example.yaml'
    >>> refuse_existing_report(yaml_path, md_path)

    Nothing is written by either call. The label matters here: this
    example first used ``label="full"``, which is a report this
    repository has actually committed, so the refusal fired inside the
    example and the doctest was red. That is the function working.
    """
    date = resolve_report_date(date)
    return report_paths(out_dir, series="PHY", versions=[version], date=date, label=label)


def write_physics_report(
    run: PhysicsRun, out_dir: str | Path, *, date: str | None = None, label: str | None = None
) -> tuple[Path, Path]:
    """Write one physics run as a report pair (YAML plus Markdown).

    Same evidence discipline as the compat reports: the stem is
    ``PHY-<version digits>_<date>`` plus the optional label, and an
    existing report is never overwritten.

    Parameters
    ----------
    run : PhysicsRun
        The run to record.
    out_dir : str or Path
        Target directory, normally ``reports/physics/``.
    date : str, optional
        ISO date stamped into the report; defaults to today.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order.

    Raises
    ------
    FileExistsError
        When a report with the same stem already exists.
    QaEvidenceError
        When the date is not spelled ``YYYY-MM-DD``. The stem carries
        the string, so a value that cannot go in a file name is
        refused before the write rather than after it.
    UnknownVersionError, AmbiguousVersionAliasError
        When the run's version is not a registered build, or is a
        vendor release name shared by several. NEW on 2026-08-18: the
        stem's build key is resolved through the registry now, so
        these reach a direct Python caller where they did not before.
        ``pyfs-qa`` resolves first and never meets them.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = resolve_report_date(date)
    yaml_path, md_path = physics_report_paths(out_dir, version=run.version, date=date, label=label)
    refuse_existing_report(yaml_path, md_path)
    counts = run.verdict_counts()
    document = {
        "schema": PHYSICS_SCHEMA,
        "fs_version": run.version,
        "date": date,
        "package_version": run.package_version,
        "fs_exe": run.fs_exe_name,
        # Written even when it is None: see the compat writer, which
        # carries the same field for the same reason.
        "fs_exe_sha256": run.fs_exe_sha256,
        "executor": describe_invocation(run.executor),
        # The rows the cases came from, since 0.13.0; None for a run
        # built in Python, which the tier-1 tests still do.
        "source": run.source,
        "solver_identity": list(run.solver_identity),
        "summary": counts,
        "cases": {
            result.case_id: {
                "title": result.title,
                "geometry": result.geometry,
                "error": result.error,
                "points": [
                    {
                        "label": point.label or f"a{point.alpha_deg:g}",
                        "alpha_deg": point.alpha_deg,
                        "iterations": point.iterations,
                        "converged": point.converged,
                        "total": {key: float(value) for key, value in point.total.items()},
                    }
                    for point in result.points
                ],
                "metrics": {name: float(value) for name, value in result.metrics.items()},
                "verdicts": {name: verdict.value for name, verdict in result.verdicts.items()},
                "reference": None
                if result.reference is None
                else {
                    "fs_version_basis": result.reference.fs_version_basis,
                    "updated": result.reference.updated,
                    "reason": result.reference.reason,
                },
            }
            for result in run.results
        },
    }
    yaml_path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    md_path.write_text(_render_markdown(run, date, counts), encoding="utf-8")
    return yaml_path, md_path


def _render_markdown(run: PhysicsRun, date: str, counts: dict[str, int]) -> str:
    """Render the human-readable side of the physics report."""
    lines = [
        f"# Physics report: FlightStream {run.version} ({date})",
        "",
        "Tier 3 physics regression evidence produced by `pyfs-qa physics`",
        "(SAD Section 11): the physics cases as rows of a run matrix in a",
        "campaign workspace, built by the package's workflows over the",
        "workspace's synthetic library, their loads reduced to the case",
        "metrics and compared against stored references inside WARN and",
        "FAIL bands. References change only through",
        "`pyfs-qa update-reference`, which records a reason; no research",
        "geometry is involved.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Source | {run.source or 'cases built in Python'} |",
        f"| Executable | {run.fs_exe_name} "
        f"(sha256 {run.fs_exe_sha256 or 'not recorded'}, "
        "local, never committed) |",
        f"| Executor | {describe_invocation(run.executor, markdown=True)} |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, "
        f"{counts['no_reference']} without reference.",
        "",
    ]
    for result in run.results:
        lines.extend([f"## {result.case_id}: {result.title}", ""])
        if result.error is not None:
            lines.extend([f"Case aborted: {result.error}", ""])
            continue
        lines.extend([result.geometry, ""])
        if result.points:
            lines.extend(
                [
                    "| point | alpha (deg) | CL | CDi | iterations | converged |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for point in result.points:
                label = point.label or f"a{point.alpha_deg:g}"
                lines.append(
                    f"| {label} | {point.alpha_deg:+.1f} "
                    f"| {point.total.get('CL', float('nan')):.5f} "
                    f"| {point.total.get('CDi', float('nan')):.5f} | {point.iterations} "
                    f"| {'yes' if point.converged else 'no'} |"
                )
            lines.append("")
        lines.extend(
            [
                "| Metric | Measured | Reference | Bands (warn/fail) | Verdict |",
                "|---|---|---|---|---|",
            ]
        )
        for name, value in result.metrics.items():
            band = result.reference.metrics.get(name) if result.reference else None
            if band is None:
                reference_cell, band_cell = "-", "-"
            else:
                reference_cell = f"{band.value:.5f}"
                band_cell = f"{band.warn:g}/{band.fail:g} ({band.kind})"
            verdict = result.verdicts.get(name, Verdict.NO_REFERENCE).value
            lines.append(f"| {name} | {value:.5f} | {reference_cell} | {band_cell} | {verdict} |")
        lines.append("")
    return "\n".join(lines)


def read_physics_report(path: str | Path) -> dict:
    """Load and check a machine-readable physics report."""
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != PHYSICS_SCHEMA:
        raise QaEvidenceError(
            f"{path} is not a physics report (expected schema {PHYSICS_SCHEMA!r}); "
            "references are seeded only from committed physics evidence"
        )
    return document


def update_reference(
    case_id: str,
    report_path: str | Path,
    reason: str,
    *,
    references_dir: str | Path | None = None,
    date: str | None = None,
) -> Path:
    """Update (or seed) one case reference from a committed physics report.

    The only write path into ``qa/references/`` (SAD Section 11): it
    demands a non-empty reason string, copies the measured metric
    values from the report, and keeps the curated bands of an existing
    reference; metrics new to the reference receive the default bands
    of the case's metric specifications. A reference update never
    shares a commit with code changes.

    Parameters
    ----------
    case_id : str
        Case whose reference to update.
    report_path : str or Path
        Committed physics report YAML carrying the measured values.
    reason : str
        Why the reference moves (initial seeding, solver change
        accepted after triage, case redefinition, ...); recorded in
        the reference file.
    references_dir : str or Path, optional
        Alternative directory, used by tests.
    date : str, optional
        ISO date recorded as the update date; defaults to today.

    Returns
    -------
    Path
        The written reference file.

    Raises
    ------
    QaEvidenceError
        When the reason is empty, the date is not spelled
        ``YYYY-MM-DD``, the case is unknown, the report is
        not a physics report, the report carries no metrics for the
        case, or a metric it carries is neither in the existing
        reference nor declared by the case. A subclass of ``ValueError``,
        so a caller written before the catalogue existed still catches
        it.
    """
    if not reason or not reason.strip():
        raise QaEvidenceError(
            "a reference update requires a reason string; references move only "
            "deliberately (SAD Section 11)"
        )
    registry = registered_cases(include_smi=True)
    case = registry.get(case_id)
    if case is None:
        raise QaEvidenceError(
            f"unknown physics case {case_id!r}; registered: {', '.join(sorted(registry))}"
        )
    report = read_physics_report(report_path)
    case_body = report.get("cases", {}).get(case_id)
    if not case_body or not case_body.get("metrics"):
        raise QaEvidenceError(f"{report_path} carries no measured metrics for {case_id}")
    existing = load_reference(case_id, references_dir)
    specs = case.specs_by_name
    metrics: dict[str, dict] = {}
    for name, value in case_body["metrics"].items():
        if existing is not None and name in existing.metrics:
            band = existing.metrics[name]
            warn, fail, kind = band.warn, band.fail, band.kind
        elif name in specs:
            warn, fail, kind = specs[name].warn, specs[name].fail, specs[name].kind
        else:
            raise QaEvidenceError(
                f"metric {name!r} is neither in the existing reference nor declared "
                f"by {case_id}; declare it in the case's metric specifications first"
            )
        metrics[name] = {"value": float(value), "warn": warn, "fail": fail, "kind": kind}
    directory = Path(references_dir) if references_dir else _references_dir()
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": REFERENCE_SCHEMA,
        "case": case_id,
        "fs_version_basis": report["fs_version"],
        "updated": resolve_report_date(date),
        "reason": reason.strip(),
        "source_report": Path(report_path).as_posix(),
        "metrics": metrics,
    }
    path = directory / f"{case_id}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    return path
