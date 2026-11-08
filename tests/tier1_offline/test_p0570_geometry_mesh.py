"""P0570 geometry mesh: meshing a generated configuration into all-quad patches (needs gmsh).

The kernel-bound checks of the mesher. The comparison with the research mesher is tier 2: it
skips unless ``PYFS_RESEARCH_GEOMMESH`` names the research ``smi-geometry`` folder, and
requires the node coordinates, the cells and the component labels to be identical. The
refusal and the unknown-name checks run everywhere.
"""

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.extras import MissingExtraError
from pyflightstream.geometry import resolve_config
from pyflightstream.geometry.config import write_config
from pyflightstream.geometry.mesh_topology import read_obj
from pyflightstream.workspace._geometry_mesh import junction_bays, mesh_generated

WB = {
    "components": {
        "FUS": {"type": "body"},
        "WING": {
            "type": "lifting_surface",
            "attach": {"parent": "FUS", "station": 0.4},
            "sections": {"airfoils": ["NACA0012"]},
        },
        "FAIRING": {
            "type": "wing_fuselage_fairing",
            "hosts": ["FUS", "WING"],
            "attach": {"parent": "FUS", "station": 0.0},
        },
    },
}

RESEARCH = os.environ.get("PYFS_RESEARCH_GEOMMESH")


def need_gmsh():
    return pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")


def test_p0570_unknown_component_is_refused_with_the_names_found():
    need_gmsh()
    with pytest.raises(InputValueError, match="unknown; available"):
        mesh_generated(WB, component="NOPE")


def test_p0570_a_fairing_cannot_be_meshed_alone():
    need_gmsh()
    with pytest.raises(InputValueError, match="only body and lifting_surface"):
        mesh_generated(WB, component="FAIRING")


def test_p0570_assembly_needs_one_fairing():
    need_gmsh()
    raw = {"components": {"FUS": {"type": "body"}}}
    with pytest.raises(InputValueError, match="exactly one wing_fuselage_fairing"):
        mesh_generated(raw)


def test_p0570_missing_gmsh_is_refused_with_the_install_command(monkeypatch):
    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "gmsh" or name.startswith("gmsh."):
            raise ImportError("no gmsh")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    with pytest.raises(MissingExtraError, match="gmsh"):
        mesh_generated(WB, component="FUS")


def test_p0570_junction_bays_follow_the_family_order_and_skip_the_cap():
    patches = [SimpleNamespace(family=f) for f in ("a", "b", "c", "d", "tip_cap")]
    expected = ["inner", "outer", "outboard", "inner", None]
    assert junction_bays(patches) == expected  # type: ignore[arg-type]


def test_p0570_the_body_meshes_all_quad_and_is_accepted(tmp_path):
    need_gmsh()
    out = tmp_path / "fus.obj"
    result = mesh_generated(WB, component="FUS", obj=out)
    record = result.record
    assert record["accepted"] is True
    assert record["non_quad_count"] == 0
    assert record["inverted_count"] == 0
    assert record["degenerate_count"] == 0
    assert record["non_manifold_count"] == 0
    assert record["free_edges_off_y0_count"] == 0
    assert record["spacing_rules"]["passed"] is True
    again = read_obj(out)
    assert len(again.cells) == len(result.mesh.cells)


def test_p0570_the_wing_meshes_all_quad_with_its_tip_cap():
    need_gmsh()
    record = mesh_generated(WB, component="WING").record
    assert record["accepted"] is True
    assert record["non_quad_count"] == 0
    assert record["cap_cells"] > 0
    assert record["spacing_rules"]["passed"] is True


def test_p0570_the_assembly_has_no_open_or_nonmanifold_edge_and_triangles_only_in_the_ring():
    need_gmsh()
    result = mesh_generated(WB)
    record = result.record
    assert record["non_manifold_count"] == 0
    assert record["free_edges_off_y0_count"] == 0
    assert record["degenerate_count"] == 0
    assert record["forbidden_non_quad_cells"] == []
    assert record["inconsistent_shared_edge_directions"] == 0
    assert set(result.mesh.components) >= {"FUS", "WING"}
    assert record["accepted"] is (record["inverted_count"] == 0)


