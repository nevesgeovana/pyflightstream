"""P0400-FSIEXT (FR-462): an FSI row couples a structural program of the user's own.

The input is read and refused at reading (R1, R4); the coupling block of a
steady wing is held to the beam route's shape with the archiving step as the
execution command and the user's node file imported (R5); the run stages the
manifest, the node file, the declared inputs and the provenance (R6); and the
step, run on a stand-in program that writes the PyNite-format displacements,
archives and validates each call, failing on each defect R3 names (R3).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.cases._fsi_external import EXTERNAL_NODES_FILE
from pyflightstream.fsi.cli import main as fsi_main
from pyflightstream.fsi.external import (
    EXTERNAL_CALLS_LOG,
    EXTERNAL_MANIFEST,
    ExternalStructure,
    external_step,
)
from pyflightstream.fsi.state import DISPLACEMENT_FILE, LOADS_FILE
from pyflightstream.workspace.fsi_external_setup import (
    FsiExternalSetupError,
    resolve_external_fsi,
)
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_row_fsi
from tests.tier1_offline.test_fsig_fixed_wing import _wing_update
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

NODES = "0.25,0.0,0.0\n0.25,2.0,0.0\n0.25,4.0,0.0\n"

INPUT = """mode = "external"

[external]
executable = "bin/struct_wrapper.exe"
arguments = ["--quiet"]
structural_nodes = "f010.nodes.txt"
inputs = ["f010.model.dat"]
outputs = ["struct_log.txt"]

