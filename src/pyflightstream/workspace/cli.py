"""The ``pyfs-workspace`` command line.

Pipeline role: drives the managed campaign workspace from a terminal.
``pyfs-workspace init <root>`` creates the full campaign tree (the
input-artifact library skeleton under ``inputs/``, ``sims/``,
``post/``, and ``archive/``) idempotently, so a campaign starts from
the managed layout instead of hand-built folders; identity stays in
the manifest, never in names (SAD Section 6).

``pyfs-workspace archive <root> <sim_id>`` zips one manifest-recorded
simulation under ``archive/`` and removes its folder, through
:meth:`CampaignWorkspace.archive_sim`. It exists because two refusals
already told the user to run it (OPS-2009.01.10): the collection
refusal of a name already in a point's own ``datapoints/`` folder and
the pre-run refusal of a
declared output already in the simulation folder both say to archive
the simulation and re-run, and until 0.13.0 the command they named was
not there. The refusal of a simulation the manifest does not record is
``archive_sim``'s own, printed to stderr with exit 2.

``pyfs-workspace migrate-geometries <root>`` moves a flat geometry
library into one folder per geometry, each with its boundary inventory
and provenance record, through :func:`migrate_geometry_layout`
(PFS-2032.05, the reading of design 68 section A3). It says what it
moved and which folders it left alone, moves nothing on a second run,
and refuses a root with no ``inputs/geometries`` with exit 2. Nothing
migrates by itself, and the flat layout is not deprecated.

``pyfs-workspace field mirror|move|subtract|time-mean`` builds a custom
free-stream file of ``inputs/freestreams/`` out of other fields, through
:mod:`pyflightstream.workspace.fields` (0.31.0): a field mirrored through a
coordinate plane, moved so a source point lands on a target point, one
field subtracted from another on the same grid (with a stated reference
free stream), or the time mean of an unsteady run's per-step fields. Each
previews by default and writes only with ``--apply`` into the workspace
named by ``--workspace`` (the current directory by default), the file and its
``<stem>.provenance.json``, and never overwrites without ``--overwrite``; a
refusal is printed to stderr with exit 2.

0.32.0 adds ``field fill-interior`` (the probes inside the body radius
``--r-body``, 0.38 m by default, take the value of the nearest probe outside it
on the same azimuth ray) and, on ``field time-mean``, ``--fluctuation`` (the
per-probe population standard deviation of the averaged steps, written beside
the mean as ``<stem>.fluctuation.csv`` and named in its provenance) and
``--fluctuation-only --last K`` (that report alone, no field).

0.34.0 adds ``pyfs-workspace profile sections|uni|bp`` (FR-347), the radial
thrust profile of an actuator disc a row's ``PROFILE`` names, written into
``inputs/profiles/<stem>.csv`` with its provenance record through
:mod:`pyflightstream.workspace.actuator_profiles`: from a POL's written
sections, or as the uniform or the Betz-Prandtl shape, scaled to a thrust or
a CT. It previews and applies as the field operations do, and refuses an
option of another shape rather than leave it unread.
"""

from __future__ import annotations

import argparse
import glob
import sys
from typing import Any

from pyflightstream._cli import cli_entrypoint
from pyflightstream._console import command_help
from pyflightstream._digest import file_sha256
from pyflightstream._progress import command_console
from pyflightstream.workspace import (
    INPUT_KINDS,
    CampaignWorkspace,
    InputArtifactError,
    WorkspaceError,
    migrate_geometry_layout,
)
from pyflightstream.workspace import actuator_profiles as _profiles
from pyflightstream.workspace import fields as _fields