@pytest.mark.skipif(not RESEARCH, reason="tier 2: PYFS_RESEARCH_GEOMMESH names the research folder")
@pytest.mark.parametrize(
    ("component", "cells", "triangles"),
    [("WING", 2938, 0), ("FUS", 1656, 0), ("HTP", 2939, 0), (None, 4760, 248)],
)
def test_p0570_the_published_geometry_meshes_to_the_handoff_counts(component, cells, triangles):
    need_gmsh()
    source = Path(RESEARCH) / "phaseA" / "SMI-resolved.toml"
    result = mesh_generated(source, component=component)
    record = result.record
    assert len(result.mesh.cells) == cells
    assert sum(len(c) == 3 for c in result.mesh.cells) == triangles
    assert record["accepted"] is True
    assert record["inverted_count"] == 0
    assert record["degenerate_count"] == 0
    assert record["non_manifold_count"] == 0
    assert record["free_edges_off_y0_count"] == 0
    assert record["spacing_rules"]["passed"] is True


_RESEARCH_SCRIPT = r"""
import sys, tomllib
import numpy as np
root = sys.argv[1]
sys.path[:0] = [root + "/geomgen", root + "/geommesh"]
from geomgen.config import read_config, unpack
from geomgen.lifting import lifting_surface
from geomgen.subcomponents import tip_cap
from geomgen.bodies import body
from geommesh.phasem import mesh_component
from geommesh.wb import mesh_wb
controls = tomllib.loads(open(root + "/geommesh/examples/mesh_controls.toml").read())
config = read_config(sys.argv[2])
components = unpack(config)["components"]
out = {}
for name in ("FUS", "WING"):
    c = components[name]
    src = lifting_surface(c) + tip_cap(c) if c["type"] == "lifting_surface" else body(c)
    mesh, _, _ = mesh_component(name, c, controls[c["type"]], src)
    out[name] = mesh
mesh, _ = mesh_wb(config, controls, member_names=("FUS", "WING", "FAIRING"))
out["WB"] = mesh
arrays = {}
for k, m in out.items():
    arrays[k + "_xyz"] = np.asarray(m.xyz)
    arrays[k + "_cells"] = np.array([list(c) + [-1] * (4 - len(c)) for c in m.cells])
    arrays[k + "_components"] = np.array(m.components)
np.savez(sys.argv[3], **arrays)
"""


@pytest.mark.skipif(not RESEARCH, reason="tier 2: PYFS_RESEARCH_GEOMMESH names the research folder")
def test_p0570_the_mesh_equals_the_research_mesher_to_the_last_bit(tmp_path):
    need_gmsh()
    config = tmp_path / "wb.toml"
    write_config(resolve_config(WB), config)
    npz = tmp_path / "research.npz"
    done = subprocess.run(
        [sys.executable, "-I", "-c", _RESEARCH_SCRIPT, str(RESEARCH), str(config), str(npz)],
        capture_output=True,
        text=True,
        check=False,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert done.returncode == 0, done.stderr[-2000:]
    reference = np.load(npz)
    differences = {}
    for key, mine in (
        ("FUS", mesh_generated(WB, component="FUS").mesh),
        ("WING", mesh_generated(WB, component="WING").mesh),
        ("WB", mesh_generated(WB).mesh),
    ):
        cells = np.array([list(c) + [-1] * (4 - len(c)) for c in mine.cells])
        ref_cells = reference[key + "_cells"]
        same_topology = cells.shape == ref_cells.shape and np.array_equal(cells, ref_cells)
        xyz = np.asarray(mine.xyz)
        ref_xyz = reference[key + "_xyz"]
        delta = float(np.max(np.abs(xyz - ref_xyz))) if xyz.shape == ref_xyz.shape else float("inf")
        labels = np.array_equal(np.array(mine.components), reference[key + "_components"])
        differences[key] = {"topology": same_topology, "max_abs": delta, "labels": labels}
    print(json.dumps(differences))
    assert all(
        d["topology"] and d["max_abs"] == 0.0 and d["labels"] for d in differences.values()
    ), differences


def test_p0570_the_module_names_no_research_path():
    text = Path(sys.modules["pyflightstream.workspace._geometry_mesh"].__file__).read_text(
        encoding="utf-8"
    )
    assert "sys.path" not in text
    assert "GeoverseResearch" not in text
