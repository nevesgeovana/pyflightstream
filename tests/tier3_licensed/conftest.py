"""Tier 3: this folder IS a campaign workspace, run on a licensed solver.

``matriz.fs`` and its sibling matrices sit at this folder's root beside
``inputs/``; the test modules beside them read what ``pyfs-matrix run``
recorded and assert what came back. Every module carries
``needs_flightstream`` and the default invocation deselects it.

The fixtures here are the one way the modules reach the run: the
manifest, the script the solver received, the loads it exported and the
products the run left, each read through the package's own readers and
never through a path a test guessed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.results.tables import parse_run_loads
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

HERE = Path(__file__).resolve().parent
#: A point the run finished and judged from its loads table.
TERMINAL_OK = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER)


class Runs:
    """What one workspace recorded, by matrix and row."""

    def __init__(self, workspace: CampaignWorkspace) -> None:
        self.workspace = workspace
        self.records = workspace.read_manifest()

    def of(self, matrix: str, pol: str) -> list[RunRecord]:
        """Every record of one row, in manifest order; the latest per point wins."""
        latest: dict[str, RunRecord] = {}
        for record in self.records:
            if record.matrix_stem == matrix and record.sim_id == pol:
                latest[record.run_id] = record
        return list(latest.values())

    def one(self, matrix: str, pol: str, **point: float) -> RunRecord:
        """The one record of a row at a point, for example ``alpha=2.0``."""
        matches = [
            record
            for record in self.of(matrix, pol)
            if all(abs(record.point.get(axis, 1e9) - value) < 1e-9 for axis, value in point.items())
        ]
        assert len(matches) == 1, f"{matrix} row {pol} at {point}: {len(matches)} record(s)"
        return matches[0]

    def script(self, record: RunRecord) -> str:
        """The text the solver received, from the simulation folder."""
        assert record.script_path, f"{record.run_id} records no script"
        path = self.workspace.sim_dir(record.sim_id) / record.script_path
        return path.read_text(encoding="utf-8")

    def loads(self, record: RunRecord):
        """The loads spreadsheet the point exported, parsed and cross-checked."""
        return parse_run_loads(self.workspace, record)

    def total(self, record: RunRecord) -> dict[str, float]:
        return dict(self.loads(record).total)

    def products(self, matrix: str) -> Path:
        return Path(self.workspace.root) / "post" / matrix


@pytest.fixture(scope="session")
def workspace() -> CampaignWorkspace:
    return CampaignWorkspace(HERE)


@pytest.fixture(scope="session")
def runs(workspace) -> Runs:
    return Runs(workspace)


def line(script: str, command: str) -> str:
    """The first line of ``script`` starting with ``command`` followed by a space or end."""
    for text in script.splitlines():
        if text == command or text.startswith(command + " "):
            return text
    raise AssertionError(f"no {command} line in the script")


def lines(script: str, command: str) -> list[str]:
    return [t for t in script.splitlines() if t == command or t.startswith(command + " ")]


def value_after(script: str, command: str) -> str:
    """The line after a command whose argument goes on its own line."""
    texts = script.splitlines()
    for index, text in enumerate(texts):
        if text == command:
            return texts[index + 1]
    raise AssertionError(f"no {command} block in the script")
