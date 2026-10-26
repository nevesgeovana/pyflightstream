"""Saved boundary-marking measurements for 26.124 and 26.125 (PFS-2149.01).

Pipeline role: register controlled probes, using a tiny two-family blunt box.
The readers accept only the WTN4 and BASE measured layouts. Missing or unknown
layouts are unobservable. No convergence, log message or whole-file difference
can verify these commands. On 26.124 the primary trial is initialized and an
independent uninitialized trial is reported separately; 26.125 needs no init.
M3 is a measurement in the combine epilogue, never a promotion criterion.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._fsm import MeshReadError, _mesh_block, boundary_names
from pyflightstream.qa._spec_kit import _spec
from pyflightstream.qa.probes import ProbeArtifacts, emit_solver_setup
from pyflightstream.script import Script
from pyflightstream.script.helpers import (
    detect_every_boundary,
    initialize_solver,
    render_wake_edge_node_file,
    wake_edge_import_token,
)

__all__: list[str] = []

_MARK = "MARK_WAKE_TERMINATION_NODES"
_AUTO = "AUTO_DETECT_WAKE_TERMINATION_NODES"
_IMPORT = "IMPORT_WAKE_EDGES_FROM_FILE"
_CREATE = "CREATE_NEW_BASE_REGION"
_CP = "SET_BASE_REGION_CP"
_RIM = "SET_BASE_REGION_TRAILING_EDGES"
_COMBINE = "SURFACE_COMBINE"
_RENAME = "SURFACE_RENAME"
_POINTS = (
    (0.0, -1.0, -1.0),
    (0.0, 1.0, -1.0),
    (0.0, 1.0, 1.0),
    (0.0, -1.0, 1.0),
    (2.0, -1.0, -1.0),
    (2.0, 1.0, -1.0),
    (2.0, 1.0, 1.0),
    (2.0, -1.0, 1.0),
)
_FACES = (
    (1, 3, 2),
    (1, 4, 3),
    (1, 2, 6),
    (1, 6, 5),
    (2, 3, 7),
    (2, 7, 6),
    (3, 4, 8),
    (3, 8, 7),
    (4, 1, 5),
    (4, 5, 8),
    (5, 6, 7),
    (5, 7, 8),
)
_FIRST = (2.0, 0.0, -1.0)
_SECOND = (2.0, 0.0, 1.0)
_RIM_POINTS = {_FIRST, _SECOND, (2.0, -1.0, 0.0), (2.0, 1.0, 0.0)}


def _tokens(line: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in line.split(",") if part.strip())


def _section(text: str, name: str) -> list[str]:
    begin, end = f"${name}_START$", f"${name}_END$"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("missing or repeated section")
    return text.split(begin)[1].split(end)[0].strip().splitlines()


def _termination(rows: list[str], vertices: int) -> int:
    """Read the sized record after coordinates, never equating its ids to OBJ ids."""
    count = int(rows[0])
    if count < 0 or len(rows) != (4 if count else 1):
        raise ValueError("unknown termination layout")
    if count:
        payload = [tuple(map(int, _tokens(row))) for row in rows[1:]]
        if any(len(row) != count for row in payload):
            raise ValueError("truncated termination rows")
        if any(not 1 <= node <= vertices for node in payload[0]):
            raise ValueError("invalid termination node")
        if set(payload[1]) != {2} or set(payload[2]) != {1}:
            raise ValueError("unknown termination flags")
    return count


def _physics(rows: list[str]) -> tuple[tuple[tuple[str, float], ...], tuple[str, ...]]:
    """Read BASE's counted names, flag and four sized numeric rows, then TE groups."""
    count = int(rows[3])
    if count < 0:
        raise ValueError("negative base count")
    pos = 4 + count
    bases: tuple[tuple[str, float], ...] = ()
    if count:
        names = tuple(row.strip() for row in rows[4:pos])
        values = [tuple(float(x) for x in _tokens(row)) for row in rows[pos + 1 : pos + 5]]
        if len(values) != 4 or any(len(row) != count for row in values):
            raise ValueError("truncated base values")
        if len(_tokens(rows[pos])) != count or not set(_tokens(rows[pos])) <= {"T", "F"}:
            raise ValueError("invalid base flags")
        if any(not math.isfinite(v) for row in values for v in row):
            raise ValueError("nonfinite base value")
        bases = tuple(zip(names, values[0], strict=True))
        pos += 5
    groups = int(rows[pos])
    names = tuple(row.strip() for row in rows[pos + 1 : pos + 1 + groups])
    if groups < 0 or len(names) != groups or any(not name for name in names):
        raise ValueError("truncated TE groups")
    if groups and tuple(map(int, _tokens(rows[pos + 1 + groups]))) != tuple(range(1, groups + 1)):
        raise ValueError("invalid TE group indices")
    return bases, names


