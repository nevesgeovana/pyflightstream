"""Which matrices and simulations ``pyfs-matrix post`` rebuilds (PFS-2185.18).

Private to :mod:`pyflightstream.run`. :func:`post_selection` decides, from the
rows' RUN flags and the provenance the last post wrote, what a post with no
option rebuilds, and :func:`named_selection` what ``--sims`` names (FR-307);
:mod:`pyflightstream.run.cli` calls them from ``post``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyflightstream._progress import say_summary
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    WorkspaceError,
    selected_sims,
)


def named_selection(
    args: argparse.Namespace,
    records: list[RunRecord],
    matrices: list[str | None],
    listed: list[str],
    sims_of: dict[str | None, list[str]],
) -> list[str | None]:
    """Return the matrices ``post --sims`` rebuilds, filling ``sims_of`` (FR-307).

    REFUSED BY NAME BEFORE ANY WORK (:class:`WorkspaceError`). With a matrix,
    every id must be a simulation of it; without one, each matrix holding a
    named simulation is posted limited to the ones it holds.
    """
    scoped = [record for record in records if record.matrix_stem in matrices]
    scope = f"of matrix {matrices[0]!r}" if args.matrix is not None else "in the manifest"
    chosen = selected_sims(scoped, listed, scope=scope)
    for matrix in matrices:
        held = {record.sim_id for record in scoped if record.matrix_stem == matrix}
        if chosen & held:
            sims_of[matrix] = sorted(chosen & held)
    return [matrix for matrix in matrices if matrix in sims_of]


def post_selection(
    args: argparse.Namespace,
    workspace: CampaignWorkspace,
    records: list[RunRecord],
    matrices: list[str | None],
    sims_of: dict[str | None, list[str]],
) -> list[str | None]:
    """Return the matrices ``post`` rebuilds, filling ``sims_of`` where it is partial.

    PFS-2185.18. A matrix's simulations whose rows state RUN = 0 keep their
    products; its RUN = 1 simulations are rebuilt by ``--archive`` or
    ``--force-overwrite``, and otherwise only those with a recorded point
    the last post did not see (no provenance document, or one written
    before the point ran again or its status changed). A selection that is every recorded
    simulation of the matrix is the whole post; a matrix with no RUN = 1
    row, or with nothing pending, is said and skipped. The additional post
    and ``--diagnostics`` take every matrix as it is.
    """
    if args.additional_pproc or getattr(args, "diagnostics", False):
        return matrices
    rebuild = bool(args.archive or args.force_overwrite)
    kept: list[str | None] = []
    for matrix in matrices:
        recorded = {record.sim_id for record in records if record.matrix_stem == matrix}
        active = _active_pols(workspace, matrix, args.matrix)
        if active is not None and not active:
            print(
                f"warning: matrix {matrix} has no row with RUN = 1, so nothing of it is "
                "posted; set RUN = 1 on the rows to post, or name them with --sims.",
                file=sys.stderr,
            )
            continue
        eligible = recorded if active is None else recorded & active
        chosen = eligible
        if not rebuild:
            chosen = _not_posted_yet(workspace, matrix, records, eligible)
        if not chosen:
            say_summary(
                f"matrix {matrix}: every RUN = 1 simulation is already posted; nothing to "
                "post. --sims <sim> posts one again, which is how changed IDENTIFIERS or a "
                "product just turned on reach it; --archive or --force-overwrite rebuilds them."
            )
            continue
        if chosen != eligible:
            say_summary(
                f"matrix {matrix}: {len(eligible - chosen)} simulation(s) already posted stay as "
                "they are. --sims <sim> posts one again, which is how changed IDENTIFIERS or a "
                "product just turned on reach it."
            )
        if chosen != recorded:
            sims_of[matrix] = sorted(chosen)
        kept.append(matrix)
    return kept


def _active_pols(
    workspace: CampaignWorkspace, matrix: str | None, named: str | None
) -> set[str] | None:
    """Return the POLs of the matrix's RUN = 1 rows, or None when its file cannot be read."""
    from pyflightstream.cases.matrix import read_matrix
    from pyflightstream.workspace import find_matrix

    if matrix is None:
        return None
    try:
        path = Path(named) if named and Path(named).is_file() else None
        path = path or find_matrix(workspace.root, matrix)
        if path is None:
            return None
        return {row.pol for row in read_matrix(path, active_only=True)}
    except (MatrixError, OSError, WorkspaceError):
        return None


def _not_posted_yet(
    workspace: CampaignWorkspace,
    matrix: str | None,
    records: list[RunRecord],
    sims: set[str],
) -> set[str]:
    """Return the simulations of ``sims`` holding a point the last post did not see.

    PFS-2185.18. A post writes one provenance document per recorded run,
    stating when the solver ended (``prov:endTime``), and names it in
    ``products.json``. A run that document names is posted; one it does not
    name, or whose document states another end (a point run again) or
    another status (``pyfs:status``: a record a later command re-classified,
    discarded or marked converged) than its record, is pending. A simulation
    whose products stand on disk with no ``products.json`` to read (brought by
    a sync) is posted, so a post on a
    machine without the exports never touches it. A submitted point waits
    for collect. ``products.json`` is read under the campaign lock, as the post
    reads it, so one cut off by a post's in-place rewrite is read from its
    staged copy (REL-R3-002).
    """
    import json

    import pyflightstream._textio as _textio

    out = workspace.products_dir(matrix)
    manifest = out / "products.json"
    try:
        if not manifest.is_file():
            raise FileNotFoundError(manifest)
        document = json.loads(_textio.locked_document_text(manifest, wait=_textio.LOCK_WAIT))
        provenance = document.get("provenance") or {}
    except (OSError, ValueError, AttributeError):
        on_disk = {sim for sim in sims if any((out / "polars").glob(f"P{sim}-*"))}
        return set(sims) - on_disk
    pending: set[str] = set()
    for record in records:
        if record.matrix_stem != matrix or record.sim_id not in sims or record.sim_id in pending:
            continue
        if record.status is RunStatus.SUBMITTED:
            continue
        relative = provenance.get(record.run_id)
        if not relative:
            pending.add(record.sim_id)
            continue
        try:
            text = (out / relative).read_text(encoding="utf-8")
        except OSError:
            continue  # named by the manifest and not on this machine: posted
        stale_end = record.finished_at is not None and record.finished_at not in text
        if stale_end or f'"pyfs:status": "{record.status.value}"' not in text:
            pending.add(record.sim_id)
    return pending
