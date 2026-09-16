"""Rename a workspace written under the 0.20.x point tag to the 0.21.0 point name.

A point had two names before this release: the TAG ``a+00.0_b+00.0_j+00.8``,
which ended every ``run_id`` and named the datapoint folder, and the file stem
``POLAR-<sim>_M14AL+000BE+000J+080``. 0.21.0 has one name, written by the row's
FLIGHT_CONDITION cell, and everything a workspace holds is named by it. A
workspace already on disk therefore cannot be read by this release: its records
carry no ``point_name``, and `collect` and the post-processing stages refuse
them by name rather than recompute one and file a point's evidence where no
record of it points.

This module is the one command that moves such a workspace, and it moves ALL of
it: the datapoint folders, the scripts, the collected files, the manifest and
the plan. It prints every change it makes, and a second run makes none.

A RECORD IS NOT A POINT, and this is the shape the first writing got wrong: a
steady row is ONE job for every point of its sweep, so one record carries a
folder per point under ``points_ran``. Every one of them is renamed, and the
job's own script is renamed by the sweep name beside them.

THE OLD STEMS ARE READ, NEVER RECOMPUTED. A workspace may have been planned
under any ``--point-name`` template, so the names on disk are the ones the
record states: the script stem from ``script_path``, and each point's stem from
the output names that point recorded.

WHAT IT REFUSES, before it touches anything (a half-renamed workspace is worse
than an unrenamed one):

* a record whose simulation has no row in the matrix, because the new name is
  written BY the row and there is nothing to write it from;
* a record whose recorded point is not one of the row's points, which is a
  matrix edited since the run: renaming under the edited row would file old
  evidence under a name that means something else;
* two points whose new names would collide;
* a SUBMITTED record whose folder would move, because the scheduler writes into
  the folder the descriptor named and this command cannot reach the job.

WHY IT REWRITES ``plan.json`` RATHER THAN PLANNING AGAIN. Planning needs the
recipes, the run types and a FlightStream version, and this command needs none
of them: it reads a matrix and a manifest. Demanding them would make renaming a
recorded workspace harder than running it. The plan's own ``matrix_sha256``
still holds, because the matrix file is not touched.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
    point_name,
    point_tag,
    sweep_name,
)
from pyflightstream.cases.matrix import MatrixError, MatrixRow, read_matrix
from pyflightstream.workspace import CampaignWorkspace, RunStatus, WorkspaceError
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR,
    ARCHIVE_STAMP,
    DATAPOINT_PREFIX,
    PointName,
    datapoint_dir_name,
    point_file_stem,
    sweep_file_stem,
)

__all__ = [
    "RenameChange",
    "RenameReport",
    "rename_workspace",
]

#: The last segment of a job record's ``run_id``: a steady row is ONE job for
#: all its points, and that token is not a point name and is not renamed.
SWEEP_TOKEN = "sweep"

#: Where a datapoint folder sits under a simulation.
DATAPOINTS_DIR = "datapoints"

#: The record fields that are NOT rewritten. Everything else is, because a
#: field left out is a name that no longer resolves and the first writing of
#: this listed the fields to rewrite instead: the executor's recorded argv
#: carried a stale stem straight past it. These four are identities and
#: measurements, and a name that occurs in them occurs as itself.
KEPT_FIELDS = frozenset(
    {
        "sim_id",
        "matrix_stem",
        "point",
        "point_name_template",
    }
)


def _usable(pairs) -> tuple[tuple[str, str], ...]:
    """Return the substitutions that say something: non-empty, and a real change."""
    seen: dict[str, str] = {}
    for before, after in pairs:
        if before and before != after:
            seen[before] = after
    return tuple(seen.items())


@dataclass(frozen=True)
class _PointMove:
    """One point of one record: what it is called now and what it will be called."""

    old_tag: str
    new_name: str
    old_stem: str
    new_stem: str

    @property
    def moves(self) -> bool:
        """Say whether this point is named differently under 0.21.0."""
        return self.old_tag != self.new_name or (
            bool(self.old_stem) and self.old_stem != self.new_stem
        )

    @property
    def folder(self) -> tuple[str, str]:
        """Return this point's datapoint folder, before and after."""
        return (f"{DATAPOINT_PREFIX}{self.old_tag}", f"{DATAPOINT_PREFIX}{self.new_name}")