[coupling]
families = ["Wing"]
max_iterations = 30
"""


def _inputs(tmp_path: Path, text: str = INPUT) -> Path:
    folder = tmp_path / "inputs" / "fsi"
    (folder / "bin").mkdir(parents=True, exist_ok=True)
    (folder / "bin" / "struct_wrapper.exe").write_bytes(b"stand-in program bytes")
    (folder / "f010.nodes.txt").write_text(NODES, encoding="utf-8")
    (folder / "f010.model.dat").write_text("E = 70e9\n", encoding="utf-8")
    (folder / "f010.toml").write_text(text, encoding="utf-8")
    return folder / "f010.toml"


# --------------------------------------------------------------------------- R1, R4


def test_p0400_fsiext_resolves_and_hashes(tmp_path):
    """P0400-FSIEXT (FR-462 R1, R6): the program, nodes and inputs, hashed; three nodes."""
    path = _inputs(tmp_path)
    structure = resolve_row_fsi(tmp_path / "inputs", {"FSI": "f010"})
    assert isinstance(structure, ExternalStructure)
    assert structure.node_count == 3
    exe = path.parent / "bin" / "struct_wrapper.exe"
    assert structure.executable_sha256 == hashlib.sha256(exe.read_bytes()).hexdigest()
    assert set(structure.inputs_sha256) == {"f010.model.dat"}
    assert structure.max_iterations == 30
    assert structure.provenance()["route"].startswith("B:")


@pytest.mark.parametrize(
    ("old", "new", "words"),
    [
        ('arguments = ["--quiet"]', "show_console = true", "show_console"),
        ('mode = "external"', 'mode = "external"\nmorphing = "direct"', "morphing"),
        ('executable = "bin/struct_wrapper.exe"', 'executable = "../elsewhere.exe"', "executable"),
        ('inputs = ["f010.model.dat"]', 'inputs = ["absent.dat"]', "declared input"),
        ('families = ["Wing"]', 'families = ["Wing", "Tail"]', "one family"),
        ("max_iterations = 30", "max_iterations = 30\nrelaxation = 0.5", "Extra inputs"),
    ],
)
def test_p0400_fsiext_refusals_at_reading(tmp_path, old, new, words):
    """P0400-FSIEXT (FR-462 R4): each refusal names its key."""
    assert old in INPUT
    path = _inputs(tmp_path, INPUT.replace(old, new))
    with pytest.raises(FsiExternalSetupError, match=words):
        resolve_external_fsi(path)


def test_p0400_fsiext_empty_node_file_is_refused(tmp_path):
    """P0400-FSIEXT (FR-462 R4): a node file with no node."""
    path = _inputs(tmp_path)
    (path.parent / "f010.nodes.txt").write_text("\n", encoding="utf-8")
    with pytest.raises(FsiExternalSetupError, match="no node"):
        resolve_external_fsi(path)


def test_p0400_fsiext_factor_keys_are_refused(tmp_path):
    """P0400-FSIEXT (FR-462 R4): a factor key on an external row changes nothing, so refused."""
    _inputs(tmp_path)
    with pytest.raises(FsiSetupError, match="external"):
        resolve_row_fsi(
            tmp_path / "inputs", {"FSI": "f010", "FSI_BENDING_STIFFNESS_N_M2_FACTOR": "1.1"}
        )


# --------------------------------------------------------------------------- R5, R6


def _external_case(tmp_path: Path, make=steady_case):
    structure = resolve_row_fsi(_inputs(tmp_path).parent.parent, {"FSI": "f010"})
    assert isinstance(structure, ExternalStructure)
    update = _wing_update(tmp_path, None)
    update["fsi"] = None
    update["fsi_external"] = structure
    update["fsi_provenance"] = structure.provenance()
    return make().model_copy(update=update), structure


STEADY_EXTERNAL = [
    "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC",
    "DELETE_AEROELASTIC_STRUCTURAL_NODES",
    "ASSIGN_AEROELASTIC_SURFACES 1",
    "2",
    "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1",
    "2",
    "IMPORT_AEROELASTIC_STRUCTURAL_NODES 2 DISABLE",
    EXTERNAL_NODES_FILE,
    "SET_AEROELASTIC_WORKING_DIRECTORY",
    ".",
    "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
    "fsi_post.txt",
    "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
]


def test_p0400_fsiext_steady_block_and_staged_files(tmp_path):
    """P0400-FSIEXT (FR-462 R5, R6): the beam route's block, the step as the command."""
    case, structure = _external_case(tmp_path)
    lines, script = _lines(case)
    body = [line for line in lines if line.strip()]
    start = body.index("AEROELASTIC_RBF_TYPE MULTI_QUADRATIC")
    assert body[start : start + len(STEADY_EXTERNAL)] == STEADY_EXTERNAL
    assert body[start + len(STEADY_EXTERNAL) + 1] == "SET_AEROELASTIC_ITERATIONS 30"
    assert body[-1] == "EXECUTE_AEROELASTIC_ANALYSIS"
    assert ws.is_steady_aeroelastic_script(script.render())
    for absent in ("SET_MOTION_FSI_EXECUTABLE", "SET_MOTION_FSI_STRUCTURAL_NODES", "START_SOLVER"):
        assert not any(line.startswith(absent) for line in body), absent
    staged = script.pending_input_files
    assert "main(['external', '--out', '.'])" in staged[ws.CALLBACK_FILE]
    assert ExternalStructure.model_validate_json(staged[EXTERNAL_MANIFEST]) == structure
    assert staged[EXTERNAL_NODES_FILE] == Path(structure.structural_nodes).read_bytes()
    assert "f010.model.dat" in staged
    assert json.loads(staged["fsi-provenance.json"])["mode"] == "external"


def test_p0400_fsiext_unsteady_couples_in_the_march(tmp_path):
    """P0400-FSIEXT (FR-462 R5): one coupling iteration per step inside the march."""
    case, _ = _external_case(tmp_path, unsteady_case)
    lines, _script = _lines(case)
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE" in lines
    assert "SET_AEROELASTIC_ITERATIONS 1" in lines


def test_p0400_fsiext_refuses_symmetry_and_a_second_distribution(tmp_path):
    """P0400-FSIEXT (FR-462 R4): symmetry copies and a second section distribution."""
    case, _ = _external_case(tmp_path)
    mirrored = case.model_copy(update={"variables": {**case.variables, "SYMMETRY": "MIRROR"}})
    with pytest.raises(CampaignConfigError, match="symmetry"):
        _lines(mirrored)
    assert case.pproc is not None
    doubled = case.pproc.model_copy(deep=True)
    doubled.sections.distributions.append(doubled.sections.distributions[0])
    with pytest.raises(CampaignConfigError, match="one section"):
        _lines(case.model_copy(update={"pproc": doubled}))


# --------------------------------------------------------------------------- R3, the step

STAND_IN = """import sys
mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
rows = [line for line in open("fsi_external_nodes.csv").read().splitlines() if line.strip()]
open("struct_log.txt", "w").write("called\\n")
if mode == "fail":
    sys.exit(3)
if mode == "silent":
    sys.exit(0)
count = len(rows) - 1 if mode == "short" else len(rows)
value = "nan" if mode == "nan" else "1.0000000000000000e-03"
with open("FSIDisp.txt", "w") as out:
    for _ in range(count):
        out.write("0.0000000000000000e+00,0.0000000000000000e+00," + value + "\\n")
"""


