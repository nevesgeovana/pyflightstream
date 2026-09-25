"""G45 of 0.28.0: the Tecplot surface is written by the package from the VTK, the only route.

Oracle: what RPT-074 measured on FlightStream 26.124. The solver writes its VTK
surface export in the analysis loads frame, a point ``p`` as ``p' = R (p - o)``
and the velocity components the same way, origin included (its addendum); the
solver's own Tecplot holds the nodes in the reference frame. The translation
must put every node back where the reference frame has it, keep every cell value
as the VTK holds it, and write the velocity back as the solver wrote it.

THE SURFACE IS SYNTHETIC AND ITS LAYOUT IS THE SOLVER'S. The recorded mesh of
RPT-074 never enters this repository (NFR-14; RPT-052 says so of that mesh), so
:func:`_solver_vtk` builds a small closed body in the reference frame and writes
it the way the recorded export is laid out, measured on it: the four header
lines, ``POINTS n float`` with one leading space and three 25-column Fortran
``0.dddddddddddddddd E+xx`` fields per line, polygon lines ending in a space,
``POINT_DATA`` repeating the coordinates as ``X``, ``Y``, ``Z``, the nineteen
``CELL_DATA`` scalars in the solver's order, one 25-column field per line, and
CRLF line ends. The real files' numbers are measured offline (T45).

The names of the new surface module are imported inside the tests that use
them, so each case collects on a tree without it and fails there on what it
asserts rather than on an import.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import Campaign, CampaignConfigError, PprocSpec, ReferenceData
from pyflightstream.cases.workflows import build_script, unsteady_export_threshold
from pyflightstream.run import run_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

#: Frame 2 of RPT-074's probe, MRP at x = 9.152 m, and the same frame turned 90
#: deg about z (x' = y, y' = -x), as that probe's two scripts placed them.
MRP = {"frame": 2, "origin": [9.152, 0.0, 0.0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
TURNED_MRP = {"frame": 2, "origin": [9.152, 0.0, 0.0], "axes": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]}
REFERENCE = ReferenceData(area=50.0, length=2.526, moment_point_m=(9.152, 0.0, 0.0))
VELOCITY = ("Vx", "Vy", "Vz")
#: The nineteen cell scalars of the all-variables export, in the solver's order (RPT-074).
CELL_NAMES = (
    "Normalized_Vorticity",
    "skin_friction_coeff.",
    "Cp_reference",
    "Cp_freestream",
    "Mach_Number",
    "Area",
    "Vx",
    "Vy",
    "Vz",
    "Velocity",
    "BL_Thickness",
    "BL_streamline_length",
    "Transition_marker",
    "Separation_marker",
    "BL_momentum_thickness",
    "BL_displacement_thickness",
    "BL_shape_factor",
    "Static_pressure_ratio",
    "Boundary_Index",
)


def _fortran(value: float) -> str:
    """One number as the solver prints it: a 25-column ``0.dddddddddddddddd E+xx`` field."""
    if value == 0.0:
        body = "0.0000000000000000E+00"
    else:
        exponent = math.floor(math.log10(abs(value))) + 1
        mantissa = f"{abs(value) / 10.0**exponent:.16f}"
        if mantissa.startswith("1."):
            exponent += 1
            mantissa = f"{abs(value) / 10.0**exponent:.16f}"
        body = f"{mantissa}E{exponent:+03d}"
    return f"{'-' if value < 0 else ''}{body}".rjust(25)


def _body() -> tuple[np.ndarray, list[list[int]], dict[str, np.ndarray]]:
    """A closed synthetic body in the reference frame: its nodes, polygons and cell values.

    An ellipsoid about x = 8.5 to 11.4 m, six rings of eight nodes and a node at
    each end: 40 quadrilaterals and 16 triangles, the mixture a solver's surface
    carries. The velocity of each panel is the free stream at 2 deg plus a
    perturbation, and ``Velocity`` is its norm, as the solver's is on most panels.
    """
    rings, around = 6, 8
    nodes = [(8.5, 0.0, 0.0)]
    for ring in range(1, rings + 1):
        theta = math.pi * ring / (rings + 1)
        for step in range(around):
            phi = 2.0 * math.pi * step / around
            nodes.append(
                (
                    8.5 + 1.45 * (1.0 - math.cos(theta)),
                    0.6 * math.sin(theta) * math.cos(phi),
                    0.4 * math.sin(theta) * math.sin(phi),
                )
            )
    nodes.append((11.4, 0.0, 0.0))
    last = len(nodes) - 1
    polygons: list[list[int]] = []
    for step in range(around):
        polygons.append([0, 1 + (step + 1) % around, 1 + step])
    for ring in range(rings - 1):
        base = 1 + ring * around
        for step in range(around):
            polygons.append(
                [
                    base + step,
                    base + (step + 1) % around,
                    base + around + (step + 1) % around,
                    base + around + step,
                ]
            )
    base = 1 + (rings - 1) * around
    for step in range(around):
        polygons.append([base + step, base + (step + 1) % around, last])
    points = np.asarray(nodes, dtype=float)
    centres = np.asarray([points[ring].mean(axis=0) for ring in polygons])
    free = 68.058 * np.array([math.cos(math.radians(2.0)), 0.0, math.sin(math.radians(2.0))])
    velocity = free + np.column_stack(
        [
            12.0 * np.sin(3.0 * centres[:, 0]),
            5.0 * centres[:, 1],
            -7.0 * centres[:, 2],
        ]
    )
    speed = np.linalg.norm(velocity, axis=1)
    count = len(polygons)
    index = np.arange(count, dtype=float)
    values = {
        name: 0.001 * (position + 1) * (1.0 + np.cos(index))
        for position, name in enumerate(CELL_NAMES)
    }
    values["Cp_reference"] = 1.0 - (speed / 68.058) ** 2
    values["Cp_freestream"] = values["Cp_reference"]
    values["Vx"], values["Vy"], values["Vz"] = velocity.T
    values["Velocity"] = speed
    values["Boundary_Index"] = np.where(centres[:, 1] >= 0.0, 1.0, 2.0)
    return points, polygons, values


def _solver_vtk(path: Path, stated: dict) -> tuple[np.ndarray, list[list[int]], dict]:
    """Write :func:`_body` as the solver exports it in the frame ``stated``; return the body."""
    points, polygons, values = _body()
    rotation = np.asarray(stated["axes"], dtype=float)
    origin = np.asarray(stated["origin"], dtype=float)
    written = (points - origin) @ rotation.T
    velocity = np.column_stack([values[name] for name in VELOCITY])
    turned = (velocity - origin) @ rotation.T
    cells = dict(values)
    cells["Vx"], cells["Vy"], cells["Vz"] = turned.T
    lines = [
        "# vtk DataFile Version 3.0",
        "FlightStream vtk output",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(points)} float",
        *(" " + "".join(_fortran(value) for value in row) for row in written),
        f"POLYGONS {len(polygons)} {sum(len(ring) + 1 for ring in polygons)}",
        *(" ".join(str(value) for value in (len(ring), *ring)) + " " for ring in polygons),
        f"POINT_DATA {len(points)}",
    ]
    for axis, name in enumerate(("X", "Y", "Z")):
        lines += [f"SCALARS {name} FLOAT", "LOOKUP_TABLE default"]
        lines += [_fortran(value) for value in written[:, axis]]
    lines.append(f"CELL_DATA {len(polygons)}")
    for name in CELL_NAMES:
        lines += [f"SCALARS {name} FLOAT", "LOOKUP_TABLE default"]
        lines += [_fortran(value) for value in cells[name]]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return points, polygons, values


def _frame(stated):
    from pyflightstream.results import SurfaceFrame

    return SurfaceFrame.from_record(stated)


def _read_dat(path: Path) -> dict[str, object]:
    """Read a Tecplot the package wrote: its records, its blocks and its faces."""
    lines = path.read_text(encoding="utf-8").splitlines()
    names = [part.strip().strip('"') for part in lines[1].split("=", 1)[1].split('", "')]
    auxdata = {}
    at = 2
    while lines[at].startswith("DATASETAUXDATA"):
        key, value = lines[at].split(None, 1)[1].split("=", 1)
        auxdata[key.strip()] = value.strip().strip('"')
        at += 1
    zone = lines[at]
    fields = dict(
        part.strip().split("=", 1) for part in zone[len("ZONE ") :].split(", ") if "=" in part
    )
    nodes, cells, faces = int(fields["NODES"]), int(fields["ELEMENTS"]), int(fields["FACES"])
    tokens = " ".join(lines[at + 1 :]).split()
    blocks: dict[str, np.ndarray] = {}
    cursor = 0
    for index, name in enumerate(names):
        count = nodes if index < 3 else cells
        blocks[name] = np.asarray(tokens[cursor : cursor + count], dtype=float)
        cursor += count
    face_nodes = np.asarray(tokens[cursor : cursor + 2 * faces], dtype=int).reshape(faces, 2)
    cursor += 2 * faces
    left = np.asarray(tokens[cursor : cursor + faces], dtype=int)
    right = np.asarray(tokens[cursor + faces : cursor + 2 * faces], dtype=int)
    assert cursor + 2 * faces == len(tokens), "the file holds more than its zone declares"
    return {
        "names": names,
        "auxdata": auxdata,
        "zone": zone,
        "nodes": nodes,
        "cells": cells,
        "blocks": blocks,
        "faces": face_nodes,
        "left": left,
        "right": right,
    }


def _nodes_of(blocks) -> np.ndarray:
    return np.column_stack([blocks["X"], blocks["Y"], blocks["Z"]])


def _translated(source: Path, stated, tmp_path: Path, name: str = "p.dat") -> dict[str, object]:
    from pyflightstream.results import translate_vtk_surface

    translate_vtk_surface(source, tmp_path / name, frame=_frame(stated))
    return _read_dat(tmp_path / name)


def test_g45_the_solver_layout_is_read_as_the_surface_it_is(tmp_path):
    """The reader takes the solver's layout: CRLF, 25-column fields, a space after each polygon."""
    from pyflightstream.results import read_vtk_surface

    points, polygons, _ = _solver_vtk(tmp_path / "solution.vtk", MRP)
    surface = read_vtk_surface(tmp_path / "solution.vtk")
    assert surface.n_points == len(points) == 50 and surface.n_cells == len(polygons) == 56
    assert list(surface.point_data) == ["X", "Y", "Z"]
    assert list(surface.cell_data) == list(CELL_NAMES)
    assert np.array_equal(surface.point_data["X"], surface.points[:, 0])
    rings = [
        surface.connectivity[surface.offsets[i] : surface.offsets[i + 1]].tolist()
        for i in range(surface.n_cells)
    ]
    assert rings == polygons
    assert np.abs(surface.points - (points - np.array([9.152, 0.0, 0.0]))).max() < 1e-12


