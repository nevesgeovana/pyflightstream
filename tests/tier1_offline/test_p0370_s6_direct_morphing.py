"""Tier 1: direct mesh morphing on a quasi-steady rotor sector (FR-341, S6 of 0.37.0).

``morphing = "direct"`` in the ``[config]`` table of an FSI input replaces the
structural-node import of the sector route with the solver's direct mesh
morphing, RIGID aerodynamic nodes, in the frame the blade's sections are cut
in: the two lines the licensed arm of build 26.125 changed against the
package's script, and nothing else. The structural program then writes one
displacement per vertex of the aerodynamic nodes file instead of one per
structural node. Every other route, and every configuration that does not
choose a route, is byte-identical to 0.36.0.

Each expected value is derived from the rigid-section kinematics the mapped
route encodes (w + theta d along the section normal), the linear blend between
stations and the relaxation d_new = d_old + lambda (d_calc - d_old), never read
off the implementation. Every test was proved by a mutant of the code it holds,
reverted.
"""

from __future__ import annotations

import hashlib
import math
import re
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    MeshImport,
    PprocSpec,
    RawMeshConditions,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.fsi_workspace import (
    DIRECT_MORPHING_COMMAND,
    direct_morphing_refusal,
    validate_workspace_fsi,
)
from pyflightstream.cases.workflows import (
    QSTEADY_ROTOR,
    WORKFLOW_KEY,
    build_script,
    effective_fsi_config,
)
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi._direct_morphing import AERO_NODES_FILE
from pyflightstream.fsi.config import (
    BladeProperties,
    FsiConfig,
    PhaseSchedule,
    config_sha256,
    dump_config,
)
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.script import Script
from pyflightstream.workspace.fsi_setup import FSI_TEMPLATE, resolve_fsi_setup
from tests.tier1_offline.conftest import make_uniform_blade_config

