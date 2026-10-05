"""The rebuild of run records from the simulation folders under ``sims/``.

The matrix row is run again through this package's own campaign loop in a
throwaway SHADOW workspace, with a submitting executor that submits nothing,
which mints the SUBMITTED record; the executed script under
``sims/sim_<id>/scripts/`` must be the script the row renders now, and every
record the rebuild makes says so in its ``warnings``, beginning with
:data:`REBUILT`. The module docstring of :mod:`pyflightstream.run.records`
states the procedure and what proves it; :func:`rebuild` is its entry and
:func:`summary_lines` its report.

The public names are re-exported, unchanged, by :mod:`pyflightstream.run.records`,
their path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import json
import re
import shutil
import tempfile
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream.run._executors import PROGRESS_EVERY_DEFAULT
from pyflightstream.run._rebuild_evidence import (
    _changes,
    _compare_scripts,
    _copy_inputs,
    _drift,
    _Known,
    _known_runs,
    _matrices,
    _on_disk,
    _plan_campaign_name,
    _reactivate,
    _read_rows,
    _shadow_home,
    _sim_of,
    _slashes,
    _snapshot,
    collect_without_writing,
    descriptor_folder,
)
from pyflightstream.run._rebuild_grouped import (
    batch_label,
    grouped_facts,
    grouped_point,
    rendered_at_home,
    simulation_home,
    with_job,
)
from pyflightstream.run._record_files import (
    RecordsError,
    _now_stamp,
    _relative,
    _replace_bytes,
    manifest_lock,
)
from pyflightstream.workspace._matrix_homes import matrix_path
from pyflightstream.workspace.naming import (
    DEFAULT_MANIFEST,
    free_root_archive,
    resolve_manifest,
)

#: Seconds a simulation folder must have been quiet before its job is taken as
#: over. A folder written more recently stays SUBMITTED, since its job may
#: still be writing (RST-7); 30 minutes is the window the prototype measured.
QUIET_WINDOW_S = 1800.0

#: The word every rebuilt record's warning starts with.
REBUILT = "REBUILT"

#: What to do about a row this version cannot mint again (FR-412 R3).
_MINT_REMEDY = (
    "rebuild with the pyflightstream version that ran it, or pass the matrix revision that "
    "ran (CLI: --matrix FILE)"
)

_NOT_RECOVERABLE_NOTE = (
    "do not run `pyfs-matrix run --resume` on a refused simulation: with no record, the "
    "resume takes it as never run and runs it again"
)


# ---------------------------------------------------------------------------
# the run layer's own machinery, public
# ---------------------------------------------------------------------------


def row_versions(resolved: Any) -> dict[str, str]:
    """Return the per-simulation solver version of a bound matrix, keyed by sim id.

    The version each row's build declares in the build registry; a row on a
    build declaring none is absent and runs under the campaign default. The
    same answer ``pyfs-matrix plan`` and ``run`` use.

    Parameters
    ----------
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix.
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._row_versions(resolved)


def campaign_executor(
    workspace: Any,
    resolved: Any,
    path: str | Path,
    *,
    executor: Any = None,
    local: bool = False,
    hidden: bool | None = None,
    progress_every: int = PROGRESS_EVERY_DEFAULT,
) -> tuple[Any, Callable[[Path], Any]]:
    """Return the executor a bound matrix runs on, and the one for each other build.

    The one choice ``pyfs-matrix run`` makes: a caller's ``executor`` answers
    for every build; left out, the cluster rule and the matrix's HIDDEN column
    decide. A build the submission profile cannot name is refused here.

    Parameters
    ----------
    workspace : pyflightstream.workspace.CampaignWorkspace
        The campaign root, whose submission profile a cluster reads.
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix; its ``fs_exe`` is the campaign's own executable.
    path : str or Path
        The matrix file.
    executor : pyflightstream.run.Executor, optional
        An executor that answers for every build; left out, the cluster rule and
        the matrix's HIDDEN column decide.
    local : bool, optional
        Keep the run on this machine, as ``pyfs-matrix run --local``.
    hidden : bool or None, optional
        Windowless solver runs; None lets the matrix's HIDDEN column decide.
    progress_every : int, optional
        How often a local unsteady point says its progress, in time steps.
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._campaign_executor(
        workspace,
        resolved,
        path,
        executor=executor,
        local=local,
        hidden=hidden,
        progress_every=progress_every,
    )


def bind_row_builds(
    resolved: Any, default: str | None, executor: Any, executor_for: Callable[[Path], Any]
) -> tuple[Any, Any]:
    """Carry each row's build onto the campaign that runs, as ``pyfs-matrix run`` does.

    Returns the campaign and the ``builds`` mapping the campaign loop takes.
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._bind_row_builds(resolved, default, executor, executor_for)


# ---------------------------------------------------------------------------
# rebuild: one simulation, re-minted in the shadow
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Outcome:
    records: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    refused: dict[str, str] = dataclasses.field(default_factory=dict)
    notes: list[str] = dataclasses.field(default_factory=list)
    never_ran: list[str] = dataclasses.field(default_factory=list)
    waiting: list[str] = dataclasses.field(default_factory=list)
    changes: list[str] = dataclasses.field(default_factory=list)
    aliases: dict[str, str] = dataclasses.field(default_factory=dict)


