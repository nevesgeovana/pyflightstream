"""A sync client holding the empty inputs folder costs a link, never the run.

THE DEFECT, met on a licensed campaign whose workspace sits under a synced folder.
Staging makes `sims/sim_<id>/inputs` a LINK to the geometry library, and to do that
it first removes the empty folder `create_sim` made. A sync client that has just
seen the folder appear holds it for a moment, and the removal is refused with
"access denied". The fallback that already covers a refused LINK, copy the file and
say why, did not cover the refused REMOVAL one line above it, so the whole matrix
stopped before any solver started: `matrix not run: [WinError 5] ...inputs`.

The requirement is the method's own: make the folder a link, "or say why not".
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_workspace import _library_geometry  # noqa: E402

from pyflightstream._digest import file_sha256  # noqa: E402
from pyflightstream.workspace import CampaignWorkspace, _is_link  # noqa: E402


def test_an_inputs_folder_that_cannot_be_removed_is_staged_by_copy_with_the_reason(
    tmp_path, monkeypatch
):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    library = _library_geometry(workspace)
    real_rmdir = Path.rmdir

    def held(self: Path) -> None:
        if self.name == "inputs":
            raise PermissionError(5, "Acesso negado", str(self))
        real_rmdir(self)

    monkeypatch.setattr(Path, "rmdir", held)
    hashes = workspace.stage_inputs("9001", [library])
    inputs = workspace.sim_dir("9001") / "inputs"
    assert inputs.is_dir() and not _is_link(inputs)
    assert (inputs / "wing.fsm").read_bytes() == library.read_bytes()
    assert hashes == {"wing.fsm": file_sha256(library)}
    mode, reason = workspace.staged_as("9001")
    assert mode == "copy" and "Acesso negado" in reason, (mode, reason)