@dataclass(frozen=True)
class _Plan:
    """One record and the names it takes: read in the first pass, written in the second."""

    record: dict[str, Any]
    points: tuple[_PointMove, ...]
    script: tuple[str, str]
    new_name: str
    new_sweep: str

    @property
    def moves(self) -> bool:
        """Say whether anything of this record is named differently now."""
        return self.script[0] != self.script[1] or any(point.moves for point in self.points)

    def identity_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return the substitutions of an IDENTITY: a tag becomes a point name.

        The `run_id`, the tags of `points_ran` and the keys a submission files
        its points under. None of them is a file name.
        """
        return _usable((point.old_tag, point.new_name) for point in self.points)

    def path_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return the substitutions of a PATH: a folder and a file stem.

        THE FOLDER FIRST, because a path holds both and the folder carries the
        tag inside it (`datapoints/DP-<tag>/<stem>.txt`).

        WHY THE TWO KINDS ARE SEPARATE, which one ordered list could not do: a
        workspace planned under the library default rendered `{point}` as the
        TAG, so there the stem and the tag are the same string. One list then
        holds two rules with one left-hand side and the winner is
        set-iteration order -- measured by the qa lens, 2026-09-16: the
        `run_id` came out holding the file stem while `point_name` beside it
        held the name. A field is an identity or a path, and that is knowable.
        """
        pairs = []
        for point in self.points:
            pairs.append(point.folder)
            pairs.append((point.old_stem, point.new_stem))
        pairs.append(self.script)
        return _usable(pairs)


@dataclass(frozen=True)
class RenameChange:
    """One change this command made or would make: what kind, from what, to what."""

    kind: str
    before: str
    after: str

    def line(self) -> str:
        """Return the one line this change prints."""
        return f"{self.kind}: {self.before} -> {self.after}"


@dataclass
class RenameReport:
    """What one run of the command found, refused and changed."""

    changes: list[RenameChange] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    records: int = 0
    renamed_records: int = 0
    applied: bool = False

    def lines(self) -> list[str]:
        """Return one line per change, in the order they were made."""
        return [change.line() for change in self.changes]

    def summary(self) -> str:
        """Return the closing line: how much was read, moved and changed."""
        verb = "renamed" if self.applied else "would rename"
        return (
            f"{self.records} record(s) read, {verb} {self.renamed_records}, "
            f"{len(self.changes)} change(s)"
        )


def _case_for_naming(row: MatrixRow) -> SimCase:
    """Build the case the NAMING functions read, and nothing more.

    A rename needs the row's declared condition, its order, its Mach number
    and its sweep; it needs no recipe, no geometry, no artifact and no
    FlightStream version. Building the full campaign would demand every one of
    them from a user who is renaming records that already ran.
    """
    return SimCase(
        sim_id=row.pol,
        aircraft=row.aircraft,
        description=row.description,
        flight_condition=dict(row.flight_condition),
        condition_order=list(row.condition_order),
        mach=row.flight_condition.get("MACH"),
        sweep=row.sweep,
        recipe=row.workflow or "rename",
        variables=dict(row.variables),
        motions=[dict(record) for record in row.motions],
    )


def _rows_of(root: Path, stem: str | None) -> dict[str, MatrixRow]:
    """Return the rows of one matrix of the workspace, keyed by POL."""
    if not stem:
        return {}
    path = root / f"{stem}.fs"
    if not path.is_file():
        raise WorkspaceError(
            f"the manifest records runs of the matrix {stem!r} and the workspace holds no "
            f"{path.name} at its root, so the rows that write the new names cannot be read. "
            "Put the matrix back beside runs.json and run this again."
        )
    try:
        # EVERY row, including the ones the RUN column hides: a hidden row may
        # still have records from before it was hidden, and they are renamed.
        return {row.pol: row for row in read_matrix(path, active_only=False)}
    except MatrixError as error:
        raise WorkspaceError(f"the matrix {path.name} cannot be read: {error}") from error