def _row_inputs(matrix: Path, pol: str) -> list[str]:
    """Return the reference, setup and pproc files a row names, relative to ``inputs/``."""
    from pyflightstream.cases.matrix import read_matrix

    try:
        rows = read_matrix(matrix, active_only=False)
    except Exception:  # noqa: BLE001 - an unreadable matrix names no input; its refusal comes later
        return []
    for row in rows:
        if str(row.pol) == pol:
            names = []
            for folder, code in (
                ("references", row.ref_code),
                ("setups", row.set_code),
                ("pproc", row.pproc_code),
            ):
                if code:
                    names.append(f"{folder}/{code}.toml")
            return names
    return []


def _stub_profile() -> Any:
    from pyflightstream.workspace.inputs import HpcProfile

    return HpcProfile(
        application_id="pyfs-rebuild-no-submission",
        descriptor_format="text",
        descriptor_name="pyfs_rebuild_no_submission.txt",
        fields={"script": "{script_path}"},
        submit=("true",),
        defaults={},
        path=Path("pyfs-rebuild-no-submission.toml"),
    )


@dataclasses.dataclass
class _Context:
    base: Path
    shadow: Path
    version: str
    profile: Any
    build_alias: Mapping[str, str]
    origin: Path | None
    origin_differs: list[str]
    known: dict[str, _Known]
    quiet_window_s: float


def _mint(
    context: _Context,
    matrix: Path,
    sim: str,
    template: str,
    name: str,
    name_from: str | None,
    out: _Outcome,
    notes: list[str],
) -> tuple[list[dict[str, Any]], str] | str:
    """Run one simulation's row in the shadow with nothing submitted.

    Returns the SUBMITTED rows the loop wrote and the rendered script text,
    or the refusal.
    """
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import (
        CampaignErrors,
        LoadsAssessor,
        SubmittingExecutor,
        plan_campaign,
        run_campaign,
    )
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import resolve_matrix
    from pyflightstream.workspace.naming import NamingTemplate

    shadow = context.shadow
    workspace = CampaignWorkspace(shadow, naming=NamingTemplate(point_name=template))
    resolved = resolve_matrix(
        matrix, workspace, name=name, fs_version=None, recipes={}, ignore_missing_families=True
    )
    cases = list(resolved.campaign.sims)
    index = next(number for number, case in enumerate(cases) if str(case.sim_id) == sim)
    campaign = resolved.campaign.model_copy(update={"sims": [cases[index]]})
    row_builds = resolved.row_builds
    if len(row_builds) == len(cases):
        row_builds = (row_builds[index],)
    one = dataclasses.replace(resolved, campaign=campaign, row_builds=row_builds)
    build = row_builds[0] if row_builds else None
    profile = context.profile
    if profile is not None and profile.builds and build and build not in profile.builds:
        alias = context.build_alias.get(build, build)
        profile = dataclasses.replace(profile, builds={**profile.builds, build: alias})
        line = (
            f"the submission profile maps no scheduler name for build {build}; {alias} was "
            f"assumed (build_alias, CLI: --build-alias {build}=ALIAS; the build itself by "
            "default), in the job descriptor only: the solver script does not carry it"
        )
        if build not in out.aliases:
            out.notes.append(line)
        out.aliases[build] = alias
        notes.append(line)
    plan = plan_campaign(
        campaign,
        workspace,
        recipes=workflow_registry(),
        versions=row_versions(one),
        matrix_path=matrix,
        write_plan=False,
    )
    if plan.blocked:
        return (
            f"pyflightstream {context.version} refuses this row now, so its record cannot be "
            f"minted again: {plan.blocked[0].error}; correct the row, or {_MINT_REMEDY}"
        )
    executor = SubmittingExecutor(
        profile or _stub_profile(),
        values={"fs_build": build or campaign.fs_version or ""},
        submit=False,
    )
    executor, executor_for = campaign_executor(workspace, one, matrix, executor=executor)
    bound, builds = bind_row_builds(one, None, executor, executor_for)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            run_campaign(
                bound,
                executor,
                workspace,
                assess=LoadsAssessor(),
                recipes=workflow_registry(),
                builds=builds,
                name_from=name_from,
                preflight=False,
                quiet=True,
            )
        except CampaignErrors:
            pass
    rows = [row for row in workspace.read_raw_manifest() if str(row.get("sim_id")) == sim]
    bad = [row for row in rows if row.get("status") != "SUBMITTED"]
    if bad or not rows:
        reason = f"{bad[0].get('status')}: {bad[0].get('error')}" if bad else "no record came out"
        return f"the package could not mint this row's record again ({reason}); {_MINT_REMEDY}"
    scripts = {str(row["script_path"]) for row in rows}
    rendered = "\n".join(
        (shadow / "sims" / f"sim_{sim}" / script).read_text(encoding="utf-8", errors="replace")
        for script in sorted(scripts)
    )
    return rows, rendered


def _clear_shadow_run(shadow: Path, sim: str) -> None:
    (shadow / DEFAULT_MANIFEST).unlink(missing_ok=True)
    shutil.rmtree(shadow / "sims" / f"sim_{sim}", ignore_errors=True)


def _join_root(run_root: str, relative: Path) -> str:
    """Join a relative path onto the run's own root, in that root's separator style."""
    if run_root.startswith("/"):
        return run_root.rstrip("/") + "/" + relative.as_posix()
    return str(Path(run_root) / relative)


def _substitute(record: dict[str, Any], pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Replace every spelling of the shadow root by the run's root, in its own style."""
    text = json.dumps(record)
    for old, new in pairs:
        if not old or old == new:
            continue
        text = text.replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1])
        if new.startswith("/"):
            escaped = json.dumps(new)[1:-1]
            text = re.sub(
                re.escape(escaped) + r'[^"]*',
                lambda match: match.group(0).replace("\\\\", "/"),
                text,
            )
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def _utc(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).isoformat(timespec="seconds")


