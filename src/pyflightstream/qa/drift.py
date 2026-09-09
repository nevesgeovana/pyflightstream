"""Cross-version drift suite (FR-27, SAD Section 11).

Pipeline role: diffs the same physics case set measured on two
FlightStream versions, so a solver release cannot silently move the
physics the research depends on. The case set is the Tier 3 registry of
:mod:`pyflightstream.qa.physics`, and since 0.13.0 the two measurements
are two runs of the workspace's physics matrix under two registries,
made by :func:`pyflightstream.qa.matrix.drift_from_workspace`
(PFS-2031.17); this module owns the diff and the report and runs
nothing itself.

Drift needs no stored references: version A is the baseline and
version B is judged against it inside the same WARN and FAIL half
widths the case metrics declare, so "the physics moved more than a
reference regression would tolerate" means the same thing in both
suites. The degenerate self-comparison (same version twice) exercises
the whole machinery and must land every delta at zero, since repeat
runs on 26.120 proved bit-identical (PHY-26120_2026-07-21_full).

Every executable path is explicit input, one per version, never
guessed (SAD Section 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

import pyflightstream
from pyflightstream.qa.physics import (
    PhysicsRun,
    ReferenceBand,
    Verdict,
    registered_cases,
)
from pyflightstream.qa.reports import (
    refuse_existing_report,
    report_paths,
    resolve_report_date,
)
from pyflightstream.run import ExecutorRecord, describe_invocation

DRIFT_SCHEMA = "pyflightstream-drift-report/1"

__all__ = [
    "DriftMetric",
    "DriftCaseResult",
    "DriftRun",
    "diff_runs",
    "drift_report_paths",
    "write_drift_report",
]


@dataclass(frozen=True)
class DriftMetric:
    """One metric compared across the two versions.

    Attributes
    ----------
    value_a, value_b : float
        Measured values on the baseline and the compared version.
    delta : float
        ``value_b - value_a``.
    verdict : Verdict
        Judgment of ``value_b`` against the case's declared bands
        centered on ``value_a`` (``NO_REFERENCE`` when the metric is
        missing from the case's specifications).
    warn, fail : float
        The half widths applied, from the case metric specification.
    kind : str
        Band kind applied (``rel`` or ``abs``).
    """

    value_a: float
    value_b: float
    delta: float
    verdict: Verdict
    warn: float
    fail: float
    kind: str


@dataclass(frozen=True)
class DriftCaseResult:
    """Drift outcome of one physics case.

    ``error`` carries the failure text when the case aborted on either
    version; a failed case reports instead of hiding the others.
    """

    case_id: str
    title: str
    metrics: dict[str, DriftMetric]
    error: str | None = None


@dataclass(frozen=True)
class DriftRun:
    """One complete cross-version drift comparison."""

    version_a: str
    version_b: str
    fs_exe_names: dict[str, str]
    package_version: str
    results: tuple[DriftCaseResult, ...]
    solver_identity: tuple[str, ...] = ()
    #: Executable digest per version, beside :attr:`fs_exe_names` and
    #: keyed the same way. A drift report is the one place where two
    #: executables are named at once, and the vendor installer gives
    #: four registered builds the same file name, so the NAME map can
    #: print one string on both rows of a comparison between two of
    #: them. A version with no measured digest maps to ``None``.
    fs_exe_sha256s: dict[str, str | None] = field(default_factory=dict)
    #: How each version's solver was called, keyed like the names above
    #: and read off the physics run of that version (PFS-2012.04); a
    #: version whose run recorded none maps to ``None``.
    executors: dict[str, ExecutorRecord | None] = field(default_factory=dict)

    def verdict_counts(self) -> dict[str, int]:
        """Count metric verdicts over every case, for the summary line."""
        counts = {verdict.value: 0 for verdict in Verdict}
        for result in self.results:
            for metric in result.metrics.values():
                counts[metric.verdict.value] += 1
        return counts


def diff_runs(run_a: PhysicsRun, run_b: PhysicsRun) -> DriftRun:
    """Diff two physics runs case by case and metric by metric.

    Pure reduction over already-measured runs, so the drift judgment
    is testable without a solver. Metrics are judged with the case's
    declared bands centered on the version-A value; a metric absent
    from the case specifications judges ``NO_REFERENCE`` rather than
    inventing a band.

    Parameters
    ----------
    run_a, run_b : PhysicsRun
        The baseline and compared runs, normally of two different
        versions on the same case set.

    Returns
    -------
    DriftRun
        The comparison, one entry per case present in both runs.
    """
    cases_b = {result.case_id: result for result in run_b.results}
    results: list[DriftCaseResult] = []
    for result_a in run_a.results:
        result_b = cases_b.get(result_a.case_id)
        if result_b is None:
            continue
        title = result_a.title or result_b.title
        errors = [
            f"{version}: {error}"
            for version, error in (
                (run_a.version, result_a.error),
                (run_b.version, result_b.error),
            )
            if error is not None
        ]
        if errors:
            results.append(
                DriftCaseResult(
                    case_id=result_a.case_id, title=title, metrics={}, error="; ".join(errors)
                )
            )
            continue
        case = registered_cases(include_smi=True).get(result_a.case_id)
        specs = case.specs_by_name if case is not None else {}
        metrics: dict[str, DriftMetric] = {}
        for name, value_a in result_a.metrics.items():
            if name not in result_b.metrics:
                continue
            value_b = result_b.metrics[name]
            spec = specs.get(name)
            if spec is None:
                metrics[name] = DriftMetric(
                    value_a=value_a,
                    value_b=value_b,
                    delta=value_b - value_a,
                    verdict=Verdict.NO_REFERENCE,
                    warn=float("nan"),
                    fail=float("nan"),
                    kind="abs",
                )
                continue
            band = ReferenceBand(value=value_a, warn=spec.warn, fail=spec.fail, kind=spec.kind)
            metrics[name] = DriftMetric(
                value_a=value_a,
                value_b=value_b,
                delta=value_b - value_a,
                verdict=band.judge(value_b),
                warn=spec.warn,
                fail=spec.fail,
                kind=spec.kind,
            )
        results.append(DriftCaseResult(case_id=result_a.case_id, title=title, metrics=metrics))
    identity = list(run_a.solver_identity)
    identity.extend(line for line in run_b.solver_identity if line not in identity)
    return DriftRun(
        version_a=run_a.version,
        version_b=run_b.version,
        fs_exe_names={run_a.version: run_a.fs_exe_name, run_b.version: run_b.fs_exe_name},
        fs_exe_sha256s={
            run_a.version: run_a.fs_exe_sha256,
            run_b.version: run_b.fs_exe_sha256,
        },
        package_version=pyflightstream.__version__,
        results=tuple(results),
        solver_identity=tuple(identity),
        executors={run_a.version: run_a.executor, run_b.version: run_b.executor},
    )


def drift_report_paths(
    out_dir: str | Path,
    *,
    version_a: str,
    version_b: str,
    date: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where a drift report for one comparison WOULD be written.

    The ``DRF`` counterpart of
    :func:`pyflightstream.qa.physics.physics_report_paths`, and the one
    with the most to lose from a second copy: its stem joins TWO build
    identifiers, so the CLI predicting the name had to reproduce both the
    dot-stripping and the join order. The two builds are stated in the
    order compared, A then B, which is the order the report's own body
    uses; the join is not sorted, so swapping the arguments names a
    different report rather than the same one.

    Parameters
    ----------
    out_dir : str or Path
        Target directory, normally ``reports/physics/``.
    version_a, version_b : str, keyword-only
        Version identifiers, as :attr:`DriftRun.version_a` and
        :attr:`DriftRun.version_b` carry. Keyword-only precisely because
        they are a swappable pair: positionally, transposing them names a
        different report and complains about nothing.
    date : str, optional, keyword-only
        ISO date stamped into the stem; defaults to today. A caller that
        will also write the report should resolve the date once and pass
        it here AND to :func:`write_drift_report`.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order. Neither is
        created and the directory is not made.
    """
    date = resolve_report_date(date)
    return report_paths(
        out_dir, series="DRF", versions=[version_a, version_b], date=date, label=label
    )


def write_drift_report(
    run: DriftRun, out_dir: str | Path, *, date: str | None = None, label: str | None = None
) -> tuple[Path, Path]:
    """Write one drift comparison as a report pair (YAML plus Markdown).

    Same evidence discipline as the physics reports: the stem is
    ``DRF-<A digits>-<B digits>_<date>`` plus the optional label, under
    ``reports/physics/``, and an existing report is never overwritten.

    Parameters
    ----------
    run : DriftRun
        The comparison to record.
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
    yaml_path, md_path = drift_report_paths(
        out_dir,
        version_a=run.version_a,
        version_b=run.version_b,
        date=date,
        label=label,
    )
    refuse_existing_report(yaml_path, md_path)
    counts = run.verdict_counts()
    document = {
        "schema": DRIFT_SCHEMA,
        "fs_version_a": run.version_a,
        "fs_version_b": run.version_b,
        "date": date,
        "package_version": run.package_version,
        "fs_exes": dict(run.fs_exe_names),
        # Written even when a value is None, on the compat writer's
        # reasoning: an absent key reads as an older schema, and a
        # reader cannot tell that from a digest nobody took.
        "fs_exe_sha256s": dict(run.fs_exe_sha256s),
        "executor": _executor_sentence(run),
        "solver_identity": list(run.solver_identity),
        "summary": counts,
        "cases": {
            result.case_id: {
                "title": result.title,
                "error": result.error,
                "metrics": {
                    name: {
                        "value_a": float(metric.value_a),
                        "value_b": float(metric.value_b),
                        "delta": float(metric.delta),
                        "warn": float(metric.warn),
                        "fail": float(metric.fail),
                        "kind": metric.kind,
                        "verdict": metric.verdict.value,
                    }
                    for name, metric in result.metrics.items()
                },
            }
            for result in run.results
        },
    }
    yaml_path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    md_path.write_text(_render_markdown(run, date, counts), encoding="utf-8")
    return yaml_path, md_path


def _executor_sentence(run: DriftRun, *, markdown: bool = False) -> str:
    """Return the executor sentence of a drift report, read off both runs.

    One sentence when both versions were called the same way, which is
    the usual case and the one the compat and physics reports state;
    two labelled halves when they were not, because a comparison whose
    two sides ran under different flags is a fact the report must not
    average away.
    """
    a, b = run.version_a, run.version_b
    sentence = {
        version: describe_invocation(run.executors.get(version), markdown=markdown)
        for version in (a, b)
    }
    if sentence[a] == sentence[b]:
        return sentence[a]
    return f"A ({a}): {sentence[a]}; B ({b}): {sentence[b]}"


def _render_markdown(run: DriftRun, date: str, counts: dict[str, int]) -> str:
    """Render the human-readable side of the drift report."""
    a, b = run.version_a, run.version_b
    lines = [
        f"# Drift report: FlightStream {a} versus {b} ({date})",
        "",
        "Cross-version drift evidence produced by `pyfs-qa drift` (FR-27,",
        "SAD Section 11): the rows of the workspace's physics matrix run",
        "on both versions, each under its own registry, the case metrics",
        "reduced from each run and diffed, version B judged against",
        "version A inside the WARN and FAIL half widths the case metrics",
        "declare. The geometry is the workspace's synthetic library; no",
        "research geometry is involved.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Baseline (A) | FlightStream {a}, {run.fs_exe_names.get(a, '?')} "
        f"(sha256 {run.fs_exe_sha256s.get(a) or 'not recorded'}, local, `_private/exe/`) |",
        f"| Compared (B) | FlightStream {b}, {run.fs_exe_names.get(b, '?')} "
        f"(sha256 {run.fs_exe_sha256s.get(b) or 'not recorded'}, local, `_private/exe/`) |",
        f"| Executor | {_executor_sentence(run, markdown=True)} |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, "
        f"{counts['no_reference']} without declared bands.",
        "",
    ]
    for result in run.results:
        lines.extend([f"## {result.case_id}: {result.title}", ""])
        if result.error is not None:
            lines.extend([f"Case aborted: {result.error}", ""])
            continue
        lines.extend(
            [
                f"| Metric | {a} (A) | {b} (B) | delta | Bands (warn/fail) | Verdict |",
                "|---|---|---|---|---|---|",
            ]
        )
        for name, metric in result.metrics.items():
            band_cell = (
                "-"
                if metric.verdict is Verdict.NO_REFERENCE
                else f"{metric.warn:g}/{metric.fail:g} ({metric.kind})"
            )
            lines.append(
                f"| {name} | {metric.value_a:.5f} | {metric.value_b:.5f} "
                f"| {metric.delta:+.5f} | {band_cell} | {metric.verdict.value} |"
            )
        lines.append("")
    return "\n".join(lines)
