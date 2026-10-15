"""The ``pyfs-workspace`` command line.

Every subcommand accepts ``--workspace PATH`` (0.40.0,
PFS-2089.004), defaulting to the current directory. For example,
``pyfs-workspace init --workspace campaign`` creates the campaign tree there.
``init`` and ``migrate`` take the positional root, and naming
two different folders is refused. ``archive SIM_ID --workspace ROOT`` names
the campaign the same way; ``archive ROOT SIM_ID`` still works and warns that
the positional root is deprecated.

Pipeline role: drives the managed campaign workspace from a terminal.
``pyfs-workspace init <root>`` creates the full campaign tree (the
input-artifact library skeleton under ``inputs/``, ``sims/``,
``post/``, and ``archive/``) idempotently, so a campaign starts from
the managed layout instead of hand-built folders; identity stays in
the manifest, never in names (SAD Section 6).

``pyfs-workspace archive <sim_id> --workspace <root>`` zips one manifest-recorded
simulation under ``archive/`` and removes its folder, through
:meth:`CampaignWorkspace.archive_sim`. It exists because two refusals
already told the user to run it (OPS-2009.01.10): the collection
refusal of a name already in a point's own ``datapoints/`` folder and
the pre-run refusal of a
declared output already in the simulation folder both say to archive
the simulation and re-run, and until 0.13.0 the command they named was
not there. The refusal of a simulation the manifest does not record is
``archive_sim``'s own, printed to stderr with exit 2.

``pyfs-workspace migrate <root>`` previews migration from the 0.38.0 record
format; ``--apply`` backs up each rewritten file. See docs/upgrading.md.

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

0.39.0 (FR-436) reads the workspace settings files ``pyfs.toml`` and
``pyfs.local.toml`` through :mod:`pyflightstream.workspace._settings_file`,
which owns their schema, the precedence and the provenance: this program
takes their ``[log]`` console level only (FR-1000). The command-line side of the
same files lives here too, because the parsing of a command line stays in
the command families (FR-1002): :func:`withhold_defaults` and
:func:`take_settings` adapt an ``argparse`` parser so that an option the
command line does not state takes its default from the files, and
``pyfs-matrix`` parses through them.
"""

from __future__ import annotations

import argparse
import glob
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream._cli import cli_entrypoint
from pyflightstream._console import command_help
from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._progress import command_console, say_summary
from pyflightstream.workspace import (
    INPUT_KINDS,
    CampaignWorkspace,
    InputArtifactError,
    WorkspaceError,
)
from pyflightstream.workspace import actuator_profiles as _profiles
from pyflightstream.workspace import fields as _fields
from pyflightstream.workspace._settings_file import (
    DEFAULT_KEYS,
    TakenDefaults,
    WorkspaceSettings,
    console_only,
    declare_invocation,
    invocation,
    read_workspace_settings,
    settings_supplied,
    take_defaults,
)

__all__ = [
    "WITHHELD",
    "fill_from_settings",
    "main",
    "register_command_group",
    "take_settings",
    "typed_value",
    "withhold_defaults",
]

#: The command groups a higher layer registers, as (name, parser builder,
#: handler): ``geometry`` (FR-471 to FR-477) runs the solver, which the run
#: layer owns, so its group is registered from there at import, the way the post
#: stages are, and this module never imports the run layer.
_COMMAND_GROUPS: list[tuple[str, Callable[[Any], None], Callable[[argparse.Namespace], int]]] = []