def test_g45_the_translated_nodes_are_the_reference_frames(tmp_path):
    """The VTK is written in the loads frame; the .dat puts its nodes back in the reference."""
    points, _, _ = _solver_vtk(tmp_path / "solution.vtk", MRP)
    written = _translated(tmp_path / "solution.vtk", MRP, tmp_path)
    nodes = _nodes_of(written["blocks"])
    assert nodes.shape == points.shape
    assert np.abs(nodes - points).max() < 1e-12
    # THE CONTROL: the VTK's own points are 9.152 m away in x, so a translation
    # that forgot the frame could not pass the line above.
    from pyflightstream.results import read_vtk_surface

    raw = read_vtk_surface(tmp_path / "solution.vtk").points
    assert np.abs(raw - points).max() > 9.0


def test_g45_every_cell_value_is_written_cell_centred_as_the_vtk_holds_it(tmp_path):
    from pyflightstream.results import read_vtk_surface

    source = tmp_path / "solution.vtk"
    _solver_vtk(source, MRP)
    raw = read_vtk_surface(source)
    written = _translated(source, MRP, tmp_path)
    names = written["names"]
    assert names[:3] == ["X", "Y", "Z"]
    assert names[3:] == list(CELL_NAMES), "every cell variable of the VTK, in its order"
    assert "Singularity_strength" not in names
    assert written["cells"] == raw.n_cells and written["nodes"] == raw.n_points
    assert "ZONETYPE=FEPOLYGON" in written["zone"] and "DATAPACKING=BLOCK" in written["zone"]
    assert "VARLOCATION=([4-22]=CELLCENTERED)" in written["zone"]
    blocks = written["blocks"]
    for name, values in raw.cell_data.items():
        if name in VELOCITY:
            continue
        assert np.array_equal(blocks[name], values), f"{name} is not the VTK's, value for value"
    # THE FACES are each polygon's edges, the polygon on the left, nothing on the right.
    sizes = np.diff(raw.offsets)
    assert len(written["faces"]) == int(sizes.sum())
    assert np.array_equal(written["left"], np.repeat(np.arange(1, raw.n_cells + 1), sizes))
    assert not written["right"].any()
    first = raw.connectivity[: sizes[0]] + 1
    assert written["faces"][: sizes[0]].tolist() == [
        [int(first[i]), int(first[(i + 1) % len(first)])] for i in range(len(first))
    ]
    # WHAT THE FILE STATES ABOUT ITSELF.
    auxdata = written["auxdata"]
    assert auxdata["SOURCE_VTK"] == source.name
    assert auxdata["SOURCE_VTK_SHA256"] == file_sha256(source)
    assert "Singularity_strength" in auxdata["NOT_CARRIED"]
    assert "cell-centred" in auxdata["TRANSLATION"] and "reference frame" in auxdata["TRANSLATION"]
    assert "frame 2" in auxdata["SOURCE_FRAME"]