def _mint_one(
    context: _Context,
    matrix: Path,
    sim: str,
    *,
    name: str,
    name_from: str | None,
    templates: Sequence[str],
    notes: list[str],
    out: _Outcome,
) -> tuple[list[dict[str, Any]], str, Path] | str:
    """Mint one simulation's rows with the first point-name template whose scripts are on disk.

    Returns the SUBMITTED rows, the rendered script text and the folder the
    simulation's scripts are in now (its home, or its batch folder before the
    batch was moved home, FR-412 R1b), or the refusal.
    """
    shadow = context.shadow
    refusal = (
        "no point-name template names a script that is in the folder; pass the matrix "
        "revision that ran (CLI: --matrix FILE)"
    )
    for template in templates:
        try:
            attempt = _mint(context, matrix, sim, template, name, name_from, out, notes)
        except Exception as error:  # noqa: BLE001 - every refusal of the package is this sim's reason
            _clear_shadow_run(shadow, sim)
            return (
                "the package could not mint this row's record again: "
                f"{type(error).__name__}: {error}; {_MINT_REMEDY}"
            )
        _clear_shadow_run(shadow, sim)
        if isinstance(attempt, str):
            return attempt
        rows, rendered = attempt
        scripts = [str(row["script_path"]) for row in rows]
        home = simulation_home(context.base, sim, scripts)
        missing = [script for script in scripts if not (home / script).is_file()]
        if missing:
            refusal = (
                f"the package names its script {missing[0]}, which is not in the folder: the run "
                "used another point-name template or another matrix; pass the matrix revision "
                "that ran (CLI: --matrix FILE)"
            )
            continue
        return rows, rendered, home
    return refusal


def _rebuild_one(
    context: _Context,
    matrix: Path,
    sim: str,
    name: str,
    name_from: str | None,
    templates: Sequence[str],
    notes: list[str],
    out: _Outcome,
) -> None:
    """Mint, prove and complete the records of one simulation, or refuse it."""
    shadow = context.shadow
    minted = _mint_one(
        context,
        matrix,
        sim,
        name=name,
        name_from=name_from,
        templates=templates,
        notes=notes,
        out=out,
    )
    if isinstance(minted, str):
        out.refused[sim] = minted
        return
    rows, rendered, sim_dir = minted
    executed = "\n".join(
        (sim_dir / script).read_text(encoding="utf-8", errors="replace")
        for script in sorted({str(row["script_path"]) for row in rows})
    )
    # FR-412: a batch point's script names its batch folder; read the rendering there.
    label = batch_label(executed, sim)
    comparison = _compare_scripts(rendered_at_home(rendered, shadow, sim, label), executed, shadow)
    known = context.known.get(sim)
    ran_on = known.package_version if known else None
    if ran_on and ran_on != context.version:
        out.refused[sim] = (
            f"the run was recorded by pyflightstream {ran_on} "
            f"({known.source if known else ''}) and "
            f"this is pyflightstream {context.version}: a record is rebuilt only by the version "
            f"that ran, since the proof is the script that version renders; rebuild it with "
            f"pyflightstream {ran_on}"
        )
        return
    inputs_used = _row_inputs(shadow / matrix.name, sim) or _row_inputs(matrix, sim)
    if not comparison.same:
        detail = _drift(comparison, shadow / "inputs", inputs_used)
        origin = (
            f" with the inputs of {context.origin} laid over the workspace's"
            if context.origin
            else ""
        )
        out.refused[sim] = (
            f"refused: the executed script is not the script pyflightstream {context.version} "
            f"renders for this row from this matrix and these inputs{origin}: {detail}. If an "
            "input changed after the run, pass the inputs that ran (CLI: --inputs-from "
            "<their inputs/ folder>); if the run was on another version, rebuild with that one"
        )
        return
    _complete_rows(
        context,
        sim,
        rows,
        sim_dir=sim_dir,
        stem=matrix.stem,
        executed=executed,
        run_root=comparison.run_root,
        inputs_used=inputs_used,
        notes=notes,
        out=out,
    )


def _complete_rows(
    context: _Context,
    sim: str,
    rows: Sequence[dict[str, Any]],
    *,
    sim_dir: Path,
    stem: str,
    executed: str,
    run_root: str | None,
    inputs_used: list[str],
    notes: list[str],
    out: _Outcome,
) -> None:
    """Complete each minted row of one proved simulation from the files on disk."""
    base, shadow = context.base, context.shadow
    descriptor_name = getattr(context.profile, "descriptor_name", None)
    for row in rows:
        facts = _facts(context, sim_dir, row)
        if facts is None:
            out.never_ran.append(str(row["run_id"]))
            continue
        if isinstance(facts, str):
            out.refused[sim] = facts
            return
        grouped = grouped_point(
            base,
            stem,
            str(row["run_id"]),
            executed=executed,
            home=sim_dir,
            run_root=run_root,
            descriptor_name=descriptor_name,
        )
        refusal = grouped_facts(facts, grouped)
        if refusal is not None:
            out.refused[sim] = refusal
            return
        facts.update(run_root=run_root, inputs_used=inputs_used, sim_dir=sim_dir)
        if facts.get("keep_submitted"):
            completed, deferred = dict(row), facts["keep_submitted"]
        else:
            completed, deferred = collect_without_writing(
                base, row, staging=shadow / "collect" / f"sim_{sim}"
            )
        record = _finalise(context, sim, completed, facts, deferred, notes)
        if grouped is not None:
            record = with_job(record, grouped, row.get("submission") or {})
        try:
            from pyflightstream.workspace import RunRecord

            RunRecord.model_validate(record)
        except Exception as error:  # noqa: BLE001 - the model's refusal is the reason given
            out.refused[sim] = f"the rebuilt record does not validate: {error}; {_MINT_REMEDY}"
            return
        out.records.append(record)


