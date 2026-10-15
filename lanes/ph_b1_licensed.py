"""Prepare or explicitly run ph-b1's licensed frame experiments.

Preparation uses the existing synthetic LQ1 wing workspace. These experiments
do not enable moving frames in production or promote any support verdict.
"""

# GEOVERSE_HEADER
# file_version: 1.0.0
# artifact_id: GEO-105-PYFLIGHTSTREAM-RELEASE-RECORDS
# last_modified_at: 2026-10-15
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-lane
# authority: geoverse-goddess-control-plane
# status: draft
# confidentiality: internal
# change_summary: Prepare three isolated frame observations without running the solver.
# dependencies: PFS-2140.007, tests/tier3_licensed/fsi_lq1.py
# revision_source: git

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np
from tests.support_tier3 import obj_text
from tests.tier3_licensed import fsi_lq1

from pyflightstream.cases import case_at_point
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.fsi.config import load_config
from pyflightstream.fsi.kinematics import encode_station_translations
from pyflightstream.fsi.nodes import flatten_blade_translations, generate_node_layout, write_fsidisp
from pyflightstream.qa.geometry import BladeSpec, blade_triangles
from pyflightstream.run import LocalExecutor, export_surface_mesh
from pyflightstream.run._pending import _write_pending_files
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.matrix import resolve_matrix

BUILD = "26.124"
ARMS = ("recut", "post_edit", "linked")


def _edit(*, y: float = 0.0, z: float = 0.0, frame: int = 2) -> str:
    script = Script(BUILD)
    script.declare_existing(frames=frame - 1)
    script.emit(
        "EDIT_COORDINATE_SYSTEM",
        frame=frame,
        name="MRP" if frame == 2 else "MIDSPAN_PROBE",
        origin_x=0.25,
        origin_y=y,
        origin_z=z,
        vector_x_x=1.0,
        vector_x_y=0.0,
        vector_x_z=0.0,
        vector_y_x=0.0,
        vector_y_y=1.0,
        vector_y_z=0.0,
        vector_z_x=0.0,
        vector_z_y=0.0,
        vector_z_z=1.0,
    )
    return script.render()


def _cut(name: str, *, recut: bool) -> str:
    script = Script(BUILD)
    script.declare_existing(frames=1)
    if recut:
        script.emit("DELETE_ALL_SURFACE_SECTIONS")
        script.emit(
            "CREATE_NEW_SURFACE_SECTION",
            frame=2,
            plane="XZ",
            offset=1.0,
            plot_direction="1",
            symmetry="DISABLE",
            surfaces=-1,
        )
    script.emit("UPDATE_ALL_SURFACE_SECTIONS")
    script.emit("EXPORT_ALL_SURFACE_SECTIONS", name)
    return script.render()


def _save(name: str) -> str:
    script = Script(BUILD)
    script.emit("SAVEAS", name)
    return script.render()


