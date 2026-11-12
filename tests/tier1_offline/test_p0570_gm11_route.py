"""P0570-GM11 round 2: FSM writer, generation record, strategy 1 driver and the mesh verb.

Synthetic meshes only; the WB acceptance runs the committed WB fixture of
``test_p0570_geometry_mesh.py`` through the kernel and is skipped without it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, InputValueError
from pyflightstream.geometry._mesh_topology import Mesh

ROOT = Path(__file__).resolve().parents[2]
FRESH = ROOT / "tests" / "tier3_licensed" / "inputs" / "geometries" / "20_BODY.fsm"
MARKED = ROOT / "tests" / "tier3_licensed" / "inputs" / "geometries" / "11_HALFWING.fsm"


def _grid(nx=3, ny=2, *, y0=0.0, name="WING", offset=0, z=0.0):
    xyz = np.array([[i * 0.1, y0 + j * 0.2, z] for j in range(ny + 1) for i in range(nx + 1)])
    cells = [
        (
            offset + j * (nx + 1) + i,
            offset + j * (nx + 1) + i + 1,
            offset + (j + 1) * (nx + 1) + i + 1,
            offset + (j + 1) * (nx + 1) + i,
        )
        for j in range(ny)
        for i in range(nx)
    ]
    return xyz, cells, [name] * len(cells)


def _mesh(*parts):
    xyz, cells, names = [], [], []
    for p in parts:
        xyz.append(p[0])
        cells += p[1]
        names += p[2]
    points = np.vstack(xyz)
    return Mesh(points, cells, names, [1] * len(cells), np.arange(len(points)))


# ---- sub-step 9: FSM writer -------------------------------------------------------------------


def test_p0570_gm11_fsm_round_trips_mesh_and_marks_through_the_reader(tmp_path):
    """YES: quads, a triangle, two components and a marked TE read back exactly."""
    from pyflightstream._fsm import (
        boundary_names,
        boundary_owners,
        surface_mesh,
        trailing_edge_midpoints,
    )
    from pyflightstream.workspace._fsm_write import paired_triangles, write_fsm

    wing = _grid()
    body = _grid(2, 1, y0=1.0, name="FUS", offset=len(wing[0]))
    mesh = _mesh(wing, body)
    mesh.cells.append((0, 1, len(wing[0])))
    mesh.components.append("FUS")
    mesh.surfaces.append(2)
    te = [(3, 7), (7, 11)]
    out = write_fsm(tmp_path / "m.fsm", mesh, template=FRESH, trailing_edges=te)
    vertices, triangles = surface_mesh(out)
    expected, _, _, owners = paired_triangles(mesh)
    assert np.allclose(vertices, mesh.xyz, rtol=0, atol=1e-15)
    assert [tuple(t) for t in triangles] == [tuple(t) for t in expected]
    assert boundary_names(out) == ("WING", "FUS")
    assert boundary_owners(out) == tuple(1 if o == "WING" else 2 for o in owners)
    mids = {tuple(np.round((mesh.xyz[a] + mesh.xyz[b]) / 2, 12)) for a, b in te}
    assert {tuple(np.round(m, 12)) for m in trailing_edge_midpoints(out)} == mids
    # Every block other than the mesh block is the template's.
    text, fresh = out.read_text(encoding="latin-1"), FRESH.read_text(encoding="latin-1")
    assert text.split("$MESH_END$")[1] == fresh.split("$MESH_END$")[1]


def test_p0570_gm11_fsm_partners_name_each_other_across_the_diagonal():
    from pyflightstream.workspace._fsm_write import paired_triangles

    tri, partners, slots, _ = paired_triangles(_mesh(_grid(1, 1)))
    assert [tuple(t) for t in tri] == [(0, 1, 3), (0, 3, 2)]
    assert partners == [2, 1] and slots == [3, 1]


def test_p0570_gm11_fsm_refuses_by_name(tmp_path):
    """NO: a template with another mesh's TE groups, a TE off the mesh, a pentagon, overwrite."""
    from pyflightstream.workspace._fsm_write import write_fsm

    mesh = _mesh(_grid())
    with pytest.raises(InputArtifactError, match="trailing-edge group"):
        write_fsm(tmp_path / "a.fsm", mesh, template=MARKED)
    with pytest.raises(InputValueError, match="not an edge of the mesh"):
        write_fsm(tmp_path / "b.fsm", mesh, template=FRESH, trailing_edges=[(0, 11)])
    bad = Mesh(mesh.xyz, [(0, 1, 2, 3, 4)], ["WING"], [1], mesh.node_tags)
    with pytest.raises(InputValueError, match="only 3 or 4"):
        write_fsm(tmp_path / "c.fsm", bad, template=FRESH)
    (tmp_path / "d.fsm").write_text("x")
    with pytest.raises(InputArtifactError, match="exists"):
        write_fsm(tmp_path / "d.fsm", mesh, template=FRESH)
    assert not (tmp_path / "a.fsm").exists() and not (tmp_path / "b.fsm").exists()