ROTOR = RotorBlock(
    alias="PROP",
    axis="X",
    diameter_m=2.0,
    families_blades=["Blade1", "Blade2", "Blade3"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Z"),
)

#: The coupling block of the licensed arm Q4 on build 26.125 (the sector
#: route with the structural-node import replaced by the direct command,
#: RIGID nodes), from ``AEROELASTIC_RBF_TYPE`` to the coupling iterations.
#: The arm's two instrument edits are restored to the package's lines (the
#: structural program the arm swapped for its imposer, and the 4-iteration
#: cap it set); the arm's frame 3 is the frame its sections were cut in, as
#: ``{frame}`` is here, and its interpreter path is ``{interpreter}``.
PROBE_ARM_BLOCK = """\
AEROELASTIC_RBF_TYPE MULTI_QUADRATIC
DELETE_AEROELASTIC_STRUCTURAL_NODES
ASSIGN_AEROELASTIC_SURFACES 1
2

ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1
{frame}

SET_DIRECT_AEROELASTIC_MESH_MORPHING {frame} RIGID

SET_AEROELASTIC_WORKING_DIRECTORY
.

SET_AEROELASTIC_POST_PROCESSING_SCRIPT
fsi_post.txt

SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND
{interpreter} "fsi_callback.py"

SET_AEROELASTIC_ITERATIONS 50"""

#: The sha256 of the mapped sector row's rendered script (the interpreter and
#: the temporary folder masked) and of its staged files with the staged
#: configuration, measured with the 0.37.0 tree before FR-341 entered it
#: (rel/0-37 at cb59b941) on 26.124.
MAPPED_SCRIPT_SHA256 = "94edaf5311d2f5af0b19b79804e5e0ac4850dc7666673a1ccef06fd44faf669d"
MAPPED_STAGED_SHA256 = "300be9de64bef25749161ac99310fb80ab2a59500dff3a5fa30cfd91c5101661"


def _sector(tmp_path: Path, *, morphing: str | None = None, **variables) -> SimCase:
    """A periodic sector of a three-blade rotor, blade one meshed on +z, coupled."""
    geometry = tmp_path / "blade.obj"
    geometry.write_text("o Blade1\nv 0 0 0.2\nv 0 .1 .2\nv 0 0 1.2\nf 1 2 3\n")
    config = make_uniform_blade_config(blade_count=1)
    if morphing is not None:
        config = FsiConfig.model_validate({**config.model_dump(), "morphing": morphing})
    stated = {
        WORKFLOW_KEY: QSTEADY_ROTOR,
        "VELOCITY": "30.0",
        "RPM": "1200",
        "SYMMETRY": "PERIODIC",
        "PERIODIC_COPIES": "3",
        **variables,
    }
    return SimCase(
        sim_id="9001",
        aircraft="Prop",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=QSTEADY_ROTOR,
        outputs=["DP.txt", "DP_log.txt"],
        variables={key: value for key, value in stated.items() if value is not None},
        point={"alpha": 0.0},
        rotors={ROTOR.alias: ROTOR},
        reference=ReferenceData(area=3.14, length=0.2),
        geometry=str(geometry),
        mesh_import=MeshImport(units="METER"),
        raw_mesh_conditions=RawMeshConditions.model_validate(
            {"trailing_edges": {"route": "detect"}}
        ),
        inventory=("Blade1",),
        fsi=config,
        pproc=PprocSpec.model_validate(
            {
                "sections": {
                    "count": 5,
                    "include_symmetry": False,
                    "distributions": [{"families": ["Blade1"], "frame": "SMRP", "planes": ["XY"]}],
                }
            }
        ),
    )


def _render(case: SimCase, build: str) -> tuple[str, Script]:
    script = Script(build)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render(), script


def _coupling_block(rendered: str) -> list[str]:
    """The coupling block's lines, blank lines left out."""
    lines = rendered.splitlines()
    start = lines.index("AEROELASTIC_RBF_TYPE MULTI_QUADRATIC")
    end = next(i for i, line in enumerate(lines) if line.startswith("SET_AEROELASTIC_ITERATIONS"))
    return [line for line in lines[start : end + 1] if line]


_INTERPRETER = re.compile(r'^(".*") "fsi_callback.py"$', re.M)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- the script --


def test_a_direct_sector_row_renders_the_licensed_arm_lines_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): the direct row is the arm Q4 of 26.125, line for line.

    Blank lines aside: the arm's edit kept the blank line that followed the node
    file's name, and the emitter writes none after a one-line command. Against
    the mapped row of the same case, the import, its node file and that blank
    line give way to the one direct line, in the frame the sections are cut in,
    RIGID; everything else, the staged files included, is the same.
    """
    mapped, mapped_script = _render(_sector(tmp_path), "26.125")
    direct, direct_script = _render(_sector(tmp_path, morphing="direct"), "26.125")
    frame = re.search(r"^IMPORT_AEROELASTIC_STRUCTURAL_NODES (\d+) DISABLE$", mapped, re.M)
    assert frame is not None
    interpreter = _INTERPRETER.search(direct)
    assert interpreter is not None
    arm = PROBE_ARM_BLOCK.format(frame=frame.group(1), interpreter=interpreter.group(1))
    assert _coupling_block(direct) == [line for line in arm.splitlines() if line]
    replaced = mapped.replace(
        f"IMPORT_AEROELASTIC_STRUCTURAL_NODES {frame.group(1)} DISABLE\nfsi_nodes.csv\n\n",
        f"{DIRECT_MORPHING_COMMAND} {frame.group(1)} RIGID\n",
    )
    assert replaced != mapped and direct == replaced
    assert direct_script.pending_input_files == mapped_script.pending_input_files
    staged = effective_fsi_config(_sector(tmp_path, morphing="direct"))
    assert staged is not None and staged.morphing == "direct"
    assert '"morphing": "direct"' in staged.model_dump_json(indent=2)


def test_a_row_that_chooses_no_route_is_byte_identical_to_0_36_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): mapped, stated or not, renders and stages as before.

    The hashes were measured on the tree before FR-341 entered it; the staged
    configuration carries no ``morphing`` key and hashes as it did.
    """
    for case in (_sector(tmp_path), _sector(tmp_path, morphing="mapped")):
        rendered, script = _render(case, "26.124")
        masked = _INTERPRETER.sub('"PY" "fsi_callback.py"', rendered).replace(str(tmp_path), "TMP")
        assert _sha256(masked) == MAPPED_SCRIPT_SHA256
        staged = effective_fsi_config(case)
        assert staged is not None
        payload = "".join(
            f"{name}\n{content}" for name, content in sorted(script.pending_input_files.items())
        )
        assert _sha256(payload + staged.model_dump_json(indent=2)) == MAPPED_STAGED_SHA256
        assert "morphing" not in staged.model_dump_json()
    plain = make_uniform_blade_config(blade_count=1)
    stated = FsiConfig.model_validate({**plain.model_dump(), "morphing": "mapped"})
    assert config_sha256(stated) == config_sha256(plain)