def _prepare_harmonics(root: Path, executable: Path) -> None:
    """Plan the synthetic unsteady rotor confirmation with a complete last revolution."""
    workspace = CampaignWorkspace.init(root)
    source = Path(fsi_lq1.__file__).parent / "inputs"
    for relative in ("references/r003.toml", "setups/s002.toml"):
        target = workspace.inputs_dir / relative
        target.write_bytes((source / relative).read_bytes())
    setup = workspace.inputs_dir / "setups/s002.toml"
    setup.write_text(
        setup.read_text().replace(
            "[flight_condition]", "wake_termination_x_m = 10.0\n\n[flight_condition]"
        ),
        encoding="utf-8",
    )
    (workspace.inputs_dir / "pproc/p001.toml").write_text(
        '[groups]\nTOTAL = "all"\n[sections]\ncount = 20\ninclude_symmetry = false\n'
        '[[sections.distributions]]\nfamilies = ["Blade1"]\nframe = "LOCAL_AXIS"\n'
        'planes = ["XY"]\n[plots]\nparameters = ["FX", "FY", "FZ", "MX", "MY", "MZ"]\n'
        '[[plots.groups]]\nname = "SHAFT_{family}"\nframe = "LOCAL_AXIS"\n'
        'families = ["Blade1"]\n[products]\npolars = true\nsections = true\n',
        encoding="utf-8",
    )
    reference = workspace.inputs_dir / "references/r003.toml"
    reference.write_text(
        reference.read_text().replace('zero = "Y"', 'zero = "Z"'), encoding="utf-8"
    )
    folder = workspace.inputs_dir / "geometries" / "blade"
    folder.mkdir()
    vertices, indices = np.unique(
        np.round(blade_triangles(BladeSpec()).reshape(-1, 3), 12), axis=0, return_inverse=True
    )
    (folder / "blade.obj").write_text(
        obj_text(vertices, indices.reshape(-1, 3), surface="Blade1"), encoding="utf-8"
    )
    (folder / "blade.boundaries.toml").write_text(
        'boundaries = ["Blade1"]\n[import]\nunits = "METER"\n'
        '[trailing_edges]\ndetect = "auto"\n[wake_termination]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    (workspace.inputs_dir / "executables.local.toml").write_text(
        f'"26.124" = "{executable.as_posix()}"\n', encoding="utf-8"
    )
    (workspace.inputs_dir / "executables.toml").write_text(
        '"26.124" = { path = "FlightStream_26124.exe", version = "26.124" }\n',
        encoding="utf-8",
    )
    matrix = root / "harmonics.fs"
    matrix.write_text(
        fsi_lq1._MATRIX_HEADER + "4112 | 1 | 1 | SYNTHETIC_ROTOR | - | HARMONIC_CONFIRMATION | "
        "MACH:0.1441, REmi:4.38, ALPHA:sweep, BETA:0.0 | 0.0 | blade.obj | "
        "r003 | s002 | p001 | PERIODIC | false | 2 | 2h | 26.124 | unsteady_rotor | "
        "PERIODIC_COPIES: 6 / DELTA_THETA: 10 / REVOLUTIONS: 3 / LAST_REVS_AVG: 1 / "
        "CLOCK_MOTION: ROTOR / MOTIONS: {MOVING_BC_ALIAS: ROTOR / ADVANCE_RATIO: 1.7}\n",
        encoding="utf-8",
    )
    planned = plan_matrix(
        matrix,
        workspace,
        name="harmonics",
        default_fs_version=BUILD,
        recipes={},
        recipe_registry=workflow_registry(),
    )
    if planned.blocked:
        raise ValueError(planned.summary())