# ---- section 5 acceptance and followers with shared-curve discovery ----------------------------

_KERNEL = {
    "inverted_count": 0,
    "source_distance_max_m": 1e-9,
    "source_distance_tolerance_m": 5e-4,
    "spacing_rules": {"failures": []},
}


def _controls(follows=("WING",)):
    return {
        "defaults": {"quality": {"max_aspect": 8.0, "max_skew_deg": 50.0}},
        "components": {
            "WING": {"role": "primary", "follows": []},
            "FAIR": {"role": "follower", "follows": list(follows)},
        },
    }


N_PSI, N_PHI = 8, 8


def _two_part_mesh(*, conforming=True):
    """A half torus cut by y = 0: free edges only on the symmetry plane, all quads.

    WING holds the first half of the big circle and FAIR the second; they share the ring at
    its middle node to node, or (not conforming) FAIR carries its own copy of that ring.
    """
    psi = np.linspace(0.0, np.pi, N_PSI + 1)
    phi = np.linspace(0.0, 2 * np.pi, N_PHI, endpoint=False)
    xyz = [
        [(3 + np.cos(f)) * np.cos(p), (3 + np.cos(f)) * np.sin(p), np.sin(f)]
        for p in psi
        for f in phi
    ]
    xyz = np.array(xyz)
    xyz[np.abs(xyz[:, 1]) < 1e-12, 1] = 0.0
    half = N_PSI // 2
    copy = len(xyz)
    if not conforming:
        xyz = np.vstack([xyz, xyz[half * N_PHI : (half + 1) * N_PHI] + [0.0, 0.0, 1e-3]])

    def node(i, j, owner):
        if owner == "FAIR" and i == half and not conforming:
            return copy + j % N_PHI
        return i * N_PHI + j % N_PHI

    cells, names = [], []
    for i in range(N_PSI):
        owner = "WING" if i < half else "FAIR"
        for j in range(N_PHI):
            cells.append(
                (
                    node(i, j, owner),
                    node(i + 1, j, owner),
                    node(i + 1, j + 1, owner),
                    node(i, j + 1, owner),
                )
            )
            names.append(owner)
    surfaces = [1 if n == "WING" else 2 for n in names]
    return Mesh(xyz, cells, names, surfaces, np.arange(len(xyz)))


def _by_id(checks):
    return {c["check"] if "check" in c else c["id"]: c for c in checks}


