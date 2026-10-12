"""P0400-FFPLAN: the plan reuses, adds, and refuses only the impossible (FR-455).

Every case is a synthetic box mesh imported raw (one family ``W``) with a
synthetic reference; the scripts are built offline by the public builder.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, PprocSpec, ReferenceData
from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.cases.farfield_inputs import applies, resolve_farfield
from pyflightstream.cases.workflows import build_script, row_outputs
from pyflightstream.post import farfield_products
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import read_raw_mesh_conditions
from pyflightstream.workspace.sidecars import read_mesh_import
from tests.tier1_offline.test_workflows import FIXTURE_ROTOR, steady_case

_VERTICES = [(x, y, z) for x in (0.0, 1.0) for y in (-2.0, 2.0) for z in (-0.1, 0.1)]
_FACES = [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]


def _box(root: Path) -> Path:
    mesh = root / "box.obj"
    mesh.write_text(
        "g W\n"
        + "".join(f"v {x} {y} {z}\n" for x, y, z in _VERTICES)
        + "".join("f " + " ".join(map(str, face)) + "\n" for face in _FACES),
        encoding="utf-8",
    )
    (root / "box.boundaries.toml").write_text(
        '[import]\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n', encoding="utf-8"
    )
    return mesh


def _case(root: Path, farfield: dict, **pproc: object):
    mesh = _box(root)
    sidecar = root / "box.boundaries.toml"
    spec = PprocSpec.model_validate({"groups": {"1": "all"}, "farfield": farfield, **pproc})
    case = steady_case(geometry=str(mesh)).model_copy(
        update={
            "inventory": ("W",),
            "mesh_import": read_mesh_import(sidecar),
            "raw_mesh_conditions": read_raw_mesh_conditions(sidecar),
            "reference": ReferenceData(
                area=4.0, length=1.0, span_m=4.0, moment_point_m=(0.25, 0.0, 0.0)
            ),
            "rotors": {FIXTURE_ROTOR.alias: FIXTURE_ROTOR.model_copy(update={"x_m": 0.5})},
            "pproc": spec,
            "pproc_id": "p9",
        }
    )
    return case.model_copy(update={"outputs": row_outputs(case, "steady")})


def _script(case) -> str:
    script = Script("26.124")
    build_script(case, script)
    return script


def _distributions(text: str) -> int:
    return text.splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION")


_SECTIONS = {"families": "all", "trefftz": {"variant": "sections", "stations": 20}}
_DECLARED = {"sections": {"distributions": [{"families": ["W"], "frame": "MRP", "planes": ["XZ"]}]}}


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_a_missing_distribution_is_added(tmp_path):
    """P0400-FFPLAN (FR-455 R3): no declared distribution, one added over W, 40 stations."""
    case = _case(tmp_path, _SECTIONS)
    text = _script(case).render()
    assert _distributions(text) == 1
    block = text.splitlines()[text.splitlines().index("NEW_SURFACE_SECTION_DISTRIBUTION") :]
    assert "40" in " ".join(block[:6]), "a full model lays stations per side times two"
    assert any(name.endswith("_sloads.txt") for name in case.outputs)


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_a_declared_distribution_is_reused_once(tmp_path):
    """P0400-FFPLAN (FR-455 R2): the declared XZ distribution over W is reused, never doubled."""
    case = _case(tmp_path, _SECTIONS, **_DECLARED)
    assert _distributions(_script(case).render()) == 1


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_the_wake_is_switched_on(tmp_path):
    """P0400-FFPLAN (FR-455 R3): Trefftz B adds the VTK export with the wake switch."""
    case = _case(tmp_path, {"families": "all", "trefftz": {"variant": "wake"}})
    assert any(name.endswith(".vtk") for name in case.outputs)
    text = _script(case).render()
    assert "SET_VTK_EXPORT_VARIABLES -1 ENABLE" in text
    (tmp_path / "plain").mkdir()
    plain = _case(tmp_path / "plain", _SECTIONS)
    assert "ENABLE" not in [
        line.split()[-1] for line in _script(plain).render().splitlines() if "VTK_EXPORT" in line
    ]


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_the_plane_is_added_as_probes(tmp_path):
    """P0400-FFPLAN (FR-455 R3, FR-453 R4): the C plane, behind the body, normal to the stream."""
    farfield = {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": 0.25}}
    case = _case(tmp_path, farfield)
    script = _script(case)
    assert len(script.probe_points) == 7 * 5
    xs = {round(point[1], 5) for point in script.probe_points}
    assert xs == {round(1.0 + 0.25 * 4.0, 5)}, "the plane stands distance_bref BREF aft"
    assert script.render().count("NEW_PROBE_POINT") == 35
    assert any(name.endswith("_probes.txt") for name in case.outputs)


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_a_declared_lattice_is_reused(tmp_path):
    """P0400-FFPLAN (FR-455 R2): an identical declared lattice is not emitted twice."""
    lattice = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16, "r_inner": 0.5}
    added = _script(_case(tmp_path, {"families": "all", "ledgers": dict(lattice, m_max=2)}))
    other = tmp_path / "declared"
    other.mkdir()
    reused = _script(
        _case(
            other,
            {"families": "all", "ledgers": dict(lattice, m_max=2)},
            probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [lattice]}],
        )
    )
    count = LatticeShape.model_validate(lattice).build(1.0).point_count
    assert len(added.probe_points) == len(reused.probe_points) == count


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_a_frame_lattice_is_laid_from_the_frame(tmp_path):
    """P0400-FFPLAN (FR-454 R1): a lattice of the MRP frame, along its x axis, in metres."""
    ledgers = {
        "frame": "MRP",
        "tip_radius_m": 0.5,
        "stations": [2.0],
        "n_r": 2,
        "n_psi": 16,
        "m_max": 2,
    }
    script = _script(_case(tmp_path, {"families": "all", "ledgers": ledgers}))
    shape = LatticeShape.model_validate({k: v for k, v in ledgers.items() if k != "m_max"})
    assert len(script.probe_points) == shape.build(0.5).point_count
    planes = script.probe_points[: 2 * 16]
    assert {round(point[1], 5) for point in planes} == {0.25 + 2.0 * 0.5}


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_an_added_point_inside_the_body_is_refused(tmp_path):
    """P0400-FFPLAN (FR-455 R7): a lattice station inside the box is refused, naming the remedy."""
    pytest.importorskip("rtree")
    farfield = {
        "families": "all",
        "ledgers": {"rotor": "ROTOR", "stations": [0.0], "n_r": 2, "n_psi": 16, "m_max": 2},
    }
    with pytest.raises(CampaignConfigError, match="inside the body") as caught:
        _script(_case(tmp_path, farfield))
    assert "r_inner and stations" in str(caught.value)


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_a_false_export_is_turned_on_with_a_warning(tmp_path):
    """P0400-FFPLAN (FR-455 R3): ``[exports] sectional_loads = false`` is turned on, warned."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        case = _case(tmp_path, _SECTIONS, exports={"sectional_loads": False})
    assert any(name.endswith("_sloads.txt") for name in case.outputs)
    assert any(
        issubclass(w.category, PyflightstreamWarning)
        and "sectional_loads = false" in str(w.message)
        for w in caught
    )


