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
refusal of a name already in ``raw/`` and the pre-run refusal of a
declared output already in the simulation folder both say to archive
the simulation and re-run, and until 0.13.0 the command they named was
not there. The refusal of a simulation the manifest does not record is
``archive_sim``'s own, printed to stderr with exit 2.
"""

from __future__ import annotations

import argparse
import sys

from pyflightstream.workspace import INPUT_KINDS, CampaignWorkspace, WorkspaceError


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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-workspace``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    if args.subcommand == "archive":
        return _cmd_archive(args)
    return _cmd_init(args)


def _cmd_init(args: argparse.Namespace) -> int:
    workspace = CampaignWorkspace.init(args.root)
    # `.root` is already absolute; the workspace resolves it once at
    # construction. Re-resolving here would tell a reader it might not be.
    print(f"campaign workspace ready at {workspace.root}")
    for kind in INPUT_KINDS:
        print(f"  inputs/{kind}/")
    print("  inputs/executables.toml (build registry)")
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


if __name__ == "__main__":
    raise SystemExit(main())
