"""Evidence checks for stopped runs whose manifests predate frame placement."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

from pyflightstream._digest import file_sha256
from pyflightstream.cases import CampaignConfigError, ScriptRecipe, SimCase, case_at_point
from pyflightstream.cases.workflows import RESERVED_CONTINUATION_VARIABLES, RESTART_VARIABLE
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord


def _refuse(record: RunRecord, reason: str) -> NoReturn:
    raise CampaignConfigError(
        f"run {record.run_id!r} recorded no placement of its analysis loads frame; "
        f"offline recovery cannot prove the same stopped row: {reason}. "
        "Nothing was archived or launched. Restore the original row and evidence, "
        "or set tecplot = false to continue without a surface Tecplot export."
    )


def _verified_file(record: RunRecord, path: Path, digest: str | None, label: str) -> None:
    if not digest or not path.is_file():
        _refuse(record, f"{label} is missing or has no recorded SHA256")
    if file_sha256(path) != digest:
        _refuse(record, f"{label} changed since the stopped run")


def _native_setup(text: str, script: Script) -> tuple[str, ...]:
    """Compare native setup, excluding output serialization and comments.

    0.27 wrote Tecplot natively; current releases translate VTK. Exports
    select no loads frame. Scientific commands and their order stay compared.
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    kept: list[str] = []
    at = 0
    while at < len(lines):
        line = lines[at]
        if line == "SET_VTK_EXPORT_VARIABLES -1 DISABLE":
            at += 1
            continue
        if line in {
            "EXPORT_SOLVER_ANALYSIS_TECPLOT",
            "EXPORT_SOLVER_ANALYSIS_VTK",
        } and at + 1 < len(lines):
            filename = lines[at + 1]
            suffix = ".dat" if line.endswith("TECPLOT") else ".vtk"
            # Only the documented surface serialization difference is ignored.
            # Unknown commands and unproved grammars remain in the comparison.
            if filename.split()[0] not in script.registry.commands and filename.strip(
                '"'
            ).lower().endswith(suffix):
                if line.endswith("TECPLOT"):
                    at += 2
                    continue
                if at + 2 < len(lines) and lines[at + 2] == "SURFACES -1":
                    at += 3
                    continue
        kept.append(line)
        at += 1
    return tuple(kept)


def _input_hashes(record: RunRecord, case: SimCase, script: Script) -> dict[str, str]:
    current: dict[str, str] = {}
    for name in (case.geometry, case.freestream_profile):
        if name is not None:
            path = Path(name)
            _verified_file(
                record, path, record.inputs_sha256.get(path.name), f"input {path.name!r}"
            )
            current[path.name] = file_sha256(path)
    if case.fsi is not None or script.pending_action_scripts:
        _refuse(record, "the historical record cannot verify FSI or child-script dependencies")
    for name, content in script.pending_input_files.items():
        key = Path(name).name
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        candidates = {hashlib.sha256(data).hexdigest()}
        if isinstance(content, str):
            candidates.add(hashlib.sha256(data.replace(b"\n", b"\r\n")).hexdigest())
        expected = record.inputs_sha256.get(key)
        if expected not in candidates:
            _refuse(record, f"generated input {key!r} changed or has no recorded SHA256")
        if key in current and current[key] != expected:
            _refuse(record, f"input identity {key!r} is ambiguous")
        current[key] = str(expected)
    if current != record.inputs_sha256:
        _refuse(record, "the set of native input identities changed or cannot be reconstructed")
    return current


def _rebuild(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    record: RunRecord,
    recipe: ScriptRecipe,
    version: str,
) -> Script:
    from pyflightstream.cases import point_name
    from pyflightstream.workspace import PointName, datapoint_dir_name

    variables = {
        k: v
        for k, v in case.variables.items()
        if k not in (RESTART_VARIABLE, *RESERVED_CONTINUATION_VARIABLES)
    }
    updates: dict[str, object] = {"variables": variables}
    if case.geometry is not None:
        staged = workspace.sim_dir(case.sim_id) / "inputs" / Path(case.geometry).name
        _verified_file(
            record,
            staged,
            record.inputs_sha256.get(staged.name),
            f"staged geometry {staged.name!r}",
        )
        updates["geometry"] = str(staged)
    shadow_case = case_at_point(case, dict(point), **updates)
    shadow = Script(version)
    work = (
        workspace.sim_dir(case.sim_id)
        / "datapoints"
        / datapoint_dir_name(PointName(point_name(case, point)))
    )
    shadow.working_dir = str(work)
    try:
        recipe(shadow_case, shadow)
        shadow.render()
    except Exception as error:
        _refuse(record, f"the original row cannot be rebuilt: {type(error).__name__}: {error}")
    return shadow


def recover_frame(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    record: RunRecord,
    saved: str,
    recipe: ScriptRecipe,
    version: str,
) -> dict[str, object]:
    """Recover a frame only after proving the original native setup and inputs."""
    from itertools import zip_longest

    from pyflightstream.versions import resolve

    if record.continues:
        _refuse(record, "an unplaced restart chain does not retain a proven original setup")
    if record.point != dict(point) or record.recipe != case.recipe:
        _refuse(record, "the point or recipe identity changed or was not recorded")
    if resolve(record.fs_version_requested).canonical != resolve(version).canonical:
        _refuse(record, "the requested FlightStream version changed")
    sim = workspace.sim_dir(case.sim_id)
    if not record.script_path:
        _refuse(record, "original script path is missing; no SHA256 evidence can be checked")
    original = sim / record.script_path
    _verified_file(record, original, record.script_sha256, "original script")
    saved_digest = record.outputs_sha256.get(saved)
    _verified_file(record, sim / saved, saved_digest, "saved simulation")
    shadow = _rebuild(workspace, case, point, record, recipe, version)
    inputs = _input_hashes(record, case, shadow)
    try:
        was = _native_setup(original.read_text(encoding="utf-8"), shadow)
        rebuilt = shadow.render()
        now = _native_setup(rebuilt, shadow)
    except (OSError, UnicodeError, ValueError) as error:
        _refuse(record, f"native setup evidence cannot be read: {error}")
    if was != now:
        before, after = next((a, b) for a, b in zip_longest(was, now) if a != b)
        _refuse(record, f"native setup changed: recorded {before!r}; rebuilt {after!r}")
    frame = shadow.loads_frame_record()
    if not shadow.sets_loads_frame or frame.get("origin") is None or frame.get("axes") is None:
        _refuse(record, "the rebuilt analysis loads-frame placement is ambiguous")
    return {
        "recovered_frame": frame,
        "frame_recovery": {
            "method": "offline_native_setup_and_input_comparison",
            "source_run_id": record.run_id,
            "script_sha256": record.script_sha256,
            "inputs_sha256": inputs,
            "saved_simulation_sha256": saved_digest,
            "reconstructed_text_sha256": hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
        },
    }