def _facts(context: _Context, sim_dir: Path, row: Mapping[str, Any]) -> dict[str, Any] | str | None:
    """Where the minted record's outputs are, and whether its job is over.

    None for a point with no datapoint folder (it never ran); a string for a
    refusal; else the facts the completion needs.
    """
    from pyflightstream.workspace.naming import PointName, datapoint_dir_name

    submission = row.get("submission") or {}
    working = submission.get("working_dir")
    work_dir = sim_dir / working if working else sim_dir
    by_point = submission.get("declared_by_point") or {}
    point_dirs = (
        [sim_dir / "datapoints" / datapoint_dir_name(PointName(tag)) for tag in by_point]
        if by_point
        else [work_dir]
    )
    present = [folder for folder in point_dirs if folder.is_dir()]
    if not present:
        return None
    profile = context.profile
    descriptor_dir = descriptor_folder(context.base, sim_dir, work_dir, profile)
    submitted_here = descriptor_dir is not None
    declared = [str(name) for name in submission.get("declared_outputs") or []]

    def where(name: str) -> Path | None:
        for folder in [work_dir, *present]:
            if (folder / name).is_file():
                return folder / name
        return None

    found = {name: where(name) for name in declared}
    newest = max(
        (
            path.stat().st_mtime
            for folder in present
            for path in folder.rglob("*")
            if path.is_file()
        ),
        default=0.0,
    )
    quiet = time.time() - newest >= context.quiet_window_s
    facts: dict[str, Any] = {
        "work_dir": work_dir,
        "descriptor_dir": descriptor_dir,
        "submitted_here": submitted_here,
        "found": found,
    }
    if not any(found.values()):
        if submitted_here:
            facts["keep_submitted"] = (
                "no declared output has landed yet: the job may be queued, running or lost; "
                "pyfs-matrix collect waits for it"
            )
        else:
            return (
                f"{row['run_id']}: its datapoint folder holds no declared output, so there is "
                "no run to record; delete the empty folder, or run the point again (CLI: "
                "pyfs-matrix run --resume runs the points no record carries)"
            )
    elif not quiet:
        facts["keep_submitted"] = (
            f"files changed less than {context.quiet_window_s / 60:g} minutes ago: the job may "
            "still be writing; pyfs-matrix collect completes it once it settles"
        )
    return facts


def _finalise(
    context: _Context,
    sim: str,
    record: dict[str, Any],
    facts: Mapping[str, Any],
    deferred: str | None,
    notes: Sequence[str],
) -> dict[str, Any]:
    """Put back what the shadow could not know, and say what was reconstructed."""
    from pyflightstream.run import LocalExecutor
    from pyflightstream.run.collect import assessment_of_collected
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

    base, shadow = context.base, context.shadow
    sim_dir: Path = facts.get("sim_dir") or base / "sims" / f"sim_{sim}"
    run_root = facts.get("run_root") or str(base)
    record = _substitute(record, [(str(shadow), run_root), (shadow.as_posix(), _slashes(run_root))])
    reconstructed = ["started_at", "finished_at"]
    work_dir: Path = facts["work_dir"]
    script = sim_dir / record["script_path"]
    record["script_sha256"] = file_sha256(script)
    digests = {}
    for key, value in (record.get("inputs_sha256") or {}).items():
        for folder in (work_dir, sim_dir / "inputs", sim_dir):
            if (folder / key).is_file():
                digests[key] = file_sha256(folder / key)
                break
        else:
            digests[key] = value
    record["inputs_sha256"] = digests
    workspace = CampaignWorkspace(base)
    with contextlib.suppress(Exception):
        staged_as, reason = workspace.staged_as(sim)
        if staged_as is not None:
            record["staged_as"], record["staged_as_reason"] = staged_as, reason
    status = record.get("status")
    if facts["submitted_here"]:
        descriptor = facts["descriptor_dir"] / context.profile.descriptor_name
        submission = dict(record.get("submission") or {})
        submission["submitted"] = True
        record["submission"] = submission
        record["started_at"] = record["finished_at"] = _utc(descriptor)
    else:
        if status == "SUBMITTED":
            submission = dict(record.get("submission") or {})
            submission.update(
                {"descriptor": None, "profile": None, "application_id": None, "submitted": False}
            )
            record["submission"] = submission
        else:
            record["submission"] = None
        posix = run_root.startswith("/")
        own_root = facts.get("run_root") is not None
        record["cwd"] = (
            _join_root(run_root, work_dir.relative_to(base)) if own_root else str(work_dir)
        )
        script_at_run = _join_root(run_root, script.relative_to(base)) if own_root else str(script)
        try:
            local = LocalExecutor(record["fs_exe"], hidden=True)
            argv = [str(item) for item in local._argv(Path(script_at_run))]
            if posix:
                argv = [
                    script_at_run if item == str(Path(script_at_run)) else item for item in argv
                ]
        except Exception:  # noqa: BLE001 - an executable not on this machine still has an argv
            argv = [str(record.get("fs_exe")), "-script", script_at_run]
        record["argv"] = argv
        record["executor"] = {"class_name": "LocalExecutor", "argv": argv}
        reconstructed += ["argv", "executor", "cwd"]
        record["started_at"] = _utc(script)
        log = record.get("log_file_used")
        ends = (
            [work_dir / log]
            if log and (work_dir / log).is_file()
            else [path for path in facts["found"].values() if path is not None]
        )
        record["finished_at"] = (
            _utc(max(ends, key=lambda path: path.stat().st_mtime)) if ends else record["started_at"]
        )
        record["wall_time_s"] = None
        if status != "SUBMITTED":
            with contextlib.suppress(Exception):
                record["outputs_sha256"] = workspace.output_digests(
                    sim, record.get("outputs") or []
                )
                reconstructed.append("outputs_sha256 (hashed now)")
            with contextlib.suppress(Exception):
                assessment = assessment_of_collected(RunRecord.model_validate(record), sim_dir)
                record["fs_version_reported"] = assessment.fs_version_reported
                record["fs_build"] = assessment.fs_build
    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    lost = [] if facts["submitted_here"] else ["wall_time_s"]
    note = (
        f"{REBUILT} on {stamp} from sims/sim_{sim} with pyflightstream {context.version}: not "
        "the record written when it ran. The setup fields come from the package running the "
        "matrix row again with nothing submitted, proved by the executed script being the one "
        "this version renders; status and solver figures from the package's collect stage over "
        f"the files on disk; reconstructed: {', '.join(reconstructed)}"
        + (f"; not recoverable: {', '.join(lost)}" if lost else "")
        + "."
    )
    if deferred:
        note += f" Left SUBMITTED: {deferred}"
    extra = list(dict.fromkeys(notes))
    used = set(facts.get("inputs_used") or [])
    taken = [name for name in context.origin_differs if name in used] or (
        list(context.origin_differs) if context.origin_differs and not used else []
    )
    if context.origin is not None and taken:
        extra.append(
            "DRIFT: input(s) "
            + ", ".join(f"inputs/{name}" for name in taken)
            + f" taken from {context.origin}, whose bytes differ from the workspace's; the "
            "workspace's own files were not changed"
        )
    record["warnings"] = [*list(record.get("warnings") or []), note, *extra]
    return record