def test_p0570_gm11_shared_curves_are_discovered_on_the_realized_mesh():
    from pyflightstream.workspace._geometry_mesh_s1 import shared_curves

    ring = set(range(N_PSI // 2 * N_PHI, (N_PSI // 2 + 1) * N_PHI))
    edges = shared_curves(_two_part_mesh())[("FAIR", "WING")]
    assert len(edges) == N_PHI and {v for e in edges for v in e} == ring
    assert shared_curves(_two_part_mesh(conforming=False)) == {}


def test_p0570_gm11_follower_shares_a_curve_with_each_neighbour_yes_no():
    """YES: welded follower of WING. NO: a copied ring (no shared curve), an absent neighbour."""
    from pyflightstream.workspace._geometry_mesh_s1 import follower_checks

    yes = follower_checks(_two_part_mesh(), _controls())
    assert [c["status"] for c in yes] == ["passed"]
    gap = follower_checks(_two_part_mesh(conforming=False), _controls())
    assert gap[0]["status"] == "failed" and gap[0]["where"]["missing_neighbours"] == ["WING"]
    other = follower_checks(_two_part_mesh(), _controls(("WING", "FUS")))
    assert other[0]["where"]["missing_neighbours"] == ["FUS"]


def test_p0570_gm11_acceptance_table_yes_no():
    """YES: a conforming structured mesh passes every row. NO: each planted defect fails its row."""
    from pyflightstream.workspace._geometry_mesh_s1 import acceptance_checks

    mesh = _two_part_mesh()
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"FAIR": {}}))
    expected = {
        "mesh.inverted",
        "mesh.degenerate",
        "mesh.quality.aspect",
        "mesh.quality.skew",
        "mesh.node_to_node",
        "mesh.free_edges",
        "mesh.triangles.region",
        "mesh.triangles.fraction",
        "mesh.irregular_nodes",
        "mesh.spacing_laws",
        "mesh.source_distance",
        "mesh.follower.shared_curves",
    }
    assert set(checks) == expected
    assert all(c["status"] in {"passed", "skipped"} for c in checks.values()), checks
    assert checks["mesh.triangles.fraction"]["status"] == "skipped"
    # A triangle on the primary lifting surface.
    tri = _two_part_mesh()
    a, b, c, d = tri.cells[0]
    tri.cells[0:1] = [(a, b, c), (a, c, d)]
    tri.components.insert(0, "WING")
    tri.surfaces.insert(0, 1)
    bad = _by_id(acceptance_checks(tri, _KERNEL, _controls(), {"FAIR": {}}))
    assert bad["mesh.triangles.region"]["status"] == "failed"
    # A stretched cell beyond max_aspect, a free edge off y = 0, a spacing failure.
    stretched = _two_part_mesh()
    stretched.xyz[N_PHI + 3] *= [40.0, 40.0, 1.0]
    bad = _by_id(
        acceptance_checks(
            stretched, {**_KERNEL, "spacing_rules": {"failures": [1]}}, _controls(), {"FAIR": {}}
        )
    )
    assert bad["mesh.quality.aspect"]["status"] == "failed"
    assert bad["mesh.spacing_laws"]["status"] == "failed"
    gap = _by_id(acceptance_checks(_two_part_mesh(conforming=False), _KERNEL, _controls(), {}))
    assert gap["mesh.free_edges"]["status"] == "failed"
    over = _two_part_mesh()
    over.cells.append(over.cells[0])
    over.components.append("WING")
    over.surfaces.append(1)
    assert (
        _by_id(acceptance_checks(over, _KERNEL, _controls(), {}))["mesh.node_to_node"]["status"]
        == "failed"
    )


def test_p0570_gm11_irregular_node_inside_a_structured_surface_is_counted():
    from pyflightstream.workspace._geometry_mesh_s1 import acceptance_checks

    mesh = _two_part_mesh()
    centre = N_PHI + 1  # an interior node of the wing half
    cells = [
        c for c in mesh.cells if centre in c and mesh.components[mesh.cells.index(c)] == "WING"
    ]
    first = cells[0]
    i = first.index(centre)
    split = (
        [first[i], first[(i + 1) % 4], first[(i + 2) % 4]],
        [first[i], first[(i + 2) % 4], first[(i + 3) % 4]],
    )
    k = mesh.cells.index(first)
    mesh.cells[k : k + 1] = [tuple(split[0]), tuple(split[1])]
    mesh.components.insert(k, "WING")
    mesh.surfaces.insert(k, 1)
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"WING": {}, "FAIR": {}}))
    assert checks["mesh.irregular_nodes"]["status"] == "passed"  # inside a transition component
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"FAIR": {}}))
    assert checks["mesh.irregular_nodes"]["status"] == "failed"


# ---- sub-steps 1 to 3, 10: schema integration, plan and dry run -------------------------------