__all__ = [
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-workspace",
        description=(
            "Managed campaign workspace tooling; the tree it creates is owned by "
            "pyflightstream and never hand-built."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init = subparsers.add_parser(
        "init",
        help="create the full campaign tree (inputs library, sims, post, archive)",
    )
    init.add_argument(
        "root",
        nargs="?",
        default=".",
        help="campaign root to create or complete (default: the current directory)",
    )

    archive = subparsers.add_parser(
        "archive",
        help="zip one recorded simulation under archive/ and remove its folder",
        description=(
            "Zips sims/sim_<sim_id>/ of a completed simulation into archive/ and removes "
            "the folder, so the simulation can be re-run into a clean folder while its "
            "evidence stays. Refuses a simulation the manifest (runs.json) does not "
            "record, and an archive name already taken: file management never destroys "
            "an unrecorded run or an earlier archive."
        ),
    )
    archive.add_argument("root", help="campaign root carrying runs.json and sims/")
    archive.add_argument(
        "sim_id",
        help="the simulation to archive, as the manifest records it (the folder is "
        "sims/sim_<sim_id>/)",
    )

    migrate = subparsers.add_parser(
        "migrate-geometries",
        help="move a flat inputs/geometries library into one folder per geometry",
        description=(
            "Moves every inputs/geometries/<stem>.<ext> into inputs/geometries/<stem>/ "
            "with its <stem>.boundaries.toml and <stem>.provenance.toml, so what belongs "
            "to one geometry sits in one place and a point stages that geometry's files "
            "only. A folder that already exists is left alone, a second run moves "
            "nothing, and the GEOMETRY cells of a matrix do not change: the package reads "
            "both layouts, the folder first. Refuses a root with no inputs/geometries."
        ),
    )
    migrate.add_argument(
        "root",
        nargs="?",
        default=".",
        help="campaign root carrying inputs/geometries/ (default: the current directory)",
    )
    _add_field_commands(subparsers)
    _add_profile_commands(subparsers)
    return parser


def _add_output_options(sub: argparse.ArgumentParser) -> None:
    """Add the options every field operation shares: where it writes and whether it does."""
    sub.add_argument(
        "--out",
        required=True,
        metavar="STEM",
        help="the stem of the file written in inputs/freestreams/ (no extension: the form "
        "gives it, .txt STRUCTURED, .dat UNSTRUCTURED)",
    )
    sub.add_argument(
        "--workspace",
        default=".",
        help="campaign workspace whose inputs/freestreams/ receives the field (default: the "
        "current directory)",
    )
    sub.add_argument("--apply", action="store_true", help="write the files (default: preview)")
    sub.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing <stem> file and its provenance record",
    )


def _add_tolerance(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--tolerance",
        type=float,
        default=_fields.POSITION_TOLERANCE_M,
        metavar="M",
        help="two positions closer than this, in m along each axis, are one point "
        f"(default: {_fields.POSITION_TOLERANCE_M:g})",
    )


def _add_field_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``field`` group: four operations that write a custom free-stream file."""
    field = subparsers.add_parser(
        "field",
        help="build a custom free-stream file of inputs/freestreams/ from other fields",
        description=(
            "Builds a custom free-stream field (the file a row's FREESTREAM names) from other "
            "fields: mirror, move, subtract, time-mean. Metres and m/s in the global frame, "
            "nothing converted. Previews by default; --apply writes inputs/freestreams/"
            "<stem>.txt or .dat and <stem>.provenance.json (operation, parameters, inputs "
            "with sha256), and an existing file is replaced only with --overwrite."
        ),
    )
    operations = field.add_subparsers(dest="field_command", required=True)

    mirror = operations.add_parser(
        "mirror",
        help="mirror a field through the plane x = 0, y = 0 or z = 0",
        description=(
            "Mirrors a field through a coordinate plane: through y = 0 each row x y z vx vy vz "
            "becomes x -y z vx -vy vz. The row order and a STRUCTURED header are kept."
        ),
    )
    mirror.add_argument("field", help="the field file (.txt STRUCTURED or .dat UNSTRUCTURED)")
    mirror.add_argument(
        "--plane",
        required=True,
        choices=sorted(_fields.MIRROR_PLANES),
        help="the coordinate whose sign changes: y mirrors through the plane y = 0",
    )
    _add_output_options(mirror)

    move = operations.add_parser(
        "move",
        help="translate a field so a source point lands on a target point",
        description=(
            "Translates every position by (target - source), so the source point (a hub) "
            "lands on the target point; the velocities are unchanged."
        ),
    )
    move.add_argument("field", help="the field file (.txt STRUCTURED or .dat UNSTRUCTURED)")
    for flag, dest, what in (
        ("--source-point", "source_point", "the source point (a hub)"),
        ("--target-point", "target_point", "the point the source point lands on"),
    ):
        move.add_argument(
            flag,
            dest=dest,
            nargs=3,
            type=float,
            required=True,
            metavar=("X", "Y", "Z"),
            help=f"{what} in m, global frame",
        )
    _add_output_options(move)

    subtract = operations.add_parser(
        "subtract",
        help="total - (other - reference), point by point on one grid",
        description=(
            "Subtracts OTHER from TOTAL point by point, matched by position: the result is "
            "total - (other - reference), with --reference the uniform free stream OTHER was "
            "solved in, so only the velocity OTHER's body induces is removed. --reference is "
            "required: state 0 0 0 only where OTHER is already induced-only (its free stream "
            "taken out), and the result is then total - other. Two grids that are not one "
            "point set are refused."
        ),
    )
    subtract.add_argument("total", help="the field subtracted from (its positions are kept)")
    subtract.add_argument("other", help="the field subtracted, on the same grid")
    subtract.add_argument(
        "--reference",
        nargs=3,
        type=float,
        required=True,
        metavar=("VX", "VY", "VZ"),
        help="the free stream OTHER was solved in, m/s, global frame (required; 0 0 0 only "
        "where OTHER is already induced-only)",
    )
    _add_tolerance(subtract)
    _add_output_options(subtract)

    mean = operations.add_parser(
        "time-mean",
        help="the time mean of an unsteady run's per-step fields",
        description=(
            "Averages the per-step fields of an unsteady run (<point>_field_NN_step_<N>"
            ".inflow.dat, written by the post from a [[probes]] entry with reusable_inflow) "
            "into one field. The steps must be equally spaced and hold the same points."
        ),
    )
    mean.add_argument("files", nargs="+", help="the per-step field files, or glob patterns")
    mean.add_argument(
        "--last",
        type=int,
        default=None,
        metavar="K",
        help="average only the last K steps given (default: every step given)",
    )
    mean.add_argument(
        "--fluctuation",
        action="store_true",
        help="also write <stem>.fluctuation.csv: the per-probe population standard deviation "
        "of the averaged steps (needs at least two steps)",
    )
    mean.add_argument(
        "--fluctuation-only",
        action="store_true",
        help="report the fluctuation only, with no field (needs --last)",
    )
    mean.add_argument(
        "--vinf",
        type=float,
        default=None,
        metavar="M_S",
        help="the free-stream speed, in m/s, the fluctuation summary is also stated against",
    )
    _add_tolerance(mean)
    _add_output_options(mean)

    fill = operations.add_parser(
        "fill-interior",
        help="fill the probes inside the body from the ray outside it",
        description=(
            "Every probe with r < --r-body about the x axis takes the velocity of the probe at "
            "r >= --r-body with the smallest radius on the same azimuth ray (within 1e-3 rad). "
            "A probe with no such partner is refused."
        ),
    )
    fill.add_argument("field", help="the field file (.txt STRUCTURED or .dat UNSTRUCTURED)")
    fill.add_argument(
        "--r-body",
        type=float,
        default=_fields.DEFAULT_R_BODY_M,
        metavar="M",
        help=f"the body radius about the x axis, in m (default: {_fields.DEFAULT_R_BODY_M:g})",
    )
    _add_output_options(fill)


#: The options each shape of ``profile`` reads beyond the disc, the target and the output;
#: one given to another shape is refused rather than ignored.
_SHAPE_OPTIONS = {
    "sections": ("table", "pol", "family", "component", "sign", "last"),
    "uni": ("stations",),
    "bp": ("advance_ratio", "stations"),
}


def _add_profile_commands(subparsers: argparse._SubParsersAction) -> None:
    """Add ``profile``: an actuator-disc profile of ``inputs/profiles/`` (FR-347)."""
    profile = subparsers.add_parser(
        "profile",
        help="build an actuator-disc radial thrust profile of inputs/profiles/",
        description=(
            "Builds the radial thrust profile a row's PROFILE names (the CUSTOM disc): rows "
            "r,F with r in m and F in N/m per blade, no header and no final newline, scaled so "
            "that B * integral(F dr) is the target thrust (--thrust in N, or --ct with --rho "
            "and --rpm, CT = T / (rho n^2 D^4)). The shape is 'sections' (a POL's written "
            "sections: the sectional loads table, or --pol; -Fx at the stations, a zero from "
            "the axis to the hub and a zero at the tip; --last K averages a table of several "
            "steps), 'uni' (F = c r) or 'bp' (Betz-Prandtl, --advance-ratio J). The disc is a "
            "reference's block (--ref, --disc) or stated (--tip-radius, --hub-radius, "
            "--blades). The ELLIPTICAL disc is native in the solver and needs no file: its row "
            "states ACTUATOR_THRUST. A RELAXED disc ignores a custom profile (RPT-137). "
            "Previews by default; --apply writes inputs/profiles/<stem>.csv and "
            "<stem>.provenance.json, and an existing file is replaced only with --overwrite."
        ),
    )
    profile.add_argument("shape", choices=tuple(_SHAPE_OPTIONS), help="the shape of the profile")
    profile.add_argument(
        "table", nargs="?", help="sections: the sectional loads table (or --pol to find it)"
    )
    profile.add_argument("--pol", help="sections: the POL whose table the post recorded")
    profile.add_argument("--family", help="sections: the family of --pol (default: Blade1)")
    profile.add_argument(
        "--component", choices=("Fx", "Fz"), help="sections: the force read (default: Fx)"
    )
    profile.add_argument(
        "--sign", type=int, choices=(-1, 1), help="sections: its sign (default: -1, so -Fx)"
    )
    profile.add_argument(
        "--last", type=int, metavar="K", help="sections: average the last K steps of a table"
    )
    profile.add_argument(
        "--advance-ratio", type=float, metavar="J", help="bp: J = V / (n D), required"
    )
    profile.add_argument(
        "--stations",
        type=int,
        metavar="N",
        help=f"uni, bp: radii from the hub to the tip (default: {_profiles.DEFAULT_STATIONS})",
    )
    profile.add_argument("--ref", metavar="RID", help="the reference id that declares the disc")
    profile.add_argument("--disc", metavar="NAME", help="the disc's block name in --ref")
    profile.add_argument("--tip-radius", type=float, metavar="M", help="the tip radius, in m")
    profile.add_argument("--hub-radius", type=float, metavar="M", help="the hub radius, in m")
    profile.add_argument("--blades", type=int, metavar="B", help="the blade count")
    profile.add_argument("--thrust", type=float, metavar="N", help="the target thrust, in N")
    profile.add_argument("--ct", type=float, help="the target CT = T / (rho n^2 D^4)")
    profile.add_argument("--rho", type=float, metavar="KG_M3", help="the density of --ct")
    profile.add_argument("--rpm", type=float, help="the speed of --ct, in rev/min")
    profile.add_argument(
        "--out",
        required=True,
        metavar="STEM",
        help="the stem of the file written in inputs/profiles/ (the row's PROFILE)",
    )
    profile.add_argument(
        "--workspace",
        default=".",
        help="campaign workspace whose inputs/profiles/ receives the profile (default: the "
        "current directory)",
    )
    profile.add_argument("--apply", action="store_true", help="write the files (default: preview)")
    profile.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing <stem> file and its provenance record",
    )


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-workspace``; returns the process exit code.

    Parameters
    ----------
    argv : list of str, optional
        The command-line arguments, ``sys.argv[1:]`` by default.

    Returns
    -------
    int
        The process exit code of the subcommand that ran.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    # THE CONSOLE CONTRACT (0.32.0, FR-200, FR-201): a titled opening block
    # and the warnings at the end, as every pyfs-matrix command.
    group = getattr(args, f"{args.subcommand}_command", None)
    names = [args.subcommand, *([group] if group else [])]
    with command_console(
        "pyfs-workspace",
        " ".join(names),
        what=command_help(parser, names),
        workspace=getattr(args, "workspace", None) or getattr(args, "root", None),
    ):
        if args.subcommand == "archive":
            return _cmd_archive(args)
        if args.subcommand == "migrate-geometries":
            return _cmd_migrate_geometries(args)
        if args.subcommand == "field":
            return _cmd_field(args)
        if args.subcommand == "profile":
            return _cmd_profile(args)
        return _cmd_init(args)


def _cmd_init(args: argparse.Namespace) -> int:
    workspace = CampaignWorkspace.init(args.root)
    # `.root` is already absolute; the workspace resolves it once at
    # construction. Re-resolving here would tell a reader it might not be.
    print(f"campaign workspace ready at {workspace.root}")
    for kind in INPUT_KINDS:
        print(f"  inputs/{kind}/")
    print("  inputs/executables.toml (build registry)")
    print("  inputs/pproc/VARIABLES.md, WRITING-EQUATIONS.md (generated pproc guides)")
    print("  inputs/INPUTS.md (generated input glossary; custom notes preserved)")
    print("  inputs/input_template.md (generated: an example of every input file)")
    for name in ("sims", "post", "archive"):
        print(f"  {name}/")
    print("init is idempotent: existing folders and files were kept untouched")
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    """Archive one recorded simulation; the refusals are ``archive_sim``'s own."""
    workspace = CampaignWorkspace(args.root)
    try:
        bundle = workspace.archive_sim(args.sim_id)
    except (OSError, WorkspaceError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"archived sim_{args.sim_id} to {bundle}; the folder sims/sim_{args.sim_id}/ is removed")
    return 0


def _cmd_migrate_geometries(args: argparse.Namespace) -> int:
    """Move a flat geometry library into folders; the refusal is the migration's own."""
    workspace = CampaignWorkspace(args.root)
    try:
        migration = migrate_geometry_layout(workspace.inputs_dir)
    except (OSError, InputArtifactError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for source, target in migration.moved:
        print(
            f"moved {source.relative_to(workspace.root).as_posix()} -> "
            f"{target.relative_to(workspace.root).as_posix()}"
        )
    for stem in migration.kept:
        print(f"left alone: inputs/geometries/{stem}/ (already a folder)")
    if migration.moved:
        folders = {target.parent for _, target in migration.moved}
        print(
            f"moved {len(migration.moved)} file(s) into {len(folders)} folder(s) under "
            f"{workspace.inputs_dir / 'geometries'}; the GEOMETRY cells of every matrix "
            "keep reading, the folder first"
        )
    else:
        print(f"nothing to move under {workspace.inputs_dir / 'geometries'}")
    return 0


def _expand(patterns: list[str]) -> list[str]:
    """Expand the glob patterns a shell left alone (a Windows console expands none)."""
    found: list[str] = []
    for pattern in patterns:
        if glob.has_magic(pattern):
            matches = sorted(glob.glob(pattern))
            if not matches:
                raise WorkspaceError(f"no file matches {pattern}")
            found.extend(matches)
        else:
            found.append(pattern)
    return found


def _vector(values: list[float]) -> str:
    return "(" + ", ".join(f"{v:g}" for v in values) + ")"


def _fluctuation_words(report: _fields.FluctuationReport, v_inf: float | None) -> str:
    """Say the largest and the rms fluctuation, in m/s and, given V_inf, in % of V_inf."""
    peak, rms = _fields.fluctuation_extent(report)
    words = f"fluctuation: max |std(V)| {peak:.6g} m/s, rms of std_mag {rms:.6g} m/s"
    if v_inf:
        words += f" ({100.0 * peak / v_inf:.4g} % and {100.0 * rms / v_inf:.4g} % of V_inf)"
    return words


def _cmd_fluctuation_only(args: argparse.Namespace) -> int:
    """Report the fluctuation of the last K steps with no field; preview unless --apply."""
    if args.last is None:
        raise WorkspaceError(
            "--fluctuation-only refuses to run without --last K: a steady field, or a run whose "
            "steps are not chosen, has no fluctuation to report."
        )
    steps = _fields.read_step_fields(_expand(args.files), last=args.last)
    report = _fields.fluctuation_report(steps, tolerance_m=args.tolerance)
    written = _fields.write_fluctuation(
        args.workspace,
        args.out,
        report,
        parameters={
            "steps": [each.step for each in steps],
            "last": args.last,
            "tolerance_m": args.tolerance,
        },
        inputs=[str(each.field.source) for each in steps],
        apply=args.apply,
        overwrite=args.overwrite,
    )
    print(
        f"field time-mean --fluctuation-only: {len(steps)} steps, {steps[0].step:g} to "
        f"{steps[-1].step:g}, {len(report.rows)} probes"
    )
    print("  " + _fluctuation_words(report, args.vinf))
    if not written.applied:
        print(f"preview: would write {written.target} and {written.sidecar.name}")
        print("nothing written; run again with --apply to write")
        return 0
    for path in written.overwritten:
        print(f"replaced {path}")
    print(f"wrote {written.target} and {written.sidecar.name}")
    return 0


def _cmd_field(args: argparse.Namespace) -> int:
    """Run one field operation; a preview unless --apply, a refusal to stderr with exit 2."""
    parameters: dict[str, object]
    sidecars: dict[str, str] | None = None
    try:
        if args.field_command == "mirror":
            result = _fields.mirror_field(_fields.read_field(args.field), plane=args.plane)
            inputs = [args.field]
            parameters = {"plane": f"{args.plane} = 0"}
            what = f"{args.field} mirrored through the plane {args.plane} = 0"
        elif args.field_command == "move":
            result = _fields.move_field(
                _fields.read_field(args.field),
                source_point_m=args.source_point,
                target_point_m=args.target_point,
            )
            inputs = [args.field]
            parameters = {"source_point_m": args.source_point, "target_point_m": args.target_point}
            what = (
                f"{args.field} moved from {_vector(args.source_point)} to "
                f"{_vector(args.target_point)} m"
            )
        elif args.field_command == "subtract":
            reference = args.reference
            result = _fields.subtract_fields(
                _fields.read_field(args.total),
                _fields.read_field(args.other),
                reference_m_s=reference,
                tolerance_m=args.tolerance,
            )
            inputs = [args.total, args.other]
            parameters = {
                "rule": "total - (other - reference)",
                "reference_m_s": reference,
                "tolerance_m": args.tolerance,
            }
            what = f"{args.total} - ({args.other} - {_vector(reference)} m/s)"
        elif args.field_command == "fill-interior":
            result, replaced = _fields.fill_interior(
                _fields.read_field(args.field), r_body_m=args.r_body
            )
            inputs = [args.field]
            parameters = {"r_body_m": args.r_body, "replaced": replaced}
            what = (
                f"{args.field} filled inside r < {args.r_body:g} m about the x axis: "
                f"{replaced} points replaced"
            )
        else:
            if args.fluctuation_only:
                return _cmd_fluctuation_only(args)
            steps = _fields.read_step_fields(_expand(args.files), last=args.last)
            result = _fields.time_mean_fields(steps, tolerance_m=args.tolerance)
            inputs = [str(each.field.source) for each in steps]
            parameters = {
                "steps": [each.step for each in steps],
                "last": args.last,
                "tolerance_m": args.tolerance,
            }
            what = f"the time mean of {len(steps)} steps, {steps[0].step:g} to {steps[-1].step:g}"
            if args.fluctuation:
                report = _fields.fluctuation_report(steps, tolerance_m=args.tolerance)
                sidecars = {".fluctuation.csv": _fields.render_fluctuation(report)}
                parameters["fluctuation"] = True
                what += "; " + _fluctuation_words(report, args.vinf)
        written = _fields.write_freestream(
            args.workspace,
            args.out,
            result,
            operation=args.field_command,
            parameters=parameters,
            inputs=inputs,
            apply=args.apply,
            overwrite=args.overwrite,
            sidecars=sidecars,
        )
    except (OSError, WorkspaceError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"field {args.field_command}: {what}")
    print(f"  {len(result.rows)} points, {result.form}; m and m/s, global frame, not converted")
    if not written.applied:
        print(f"preview: would write {written.target} and {written.sidecar.name}")
        print("nothing written; run again with --apply to write")
        return 0
    for path in written.overwritten:
        print(f"replaced {path}")
    print(f"wrote {written.target} and {written.sidecar.name}")
    return 0


def _profile_disc(
    args: argparse.Namespace,
) -> tuple[_profiles.DiscGeometry, dict[str, object]]:
    """Return the disc a profile is for: a reference's block, or the three stated values."""
    stated = (args.tip_radius, args.hub_radius, args.blades)
    if args.ref is not None or args.disc is not None:
        if args.ref is None or args.disc is None:
            raise WorkspaceError("a reference's disc is named by both --ref and --disc.")
        if any(value is not None for value in stated):
            raise WorkspaceError(
                "the disc is read from --ref and --disc, or stated by --tip-radius, "
                "--hub-radius and --blades, not both."
            )
        return _profiles.disc_from_reference(args.workspace, args.ref, args.disc)
    if any(value is None for value in stated):
        raise WorkspaceError(
            "name the disc: --ref RID --disc NAME (a reference's actuator block), or "
            "--tip-radius, --hub-radius and --blades."
        )
    disc = _profiles.DiscGeometry(args.tip_radius, args.hub_radius, args.blades)
    return disc, {"stated": "on the command line"}


def _refuse_foreign_options(args: argparse.Namespace) -> None:
    """Refuse an option of another shape, which this shape would not read."""
    own = set(_SHAPE_OPTIONS[args.shape])
    foreign = sorted(
        {name for names in _SHAPE_OPTIONS.values() for name in names} - own,
    )
    given = [name for name in foreign if getattr(args, name) is not None]
    if given:
        words = ", ".join(
            name if name == "table" else "--" + name.replace("_", "-") for name in given
        )
        raise WorkspaceError(
            f"profile {args.shape} does not read {words}; that belongs to another shape, and an "
            "option the shape would ignore is refused rather than left unread."
        )


def _profile_shape(
    args: argparse.Namespace, disc: _profiles.DiscGeometry
) -> tuple[str, _profiles.RadialProfile, dict[str, object], list[dict[str, object]], str]:
    """Return the shape, its profile, its parameters, its inputs and what it is, in words."""
    _refuse_foreign_options(args)
    stations = _profiles.DEFAULT_STATIONS if args.stations is None else args.stations
    if args.shape == "uni":
        profile = _profiles.uniform_profile(disc, stations=stations)
        return "UNI", profile, {"stations": stations}, [], "uniform pressure jump"
    if args.shape == "bp":
        if args.advance_ratio is None:
            raise WorkspaceError("profile bp needs the advance ratio: --advance-ratio J.")
        profile = _profiles.betz_prandtl_profile(
            disc, advance_ratio=args.advance_ratio, stations=stations
        )
        stated = {"stations": stations, "advance_ratio": args.advance_ratio}
        return "BP", profile, stated, [], f"Betz-Prandtl, J = {args.advance_ratio:g}"
    if (args.table is None) == (args.pol is None):
        raise WorkspaceError("name the sectional loads table, or --pol to find it; one of the two.")
    family = args.family or "Blade1"
    table = (
        args.table
        if args.pol is None
        else _profiles.find_pol_sections(args.workspace, args.pol, family=family)
    )
    sign = -1 if args.sign is None else args.sign
    component = f"{'-' if sign < 0 else ''}{args.component or 'Fx'}"
    loads = _profiles.read_section_loads(table, component=component, last=args.last)
    parameters: dict[str, object] = {
        "component": component,
        "steps": list(loads.steps),
        "stations": len(loads.stations),
        "negative_stations_set_to_zero": loads.clipped,
        **({"pol": args.pol, "family": family} if args.pol is not None else {}),
    }
    inputs: list[dict[str, object]] = [{"path": str(table), "sha256": file_sha256(table)}]
    what = f"{table}, thrust {component}, {len(loads.stations)} stations, {loads.clipped} set to 0"
    return "SECTIONS", _profiles.sections_profile(loads, disc), parameters, inputs, what


def _cmd_profile(args: argparse.Namespace) -> int:
    """Build one actuator-disc profile; a preview unless --apply, a refusal to stderr, exit 2."""
    try:
        disc, source = _profile_disc(args)
        target = _profiles.thrust_target(
            tip_radius_m=disc.tip_radius_m,
            thrust_n=args.thrust,
            ct=args.ct,
            rho_kg_m3=args.rho,
            rpm=args.rpm,
        )
        shape, profile, parameters, inputs, what = _profile_shape(args, disc)
        reference = source.get("file")
        written = _profiles.write_profile(
            args.workspace,
            args.out,
            profile,
            disc=disc,
            target=target,
            shape=shape,
            parameters={
                **parameters,
                "disc_source": {k: v for k, v in source.items() if k != "file"},
            },
            inputs=[*inputs, *([reference] if isinstance(reference, dict) else [])],
            apply=args.apply,
            overwrite=args.overwrite,
        )
    except (OSError, WorkspaceError, InputArtifactError) as error:
        print(str(error), file=sys.stderr)
        return 2
    _print_profile(args, written, what, source.get("wake_type"))
    return 0


def _print_profile(
    args: argparse.Namespace, written: _profiles.ProfileWrite, what: str, wake: object
) -> None:
    """Say what the profile is, its check, and what was written or would be."""
    record: dict[str, Any] = written.provenance
    target, integral, disc = record["target"], record["integral"], record["disc"]
    print(f"profile {args.shape}: {what}")
    print(
        f"  disc: tip {disc['tip_radius_m']:g} m, hub {disc['hub_radius_m']:g} m, "
        f"{disc['blades']} blades; {len(written.profile.rows)} rows r,F (m, N/m per blade)"
    )
    print(
        f"  target {target['thrust_n']:.10g} N ({target['basis']}); scale {record['scale']:.6g}; "
        f"B * integral(F dr) = {integral['blades_times_integral_n']:.10g} N "
        "(trapezoid over the written rows)"
    )
    if wake == "RELAXED":
        print(
            f"  note: the disc {args.disc!r} is RELAXED; measured on 26.124 (RPT-137) a RELAXED "
            "disc ignored a custom profile, and the plan warns on a row that names one. A "
            "RIGID disc reads the profile."
        )
    if not written.applied:
        print(f"preview: would write {written.target} and {written.sidecar.name}")
        print("nothing written; run again with --apply to write")
        return
    for path in written.overwritten:
        print(f"replaced {path}")
    print(f"wrote {written.target} and {written.sidecar.name}; a row names it PROFILE: {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
