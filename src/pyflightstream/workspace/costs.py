"""The per-machine cost file of a workspace: ``inputs/costs/c<NNN>.toml`` (FR-398).

Run cost depends on the machine and the mesh, so the measured values of a
machine belong to its user and never to the package. A workspace may carry
one file per machine under ``costs/``; :func:`read_cost_file` reads one into a
:class:`CostFile`, refusing an unknown or misplaced key by name, and
:func:`resolve_cost_file` finds the one a plan names. :func:`estimate_seconds`
turns a file and a point's figures into an expected wall time::

    seconds = reference.wall_time_s
              x (faces / reference.mesh_faces) ** mesh.exponent_b
              x (steps / reference.steps) ** steps.exponent
              x speedup(reference.ncpus) / speedup(ncpus)
              x product of the multipliers of the flags the point sets

The efficiency curve ``[parallel]`` is a table of ``ncpus`` against
``speedup``, interpolated linearly between its stated points. A processor
count outside the stated range is NEVER extrapolated: the estimate is
withheld and the basis says why. The package ships only a synthetic example
(``examples/costs/c000.toml``); :func:`unmarked_cost_files` is the guard that
every cost file a tree tracks says so.
"""

from __future__ import annotations

import dataclasses
import math
import warnings
from collections.abc import Collection, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace.sidecars import load_toml

__all__ = [
    "COSTS_DIR",
    "SYNTHETIC_WORD",
    "CostEstimate",
    "CostFile",
    "cost_files",
    "estimate_seconds",
    "priced_rows",
    "read_cost_file",
    "resolve_cost_file",
    "select_cost_file",
    "unmarked_cost_files",
]

#: Where a workspace keeps the cost file of each machine it is planned for.
COSTS_DIR = "costs"

#: The word every tracked cost file carries, so no measured value ships (FR-398 R5).
SYNTHETIC_WORD = "synthetic"

_TABLES: dict[str, frozenset[str]] = {
    "machine": frozenset({"name", "fs_build"}),
    "reference": frozenset({"pol", "run_type", "mesh_faces", "ncpus", "wall_time_s", "steps"}),
    "parallel": frozenset({"ncpus", "speedup", "fit_coefficient", "fit_exponent"}),
    "mesh": frozenset({"exponent_b"}),
    "steps": frozenset({"exponent"}),
    "flags": frozenset(),
}

#: The stem selected by ``--cost-file NAME``, or None.
_SELECTED_COST_FILE: ContextVar[str | None] = ContextVar("pyflightstream_cost_file", default=None)


@dataclass(frozen=True)
class CostFile:
    """One machine's cost model (FR-398).

    Attributes
    ----------
    path : Path
        Where it was read from, for a refusal that has to name it.
    machine : dict
        ``name`` and ``fs_build`` of the machine.
    reference : dict
        The anchor run: ``wall_time_s``, ``mesh_faces``, ``ncpus`` and
        optionally ``steps``, ``pol`` and ``run_type``.
    ncpus : tuple of float
        The processor counts of the efficiency curve, ascending.
    speedup : tuple of float
        The speedup stated at each of ``ncpus``.
    fit : tuple of float or None
        ``(a, c)`` of ``speedup = a N^c`` when the file states it; recorded,
        never used to extrapolate.
    mesh_exponent : float
        The exponent b of the face count.
    steps_exponent : float
        The exponent of the step count.
    flags : dict of str to float
        The multiplier of each solver flag.
    """

    path: Path
    machine: dict
    reference: dict
    ncpus: tuple[float, ...]
    speedup: tuple[float, ...]
    fit: tuple[float, float] | None = None
    mesh_exponent: float = 1.0
    steps_exponent: float = 1.0
    flags: dict[str, float] = field(default_factory=dict)

    def speedup_at(self, ncpus: float) -> float | None:
        """Interpolate the efficiency curve at ``ncpus``, or None outside its range.

        Parameters
        ----------
        ncpus : float
            Processor count.

        Returns
        -------
        float or None
            The speedup, linear between the two stated points around
            ``ncpus``; None when ``ncpus`` lies outside the stated range.
        """
        points = list(zip(self.ncpus, self.speedup, strict=True))
        if not points or ncpus < points[0][0] or ncpus > points[-1][0]:
            return None
        for (n0, s0), (n1, s1) in zip(points, points[1:], strict=False):
            if n0 <= ncpus <= n1:
                return s0 if n1 == n0 else s0 + (s1 - s0) * (ncpus - n0) / (n1 - n0)
        return points[0][1]


