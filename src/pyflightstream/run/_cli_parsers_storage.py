"""The parsers of the four storage subcommands of ``pyfs-matrix``.

Pipeline role: the argument side of ``space-in-use``, ``free-space``,
``delete-sims`` and ``sync``, which each also read as a flag. The parser
builder of :mod:`pyflightstream.run._cli_parsers` calls
:func:`add_storage_parsers` as one family of the command line (AD-18); the
handlers are in :mod:`pyflightstream.run.cli`.
"""

from __future__ import annotations

import argparse
from typing import Any

from pyflightstream.run._cli_selectors import _add_sim_ids


def _top_rows(text: str) -> int:
    """Parse the N of ``space-in-use --top N``: a whole number of at least 1 (PFS-2097.009)."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"top (CLI: --top) takes a whole number, not {text!r}"
        ) from None
    if value < 1:
        raise argparse.ArgumentTypeError(
            f"top (CLI: --top) takes a whole number of at least 1, not {value}"
        )
    return value


def add_storage_parsers(subparsers: Any) -> None:
    """Register the four storage subcommands; each also reads as a flag."""
    workspace_help = "the workspace root carrying runs.json (default: the current directory)"
    apply_help = "change files; without it the command previews and changes nothing"
    space = subparsers.add_parser(
        "space-in-use",
        help="report the sizes on disk: by top-level folder, by sims/sim_*, by extension",
        description=(
            "Prints the workspace's sizes in three groupings, in this order: by top-level "
            "folder, by simulation (sims/sim_*, compacted ones included) and by extension. "
            "Changes no file; the call is recorded in storage_management.json."
        ),
    )
    space.add_argument("--workspace", default=".", help=workspace_help)
    space.add_argument(
        "--top", type=_top_rows, default=15, help="rows shown per grouping (default: 15)"
    )
    free = subparsers.add_parser(
        "free-space",
        help="run a storage recipe inputs/management/m<id>.toml (preview unless --apply)",
        description=(
            "Runs the recipe's steps in order: [[prune_step_exports]] deletes an unsteady point's "
            "per-step exports (the *_iteration=<step> files) except the last step of each export "
            "(keep_last = K keeps the last K steps, delete_steps = [A, B] deletes the steps A to B "
            "and keeps the rest), and a later post refuses a product that needs a deleted step, "
            "naming it; [[compact_sims]] zips a simulation folder into sims/sim_<id>.zip (post, "
            "collect and a continuation restore it automatically), [[delete_extensions]] deletes "
            "files of the named extensions under sims/ except what a later post needs (saved "
            "simulations, scripts, logs, and every file a run record names or hashes), "
            "[[post_archives]] compacts or deletes the archive/<stamp>/ folders the post wrote. "
            "Nothing outside sims/ and the post archives is touched. Every call is recorded in "
            "storage_management.json."
        ),
    )
    free.add_argument("recipe", help="the recipe id, m<id> (inputs/management/m<id>.toml)")
    free.add_argument("--workspace", default=".", help=workspace_help)
    free.add_argument("--apply", action="store_true", help=apply_help)
    free.add_argument(
        "--list",
        dest="list_paths",
        action="store_true",
        help="after each step, print every path it would touch (preview) or touched "
        "(--apply) with its size and what happens to it",
    )
    delete = subparsers.add_parser(
        "delete-sims",
        help="delete simulations, their post products and their records (preview unless --apply)",
        description=(
            "Deletes each named simulation: its sims/sim_<id> folder (or zip), its own post "
            "products and its records in runs.json, which keeps one note row per "
            "simulation saying its id belonged to a deleted one. The full mention (id, "
            "matrix, run ids, statuses, dates, sizes and hashes, caller) is recorded in "
            "storage_management.json. The id may be reused afterwards. A product that "
            "mixes the deleted points with others needs --matrix-products: points-only "
            "leaves it, recorded stale; regenerate reruns that matrix's post without them."
        ),
    )
    delete.add_argument(
        "legacy_sims", nargs="?", help="deprecated positional alias; use --sims ID [ID ...]"
    )
    _add_sim_ids(delete)
    delete.add_argument("--workspace", default=".", help=workspace_help)
    delete.add_argument(
        "--matrix-products",
        dest="matrix_products",
        choices=("points-only", "regenerate"),
        default=None,
        help="what happens to a matrix product that also holds the deleted points",
    )
    delete.add_argument(
        "--force",
        action="store_true",
        help="delete a simulation whatever the status of its records; without it a "
        "simulation with a run still SUBMITTED is refused",
    )
    delete.add_argument("--apply", action="store_true", help=apply_help)
    delete.add_argument(
        "--archive",
        action="store_true",
        help="keep replaced matrix products when regenerating; default: overwrite in place",
    )
    sync = subparsers.add_parser(
        "sync",
        help="bring runs and results from the workspaces in inputs/sync-workspaces.toml",
        description=(
            "Levels are cumulative: runs (runs.json and run provenance: scripts/ and the "
            "datapoint logs), post (+ post/), fsm (+ the datapoints' saved simulations), all "
            "(+ everything else under sims/). Run on the main workspace. A record only in "
            "the other workspace is added; a main record still SUBMITTED takes the other's; "
            "any other difference is a conflict where main wins unless --prefer-other. A "
            "simulation still SUBMITTED there syncs its record only. A file conflict keeps "
            "main's copy unless --overwrite, which archives it first. Nothing in main is "
            "deleted and inputs/ is never touched, except a declared matrix. MATRICES: "
            "each is declared in sync-workspaces.toml by the one workspace that owns it "
            '(matrices = ["<stem>", ...]); a difference is always reported as a MERGE '
            "CONFLICT and the owning workspace's copy wins. A synced simulation's "
            "inputs/ is linked into main's own geometry library, never copied. "
            "Every call is recorded in storage_management.json."
        ),
    )
    sync.add_argument("level", choices=("runs", "post", "fsm", "all"), help="what to bring")
    sync.add_argument("--workspace", default=".", help=workspace_help)
    sync.add_argument(
        "--from",
        dest="source",
        default=None,
        help="one workspace name from sync-workspaces.toml (default: every non-main one)",
    )
    sync.add_argument("--apply", action="store_true", help=apply_help)
    sync.add_argument(
        "--prefer-other",
        dest="prefer_other",
        action="store_true",
        help="on a runs.json conflict, take the other workspace's record",
    )
    sync.add_argument(
        "--overwrite",
        action="store_true",
        help="on a file conflict, archive main's copy and take the other's",
    )
    # Package B2: both off by default.
    sync.add_argument(
        "--restore",
        action="store_true",
        help="with --apply, rebuild the records of the sims/ folders no record carries",
    )
    sync.add_argument(
        "--include-archives",
        dest="include_archives",
        action="store_true",
        help="also bring the files under folders named archive (skipped by default)",
    )
