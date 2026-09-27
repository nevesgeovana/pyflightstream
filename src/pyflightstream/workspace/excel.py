# GEOVERSE_HEADER
# file_version: 2.0.1
# last_modified_at: 2026-09-27T23:24:23.671Z
# last_modified_by: OpenAI / Codex / unknown / architect-correction-proposal
# dependencies: [workspace.excel_sync, workspace.excel_file, XlsxWriter]
# authority: geoverse-goddess-control-plane
# file_role: macro-free-matrix-workbook-factory
# status: active
# confidentiality: public
# change_summary: Use the shared optional dependency refusal for workbook creation.
# revision_source: git
"""Create the optional workbook without launching Excel or changing trust settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream._cli import cli_entrypoint
from pyflightstream.cases.matrix import _COLUMNS
from pyflightstream.extras import missing_extra
from pyflightstream.workspace.excel_sync import ExcelSyncError


def create_workbook(
    path: str | Path, *, workspace: str | Path, python: str | Path = sys.executable
) -> Path:
    """Create a new macro-free .xlsx; synchronize saved files through the CLI."""
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
            (4, "Python executable", str(Path(python).resolve())),
            (5, "Matrices (optional, semicolon separated)", ""),
            (7, "Preview direction", "read"),
            (8, "Session directory", ""),
            (9, "Preview state", ""),
            (
                11,
                "Usage",
                "Save and close Excel. Use the CLI to create a read or write preview. "
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
        names = ("MATRIX", *_COLUMNS)
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


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Create or explicitly synchronize a saved macro-free workbook."""
    from pyflightstream.workspace.excel_file import (
        apply_batch,
        cancel_batch,
        check_file,
        preview_file,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create", help="Create a new macro-free workbook")
    create.add_argument("output", type=Path)
    create.add_argument("--workspace", type=Path, required=True)
    preview = commands.add_parser("preview", help="Inspect changes without applying them")
    preview.add_argument("workbook", type=Path)
    preview.add_argument("--workspace", type=Path, required=True)
    preview.add_argument("--direction", choices=("read", "write"), required=True)
    preview.add_argument("--batch", type=Path, required=True)
    preview.add_argument("--matrix", action="append", dest="matrices")
    apply = commands.add_parser("apply", help="Apply one fresh reviewed batch")
    apply.add_argument("batch", type=Path)
    cancel = commands.add_parser("cancel", help="Cancel a preview without changing inputs")
    cancel.add_argument("batch", type=Path)
    check = commands.add_parser("check", help="Validate Runs and Dictionary")
    check.add_argument("workbook", type=Path)
    args = parser.parse_args(argv)
    if args.action == "create":
        print(create_workbook(args.output, workspace=args.workspace))
    elif args.action == "preview":
        print(
            preview_file(
                args.workbook,
                workspace=args.workspace,
                direction=args.direction,
                batch=args.batch,
                matrices=args.matrices,
            )
        )
    elif args.action == "apply":
        result = apply_batch(args.batch)
        print(result)
        return 1 if result.get("error") else 0
    elif args.action == "cancel":
        cancel_batch(args.batch)
        print("Preview cancelled; workbook and matrices unchanged.")
    else:
        check_file(args.workbook)
        print("Runs and Dictionary are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
