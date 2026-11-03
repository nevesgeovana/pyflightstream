"""Saved vertex-file marking measurement for 26.100 (PFS-2186.07).

Pipeline role: register the controlled probe of ``TRAILING_EDGES_IMPORT`` (FSM-26.100
p.314), the command the marking pass uses on 26.100 because that build has no
``IMPORT_WAKE_EDGES_FROM_FILE``. The mesh is the blunt box of the 0.46.0 marking
probes: its end cap is a one-cell strip whose two rims (A, the lower side edge, and
B, the upper one) are joined by three edges the solver must not mark.

Three questions, each with the unchanged control (the saved state before the trial):

1. SPLIT: one file per rim, imported one after the other. Marks exactly the two rim
   edges and no edge between them: the one-rim-per-file route works.
2. ADDS OR REPLACES: SPLIT leaves both rim edges (the second import adds) or only B
   (it replaces). A control trial imports rim A alone, from the same saved state.
3. JOINT: both rims in one file. Records what the solver marks when a file names
   vertices of two rims, which is the reason the pass writes one rim per file.

The saved state is read with the measured mesh-block reader (:func:`trailing_edge_midpoints`),
which returns the mid-point of every flagged edge. The effect is True only for SPLIT
marking exactly both rim edges against an empty control; a replace or a cross edge is
False, and the pass then takes the saved route (``MARKING_ROUTE_26100 = "direct"``).
The file layout is the package's own (``render_trailing_edge_vertex_file``); a layout the
solver does not read shows as an empty read-back, which the observation records.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pyflightstream._fsm import MeshReadError, trailing_edge_midpoints
from pyflightstream._textio import write_text
from pyflightstream.qa._spec_0460_marking import _geometry
from pyflightstream.qa._spec_kit import _spec
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script
from pyflightstream.script.helpers import VERTEX_IMPORT_ROUTE, render_trailing_edge_vertex_file

__all__: list[str] = []

_RIM_A = ((2.0, -1.0, -1.0), (2.0, 1.0, -1.0))
_RIM_B = ((2.0, 1.0, 1.0), (2.0, -1.0, 1.0))
_MID_A = (2.0, 0.0, -1.0)
_MID_B = (2.0, 0.0, 1.0)
#: The three edges of the end cap that join rim A to rim B: its two sides and its diagonal.
_CROSS = frozenset({(2.0, 1.0, 0.0), (2.0, -1.0, 0.0), (2.0, 0.0, 0.0)})
_TRIALS = ("split", "single", "joint", "split_ws")


def _files(workdir: Path) -> dict[str, Path]:
    """Write the vertex files of every trial and return their paths by name."""
    texts = {
        "a": render_trailing_edge_vertex_file(_RIM_A),
        "b": render_trailing_edge_vertex_file(_RIM_B),
        "joint": render_trailing_edge_vertex_file((*_RIM_A, *_RIM_B)),
        "a_ws": render_trailing_edge_vertex_file(_RIM_A).replace(",", " "),
        "b_ws": render_trailing_edge_vertex_file(_RIM_B).replace(",", " "),
    }
    paths = {}
    for name, text in texts.items():
        paths[name] = workdir / f"rim_{name}.txt"
        write_text(paths[name], text, encoding="ascii")
    return paths


def _trial(script: Script, workdir: Path, name: str, imports: tuple[str, ...]) -> None:
    """Open the saved state, import the named files in order, save under the trial's name."""
    paths = _files(workdir)

    def build(inner: Script) -> None:
        inner.emit("OPEN", workdir / "before.fsm")
        inner.declare_existing(boundaries=2)
        for key in imports:
            inner.emit(VERTEX_IMPORT_ROUTE, paths[key])
        inner.emit("SAVEAS", workdir / f"{name}.fsm")

    _nested(script, workdir, f"trial_{name}", build)


def _nested(script: Script, workdir: Path, name: str, build: Callable[[Script], None]) -> None:
    """Validate the trial's grammar in a nested script and run it from the probe script."""
    inner = Script(script.version, registry=script.registry)
    build(inner)
    path = workdir / f"{name}.txt"
    write_text(path, inner.render(), encoding="utf-8")
    script.emit("RUN_SCRIPT", path)


def _edges(path: Path) -> frozenset[tuple[float, float, float]] | None:
    """Return the rounded mid-points of the saved trailing edges, or None if unreadable."""
    try:
        return frozenset(
            (round(x, 6), round(y, 6), round(z, 6)) for x, y, z in trailing_edge_midpoints(path)
        )
    except (OSError, ValueError, MeshReadError):
        return None


def _reading(workdir: Path) -> dict[str, object]:
    edges = {name: _edges(workdir / f"{name}.fsm") for name in ("before", "control", *_TRIALS)}
    reading: dict[str, object] = {
        name: None if found is None else sorted(found) for name, found in edges.items()
    }
    split = edges["split"]
    reading["control_unchanged"] = edges["before"] == edges["control"] and edges["before"] == set()
    if split is not None:
        reading["split_adds"] = {_MID_A, _MID_B} <= split
        reading["split_replaces"] = _MID_B in split and _MID_A not in split
        reading["split_cross_edges"] = sorted(split & _CROSS)
    joint = edges["joint"]
    if joint is not None:
        reading["joint_cross_edges"] = sorted(joint & _CROSS)
    return reading


def _effect(artifacts: ProbeArtifacts) -> bool | None:
    workdir = artifacts.workdir
    before, control, split = (
        _edges(workdir / f"{name}.fsm") for name in ("before", "control", "split")
    )
    if before is None or control is None or split is None or before or control != before:
        return None
    return split == {_MID_A, _MID_B}


def _observe(artifacts: ProbeArtifacts) -> str:
    return json.dumps(_reading(artifacts.workdir), sort_keys=True)


def _prelude(script: Script, workdir: Path) -> None:
    _geometry(script, workdir)
    script.emit("SAVEAS", workdir / "before.fsm")
    script.emit("SAVEAS", workdir / "control.fsm")


def _target(script: Script, workdir: Path) -> None:
    paths = _files(workdir)
    script.declare_existing(boundaries=2)
    script.emit(VERTEX_IMPORT_ROUTE, paths["a"])
    script.emit(VERTEX_IMPORT_ROUTE, paths["b"])


def _epilogue(script: Script, workdir: Path) -> None:
    script.emit("SAVEAS", workdir / "split.fsm")
    _trial(script, workdir, "single", ("a",))
    _trial(script, workdir, "joint", ("joint",))
    _trial(script, workdir, "split_ws", ("a_ws", "b_ws"))


_spec(
    command=VERTEX_IMPORT_ROUTE,
    build_target=_target,
    prelude=_prelude,
    epilogue=_epilogue,
    assert_effect=_effect,
    observe=_observe,
    preconditions=("SAVEAS", "OPEN"),
    effect_note="saved trailing edges after one file per rim, against an unchanged control: "
    "both rim edges and none between them; trials for a single rim, both rims in one file and "
    "a whitespace layout record add or replace and the edges a joint file marks",
)
