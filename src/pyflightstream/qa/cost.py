"""Wall-time cost of recorded runs, gathered so two builds can be compared.

Pipeline role: a READER over campaign manifests, at the qa end of the
pipeline. It executes nothing, opens no report and needs no licensed
seat: its whole input is the ``runs.json`` that FR-19 already requires
every campaign to write, and its output is a table in which the same
sweep points measured on two solver builds sit side by side.

The gap it closes. FR-19 has recorded ``wall_time_s`` per run since the
v0.3 line, beside the requested version, the reported version, the
vendor build string and the sha256 of the executable that actually ran.
Nothing read those five fields together, so the question "did the new
build get slower" had a complete answer sitting in every campaign root
and no way to ask it.

Three decisions this module makes, each of which could reasonably have
gone the other way and none of which is safe to leave implicit.

**A column is a (build, executable) PAIR.** ``fs_build`` is what the
vendor prints and ``fs_exe_sha256`` is what ran. A hotfix rebuilt from
the same source tag prints the same build string and is a different
program, so keying on the build string alone would average two
executables into one column and hide the regression this view exists to
show. Both fields are columns of :func:`cost_rows`, and the pivot's
column label carries the build string plus the first twelve characters
of the hash.

**Absence is ``None``, never ``0.0`` and never ``math.nan``.** A run
whose record carries no wall time is not a run that took no time.
``results.tables`` maps the same missing field to ``math.nan`` and is
right to, because its substrate is a numeric frame in which every cell
must be a number; this module's substrate is plain Python, its output is
evidence rather than arithmetic, and a caller who sums a column here
must be stopped by a ``TypeError`` rather than quietly handed a total
that is short by however many runs were never timed.

**A comparison sums only the work both builds did.** Points timed on one
build alone are reported as unpaired and kept out of both totals: a
total over two different sets of points is not a comparison, and the
direction of the error is the dangerous one, since the build that ran
MORE points looks slower for having done more.

Units and frames: every duration in this module is a wall-clock
duration in SECONDS, measured around the solver process by the run layer
(``run/__init__.py``) with ``time.perf_counter``. It is not CPU time,
it includes process start-up and file IO, and it is therefore only
comparable between runs taken on the same machine under a comparable
load. No reference frame applies; nothing here is a physical quantity.

Examples
--------
>>> from pyflightstream.qa.cost import cost_view
>>> from pyflightstream.workspace import RunRecord, RunStatus
>>> def timed(run_id, sim_id, alpha_deg, build, sha, seconds):
...     return RunRecord(
...         run_id=run_id,
...         sim_id=sim_id,
...         point={"alpha_deg": alpha_deg},
...         fs_version_requested="26.120",
...         fs_build=build,
...         fs_exe_sha256=sha,
...         package_version="0.8.0",
...         script_sha256="0" * 64,
...         raw_flag=False,
...         status=RunStatus.CONVERGED,
...         wall_time_s=seconds,
...     )
>>> view = cost_view(
...     [
...         timed("r1", "SIM-01", 2.0, "2122026", "a" * 64, 41.0),
...         timed("r2", "SIM-01", 2.0, "2900000", "b" * 64, 63.5),
...     ]
... )
>>> [build.label for build in view.builds]
['2122026@aaaaaaaaaaaa', '2900000@bbbbbbbbbbbb']
>>> comparison = view.compare(*view.builds)
>>> round(comparison.ratio, 3)
1.549
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

__all__ = [
    "ABSENT",
    "BuildComparison",
    "BuildKey",
    "COST_ROW_COLUMNS",
    "CostCell",
    "CostView",
    "NOT_RUN",
    "PointCost",
    "PointKey",
    "cost_rows",
    "cost_view",
]

#: Placeholder for a build field the manifest does not carry. Manifests
#: written before the build fields existed are still evidence, and a
#: column labelled as unrecorded is honest where a guessed one is not.
UNRECORDED_BUILD = "unrecorded-build"
UNRECORDED_EXE = "unrecorded-exe"

#: Characters of ``fs_exe_sha256`` a column label carries. The label is
#: for reading; :attr:`BuildKey.fs_exe_sha256` and the long-form table
#: carry the whole hash, and a label that would collide is refused
#: rather than truncated further (see :class:`CostView`).
LABEL_SHA_CHARS = 12

#: How a renderer names the two kinds of empty cell. They are different
#: facts: ``ABSENT`` means runs are recorded there and none carries a
#: wall time, ``NOT_RUN`` means that point was never run on that build.
ABSENT = "absent"
NOT_RUN = "not-run"

#: Column labels of the long-form table, which is one row per RUN.
#: Order is presentation; a reader resolves a column by its label
#: (NFR-19).
COST_ROW_COLUMNS = (
    "run_id",
    "sim_id",
    "point",
    "fs_build",
    "fs_exe_sha256",
    "status",
    "wall_time_s",
)

#: Fixed identity columns of the pivot; every other column of a pivot
#: row is a build label. A build label always contains ``@``, which
#: neither of these does, so a build column can never shadow one.
COST_VIEW_IDENTITY_COLUMNS = ("sim_id", "point")

#: Statuses whose wall time is time to a FAILURE. Derived from the enum
#: rather than listed, so a status added to
#: :class:`pyflightstream.workspace.RunStatus` under the FAILED_ prefix
#: is counted the day it arrives; one added under any other name is not,
#: which is why ``tests/test_qa_cost.py`` pins the complement.
_FAILED_STATUSES = frozenset(status for status in RunStatus if status.name.startswith("FAILED"))

#: Rendered when a point carries no sweep axes at all (a single-point
#: simulation). An empty string would render as a blank column and read
#: as missing data.
NO_AXES = "(no axes)"


@dataclass(frozen=True)
class BuildKey:
    """One column of the cost view: the solver that produced the times.

    Attributes
    ----------
    fs_build : str or None
        Vendor build string as the solver reported it, from
        :attr:`pyflightstream.workspace.RunRecord.fs_build`. ``None``
        for a manifest written before the field existed.
    fs_exe_sha256 : str or None
        Hex sha256 of the executable that ran, from
        :attr:`pyflightstream.workspace.RunRecord.fs_exe_sha256`.
        ``None`` for a manifest that did not record it.
    """

    fs_build: str | None
    fs_exe_sha256: str | None

    @property
    def label(self) -> str:
        """Reading name of the column, ``<build>@<first 12 of sha256>``.

        Both halves are present even when one field is missing, so a
        label is always shaped the same way and a reader can tell an
        unrecorded field from a recorded one.
        """
        build = self.fs_build or UNRECORDED_BUILD
        exe = self.fs_exe_sha256[:LABEL_SHA_CHARS] if self.fs_exe_sha256 else UNRECORDED_EXE
        return f"{build}@{exe}"


@dataclass(frozen=True)
class PointKey:
    """One row of the cost view: a simulation and the point it ran.

    The point is IDENTIFIED here, not analysed. Its axes stay a sorted
    tuple rather than becoming columns, which is why this table has no
    axis-collides-with-a-fixed-column failure mode;
    :func:`pyflightstream.results.tables.sweep_table` is where an axis
    becomes a column and where that collision is checked.

    Attributes
    ----------
    sim_id : str
        Simulation identifier from the manifest record.
    axes : tuple of (str, float)
        Sweep point as (axis name, value) pairs sorted by name. Values
        are compared exactly, which is what makes two runs of the same
        matrix line land in the same row; units are the axis's own, as
        the case matrix declared them.
    """

    sim_id: str
    axes: tuple[tuple[str, float], ...]

    @property
    def label(self) -> str:
        """Reading name of the point, ``alpha_deg=2.0, beta_deg=0.0``.

        The value is rendered with ``repr``, which round-trips a float
        exactly, rather than with a fixed precision. This label is an
        IDENTITY and two points a hair apart are two rows; ``:g`` would
        have printed six significant digits and given them one name.
        """
        if not self.axes:
            return NO_AXES
        return ", ".join(f"{name}={value!r}" for name, value in self.axes)

    @property
    def point(self) -> dict[str, float]:
        """The sweep point as the manifest carried it."""
        return dict(self.axes)


@dataclass(frozen=True)
class CostCell:
    """Every run recorded for one (point, build), and what they cost.

    Attributes
    ----------
    samples : tuple of float
        Wall-clock seconds of each run there that recorded one, in
        manifest order. A re-run adds a sample rather than replacing
        one: a manifest is evidence and the second reading does not
        delete the first.
    run_count : int
        Runs recorded for this (point, build), timed or not.
    failed_count : int
        How many of them ended in a FAILED status. Time to a failure is
        time, and it is not the time to an answer; the runs are kept
        and counted rather than dropped, because a silent drop is a
        quieter lie than a reported one.
    """

    samples: tuple[float, ...] = ()
    run_count: int = 0
    failed_count: int = 0

    @property
    def wall_time_s(self) -> float | None:
        """Mean of the recorded samples in seconds, or ``None``.

        ``None`` when nothing there was timed. It is deliberately not
        ``0.0`` and deliberately not ``math.nan``: see this module's
        top docstring.
        """
        return fmean(self.samples) if self.samples else None

    @property
    def absent(self) -> bool:
        """True when no run there carries a wall time."""
        return not self.samples

    @property
    def recorded(self) -> bool:
        """True when at least one run is recorded there, timed or not."""
        return self.run_count > 0


_EMPTY_CELL = CostCell()


@dataclass(frozen=True)
class PointCost:
    """One point measured on both builds of a comparison.

    Attributes
    ----------
    point : PointKey
        The simulation and sweep point.
    baseline_s, candidate_s : float
        Mean wall-clock seconds on each build.
    """

    point: PointKey
    baseline_s: float
    candidate_s: float

    @property
    def ratio(self) -> float | None:
        """``candidate_s / baseline_s``; above 1 means slower.

        ``None`` when the baseline reading is zero, which no real
        solver run produces and a hand-built record can.
        """
        if self.baseline_s == 0:
            return None
        return self.candidate_s / self.baseline_s


@dataclass(frozen=True)
class BuildComparison:
    """Two builds over the points BOTH of them timed.

    Attributes
    ----------
    baseline, candidate : BuildKey
        The two columns compared, in that order.
    paired : tuple of PointCost
        Points timed on both builds, in the view's row order.
    unpaired : tuple of PointKey
        Points recorded on at least one of the two builds and timed on
        fewer than both. They are named rather than silently dropped,
        because the totals below exclude them and a reader has to know
        how much of the campaign the comparison did not cover.
    """

    baseline: BuildKey
    candidate: BuildKey
    paired: tuple[PointCost, ...] = ()
    unpaired: tuple[PointKey, ...] = ()

    @property
    def baseline_total_s(self) -> float:
        """Seconds the baseline spent on the paired points."""
        return sum(pair.baseline_s for pair in self.paired)

    @property
    def candidate_total_s(self) -> float:
        """Seconds the candidate spent on the same paired points."""
        return sum(pair.candidate_s for pair in self.paired)

    @property
    def ratio(self) -> float | None:
        """Total candidate time over total baseline time; None if unknown.

        ``None`` when no point is paired, so the caller cannot read
        "nothing to compare" as "no change".
        """
        if not self.paired or self.baseline_total_s == 0:
            return None
        return self.candidate_total_s / self.baseline_total_s


@dataclass(frozen=True)
class CostView:
    """The pivot: sweep points down, solver builds across.

    Attributes
    ----------
    builds : tuple of BuildKey
        Columns, ordered by label so a rendering is reproducible.
    points : tuple of PointKey
        Rows, ordered by simulation id then by axis values.
    cells : mapping
        ``(point, build)`` to :class:`CostCell`, sparse: a pair with no
        run recorded is simply absent from it.

    Raises
    ------
    QaEvidenceError
        If two builds render the same label, which two hashes sharing
        their first twelve characters would do. Refusing is the point:
        a duplicated label makes one column overwrite the other in
        :meth:`rows`, which is the silent merge this view exists to
        prevent. It keeps ``ValueError`` as its standard-library base.
    """

    builds: tuple[BuildKey, ...] = ()
    points: tuple[PointKey, ...] = ()
    cells: Mapping[tuple[PointKey, BuildKey], CostCell] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse a view whose columns cannot be told apart by label."""
        labels = [build.label for build in self.builds]
        duplicated = sorted({label for label in labels if labels.count(label) > 1})
        if duplicated:
            raise QaEvidenceError(
                f"two solver builds render the same cost column label {duplicated}; "
                "their executable hashes agree on the first "
                f"{LABEL_SHA_CHARS} characters. Compare them through their "
                "BuildKey values rather than through labels, because one label "
                "for two executables merges two columns into one."
            )

    def cell(self, point: PointKey, build: BuildKey) -> CostCell:
        """Return the runs recorded for one point on one build.

        Returns an empty cell (``run_count == 0``) when that point was
        never run on that build, which is a different fact from a run
        that was not timed; :attr:`CostCell.recorded` separates them.
        """
        return self.cells.get((point, build), _EMPTY_CELL)

    def wall_time_s(self, point: PointKey, build: BuildKey) -> float | None:
        """Mean wall-clock seconds there, or ``None`` when absent."""
        return self.cell(point, build).wall_time_s

    def build(self, label: str) -> BuildKey:
        """Resolve one column by its label.

        Parameters
        ----------
        label : str
            A label as :attr:`BuildKey.label` renders it.

        Returns
        -------
        BuildKey
            The column that label names.

        Raises
        ------
        QaEvidenceError
            If no column carries it. The message lists the labels that
            do exist, because the caller typed one and the useful
            answer is the real ones rather than the shape of a label.
        """
        for build in self.builds:
            if build.label == label:
                return build
        known = ", ".join(candidate.label for candidate in self.builds) or "(none)"
        raise QaEvidenceError(
            f"no solver build labelled {label!r} in this cost view; it carries {known}"
        )

    def rows(self) -> list[dict[str, object]]:
        """Return the pivot as plain rows: identity columns, then one per build.

        Returns
        -------
        list of dict
            One dict per point. Keys are ``"sim_id"``, ``"point"`` and
            one :attr:`BuildKey.label` per build; each build value is
            the mean wall-clock time in seconds or ``None`` when that
            cell is absent. Plain dicts rather than a dataframe: this
            layer holds no opinion about a substrate, and
            ``pandas.DataFrame(view.rows())`` is one call away.
        """
        rows: list[dict[str, object]] = []
        for point in self.points:
            row: dict[str, object] = {"sim_id": point.sim_id, "point": point.label}
            for build in self.builds:
                row[build.label] = self.wall_time_s(point, build)
            rows.append(row)
        return rows

    def compare(self, baseline: BuildKey | str, candidate: BuildKey | str) -> BuildComparison:
        """Put two builds side by side over the points both of them timed.

        Parameters
        ----------
        baseline, candidate : BuildKey or str
            The two columns, as keys or as labels. The baseline is the
            build the other is measured against, so a ratio above 1
            means the candidate is slower.

        Returns
        -------
        BuildComparison
            Carrying the paired points, the points it could not pair,
            and the two totals over the paired set only.
        """
        base = self.build(baseline) if isinstance(baseline, str) else baseline
        cand = self.build(candidate) if isinstance(candidate, str) else candidate
        paired: list[PointCost] = []
        unpaired: list[PointKey] = []
        for point in self.points:
            base_cell = self.cell(point, base)
            cand_cell = self.cell(point, cand)
            if not (base_cell.recorded or cand_cell.recorded):
                # Recorded on some THIRD build only: not part of this
                # comparison at all, so naming it as unpaired would
                # overstate what these two builds failed to cover.
                continue
            base_seconds = base_cell.wall_time_s
            cand_seconds = cand_cell.wall_time_s
            if base_seconds is None or cand_seconds is None:
                unpaired.append(point)
                continue
            paired.append(PointCost(point, base_seconds, cand_seconds))
        return BuildComparison(base, cand, tuple(paired), tuple(unpaired))


