"""The completion of one additional-post extraction, local or collected (G12).

An extraction reopens a recorded point's saved simulation and exports a
second pproc from it. It ends in one of two places: on this machine, right
after the solver returns (:func:`pyflightstream.run.matrix.run_additional_post`),
or on a cluster, when ``collect`` finds its outputs settled
(:mod:`pyflightstream.run.collect`). Both complete it here, by one rule
(PFS-2103.008): the local path judged by file existence alone and recorded
EXTRACTED over a translation problem the collected path refused.

Below both callers, so neither reaches up into the other for it. It also holds the
sections a recorded run cut, which the extraction numbers its own after (RPT-062,
PFS-2130.051).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, TypeGuard

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256, optional_file_sha256, text_sha256
from pyflightstream.cases import EXPORT_KINDS
from pyflightstream.cases.workflows import creates_surface_sections
from pyflightstream.results import translate_surface_exports
from pyflightstream.run._executors import Submitting, bind_submission_values
from pyflightstream.workspace import (
    AdditionalRecord,
    CampaignWorkspace,
    ExtractionStatus,
    WorkspaceError,
)
from pyflightstream.workspace.inputs import resolve_hpc_profile
from pyflightstream.workspace.naming import ARCHIVE_DIR

if TYPE_CHECKING:
    from pyflightstream.script import Script
    from pyflightstream.workspace import RunRecord


def complete_extraction(
    workspace: CampaignWorkspace,
    base: dict[str, object],
    *,
    folder: Path,
    original: Path,
    names: Sequence[str],
    translations: Sequence[Mapping[str, object]] | None,
) -> AdditionalRecord:
    """Translate, check and record one extraction whose solver has ended.

    A TRANSLATION PROBLEM IS A FAILED EXTRACTION (Q0 CX-4), even where the
    declared ``.dat`` exists: a file whose source, frame or content proof no
    longer holds is preserved, not re-derived, and existence alone would
    record it EXTRACTED and let the private copy it could be re-made from go.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace whose additional records are appended to.
    base : dict of str to object
        The record's fields so far; its ``surface_translations`` are written here.
    folder : Path
        The extraction's working folder, where its exports are.
    original : Path
        The original saved simulation, hashed again.
    names : sequence of str
        The outputs the extraction is held to, relative to the simulation folder.
    translations : sequence of mapping, optional
        The surface translations (G45) the extraction declares.

    Returns
    -------
    AdditionalRecord
        The record, appended: EXTRACTED, FAILED_INCOMPLETE_OUTPUT naming what
        is missing, or FAILED_EXECUTION for a translation problem.
    """
    sim_dir = workspace.sim_dir(str(base["sim_id"]))
    if translations:
        base["surface_translations"] = translate_surface_exports(folder, list(translations))
    problems = [
        str(problem)
        for translation in base.get("surface_translations") or []  # type: ignore[attr-defined]
        for problem in translation.get("problems") or []
    ]
    if problems:
        return record_additional_extraction(
            workspace,
            base,
            status=ExtractionStatus.FAILED_EXECUTION,
            error="surface translation failed: " + "; ".join(problems),
            original=original,
        )
    missing = [name for name in names if not (sim_dir / name).is_file()]
    return record_additional_extraction(
        workspace,
        base,
        status=ExtractionStatus.FAILED_INCOMPLETE_OUTPUT if missing else ExtractionStatus.EXTRACTED,
        error=f"the extraction ended and did not write {', '.join(missing)}" if missing else None,
        original=original,
        outputs=[name for name in names if name not in missing],
    )


def record_additional_extraction(
    workspace: CampaignWorkspace,
    base: Mapping[str, object],
    *,
    status: ExtractionStatus,
    error: str | None,
    original: Path,
    outputs: list[str] | None = None,
) -> AdditionalRecord:
    """Hash the original again, then write the record; an original that moved fails it.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace whose manifest of additional records is appended to.
    base : mapping of str to object
        The record's fields so far, with the ``sim_id`` and the original's ``fsm_sha256`` before
        the extraction.
    status : ExtractionStatus
        The extraction's status; FAILED_EXECUTION when the original moved.
    error : str or None
        What went wrong, if anything.
    original : Path
        The original saved simulation, hashed again.
    outputs : list of str, optional
        The files the extraction wrote, in the simulation folder; each is hashed into the record.

    Returns
    -------
    AdditionalRecord
        The record, appended to the workspace.
    """
    sim_dir = workspace.sim_dir(str(base["sim_id"]))
    after = optional_file_sha256(original)
    if after != base["fsm_sha256"]:
        status = ExtractionStatus.FAILED_EXECUTION
        error = (
            f"THE ORIGINAL SAVED SIMULATION MOVED during the extraction: {original} hashed "
            f"{str(base['fsm_sha256'])[:12]} before and {(after or 'nothing')[:12]} after. "
            "The extraction opens a copy and never the original, so something else wrote "
            "it; the point's record no longer describes the file." + (f" {error}" if error else "")
        )
    listed = outputs or []
    record = AdditionalRecord.model_validate(
        {
            **base,
            "fsm_sha256_after": after,
            "status": status,
            "error": error,
            "outputs": listed,
            "outputs_sha256": {name: file_sha256(sim_dir / name) for name in listed},
        }
    )
    workspace.append_additional(record)
    return record


def extraction_context(workspace, record):
    """Resolve contained extraction paths and verify immutable source evidence."""
    from pyflightstream._digest import optional_file_sha256

    sim_dir = workspace.sim_dir(record.sim_id)
    root = sim_dir.resolve()
    folder = (sim_dir / record.working_dir).resolve()
    original = (sim_dir / record.fsm).resolve()
    script = (sim_dir / record.script_path).resolve()
    copy = folder / (record.reopened_copy or "")
    names = record.declared_outputs
    paths = [folder, original, script, copy, *(folder / name for name in names)]
    if (
        not names
        or not record.reopened_copy
        or any(not path.resolve().is_relative_to(root) for path in paths)
    ):
        raise WorkspaceError("submitted extraction has no safe declared outputs or private copy")
    changed = [
        label
        for label, path, digest in (
            ("original saved simulation", original, record.fsm_sha256),
            ("saved extraction script", script, record.script_sha256),
            ("private reopened simulation", copy, record.fsm_sha256),
        )
        if optional_file_sha256(path) != digest
    ]
    if changed:
        raise WorkspaceError("changed or missing " + ", ".join(changed))
    return sim_dir, folder, original, copy


def finish_extraction(workspace, record, context):
    """Complete a settled extraction by the one rule the local path shares, then drop its copy.

    The rule is :func:`pyflightstream.run._additional.complete_extraction`
    (PFS-2103.008): a translation problem fails the extraction and the
    private copy is kept, whatever the declared files are.
    """
    sim_dir, folder, original, copy = context
    relative = folder.relative_to(sim_dir).as_posix()
    completed = complete_extraction(
        workspace,
        record.model_dump(),
        folder=folder,
        original=original,
        names=[f"{relative}/{name}" for name in record.declared_outputs],
        translations=record.surface_translations,
    )
    return discard_extraction_copy(workspace, completed, copy)


def discard_extraction_copy(
    workspace: CampaignWorkspace, completed: AdditionalRecord, copy: Path
) -> AdditionalRecord:
    """Remove a successful extraction's private copy, recording cleanup failures as notes.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace holding the completed extraction.
    completed : AdditionalRecord
        The record already written; a failed extraction keeps its private copy.
    copy : Path
        The private saved simulation to remove after successful extraction.

    Returns
    -------
    AdditionalRecord
        The completed record, with a cleanup note when the copy remains.
    """
    if completed.status is ExtractionStatus.EXTRACTED:
        # THE EXTRACTED ROW IS WRITTEN, so a copy that cannot be removed (a
        # file still held on a share) is a note on it, never a second row
        # that re-records the extraction FAILED_EXECUTION (PFS-2103.005).
        try:
            copy.unlink(missing_ok=True)
        except OSError as error:
            said = (
                f"the private copy {copy.name} could not be removed ({error}); "
                "the extraction is complete, so remove it by hand"
            )
            note = f"{completed.note} {said}" if completed.note else said
            completed = completed.model_copy(update={"note": note})
            workspace.append_additional(completed)
    return completed


def _fill_end_pattern(pattern: str, sim: str, point: str) -> str:
    """Fill the placeholders an extraction knows, or refuse naming the one it cannot fill."""
    try:
        return pattern.format(sim=sim, point=point)
    except (KeyError, IndexError) as error:
        raise WorkspaceError(
            f"the HPC profile's log pattern {pattern!r} names {error}, which a submitted "
            "extraction cannot fill; an extraction knows {sim} and {point} only"
        ) from error


def extraction_job_end(workspace, record, folder: Path) -> str | None:
    """Say how a submitted extraction's job is known to have ended, or None while it may run.

    The HPC profile's ``job_end_files`` all matching (FR-311) ends the job. The
    scheduler's live log (``native_log``) is written while the job runs, so its
    existence says nothing about the end and is never taken as proof of it.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    point = record.point_name or ""
    job = (record.submission or {}).get("scheduler_id") or "its job"
    patterns = tuple(getattr(profile, "job_end_files", ()) or ())
    found: list[Path] = []
    for pattern in patterns:
        matched = [p for p in folder.glob(_fill_end_pattern(pattern, record.sim_id, point))]
        if not any(path.is_file() for path in matched):
            found = []
            break
        found += [path for path in matched if path.is_file()]
    if not found:
        return None
    return (
        f"the extraction job {job} ended without its outputs: "
        f"{', '.join(sorted(p.name for p in found))} exist (the HPC profile's end of job)"
    )