# ---------------------------------------------------------------------------
# rebuild: the entry
# ---------------------------------------------------------------------------


def _refuse_before_any_work(
    base: Path,
    out: str | None,
    all_sims: bool,
    sims: Sequence[str] | None,
    matrix: str | Path | None,
    inputs_from: str | Path | None,
) -> Path | None:
    """Every refusal a rebuild can make from its arguments alone, before it reads anything."""
    if all_sims and out is None:
        raise RecordsError(
            "rebuild all_sims (CLI: --all-sims) needs out (CLI: --out), the manifest NAME: it "
            "rebuilds every simulation to compare with runs.json, and never writes runs.json"
        )
    if all_sims and sims:
        raise RecordsError(
            "rebuild: all_sims (CLI: --all-sims) is every simulation on disk; give it or sims "
            "(CLI: --sims), not both"
        )
    target = None
    if out is not None:
        target = resolve_manifest(base, out)
        if target.name.lower() == DEFAULT_MANIFEST:
            raise RecordsError(
                f"rebuild out (CLI: --out) may not be {DEFAULT_MANIFEST}: out names another file, "
                "so runs.json is never touched; choose another name"
            )
        if target.exists():
            raise RecordsError(
                f"rebuild out (CLI: --out) {out}: the file exists; choose a new name, nothing "
                "is overwritten"
            )
    if matrix is not None and not Path(matrix).is_file():
        raise RecordsError(
            f"rebuild matrix (CLI: --matrix) {matrix}: no such file in the workspace's matrix "
            "homes (its root and inputs/matrices/) or at that path; name the matrix the "
            "simulations ran from"
        )
    if inputs_from is not None and not Path(inputs_from).is_dir():
        raise RecordsError(
            f"rebuild inputs_from (CLI: --inputs-from) {inputs_from}: no such folder; name the "
            "inputs/ folder of the workspace whose inputs ran"
        )
    return target


def _refused_before_minting(
    sim: str,
    out: _Outcome,
    *,
    retired: set[str],
    folders: set[str],
    zipped: set[str],
    submitted: set[str],
) -> bool:
    """Refuse, naming its reason and remedy, a simulation a rebuild cannot start on (FR-412 R3)."""
    if sim in retired:
        out.refused[sim] = (
            "delete-sims retired this simulation, so it is not brought back; run its row again "
            "to make a new record"
        )
    elif sim in zipped and sim not in folders:
        out.refused[sim] = (
            "stored compressed (sims/sim_<id>.zip); expand it with the package first, then "
            "rebuild. A rebuild never expands or deletes an archive"
        )
    elif sim not in folders:
        out.refused[sim] = (
            "no such simulation folder under sims/ or in a batch folder under sims/batch/; name "
            "a simulation whose folder is there"
        )
    elif sim in submitted:
        out.refused[sim] = (
            "SUBMITTED in runs.json: a rebuild gives it no end; pyfs-matrix collect "
            "completes it, or rebuild every simulation (all_sims, CLI: --all-sims)"
        )
    else:
        return False
    return True


