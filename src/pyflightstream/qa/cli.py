"""The ``pyfs-qa`` command line, first console entry point of the package.

Pipeline role: drives the qa evidence workflow from a terminal on the
licensed machine. ``pyfs-qa probe`` runs the Tier 2 command-validity
probes for one FlightStream version and writes the compat report;
``pyfs-qa apply-compat`` promotes database statuses from a committed
report. ``pyfs-qa physics`` runs the Tier 3 physics regression matrix
and writes the physics report; ``pyfs-qa update-reference`` is the only
write path into the stored physics references and demands a reason
string (SAD Section 11); ``pyfs-qa drift`` runs the same case set on
two versions and diffs the aggregated coefficients (FR-27);
``pyfs-qa cases`` prints the Tier 3 test matrix itself, one line per
case id, without running anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream.commands import CommandRegistry
from pyflightstream.qa.compat import apply_compat, write_compat_report
from pyflightstream.qa.drift import run_drift, write_drift_report
from pyflightstream.qa.physics import (
    PhysicsEnvironmentError,
    case_table,
    run_physics,
    update_reference,
    write_physics_report,
)
from pyflightstream.qa.probes import ProbeEnvironmentError, probe_version
from pyflightstream.versions import resolve


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-qa",
        description=(
            "Tier 2 and 3 evidence tooling for the pyflightstream command database; "
            "probes run FlightStream locally and need a licensed machine."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    probe = subparsers.add_parser(
        "probe",
        help="run command-validity probes and write the compat report",
    )
    probe.add_argument(
        "--version",
        required=True,
        help="target FlightStream version, canonical or alias (for example 26.120)",
    )
    probe.add_argument(
        "--fs-exe",
        required=True,
        help="explicit path of the FlightStream executable (never guessed)",
    )
    probe.add_argument(
        "--commands",
        help="comma-separated subset to probe; default: every command with a probe spec",
    )
    probe.add_argument(
        "--fsm",
        help=(
            "local simulation (.fsm) file for prelude tiers above none; specs needing "
            "it are recorded unprobed when absent"
        ),
    )
    probe.add_argument(
        "--workroot",
        default="runs/probes",
        help="scratch root for probe scripts and logs (default runs/probes/, not committed)",
    )
    probe.add_argument(
        "--timeout", type=float, default=120.0, help="per-probe wall-clock limit, seconds"
    )
    probe.add_argument(
        "--report-dir",
        default="reports/compat",
        help="directory receiving the compat report pair (default reports/compat/)",
    )
    probe.add_argument(
        "--label",
        help="report stem suffix distinguishing several reports on one day",
    )

    apply_parser = subparsers.add_parser(
        "apply-compat",
        help="promote database statuses from a committed compat report",
    )
    apply_parser.add_argument("report", help="the compat report YAML file")
    apply_parser.add_argument(
        "--root",
        default=".",
        help="repository root; the report is cited relative to it (default .)",
    )

    physics = subparsers.add_parser(
        "physics",
        help="run the Tier 3 physics regression matrix and write the physics report",
    )
    physics.add_argument(
        "--version",
        required=True,
        help="target FlightStream version, canonical or alias (for example 26.120)",
    )
    physics.add_argument(
        "--fs-exe",
        required=True,
        help="explicit path of the FlightStream executable (never guessed)",
    )
    physics.add_argument(
        "--cases",
        help="comma-separated case subset (for example PHY-01); default: every case",
    )
    physics.add_argument(
        "--workroot",
        default="runs/physics",
        help="scratch root for geometry, scripts, and outputs (default runs/physics/)",
    )
    physics.add_argument(
        "--timeout", type=float, default=900.0, help="per-point wall-clock limit, seconds"
    )
    physics.add_argument(
        "--report-dir",
        default="reports/physics",
        help="directory receiving the report pair (default reports/physics/)",
    )
    physics.add_argument(
        "--label",
        help="report stem suffix distinguishing several reports on one day",
    )
    physics.add_argument(
        "--smi-root",
        help="local SMI geometry root (normally _private/geometry/smi); enables the "
        "SMI drift class, geometry never enters Git",
    )

    drift = subparsers.add_parser(
        "drift",
        help="run the case set on two versions and diff the coefficients (FR-27)",
    )
    drift.add_argument(
        "--versions",
        required=True,
        help="two comma-separated versions, baseline first (for example 26.100,26.120); "
        "the same version twice is the degenerate self-comparison",
    )
    drift.add_argument(
        "--fs-exe",
        action="append",
        required=True,
        metavar="VERSION=PATH",
        help="explicit executable per version (repeatable, never guessed), "
        "for example --fs-exe 26.100=C:/fs26100/FS.exe",
    )
    drift.add_argument(
        "--cases",
        help="comma-separated case subset (for example PHY-01); default: every case",
    )
    drift.add_argument(
        "--workroot",
        default="runs/drift",
        help="scratch root; each version nests under its canonical name",
    )
    drift.add_argument(
        "--timeout", type=float, default=900.0, help="per-point wall-clock limit, seconds"
    )
    drift.add_argument(
        "--report-dir",
        default="reports/physics",
        help="directory receiving the report pair (default reports/physics/)",
    )
    drift.add_argument(
        "--label",
        help="report stem suffix distinguishing several reports on one day",
    )
    drift.add_argument(
        "--smi-root",
        help="local SMI geometry root (normally _private/geometry/smi); enables the "
        "SMI drift class on both versions, geometry never enters Git",
    )

    cases = subparsers.add_parser(
        "cases",
        help="print the Tier 3 test matrix: one line per registered case id, nothing runs",
    )
    cases.add_argument(
        "--include-smi",
        action="store_true",
        help="include the SMI local-geometry class; like the runs, it never appears implicitly",
    )

    update = subparsers.add_parser(
        "update-reference",
        help="update or seed one physics reference from a committed physics report",
    )
    update.add_argument("case", help="case identifier, for example PHY-01")
    update.add_argument(
        "--from-report",
        required=True,
        help="committed physics report YAML carrying the measured values",
    )
    update.add_argument(
        "--reason",
        required=True,
        help="why the reference moves; recorded in the reference file (required)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-qa``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    if args.subcommand == "probe":
        return _cmd_probe(args)
    if args.subcommand == "physics":
        return _cmd_physics(args)
    if args.subcommand == "drift":
        return _cmd_drift(args)
    if args.subcommand == "update-reference":
        return _cmd_update_reference(args)
    if args.subcommand == "cases":
        return _cmd_cases(args)
    return _cmd_apply_compat(args)


def _cmd_cases(args: argparse.Namespace) -> int:
    rows = case_table(include_smi=args.include_smi)
    header = {"case_id": "CASE", "title": "TITLE", "metrics": "METRICS", "versions": "VERSIONS"}
    widths = {key: max(len(header[key]), *(len(str(row[key])) for row in rows)) for key in header}
    line = "  ".join(header[key].ljust(widths[key]) for key in header)
    print(line.rstrip())
    for row in rows:
        line = "  ".join(str(row[key]).ljust(widths[key]) for key in header)
        print(line.rstrip())
    print(f"{len(rows)} case(s); every physics validation is one matrix line with an id")
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    canonical = resolve(args.version).canonical
    commands = None
    if args.commands:
        commands = [name.strip() for name in args.commands.split(",") if name.strip()]
    try:
        run = probe_version(
            canonical,
            workroot=Path(args.workroot) / canonical,
            fs_exe=args.fs_exe,
            commands=commands,
            fsm=args.fsm,
            timeout_s=args.timeout,
        )
    except ProbeEnvironmentError as error:
        print(f"probe run aborted: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_compat_report(run, args.report_dir, label=args.label)
    counts = run.outcome_counts()
    print(
        f"FlightStream {run.version} ({run.fs_exe_name}): "
        f"{counts['verified']} verified, {counts['broken']} broken, "
        f"{counts['unprobed']} unprobed"
    )
    for line in run.solver_identity:
        print(f"solver: {line}")
    print(f"report: {yaml_path}")
    print(f"report: {md_path}")
    return 0


def _cmd_physics(args: argparse.Namespace) -> int:
    canonical = resolve(args.version).canonical
    cases = None
    if args.cases:
        cases = [name.strip() for name in args.cases.split(",") if name.strip()]
    try:
        run = run_physics(
            canonical,
            fs_exe=args.fs_exe,
            workroot=args.workroot,
            cases=cases,
            timeout_s=args.timeout,
            smi_root=args.smi_root,
        )
    except PhysicsEnvironmentError as error:
        print(f"physics run aborted: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_physics_report(run, args.report_dir, label=args.label)
    counts = run.verdict_counts()
    print(
        f"FlightStream {run.version} ({run.fs_exe_name}): "
        f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, "
        f"{counts['no_reference']} without reference"
    )
    for result in run.results:
        if result.error is not None:
            print(f"{result.case_id} aborted: {result.error}", file=sys.stderr)
    for line in run.solver_identity:
        print(f"solver: {line}")
    print(f"report: {yaml_path}")
    print(f"report: {md_path}")
    aborted = any(result.error is not None for result in run.results)
    return 1 if counts["fail"] or aborted else 0


def _cmd_drift(args: argparse.Namespace) -> int:
    versions = [name.strip() for name in args.versions.split(",") if name.strip()]
    if len(versions) != 2:
        print(
            "drift compares exactly two versions, baseline first "
            "(for example --versions 26.100,26.120)",
            file=sys.stderr,
        )
        return 2
    fs_exes: dict[str, str] = {}
    for item in args.fs_exe:
        version, separator, path = item.partition("=")
        if not separator or not path:
            print(f"--fs-exe expects VERSION=PATH, got {item!r}", file=sys.stderr)
            return 2
        fs_exes[resolve(version.strip()).canonical] = path.strip()
    canonicals = [resolve(version).canonical for version in versions]
    missing = [canonical for canonical in canonicals if canonical not in fs_exes]
    if missing:
        print(
            f"no executable given for {', '.join(missing)}; pass --fs-exe VERSION=PATH",
            file=sys.stderr,
        )
        return 2
    cases = None
    if args.cases:
        cases = [name.strip() for name in args.cases.split(",") if name.strip()]
    try:
        run = run_drift(
            canonicals[0],
            canonicals[1],
            fs_exes=fs_exes,
            workroot=args.workroot,
            cases=cases,
            timeout_s=args.timeout,
            smi_root=args.smi_root,
        )
    except PhysicsEnvironmentError as error:
        print(f"drift run aborted: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_drift_report(run, args.report_dir, label=args.label)
    counts = run.verdict_counts()
    print(
        f"FlightStream {run.version_a} vs {run.version_b}: "
        f"{counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, "
        f"{counts['no_reference']} without declared bands"
    )
    for result in run.results:
        if result.error is not None:
            print(f"{result.case_id} aborted: {result.error}", file=sys.stderr)
    for line in run.solver_identity:
        print(f"solver: {line}")
    print(f"report: {yaml_path}")
    print(f"report: {md_path}")
    aborted = any(result.error is not None for result in run.results)
    return 1 if counts["fail"] or aborted else 0


def _cmd_update_reference(args: argparse.Namespace) -> int:
    try:
        path = update_reference(args.case, args.from_report, args.reason)
    except ValueError as error:
        print(f"reference not updated: {error}", file=sys.stderr)
        return 2
    print(f"reference written: {path}")
    print("commit it alone: a reference update never shares a commit with code changes")
    return 0


def _cmd_apply_compat(args: argparse.Namespace) -> int:
    promotions = apply_compat(args.report, repo_root=args.root)
    if not promotions:
        print("no verified or broken judgment in the report; nothing promoted")
        return 0
    for name, status, chapter in promotions:
        print(f"{name}: {status} ({chapter})")
    CommandRegistry.load.cache_clear()
    CommandRegistry.load()
    print(f"{len(promotions)} status(es) promoted; database reloaded and valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
