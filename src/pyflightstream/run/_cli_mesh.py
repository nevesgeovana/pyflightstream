"""The panel-mesh verbs of ``pyfs-matrix`` (0.38.0): ``audit-mesh``.

Pipeline role: the command side of the panel-mesh audit of
:mod:`pyflightstream.workspace` (FR-426). Each verb's parser names its
handler as the ``mesh_command`` default, which :mod:`pyflightstream.run.cli`
calls, so the dispatcher imports nothing of this module. The handler reaches
the audit only through :func:`pyflightstream.workspace.audit_mesh` (FR-424
R14), so the command and a Python caller run the same code.

A mesh verb needs no executable, no matrix and no workspace: it reads the OBJ
it is given and writes beside it. Its exit status is the console contract of
FR-426 R1: 0 when every gate and check passes, 1 when one fails (the audit is
still written, and each failure is a warning held to the end of the command),
2 when the input is refused, with the refusal on standard error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.workspace import MeshAudit, audit_mesh

#: The exit status of an audit that passed, of one that failed, of a refusal (FR-426 R1).
EXIT_PASSED, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2

_AUDIT_DESCRIPTION = (
    "Audits an OBJ and writes <stem>.audit.json beside it. The gates G1 to G6 judge the "
    "topology, the orientation, the open boundary, the trailing edge and the nodes families "
    "share; the relative checks compare the 95th percentiles of the skewness, the warp and the "
    "size growth with the source's; the other figures are reported and never judged. Without "
    "--against only G1, G2 and G4 are judged. The trailing-edge points file is the one "
    "<stem>.boundaries.toml names, or else <stem>.te.txt. A gate or check that fails is a "
    "warning, and the audit is still written. Exits 0 when every gate and check passes, 1 when "
    "one fails, 2 when the input is refused. Needs no executable."
)


def add_mesh_parsers(subparsers: Any) -> None:
    """Add the mesh verbs to ``pyfs-matrix``: audit-mesh (FR-426)."""
    audit = subparsers.add_parser(
        "audit-mesh",
        help=(
            "audit a panel mesh's topology, trailing edge and panel quality, alone or against "
            "the source it was made from"
        ),
        description=_AUDIT_DESCRIPTION,
    )
    audit.add_argument("mesh", metavar="OBJ", help="the OBJ to audit")
    audit.add_argument(
        "--against",
        metavar="SOURCE",
        help=(
            "the OBJ the mesh was refined or coarsened from; the gates and checks that compare "
            "with a source are judged against it"
        ),
    )
    audit.add_argument(
        "--csv",
        dest="csv_file",
        metavar="FILE",
        help="also write the figures as CSV, one row per family and figure",
    )
    audit.set_defaults(mesh_command=run_audit_mesh)


def _refused_csv(csv: str | None) -> str | None:
    """Return the refusal of a ``--csv`` file that cannot be written, before anything is.

    A folder that does not exist, or a path that is a folder, is refused
    before the audit runs, so a refusal leaves no audit behind (FR-426 R1).
    """
    if csv is None:
        return None
    target = Path(csv)
    if target.is_dir() or not target.parent.is_dir():
        return (
            f"{target}: --csv names a folder, or a file in a folder that does not exist. "
            "Name a file in an existing folder and run again. Nothing was written."
        )
    return None


def run_audit_mesh(args: argparse.Namespace) -> int:
    """Audit one OBJ, alone or against its source, and write its audit beside it (FR-426).

    The summary goes to standard output, then the audit written and the CSV
    of ``--csv``, one path per line.
    """
    if (refused := _refused_csv(args.csv_file)) is not None:
        print(refused, file=sys.stderr)
        return EXIT_REFUSED
    try:
        audit = audit_mesh(args.mesh, against=args.against)
        written = [audit.path] + _csv(audit, args.csv_file)
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_REFUSED
    for line in audit.summary() + [str(path) for path in written]:
        print(line)
    return EXIT_PASSED if audit.passed else EXIT_FAILED


def _csv(audit: MeshAudit, csv: str | None) -> list[Path]:
    """Write the figures as CSV when ``--csv`` names a file; return what was written."""
    return [] if csv is None else [audit.write_csv(csv)]
