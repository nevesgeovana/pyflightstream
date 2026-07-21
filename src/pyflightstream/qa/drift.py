"""Cross-version drift suite (FR-27, SAD Section 11).

Pipeline role: runs the same physics case set on two FlightStream
versions and diffs the aggregated coefficients, so a solver release
cannot silently move the physics the research depends on. The case
set is exactly the Tier 3 registry of :mod:`pyflightstream.qa.physics`
(synthetic committed geometry; the SMI class joins later as more
registry cases, geometry staying local under ``_private/``).

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

import datetime
from dataclasses import dataclass
from pathlib import Path

import yaml

import pyflightstream
from pyflightstream.qa.physics import (
    PhysicsRun,
    ReferenceBand,
    Verdict,
    registered_cases,
    run_physics,
)
from pyflightstream.versions import resolve

DRIFT_SCHEMA = "pyflightstream-drift-report/1"

__all__ = [
    "DriftMetric",
    "DriftCaseResult",
    "DriftRun",
    "diff_runs",
    "run_drift",
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
        package_version=pyflightstream.__version__,
        results=tuple(results),
        solver_identity=tuple(identity),
    )


def run_drift(
    version_a: str,
    version_b: str,
    *,
    fs_exes: dict[str, str | Path],
    workroot: str | Path,
    cases: list[str] | None = None,
    timeout_s: float = 900.0,
    smi_root: str | Path | None = None,
) -> DriftRun:
    """Run the physics case set on both versions and diff the results.

    Parameters
    ----------
    version_a, version_b : str
        Baseline and compared versions, canonical or alias. The same
        version twice is the degenerate self-comparison that proves
        the machinery.
    fs_exes : dict of str to path
        Explicit executable per canonical version (never guessed);
        must cover both versions.
    workroot : str or Path
        Scratch root; each version nests its own per-case directories
        under its canonical name.
    cases : list of str, optional
        Case subset; defaults to every registered case (the SMI class
        joins the default only when ``smi_root`` is given).
    timeout_s : float
        Wall-clock limit per solver point.
    smi_root : str or Path, optional
        Local SMI geometry root; enables the SMI drift class on both
        versions. Explicit input, never guessed.

    Returns
    -------
    DriftRun
        The comparison.

    Raises
    ------
    PhysicsEnvironmentError
        When an executable is missing for either version or a case is
        unknown (raised by the underlying physics runs).
    KeyError
        When ``fs_exes`` does not cover a requested version.
    """
    canonical_a = resolve(version_a).canonical
    canonical_b = resolve(version_b).canonical
    run_a = run_physics(
        canonical_a,
        fs_exe=fs_exes[canonical_a],
        workroot=workroot,
        cases=cases,
        timeout_s=timeout_s,
        smi_root=smi_root,
    )
    if canonical_b != canonical_a:
        run_b = run_physics(
            canonical_b,
            fs_exe=fs_exes[canonical_b],
            workroot=workroot,
            cases=cases,
            timeout_s=timeout_s,
            smi_root=smi_root,
        )
    else:
        # Degenerate self-comparison: run the case set a second time so
        # the diff really compares two independent solver executions.
        run_b = run_physics(
            canonical_b,
            fs_exe=fs_exes[canonical_b],
            workroot=Path(workroot) / "self_b",
            cases=cases,
            timeout_s=timeout_s,
            smi_root=smi_root,
        )
    return diff_runs(run_a, run_b)


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
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = date or datetime.date.today().isoformat()
    stem = f"DRF-{run.version_a.replace('.', '')}-{run.version_b.replace('.', '')}_{date}"
    if label:
        stem += f"_{label}"
    yaml_path = out_dir / f"{stem}.yaml"
    md_path = out_dir / f"{stem}.md"
    for path in (yaml_path, md_path):
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; drift reports are evidence and are never "
                "overwritten. Pick another date or label."
            )
    counts = run.verdict_counts()
    document = {
        "schema": DRIFT_SCHEMA,
        "fs_version_a": run.version_a,
        "fs_version_b": run.version_b,
        "date": date,
        "package_version": run.package_version,
        "fs_exes": dict(run.fs_exe_names),
        "executor": "LocalExecutor, -hidden --script (SRC-003 pp.279-280)",
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


def _render_markdown(run: DriftRun, date: str, counts: dict[str, int]) -> str:
    """Render the human-readable side of the drift report."""
    a, b = run.version_a, run.version_b
    lines = [
        f"# Drift report: FlightStream {a} versus {b} ({date})",
        "",
        "Cross-version drift evidence produced by `pyfs-qa drift` (FR-27,",
        "SAD Section 11): the committed synthetic physics cases run on both",
        "versions, aggregated coefficients diffed, version B judged against",
        "version A inside the WARN and FAIL half widths the case metrics",
        "declare. Geometry is generated by the suite; no research geometry",
        "is involved.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Baseline (A) | FlightStream {a}, {run.fs_exe_names.get(a, '?')} "
        "(local, `_private/exe/`) |",
        f"| Compared (B) | FlightStream {b}, {run.fs_exe_names.get(b, '?')} "
        "(local, `_private/exe/`) |",
        "| Executor | LocalExecutor, `-hidden --script` (SRC-003 pp.279-280) |",
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
