"""The external structural program and the archiving step that calls it (FR-462).

An FSI input with ``mode = "external"`` names a structural program of the
user's own. The solver does not call it directly: its aeroelastic execution
command calls ``pyfs-fsi external`` in the point folder at every coupling
iteration, and :func:`external_step` runs the program, then archives and
validates the call (FR-1092).

THE EXCHANGE IS THE PACKAGE BEAM'S (FR-1091): the solver writes the section
loads file :data:`~pyflightstream.fsi.state.LOADS_FILE` in the point folder,
and the program writes :data:`~pyflightstream.fsi.state.DISPLACEMENT_FILE`, one
comma-separated ``dx,dy,dz`` translation in metres per structural node, in the
order of the node file, which is the user's (one ``x,y,z`` row per node, in
metres, the grammar :func:`~pyflightstream.fsi.nodes.write_node_file` writes).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

import pyflightstream._textio as _textio
from pyflightstream._digest import one_file_key
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.nodes import read_fsidisp
from pyflightstream.fsi.state import DISPLACEMENT_FILE, LOADS_FILE

__all__ = [
    "ARCHIVE_RECORD",
    "EXTERNAL_CALLS_LOG",
    "EXTERNAL_MANIFEST",
    "EXTERNAL_NODES_FILE",
    "STEP_NAMES",
    "ExternalStructure",
    "count_structural_nodes",
    "external_step",
    "step_name_collisions",
]

#: The manifest the plan stages in each point folder: what the step runs and checks.
EXTERNAL_MANIFEST = "fsi_external.json"
#: One row per call, appended by the step (FR-1092).
EXTERNAL_CALLS_LOG = "fsi_external_calls.csv"
#: The user's node file, as the point folder holds it.
EXTERNAL_NODES_FILE = "fsi_external_nodes.csv"
#: The record of one call, written by the step into the call's archive folder.
ARCHIVE_RECORD = "call.json"
_ARCHIVE_DIR = "fsi_archive"
_ERROR_LOG = "pyfs_fsi_error.log"
_STDOUT = "fsi_external_stdout.txt"
#: Every name the step reads or writes in the point folder or in a call's archive
#: (FR-1092, FR-1093). A declared input or output under one of them, compared without
#: case as the file system does, would be overwritten by the step or overwrite
#: its file while the call reports success, so it is refused at reading, at plan
#: and by the step itself before the program runs.
STEP_NAMES = frozenset(
    {
        EXTERNAL_MANIFEST,
        EXTERNAL_CALLS_LOG,
        EXTERNAL_NODES_FILE,
        ARCHIVE_RECORD,
        _ARCHIVE_DIR,
        _ERROR_LOG,
        _STDOUT,
        LOADS_FILE,
        DISPLACEMENT_FILE,
    }
)
_LOG_COLUMNS = (
    "call",
    "started",
    "return_code",
    "wall_time_s",
    "node_count",
    "rows_written",
    "verdict",
    "reason",
)


class ExternalStructure(BaseModel):
    """A resolved external structural program, as the plan hashed it (FR-1090, FR-1095).

    Attributes
    ----------
    source : str
        The FSI input file.
    source_sha256 : str
        Its digest.
    executable : str
        The program's absolute path, under the workspace's ``inputs/fsi/``.
    executable_sha256 : str
        Its digest, verified before every call.
    arguments : list of str
        The arguments the step passes the program, after its path.
    structural_nodes : str
        The node file's absolute path.
    structural_nodes_sha256 : str
        Its digest.
    node_count : int
        The number of nodes, so of rows the displacement file must hold.
    inputs : dict of str to str
        The files the program reads, by the name it reads them under in the point
        folder, each to its absolute source path.
    inputs_sha256 : dict of str to str
        Their digests, verified in the point folder before every call.
    outputs : list of str
        The files the program writes per call, archived with each call.
    timeout_s : float
        The longest one call may run.
    families : list of str
        The coupled family, one.
    max_iterations : int or None
        The cap on a steady row's coupling iterations; None takes the package's.
    convergence_threshold : float or None
        The displacement residual the solver stops at; None leaves the solver's.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    source: str
    source_sha256: str
    executable: str
    executable_sha256: str
    arguments: list[str] = Field(default_factory=list)
    structural_nodes: str
    structural_nodes_sha256: str
    node_count: int = Field(ge=1)
    inputs: dict[str, str] = Field(default_factory=dict)
    inputs_sha256: dict[str, str] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    timeout_s: float = Field(default=3600.0, gt=0.0)
    families: list[str] = Field(min_length=1, max_length=1)
    max_iterations: int | None = Field(default=None, ge=1)
    convergence_threshold: float | None = Field(default=None, gt=0.0)

    def provenance(self) -> dict[str, object]:
        """Return the record's ``fsi-provenance.json`` content (FR-1095)."""
        return {
            "mode": "external",
            "route": "B: SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND -> pyfs-fsi external",
            "source": self.source,
            "source_sha256": self.source_sha256,
            "executable": self.executable,
            "executable_sha256": self.executable_sha256,
            "structural_nodes": self.structural_nodes,
            "structural_nodes_sha256": self.structural_nodes_sha256,
            "node_count": self.node_count,
            "inputs_sha256": dict(self.inputs_sha256),
            "outputs": list(self.outputs),
            "arguments": list(self.arguments),
        }