@dataclass(frozen=True)
class _State:
    names: tuple[str, ...]
    vertices: tuple[tuple[float, float, float], ...]
    termination: int
    bases: tuple[tuple[str, float], ...]
    groups: tuple[str, ...]
    edges: frozenset[tuple[tuple[float, float, float], int]]


def _state(path: Path) -> _State | None:
    """Read bounded mesh rows and the measured per-face type row (WTN4 G5)."""
    try:
        text = path.read_text(encoding="utf-8")
        rows = _section(text, "MESH")
        vertices, faces, flags, _ = _mesh_block(path)
        names = boundary_names(path)
        if not names or not vertices or not faces:
            return None
        start = 3 + 3 * len(names)
        flag = next(i for i in range(start + 6, len(rows)) if set(_tokens(rows[i])) <= {"T", "F"})
        # Fifteen numeric per-face rows precede the five T/F rows in WTN4/BASE.
        if flag != start + 21:
            return None
        types = tuple(map(int, _tokens(rows[start + 13])))
        if len(types) != len(faces):
            return None
        term = _termination(rows[flag + 10 :], len(vertices))
        edges = set()
        for face, kind, *marked in zip(faces, types, *flags[1:4], strict=True):
            for active, (a, b) in zip(marked, ((0, 1), (1, 2), (2, 0)), strict=True):
                if active:
                    midpoint = tuple(
                        round((vertices[face[a]][i] + vertices[face[b]][i]) / 2, 9)
                        for i in range(3)
                    )
                    edges.add(((midpoint[0], midpoint[1], midpoint[2]), kind))
        bases, groups = _physics(_section(text, "PHYSICS"))
        return _State(names, vertices, term, bases, groups, frozenset(edges))
    except (OSError, UnicodeError, ValueError, IndexError, StopIteration, MeshReadError):
        return None


def _geometry(script: Script, workdir: Path) -> None:
    path = workdir / "marking.obj"
    lines = ["v " + " ".join(map(str, point)) for point in _POINTS]
    for i, face in enumerate(_FACES):
        if i in (0, 10):
            lines.append("g " + ("Body" if i == 0 else "Rim"))
        lines.append("f " + " ".join(map(str, face)))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "OBJ", path, clear=True)
    script.declare_existing(boundaries=2)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")


def _import(script: Script, workdir: Path, second: bool = False) -> None:
    path = workdir / ("second.txt" if second else "first.txt")
    path.write_text(render_wake_edge_node_file([_SECOND if second else _FIRST]), encoding="ascii")
    script.emit(
        _IMPORT,
        "RELAXED" if second else "STANDARD",
        0.0001,
        wake_edge_import_token(script, "METER"),
        path,
    )


def _prepare(script: Script, workdir: Path, command: str, initialized: bool, prefix: str) -> None:
    if script.version.canonical not in {"26.124", "26.125"}:
        raise ValueError("marking instruments are bounded to 26.124 and 26.125")
    _geometry(script, workdir)
    if command in {_MARK, _AUTO}:
        detect_every_boundary(script, "trailing_edges")
    if command == _IMPORT:
        _import(script, workdir)
    if command in {_CP, _RIM}:
        script.emit(_CREATE, 2, "EMPIRICAL", 0.0)
    if initialized:
        emit_solver_setup(script)
        initialize_solver(script)
    script.emit("SAVEAS", workdir / f"{prefix}before.fsm")
    script.emit("SAVEAS", workdir / f"{prefix}control.fsm")


def _target(script: Script, workdir: Path, command: str, prefix: str = "") -> None:
    if command == _COMBINE:
        for name, order in (("forward", [1, 2]), ("reverse", [2, 1])):

            def combine(inner: Script, order: list[int] = order, name: str = name) -> None:
                inner.emit("OPEN", workdir / f"{prefix}before.fsm")
                inner.declare_existing(boundaries=2)
                inner.emit(_COMBINE, 2, order)
                inner.emit("SAVEAS", workdir / f"{prefix}{name}.fsm")

            _invoke(script, workdir, prefix + name, combine)
        return
    script.declare_existing(boundaries=2)
    if command == _MARK:
        script.emit("SELECT_MESH_NODE", 7)
        script.emit(_MARK)
    elif command == _IMPORT:
        _import(script, workdir, True)
    elif command == _CREATE:
        script.emit(command, 2, "EMPIRICAL", -0.2)
    elif command == _CP:
        script.emit(command, 1, "CUSTOM", -0.35)
    elif command == _RIM:
        script.emit(command, -1)
    elif command == _RENAME:
        script.emit(command, 2, "RenamedRim")
    else:
        script.emit(command)