def rebuild(
    root: str | Path,
    *,
    out: str | None = None,
    all_sims: bool = False,
    sims: Sequence[str] | None = None,
    build_alias: Mapping[str, str] | None = None,
    matrix: str | Path | None = None,
    apply: bool = False,
    inputs_from: str | Path | None = None,
) -> dict[str, Any]:
    """Rebuild run records from the simulation folders under ``sims/``.

    Each record is minted again by this package from the matrix row, proved
    by the executed script being the one this version renders for that row,
    and completed by the collect stage over the files on disk, read-only (the
    module docstring says how). A record the rebuild makes carries a warning
    starting with ``REBUILT`` that says what was reconstructed and with which
    version.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    out : str, optional
        The manifest file the rebuilt records go to, a name
        :func:`resolve_manifest` accepts, never ``runs.json`` and never a file
        that exists: both refused before any work. With it ``runs.json`` is
        never touched: the file holds the rows of ``runs.json`` with each
        rebuilt record in the place of the row of its run id, and the other
        rebuilt records after them (with ``all_sims``, the rebuilt records
        only). Without it, applying appends the rebuilt records whose
        run ids ``runs.json`` does not hold, after archiving ``runs.json`` to
        ``archive/runs-<stamp>.json``, or writes ``runs.json`` when there is
        none.
    all_sims : bool, default False
        Rebuild EVERY simulation folder on disk, recorded or not, so the result
        can be compared with ``runs.json``; requires ``out``. A SUBMITTED status
        in ``runs.json`` is then ignored and each simulation takes the status
        its outputs support, except a folder written within
        :data:`QUIET_WINDOW_S`, which stays SUBMITTED. Without it only the
        simulations no record names are rebuilt, and each SUBMITTED record is
        pointed to ``pyfs-matrix collect`` rather than given an end.
    sims : sequence of str, optional
        The simulation ids to rebuild, recorded or not.
    build_alias : mapping of str to str, optional
        The scheduler name a solver build had when it ran, keyed by the build,
        for a build the submission profile no longer maps; the default is the
        build itself. It enters only the job descriptor of the shadow run,
        never the solver script, and the record says which alias was assumed.
    matrix : str or Path, optional
        The matrix revision the simulations ran from, for a POL no current
        matrix holds (a row deleted or renumbered after it ran). Name the file
        as the matrix was named when it ran. Without it every matrix at the
        root and in ``inputs/matrices/`` is read.
    apply : bool, default False
        Write the manifest; without it the call previews and writes nothing.
    inputs_from : str or Path, optional
        Another origin's ``inputs/`` folder (another workspace's, a copy from
        the cluster) whose files are laid over this workspace's in the shadow,
        for inputs that changed after the run. Each record names the inputs it
        took from there whose bytes differ from the workspace's; the
        workspace's own files are never changed.

    Returns
    -------
    dict
        ``target`` (the manifest applying writes), ``applied``, ``written``,
        ``archived_as``, ``package_version``, ``rebuilt`` (sim, run id and
        status per record), ``records`` (the rebuilt records), ``refused`` (by
        sim, the reason), ``submitted`` (the SUBMITTED run ids pointed to
        collect), ``waiting_for_matrix`` (the sims no matrix row names),
        ``never_ran``, ``build_aliases`` and ``notes``.

    Raises
    ------
    RunsManifestError
        ``out`` is not a file name directly in the root.
    RecordsError
        ``all_sims`` without ``out``, or with ``sims``; ``out`` naming
        ``runs.json`` or a file that exists; a ``matrix`` or ``inputs_from``
        that is not there; no ``sims/``; a run holding ``runs.json.lock``;
        applying when nothing was rebuilt, when the workspace tree changed
        during the rebuild, or when ``runs.json`` changed meanwhile.
    """
    import pyflightstream
    from pyflightstream.workspace.inputs import resolve_hpc_profile
    from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate

    base = Path(root).resolve()
    # FR-411: a bare name is the workspace's matrix, whatever the working directory holds.
    matrix = None if matrix is None else matrix_path(base, matrix)
    target = _refuse_before_any_work(base, out, all_sims, sims, matrix, inputs_from)
    lock = base / (DEFAULT_MANIFEST + ".lock")
    if lock.exists():
        raise RecordsError(
            f"rebuild: {lock.name} is present, so a run is writing runs.json; try again when "
            "it ends. Nothing was read or written."
        )
    if not (base / "sims").is_dir():
        raise RecordsError(f"rebuild: {base} holds no sims/ folder; run it at the workspace root")
    manifest = base / DEFAULT_MANIFEST
    manifest_bytes = manifest.read_bytes() if manifest.is_file() else None
    rows = _read_rows(manifest) if manifest_bytes is not None else []
    if rows is None:
        raise RecordsError(f"rebuild: {manifest} is not a readable list of run records")
    live = [row for row in rows if "deleted_sim" not in row]
    retired = {str(row["deleted_sim"]) for row in rows if "deleted_sim" in row}
    recorded = {sim for sim in (_sim_of(row) for row in live) if sim is not None}
    submitted_rows = [row for row in live if row.get("status") == "SUBMITTED"]
    submitted_sims = {sim for sim in (_sim_of(row) for row in submitted_rows) if sim}
    folders, zipped = _on_disk(base)
    out_come = _Outcome()
    notes = out_come.notes
    if all_sims:
        wanted = sorted((folders | zipped) - retired)
    elif sims:
        wanted = sorted(dict.fromkeys(str(sim) for sim in sims))
    else:
        wanted = sorted((folders | zipped) - recorded - retired)
    submitted: list[str] = []
    if submitted_rows and not all_sims:
        submitted = sorted(str(row["run_id"]) for row in submitted_rows)
        notes.append(
            f"{len(submitted)} record(s) are SUBMITTED in runs.json: a rebuild gives them no "
            "end; pyfs-matrix collect completes them (then post again)"
        )
    elif submitted_rows:
        notes.append(
            f"{len(submitted_rows)} record(s) are SUBMITTED in runs.json; all_sims ignores that "
            "status and judges each simulation from its outputs"
        )
    todo = [
        sim
        for sim in wanted
        if not _refused_before_minting(
            sim,
            out_come,
            retired=retired,
            folders=folders,
            zipped=zipped,
            submitted=set() if all_sims else submitted_sims,
        )
    ]
    version = str(pyflightstream.__version__)
    if todo:
        known = _known_runs(base, live)
        _rebuild_all(
            base,
            todo,
            known,
            version,
            matrix=matrix,
            build_alias=dict(build_alias or {}),
            origin=None if inputs_from is None else Path(inputs_from).resolve(),
            profile_of=lambda inputs: resolve_hpc_profile(inputs),
            templates=(MATRIX_POINT_NAME, NamingTemplate().point_name),
            out=out_come,
        )
    entry: dict[str, Any] = {
        "workspace": str(base),
        "target": target.name if target is not None else DEFAULT_MANIFEST,
        "applied": False,
        "written": None,
        "archived_as": None,
        "package_version": version,
        "rebuilt": [
            {
                "sim": str(row.get("sim_id")),
                "run_id": row.get("run_id"),
                "status": row.get("status"),
            }
            for row in out_come.records
        ],
        "records": out_come.records,
        "refused": dict(sorted(out_come.refused.items())),
        "submitted": submitted,
        "waiting_for_matrix": sorted(out_come.waiting),
        "never_ran": out_come.never_ran,
        "build_aliases": dict(out_come.aliases),
        "notes": notes + ([_NOT_RECOVERABLE_NOTE] if out_come.refused else []),
    }
    if out_come.changes:
        entry["changes"] = out_come.changes
    if not apply:
        return entry
    if out_come.changes:
        raise RecordsError(
            f"rebuild: the workspace tree changed during the rebuild ({len(out_come.changes)} "
            f"path(s), first {out_come.changes[0]}): another process is writing; nothing was "
            "written, run it again when it ends"
        )
    if not out_come.records:
        # FR-412 R3: every simulation refused is named, with its reason and its remedy.
        said = summary_lines(entry)
        head = "rebuild: no record was rebuilt, so there is nothing to write"
        raise RecordsError("\n".join([head, *said[:-2], said[-1]]))
    ids = {row.get("run_id") for row in live}
    fresh = [row for row in out_come.records if row.get("run_id") not in ids]
    if target is not None:
        # The file out names holds the REBUILT records: a rebuilt run id that
        # runs.json holds takes that row's place in this copy (runs.json itself
        # is never written), and the others are appended after the rows.
        rebuilt = {row.get("run_id"): row for row in out_come.records}
        written = (
            list(out_come.records)
            if all_sims
            else [rebuilt.get(row.get("run_id"), row) for row in rows] + fresh
        )
        try:
            with _textio.open_text(target, "x") as handle:
                handle.write(json.dumps(written, indent=2) + "\n")
        except FileExistsError as error:
            raise RecordsError(
                f"rebuild out (CLI: --out) {target.name}: the file appeared meanwhile; nothing "
                "is overwritten"
            ) from error
        entry.update(applied=True, written=target.name)
        return entry
    if not fresh:
        raise RecordsError(
            "rebuild: every rebuilt run id is already in runs.json; nothing to write (name "
            "out (CLI: --out) to write the rebuilt records beside it)"
        )
    with manifest_lock(base):
        now = manifest.read_bytes() if manifest.is_file() else None
        if now != manifest_bytes:
            raise RecordsError("rebuild: runs.json changed while the rebuild ran; nothing written")
        if now is not None:
            kept = free_root_archive(base, DEFAULT_MANIFEST, _now_stamp())
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, kept)
            entry["archived_as"] = _relative(base, kept)
        _replace_bytes(manifest, (json.dumps([*rows, *fresh], indent=2) + "\n").encode("utf-8"))
    entry.update(applied=True, written=DEFAULT_MANIFEST)
    return entry