def prepare(root: Path, executable: Path) -> dict[str, Path]:
    """Build the workspace and isolated probe scripts; never execute them."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "probe_matrix.json").exists():
        raise FileExistsError("probe workspace already prepared; retain it and choose a fresh root")
    fsi_lq1.build(root, str(executable))
    workspace = CampaignWorkspace(root)
    planned = plan_matrix(
        root / fsi_lq1.MATRIX,
        workspace,
        name="frame_probes",
        default_fs_version=BUILD,
        recipes={},
        recipe_registry=workflow_registry(),
    )
    if planned.blocked:
        raise ValueError(planned.summary())
    resolved = resolve_matrix(
        root / fsi_lq1.MATRIX, workspace, name="frame_probes", fs_version=BUILD, recipes={}
    )
    paths = {}
    matrix = []
    for arm in ARMS:
        folder = root / "probes" / arm
        folder.mkdir(parents=True)
        original = resolved.campaign.sims[0 if arm == "recut" else 1]
        case = case_at_point(original, {"ALPHA": 5.0})
        script = Script(BUILD)
        build_script(case, script)
        _write_pending_files(script, folder, case=case, recorded={})
        body = script.render()
        if arm == "recut":
            # Deliberate experimental phase transitions: each fragment is validated
            # separately. The licensed observation decides whether the transitions work.
            experiment = (
                _edit()
                + _cut("sections_before.txt", recut=True)
                + _edit(y=0.5)
                + _cut("sections_after_edit.txt", recut=False)
                + _cut("sections_recut.txt", recut=True)
            )
            assert body.count("CLOSE_FLIGHTSTREAM") == 1
            body = body.replace("CLOSE_FLIGHTSTREAM", experiment + "CLOSE_FLIGHTSTREAM")
        else:
            config = load_config(folder / "config.json")
            layout = generate_node_layout(config)
            radius = np.asarray(config.blade.station_radii_m)
            translations = encode_station_translations(
                0.1 * (radius / radius[-1]) ** 2,
                np.zeros_like(radius),
                np.asarray(layout.le_offset_m),
                np.asarray(layout.te_offset_m),
            )
            write_fsidisp(
                folder / "fsi_frozen_displacements.txt",
                flatten_blade_translations(layout, [translations]),
            )
            post_path = folder / "fsi_post.txt"
            post = post_path.read_text(encoding="utf-8")
            if arm == "post_edit":
                post = _edit(z=0.05) + post
            else:
                assignment = Script(BUILD)
                assignment.declare_existing(frames=2)
                assignment.emit("ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS", 2, [2, 3])
                old = "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1\n2"
                assert old in body
                body = body.replace(
                    old,
                    "CREATE_NEW_COORDINATE_SYSTEM\n" + _edit(y=2.0, frame=3) + assignment.render(),
                )
            post += _cut("sections_after.txt", recut=False) + _save("frame_after.fsm")
            post_path.write_text(post, encoding="utf-8", newline="\n")
            assert body.rstrip().endswith("EXECUTE_AEROELASTIC_ANALYSIS")
            body = body.replace(
                "EXECUTE_AEROELASTIC_ANALYSIS",
                _save("frame_before.fsm") + "EXECUTE_AEROELASTIC_ANALYSIS",
            )
        path = folder / "control.txt"
        path.write_text(body, encoding="utf-8", newline="\n")
        paths[arm] = path
        matrix.append({"arm": arm, "source_matrix": fsi_lq1.MATRIX, "POL": case.sim_id})
    resume = Script(BUILD)
    resume.emit("OPEN", "frame_after.fsm")
    resume.emit("EXECUTE_AEROELASTIC_ANALYSIS")
    (root / "resume.txt").write_text(resume.render(), encoding="utf-8", newline="\n")
    (root / "probe_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    (workspace.inputs_dir / "pproc/p420.toml").write_text(
        '[[probes]]\nframe = "REFERENCE"\nscale = "m"\nparameters = ["VX"]\n'
        "[[probes.grids]]\nframe = {origin = [0, 0, 2], x_axis = [1, 0, 0], "
        "y_axis = [0, 1, 0]}\nu = {start = 0, stop = 1, count = 2}\n"
        "v = {start = 0, stop = 4, count = 5}\n",
        encoding="utf-8",
    )
    workspace.resolve_pproc("p420")
    (root / "grids.fs").write_text(
        fsi_lq1._MATRIX_HEADER + "4120 | 1 | 1 | SYNTHETIC_WING | - | FSM_PLANAR_GRID | "
        "MACH:0.147, REmi:3.42, ALPHA:sweep | 5.0 | probe-wing.fsm | "
        "r340 | s340 | p420 | NONE | false | 2 | 2h | 26.124 | steady |\n",
        encoding="utf-8",
    )
    _prepare_harmonics(root / "harmonics", executable)
    return paths


def main() -> int:
    """Prepare offline, or explicitly execute one named licensed observation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "resume", "mesh"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--arm", choices=ARMS)
    args = parser.parse_args()
    if args.action == "prepare":
        for arm, path in prepare(args.workspace, args.exe).items():
            print(f"{arm}: {path}")
        return 0
    if args.action == "mesh":
        folder = args.workspace.resolve() / "probes" / "linked"
        if (args.workspace.resolve() / "mesh_export").exists():
            raise FileExistsError("retain the previous surface export; choose a fresh workspace")
        exported = export_surface_mesh(
            folder / "frame_before.fsm",
            args.workspace.resolve() / "mesh_export",
            version=BUILD,
            fs_exe=args.exe,
            file_type="STL",
        )
        sidecar = folder / "frame_before.surface.stl"
        if sidecar.exists():
            raise FileExistsError(sidecar)
        shutil.copyfile(exported, sidecar)
        geometry = args.workspace.resolve() / "inputs/geometries/probe-wing"
        geometry.mkdir()
        shutil.copyfile(folder / "frame_before.fsm", geometry / "probe-wing.fsm")
        shutil.copyfile(sidecar, geometry / "probe-wing.surface.stl")
        print(sidecar)
        return 0
    if args.action == "resume":
        original = args.workspace.resolve() / "probes" / "linked"
        folder = args.workspace.resolve() / "probes" / "resume"
        if not (original / "frame_after.fsm").is_file():
            raise FileNotFoundError("run the linked arm first; no saved coupled state exists")
        shutil.copytree(original, folder)
        shutil.copyfile(args.workspace.resolve() / "resume.txt", folder / "control.txt")
    else:
        if not args.arm:
            parser.error("run requires one --arm; run the probes serially")
        folder = args.workspace.resolve() / "probes" / args.arm
    receipt = folder / ("resume_execution.json" if args.action == "resume" else "execution.json")
    if receipt.exists():
        raise FileExistsError("retain the previous observation; prepare a fresh workspace")
    result = LocalExecutor(args.exe).run_script(folder / "control.txt", folder, timeout_s=600)
    receipt.write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
    print("Licensed observation recorded; no production support verdict was changed.")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