WB_CONFIG = {
    "components": {
        "FUS": {"type": "body"},
        "WING": {
            "type": "lifting_surface",
            "attach": {"parent": "FUS", "station": 0.4},
            "stations": [{"eta": 0.0, "section": {"kind": "naca", "code": "0012"}}],
        },
        "FAIRING": {
            "type": "wing_fuselage_fairing",
            "hosts": ["FUS", "WING"],
            "attach": {"parent": "FUS", "station": 0.0},
        },
    },
}


def _wb_controls(**mesh):
    return {
        "mesh": {"strategy": 1, "variant": "clean", **mesh},
        "defaults": {"lifting_surface": {"chordwise": {"ratio": 1.12}}},
        "components": {
            "FUS": {"type": "body", "role": "primary", "x_step_m": 0.0125, "azimuth_cells": 24},
            "WING": {
                "type": "lifting_surface",
                "role": "primary",
                "chordwise": {"cells": 40, "law": "geometric_cap", "hinge_rows": [0.7]},
                "spanwise": {"cells": 32, "law": "constant", "tip_cells": 5},
                "trailing_edge": "blunt",
            },
        },
    }


def test_p0570_gm11_dry_run_plans_counts_and_defaults_without_a_kernel(monkeypatch):
    """YES: the plan fills defaults, makes the fairing a follower and opens no kernel."""
    import builtins
    import sys

    from pyflightstream.workspace.geometry_pipeline import mesh_configuration

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "gmsh" or name.startswith("gmsh."):
            raise ImportError("a dry run must not load the kernel")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    record = mesh_configuration(WB_CONFIG, _wb_controls(), dry_run=True).record
    assert record["dry_run"] is True and record["members"] == ["FUS", "WING", "FAIRING"]
    wing, fus, fair = (record["components"][n] for n in ("WING", "FUS", "FAIRING"))
    assert (wing["chord_cells_per_side"], wing["span_cells"], wing["tip_cells"]) == (40, 32, 5)
    assert wing["hinge_rows"] == [0.7]
    assert fus["x_cells"] == 80 and fus["azimuth_cells"] == 24
    assert fair == {
        "type": "wing_fuselage_fairing",
        "role": "follower",
        "follows": ["FUS", "WING"],
        "fill": "quad_dominant",
    }
    assert record["transition_components"] == ["FAIRING"]
    assert any("FAIRING: no mesh table" in w for w in record["warnings"])


def test_p0570_gm11_plan_maps_tables_onto_the_kernel_controls():
    from pyflightstream.geometry import resolve_config
    from pyflightstream.workspace._geometry_mesh_s1 import plan_strategy1

    plan = plan_strategy1(resolve_config(WB_CONFIG), _wb_controls())
    lc = plan["kernel_controls"]["lifting_surface"]
    assert lc["chord_growth"] == 1.12  # from defaults.lifting_surface
    assert lc["hinge_rows"] == (0.7,)
    assert plan["kernel_controls"]["body"]["x_cells"] == 80  # 1.0 m / 0.0125 m


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda c: c["components"]["WING"]["spanwise"].pop("law"), "E15"),
        (lambda c: c["components"].update(TAIL={"role": "primary"}), None),
        (lambda c: c["components"]["WING"]["chordwise"].update(law="cosine"), "geometric_cap"),
        (lambda c: c["components"]["WING"]["spanwise"].update(root_cells=2), "root_cells"),
        (
            lambda c: (
                c["components"]["FUS"].update(azimuth_rule={})
                or c["components"]["FUS"].pop("azimuth_cells")
            ),
            "azimuth_rule",
        ),
        (lambda c: c["mesh"].update(configuration="NOPE"), "unknown"),
        (lambda c: c["mesh"].update(strategy=2), "full-grid"),
        (lambda c: c["components"].update(FAIRING={"role": "follower", "follows": "TAIL"}), "E01"),
    ],
)
def test_p0570_gm11_plan_refuses_by_name_and_warns_w01(edit, match):
    from pyflightstream.geometry import resolve_config
    from pyflightstream.workspace._geometry_mesh_s1 import plan_strategy1

    controls = _wb_controls()
    edit(controls)
    if match is None:  # a table outside the configuration warns W01 and is ignored
        plan = plan_strategy1(resolve_config(WB_CONFIG), controls)
        assert any(w.startswith("W01: TAIL") for w in plan["warnings"])
        return
    with pytest.raises(InputValueError, match=match):
        plan_strategy1(resolve_config(WB_CONFIG), controls)