def register_command_group(
    name: str,
    add: Callable[[Any], None],
    handler: Callable[[argparse.Namespace], int],
) -> None:
    """Register a command group of ``pyfs-workspace`` that a higher layer defines.

    Parameters
    ----------
    name : str
        The subcommand, such as ``geometry``.
    add : callable
        Adds the group's parser to the subparsers it is given.
    handler : callable
        Runs the parsed command and returns its exit code.
    """
    if all(entry[0] != name for entry in _COMMAND_GROUPS):
        _COMMAND_GROUPS.append((name, add, handler))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-workspace",
        description=(
            "Managed campaign workspace tooling; the tree it creates is owned by "
            "pyflightstream and never hand-built."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    migration = subparsers.add_parser(
        "migrate",
        help="preview the record migration from 0.38.0; --apply writes backups and records",
    )
    migration.add_argument("root", nargs="?", default=".")
    migration.add_argument("--apply", action="store_true")

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
            "Zips sims/sim_<sim_id>/ of a recorded simulation into archive/ and removes "
            "the folder, so the simulation can be re-run into a clean folder while its "
            "evidence stays. Refuses a simulation the manifest (runs.json) does not "
            "record, and an archive name already taken: file management never destroys "
            "an unrecorded run or an earlier archive. It does not read the status of the "
            "simulation's runs, so a failed or stale run is archived like a finished one; "
            "do not archive a simulation whose run is still going."
        ),
    )
    archive.add_argument(
        "root",
        nargs="?",
        help="deprecated positional alias of --workspace; still accepted with a warning",
    )
    archive.add_argument(
        "sim_id",
        help="the simulation to archive, as the manifest records it (the folder is "
        "sims/sim_<sim_id>/)",
    )

    # THE CAMPAIGN IS NAMED AS EVERY OTHER SUBCOMMAND NAMES IT (PFS-2089.004): --workspace,
    # beside the positional roots retained for compatibility.
    for command in (init, archive, migration):
        command.add_argument(
            "--workspace",
            help="campaign workspace (default: the current directory); the positional "
            "root names the same folder",
        )
    _add_field_commands(subparsers)
    _add_profile_commands(subparsers)
    for _, add, _ in _COMMAND_GROUPS:
        add(subparsers)
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
    _take_the_console_level(args)
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
        if args.subcommand == "migrate":
            from pyflightstream.workspace.migrate import migrate_workspace

            try:
                changes = migrate_workspace(_campaign_root(args), apply=args.apply)
            except (WorkspaceError, OSError) as error:
                print(str(error), file=sys.stderr)
                return 2
            for change in changes:
                print(
                    f"{change['file']}: schema_version=4, id, artifacts and shared definition ids; "
                    f"{change['before_bytes']} -> {change['after_bytes']} bytes; "
                    f"backup {change['backup']}"
                )
            print(
                "migration applied"
                if args.apply and changes
                else "no changes needed"
                if not changes
                else "preview only; --apply writes"
            )
            return 0
        if args.subcommand == "field":
            return _cmd_field(args)
        if args.subcommand == "profile":
            return _cmd_profile(args)
        for name, _, handler in _COMMAND_GROUPS:
            if args.subcommand == name:
                return handler(args)
        return _cmd_init(args)


def _take_the_console_level(args: argparse.Namespace) -> None:
    """Read the workspace settings files and take their console level, nothing else (FR-1000).

    The files are read and refused as every ``pyfs-matrix`` command reads
    them, before anything is written; no key of ``[defaults]`` reaches a
    command of this program.
    """
    root = getattr(args, "workspace", None) or getattr(args, "root", None) or "."
    taken = console_only(_settings_or_refusal(root))
    declare_invocation(taken, verbose=taken.console == "verbose")


def _settings_or_refusal(root: str | Path) -> WorkspaceSettings:
    """Read a workspace's settings files; a refused file stops the command, exit 2 (FR-995).

    Before the command's console opens and before anything is written, for
    both programs: the message names the key (or the parse error) and the file.
    """
    try:
        return read_workspace_settings(root)
    except InputArtifactError as error:
        print(f"workspace settings refused: {error}", file=sys.stderr)
        raise SystemExit(2) from None


# --- the command line over the settings files (FR-1002) --------------------------


class _Withheld:
    """The marker an option holds after the parse when the command line did not state it.

    A repeatable option copies its default before appending to it, so a copy of
    the marker is an empty list: a typed ``--recipe`` starts from nothing, as it
    does with the package's own empty default.
    """

    def __copy__(self) -> list[object]:
        return []

    def __repr__(self) -> str:
        return "<not typed>"


#: The one marker :func:`withhold_defaults` installs.
WITHHELD = _Withheld()

#: The console options, resolved with ``[log]`` rather than with ``[defaults]``.
_CONSOLE_OPTIONS = ("log_level", "verbose", "pproc_warnings")

#: The option whose bare flag states the negation of a settable switch, when the
#: two are separate destinations: the file must not answer over a typed negation.
_NEGATIONS = {"ignore_missing_families": "refuse_missing_families"}


@dataclass
class _Held:
    """The defaults one parser had before they were withheld, and its relaxed requirements."""

    defaults: dict[tuple[int, str], object] = field(default_factory=dict)
    relaxed: set[tuple[int, str]] = field(default_factory=set)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Return every subcommand's parser by name, aliases included."""
    found: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found.update(action.choices)
    return found


