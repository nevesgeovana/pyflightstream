# Optional Excel matrix workbook

The optional workbook is an ordinary **.xlsx without macros or buttons**. Python
creates it and synchronizes saved files in both directions. Excel is an editor;
no solver starts, no synchronization happens on open, and no trust setting needs
to change. Install the authoring extra, then create a new file:

~~~console
python -m pip install "pyflightstream[excel]"
python -m pyflightstream.workspace.excel create C:/Work/matrices.xlsx --workspace C:/Work/Campaign
~~~

## Preview, apply or cancel

Save and close the workbook before using the CLI. Unsaved Excel edits are not
visible to a file operation. A read imports matrices into Runs; a write exports
Runs to matrices. Both require an explicit preview followed by Apply:

~~~console
python -m pyflightstream.workspace.excel preview C:/Work/matrices.xlsx --workspace C:/Work/Campaign --direction read --batch C:/Work/read-preview.json
python -m pyflightstream.workspace.excel apply C:/Work/read-preview.json
python -m pyflightstream.workspace.excel check C:/Work/matrices.xlsx
~~~

Open the adjacent **read-preview.html** to inspect every field and action before
Apply. The JSON is the pending transaction; preserve it unchanged. For the
reverse direction, save Excel edits, use **--direction write** and a new batch
path. Add repeated **--matrix batch.fs** options to select a subset explicitly.
Cancel uses **python -m pyflightstream.workspace.excel cancel C:/Work/read-preview.json**.
Preview and Cancel change neither workbook nor matrices. Each batch is single-use.

## Runs and Dictionary

All matrices share **Runs**. **Dictionary** maps exact ASCII names to custom
Excel headers through ASCII_NAME, EXCEL_HEADER and STATUS. Mapped entries
use MAPPED. An Excel-only entry has empty ASCII_NAME and status EXCEL ONLY;
unmapped custom columns are also preserved and identified in the preview.
Reorder columns freely, and update Dictionary when renaming mapped headers.

MATRIX is a filename, and **MATRIX + POL** identifies each row. Duplicate or blank
headers, duplicate identities, unsupported keys and ambiguous mappings are
refused. Use text cells for identifiers: 001 remains 001; formatting an
already numeric 1 cannot recover lost zeros. Formula cells in mapped fields are
refused; custom formulas retain their original XML and cached values. Sweeps
remain in one cell. Python does not calculate formulas.

Matrices may live at the workspace root or in inputs/matrices. Existing files
keep their location; new files use inputs/matrices. A duplicate filename across
both locations is ambiguous. Recognized historical schemas retain their own
columns and order. New supported fields append proposed mappings and columns;
collisions with custom headers are refused. Identity changes add rows and never
silently delete old rows. Unrelated comments and line endings remain intact.

## Preservation and recovery

Preview shows ADD, UPDATE, UNCHANGED, CONFLICT, INVALID and EXCEL ONLY actions. A
hidden baseline records shared values. Different edits on both sides have no
automatic winner. Without a baseline, competing nonempty values are also a
conflict. Resolve the conflict and create a new preview.

Apply verifies the complete workbook hash and every selected matrix hash. Any
saved workbook change after Preview, including an unrelated sheet edit, makes
the batch stale. The adapter replaces selected cell XML only and copies all
unrelated ZIP members unchanged, including drawing/shape parts, relationships,
styles and custom-sheet content. It preserves existing column order and custom
formulas. Unsupported prefixed worksheet XML is refused instead of rewritten.

Before replacement, exact originals are retained under
**.excel-sync-recovery/&lt;batch-token&gt;/**. Each file replacement is atomic; a
multi-file batch is not a filesystem-wide transaction. Partial failures report
completed files and recovery paths. If Excel holds a write lock, close it and
use the reported original/recovery state to create a new preview. Never reuse a
partially applied batch. Reopen the workbook after Apply to view its saved state.

The earlier embedded VBA experiment is not part of this release's workbook
workflow. Existing .xlsm files are not silently converted; create a new .xlsx and
review any data transfer explicitly.