def _archive_extraction_script(script_target: Path, stamp: str) -> None:
    """Preserve an earlier extraction script, including same-stamp retries."""
    if script_target.is_file():
        archived = script_target.parent / ARCHIVE_DIR / stamp / script_target.name
        index = 2
        while archived.exists():
            archived = script_target.parent / ARCHIVE_DIR / f"{stamp}.{index}" / script_target.name
            index += 1
        archived.parent.mkdir(parents=True, exist_ok=True)
        script_target.replace(archived)


def _launch_extraction(executor, case, script_path, folder, copy, *, base):
    """Return the launch result or refusal after cleaning a local private copy."""
    result = None
    error_text = None
    try:
        bind_submission_values(executor, case, case)
        result = executor.run_script(
            script_path, working_dir=folder, timeout_s=case.solver.timeout_s
        )
    except Exception as error:
        error_text = f"{type(error).__name__}: {error}"
    finally:
        if (result is None and not isinstance(executor, Submitting)) or (
            result is not None and result.failed
        ):
            try:
                copy.unlink(missing_ok=True)
            except OSError as error:
                base["note"] = f"the private copy {copy.name} could not be removed ({error})"
    return result, error_text


def _archive_extraction_folder(folder: Path, stamp: str) -> None:
    """Archive a prior extraction before new output can be mistaken for it."""
    if folder.is_dir():
        movable = [child for child in folder.iterdir() if child.name != ARCHIVE_DIR]
        if movable:
            target = folder / ARCHIVE_DIR / stamp
            target.mkdir(parents=True, exist_ok=True)
            for child in movable:
                child.replace(target / child.name)
    folder.mkdir(parents=True, exist_ok=True)