def _point(tmp_path: Path, mode: str = "ok") -> Path:
    folder = tmp_path / "point"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stand_in.py").write_text(STAND_IN, encoding="utf-8")
    (folder / EXTERNAL_NODES_FILE).write_text(NODES, encoding="utf-8")
    (folder / LOADS_FILE).write_text("loads of the call\n", encoding="utf-8")
    exe = Path(sys.executable)
    script = folder / "stand_in.py"
    structure = ExternalStructure(
        source=str(folder / "f010.toml"),
        source_sha256="0" * 64,
        executable=str(exe),
        executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        arguments=["stand_in.py", mode],
        structural_nodes=str(folder / EXTERNAL_NODES_FILE),
        structural_nodes_sha256=hashlib.sha256(
            (folder / EXTERNAL_NODES_FILE).read_bytes()
        ).hexdigest(),
        node_count=3,
        inputs={"stand_in.py": str(script)},
        inputs_sha256={"stand_in.py": hashlib.sha256(script.read_bytes()).hexdigest()},
        outputs=["struct_log.txt"],
        timeout_s=60.0,
        families=["Wing"],
    )
    (folder / EXTERNAL_MANIFEST).write_text(structure.model_dump_json(), encoding="utf-8")
    return folder


def test_p0400_fsiext_step_archives_and_validates_a_call(tmp_path):
    """P0400-FSIEXT (FR-462 R2, R3): the call archived with its record, through the CLI."""
    folder = _point(tmp_path)
    assert fsi_main(["external", "--out", str(folder)]) == 0
    archive = folder / "fsi_archive" / "call_0001"
    record = json.loads((archive / "call.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "passed" and record["return_code"] == 0
    assert record["rows_written"] == 3 and record["node_count"] == 3
    assert {LOADS_FILE, "stand_in.py"} <= set(record["read_sha256"])
    assert set(record["written_sha256"]) == {DISPLACEMENT_FILE, "struct_log.txt"}
    for name in (LOADS_FILE, DISPLACEMENT_FILE, "struct_log.txt"):
        assert (archive / name).is_file(), name
    assert external_step(folder) == 0
    log = (folder / EXTERNAL_CALLS_LOG).read_text(encoding="utf-8").splitlines()
    assert log[0].startswith("call,") and len(log) == 3


@pytest.mark.parametrize(
    ("mode", "words"),
    [
        ("fail", "returned 3"),
        ("silent", "wrote no FSIDisp.txt"),
        ("short", "2 rows for 3"),
        ("nan", "not finite"),
    ],
)
def test_p0400_fsiext_step_fails_each_defect(tmp_path, mode, words):
    """P0400-FSIEXT (FR-462 R3): a nonzero code, no file, a wrong count, a non-finite value."""
    folder = _point(tmp_path, mode)
    assert external_step(folder) == 1
    error = (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
    assert words in error
    record = json.loads(
        (folder / "fsi_archive" / "call_0001" / "call.json").read_text(encoding="utf-8")
    )
    assert record["verdict"] == "failed"


def test_p0400_fsiext_step_refuses_a_changed_input(tmp_path):
    """P0400-FSIEXT (FR-462 R3): a declared input changed after the plan hashed it."""
    folder = _point(tmp_path)
    (folder / "stand_in.py").write_text(STAND_IN + "\n# edited\n", encoding="utf-8")
    assert external_step(folder) == 1
    assert "changed after the plan" in (folder / "pyfs_fsi_error.log").read_text(encoding="utf-8")
    assert not (folder / DISPLACEMENT_FILE).exists()


def test_p0400_fsiext_a_previous_answer_is_not_passed_on(tmp_path):
    """P0400-FSIEXT (FR-462 R3): the last call's FSIDisp.txt does not survive a silent call."""
    folder = _point(tmp_path)
    assert external_step(folder) == 0
    manifest = json.loads((folder / EXTERNAL_MANIFEST).read_text(encoding="utf-8"))
    manifest["arguments"] = ["stand_in.py", "silent"]
    (folder / EXTERNAL_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert external_step(folder) == 1