def _restore_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix restore`` prints for its entry."""
    lines = [
        f"restore {entry['kind']}: {entry['source']} -> {entry['target']} (stamp {entry['stamp']})",
        f"  stamps available: {', '.join(entry['stamps_available'])}",
    ]
    if "records" in entry:
        lines.append(f"  the archived manifest holds {entry['records']} record(s)")
    if entry["same"]:
        lines.append("  the current file already holds these bytes; nothing to do")
    elif entry["applied"]:
        kept = entry["archived_as"]
        lines.append("  restored" + (f"; the current file was archived as {kept}" if kept else ""))
    else:
        lines.append("  preview only: add --apply to restore it")
    return lines


def summary_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix restore`` and ``rebuild`` print for an entry.

    The entry is what :func:`~pyflightstream.run.records.restore` or
    :func:`rebuild` returned: the lines say what was, or would be, written,
    and name every refusal. A rebuild's lines end with the count rebuilt and
    the count refused (FR-412 R3).
    """
    if "kind" in entry:
        return _restore_lines(entry)
    lines: list[str] = []
    rebuilt, refused = entry["rebuilt"], entry["refused"]
    lines.append(
        f"rebuild: {len(rebuilt)} record(s) rebuilt with pyflightstream "
        f"{entry['package_version']}, {len(refused)} simulation(s) refused"
    )
    for row in rebuilt:
        lines.append(f"  sim_{row['sim']}: {REBUILT} {row['status']} {row['run_id']}")
    for sim, reason in refused.items():
        lines.append(f"  sim_{sim}: NOT RECOVERABLE: {reason}")
    for run_id in entry["submitted"]:
        lines.append(f"  SUBMITTED, for pyfs-matrix collect: {run_id}")
    if entry["waiting_for_matrix"]:
        lines.append(
            "  waiting for the matrix revision that ran (--matrix FILE): "
            + ", ".join(f"sim_{sim}" for sim in entry["waiting_for_matrix"])
        )
    for run_id in entry["never_ran"]:
        lines.append(f"  never ran (no datapoint folder), no record: {run_id}")
    for line in entry["notes"]:
        lines.append(f"  note: {line}")
    for line in entry.get("changes", [])[:30]:
        lines.append(f"  the workspace changed during the rebuild: {line}")
    if entry["applied"]:
        kept = entry["archived_as"]
        lines.append(
            f"  wrote {entry['written']}"
            + (f"; the previous runs.json was archived as {kept}" if kept else "")
        )
    else:
        lines.append(f"  preview only: add --apply to write {entry['target']}")
    lines.append(f"rebuild: {len(rebuilt)} rebuilt, {len(refused)} refused")
    return lines