def _stem_of(names: Sequence[str]) -> str:
    """Return the file stem the given names of one point share, or "" if they share none.

    Every export of a point is ``<stem>`` plus a suffix that begins with ``.``
    or ``_`` (``.txt``, ``.dat``, ``_cp.txt``, ``_log.txt``), so the stem is
    the longest common prefix that every name continues with one of those two
    characters. A single file therefore yields its own name without its
    extension, which is the same string.
    """
    if not names:
        return ""
    if len(names) == 1:
        return Path(names[0]).stem
    shortest = min(names, key=len)
    for size in range(len(shortest), 0, -1):
        head = shortest[:size]
        if all(
            name.startswith(head) and (len(name) > size and name[size] in "._") for name in names
        ):
            return head
    return ""


def _recorded_points(record: Mapping[str, Any]) -> list[tuple[str, dict[str, float], list[str]]]:
    """Return (tag, point, output names) per point of a record, from the record alone."""
    ran = record.get("points_ran") or []
    if ran:
        return [
            (
                str(entry.get("tag", "")),
                dict(entry.get("point") or {}),
                [Path(str(name)).name for name in (entry.get("outputs") or [])],
            )
            for entry in ran
            if isinstance(entry, Mapping)
        ]
    tag = str(record.get("run_id", "")).rsplit("/", 1)[-1]
    outputs = [Path(str(name)).name for name in (record.get("outputs") or [])]
    return [(tag, dict(record.get("point") or {}), outputs)]