@dataclass(frozen=True)
class CostEstimate:
    """The expected wall time of one point under a cost file.

    Attributes
    ----------
    seconds : float or None
        The estimate, None when the file cannot answer for this point.
    basis : str
        One sentence naming what the figure rests on, or why there is none.
    """

    seconds: float | None
    basis: str


def cost_files(inputs_dir: str | Path) -> list[Path]:
    """Every cost file a workspace carries, sorted.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    list of Path
        The ``c*.toml`` files of its ``costs/`` folder; empty when none.
    """
    directory = Path(inputs_dir) / COSTS_DIR
    return sorted(directory.glob("c*.toml")) if directory.is_dir() else []


def select_cost_file(name: str | None) -> None:
    """Select which cost file :func:`resolve_cost_file` returns (CLI ``--cost-file NAME``).

    Parameters
    ----------
    name : str or None
        The file stem, ``c002`` for ``inputs/costs/c002.toml``; None clears it.

    Returns
    -------
    None
        Held in a context variable, so it belongs to the invocation.
    """
    _SELECTED_COST_FILE.set(None if name is None else Path(name).stem)


def resolve_cost_file(inputs_dir: str | Path) -> CostFile | None:
    """Return the cost file this plan uses, or None when the workspace has none.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    CostFile or None
        The selected file, else the only one; None without any.

    Raises
    ------
    InputArtifactError
        If the selection names no file, if several files exist and none is
        selected, or the file is refused by :func:`read_cost_file`.
    """
    found = cost_files(inputs_dir)
    selected = _SELECTED_COST_FILE.get()
    if selected is not None:
        for path in found:
            if path.stem == selected:
                return read_cost_file(path)
        raise InputArtifactError(
            f"{Path(inputs_dir) / COSTS_DIR} holds no cost file named {selected!r} "
            f"(CLI: --cost-file); available: {', '.join(p.stem for p in found) or 'none'}."
        )
    if len(found) > 1:
        raise InputArtifactError(
            f"{Path(inputs_dir) / COSTS_DIR} holds {len(found)} cost files "
            f"({', '.join(p.name for p in found)}) and nothing says which machine this is. "
            "One file needs no selector; several need one: cost_file (CLI: --cost-file) "
            "taking <name>, or select_cost_file(name)."
        )
    return read_cost_file(found[0]) if found else None


def _number(table: Mapping, key: str, where: str, path: Path) -> float:
    """Return ``table[key]`` as a finite number, refusing it by name otherwise."""
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise InputArtifactError(f"the cost file {path} needs [{where}] {key} to be a number.")
    return float(value)


def _refuse_unknown(raw: Mapping, path: Path) -> None:
    """Refuse a table or key this package does not read, naming it."""
    for name, table in raw.items():
        if name not in _TABLES or not isinstance(table, Mapping):
            raise InputArtifactError(
                f"the cost file {path} states {name!r} at the top level; this package reads "
                f"the tables {', '.join(sorted(_TABLES))}."
            )
        allowed = _TABLES[name]
        extra = sorted(str(k) for k in table if name != "flags" and k not in allowed)
        if extra:
            raise InputArtifactError(
                f"the cost file {path} states {', '.join(extra)} in [{name}], and this package "
                f"reads {', '.join(sorted(allowed))} there."
            )