def test_p0570_gm11_e04_reads_the_iges_component_names(tmp_path):
    """YES: names from the IGES 406 form 15 properties. NO: a table naming no IGES component."""
    from pyflightstream.geometry import resolve_config
    from pyflightstream.workspace._geometry_mesh_s1 import iges_names, plan_strategy1

    def directory(seq, entity, pointer, form):
        first = f"{entity:8d}{pointer:8d}" + f"{0:8d}" * 6 + "00000200"
        second = f"{entity:8d}" + f"{0:8d}" * 2 + f"{1:8d}{form:8d}" + f"{0:8d}" * 3 + " " * 8
        return [f"{first:<72}D{seq:7d}", f"{second:<72}D{seq + 1:7d}"]

    names = ["FUS", "WING"]
    lines = [f"{'':<72}S{1:7d}", f"{'1H,,1H;;':<72}G{1:7d}"]
    for k in range(len(names)):
        lines += directory(2 * k + 1, 406, k + 1, 15)
    for k, name in enumerate(names):
        lines.append(f"{f'406,1,{len(name)}H{name};':<64}{2 * k + 1:8d}P{k + 1:7d}")
    lines.append(f"{'S      1G      1D      4P      2':<72}T{1:7d}")
    iges = tmp_path / "wb.igs"
    iges.write_text("\n".join(lines) + "\n", encoding="ascii")
    assert iges_names(iges) == {"FUS", "WING"}
    resolved = resolve_config(WB_CONFIG)
    with pytest.raises(InputValueError, match="E04.*FAIRING"):
        plan_strategy1(resolved, _wb_controls(iges="wb.igs"), base=tmp_path)
    assert plan_strategy1(resolved, _wb_controls())["members"] == ["FUS", "WING", "FAIRING"]