CostSource = CampaignWorkspace | str | Path | Iterable[RunRecord]


def _records(source: CostSource) -> list[RunRecord]:
    """Normalise every accepted source to a list of manifest records."""
    if isinstance(source, CampaignWorkspace):
        return source.read_manifest()
    if isinstance(source, (str, Path)):
        # Checked BEFORE the iterable branch: a str is iterable, and
        # iterating a campaign path yields characters rather than an
        # error.
        return CampaignWorkspace(source).read_manifest()
    if isinstance(source, Sequence) or isinstance(source, Iterable):
        return list(source)
    raise QaEvidenceError(
        f"cost view source {type(source).__name__} is neither a CampaignWorkspace, a "
        "campaign root path, nor a sequence of RunRecord; the cost view is built "
        "from run manifests and from nothing else"
    )


def _point_key(record: RunRecord) -> PointKey:
    """Return the row this record belongs to."""
    return PointKey(record.sim_id, tuple(sorted(record.point.items())))


def cost_view(source: CostSource) -> CostView:
    """Build the wall-time cost view of one campaign's manifest.

    Parameters
    ----------
    source : CampaignWorkspace, str, Path, or iterable of RunRecord
        A managed workspace, a campaign root whose ``runs.json`` is
        read, or the records themselves. Nothing else is read: no
        report, no output file, no solver.

    Returns
    -------
    CostView
        Points down, solver builds across. Empty (no builds, no points)
        for a campaign with no recorded runs, which a caller must
        decide about: an empty cost table is not a fast campaign.

    See Also
    --------
    cost_rows : the long form, one row per run.
    pyflightstream.results.tables.run_table : the results-layer view of
        the same manifest, which carries coefficients and maps a
        missing wall time to ``math.nan``.

    Examples
    --------
    See this module's top docstring for a runnable example.
    """
    records = _records(source)
    builds: set[BuildKey] = set()
    points: set[PointKey] = set()
    gathered: dict[tuple[PointKey, BuildKey], CostCell] = {}
    for record in records:
        build = BuildKey(record.fs_build, record.fs_exe_sha256)
        point = _point_key(record)
        builds.add(build)
        points.add(point)
        cell = gathered.get((point, build), _EMPTY_CELL)
        samples = cell.samples
        if record.wall_time_s is not None:
            samples = (*samples, float(record.wall_time_s))
        gathered[(point, build)] = CostCell(
            samples=samples,
            run_count=cell.run_count + 1,
            failed_count=cell.failed_count + (1 if record.status in _FAILED_STATUSES else 0),
        )
    return CostView(
        builds=tuple(sorted(builds, key=lambda item: item.label)),
        points=tuple(sorted(points, key=lambda item: (item.sim_id, item.axes))),
        cells=gathered,
    )


def cost_rows(source: CostSource) -> list[dict[str, object]]:
    """Return the long form of the same evidence: one row per run.

    Where :func:`cost_view` pivots so two builds can be read across, this
    keeps the manifest's own shape and spells ``fs_build`` and
    ``fs_exe_sha256`` as ordinary columns, with the FULL hash rather
    than a label prefix.

    Parameters
    ----------
    source : CampaignWorkspace, str, Path, or iterable of RunRecord
        As :func:`cost_view`.

    Returns
    -------
    list of dict
        One dict per run, in manifest order, which is the order the
        campaign recorded them in and therefore the evidence order.
        Keys are :data:`COST_ROW_COLUMNS`; ``wall_time_s`` is seconds
        or ``None``, never zero.
    """
    return [
        {
            "run_id": record.run_id,
            "sim_id": record.sim_id,
            "point": _point_key(record).label,
            "fs_build": record.fs_build,
            "fs_exe_sha256": record.fs_exe_sha256,
            "status": str(record.status),
            "wall_time_s": record.wall_time_s,
        }
        for record in _records(source)
    ]