def _curve(parallel: Mapping, path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Read and check the efficiency curve of the ``[parallel]`` table."""
    ncpus, speedup = parallel.get("ncpus", []), parallel.get("speedup", [])
    if not isinstance(ncpus, list) or not isinstance(speedup, list) or len(ncpus) != len(speedup):
        raise InputArtifactError(
            f"the cost file {path} needs [parallel] ncpus and speedup to be lists of one length."
        )
    xs = tuple(float(x) for x in ncpus)
    if list(xs) != sorted(set(xs)) or any(s <= 0 for s in speedup):
        raise InputArtifactError(
            f"the cost file {path} needs [parallel] ncpus ascending and distinct and every "
            "speedup positive."
        )
    return xs, tuple(float(s) for s in speedup)


def read_cost_file(path: str | Path) -> CostFile:
    """Read one cost file, refusing an unknown or malformed key by name.

    Parameters
    ----------
    path : str or Path
        The ``c<NNN>.toml`` file.

    Returns
    -------
    CostFile
        The model.

    Raises
    ------
    InputArtifactError
        If a table or key is not one this package reads, a required number is
        missing, or the efficiency curve is malformed.
    """
    target = Path(path)
    raw = load_toml(target, "cost file")
    _refuse_unknown(raw, target)
    reference = dict(raw.get("reference", {}))
    for key in ("wall_time_s", "mesh_faces", "ncpus"):
        _number(reference, key, "reference", target)
    xs, ys = _curve(raw.get("parallel", {}), target)
    fit = None
    parallel = raw.get("parallel", {})
    if "fit_coefficient" in parallel and "fit_exponent" in parallel:
        fit = (
            _number(parallel, "fit_coefficient", "parallel", target),
            _number(parallel, "fit_exponent", "parallel", target),
        )
    flags = {str(k): _number(raw["flags"], str(k), "flags", target) for k in raw.get("flags", {})}
    mesh, steps = raw.get("mesh", {}), raw.get("steps", {})
    return CostFile(
        path=target,
        machine=dict(raw.get("machine", {})),
        reference=reference,
        ncpus=xs,
        speedup=ys,
        fit=fit,
        mesh_exponent=_number(mesh, "exponent_b", "mesh", target) if mesh else 1.0,
        steps_exponent=_number(steps, "exponent", "steps", target) if steps else 1.0,
        flags=flags,
    )


def estimate_seconds(
    cost: CostFile,
    *,
    faces: int | None,
    steps: int | None,
    ncpus: int | None,
    flags: Collection[str] = (),
) -> CostEstimate:
    """Estimate the wall time of one point under ``cost`` (FR-398).

    A figure the point does not state (faces, steps, ncpus) leaves its factor
    at one and the basis says so; a processor count outside the stated range
    of the efficiency curve withholds the estimate rather than extrapolating.

    Parameters
    ----------
    cost : CostFile
        The machine's model.
    faces : int or None
        The mesh face count of the point.
    steps : int or None
        The time steps of the point; None for a steady row.
    ncpus : int or None
        The processors the point sets.
    flags : collection of str
        The solver flags the point sets; each one the file states multiplies.

    Returns
    -------
    CostEstimate
        The seconds, or None with the reason in ``basis``.
    """
    ref = cost.reference
    ref_cpus = float(ref["ncpus"])
    notes: list[str] = []
    seconds = float(ref["wall_time_s"])
    if faces is None:
        notes.append("mesh size unknown, the face term is left at one")
    else:
        seconds *= (faces / float(ref["mesh_faces"])) ** cost.mesh_exponent
    if steps is None or "steps" not in ref:
        notes.append("no step term")
    else:
        seconds *= (steps / float(ref["steps"])) ** cost.steps_exponent
    point_cpus = ref_cpus if ncpus is None else float(ncpus)
    ref_speed, point_speed = cost.speedup_at(ref_cpus), cost.speedup_at(point_cpus)
    if ref_speed is None or point_speed is None:
        stated = f"{cost.ncpus[0]:g} to {cost.ncpus[-1]:g}" if cost.ncpus else "none"
        return CostEstimate(
            None,
            f"cost file {cost.path.name}: ncpus {point_cpus:g} or the reference "
            f"{ref_cpus:g} lies outside the stated efficiency range ({stated}); "
            "no estimate is offered rather than an extrapolation",
        )
    seconds *= ref_speed / point_speed
    applied = sorted(name for name in flags if name in cost.flags)
    for name in applied:
        seconds *= cost.flags[name]
    tail = f" ({'; '.join(notes)})" if notes else ""
    flagged = f", flag multipliers {', '.join(applied)}" if applied else ""
    return CostEstimate(
        round(seconds, 1),
        f"cost file {cost.path.name}: reference run scaled by mesh faces, steps and "
        f"processors{flagged}{tail}. It is the user's own model, not a measurement of this point",
    )


def unmarked_cost_files(root: str | Path, *, skip: Collection[str] = ("tests",)) -> list[Path]:
    """Every tracked-style ``c*.toml`` under ``root`` that does not say it is synthetic.

    The guard of FR-398 R5: the package ships no measured machine value, so a
    cost file anywhere in the tree (outside the ``skip`` folders) must carry
    the word :data:`SYNTHETIC_WORD`.

    Parameters
    ----------
    root : str or Path
        The tree to walk (a repository root).
    skip : collection of str
        Top-level folders left out, the tests' own fixtures by default.

    Returns
    -------
    list of Path
        The cost files lacking the word, sorted; empty when the tree is clean.
    """
    base = Path(root)
    found = [
        path
        for path in base.rglob("c*.toml")
        if path.parent.name == COSTS_DIR
        and not any(part in skip for part in path.relative_to(base).parts[:1])
        and ".git" not in path.relative_to(base).parts
    ]
    return sorted(p for p in found if SYNTHETIC_WORD not in p.read_text(encoding="utf-8").lower())


def _flags_of(cost: CostFile, case: object) -> list[str]:
    """List the flags of ``cost`` the case sets (a truthy solver setting or row variable)."""
    solver = getattr(case, "solver", None)
    variables = getattr(case, "variables", None) or {}
    upper = {str(k).upper(): v for k, v in variables.items()}
    return [
        name
        for name in cost.flags
        if getattr(solver, name, None) or upper.get(name.upper()) not in (None, False, 0, "", "0")
    ]


def priced_rows(
    rows: Sequence, cases_by_run_id: Mapping[str, object], inputs_dir: str | Path | None
):
    """Replace the fitted time of each cost row by the cost file's, when the workspace has one.

    FR-398. Without a cost file the rows come back as they are, which is what
    keeps ``plan --cost`` byte-identical to 0.34.0. A point the file cannot
    answer for (a processor count outside its stated range) keeps no number
    and a warning names it.

    Parameters
    ----------
    rows : sequence of PlannedPointCost
        The rows the recorded-run fit produced.
    cases_by_run_id : mapping
        The case of each run id, specialised to its point.
    inputs_dir : str or Path or None
        The workspace ``inputs/`` directory; None (a stand-in without one) prices nothing.

    Returns
    -------
    list
        The rows, with ``seconds``, ``samples`` and ``basis`` of the cost
        file's estimate where the workspace carries one.
    """
    cost = None if inputs_dir is None else resolve_cost_file(inputs_dir)
    if cost is None:
        return list(rows)
    priced = []
    for row in rows:
        case = cases_by_run_id[row.run_id]
        estimate = estimate_seconds(
            cost,
            faces=row.panels,
            steps=row.time_iterations,
            ncpus=row.processors,
            flags=_flags_of(cost, case),
        )
        if estimate.seconds is None:
            warnings.warn(f"{row.run_id}: {estimate.basis}.", PyflightstreamWarning, stacklevel=2)
        priced.append(
            dataclasses.replace(row, seconds=estimate.seconds, samples=0, basis=estimate.basis)
        )
    return priced