def _declared_by_point(record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return the outputs a SUBMITTED record declared per point, keyed by tag."""
    submission = record.get("submission")
    if not isinstance(submission, Mapping):
        return {}
    declared = submission.get("declared_by_point")
    if not isinstance(declared, Mapping):
        return {}
    return {
        str(tag): [Path(str(name)).name for name in names]
        for tag, names in declared.items()
        if isinstance(names, list)
    }


#: The record fields that are IDENTITIES rather than paths: a tag in them is a
#: point's name and never a file. Everything else that carries a name carries it
#: as part of a path.
IDENTITY_FIELDS = frozenset({"run_id", "job_id", "point_name", "sweep_name"})

#: Inside the submission block, the two mappings keyed BY POINT: their keys are
#: identities and their values are declared output paths.
SUBMISSION_BY_POINT = ("declared_by_point", "points_by_tag")


def _rewrite_field(name: str, value: Any, plan: _Plan) -> Any:
    """Rewrite one record field, as the kind of thing that field holds.

    An identity takes the point NAME; a path takes the datapoint folder and the
    file stem. `points_ran` and `submission` hold both kinds and are walked
    entry by entry rather than substituted whole.
    """
    if name in IDENTITY_FIELDS:
        return _substitute(value, plan.identity_pairs())
    if name == "points_ran" and isinstance(value, list):
        return [_rewrite_point_ran(entry, plan) for entry in value]
    if name == "submission" and isinstance(value, Mapping):
        return _rewrite_submission(value, plan)
    return _substitute(value, plan.path_pairs())


def _rewrite_point_ran(entry: Any, plan: _Plan) -> Any:
    """Rewrite one entry of ``points_ran``: its tag is an identity, its outputs are paths."""
    if not isinstance(entry, Mapping):
        return entry
    rewritten = dict(entry)
    if "tag" in rewritten:
        rewritten["tag"] = _substitute(rewritten["tag"], plan.identity_pairs())
    for key, item in rewritten.items():
        if key != "tag":
            rewritten[key] = _substitute(item, plan.path_pairs())
    return rewritten


def _rewrite_submission(block: Mapping[str, Any], plan: _Plan) -> dict[str, Any]:
    """Rewrite a submission block: two mappings are keyed by point, the rest are paths."""
    rewritten: dict[str, Any] = {}
    for key, value in block.items():
        if key in SUBMISSION_BY_POINT and isinstance(value, Mapping):
            rewritten[key] = {
                _substitute(point, plan.identity_pairs()): _substitute(item, plan.path_pairs())
                for point, item in value.items()
            }
        else:
            rewritten[key] = _substitute(value, plan.path_pairs())
    return rewritten


def _substitute(value: Any, pairs: tuple[tuple[str, str], ...]) -> Any:
    """Rewrite every string under ``value``, longest pattern first."""
    if isinstance(value, str):
        for before, after in pairs:
            value = value.replace(before, after)
        return value
    if isinstance(value, list):
        return [_substitute(item, pairs) for item in value]
    if isinstance(value, dict):
        return {_substitute(key, pairs): _substitute(item, pairs) for key, item in value.items()}
    return value


def _point_of_row(row: MatrixRow, point: Mapping[str, float]) -> bool:
    """Say whether the row still holds the point this record ran."""
    if not point:
        return True
    try:
        tag = point_tag(dict(point))
        candidates = {point_tag(dict(candidate)) for candidate in row.sweep.points()}
    except CampaignConfigError:
        return True
    return tag in candidates


def _archive_manifest(workspace: CampaignWorkspace) -> RenameChange:
    """Copy runs.json under ``archive/`` before it is rewritten."""
    stamp = datetime.now(UTC).strftime(ARCHIVE_STAMP)
    archive = workspace.root / ARCHIVE_DIR
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / f"runs-{stamp}.json"
    shutil.copy2(workspace.manifest_path, target)
    return RenameChange(
        "manifest archived",
        workspace.manifest_path.name,
        target.relative_to(workspace.root).as_posix(),
    )


def _folder_of_the_old_tag(tag: str) -> str:
    """Return the datapoint folder of a 0.20.x tag, which is not a PointName.

    Named rather than concatenated inline, so the one place this package builds
    a datapoint folder WITHOUT the checked type says in its name that it is
    reading the older scheme.
    """
    return f"{DATAPOINT_PREFIX}{tag}"


def _rename_path(before: Path, after: Path) -> None:
    """Move one path, refusing to write over something already there."""
    if after.exists():
        raise WorkspaceError(
            f"{after} is already there, so renaming {before.name} onto it would destroy it. "
            "Nothing else was changed; move it aside and run this again."
        )
    after.parent.mkdir(parents=True, exist_ok=True)
    before.rename(after)


def _files_to_move(folder: Path, old_stem: str, new_stem: str) -> list[tuple[str, str]]:
    """Return the file names inside one datapoint folder that the new stem renames."""
    if not old_stem or old_stem == new_stem or not folder.is_dir():
        return []
    return [
        (path.name, new_stem + path.name[len(old_stem) :])
        for path in sorted(folder.iterdir())
        if path.is_file() and path.name.startswith(old_stem)
    ]


def _plan_record(
    record: Mapping[str, Any],
    row: MatrixRow,
    report: RenameReport,
    claimed: dict[tuple[str, str], str],
) -> _Plan | None:
    """Work out what one record takes, or register the refusal that stops it."""
    sim_id = str(record.get("sim_id", ""))
    run_id = str(record.get("run_id", ""))
    case = _case_for_naming(row)
    declared = _declared_by_point(record)
    moves: list[_PointMove] = []
    for tag, point, outputs in _recorded_points(record):
        if not _point_of_row(row, point):
            report.refusals.append(
                f"record {run_id!r}: the point it ran, {point}, is not a point of row "
                f"{sim_id} as the matrix reads today, so the matrix changed since the run. "
                "Rename against the matrix that ran it, or move that record aside."
            )
            return None
        try:
            new_name = point_name(case, point)
        except CampaignConfigError as error:
            report.refusals.append(f"record {run_id!r}: {error}")
            return None
        key = (sim_id, new_name)
        if key in claimed and claimed[key] != run_id:
            report.refusals.append(
                f"records {claimed[key]!r} and {run_id!r} would both name a point "
                f"{new_name!r} in simulation {sim_id}, and two points cannot share one folder."
            )
            return None
        claimed[key] = run_id
        moves.append(
            _PointMove(
                old_tag=tag,
                new_name=new_name,
                old_stem=_stem_of(outputs or declared.get(tag, [])),
                new_stem=point_file_stem(sim_id, PointName(new_name)),
            )
        )
    new_sweep = sweep_name(case)
    tail = str(record.get("run_id", "")).rsplit("/", 1)[-1]
    is_job = tail == SWEEP_TOKEN
    script = str(record.get("script_path") or "")
    old_script_stem = Path(script).stem if script else ""
    new_script_stem = (
        sweep_file_stem(sim_id, new_sweep)
        if is_job
        else point_file_stem(sim_id, PointName(moves[0].new_name))
    )
    plan = _Plan(
        record=dict(record),
        points=tuple(moves),
        script=(old_script_stem, new_script_stem if old_script_stem else ""),
        new_name=new_sweep if is_job else moves[0].new_name,
        new_sweep=new_sweep,
    )
    if plan.moves and str(record.get("status")) == str(RunStatus.SUBMITTED):
        report.refusals.append(
            f"record {run_id!r} is in a scheduler's queue and its folder would move to "
            f"{DATAPOINT_PREFIX}{plan.new_name}. The job writes where its descriptor said, "
            "which this "
            "command cannot reach: collect it (pyfs-matrix collect) and rename afterwards."
        )
        return None
    return plan


def rename_workspace(
    workspace: CampaignWorkspace,
    *,
    apply: bool = True,
) -> RenameReport:
    """Rename a 0.20.x workspace to the 0.21.0 names, or say what would move.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign root, holding ``runs.json`` and the matrices beside it.
    apply : bool
        Write the changes. False reports what would move and touches nothing.

    Returns
    -------
    RenameReport
        Every change, in the order it was made, and the summary line.

    Raises
    ------
    WorkspaceError
        If anything cannot be mapped. Nothing has been written when it is
        raised: every refusal is found in the reading pass.
    """
    report = RenameReport(applied=apply)
    if not workspace.manifest_path.is_file():
        raise WorkspaceError(
            f"{workspace.manifest_path} is not there, so this is not a campaign workspace to "
            "rename. Name the root that holds runs.json as workspace (CLI: --workspace)."
        )
    raw = workspace.read_raw_manifest()
    report.records = len(raw)
    rows_by_stem: dict[str | None, dict[str, MatrixRow]] = {}
    plans: list[_Plan] = []
    claimed: dict[tuple[str, str], str] = {}

    for record in raw:
        stem = record.get("matrix_stem")
        if stem not in rows_by_stem:
            rows_by_stem[stem] = _rows_of(workspace.root, stem)
        sim_id = str(record.get("sim_id", ""))
        row = rows_by_stem[stem].get(sim_id)
        if row is None:
            report.refusals.append(
                f"record {str(record.get('run_id', ''))!r}: simulation {sim_id} has no row in "
                f"{stem or 'the matrix'}, and the new name is written by the row."
            )
            continue
        plan = _plan_record(record, row, report, claimed)
        if plan is not None:
            plans.append(plan)

    if report.refusals:
        raise WorkspaceError(
            "this workspace cannot be renamed as it stands, and nothing was changed:\n  "
            + "\n  ".join(report.refusals)
        )

    rewritten: list[dict[str, Any]] = []
    pending: list[tuple[Path, Path]] = []
    for plan in plans:
        entry = dict(plan.record)
        sim = workspace.sim_dir(str(plan.record.get("sim_id", "")))
        if plan.moves:
            report.renamed_records += 1
        for move in plan.points:
            folder = sim / DATAPOINTS_DIR / _folder_of_the_old_tag(move.old_tag)
            # THE NEW FOLDER GOES THROUGH THE CHECKED RENDERER, which refuses a
            # name that already carries the prefix or is not portable. The first
            # writing concatenated, so the one command whose job is moving
            # folders was the one place that gate did not fire (the architecture
            # lens, 2026-09-16). The OLD side cannot: a 0.20 tag is not a
            # PointName, which is why it has a named helper of its own.
            target = sim / DATAPOINTS_DIR / datapoint_dir_name(PointName(move.new_name))
            # THE FILES ARE READ BEFORE THE FOLDER MOVES and moved after it, so
            # both halves of each pair name the NEW folder: a folder rename
            # carries its contents, and a file move naming the old folder would
            # then find nothing there.
            inside = folder if folder.is_dir() else target
            files = _files_to_move(inside, move.old_stem, move.new_stem)
            if folder.is_dir() and folder != target:
                pending.append((folder, target))
                report.changes.append(RenameChange("datapoint", folder.name, target.name))
            for before, after in files:
                pending.append((target / before, target / after))
                report.changes.append(RenameChange("file", before, after))
        old_stem, new_stem = plan.script
        if old_stem and old_stem != new_stem:
            before_path = sim / str(plan.record.get("script_path"))
            after_path = before_path.with_name(f"{new_stem}{before_path.suffix}")
            if before_path.is_file():
                pending.append((before_path, after_path))
                report.changes.append(RenameChange("script", before_path.name, after_path.name))
        for name, value in list(entry.items()):
            if name in KEPT_FIELDS:
                continue
            entry[name] = _rewrite_field(name, value, plan)
        entry["point_name"] = plan.new_name
        entry["sweep_name"] = plan.new_sweep
        rewritten.append(entry)

    # THE REHEARSAL REPORTS WHAT THE RUN WOULD DO, all of it. The first writing
    # returned here, so a dry run named no manifest archive and no plan rewrite
    # -- the two changes OUTSIDE the datapoint folders, which are the ones a
    # user most wants warned about -- and its change count was lower than the
    # apply run's for the same workspace (the interface lens, 2026-09-16).
    moves_something = bool(report.changes) or rewritten != raw
    if not apply:
        if moves_something:
            report.changes.insert(
                0,
                RenameChange(
                    "manifest would be archived",
                    workspace.manifest_path.name,
                    f"{ARCHIVE_DIR}/runs-<stamp>.json",
                ),
            )
        report.changes.extend(_plan_changes(workspace, plans, applied=False))
        return report

    if moves_something:
        report.changes.insert(0, _archive_manifest(workspace))
    # THE FOLDERS MOVE BEFORE THE MANIFEST IS REWRITTEN, so a failure leaves a
    # manifest that still describes the tree as it is rather than one that
    # describes a tree nobody has.
    for before_path, after_path in pending:
        if before_path.exists():
            _rename_path(before_path, after_path)
    if rewritten != raw:
        workspace.manifest_path.write_text(json.dumps(rewritten, indent=2) + "\n", encoding="utf-8")
    report.changes.extend(_plan_changes(workspace, plans, applied=True))
    return report


def _plan_changes(
    workspace: CampaignWorkspace,
    plans: Iterable[_Plan],
    *,
    applied: bool,
) -> list[RenameChange]:
    """Rewrite every plan.json of the workspace, or say which ones would change.

    The plan's points carry the run ids and script names the records do, so a
    plan left alone would name folders that are no longer there and a resume
    would rehearse against them.

    ``applied`` is False for the rehearsal, which reads the same files, decides
    the same way and writes nothing.
    """
    identity: list[tuple[str, str]] = []
    paths: list[tuple[str, str]] = []
    stems: set[str | None] = set()
    for plan in plans:
        identity.extend(plan.identity_pairs())
        paths.extend(plan.path_pairs())
        stems.add(plan.record.get("matrix_stem"))
    changes: list[RenameChange] = []
    for stem in stems:
        plan_file = workspace.plan_dir(stem) / "plan.json"
        if not plan_file.is_file():
            continue
        before = plan_file.read_text(encoding="utf-8")
        # THE PLAN CARRIES BOTH KINDS: `run_id` is an identity and
        # `script_name` is a path, so each entry is rewritten the way the
        # record's own fields are.
        payload = json.loads(before)
        for entry in payload.get("points", []) if isinstance(payload, dict) else []:
            if not isinstance(entry, dict):
                continue
            for key, value in entry.items():
                entry[key] = _substitute(
                    value, tuple(identity) if key in IDENTITY_FIELDS else tuple(paths)
                )
        after = json.dumps(payload, indent=2) + "\n"
        if after != before:
            if applied:
                plan_file.write_text(after, encoding="utf-8")
            changes.append(
                RenameChange(
                    "plan" if applied else "plan would be",
                    plan_file.relative_to(workspace.root).as_posix(),
                    "rewritten under the new names",
                )
            )
    return changes
