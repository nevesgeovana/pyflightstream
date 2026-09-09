"""The ``pyfs-qa`` command line, first console entry point of the package.

Pipeline role: drives the qa evidence workflow from a terminal on the
licensed machine. ``pyfs-qa probe`` runs the Tier 2 command-validity
probes for one FlightStream version and writes the compat report;
``pyfs-qa apply-compat`` promotes database statuses from a committed
report. ``pyfs-qa physics`` runs the physics matrix of a campaign
workspace through the run layer, reduces the records with the qa
functions and writes the physics report (PFS-2031.17);
``pyfs-qa update-reference`` is the only write path into the stored
physics references and demands a reason string (SAD Section 11);
``pyfs-qa drift`` runs the same matrix on two builds, each under its own
registry, and diffs the two reductions (FR-27); ``pyfs-qa cases`` prints
the case registry, one line per case id, without running anything;
``pyfs-qa cost`` reads a campaign's ``runs.json`` and prints what each
sweep point cost in wall-clock seconds, one column per solver build, so a
build that got slower can be shown (FR-19 records the field, this reads
it).

Three of the seven subcommands need a licensed machine (``probe``,
``physics``, ``drift``) and four do not: ``apply-compat``,
``update-reference``, ``cases`` and ``cost`` read committed or recorded
evidence and start no solver. ``physics --resume`` on a workspace whose
matrix already ran is the fourth reader: it executes nothing and reports
what the manifest holds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import WorkflowCoverageError
from pyflightstream.commands import CommandRegistry
from pyflightstream.options import get_option
from pyflightstream.qa.compat import (
    PROMOTABLE_OUTCOMES,
    apply_compat,
    compat_report_paths,
    read_compat_report,
    write_compat_report,
)
from pyflightstream.qa.cost import ABSENT, NOT_RUN, CostView, PointKey, cost_view
from pyflightstream.qa.drift import drift_report_paths, write_drift_report
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.matrix import (
    DEFAULT_MATRIX,
    drift_from_workspace,
    physics_build,
    physics_from_workspace,
    physics_matrix,
)
from pyflightstream.qa.physics import (
    PhysicsEnvironmentError,
    case_table,
    physics_report_paths,
    update_reference,
    write_physics_report,
)
from pyflightstream.qa.probes import ProbeEnvironmentError, probe_version
from pyflightstream.qa.reports import refuse_existing_report, resolve_report_date
from pyflightstream.versions import AmbiguousVersionAliasError, UnknownVersionError, resolve
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, WorkspaceError

#: The refusals the run layer raises BEFORE anything executes, caught the
#: way ``pyfs-matrix run`` catches them, plus the workspace's own refusal
#: of a recorded point re-run without --resume, which is the one a reader
#: of a workspace that already ran meets first.
_RUN_LAYER_REFUSALS = (
    MatrixError,
    InputArtifactError,
    WorkspaceError,
    CampaignConfigError,
    WorkflowCoverageError,
    OSError,
    ValueError,
)


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
        "--fs-version",
        required=True,
        help="target FlightStream version: canonical identifier (for example "
        "26.120); a vendor release name works only where it names exactly one "
        "registered build",
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
        "--identity-only",
        action="store_true",
        help=(
            "judge no command: run the baseline, capture the solver's identity banner, "
            "and write the report pair. This is how a newly registered build gets its "
            "build number into a committed report, which is the only place the version "
            "registry accepts one from"
        ),
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
        default=f"{get_option('qa.scratch_root')}/probes",
        help="scratch root for probe scripts and logs (default from the "
        "qa.scratch_root option: runs/probes/, not committed)",
    )
    probe.add_argument(
        "--timeout",
        type=float,
        default=get_option("qa.probe_timeout_s"),
        help="per-probe wall-clock limit, seconds (default from the qa.probe_timeout_s option)",
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
        help="run the physics matrix of a workspace, reduce its records and write the "
        "physics report",
    )
    physics.add_argument(
        "--workspace",
        default=".",
        help="the campaign workspace holding inputs/ and the physics matrix at its root "
        "(default: the current directory); tests/tier3_licensed is this repository's",
    )
    physics.add_argument(
        "--matrix",
        default=DEFAULT_MATRIX,
        help=f"the matrix file name at the workspace root (default {DEFAULT_MATRIX}); "
        "every active row fills FS_BUILD with one build id, which the report names",
    )
    physics.add_argument(
        "--name",
        default=None,
        help="campaign name; without it the workspace directory's name is the campaign's, "
        "as pyfs-matrix run names it, so a resumed run finds the points it recorded",
    )
    physics.add_argument(
        "--resume",
        action="store_true",
        help="skip points already in the manifest and run the rest; on a workspace whose "
        "matrix already ran this executes nothing and reports what was recorded. "
        "Without it an already-recorded point refuses before anything executes",
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

    drift = subparsers.add_parser(
        "drift",
        help="run the physics matrix on two builds, each under its own registry, and "
        "diff the two reductions (FR-27)",
    )
    drift.add_argument(
        "--workspace",
        default=".",
        help="the campaign workspace whose inputs/ library and physics matrix both sides "
        "copy (default: the current directory)",
    )
    drift.add_argument(
        "--matrix",
        default=DEFAULT_MATRIX,
        help=f"the matrix file name at the workspace root (default {DEFAULT_MATRIX})",
    )
    drift.add_argument(
        "--fs-versions",
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
        "--name",
        default=None,
        help="campaign name of both sides; without it the workspace directory's name",
    )
    drift.add_argument(
        "--workroot",
        default=f"{get_option('qa.scratch_root')}/drift",
        help="where the two side workspaces are made, a_<build> and b_<build>, each a "
        "copy of the library with an overlay registry naming that side's executable "
        "(default from the qa.scratch_root option: runs/drift/); a side that exists "
        "is refused, a drift being two fresh runs",
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

    cases = subparsers.add_parser(
        "cases",
        help="print the Tier 3 test matrix: one line per registered case id, nothing runs",
    )
    cases.add_argument(
        "--include-smi",
        action="store_true",
        help="include the SMI local-geometry class; like the runs, it never appears implicitly",
    )

    cost = subparsers.add_parser(
        "cost",
        help=(
            "report wall-time cost per sim and point from a campaign manifest, one "
            "column per solver build; reads runs.json and runs nothing"
        ),
    )
    cost.add_argument(
        "campaign",
        help="campaign root whose runs.json is read; no solver is started",
    )
    cost.add_argument(
        "--compare",
        metavar="BASELINE,CANDIDATE",
        help="two build column labels, baseline first, as the table's own header "
        "spells them; only the points both builds timed are compared",
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
    if args.subcommand == "cost":
        return _cmd_cost(args)
    return _cmd_apply_compat(args)


def _cmd_cost(args: argparse.Namespace) -> int:
    """Print the wall-time cost table of one campaign, and optionally a comparison.

    Presentation lives here rather than in :mod:`pyflightstream.qa.cost`,
    like every other subcommand of this CLI: the library answers what a
    run cost, the command line decides how a terminal reads it.
    """
    workspace = CampaignWorkspace(args.campaign)
    view = cost_view(workspace)
    if not view.points:
        print(
            f"no runs recorded: {workspace.manifest_path} "
            f"{'is empty' if workspace.manifest_path.is_file() else 'does not exist'}, "
            "so there is no wall time to report. A campaign with no manifest is not "
            "a campaign that cost nothing.",
            file=sys.stderr,
        )
        return 2

    header = {"sim_id": "SIM", "point": "POINT"}
    header.update({build.label: build.label for build in view.builds})
    cells = [_cost_row_text(view, point) for point in view.points]
    widths = {key: max(len(header[key]), *(len(row[key]) for row in cells)) for key in header}
    print("  ".join(header[key].ljust(widths[key]) for key in header).rstrip())
    for row in cells:
        print("  ".join(row[key].ljust(widths[key]) for key in header).rstrip())

    print("")
    for build in view.builds:
        print(
            f"column {build.label}: fs_build={build.fs_build} fs_exe_sha256={build.fs_exe_sha256}"
        )
    print(
        f"seconds of wall-clock time around the solver process; {ABSENT} = the run is "
        f"recorded and carries no wall time, {NOT_RUN} = that point never ran on that "
        "build. Both are read as absent, never as zero."
    )
    failed = sum(
        view.cell(point, build).failed_count for point in view.points for build in view.builds
    )
    if failed:
        print(
            f"{failed} of the recorded runs ended in a FAILED status; their time is "
            "time to a failure, not time to an answer"
        )

    if args.compare:
        return _print_cost_comparison(view, args.compare)
    return 0


def _cost_row_text(view: CostView, point: PointKey) -> dict[str, str]:
    """Render one pivot row, keeping absence distinguishable from a zero.

    The two empty cells are printed differently on purpose: a point that
    ran and was not timed is evidence with a hole in it, and a point that
    never ran on that build is not evidence at all. Neither is a number.
    """
    row: dict[str, str] = {"sim_id": point.sim_id, "point": point.label}
    for build in view.builds:
        cell = view.cell(point, build)
        seconds = cell.wall_time_s
        if seconds is None:
            row[build.label] = ABSENT if cell.recorded else NOT_RUN
        else:
            row[build.label] = f"{seconds:.2f}"
    return row


def _print_cost_comparison(view: CostView, spec: str) -> int:
    """Print a baseline-to-candidate comparison over the points both timed."""
    baseline, separator, candidate = spec.partition(",")
    if not separator or not candidate.strip():
        print(
            f"--compare expects BASELINE,CANDIDATE, got {spec!r}; the two names are "
            "column labels as the table above spells them",
            file=sys.stderr,
        )
        return 2
    try:
        comparison = view.compare(baseline.strip(), candidate.strip())
    except ValueError as error:
        print(f"nothing compared: {error}", file=sys.stderr)
        return 2
    print("")
    for pair in comparison.paired:
        ratio = "-" if pair.ratio is None else f"{pair.ratio:.2f}"
        print(
            f"{pair.point.sim_id}  {pair.point.label}  "
            f"{pair.baseline_s:.2f} -> {pair.candidate_s:.2f}  x{ratio}"
        )
    for point in comparison.unpaired:
        print(f"{point.sim_id}  {point.label}  not timed on both builds, left out")
    total = "unknown" if comparison.ratio is None else f"{comparison.ratio:.2f}"
    print(
        f"{len(comparison.paired)} point(s) compared, {len(comparison.unpaired)} unpaired: "
        f"{comparison.baseline_total_s:.2f} s -> {comparison.candidate_total_s:.2f} s, "
        f"overall x{total} (above 1 means the candidate build is slower)"
    )
    return 0


def _cmd_cases(args: argparse.Namespace) -> int:
    rows = case_table(include_smi=args.include_smi)
    # The COLUMN HEADING is the renderer's choice and the KEY is the
    # data's; they were the same word and the value stopped being a
    # list of versions, so the key moved and the heading follows the
    # meaning rather than the old name.
    header = {
        "case_id": "CASE",
        "title": "TITLE",
        "metrics": "METRICS",
        "minimum_version": "MINIMUM VERSION",
    }
    widths = {key: max(len(header[key]), *(len(str(row[key])) for row in rows)) for key in header}
    line = "  ".join(header[key].ljust(widths[key]) for key in header)
    print(line.rstrip())
    for row in rows:
        line = "  ".join(str(row[key]).ljust(widths[key]) for key in header)
        print(line.rstrip())
    print(f"{len(rows)} case(s); every physics validation is one matrix line with an id")
    return 0


def _resolve_or_report(version: str) -> str | None:
    """Resolve one user-typed version, reporting a refusal instead of raising.

    A version string reaches every ``pyfs-qa`` subcommand straight from
    argparse, and both refusals it can meet (unregistered identifier,
    vendor name shared by several builds) are ordinary user error.
    Letting them propagate showed a traceback where the library's own
    message already says what to do.

    Parameters
    ----------
    version : str
        Canonical identifier or vendor release name, as typed.

    Returns
    -------
    str or None
        The canonical identifier, or ``None`` when the refusal has
        already been printed and the caller should exit 2.
    """
    try:
        return resolve(version).canonical
    except (AmbiguousVersionAliasError, UnknownVersionError) as error:
        print(f"version not resolved: {error}", file=sys.stderr)
        return None


def _cmd_probe(args: argparse.Namespace) -> int:
    canonical = _resolve_or_report(args.fs_version)
    if canonical is None:
        return 2
    commands = None
    if args.identity_only:
        # The empty list, which probe_version reads as "the baseline and
        # nothing else". A build that records no commands cannot be
        # probed for one, and its solver_identity is what the version
        # registry needs before anything else can happen.
        commands = []
    elif args.commands:
        commands = [name.strip() for name in args.commands.split(",") if name.strip()]

    # BEFORE the solver starts, for the reason the shared helper states.
    # ONE date for the whole run: resolved here, asked about here, and
    # stamped by the writer below. Each writer used to resolve its own a
    # moment later, so a run started at 23:59 checked one stem and wrote
    # another, which is a missed refusal and therefore a licensed seat.
    date = resolve_report_date()
    if _refuse_before_the_solver(
        compat_report_paths(args.report_dir, version=canonical, date=date, label=args.label)
    ):
        return 2

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
    yaml_path, md_path = write_compat_report(run, args.report_dir, date=date, label=args.label)
    counts = run.outcome_counts()
    # Iterated, not a hardcoded triple: the counts are derived from the
    # outcome enum, so a listed subset makes this line disagree with the
    # Markdown report beside it and stop summing to the command count.
    print(
        f"FlightStream {run.version} ({run.fs_exe_name}): "
        + ", ".join(f"{count} {name}" for name, count in counts.items())
    )
    for line in run.solver_identity:
        print(f"solver: {line}")
    print(f"report: {yaml_path}")
    print(f"report: {md_path}")
    return 0


def _refuse_before_the_solver(paths: tuple[Path, Path]) -> bool:
    """Ask whether the report already exists, BEFORE anything is run.

    The refusal is right and its POSITION was wrong, in all THREE evidence
    writers. It was hoisted for `probe` on 2026-08-17, after a full
    campaign of 111 command probes over five minutes of licensed solver
    ran to completion and was then discarded on a stem collision knowable
    from the command line. `physics` and `drift` kept the defect until the
    review round of the same day: the whole Tier 3 matrix could still run
    and then die on an uncaught FileExistsError, which is worse than the
    original, because probe at least caught and printed.

    Returns True when the caller must stop.

    IT NO LONGER BUILDS THE NAME, which is the correction of 2026-08-18.
    It took a series prefix and an already-derived build key, so this
    function and the writer it protects each spelled the stem once and
    agreed by coincidence; sabotaging one writer's prefix left the whole
    suite green, so the guard was decorative for two of the three series.
    Each caller now asks the SERIES' OWN helper for the pair and hands it
    both here and to the writer, so there is one expression and one date.
    """
    try:
        refuse_existing_report(*paths)
    except FileExistsError as error:
        # RE-WORDED IN THIS CLI'S FLAGS. The library names its own
        # parameter, which is right for a Python caller; here the reader
        # has a command line in front of them and the two escapes have
        # names they can type.
        print(
            f"nothing run: {error} From this command line those are --label and --report-dir.",
            file=sys.stderr,
        )
        return True
    return False


def _cmd_physics(args: argparse.Namespace) -> int:
    """Run the workspace's physics matrix, reduce it and write the report.

    The build the stem names is read off the matrix rows BEFORE anything
    runs, so the pre-flight below can refuse a colliding stem while the
    seat is still unspent; the run's own version, read back from the
    records, is what the writer stamps, and the pairing test in
    ``tests/tier1_offline/test_qa_cli.py`` holds the two to one stem.
    """
    try:
        matrix = physics_matrix(args.workspace, args.matrix)
        canonical = physics_build(matrix)
    except (PhysicsEnvironmentError, MatrixError, OSError) as error:
        print(f"nothing run: {error}", file=sys.stderr)
        return 2
    date = resolve_report_date()
    if _refuse_before_the_solver(
        physics_report_paths(args.report_dir, version=canonical, date=date, label=args.label)
    ):
        return 2
    try:
        run = physics_from_workspace(
            args.workspace, matrix=args.matrix, name=args.name, resume=args.resume
        )
    except PhysicsEnvironmentError as error:
        print(f"physics run aborted: {error}", file=sys.stderr)
        return 2
    except _RUN_LAYER_REFUSALS as error:
        print(f"matrix not run: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_physics_report(run, args.report_dir, date=date, label=args.label)
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
    versions = [name.strip() for name in args.fs_versions.split(",") if name.strip()]
    if len(versions) != 2:
        print(
            "drift compares exactly two versions, baseline first "
            "(for example --fs-versions 26.100,26.120)",
            file=sys.stderr,
        )
        return 2
    fs_exes: dict[str, str] = {}
    for item in args.fs_exe:
        version, separator, path = item.partition("=")
        if not separator or not path:
            print(f"--fs-exe expects VERSION=PATH, got {item!r}", file=sys.stderr)
            return 2
        canonical = _resolve_or_report(version.strip())
        if canonical is None:
            return 2
        fs_exes[canonical] = path.strip()
    canonicals = []
    for version in versions:
        canonical = _resolve_or_report(version)
        if canonical is None:
            return 2
        canonicals.append(canonical)
    missing = [canonical for canonical in canonicals if canonical not in fs_exes]
    if missing:
        print(
            f"no executable given for {', '.join(missing)}; pass --fs-exe VERSION=PATH",
            file=sys.stderr,
        )
        return 2
    try:
        physics_matrix(args.workspace, args.matrix)
    except PhysicsEnvironmentError as error:
        print(f"nothing run: {error}", file=sys.stderr)
        return 2
    date = resolve_report_date()
    if _refuse_before_the_solver(
        drift_report_paths(
            args.report_dir,
            version_a=canonicals[0],
            version_b=canonicals[1],
            date=date,
            label=args.label,
        )
    ):
        return 2
    try:
        run = drift_from_workspace(
            args.workspace,
            canonicals[0],
            canonicals[1],
            fs_exes=fs_exes,
            workroot=args.workroot,
            matrix=args.matrix,
            name=args.name,
        )
    except PhysicsEnvironmentError as error:
        print(f"drift run aborted: {error}", file=sys.stderr)
        return 2
    except _RUN_LAYER_REFUSALS as error:
        print(f"matrix not run: {error}", file=sys.stderr)
        return 2
    yaml_path, md_path = write_drift_report(run, args.report_dir, date=date, label=args.label)
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
    # Trapped like every sibling subcommand: the library's refusals here
    # say what to do (which report supersedes this one, which page
    # contradicts a measured removal), and a traceback buries that under
    # a stack the operator did not ask for.
    try:
        report_body = read_compat_report(args.report).get("commands", {})
        promotions = apply_compat(args.report, repo_root=args.root)
    except QaEvidenceError as error:
        print(f"nothing promoted: {error}", file=sys.stderr)
        return 2
    if not promotions:
        promotable = ", ".join(sorted(str(o) for o in PROMOTABLE_OUTCOMES))
        # The remedy is derived from the report rather than assumed. An
        # --identity-only run records every command "not probed in this
        # run" and applying it is a documented step of registering a
        # build, so the operator most likely to reach this line is one
        # whose next step is a fuller run, not a new specification.
        reasons = [str(body.get("detail", "")) for body in report_body.values()]
        dominant = max(set(reasons), key=reasons.count) if reasons else ""
        remedy = (
            "re-run pyfs-qa probe without --identity-only, and with --fsm if the "
            "specifications need an opened simulation"
            if "not probed in this run" in dominant
            else "add a probe specification for the commands you need judged, or "
            "supply --fsm, and re-run pyfs-qa probe"
        )
        print(
            f"nothing to promote: the promotable outcomes are {promotable}, and this "
            f"report records none of them. Every command in it is unprobed. Most "
            f"common reason recorded: {dominant[:90]!r}. Next step: {remedy}"
        )
        return 0
    for name, status, chapter in promotions:
        print(f"{name}: {status} ({chapter})")
    CommandRegistry.load.cache_clear()
    try:
        CommandRegistry.load()
    except ValueError as error:
        # The writes have landed by now, so the one thing the operator
        # needs is which state the tree is in.
        print(
            f"promoted, but the database no longer loads: {error}. The chapter files "
            "on disk carry the promotions; repair or revert them",
            file=sys.stderr,
        )
        return 2
    print(f"{len(promotions)} status(es) promoted; database reloaded and valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
