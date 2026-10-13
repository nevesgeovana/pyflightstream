"""The completion of one additional-post extraction, local or collected (G12).

An extraction reopens a recorded point's saved simulation and exports a
second pproc from it. It ends in one of two places: on this machine, right
after the solver returns (:func:`pyflightstream.run.matrix.run_additional_post`),
or on a cluster, when ``collect`` finds its outputs settled
(:mod:`pyflightstream.run.collect`). Both complete it here, by one rule
(PFS-2103.008): the local path judged by file existence alone and recorded
EXTRACTED over a translation problem the collected path refused.

Below both callers, so neither reaches up into the other for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from pyflightstream._digest import file_sha256, optional_file_sha256
from pyflightstream.results import translate_surface_exports
from pyflightstream.workspace import (
    AdditionalRecord,
    CampaignWorkspace,
    ExtractionStatus,
    WorkspaceError,
)
from pyflightstream.workspace.inputs import resolve_hpc_profile


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


def extraction_job_end(workspace, record, folder: Path) -> str | None:
    """Say how a submitted extraction's job is known to have ended, or None while it may run.

    The HPC profile's ``job_end_files`` all matching (FR-311), or the log
    the scheduler writes (``native_log``) being there, ends the job.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    point = record.point_name or ""
    job = (record.submission or {}).get("scheduler_id") or "its job"
    patterns = tuple(getattr(profile, "job_end_files", ()) or ())
    found: list[Path] = []
    for pattern in patterns:
        matched = [p for p in folder.glob(pattern.format(sim=record.sim_id, point=point))]
        if not any(path.is_file() for path in matched):
            found = []
            break
        found += [path for path in matched if path.is_file()]
    native = getattr(profile, "native_log", None)
    if not found and native:
        found = [
            path
            for path in folder.glob(str(native).format(sim=record.sim_id, point=point))
            if path.is_file()
        ]
    if not found:
        return None
    return (
        f"the extraction job {job} ended without its outputs: "
        f"{', '.join(sorted(p.name for p in found))} exist (the HPC profile's end of job)"
    )
