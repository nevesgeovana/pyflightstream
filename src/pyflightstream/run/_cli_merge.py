"""The ``pyfs-workspace geometry merge`` verb: two trimmed OBJ joined along a cut (FR-3480).

Pipeline role: the run row's command line over the workspace layer's
:func:`pyflightstream.workspace.merge_objs`, registered by the geometry group.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from pyflightstream._errors import PyflightstreamError


def add_merge_parser(verbs: Any) -> None:
    """Add ``geometry merge`` to the group's verbs."""
    merge = verbs.add_parser(
        "merge",
        help="join two trimmed OBJ along their open boundaries within a threshold",
        description=(
            "Joins two trimmed OBJ along the open boundaries that lie within --threshold of "
            "each other. The part --adapt names takes the other's nodes along that interface; "
            "the other part is kept unchanged. Writes the OBJ, <out stem>.merge.json, its audit "
            "and its inventory. The boundary declarations of the two sources are not merged. "
            "A threshold that finds no interface warns, writes nothing and exits non-zero "
            "(docs/geometry.md)."
        ),
    )
    merge.add_argument("parts", nargs=2, metavar="OBJ", help="the two trimmed parts")
    merge.add_argument(
        "--threshold",
        type=float,
        required=True,
        metavar="LENGTH",
        help="the largest distance across the interface, in the OBJ's own length unit",
    )
    merge.add_argument(
        "--adapt",
        required=True,
        metavar="OBJ",
        help="which of the two parts is adapted; the other keeps its nodes and faces",
    )
    merge.add_argument("--out", required=True, metavar="OBJ", help="the merged OBJ to write")
    merge.add_argument("--overwrite", action="store_true", help="replace an existing output")


def run_merge(args: argparse.Namespace) -> int:
    """Merge the two parts and print what was written; return the exit code."""
    from pyflightstream.workspace import merge_objs

    first, second = args.parts
    try:
        merged = merge_objs(
            first,
            second,
            threshold=args.threshold,
            adapt=args.adapt,
            out=args.out,
            overwrite=args.overwrite,
            say=print,
        )
    except (PyflightstreamError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if merged.obj is None:
        return 1
    print(
        f"interface edges {merged.interface_edges}, nodes moved {merged.moved_nodes}, band faces "
        f"{merged.band_faces}, triangles created {merged.triangles_created}, open edges left "
        f"{merged.open_edges_left} ({merged.facing_edges_left} facing the other part)"
    )
    for path in (merged.obj, merged.record, merged.boundaries):
        print(path)
    if merged.audit is not None:
        print(merged.audit.path)
    return 0