def test_g45_the_velocity_is_written_back_as_the_solver_wrote_it_as_a_point(tmp_path):
    """RPT-074's addendum: the components carry the origin; only its undoing gives the speed."""
    source = tmp_path / "solution.vtk"
    _, _, values = _solver_vtk(source, MRP)
    from pyflightstream.results import read_vtk_surface

    raw = read_vtk_surface(source)
    written = _translated(source, MRP, tmp_path)["blocks"]
    speed = raw.cell_data["Velocity"]
    back = np.column_stack([written[name] for name in VELOCITY])
    as_vector = np.column_stack([raw.cell_data[name] for name in VELOCITY])
    assert np.abs(back - np.column_stack([values[name] for name in VELOCITY])).max() < 1e-12
    assert np.median(np.abs(np.linalg.norm(back, axis=1) - speed)) < 1e-9
    # THE CONTROL: turned back as a vector alone, the speed misses by the origin.
    assert np.median(np.abs(np.linalg.norm(as_vector, axis=1) - speed)) > 1.0


def test_g45_a_turned_loads_frame_is_undone(tmp_path):
    """RPT-074's turned frame: its file comes back onto the plain one's and the reference."""
    points, _, _ = _solver_vtk(tmp_path / "plain.vtk", MRP)
    _solver_vtk(tmp_path / "turned.vtk", TURNED_MRP)
    plain = _translated(tmp_path / "plain.vtk", MRP, tmp_path, "plain.dat")["blocks"]
    turned = _translated(tmp_path / "turned.vtk", TURNED_MRP, tmp_path, "turned.dat")["blocks"]
    assert np.abs(_nodes_of(turned) - points).max() < 1e-12
    for name in (*VELOCITY, "Cp_reference", "Velocity"):
        assert np.abs(turned[name] - plain[name]).max() < 1e-12, name
    # THE CONTROL: the turned file read as if its frame did not turn lands elsewhere.
    wrong = _translated(tmp_path / "turned.vtk", MRP, tmp_path, "wrong.dat")["blocks"]
    assert np.abs(_nodes_of(wrong) - points).max() > 0.1