def test_p0570_gm11_mesh_verb_dry_run_exits_0_with_counts_and_writes_nothing(tmp_path, capsys):
    import tomllib

    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry.stages import write_config
    from pyflightstream.workspace.cli import main

    config = tmp_path / "wb.toml"
    write_config(resolve_config(WB_CONFIG), config)
    controls = tmp_path / "mesh.toml"
    controls.write_text(
        '[mesh]\nstrategy = 1\n\n[components.FUS]\ntype = "body"\nx_cells = 80\n\n'
        '[components.WING]\ntype = "lifting_surface"\n'
        'chordwise = { cells = 40, law = "geometric_cap" }\n'
        'spanwise = { cells = 32, law = "constant" }\nmystery = 1\n',
        encoding="utf-8",
    )
    tomllib.loads(controls.read_text(encoding="utf-8"))
    before = sorted(p.name for p in tmp_path.iterdir())
    code = main(
        [
            "geometry",
            "mesh",
            str(config),
            "--controls",
            str(controls),
            "--dry-run",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    out = capsys.readouterr()
    assert code == 0
    assert '"span_cells": 32' in out.out and '"x_cells": 80' in out.out
    assert "WING.mystery: unknown key ignored" in out.err
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    bad = tmp_path / "bad.toml"
    bad.write_text(
        controls.read_text(encoding="utf-8").replace(', law = "constant"', ""), encoding="utf-8"
    )
    assert main(["geometry", "mesh", str(config), "--controls", str(bad), "--dry-run"]) == 2
    assert "E15" in capsys.readouterr().err


# ---- sub-steps 7 and 8: hinge rows in the chord law, TE groups and collapse --------------------


def test_p0570_gm11_hinge_rows_pin_the_chord_law_of_the_route():
    """YES: the global chord law holds 0.7 exactly with the cell count kept. NO: no hinge."""
    from pyflightstream.geometry._mesh_rules import DEFAULT_CONTROLS, geometric_cap, pin_fractions

    lc = dict(DEFAULT_CONTROLS["lifting_surface"])
    law = geometric_cap(lc["chord_cells"], lc["chord_growth"], growth_until=lc["growth_until"])
    assert not np.any(np.isclose(law, 0.7, rtol=0, atol=1e-12))
    pinned = pin_fractions(law, [0.7])
    assert len(pinned) == len(law) and np.any(pinned == 0.7) and np.all(np.diff(pinned) > 0)
    with pytest.raises(InputValueError, match="hinge rows"):
        pin_fractions(law, [1.2])


def _te_strip():
    """A strip of 2 span cells: upper skin, a 2-cell base (upper, lower half), lower skin."""
    rows = [(0.9, 0.02), (1.0, 0.01), (1.0, 0.0), (1.0, -0.01), (0.9, -0.02)]
    xyz = np.array([[x, y, z] for y in (0.0, 0.5, 1.0) for x, z in rows])
    fam = ["upper_aft", "trailing_upper", "trailing_lower", "lower_aft"]
    cells, surfaces = [], []
    for j in range(2):
        for i in range(4):
            a = j * 5 + i
            cells.append((a, a + 1, a + 6, a + 5))
            surfaces.append(i + 1)
    mesh = Mesh(xyz, cells, ["WING"] * len(cells), surfaces, np.arange(len(xyz)) + 100)
    return mesh, {k + 1: f for k, f in enumerate(fam)}


def test_p0570_gm11_te_groups_find_the_base_across_and_the_te_lines():
    from pyflightstream.workspace._geometry_mesh_s1 import cells_across, trailing_edge_groups

    mesh, families = _te_strip()
    base, groups, lines = trailing_edge_groups(mesh, families, "WING")
    assert base == {1, 2, 5, 6}
    assert groups == [[1, 2, 3], [6, 7, 8], [11, 12, 13]]
    assert lines == [(1, 6), (3, 8), (6, 11), (8, 13)]
    assert cells_across(groups)["status"] == "failed"  # two cells across, the rule says one
    assert cells_across([[1, 3]])["status"] == "passed"


def test_p0570_gm11_collapse_groups_and_reduces_a_soft_neighbour():
    from pyflightstream.workspace._geometry_mesh_s1 import (
        collapse_trailing_edge,
        trailing_edge_groups,
    )

    mesh, families = _te_strip()
    base, groups, _ = trailing_edge_groups(mesh, families, "WING")
    collapsed, checks = collapse_trailing_edge(mesh, groups, base, tolerance_m=0.011)
    assert len(collapsed.cells) == 4 and all(c["status"] == "passed" for c in checks)
    with pytest.raises(InputValueError, match="distance"):
        collapse_trailing_edge(mesh, groups, base, tolerance_m=0.009)
    # A cap cell holding two nodes of one TE group: refused, or a triangle when declared soft.
    capped = Mesh(
        np.vstack([mesh.xyz, [[1.0, 1.2, 0.01], [1.0, 1.2, -0.01]]]),
        [*mesh.cells, (11, 13, 16, 15)],
        [*mesh.components, "WING"],
        [*mesh.surfaces, -1],
        np.arange(len(mesh.xyz) + 2) + 100,
    )
    with pytest.raises(InputValueError, match="would degenerate"):
        collapse_trailing_edge(capped, groups, base, tolerance_m=0.011)
    result, _ = collapse_trailing_edge(
        capped, groups, base, tolerance_m=0.011, reducible=frozenset({8})
    )
    assert len(result.cells[-1]) == 3


# ---- strategy 1 on the committed WB fixture (kernel) -------------------------------------------


@pytest.fixture(scope="module")
def wb_run(tmp_path_factory):
    from tests.tier1_offline._kernel_support import kernel_or_skip

    kernel_or_skip()
    from pyflightstream.workspace.geometry_pipeline import mesh_configuration

    out = tmp_path_factory.mktemp("wb")
    controls = _wb_controls()
    del controls["components"]["WING"]["chordwise"]["hinge_rows"]
    controls["defaults"]["quality"] = {"max_aspect": 30.0, "max_skew_deg": 60.0}
    return mesh_configuration(
        WB_CONFIG, controls, out=out, descriptor="wb", fsm_template=FRESH
    ), out


def test_p0570_gm11_wb_strategy1_writes_mesh_record_and_fsm(wb_run):
    """The WB fixture runs end to end: OBJ, FSM and record written, and the FSM reads back."""
    import json

    from pyflightstream._fsm import boundary_names, surface_mesh
    from pyflightstream.geometry._mesh_topology import read_obj
    from pyflightstream.workspace._fsm_write import paired_triangles

    result, out = wb_run
    assert sorted(Path(p).name for p in result.written.values()) == [
        "wb.fsm",
        "wb.mesh.json",
        "wb.obj",
    ]
    record = json.loads((out / "wb.mesh.json").read_text(encoding="utf-8"))
    assert record["members"] == ["FUS", "WING", "FAIRING"]
    assert set(record["outputs"]) == {"obj", "fsm"}
    assert len(read_obj(out / "wb.obj").cells) == len(result.mesh.cells)
    vertices, triangles = surface_mesh(out / "wb.fsm")
    assert len(vertices) == len(result.mesh.xyz)
    assert len(triangles) == len(paired_triangles(result.mesh)[0])
    assert boundary_names(out / "wb.fsm") == ("FUS", "WING", "FAIRING")


def test_p0570_gm11_wb_strategy1_measures_every_acceptance_row(wb_run):
    """Every row of the strategy 1 table is measured; the rows this route meets pass.

    ``accepted`` follows from the rows: the kernel's wing-fuselage ring still puts
    triangles on fuselage and wing faces, which the settled rules forbid (reported).
    """
    result, _ = wb_run
    checks = {c["id"]: c for c in result.record["checks"]}
    assert set(checks) >= {
        "mesh.inverted",
        "mesh.degenerate",
        "mesh.quality.aspect",
        "mesh.quality.skew",
        "mesh.node_to_node",
        "mesh.free_edges",
        "mesh.triangles.region",
        "mesh.irregular_nodes",
        "mesh.spacing_laws",
        "mesh.source_distance",
        "mesh.follower.shared_curves",
        "mesh.surfaces_only",
        "mesh.trailing_edge_one_quad",
    }
    for row in (
        "mesh.node_to_node",
        "mesh.free_edges",
        "mesh.source_distance",
        "mesh.follower.shared_curves",
        "mesh.surfaces_only",
    ):
        assert checks[row]["status"] == "passed", checks[row]
    assert result.record["accepted"] is all(c["status"] != "failed" for c in checks.values())


# ---- delta F.2: junction blocks on the layout sidecar interface (G16 supplies the sidecar) -----


def test_p0570_gm11_junction_blocks_classify_untouched_curved_and_quad_dominant():
    """YES and NO: an untouched block, a root single valued in u, and a closed footprint."""
    from pyflightstream.workspace._geometry_mesh_s1 import junction_blocks

    faces = {"FUS.p0": {"u": [0.0, 0.5, 1.0], "v": [0.0, 1.0]}}
    s = np.linspace(0.05, 0.45, 9)
    root = np.c_[s, 0.3 + 0.1 * s]  # v as a function of u inside block 0
    blocks = junction_blocks(faces, {"FUS.p0": [root]})["FUS.p0"]
    assert [b["kind"] for b in blocks] == ["transfinite_curved", "transfinite"]
    assert blocks[0]["single_valued_in"] == "u"
    t = np.linspace(0.0, 2 * np.pi, 33)
    footprint = np.c_[0.75 + 0.1 * np.cos(t), 0.5 + 0.2 * np.sin(t)]
    blocks = junction_blocks(faces, {"FUS.p0": [footprint]})["FUS.p0"]
    assert [b["kind"] for b in blocks] == ["transfinite", "quad_dominant"]
    assert [b["kind"] for b in junction_blocks(faces, {})["FUS.p0"]] == ["transfinite"] * 2
