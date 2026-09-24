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

import json
from pathlib import Path

import pytest

import pyflightstream
from pyflightstream.results.tables import parse_run_loads
from pyflightstream.versions import resolve
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

HERE = Path(__file__).resolve().parent
#: A point the run finished and judged from its loads table.
TERMINAL_OK = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER)


def source_repository() -> Path:
    """The Git checkout whose history and committed files the licensed checks read.

    The repository this folder sits in, when it sits in one; otherwise the
    checkout the imported package was loaded from, which is the code that
    ran. A copy of this workspace outside Git (the fresh workspace of the
    0.27.0 licensed regression T12) still reaches the committed ``Band
    (T07)`` line, the reports and the command database of the code under
    test, where ``HERE.parents[1]`` named a folder holding none of them.
    """
    candidates = (HERE.parents[1], Path(pyflightstream.__file__).resolve().parents[2])
    for root in candidates:
        if (root / ".git").exists():
            return root
    return candidates[0]


def requested_version(build_id: str, workspace: CampaignWorkspace | None = None) -> str:
    """The version a row naming ``build_id`` in its FS_BUILD cell requests HERE.

    A record's ``fs_version_requested`` is the version the workspace's build
    registry declares for the row's build id, read through
    ``inputs/executables.local.toml`` over ``inputs/executables.toml``
    (PFS-2031.15). On the author's machine the overlay keeps each id's own
    version, so this is the id itself; an overlay that sends the ids to one
    installation (T12 of 0.27.0 sends 26.120, 26.123 and 26.124 to 26.124)
    makes every row request that version, and the check follows the
    registry rather than a literal.
    """
    declared = (workspace or CampaignWorkspace(HERE)).resolve_build(build_id).fs_version
    assert declared, f"the build registry declares no version for {build_id!r}"
    return resolve(declared).canonical


def requested_executable(build_id: str, workspace: CampaignWorkspace | None = None) -> Path:
    """The executable the workspace's build registry sends ``build_id`` to."""
    return Path((workspace or CampaignWorkspace(HERE)).resolve_build(build_id).fs_exe)


class Runs:
    """What one workspace recorded, by matrix and row."""

    def __init__(self, workspace: CampaignWorkspace) -> None:
        self.workspace = workspace
        # A steady row of several points is ONE job record; its points are read
        # as the package reads them (RunRecord.as_points), so a check per point
        # sees every point that ran, with the outputs it collected.
        self.records = [
            point for record in workspace.read_manifest() for point in record.as_points()
        ]

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

    def polar(self, matrix: str, pol: str, group: int) -> Path:
        """The steady polar table of one row and pproc group, as ``products.json`` indexes it.

        Found by the index and the row's run ids rather than by a spelled path:
        the table lives under ``polars/`` since 0.16.0 (FR-88) and is named
        ``P<sim>-<name>_g<NN>.csv`` since 0.21.0 (the point name).
        """
        index = json.loads((self.products(matrix) / "products.json").read_text(encoding="utf-8"))
        run_ids = {record.run_id for record in self.of(matrix, pol)}
        found = [
            key
            for key, entry in index["products"].items()
            if key.startswith(f"polars/P{pol}-")
            and key.endswith(f"_g{group:02d}.csv")
            and run_ids & set(entry.get("runs") or ())
        ]
        assert len(found) == 1, f"{matrix} row {pol} group {group}: {found}"
        return self.products(matrix) / found[0]


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