def test_g45_a_campaign_surface_exports_the_vtk_and_never_the_solvers_tecplot():
    case = steady_case().model_copy(
        update={"reference": REFERENCE, "outputs": ["p.txt", "p.dat", "p_log.txt"]}
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    assert "EXPORT_SOLVER_ANALYSIS_TECPLOT" not in lines
    at = lines.index("EXPORT_SOLVER_ANALYSIS_VTK")
    assert lines[at + 1 : at + 3] == ["p.vtk", "SURFACES -1"]
    assert "SET_VTK_EXPORT_VARIABLES -1 DISABLE" in lines, "every variable and no wake file"
    assert lines.index("SET_VTK_EXPORT_VARIABLES -1 DISABLE") < at
    assert script.surface_translations == [
        {
            "vtk": "p.vtk",
            "dat": "p.dat",
            "frame": {
                "frame": 2,
                "origin": [9.152, 0.0, 0.0],
                "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            },
        }
    ]
    # ONE VTK FEEDS BOTH: a point asking for the VTK too exports it once, and a
    # selection of variables is the Tecplot's selection too.
    both = steady_case().model_copy(
        update={
            "reference": REFERENCE,
            "outputs": ["p.txt", "p.dat", "field.vtk"],
            "pproc": PprocSpec(exports={"vtk": True}, vtk_variables=["X", "CP_FREESTREAM"]),
        }
    )
    script = Script("26.124")
    build_script(both, script)
    text = script.render()
    assert text.count("EXPORT_SOLVER_ANALYSIS_VTK") == 1
    assert "EXPORT_SOLVER_ANALYSIS_VTK\nfield.vtk\nSURFACES -1" in text
    assert "SET_VTK_EXPORT_VARIABLES 2 DISABLE\nX\nCP_FREESTREAM" in text
    assert [(entry["vtk"], entry["dat"]) for entry in script.surface_translations] == [
        ("field.vtk", "p.dat")
    ]


def test_g45_the_per_step_exports_carry_the_vtk_and_each_is_translated(tmp_path):
    case = unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="37").model_copy(
        update={"outputs": ["p.txt", "p.dat"]}
    )
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None
    assert "EXPORT_SOLVER_ANALYSIS_TECPLOT" not in threshold.exports
    assert "EXPORT_SOLVER_ANALYSIS_VTK\np.vtk\nSURFACES -1" in threshold.exports
    from pyflightstream.results import translate_surface_exports

    points, _, _ = _solver_vtk(tmp_path / "p.vtk", MRP)
    for name in ("p_iteration=37.vtk", "p_iteration=38.vtk"):
        shutil.copyfile(tmp_path / "p.vtk", tmp_path / name)
    recorded = translate_surface_exports(tmp_path, [{"vtk": "p.vtk", "dat": "p.dat", "frame": MRP}])
    assert recorded[0]["written"] == ["p.dat", "p_iteration=37.dat", "p_iteration=38.dat"]
    assert recorded[0]["problems"] == []
    for name in recorded[0]["written"]:
        blocks = _read_dat(tmp_path / name)["blocks"]
        assert np.abs(_nodes_of(blocks) - points).max() < 1e-12
    # A STEP WHOSE VTK NEVER CAME IS SAID, and no .dat stands in for it.
    (tmp_path / "p.vtk").unlink()
    (tmp_path / "p.dat").unlink()
    again = translate_surface_exports(tmp_path, [{"vtk": "p.vtk", "dat": "p.dat", "frame": MRP}])
    assert again[0]["problems"] and "p.dat was not written" in again[0]["problems"][0]
    assert not (tmp_path / "p.dat").exists()


def test_g45_a_run_writes_the_tecplot_from_its_vtk_and_the_products_say_so(tmp_path):
    """End to end: a stub solver hands back a VTK in the loads frame; the run writes the .dat."""
    source = tmp_path / "exported.vtk"
    points, _, _ = _solver_vtk(source, MRP)
    case = steady_case().model_copy(
        update={"reference": REFERENCE, "outputs": ["p.txt", "p.dat"], "pproc": PprocSpec()}
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    code = (
        "import pathlib,shutil,sys; lines=pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        f"vtk={str(source)!r}; "
        "[shutil.copyfile(vtk, lines[i+1]) if line == 'EXPORT_SOLVER_ANALYSIS_VTK' else "
        "pathlib.Path(lines[i+1]).write_text('LOADS') for i, line in enumerate(lines) "
        "if line.startswith('EXPORT_SOLVER_ANALYSIS_')]"
    )
    record = run_campaign(
        campaign,
        StubSolver(code),
        workspace,
        assess=converged,
        recipes={"steady": build_script},
        preflight=False,
    )[0]
    names = [Path(name).name for name in record.outputs]
    assert names == ["p.txt", "p.dat", "p.vtk"], "the VTK the .dat is written from is kept"
    dat = workspace.sim_dir(record.sim_id) / next(o for o in record.outputs if o.endswith(".dat"))
    assert np.abs(_nodes_of(_read_dat(dat)["blocks"]) - points).max() < 1e-12
    assert record.surface_translations is not None
    assert record.surface_translations[0]["written"] == ["p.dat"]
    assert record.surface_translations[0]["frame"]["origin"] == [9.152, 0.0, 0.0]
    vtk_key = next(o for o in record.outputs if o.endswith(".vtk"))
    assert record.outputs_sha256[vtk_key] == file_sha256(source)
    from pyflightstream.post.products import _prov_document, write_campaign_products

    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads((workspace.products_dir(None) / "products.json").read_text())
    entry = next(e for e in manifest["products"].values() if e.get("format") == "tecplot")
    assert entry["translated_from"] == "p.vtk"
    assert entry["source_sha256"] == file_sha256(source)
    assert entry["location"] == "cell-centred" and entry["frame"] == "reference"
    assert entry["not_carried"] == ["Singularity_strength"]
    assert entry["kind"] == "instant"
    document = _prov_document(record, workspace.sim_dir(record.sim_id))
    dat_id = next(key for key in document["entity"] if key.endswith(".dat"))
    attributed = [a for a in document["wasAttributedTo"].values() if a["prov:entity"] == dat_id]
    assert [a["prov:agent"] for a in attributed] == [
        f"pyfs:package/pyflightstream/{record.package_version}"
    ], "the package wrote the .dat, not the solver"
    derived = [
        d for d in document["wasDerivedFrom"].values() if d["prov:generatedEntity"] == dat_id
    ]
    assert [d["prov:usedEntity"] for d in derived] == [f"pyfs:output/{vtk_key}"]


def test_g45_a_loads_frame_the_script_did_not_place_is_refused_before_the_run():
    from pyflightstream.cases.workflows import refuse_an_untranslatable_surface

    script = Script("26.124")
    script.declare_existing(frames=1)
    script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 2)
    script.surface_translations.append(
        {"vtk": "p.vtk", "dat": "p.dat", "frame": script.loads_frame_record()}
    )
    with pytest.raises(CampaignConfigError, match=r"p\.dat .* frame 2 cannot be undone"):
        refuse_an_untranslatable_surface(steady_case(), script)


def test_g45_some_of_the_velocity_components_are_refused_where_the_frame_moves():
    case = steady_case().model_copy(
        update={
            "reference": REFERENCE,
            "outputs": ["p.txt", "p.dat"],
            "pproc": PprocSpec(vtk_variables=["X", "VX"]),
        }
    )
    with pytest.raises(CampaignConfigError, match="VX of the three velocity components"):
        build_script(case, Script("26.124"))
    # Where the loads frame is the reference frame, a component alone is as the VTK holds it.
    plain = steady_case().model_copy(
        update={"outputs": ["p.txt", "p.dat"], "pproc": PprocSpec(vtk_variables=["X", "VX"])}
    )
    build_script(plain, Script("26.124"))