def step_name_collisions(names: Iterable[str]) -> list[str]:
    """Return names identifying a file of :data:`STEP_NAMES` (FR-1093).

    Use the staged-file identity rule, including Windows trailing dots and
    spaces, so an alias cannot overwrite the archive record (REL9-001).

    Parameters
    ----------
    names : iterable of str
        Declared input or output file names.

    Returns
    -------
    list of str
        The colliding names, as declared, in their order.
    """
    owned = {one_file_key(name) for name in STEP_NAMES}
    return [name for name in names if one_file_key(name) in owned]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_structural_nodes(path: str | Path) -> int:
    """Count the nodes of a node file: one ``x,y,z`` row each, finite (FR-1091).

    Parameters
    ----------
    path : str or Path
        The node file.

    Returns
    -------
    int
        The number of nodes.

    Raises
    ------
    FsiInputError
        A row that is not three numbers, a value that is not finite, or no node at all.
    """
    rows = read_fsidisp(path)
    if len(rows) == 0:
        raise FsiInputError(f"{path}: the structural node file holds no node")
    if not all(math.isfinite(float(value)) for value in rows.ravel()):
        raise FsiInputError(f"{path}: a structural node coordinate is not finite")
    return len(rows)


def _next_call(directory: Path) -> int:
    archive = directory / _ARCHIVE_DIR
    taken = [
        int(child.name.removeprefix("call_"))
        for child in archive.glob("call_*")
        if child.name.removeprefix("call_").isdigit()
    ]
    return max(taken, default=0) + 1


def _append_log(directory: Path, row: dict[str, object]) -> None:
    path = directory / EXTERNAL_CALLS_LOG
    new = not path.is_file()
    with _textio.open_text(path, "a") as handle:
        writer = _textio.csv_dict_writer(handle, _LOG_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in _LOG_COLUMNS})


def _verify_digests(directory: Path, structure: ExternalStructure) -> str | None:
    """Return why a digest differs from the plan's, or None."""
    nodes = directory / EXTERNAL_NODES_FILE
    if not nodes.is_file():
        return f"the structural node file {EXTERNAL_NODES_FILE} is missing"
    if _sha256(nodes) != structure.structural_nodes_sha256:
        return f"the structural node file {EXTERNAL_NODES_FILE} changed after the plan hashed it"
    executable = Path(structure.executable)
    if not executable.is_file():
        return f"the executable {executable} is missing"
    if _sha256(executable) != structure.executable_sha256:
        return f"the executable {executable} changed after the plan hashed it"
    for name, expected in structure.inputs_sha256.items():
        staged = directory / name
        if not staged.is_file():
            return f"the declared input {name} is not in the point folder"
        if _sha256(staged) != expected:
            return f"the declared input {name} changed after the plan hashed it"
    return None