def _verdict(
    command: str,
    before: _State | None,
    after: _State | None,
    control: _State | None,
    forward: _State | None = None,
) -> bool | None:
    if before is None or after is None or control != before:
        return None
    if command in {_MARK, _AUTO}:
        if before.termination or not before.edges:
            return None
        # Autodetection's eligibility on this synthetic mesh is not yet licensed.
        return bool(after.termination) or (None if command == _AUTO else False)
    if command == _IMPORT:
        if (_FIRST, 1) not in before.edges or len(before.groups) != 1:
            return None
        return (
            after.groups[:-1] == before.groups
            and len(after.groups) == 2
            and before.edges <= after.edges
            and (_SECOND, 2) in after.edges
        )
    if command == _CREATE:
        return not before.bases and after.bases == (("Rim", -0.2),)
    if command == _CP:
        if before.bases != (("Rim", 0.0),):
            return None
        return after.bases == (("Rim", -0.35),)
    if command == _RIM:
        if before.bases != (("Rim", 0.0),) or before.edges:
            return None
        return (
            after.bases == before.bases
            and {point for point, _ in after.edges} == _RIM_POINTS
            and len(after.groups) == 1
        )
    if before.names != ("Body", "Rim"):
        return None
    if command == _COMBINE:
        return None if forward is None else after.names == forward.names == ("Body",)
    return after.names == ("Body", "RenamedRim")


def _reading(workdir: Path, command: str, prefix: str = "") -> dict[str, object]:
    states = [
        _state(workdir / f"{prefix}{name}.fsm")
        for name in ("before", "after", "control", "forward")
    ]
    return {
        "effect": _verdict(command, *states),
        "states": [
            None
            if state is None
            else {
                "names": state.names,
                "termination": state.termination,
                "bases": state.bases,
                "groups": state.groups,
                "edges": sorted(state.edges),
            }
            for state in states[:3]
        ],
    }


def _register(command: str) -> None:
    def prelude(script: Script, workdir: Path) -> None:
        initialized = script.version.canonical == "26.124"
        (workdir / "initialization.txt").write_text(str(initialized), encoding="ascii")
        _invoke(
            script,
            workdir,
            "prepare",
            lambda inner: _prepare(inner, workdir, command, initialized, ""),
        )

    def target(script: Script, workdir: Path) -> None:
        _invoke(script, workdir, "target", lambda inner: _target(inner, workdir, command))

    def epilogue(script: Script, workdir: Path) -> None:
        script.emit("SAVEAS", workdir / "after.fsm")
        if script.version.canonical == "26.124":
            _invoke(
                script,
                workdir,
                "noinit_prepare",
                lambda inner: _prepare(inner, workdir, command, False, "noinit_"),
            )
            _invoke(
                script,
                workdir,
                "noinit_target",
                lambda inner: _target(inner, workdir, command, "noinit_"),
            )
            script.emit("SAVEAS", workdir / "noinit_after.fsm")

    def effect(artifacts: ProbeArtifacts) -> bool | None:
        value = _reading(artifacts.workdir, command)["effect"]
        return value if isinstance(value, bool) else None

    def observe(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / "initialization.txt"
        initialized = path.read_text(encoding="ascii") if path.exists() else "unknown"
        readings = {
            "primary_initialized": initialized,
            "primary": _reading(artifacts.workdir, command),
        }
        if initialized == "True":
            readings["without_INITIALIZE_SOLVER"] = _reading(artifacts.workdir, command, "noinit_")
        return json.dumps(readings, sort_keys=True)

    _spec(
        command=command,
        build_target=target,
        prelude=prelude,
        epilogue=epilogue,
        assert_effect=effect,
        observe=observe,
        preconditions=("SELECT_MESH_NODE", "INITIALIZE_SOLVER", _CREATE, _IMPORT),
        effect_note="saved marking state against an unchanged control; 26.124 primary initialized, "
        "with an independent no-initialization measurement; 26.125 without INITIALIZE_SOLVER",
    )


def _invoke(script: Script, workdir: Path, name: str, build: Callable[[Script], None]) -> None:
    """Validate grammar in a nested script; runtime phase ordering is the experiment.

    SELECT and COMBINE are geometry commands in the builder. A nested script
    lets the licensed probe measure them on an initialized state without
    changing their production phase contract or emitting unvalidated text.
    """
    inner = Script(script.version, registry=script.registry)
    for command in (
        _MARK,
        _AUTO,
        _IMPORT,
        _CREATE,
        _CP,
        _RIM,
        _COMBINE,
        _RENAME,
        "SELECT_MESH_NODE",
        "TRANSFORM_SELECTED_NODES",
    ):
        inner.allow_broken(command, reason="boundary-marking probe: measure the saved effect")
    build(inner)
    path = workdir / f"{name}.txt"
    path.write_text(inner.render(), encoding="utf-8")
    script.emit("RUN_SCRIPT", path)


_register(_MARK)
_register(_AUTO)
_register(_IMPORT)
_register(_CREATE)
_register(_CP)
_register(_RIM)
_register(_COMBINE)