def _resolve(**overrides: object):
    spec = PprocSpec.model_validate(
        {
            "groups": {"1": "all"},
            "farfield": {
                "families": "all",
                "trefftz": {"variant": ["sections", "plane"]},
                "ledgers": {"rotor": "ROTOR"},
            },
        }
    ).farfield
    arguments: dict[str, object] = {
        "run_type": "steady",
        "covered_families": {"W"},
        "selected_families": ["W"],
        "exports": {},
        "declares_lattice": False,
        "declares_plane": False,
        "coupled": False,
        "admits_probes": True,
        "has_command": lambda command: True,
    }
    arguments.update(overrides)
    return resolve_farfield(spec, **arguments)


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_the_three_states():
    """P0400-FFPLAN (FR-455 R2, R3, R5): reused, added and not applicable, each with its source."""
    resolution = _resolve()
    assert resolution.state_of("trefftz:sections") == "ready"
    states = {(item.analysis, item.input): item.state for item in resolution.inputs}
    assert states[("trefftz:sections", "section_distribution")] == "reused"
    assert states[("trefftz:plane", "probe_points")] == "added"
    rotor = _resolve(run_type="unsteady_rotor")
    assert rotor.state_of("trefftz:sections") == "not_applicable"
    assert not rotor.refused
    assert {"inputs"} == set(resolution.as_record())


@pytest.mark.parametrize(
    ("overrides", "analysis", "words"),
    [
        (
            {"has_command": lambda command: command != "EXPORT_SURFACE_SECTIONAL_LOADS"},
            "trefftz:sections",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
        ),
        ({"admits_probes": False, "coupled": True}, "trefftz:plane", "takes no probes"),
        ({"selected_families": []}, "ledgers", "names no family"),
        ({"coupled": True, "covered_families": set()}, "trefftz:sections", "exactly one"),
    ],
)
@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_only_the_impossible_is_refused(overrides, analysis, words):
    """P0400-FFPLAN (FR-455 R6): the build, the row type, the families, the coupled cut."""
    resolution = _resolve(**overrides)
    refused = [item for item in resolution.refused if item.analysis == analysis]
    assert refused and words in refused[0].reason
    assert resolution.state_of(analysis) == "refused"


@pytest.mark.requirement("FR-455")
def test_p0400_ffplan_post_resolves_with_the_same_function():
    """P0400-FFPLAN (FR-455 R4): post reads applicability through the plan's one function."""
    assert farfield_products.applies is applies
