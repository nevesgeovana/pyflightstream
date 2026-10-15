"""The third stage of `pyfs-matrix upgrade`: the 0.11.0 layout and the pproc library.

PFS-2029.04, PFS-2029.07.01 and PFS-2029.07.02. The committed samples are the
same eight rows at three layouts, so every stage is measured against a file a
reader can diff: v0.9.0 (fifteen columns, ENTRY and FS_SCRIPT), v0.11.0
(fourteen, PPROC) and the current one (thirteen, no SWEEP_TYPE). The stage
this module is about is the third; the fourth has its own case in
`test_matrix.py`, and what is measured here is that a file at ANY of the
older layouts lands on the current one.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
LAYOUT_0_9_0 = FIXTURES / "pfs202609_matrix15.fs"
LAYOUT_0_11_0 = FIXTURES / "pfs202609_matrix14.fs"
#: The author's 0.10.1 reference workspace, outside this repository; the
#: same conversion is measured on it when the estate is present.
PFS0101 = (
    Path(__file__).resolve().parents[3] / "GeoverseResearch/tools/fts_workspace/pfs0101/matriz.fs"
)