def _write_extraction_script(workspace, sim_id, name, text, *, stamp):
    """Archive a previous script before the workspace writes its replacement.

    The script lives in a folder of its own under ``scripts`` (``additional/<pproc>/``), which
    ``write_script`` refuses by design (a plain file name only), so it is written here and the
    name is checked to stay inside the simulation's scripts folder (F-727).
    """
    scripts = workspace.create_sim(sim_id) / "scripts"
    target = scripts / name
    if not target.resolve().is_relative_to(scripts.resolve()):
        raise WorkspaceError(f"script name {name!r} leaves the simulation's scripts folder.")
    target.parent.mkdir(parents=True, exist_ok=True)
    _archive_extraction_script(target, stamp)
    _textio.write_text(target, text)
    return target, file_sha256(target)


#: The suffix of a declared solver log, the log export kind's own.
_LOG_SUFFIX = next(suffix for kind, suffix, _, _ in EXPORT_KINDS if kind == "log")


def _the_extraction_s_log(
    base: dict[str, object], names: list[str], sim_dir: Path, printed: str
) -> list[str]:
    """Write an extraction's declared log from what the solver printed, or excuse it.

    On a machine that cannot export the log the extraction script carries no
    ``EXPORT_LOG``, as a run's does there. What the solver printed is written
    as the declared log; with nothing printed the log is not required, since
    the machine cannot write one. Either way the record's ``note`` says so.
    Returns the names the extraction is held to.
    """
    logs = [name for name in names if name.endswith(_LOG_SUFFIX) and not (sim_dir / name).is_file()]
    if not logs:
        return names
    if printed:
        _textio.write_text(sim_dir / logs[0], printed)
        said = (
            f"{PurePath(logs[0]).name} is the solver's captured standard output and error, "
            "written by this package: this machine's HPC profile states export_log = false, "
            "so the extraction script exports no log"
        )
    else:
        names = [name for name in names if name != logs[0]]
        said = (
            "no solver log: this machine's HPC profile states export_log = false, so the "
            "extraction script exports none, and the solver printed nothing to capture"
        )
    base["note"] = "; ".join(str(part) for part in (base.get("note"), said) if part)
    return names