def _dests(sub: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    """Return each settable or console destination of a parser, with its first action."""
    found: dict[str, argparse.Action] = {}
    for action in sub._actions:
        # Options only: a positional sharing a key's name (the recipe id of
        # `free-space`) is never typed as an option, so no file answers for it.
        if action.option_strings and action.dest in {
            *DEFAULT_KEYS,
            *_CONSOLE_OPTIONS,
            "accept_unregistered_build",
        }:
            found.setdefault(action.dest, action)
    return found


def _named_workspace(argv: Sequence[str] | None) -> str:
    """Return the folder ``--workspace`` names on a command line, else the current one (FR-992).

    Read before the full parse, so the REQUIRED options a file supplies are
    relaxed against the files of the workspace the command names, not of
    wherever it was typed. The tokens are scanned rather than parsed: a second
    parser would be the first ``parse_args`` a reader of the command line (the
    generated command-line reference) catches. ``--workspace PATH`` and
    ``--workspace=PATH`` are read, the last one winning as in the parse; a
    malformed one is the full parse's to refuse, in its own words.
    """
    tokens = sys.argv[1:] if argv is None else list(argv)
    named = "."
    for index, token in enumerate(tokens):
        if token == "--":
            break
        if token == "--workspace" and index + 1 < len(tokens):
            named = tokens[index + 1]
        elif token.startswith("--workspace="):
            named = token.partition("=")[2]
    return named or "."


@contextmanager
def withhold_defaults(
    parser: argparse.ArgumentParser, argv: Sequence[str] | None
) -> Iterator[_Held]:
    """Hold the defaults of every settable option back for the length of one parse.

    Inside, each settable option of each subcommand defaults to
    :data:`WITHHELD`, so an option still holding it after the parse was not
    typed; a REQUIRED option a settings file of the workspace ``argv`` names
    supplies stops being required at the parse, and is required again by
    :func:`fill_from_settings` if no file answers for it after all. The
    parser's own defaults are put back on the way out, whatever happened
    inside, so the parser a reader inspects (``--help``, the generated
    command-line reference) shows the package's defaults.

    Abbreviated options are refused for the length of the parse: the
    settings are read from the folder an exact ``--workspace`` names, so an
    abbreviation argparse would expand (``--works PATH``) would parse to one
    workspace while the settings came from another.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, whose subcommands are walked.
    argv : sequence of str or None
        The command line about to be parsed; None reads ``sys.argv``.

    Yields
    ------
    _Held
        What :func:`fill_from_settings` needs to restore a default nobody stated.
    """
    supplied = settings_supplied(_named_workspace(argv))
    held = _Held()
    changed: list[tuple[argparse.Action, object, bool]] = []
    parsers = {id(sub): sub for sub in (parser, *_subparsers(parser).values())}.values()
    abbreviating = [(each, each.allow_abbrev) for each in parsers]
    for each, _ in abbreviating:
        each.allow_abbrev = False
    for sub in {id(sub): sub for sub in _subparsers(parser).values()}.values():
        for dest in _dests(sub):
            for action in (a for a in sub._actions if a.dest == dest and a.option_strings):
                changed.append((action, action.default, action.required))
                held.defaults.setdefault((id(sub), dest), action.default)
                action.default = WITHHELD
                if action.required and dest in supplied:
                    action.required = False
                    held.relaxed.add((id(sub), dest))
    try:
        yield held
    finally:
        for action, default, required in changed:
            action.default, action.required = default, required
        for each, allowed in abbreviating:
            each.allow_abbrev = allowed


def fill_from_settings(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    held: _Held,
    settings: WorkspaceSettings,
) -> TakenDefaults:
    """Give every option the command line did not state the value the files decide.

    What was typed and what was left open is read off the parse; which file
    answers is decided by
    :func:`~pyflightstream.workspace._settings_file.take_defaults`; an option
    no file answers for gets its package default back, required where it was
    required.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, as :func:`withhold_defaults` left it.
    args : argparse.Namespace
        The parsed command line, changed in place.
    held : _Held
        What :func:`withhold_defaults` yielded.
    settings : WorkspaceSettings
        The workspace's settings files, read.

    Returns
    -------
    TakenDefaults
        What the command took from the files.
    """
    sub = _subparsers(parser)[args.subcommand]
    actions = _dests(sub)
    typed = {
        dest: getattr(args, dest)
        for dest in actions
        if getattr(args, dest, WITHHELD) is not WITHHELD
    }
    taken = take_defaults(
        settings,
        typed,
        [dest for dest in actions if dest not in typed and dest in DEFAULT_KEYS],
        negated={key for key, flag in _NEGATIONS.items() if getattr(args, flag, False)},
        console="log_level" in actions,
        post_warnings="pproc_warnings" in actions,
    )
    for dest, action in actions.items():
        if dest in typed:
            continue
        if dest in taken.values:
            value = taken.values[dest]
        elif (id(sub), dest) in held.relaxed:
            sub.error(f"the following arguments are required: {'/'.join(action.option_strings)}")
        else:
            value = held.defaults.get((id(sub), dest))
        if isinstance(value, str) and callable(action.type) and dest not in _CONSOLE_OPTIONS:
            value = action.type(value)
        setattr(args, dest, value)
    if "log_level" in actions:
        shown = taken.console or ("verbose" if typed.get("verbose") is True else "normal")
        args.log_level, args.verbose = shown, shown == "verbose"
    if "pproc_warnings" in actions:
        chosen = typed.get("pproc_warnings", taken.values.get("log.pproc_warnings", False))
        args.pproc_warnings = bool(chosen)
    return taken


def take_settings(parser: argparse.ArgumentParser, args: argparse.Namespace, held: _Held) -> None:
    """Take what a parsed command line did not state from its workspace's files (FR-436).

    An option typed wins over ``pyfs.local.toml``, which wins over
    ``pyfs.toml``, which wins over the package default, and a workspace
    holding neither file parses exactly as before. A file the reader refuses
    stops the command here, exit 2, before its console opens and before
    anything is written. What was taken holds for the rest of the invocation.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, as :func:`withhold_defaults` left it.
    args : argparse.Namespace
        The command line parsed inside :func:`withhold_defaults`, changed in place.
    held : _Held
        What :func:`withhold_defaults` yielded.
    """
    settings = _settings_or_refusal(getattr(args, "workspace", None) or ".")
    taken = fill_from_settings(parser, args, held, settings)
    declare_invocation(taken, verbose=bool(getattr(args, "verbose", False)))


def typed_value(args: argparse.Namespace, flag: str) -> object:
    """Return the value of ``flag`` where the command line typed it, else None (FR-993).

    A value a workspace settings file supplied is not the command line's: a
    command that judges what was asked of it judges the typed value alone, and
    leaves unused a file's value it does not use.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line, as :func:`take_settings` left it.
    flag : str
        The long option, ``--fs-exe`` for instance.

    Returns
    -------
    object
        The option's value, or None where a settings file supplied it.
    """
    dest = flag.removeprefix("--").replace("-", "_")
    return None if dest in invocation().sources else getattr(args, dest)


def _campaign_root(args: argparse.Namespace) -> str:
    """Return the campaign folder a command names by --workspace or by its positional root.

    Both spellings name one folder (PFS-2089.004); two different folders are refused,
    after the command's titled block, as every refusal is.
    """
    named = getattr(args, "workspace", None)
    root = str(getattr(args, "root", None) or ".")
    if named is None:
        return root
    if root not in (".", named):
        raise WorkspaceError(
            f"the campaign is named twice: --workspace {named!r} and the positional root "
            f"{root!r}. Name it once."
        )
    return str(named)


def _cmd_init(args: argparse.Namespace) -> int:
    # Refused like every sibling subcommand (PFS-2095.059): a bad root is a message and
    # exit 2, never a traceback.
    try:
        workspace = CampaignWorkspace.init(_campaign_root(args))
    except (OSError, WorkspaceError, InputArtifactError) as error:
        print(str(error), file=sys.stderr)
        return 2
    # `.root` is already absolute; the workspace resolves it once at
    # construction. Re-resolving here would tell a reader it might not be.
    say_summary(f"campaign workspace ready at {workspace.root}")
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
    try:
        workspace = CampaignWorkspace(_campaign_root(args))
        if args.root is not None:
            warn(
                "archive's positional root is deprecated since 0.40.0; it is an alias of "
                "--workspace, which gives the identical result: write "
                f"pyfs-workspace archive {args.sim_id} --workspace {args.root}.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        bundle = workspace.archive_sim(args.sim_id)
    except (OSError, WorkspaceError) as error:
        print(str(error), file=sys.stderr)
        return 2
    say_summary(
        f"archived sim_{args.sim_id} to {bundle}; the folder sims/sim_{args.sim_id}/ is removed"
    )
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
        say_summary("nothing written; run again with --apply to write")
        return 0
    for path in written.overwritten:
        print(f"replaced {path}")
    say_summary(f"wrote {written.target} and {written.sidecar.name}")
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
        say_summary("nothing written; run again with --apply to write")
        return 0
    for path in written.overwritten:
        print(f"replaced {path}")
    say_summary(f"wrote {written.target} and {written.sidecar.name}")
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
    if args.pol is None and args.family is not None:
        raise WorkspaceError(
            "--family names the family whose table --pol finds; a named table is read as it is, "
            "so leave --family out."
        )
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
    inputs: list[dict[str, object]] = [_table_input(Path(table), Path(args.workspace))]
    what = f"{table}, thrust {component}, {len(loads.stations)} stations, {loads.clipped} set to 0"
    return "SECTIONS", _profiles.sections_profile(loads, disc), parameters, inputs, what


def _table_input(table: Path, root: Path) -> dict[str, object]:
    """Return the record of a table read: workspace-relative inside the workspace, else as named."""
    try:
        path = table.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        path = str(table)
    return {"path": path, "sha256": file_sha256(table)}


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
        say_summary("nothing written; run again with --apply to write")
        return
    for path in written.overwritten:
        print(f"replaced {path}")
    say_summary(
        f"wrote {written.target} and {written.sidecar.name}; a row names it PROFILE: {args.out}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
