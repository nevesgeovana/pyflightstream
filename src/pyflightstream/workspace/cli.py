"""The ``pyfs-workspace`` command line.

Pipeline role: drives the managed campaign workspace from a terminal.
``pyfs-workspace init <root>`` creates the full campaign tree (the
input-artifact library skeleton under ``inputs/``, ``sims/``,
``post/``, and ``archive/``) idempotently, so a campaign starts from
the managed layout instead of hand-built folders; identity stays in
the manifest, never in names (SAD Section 6).
"""

from __future__ import annotations

import argparse

from pyflightstream.workspace import INPUT_KINDS, CampaignWorkspace


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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-workspace``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    return _cmd_init(args)


def _cmd_init(args: argparse.Namespace) -> int:
    workspace = CampaignWorkspace.init(args.root)
    print(f"campaign workspace ready at {workspace.root.resolve()}")
    for kind in INPUT_KINDS:
        print(f"  inputs/{kind}/")
    print("  inputs/executables.toml (build registry)")
    for name in ("sims", "post", "archive"):
        print(f"  {name}/")
    print("init is idempotent: existing folders and files were kept untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