def test_the_fsi_input_states_the_route_in_its_config_table_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): ``[config] morphing`` reaches the staged configuration."""
    text = FSI_TEMPLATE.replace("blade_count = 2", 'blade_count = 1\nmorphing = "direct"')
    assert tomllib.loads(text)["config"]["morphing"] == "direct"
    source = tmp_path / "f001.toml"
    source.write_text(text, encoding="utf-8")
    resolved = resolve_fsi_setup(source)
    assert resolved.effective.morphing == "direct"
    assert resolved.provenance()["effective"]["morphing"] == "direct"


# ----------------------------------------------------------- the refusals --


def test_deflected_nodes_are_refused_naming_the_measured_gap_fr_341():
    """P0370-S6-DIRECT-MORPHING (FR-341): DEFLECTED is refused where the configuration is read."""
    plain = make_uniform_blade_config(blade_count=1)
    with pytest.raises(ValidationError) as caught:
        FsiConfig.model_validate({**plain.model_dump(), "morphing": "direct_deflected"})
    said = str(caught.value)
    assert "DEFLECTED" in said and "already deflected" in said and "morphing = 'direct'" in said
    assert "RPT-" not in said


@pytest.mark.parametrize(
    ("workflow", "words"),
    [
        ("unsteady_rotor", "the azimuth it was imported at"),
        ("steady", "the row runs steady"),
        ("unsteady", "the row runs unsteady"),
    ],
)
def test_direct_morphing_outside_a_quasi_steady_sector_is_refused_at_plan_fr_341(
    tmp_path, workflow, words
):
    """P0370-S6-DIRECT-MORPHING (FR-341): another workflow hears the direct refusal first."""
    case = _sector(tmp_path, morphing="direct")
    with pytest.raises(CampaignConfigError) as caught:
        validate_workspace_fsi(case, Script("26.124"), workflow=workflow, continuation=False)
    said = str(caught.value)
    assert words in said and "leave morphing out" in said.lower() and "RPT-" not in said
    mapped = _sector(tmp_path)
    assert direct_morphing_refusal(mapped, workflow=workflow, version="26.124") is None


def test_a_fixed_wing_cannot_choose_direct_morphing_fr_341():
    """P0370-S6-DIRECT-MORPHING (FR-341): a [config.wing] structure with direct is refused."""
    plain = make_uniform_blade_config(blade_count=1).model_dump()
    wing = {"self_weight": True, "span_axis": "+Y", "origin_m": (0.0, 0.0, 0.0)}
    with pytest.raises(ValidationError, match="fixed wing"):
        FsiConfig.model_validate({**plain, "wing": wing, "morphing": "direct"})
    assert FsiConfig.model_validate({**plain, "wing": wing}).wing is not None


def test_a_build_that_does_not_run_the_command_is_refused_at_plan_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): 26.124 answers the command as unrecognised."""
    with pytest.raises(CampaignConfigError) as caught:
        _render(_sector(tmp_path, morphing="direct"), "26.124")
    said = str(caught.value)
    assert DIRECT_MORPHING_COMMAND in said and "26.124 does not" in said
    assert "leave morphing out" in said and "RPT-" not in said
    _render(_sector(tmp_path), "26.124")


