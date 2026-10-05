"""Private campaign product context, admission and native surface indexing.

The campaign facade supplies its mutable manifest and warning sinks. These
phases preserve record order and do not import the facade or launch a solver.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pyflightstream.post._stage as _stage
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs
from pyflightstream.post._settings_product import SETTINGS_KIND as SETTINGS_KIND
from pyflightstream.post._settings_product import write_settings_product as write_settings_product
from pyflightstream.post._stage import _PartialPost, _surface_export_skip
from pyflightstream.post.series import surface_export_metadata, translated_surface
from pyflightstream.results import FrozenSolve, UnjudgeableSolve
from pyflightstream.workspace import RunStatus, WorkspaceError, find_matrix

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.cases.pproc import PprocSpec
    from pyflightstream.post.superfile import SuperfileDraft
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


@dataclass(frozen=True)
class _CampaignProducts:
    """Inputs and ordered output sinks shared by the campaign writer phases."""

    workspace: CampaignWorkspace
    records: Sequence[RunRecord]
    by_sim: Mapping[str, list[RunRecord]]
    out: Path
    written: list[Path]
    products_index: dict[str, dict[str, object]]
    manifest: dict[str, object]
    skipped: dict[str, str]
    drafts: list[SuperfileDraft]
    rows_of_the_matrix: Mapping[str, MatrixRow]
    sweep_rows: Mapping[str, Mapping[str, object]] | None
    matrix_stem: str | None
    overwrite: bool
    archive: bool
    archive_stamp: datetime | None
    check_frozen: bool
    partial: _PartialPost | None
    #: The pproc each simulation followed (None where it could not be resolved),
    #: filled as the simulations are written, for the products that span them.
    pprocs: dict[str, PprocSpec | None] = field(default_factory=dict)


def _index_record_surfaces(
    ctx: _CampaignProducts,
    sim_id: str,
    record: RunRecord,
) -> FrozenSolve | None:
    # THE RECORD'S OWN RELEASE reads its outputs (G05): a 0.26.0 record's
    # `_vsec.vtk` is the surface export it was when written.
    """Index existing surface exports and record their missing or refused inputs."""
    output_kinds = classify_outputs(record.outputs, package_version=record.package_version)
    surface_freeze: FrozenSolve | None = None
    averages = (record.surface_time_averaging, record.surface_average_window)
    if any(window is not None for window in averages) and "log" in output_kinds:
        log_path = ctx.workspace.sim_dir(sim_id) / output_kinds["log"]
        if log_path is not None:
            surface_freeze = _stage.freeze_of_log(log_path)
    for kind, name in output_kinds.items():
        if kind not in ("tecplot", "vtk", "csv"):
            continue
        path = ctx.workspace.sim_dir(sim_id) / name
        relative = Path(os.path.relpath(path, ctx.out)).as_posix()
        if not path.is_file():
            ctx.skipped[relative] = f"the recorded {kind} surface export is missing: {path}"
            continue
        metadata = surface_export_metadata(record)
        reason = _surface_export_skip(
            metadata, surface_freeze, point=record.run_id, product=relative
        )
        if reason is not None:
            ctx.skipped[relative] = reason
            continue
        ctx.products_index[relative] = {
            "sim_id": sim_id,
            "pproc": record.pproc,
            "runs": [record.run_id],
            "format": kind,
            **metadata,
            **(translated_surface(record, path) if kind == "tecplot" else {}),
        }
    # G45: A TECPLOT THE RUN COULD NOT WRITE FROM ITS VTK is said, by the
    # sentence the run recorded, never left for a reader to notice.
    problems = [
        str(problem)
        for translation in record.surface_translations or []
        if isinstance(translation, Mapping)
        for problem in translation.get("problems") or []  # type: ignore[attr-defined]
    ]
    if problems:
        ctx.skipped[f"tecplot/{record.run_id}"] = "; ".join(problems)
    return surface_freeze


def _admit_campaign_records(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    *,
    sims: frozenset[str] | None,
    superseded: Mapping[str, str],
    check_frozen: bool,
    by_sim: dict[str, list[RunRecord]],
    skipped: dict[str, str],
) -> None:
    """Expand jobs in record order and admit each current point's products."""
    for record in records:
        if sims is not None and record.sim_id not in sims:
            continue  # FR-307: another simulation's records are not read.
        # FR-95. ONE JOB IS SEVERAL POINTS, so the record is expanded
        # before its status is read. A steady row is one job since 0.17.0
        # and its record carries every point of the sweep; unexpanded, the
        # product stage classified all of their outputs together, selected
        # ONE loads file, and wrote a three-point polar with one row. And
        # the aggregate status was the filter, so one failed point
        # excluded every successful point of the same job.
        #
        # `as_points()` exists for exactly this and was called by the
        # sweep table and the QA matrix and not here: a method built and
        # not wired, in the one place nobody looked. Found by the
        # independent Codex review of `main`, 2026-09-13 (GEO-047-C02).
        # A record that is one point returns itself, so nothing written
        # before 0.17.0 changes.
        for point_record in record.as_points():
            if point_record.run_id in superseded:
                continue
            frozen_failure = _record_has_frozen_failure(workspace, point_record)
            if (
                not check_frozen
                or frozen_failure
                or point_record.status
                in (
                    RunStatus.CONVERGED,
                    RunStatus.COMPLETED_MAX_ITER,
                )
            ):
                by_sim.setdefault(point_record.sim_id, []).append(point_record)
            else:
                skipped[f"runs/{point_record.run_id}"] = (
                    f"the recorded status is {point_record.status.value}; check_frozen=True "
                    "withholds this run's products. Collect complete outputs or run the "
                    "point again to settle its status."
                )


