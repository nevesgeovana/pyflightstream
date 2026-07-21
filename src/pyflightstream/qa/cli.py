"""The ``pyfs-qa`` command line, first console entry point of the package.

Pipeline role: drives the qa evidence workflow from a terminal on the
licensed machine. ``pyfs-qa probe`` runs the Tier 2 command-validity
probes for one FlightStream version and writes the compat report;
``pyfs-qa apply-compat`` promotes database statuses from a committed
report. Physics commands (Tier 3) arrive at milestone M4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream.commands import CommandRegistry
from pyflightstream.qa.compat import apply_compat, write_compat_report
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
        "--workroot",
        default="probe_runs",
        help="scratch root for probe scripts and logs (default probe_runs/, not committed)",
    )
    probe.add_argument(
        "--timeout", type=float, default=120.0, help="per-probe wall-clock limit, seconds"
    )
    probe.add_argument(
        "--report-dir",
        default="reports/compat",
        help="directory receiving the compat report pair (default reports/compat/)",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-qa``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    if args.subcommand == "probe":
        return _cmd_probe(args)
    return _cmd_apply_compat(args)


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
            timeout_s=args.timeout,
        )
    except ProbeEnvironmentError as error:
        print(f"probe run aborted: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_compat_report(run, args.report_dir)
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