def test_a_wheel_choosing_direct_morphing_is_refused_at_plan_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): a whole wheel takes no FSI, direct or mapped."""
    wheel = _sector(tmp_path, morphing="direct", SYMMETRY=None, PERIODIC_COPIES=None)
    for build in ("26.124", "26.125"):
        with pytest.raises(CampaignConfigError) as caught:
            _render(wheel, build)
        said = str(caught.value)
        assert "RPT-" not in said
        assert "Solve a periodic sector" in said or "leave morphing out" in said


# -------------------------------------------------- the structural program --

LOADS = (
    Path(__file__).parent / "fixtures" / "fsi" / "FS_SurfaceSection_Loads_call0002.txt"
).read_text(encoding="utf-8")
STEADY_LOADS = LOADS.replace("     Time increment (sec)                        .004\n", "")
PITCH_DEG = 8.0


def _rotating_config(morphing: str) -> FsiConfig:
    """A stiff turning blade over the fixture's sections (0.29 to 1.81 m), pitch 8 deg."""
    n = 11
    blade = BladeProperties(
        station_radii_m=list(np.linspace(0.25, 1.85, n)),
        chord_m=list(np.linspace(0.26, 0.11, n)),
        mass_per_length_kg_per_m=[5.0] * n,
        inertia_major_kg_m=[1.0e-3] * n,
        inertia_minor_kg_m=[2.0e-4] * n,
        bending_stiffness_n_m2=[5.0e5] * n,
        torsion_stiffness_n_m2=[2.0e5] * n,
        elastic_axis_offset_chordwise_m=[0.01] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[PITCH_DEG] * n,
    )
    return FsiConfig(
        blade_count=1,
        omega_rad_per_s=50.0,
        blade=blade,
        phases=PhaseSchedule(coupling_relaxation=0.4),
        morphing=morphing,
    )


def _stage(run_dir: Path, morphing: str) -> FsiConfig:
    cfg = _rotating_config(morphing)
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_config(cfg, run_dir / driver.CONFIG_FILE)
    family = SectionFamilyMap(
        families=[
            SectionFamily(name="blade_1", count=50),
            SectionFamily(name="hub", count=50, is_blade=False),
        ]
    )
    (run_dir / driver.FAMILY_MAP_FILE).write_text(family.model_dump_json(indent=2) + "\n")
    (run_dir / driver.QUASI_STEADY_ROTOR_FILE).write_text("marker\n")
    return cfg


def _call(run_dir: Path, iteration: int):
    loads = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", STEADY_LOADS)
    (run_dir / driver.LOADS_FILE).write_text(loads, encoding="utf-8")
    return driver.coupling_step(run_dir)


