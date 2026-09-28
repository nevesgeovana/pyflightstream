# %% [markdown]
# # Create and synchronize an optional Excel workbook
#
# The workbook has no macros. Edit its saved cells in Excel, save and close it,
# then use the CLI to preview and explicitly apply a read or write transaction.
# The example uses a literal cell edit to exercise the same saved-file boundary.
# Preview never applies changes. Exact originals remain in the workspace recovery
# directory. The public CLI commands are documented in docs/excel-matrices.md.

# %%
"""Demonstrate both directions using an isolated, macro-free workbook."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pyflightstream.cases.matrix import _COLUMNS
from pyflightstream.workspace.excel import main
from pyflightstream.workspace.excel_file import patch_cells, read_snapshot


def demonstrate(folder: Path) -> dict[str, Path]:
    """Create literal sample rows and exercise both explicit CLI transactions."""
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "demonstration.fs"
    values = dict.fromkeys(_COLUMNS, "-")
    values.update(POL="001", RUN="1", DESCRIPTION="Before Excel edit", SWEEP_VALUES="0,2,4")
    source.write_text(
        "# Synthetic synchronization example; not a solver-ready campaign.\n"
        + " | ".join(_COLUMNS)
        + "\n"
        + " | ".join(values[name] for name in _COLUMNS)
        + "\n",
        encoding="utf-8",
    )
    book = folder / "matrices.xlsx"
    main(["create", str(book), "--workspace", str(folder)])
    read = folder / "read-preview.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(folder),
            "--direction",
            "read",
            "--batch",
            str(read),
        ]
    )
    main(["apply", str(read)])
    snapshot = read_snapshot(book)
    assert snapshot.rows[0][snapshot.headers.index("POL")].value == "001"
    patch_cells(
        book, {"Runs": {(2, snapshot.headers.index("DESCRIPTION") + 1): "Saved Excel edit"}}
    )
    write = folder / "write-preview.json"
    main(
        [
            "preview",
            str(book),
            "--workspace",
            str(folder),
            "--direction",
            "write",
            "--batch",
            str(write),
        ]
    )
    assert "Saved Excel edit" not in source.read_text()
    main(["apply", str(write)])
    assert "Saved Excel edit" in source.read_text()
    return {"workbook": book, "preview": write.with_suffix(".html"), "matrix": source}


if __name__ == "__main__":
    with TemporaryDirectory(prefix="pyfs-excel-example-") as temporary:
        demonstrate(Path(temporary))