def _run_program(
    directory: Path, structure: ExternalStructure
) -> tuple[int | None, float, str | None]:
    """Run the program in ``directory``, no console window; return code, seconds, failure."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    started = time.perf_counter()
    try:
        done = subprocess.run(  # noqa: S603 - the program the plan hashed, no shell
            [structure.executable, *structure.arguments],
            cwd=directory,
            capture_output=True,
            timeout=structure.timeout_s,
            check=False,
            creationflags=flags,
            # The program runs in the environment the solver gave the step,
            # passed on as it is, stated here rather than inherited unseen.
            env=dict(os.environ),
        )
    except subprocess.TimeoutExpired:
        return None, time.perf_counter() - started, f"timed out after {structure.timeout_s} s"
    except OSError as error:
        return None, time.perf_counter() - started, f"could not start: {error}"
    seconds = time.perf_counter() - started
    _textio.write_text(
        directory / _STDOUT,
        done.stdout.decode("utf-8", errors="replace")
        + done.stderr.decode("utf-8", errors="replace"),
    )
    return done.returncode, seconds, None


def _judge_displacements(directory: Path, structure: ExternalStructure) -> tuple[int, str | None]:
    """Return the rows the program wrote and why they are refused, or None."""
    path = directory / DISPLACEMENT_FILE
    if not path.is_file():
        return 0, f"the program wrote no {DISPLACEMENT_FILE}"
    try:
        rows = read_fsidisp(path)
    except FsiInputError as error:
        return 0, str(error)
    if len(rows) != structure.node_count:
        return len(rows), (
            f"{DISPLACEMENT_FILE} holds {len(rows)} rows for {structure.node_count} "
            "structural nodes"
        )
    if not all(math.isfinite(float(value)) for value in rows.ravel()):
        return len(rows), f"{DISPLACEMENT_FILE} holds a value that is not finite"
    return len(rows), None


def external_step(directory: str | Path) -> int:
    """Run, archive and validate one call of the external structural program (FR-1092).

    Parameters
    ----------
    directory : str or Path
        The point folder the solver runs the coupling in, holding
        :data:`EXTERNAL_MANIFEST`.

    Returns
    -------
    int
        0 when the call passed every check; 1 otherwise, with the reason in
        ``pyfs_fsi_error.log``, which stops the coupling. A manifest declaring an
        input or output under a name of :data:`STEP_NAMES` returns 1 before the
        program runs and before anything is archived.
    """
    folder = Path(directory)
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    manifest = folder / EXTERNAL_MANIFEST
    try:
        structure = ExternalStructure.model_validate_json(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        with _textio.open_text(folder / _ERROR_LOG, "a") as log:
            log.write(f"{stamp} pyfs-fsi external: cannot read {manifest}: {error}\n")
        return 1
    taken = step_name_collisions([*structure.inputs, *structure.outputs])
    if taken:
        # A manifest the plan would have refused: running the program would let
        # its files and the step's overwrite each other, so nothing runs.
        with _textio.open_text(folder / _ERROR_LOG, "a") as log:
            log.write(
                f"{stamp} pyfs-fsi external: {manifest} declares "
                f"{', '.join(repr(name) for name in taken)}, a name the archiving step "
                "owns; the program was not run and nothing was archived\n"
            )
        return 1
    call = _next_call(folder)
    archive = folder / _ARCHIVE_DIR / f"call_{call:04d}"
    archive.mkdir(parents=True, exist_ok=True)
    loads = folder / LOADS_FILE
    read: dict[str, str] = {}
    nodes = folder / EXTERNAL_NODES_FILE
    if nodes.is_file():
        read[nodes.name] = _sha256(nodes)
    if loads.is_file():
        shutil.copy2(loads, archive / LOADS_FILE)
        read[LOADS_FILE] = _sha256(loads)
    stale = folder / DISPLACEMENT_FILE
    if stale.is_file():
        # The previous call's answer is archived there; a program that writes
        # nothing this call must not pass on it.
        stale.unlink()
    reason = _verify_digests(folder, structure)
    code: int | None = None
    seconds = 0.0
    rows = 0
    if reason is None:
        code, seconds, reason = _run_program(folder, structure)
        if reason is None and code != 0:
            reason = f"the program returned {code}"
        if reason is None:
            rows, reason = _judge_displacements(folder, structure)
    written: dict[str, str] = {}
    for name in (DISPLACEMENT_FILE, *structure.outputs):
        produced = folder / name
        if produced.is_file():
            shutil.copy2(produced, archive / name)
            written[name] = _sha256(produced)
    verdict = "passed" if reason is None else "failed"
    record = {
        "call": call,
        "started": stamp,
        "command": [structure.executable, *structure.arguments],
        "return_code": code,
        "wall_time_s": round(seconds, 6),
        "read_sha256": {**read, **structure.inputs_sha256},
        "written_sha256": written,
        "node_count": structure.node_count,
        "rows_written": rows,
        "verdict": verdict,
        "reason": reason or "",
    }
    _textio.write_text(archive / ARCHIVE_RECORD, json.dumps(record, indent=2) + "\n")
    _append_log(folder, record)
    if reason is None:
        return 0
    with _textio.open_text(folder / _ERROR_LOG, "a") as log:
        log.write(f"{stamp} pyfs-fsi external call {call} failed in {folder}: {reason}\n")
    return 1