def own_sections_layout(
    workspace: CampaignWorkspace, point: RunRecord
) -> list[dict[str, Any]] | None:
    """Return the sections the run cut, or None where nothing states them.

    The record's own layout where it has one. A record that predates the layout is
    answered by its script, as the sections post answers it: a script that is on disk,
    hashes as the record says and creates no surface section cut none, and the empty
    list is the whole layout. Anything else is unknown, and is never guessed.
    """
    if point.sections_layout is not None:
        return [dict(block) for block in point.sections_layout]
    if point.continues is not None or not point.script_path or not point.script_sha256:
        return None
    try:
        text = (workspace.sim_dir(point.sim_id) / point.script_path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if text_sha256(text) != point.script_sha256 or creates_surface_sections(text):
        return None
    return []


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def sections_numbering_refusal(
    own: list[dict[str, Any]] | None, script: Script, pproc: str
) -> str | None:
    """Say why the extraction's sections cannot be numbered after the run's, or None.

    Only an extraction that cuts sections needs the run's layout; one that cuts none is
    planned whatever the record states.
    """
    if not script.section_blocks:
        return None
    if own is None:
        stated = (
            "no sections layout, and its script is not on disk as recorded to prove it cut none"
        )
    elif any(not _is_integer(block.get("distribution")) for block in own):
        stated = "a section block with no integer distribution number"
    else:
        return None
    return (
        f"{pproc} cuts sections, and the record of this point states {stated}, so the "
        "extraction's distributions cannot be numbered after the run's own and its sections "
        "product would be refused afterwards. Run the point again to record its layout."
    )


def layout_of(
    point: RunRecord, script: Script, pproc: str, own: list[dict[str, Any]] | None = None
) -> tuple[list[dict[str, object]], int]:
    """Return the run's own section blocks, then the extraction's, numbered on after the run's.

    RPT-062: a reopened export carries the distributions the run created first
    and the new ones after them, identical to the ones a run would have cut.
    ``own`` is the run's blocks as :func:`own_sections_layout` read them.
    """
    if own is None:
        own = [dict(block) for block in (point.sections_layout or [])]
    leading = sum(int(count) for block in own if _is_integer(count := block.get("count")))
    offset = max(
        (int(number) for block in own if _is_integer(number := block.get("distribution"))),
        default=0,
    )
    added = []
    for block in script.section_blocks:
        entry = dict(block)
        number = entry.get("distribution")
        if _is_integer(number):
            entry["distribution"] = offset + number
        entry["pproc"] = pproc
        added.append(entry)
    return own + added, leading