def _record_has_frozen_failure(workspace: CampaignWorkspace, point_record: RunRecord) -> bool:
    """Report a failed status and read whether its log proves a freeze."""
    frozen_failure = False
    if point_record.status not in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
        warn(
            f"point={point_record.run_id} product=available-exports: "
            f"the recorded status is {point_record.status.value}. "
            "Collect complete outputs or run the point again to settle its status.",
            PyflightstreamWarning,
            stacklevel=4,
        )
    # THE READING THAT ADMITS A POINT IS NOT THE READING THAT REFUSES
    # ITS AVERAGES, so it is not behind `check_frozen`: gating it
    # excluded every frozen failure by default, the opposite of
    # "nothing is refused unless asked" (the architect lens of the
    # closing round, 2026-09-22). This opens a failed point's log to
    # ask whether the failure was a freeze, and refuses nothing.
    if point_record.status is RunStatus.FAILED_DIVERGED:
        kinds = classify_outputs(point_record.outputs)
        log_name = kinds.get("log")
        log_path = workspace.sim_dir(point_record.sim_id) / log_name if log_name else None
        if log_path is not None and log_path.is_file():
            # A LOG THAT PROVES A FREEZE ADMITS ITS POINT, even when
            # another block of it could not be read: excluding every
            # UnjudgeableSolve removed the point's histories, instants
            # and earlier averages before their own checks could run,
            # against the preservation rule of the definitions page (the
            # independent review of GitHub main, 2026-09-22). A log that
            # proves NOTHING is not a freeze to post and stays out, as
            # it did before; it no longer raises here either.
            verdict = _stage.freeze_of_log(log_path)
            frozen_failure = verdict is not None and (
                not isinstance(verdict, UnjudgeableSolve) or verdict.frozen_from is not None
            )
    return frozen_failure


def _warn_unreadable_matrix(
    workspace: CampaignWorkspace,
    matrix_stem: str | None,
    rows_of_the_matrix: Mapping[str, MatrixRow],
) -> None:
    """Explain why post choices must fall back to the recorded matrix values."""
    if matrix_stem and not rows_of_the_matrix:
        # SAID, NOT SWALLOWED (PO-06). `matrix_rows` answers `{}` for a matrix that
        # is in neither home, for one it cannot parse, and (0.32.0, RST-1) for a
        # stem held in both homes with different bytes, and every post-only
        # choice then falls back to the run records in silence: an edited window
        # does nothing and the rotor tables, which need the row's reference, are
        # not written at all.
        try:
            found = find_matrix(workspace.root, matrix_stem)
            state = (
                "cannot be read"
                if found is not None
                else "is in neither the workspace root nor inputs/matrices/"
            )
        except WorkspaceError as two_homes:
            state = f"is refused: {two_homes}"
        warn(
            f"the matrix {matrix_stem}.fs {state}. Every post-only choice falls back to the run "
            "records, and the rotor tables, which take their geometry from the row's "
            "reference, are not written.",
            PyflightstreamWarning,
            stacklevel=3,
        )
