"""The geometry verbs: ``refine``, ``audit-mesh``, ``inventory`` and ``degenerate``.

Since 0.40.0 (FR-477) they are also the verbs of ``pyfs-workspace geometry``
(:mod:`pyflightstream.run._cli_geometry`), which copies these parsers and calls
these handlers; ``inventory`` and ``degenerate`` moved here from
:mod:`pyflightstream.run.cli` and :mod:`pyflightstream.run._cli_parsers` so that
both commands reach them without importing the ``pyfs-matrix`` dispatcher.

Pipeline role: the command side of the panel-mesh audit of
:mod:`pyflightstream.workspace` (FR-426). Each verb's parser names its
handler as the ``mesh_command`` default, which :mod:`pyflightstream.run.cli`
calls, so the dispatcher imports nothing of this module. The handler reaches
the audit only through :func:`pyflightstream.workspace.audit_mesh` (FR-424
FR-928), so the command and a Python caller run the same code.

The geometry verbs ``inventory`` and ``degenerate`` (FR-308, FR-312, FR-330) name
their handlers the same way; :func:`cmd_geometry` is the one entry the dispatcher
calls for any command of :data:`GEOMETRY_COMMANDS`.

A mesh verb needs no executable, no matrix and no workspace: it reads the OBJ
it is given and writes beside it. Its exit status is the console contract of
FR-937: 0 when every gate and check passes, 1 when one fails (the audit is
still written, and each failure is a warning held to the end of the command),
2 when the input is refused, with the refusal on standard error. ``audit-mesh``
also exits 2 when the CSV of ``--out`` cannot be written after the audit was:
the error on standard error names the audit file that was written.

The written file is named by ``--out`` on both verbs, as on their sibling
commands (``rebuild --out``, ``pyfs-workspace ... --out``): ``refine --out
DIR`` and ``audit-mesh --out FILE``. The former names ``--out-dir`` and
``--csv`` are kept as deprecated aliases (NFR-45): each gives the identical
result and warns once that it is deprecated.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases.workflows._vocabulary import RAW_MESH_FORMATS
from pyflightstream.workspace import MeshAudit, audit_mesh, derive_thin_blade, refine_mesh

#: The exit status of an audit that passed, of one that failed, of a refusal (FR-937).
EXIT_PASSED, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2

_AUDIT_DESCRIPTION = (
    "Audits an OBJ and writes <stem>.audit.json beside it. The gates G1 to G6 judge the "
    "topology, the orientation, the open boundary, the trailing edge and the nodes families "
    "share; the relative checks compare the 95th percentiles of the skewness, the warp and the "
    "size growth with the source's; the other figures are reported and never judged. Without "
    "--against only G1, G2 and G4 are judged. The trailing-edge points file is the one "
    "<stem>.boundaries.toml names, or else <stem>.te.txt. A gate or check that fails is a "
    "warning, and the audit is still written. Exits 0 when every gate and check passes, 1 when "
    "one fails, 2 when the input is refused or when the --out CSV cannot be written after the "
    "audit was (the error names the audit written). Needs no executable."
)


def add_mesh_parsers(subparsers: Any) -> None:
    """Add the mesh verbs to ``pyfs-matrix``: refine (FR-424) and audit-mesh (FR-426)."""
    _add_refine_parser(subparsers)
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
        "--out",
        metavar="FILE",
        help=(
            "write the figures as CSV, one row per family and figure; "
            "the audit JSON is always written beside the OBJ"
        ),
    )
    audit.add_argument(
        "--csv",
        dest="csv_file",
        metavar="FILE",
        help="deprecated alias of --out, with the identical result",
    )
    audit.set_defaults(mesh_command=run_audit_mesh)


def _chosen(
    args: argparse.Namespace, new: tuple[str, str], old: tuple[str, str], *, since: str = "0.39.0"
) -> tuple[str | None, str, str | None]:
    """Return an option's value, the flag that gave it, and a refusal (NFR-45).

    ``new`` and ``old`` are each ``(flag, dest)``: the option's name and its
    deprecated alias. The alias gives the identical value and warns once
    that it is deprecated; both together are refused, naming both.
    ``since`` is the release that deprecated the alias.
    """
    value, alias = getattr(args, new[1]), getattr(args, old[1])
    if alias is None:
        return value, new[0], None
    if value is not None:
        return (
            None,
            new[0],
            f"{old[0]} {alias} and {new[0]} {value}: {old[0]} is a deprecated alias of "
            f"{new[0]}. Give {new[0]} alone and run again. Nothing was written.",
        )
    warn(
        f"{old[0]} is deprecated since {since} and will be removed; it is an alias of "
        f"{new[0]}, which gives the identical result: write {new[0]} {alias}.",
        PyflightstreamWarning,
        stacklevel=2,
    )
    return alias, old[0], None


def _refused_csv(csv: str | None, flag: str = "--out") -> str | None:
    """Return the refusal of a CSV file (``--out``) that cannot be written, before anything is.

    A folder that does not exist, a path that is a folder, and a file that
    cannot be opened for writing are refused before the audit runs, so a
    refusal leaves no audit behind (FR-937). The file is opened for
    appending, which changes nothing in it, and removed again when the probe
    created it.
    """
    if csv is None:
        return None
    target = Path(csv)
    if target.is_dir() or not target.parent.is_dir():
        return (
            f"{target}: {flag} names a folder, or a file in a folder that does not exist. "
            "Name a file in an existing folder and run again. Nothing was written."
        )
    existed = target.exists()
    try:
        _textio.append_text(target, "")
    except OSError as error:
        return (
            f"{target}: {flag} names a file that cannot be written ({_reason(error)}). "
            "Close it or make it writable, or name another file, and run again. "
            "Nothing was written."
        )
    if not existed:
        target.unlink(missing_ok=True)
    return None


def _same_file(a: Path, b: Path) -> bool:
    """Return whether two paths name one file: one spelling, or one file on disk."""
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
        return os.path.normcase(a.resolve()) == os.path.normcase(b.resolve())
    except OSError:
        return False


def _read_by_the_audit(obj: str | None) -> list[tuple[str, Path]]:
    """Return the files the audit of ``obj`` reads, each with what it is.

    The audit's own list (:meth:`MeshAudit.files_read`), which reads the
    boundaries file through the refinement's one reader of it.
    """
    return [] if obj is None else MeshAudit.files_read(obj)


def _csv_collision(
    csv: str | None, mesh: str, against: str | None, flag: str = "--out"
) -> str | None:
    """Return the refusal of a CSV file (``--out``) the command reads or writes, before any is.

    The CSV must not be the audited OBJ, the source of ``--against``, a
    boundaries or trailing-edge points file either is read with, the OBJ's
    ``<stem>.refine.json`` (its refinement record, which the audit reads), or
    the audit JSON written beside the OBJ (FR-937), under any spelling.
    """
    if csv is None:
        return None
    target = Path(csv)
    audit = Path(mesh).with_name(f"{Path(mesh).stem}.audit.json")
    record = Path(mesh).with_name(f"{Path(mesh).stem}.refine.json")
    taken = [(f"mesh {what}", path) for what, path in _read_by_the_audit(mesh)]
    taken.append(("mesh its refinement record", record))
    taken += [(f"--against source {what}", path) for what, path in _read_by_the_audit(against)]
    taken.append(("the audit JSON the command writes", audit))
    for what, path in taken:
        if _same_file(target, path):
            return (
                f"{target}: {flag} names {what}, {path}, which audit-mesh reads or writes. "
                "Name another file and run again. Nothing was written."
            )
    return None


def _reason(error: OSError) -> str:
    """Return what the system said of a failed file operation, without the path it repeats."""
    return str(error.strerror or error)


def run_audit_mesh(args: argparse.Namespace) -> int:
    """Audit one OBJ, alone or against its source, and write its audit beside it (FR-426).

    The summary goes to standard output, then the audit written and the CSV
    of ``--out`` (or its deprecated alias ``--csv``), one path per line.
    Every refusal, an error of the file system included, is printed in the
    standard shape (the object, the reason, what to do), ending "Nothing was
    written." only when that holds.
    """
    csv_file, flag, refused = _chosen(args, ("--out", "out"), ("--csv", "csv_file"))
    if refused is None:
        refused = _csv_collision(csv_file, args.mesh, args.against, flag)
    if refused is None:
        refused = _refused_csv(csv_file, flag)
    if refused is not None:
        print(refused, file=sys.stderr)
        return EXIT_REFUSED
    try:
        audit = audit_mesh(args.mesh, against=args.against)
    except PyflightstreamError as error:
        print(str(error), file=sys.stderr)
        return EXIT_REFUSED
    except OSError as error:
        print(
            f"{error.filename or args.mesh}: the audit could not read or write it "
            f"({_reason(error)}). Make it readable, and its folder writable, and run again.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    try:
        written = [audit.path] + _csv(audit, csv_file)
    except OSError as error:
        print(
            f"{csv_file}: the CSV could not be written ({_reason(error)}). Close it or "
            f"name another file and run again. The audit {audit.path} was written.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    for line in audit.summary() + [str(path) for path in written]:
        print(line)
    return EXIT_PASSED if audit.passed else EXIT_FAILED


def _csv(audit: MeshAudit, csv: str | None) -> list[Path]:
    """Write the figures as CSV when ``--out`` names a file; return what was written."""
    return [] if csv is None else [audit.write_csv(csv)]


_REFINE_DESCRIPTION = (
    "Refines or coarsens a panel mesh from its OBJ into a new geometry folder "
    "<out>/<stem>_<tag>/ holding the OBJ, the trailing-edge points file, the boundaries "
    "file, <stem>_<tag>.refine.json and the audit against the source. FACTOR multiplies the "
    "intervals of each index direction of a grid family and divides the target edge length of "
    "a remeshed family; --chordwise and --spanwise replace it in one direction of the grid "
    "families. Without FACTOR, --chordwise or --spanwise, the factors come from the refinement "
    "file (--config, or <stem>.refine.toml beside the mesh), whose [components], [periodic], "
    "[refine] tag and elements (triangles or quad-dominant) are read whenever it exists. "
    "--keep-first-row names grid families with a trailing edge whose row of panels at each end "
    "meeting another component keeps its spanwise width and is refined chordwise only. "
    "Faces are written in the source's order. The "
    "source and its folder are never modified. Remeshing a family needs the geom extra. Needs "
    "no executable. Exits 0 when the level is written, even when its audit fails: each failed "
    "gate or check is a warning and the audit is written beside the level, while audit-mesh "
    "exits 1 on the same audit. Exits 2 when the request is refused, and then writes nothing."
)


def _number(text: str) -> float | str:
    """Return a factor as typed: a float when it reads as one, else the text.

    The refusal of a text that is not a number is the function's own, so the
    command and :func:`refine_mesh` refuse it with the same words (FR-424).
    """
    try:
        return float(text)
    except ValueError:
        return text


def _add_refine_parser(subparsers: Any) -> None:
    """Add ``pyfs-matrix refine`` (FR-424)."""
    refine = subparsers.add_parser(
        "refine",
        help="refine or coarsen a panel mesh from its OBJ into a new geometry folder",
        description=_REFINE_DESCRIPTION,
    )
    refine.add_argument("mesh", metavar="MESH", help="the source OBJ")
    refine.add_argument(
        "factor",
        metavar="FACTOR",
        nargs="?",
        type=_number,
        help="the factor of every selected family",
    )
    refine.add_argument("--families", help="the families to change, comma separated (default: all)")
    refine.add_argument(
        "--chordwise", type=_number, help="the chordwise factor of the grid families"
    )
    refine.add_argument("--spanwise", type=_number, help="the spanwise factor of the grid families")
    refine.add_argument(
        "--config", metavar="FILE", help="the refinement file (default: <stem>.refine.toml)"
    )
    refine.add_argument(
        "--keep-first-row",
        metavar="FAMILY[,FAMILY...]",
        help=(
            "grid families with a trailing edge that keep the spanwise width of their row of "
            "panels at another component, comma separated"
        ),
    )
    refine.add_argument(
        "--out",
        metavar="DIR",
        help="where the level folder goes (Python: out_dir; "
        "default: the parent of the source's folder)",
    )
    refine.add_argument(
        "--out-dir",
        metavar="DIR",
        help="deprecated alias of --out, with the identical result",
    )
    refine.add_argument("--overwrite", action="store_true", help="replace an existing level folder")
    refine.set_defaults(mesh_command=run_refine)


def run_refine(args: argparse.Namespace) -> int:
    """Refine one OBJ into a level folder and print what was written (FR-424).

    Exit 0 when the level is written (a failed audit is a warning), 2 when the
    request is refused; a refusal writes nothing.
    """
    out_dir, _, refused = _chosen(args, ("--out", "out"), ("--out-dir", "out_dir"))
    if refused is not None:
        print(refused, file=sys.stderr)
        return EXIT_REFUSED
    try:
        level = refine_mesh(
            args.mesh,
            args.factor,
            families=_names(args.families),
            chordwise=args.chordwise,
            spanwise=args.spanwise,
            config=args.config,
            out_dir=out_dir,
            overwrite=args.overwrite,
            keep_first_row=_names(args.keep_first_row),
        )
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_REFUSED
    for name, entry in level.report.items():
        print(f"{name}: {entry.get('method', 'copied')}")
    summary = [] if level.audit is None else level.audit.summary()
    for line in summary + [str(path) for path in level.files]:
        print(line)
    return EXIT_PASSED


def _names(text: str | None) -> list[str] | None:
    """Return the family names of a comma separated option, as ``--families`` takes them."""
    return None if text is None else [n.strip() for n in text.split(",") if n.strip()]


def add_inventory_parser(subparsers: Any) -> None:
    """Add ``inventory``: the boundary inventory of a saved simulation or an OBJ."""
    inventory = subparsers.add_parser(
        "inventory",
        help=(
            "write <stem>.boundaries.toml beside a saved simulation, from its mesh block, "
            "or beside an OBJ, from its groups"
        ),
        description=(
            "Reads the mesh block of a saved simulation and writes its boundary order as "
            "a sidecar beside it; a run whose sidecar disagrees with the file is refused "
            "before the solver starts. Needs no executable (PFS-2029.06.02). For an OBJ "
            "the order is its groups that hold a face, in the order of the file, which is "
            "what a plan writes when the OBJ has no sidecar (G30, RPT-078); an OBJ's "
            "existing sidecar is never rewritten."
        ),
    )
    inventory.add_argument("geometry", help="a saved simulation or an OBJ under inputs/geometries/")
    inventory.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "rewrite a saved simulation's sidecar that already exists; without it an "
            "existing one is refused"
        ),
    )
    inventory.add_argument(
        "--clean",
        action="store_true",
        help=(
            "remove the unsteady solver actions saved in the simulation, which inventory "
            "otherwise names as a warning, keeping a copy <file>.bak-<stamp> beside it; an "
            "existing sidecar is then kept unless --overwrite (FR-308)"
        ),
    )

    inventory.set_defaults(mesh_command=run_inventory)


def add_degenerate_parser(subparsers: Any) -> None:
    """Add ``degenerate``: the thin blade of a blade mesh (FR-330)."""
    degenerate = subparsers.add_parser(
        "degenerate",
        help=(
            "derive a degenerate geometry, the thin blade first, from a blade mesh and write "
            "it beside the source"
        ),
        description=(
            "Derives the thin blade of a blade mesh, the sheet midway between its two sides "
            "from the root to the tip, with the root moved outward along the span by "
            "--root-offset so it does not cross the spinner, and writes it beside the source "
            "as <stem>_thin_blade.obj with its boundary inventory "
            "<stem>_thin_blade.boundaries.toml. The root is the end of the blade nearer the "
            "origin of the mesh's own coordinates. The source is read only; a file holding "
            "more than one boundary needs --boundary. The derived geometry is a modelling "
            "choice: a run confirms what the solver makes of it. Needs no executable."
        ),
    )
    degenerate.add_argument("geometry", help="a blade mesh: a saved simulation or an OBJ")
    degenerate.add_argument(
        "--kind",
        choices=["thin-blade"],
        default="thin-blade",
        help="the degenerate geometry to derive; thin-blade is the one kind of 0.34.0 "
        "(default: %(default)s)",
    )
    degenerate.add_argument(
        "--root-offset",
        type=float,
        required=True,
        metavar="LENGTH",
        help="how far the root of the thin blade is moved outward along the span, a positive "
        "length in the mesh's own unit, shorter than the blade",
    )
    degenerate.add_argument(
        "--boundary",
        metavar="NAME",
        help=(
            "the boundary (an OBJ's group) that is the blade, for a file that also holds a "
            "spinner, a nacelle or other bodies; only its faces are read and the output is "
            "named <stem>_<NAME>_thin_blade; without it a file holding more than one "
            "boundary is refused"
        ),
    )
    degenerate.add_argument(
        "--overwrite",
        action="store_true",
        help="rewrite a thin blade and its inventory that already exist; without it an "
        "existing one is refused",
    )

    degenerate.set_defaults(mesh_command=run_degenerate)


def run_inventory(args: argparse.Namespace) -> int:
    """Write the boundary inventory sidecar of one saved simulation.

    A saved simulation that carries unsteady solver actions is named on
    standard error with each action and the ``--clean`` command, on every
    call (FR-308); ``--clean`` reduces the file to its meshes and boundary
    conditions first (FR-308, FR-312), and then an existing sidecar is kept,
    since the boundaries it lists did not change.
    """
    from datetime import UTC, datetime

    from pyflightstream.workspace._geometry_clean import saved_action_warning
    from pyflightstream.workspace.inputs import (
        OBJ_SUFFIX,
        clean_saved_actions,
        inventory_sidecar,
        write_inventory,
    )

    geometry = Path(args.geometry)
    # A RAW MESH IS EVERY FORMAT RAW_MESH_FORMATS NAMES, the STL as well as
    # the OBJ (PFS-2094.036): an STL read as a saved simulation was warned
    # about, or cleaned, before write_inventory refused it. Its refusal now
    # comes first, and --clean on an OBJ is refused rather than ignored.
    raw = geometry.suffix.lower() in RAW_MESH_FORMATS
    if raw and args.clean and geometry.suffix.lower() == OBJ_SUFFIX:
        print(
            f"--clean reduces a saved simulation to its meshes and boundary conditions; "
            f"{geometry.name} is a raw mesh, which carries no saved solver action. "
            "Drop --clean to write its inventory.",
            file=sys.stderr,
        )
        return 2
    saved = geometry.is_file() and not raw
    if saved and args.clean:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        try:
            cleaned = clean_saved_actions(geometry, stamp=stamp)
        except (OSError, PyflightstreamError) as error:
            print(str(error), file=sys.stderr)
            return 2
        said = [f"removed saved action {n} [{k}] {c}" for n, c, k in cleaned.actions]
        said += [f"reset block {name} to its fresh-import content" for name in cleaned.blocks_reset]
        said += [cleaned.note] if cleaned.note else []
        said += [
            f"the file as it was is {cleaned.backup.name}"
            if cleaned.backup is not None
            else f"{geometry.name} carries no saved unsteady solver action"
            + ("" if cleaned.note else ", and each measured block holds its fresh-import content")
        ]
        for line in said:
            print(line, file=sys.stderr)
        if inventory_sidecar(geometry).exists() and not args.overwrite:
            print(inventory_sidecar(geometry))
            return 0
    elif saved and (warning := saved_action_warning(geometry, args.geometry)) is not None:
        print(f"warning: {warning}", file=sys.stderr)
    try:
        sidecar = write_inventory(args.geometry, overwrite=args.overwrite)
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(sidecar)
    return 0


#: The commands that act on one geometry file: `inventory` and `degenerate` (FR-330),
#: and `audit-mesh` (0.38.0, FR-426), whose parser names its handler in ``mesh_command``.
GEOMETRY_COMMANDS = ("inventory", "degenerate", "audit-mesh", "refine")


def cmd_geometry(args: argparse.Namespace) -> int:
    """Run the geometry command ``args`` names."""
    # Every geometry verb's parser names its handler, shared with
    # `pyfs-workspace geometry` (FR-477).
    return int(args.mesh_command(args))


def run_degenerate(args: argparse.Namespace) -> int:
    """Derive the degenerate geometry of one blade mesh and write it beside it (FR-330).

    The OBJ and its boundary inventory are named on standard output, one per
    line; the offset used and a unit the source does not state are said on
    standard error. A refusal names the file and the reason on standard error
    and writes nothing.
    """
    try:
        made = derive_thin_blade(
            args.geometry,
            root_offset=args.root_offset,
            overwrite=args.overwrite,
            boundary=args.boundary,
        )
    except (OSError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(made.mesh)
    print(made.sidecar)
    unit = made.unit or "a length unit the source does not state"
    print(f"the root moved outward by {made.root_offset!r} in {unit}", file=sys.stderr)
    return 0