def _write_aero_nodes(run_dir: Path, points: np.ndarray) -> None:
    """The aerodynamic nodes file as the solver writes it: a header, then 9 columns a row."""
    header = (
        "     Aeroelastic coordinate system:              ROTOR_SMRP\n"
        f"     Total elastic aerodynamic nodes:            {len(points)}\n"
        "     X, Y, Z, nx, ny, nz, Fx, Fy, Fz\n"
    )
    rows = [
        ", ".join(f"{v: .16E}" for v in (*point, 0.0, 0.0, 1.0, 1.0e-3, 2.0e-3, 3.0e-3))
        for point in points
    ]
    (run_dir / AERO_NODES_FILE).write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def _axes() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Toward the leading edge, toward suction and the span, at the blade angle beta.

    The rotor-frame section axes of a turning blade (x the shaft, z the span):
    the chord turned by beta from the plane of rotation.
    """
    beta = math.radians(PITCH_DEG)
    toward_le = np.array([-math.sin(beta), -math.cos(beta), 0.0])
    toward_suction = np.array([-math.cos(beta), math.sin(beta), 0.0])
    return toward_le, toward_suction, np.array([0.0, 0.0, 1.0])


def test_the_call_writes_one_row_per_listed_vertex_by_rigid_section_kinematics_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): the beam solution evaluated at the solver's vertices.

    At a structural node the row is the mapped route's row for that node; on
    the elastic axis halfway between two stations it is the mean of their
    flaps along the normal; a leading-edge point adds the mean of their twists
    times its chordwise distance; past the tip and before the root the end
    station's motion holds. Each row is relaxed by lambda = 0.4 from zero.
    """
    mapped_dir, direct_dir = tmp_path / "mapped", tmp_path / "direct"
    cfg = _stage(mapped_dir, "mapped")
    _stage(direct_dir, "direct")
    layout = nodes.generate_node_layout(cfg)
    structural = nodes.node_positions(layout)
    radii = np.asarray(cfg.blade.station_radii_m)
    toward_le, toward_suction, span = _axes()
    axis_at = [structural[3 * s] for s in range(len(radii))]
    middle = 0.5 * (axis_at[4] + axis_at[5])
    delta = 0.03
    extra = np.array(
        [middle, middle + delta * toward_le, axis_at[-1] + 0.05 * span, axis_at[0] - 0.05 * span]
    )
    _write_aero_nodes(direct_dir, np.vstack([structural, extra]))
    mapped = _call(mapped_dir, 100)
    direct = _call(direct_dir, 100)
    written = nodes.read_fsidisp(direct_dir / driver.DISPLACEMENT_FILE)
    assert written.shape == (len(structural) + 4, 3)
    np.testing.assert_allclose(written[: len(structural)], mapped.displacements, rtol=0, atol=1e-12)
    flap = np.asarray(direct.solutions[0].flap_deflection_m)
    twist = np.asarray(direct.solutions[0].elastic_twist_rad)
    expected = 0.4 * np.array(
        [
            0.5 * (flap[4] + flap[5]) * toward_suction,
            0.5 * ((flap[4] + twist[4] * delta) + (flap[5] + twist[5] * delta)) * toward_suction,
            flap[-1] * toward_suction,
            flap[0] * toward_suction,
        ]
    )
    np.testing.assert_allclose(written[len(structural) :], expected, rtol=0, atol=1e-12)
    assert abs(flap[-1]) > 1e-6 and abs(twist[5]) > 1e-9


def test_two_coupling_cycles_relax_every_vertex_from_its_own_previous_row_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): the second call blends from the first's rows.

    The package's half of the truncation test: what the solver reads at call 2
    is d1 + lambda (d_calc - d1) per listed vertex, the same rows the mapped
    route writes for its nodes, and a list that changes length between the
    two calls is refused rather than blended against other vertices.
    """
    mapped_dir, direct_dir = tmp_path / "mapped", tmp_path / "direct"
    cfg = _stage(mapped_dir, "mapped")
    _stage(direct_dir, "direct")
    structural = nodes.node_positions(nodes.generate_node_layout(cfg))
    _write_aero_nodes(direct_dir, structural)
    first = [_call(mapped_dir, 100), _call(direct_dir, 100)]
    second = [_call(mapped_dir, 140), _call(direct_dir, 140)]
    for mapped, direct in (first, second):
        np.testing.assert_allclose(direct.displacements, mapped.displacements, rtol=0, atol=1e-12)
    flap = np.asarray(second[1].solutions[0].flap_deflection_m)
    tip_axis = first[1].displacements[3 * (len(flap) - 1)]
    _, toward_suction, _ = _axes()
    np.testing.assert_allclose(
        second[1].displacements[3 * (len(flap) - 1)],
        tip_axis + 0.4 * (flap[-1] * toward_suction - tip_axis),
        rtol=0,
        atol=1e-12,
    )
    _write_aero_nodes(direct_dir, structural[:-3])
    with pytest.raises(FsiInputError, match="node list changed"):
        _call(direct_dir, 180)


def test_a_direct_call_without_the_aerodynamic_nodes_file_is_refused_fr_341(tmp_path):
    """P0370-S6-DIRECT-MORPHING (FR-341): no vertex list, no displacement file."""
    _stage(tmp_path, "direct")
    with pytest.raises(FsiInputError, match=AERO_NODES_FILE):
        _call(tmp_path, 100)
    assert not (tmp_path / driver.DISPLACEMENT_FILE).exists()
