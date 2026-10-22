"""Create the optional workbook without launching Excel or changing trust settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream._cli import cli_entrypoint
from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.matrix import MATRIX_COLUMNS
from pyflightstream.extras import missing_extra
from pyflightstream.workspace.excel_sync import ExcelSyncError

__all__ = [
    "create_workbook",
    "main",
    "EXCEL_ACTION",
    "add_excel_actions",
    "run_excel_action",
]


def create_workbook(path: str | Path, *, workspace: str | Path) -> Path:
    """Create a new macro-free .xlsx; synchronize saved files through the CLI.

    Parameters
    ----------
    path : str or Path
        The new ``.xlsx`` file; an existing file is refused.
    workspace : str or Path
        The workspace the workbook synchronizes with.

    Returns
    -------
    Path
        The created workbook, resolved.

    Raises
    ------
    ExcelSyncError
        If the path is not a new ``.xlsx`` file.
    MissingExtraError
        If XlsxWriter, of the ``excel`` extra, is not installed.
    """
    output = Path(path).resolve()
    if output.suffix.lower() != ".xlsx" or output.exists():
        raise ExcelSyncError(
            f"{output}: choose a new .xlsx path; existing files are never overwritten."
        )
    try:
        import xlsxwriter
    except ImportError as exc:
        raise missing_extra("excel", package="XlsxWriter", purpose="Workbook creation") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output, {"strings_to_formulas": False, "strings_to_urls": False})
    try:
        text = workbook.add_format({"num_format": "@"})
        header = workbook.add_format(
            {"bold": True, "bg_color": "#D9EAF7", "num_format": "@", "text_wrap": True}
        )
        wrapped = workbook.add_format({"num_format": "@", "text_wrap": True, "valign": "top"})
        sheets = {}
        for name in ("Controls", "Runs", "Dictionary", "Preview", "_Baseline"):
            sheet = workbook.add_worksheet(name)
            sheet.set_column("A:U", 22, text)
            sheets[name] = sheet
        controls = sheets["Controls"]
        for row, label, value in (
            (1, "pyflightstream matrix workbook", "Explicit Preview / Apply / Cancel"),
            (3, "Workspace", str(Path(workspace).resolve())),
            (7, "Preview direction", "read"),
            (8, "Session directory", ""),
            (9, "Preview state", ""),
            (
                11,
                "Usage",
                "Save and close Excel. Run pyfs-workspace excel preview "
                '"workbook.xlsx" '
                '--workspace "workspace" --direction read --batch "preview.json". '
                "Review the HTML preview, then explicitly apply or cancel.",
            ),
            (
                12,
                "Identity",
                "MATRIX + POL. Rename or reorder Runs headers through Dictionary. "
                "No implicit deletions.",
            ),
            (
                13,
                "Runtime",
                "Python requires pyflightstream. This workbook contains no macros or buttons; "
                "no automatic sync.",
            ),
        ):
            controls.write_string(row - 1, 0, label, header if row == 1 else text)
            controls.write_string(row - 1, 1, value, wrapped)
        controls.set_column("A:A", 42, text)
        controls.set_column("B:B", 100, wrapped)
        for row in range(6, 9):
            controls.set_row(row, None, None, {"hidden": True})
        runs = sheets["Runs"]
        names = ("MATRIX", *MATRIX_COLUMNS)
        for column, name in enumerate(names, start=1):
            runs.write_string(0, column - 1, name, header)
            if name in ("FLIGHT_CONDITION", "VAR_NAMES_VALUES", "SWEEP_VALUES"):
                runs.set_column(column - 1, column - 1, 36, wrapped)
        runs.autofilter(0, 0, 1, len(names) - 1)
        runs.freeze_panes(1, 2)
        dictionary = sheets["Dictionary"]
        for column, name in enumerate(("ASCII_NAME", "EXCEL_HEADER", "STATUS"), start=1):
            dictionary.write_string(0, column - 1, name, header)
        for row, name in enumerate(names, start=2):
            dictionary.write_row(row - 1, 0, (name, name, "MAPPED"), text)
        dictionary.set_column("A:C", 30, text)
        dictionary.autofilter(0, 0, len(names), 2)
        dictionary.freeze_panes(1, 0)
        sheets["_Baseline"].write_row(0, 0, ("KEY", "VALUE"), text)
        sheets["_Baseline"].very_hidden()
        sheets["Preview"].write_row(
            0,
            0,
            ("TYPE", "ACTION", "MATRIX", "POL", "ASCII_NAME", "EXCEL_HEADER", "BEFORE", "AFTER"),
            header,
        )
        sheets["Preview"].freeze_panes(1, 0)
        controls.activate()
        workbook.close()
        return output
    except Exception:
        workbook.close()
        output.unlink(missing_ok=True)
        raise


#: The destination of the action a workbook command names, shared by both entry points.
EXCEL_ACTION = "excel_command"


def add_excel_actions(parser: argparse.ArgumentParser) -> None:
    """Add the workbook actions to ``parser``: create, preview, apply, cancel and check.

    The one definition of the workbook command line, read by
    ``pyfs-workspace excel`` and by ``python -m pyflightstream.workspace.excel``,
    its alias. ``--workspace`` defaults to the current directory, as in every
    other workspace command.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser that receives the actions as its subcommands.
    """
    commands = parser.add_subparsers(dest=EXCEL_ACTION, required=True)
    workspace_help = "Workspace root directory (default: the current directory)"
    create = commands.add_parser("create", help="Create a new macro-free workbook")
    create.add_argument("output", type=Path, help="New .xlsx path; existing files are refused")
    create.add_argument("--workspace", type=Path, default=Path("."), help=workspace_help)
    preview = commands.add_parser("preview", help="Inspect changes without applying them")
    preview.add_argument("workbook", type=Path, help="Saved .xlsx workbook to synchronize")
    preview.add_argument("--workspace", type=Path, default=Path("."), help=workspace_help)
    preview.add_argument(
        "--direction",
        choices=("read", "write"),
        required=True,
        help="read: matrices to workbook; write: workbook to matrices",
    )
    preview.add_argument("--batch", type=Path, required=True, help="New preview batch file path")
    preview.add_argument(
        "--matrix",
        action="append",
        dest="matrices",
        help="Matrix file; repeat to select several; default: all on read, workbook rows on write",
    )
    apply = commands.add_parser("apply", help="Apply one fresh reviewed batch")
    apply.add_argument("batch", type=Path, help="Reviewed preview batch file to apply")
    cancel = commands.add_parser("cancel", help="Cancel a preview without changing inputs")
    cancel.add_argument("batch", type=Path, help="Preview batch file to cancel")
    check = commands.add_parser("check", help="Validate Runs and Dictionary")
    check.add_argument("workbook", type=Path, help="Saved .xlsx workbook to validate")


def run_excel_action(args: argparse.Namespace) -> int:
    """Run the workbook action a parser of :func:`add_excel_actions` read.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line.

    Returns
    -------
    int
        0 on success, 1 when an apply reports a partial write, 2 when the command was not
        completed.
    """
    from pyflightstream.workspace.excel_file import (
        apply_batch,
        cancel_batch,
        check_file,
        preview_file,
    )

    action = getattr(args, EXCEL_ACTION)
    try:
        if action == "create":
            print(create_workbook(args.output, workspace=args.workspace))
        elif action == "preview":
            print(
                preview_file(
                    args.workbook,
                    workspace=args.workspace,
                    direction=args.direction,
                    batch=args.batch,
                    matrices=args.matrices,
                )
            )
        elif action == "apply":
            result = apply_batch(args.batch)
            print(result)
            return 1 if result.get("error") else 0
        elif action == "cancel":
            cancel_batch(args.batch)
            print("Preview cancelled; workbook and matrices unchanged.")
        else:
            check_file(args.workbook)
            print("Runs and Dictionary are valid.")
    except (PyflightstreamError, OSError, ValueError) as error:
        print(f"Excel command not completed: {error}", file=sys.stderr)
        return 2
    return 0


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Create or explicitly synchronize a saved macro-free workbook.

    The module form, kept as the alias of ``pyfs-workspace excel``.

    Parameters
    ----------
    argv : list of str, optional
        The command-line arguments, ``sys.argv[1:]`` by default.

    Returns
    -------
    int
        0 on success, 1 when an apply reports a partial write, 2 when the command was not
        completed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    add_excel_actions(parser)
    return run_excel_action(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