def _rebuild_all(
    base: Path,
    sims: Sequence[str],
    known: dict[str, _Known],
    version: str,
    *,
    matrix: str | Path | None,
    build_alias: dict[str, str],
    origin: Path | None,
    profile_of: Callable[[Path], Any],
    templates: Sequence[str],
    out: _Outcome,
) -> None:
    """Rebuild ``sims`` in one shadow workspace, proving the real tree unchanged."""
    from pyflightstream.cases.matrix import read_matrix

    notes = out.notes
    matrices = _matrices(base, matrix)
    by_pol: dict[str, Path] = {}
    for path in matrices:
        try:
            pols = [str(row.pol) for row in read_matrix(path, active_only=False)]
        except Exception as error:  # noqa: BLE001 - an unreadable matrix is said, and skipped
            notes.append(
                f"{path.name}: not readable by the package ({type(error).__name__}: {error})"
            )
            continue
        for pol in pols:
            by_pol.setdefault(pol, path)
    remaining = []
    for sim in sims:
        if sim in by_pol:
            remaining.append(sim)
            continue
        out.waiting.append(sim)
        out.refused[sim] = (
            "no row of any current matrix names this simulation (deleted or renumbered after it "
            "ran): pass the matrix revision that ran (CLI: --matrix FILE), for example the old "
            "revision from version control"
        )
    if not remaining:
        return
    shadow = Path(tempfile.mkdtemp(prefix="pyfs-rebuild-")).resolve()
    skip = shadow if (shadow == base or base in shadow.parents) else None
    before = _snapshot(base, skip)
    chatter = shadow.parent / f"{shadow.name}.log"
    try:
        try:
            profile = profile_of(base / "inputs")
        except Exception as error:  # noqa: BLE001 - several profiles: the package refuses to guess
            profile = None
            notes.append(
                f"the workspace's submission profile could not be resolved ({error}); records are "
                "rebuilt as local runs"
            )
        origin_differs = _copy_inputs(base / "inputs", shadow / "inputs", origin)
        context = _Context(
            base=base,
            shadow=shadow,
            version=version,
            profile=profile,
            build_alias=build_alias,
            origin=origin,
            origin_differs=origin_differs,
            known=known,
            quiet_window_s=QUIET_WINDOW_S,
        )
        with (
            _textio.open_text(chatter, "w") as stream,
            contextlib.redirect_stdout(stream),
            contextlib.redirect_stderr(stream),
        ):
            for path in matrices:
                chosen = [sim for sim in remaining if by_pol.get(sim) == path]
                if not chosen:
                    continue
                shadow_matrix = _shadow_home(shadow, path)
                shutil.copy2(path, shadow_matrix)
                sim_notes: dict[str, list[str]] = {sim: [] for sim in chosen}
                for pol in _reactivate(shadow_matrix, set(chosen)):
                    sim_notes[pol].append(
                        f"the row of sim_{pol} has RUN 0 in {path.name}: it was rebuilt with RUN 1 "
                        "in the shadow copy only; the matrix was not changed"
                    )
                for sim in chosen:
                    identity = known.get(sim)
                    if identity is not None and identity.campaign:
                        name, name_from = identity.campaign, identity.name_from
                        if not identity.name_from_known:
                            name_from = None
                    else:
                        planned, planned_from = _plan_campaign_name(base, path.stem)
                        name, name_from = (
                            (planned, planned_from) if planned else (base.name, "directory")
                        )
                    order = (
                        [identity.point_name_template]
                        if identity is not None and identity.point_name_template
                        else list(dict.fromkeys(templates))
                    )
                    _rebuild_one(
                        context,
                        shadow_matrix,
                        sim,
                        name,
                        name_from,
                        order,
                        sim_notes[sim],
                        out,
                    )
    finally:
        after = _snapshot(base, skip)
        out.changes = _changes(before, after)
        chatter.unlink(missing_ok=True)
        shutil.rmtree(shadow, ignore_errors=True)
