"""Tier 1: one setup, pproc and reference serve every model of a study (FR-435, P0390-R02).

The use case, written as files before any code: a wing-body model (Wing, Body,
Base) and a wing-body-tail model (those plus HTail, VTail, TailBase and a
support Sting), one reference naming every surface of the study under
``[study] surfaces`` and the aliases ``airframe``, ``tail`` and ``lifting``,
one setup removing the Sting and choosing the loads and vorticity families
over the tail, one pproc marking the two bases and summing TOTAL, AIRFRAME and
TAIL, and one matrix row per model citing the same three files. On v0.38.0 the
wing-body row is BLOCKED at plan, first by ``delete_surfaces`` and then by
``base_regions``. Every workspace here is synthetic and built in ``tmp_path``;
every plan goes through ``plan_matrix``, the call ``pyfs-matrix plan`` makes,
and every run through ``run_matrix`` with the stub solver the tier-1 suite
already drives for records.
"""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.matrix import MATRIX_COLUMNS
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.support_helpers import fold_separators, saved_mesh_fixture
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)

BUILD = "26.124"
#: The models of the study, as (POL, geometry, the boundaries its mesh block declares).
WING_BODY = ("2001", "wb.fsm", ["Wing", "Body", "Base"])
WING_BODY_TAIL = (
    "2002",
    "wbt.fsm",
    ["Wing", "Body", "Base", "HTail", "VTail", "TailBase", "Sting"],
)
WING_ALONE = ("2003", "w.fsm", ["Wing"])
STUDY_SURFACES = ["Wing", "Body", "Base", "HTail", "VTail", "TailBase", "Sting"]

REFERENCE = (
    "area_m2 = 8.0\n"
    "chord_m = 1.0\n"
    "span_m = 8.0\n"
    "[moment_point]\n"
    "x_m = 0.25\n"
    "y_m = 0.0\n"
    "z_m = 0.0\n"
    "[aliases]\n"
    'airframe = ["Wing", "Body", "Base", "HTail", "VTail", "TailBase"]\n'
    'tail = ["HTail", "VTail"]\n'
    'lifting = ["Wing", "HTail"]\n'
)
STUDY = "[study]\nsurfaces = [" + ", ".join(f'"{name}"' for name in STUDY_SURFACES) + "]\n"
SETUP = (
    "iterations = 500\n"
    "convergence = 1e-5\n"
    "farfield_layers = 5\n"
    'delete_surfaces = ["Sting"]\n'
    'analysis_families = ["Wing", "Body", "HTail", "VTail"]\n'
    'vorticity_drag_families = ["Wing", "HTail"]\n'
)
PPROC = (
    'base_regions = ["Base", "TailBase"]\n'
    "[groups]\n"
    'TOTAL = "all"\n'
    'AIRFRAME = "airframe"\n'
    'TAIL = "tail"\n'
)

#: The SHA-256 of the wing-body-tail row's script as v0.38.0 renders it from the
#: same files (the reference without ``[study]``, which v0.38.0 refuses), the
#: workspace root masked and the separators folded. Recorded on the
#: tree before FR-435 (d1082220) and kept here, beside the test (FR-990).
WING_BODY_TAIL_SCRIPT_V0380 = Path(__file__).parent / "fixtures" / "p0390_r02_script_digest.json"


def study(
    tmp_path: Path,
    *,
    reference: str = REFERENCE + STUDY,
    setup: str = SETUP,
    pproc: str = PPROC,
    models: tuple[tuple[str, str, list[str]], ...] = (WING_BODY, WING_BODY_TAIL),
) -> tuple[CampaignWorkspace, Path]:
    """Build the use case's workspace and its matrix, one row per model."""
    workspace = CampaignWorkspace.init(tmp_path / "study")
    inputs = workspace.inputs_dir
    for _, geometry, boundaries in models:
        saved_mesh_fixture(inputs / "geometries" / geometry, boundaries)
    (inputs / "references" / "r001.toml").write_text(reference, encoding="utf-8")
    (inputs / "setups" / "s001.toml").write_text(setup, encoding="utf-8")
    (inputs / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(f'"{BUILD}" = "C:/fs/FS.exe"\n')
    workspace = CampaignWorkspace(
        workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    lines = [" | ".join(MATRIX_COLUMNS), "-" * 40]
    for pol, geometry, _ in models:
        cells = {
            "POL": pol,
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Demo",
            "CONFIGURATION": geometry.split(".")[0],
            "DESCRIPTION": "ALPHA_SWEEP",
            "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
            "SWEEP_VALUES": "-2.0,0.0",
            "GEOMETRY": geometry,
            "REF": "r001",
            "SET": "s001",
            "PPROC": "p001",
            "SYMMETRY": "NONE",
            "FS_BUILD": BUILD,
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": "",
        }
        lines.append(" | ".join(cells.get(name, "-") for name in MATRIX_COLUMNS))
    path = workspace.root / "study.fs"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return workspace, path


def planned(workspace: CampaignWorkspace, path: Path, **options):
    """Plan the matrix as ``pyfs-matrix plan`` does; return the plan and the warnings it said."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            path,
            workspace,
            name="study",
            default_fs_version=BUILD,
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            write_plan=False,
            **options,
        )
    said = [
        str(item.message) for item in caught if issubclass(item.category, PyflightstreamWarning)
    ]
    return plan, said


def ran(workspace: CampaignWorkspace, path: Path):
    """Run the matrix offline through the stub solver; return the records it appended."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_matrix(
            path,
            workspace,
            name="study",
            default_fs_version=BUILD,
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=CountingStub(WRITES_EVERY_EXPORT),
        )


def status_of(plan) -> dict[str, set[PlanStatus]]:
    """Each row's statuses over its points."""
    found: dict[str, set[PlanStatus]] = {}
    for point in plan.points:
        found.setdefault(point.sim_id, set()).add(point.status)
    return found


def error_of(plan, sim_id: str) -> str:
    """The refusal of the first blocked point of one row."""
    return next(point.error for point in plan.points if point.sim_id == sim_id and point.error)


def script_of(workspace: CampaignWorkspace, records, sim_id: str) -> str:
    """The script one row's run wrote, its root masked and its separators folded."""
    record = next(record for record in records if record.sim_id == sim_id)
    text = (workspace.sim_dir(sim_id) / record.script_path).read_text(encoding="utf-8")
    for root in (str(workspace.root), str(workspace.root.resolve())):
        text = text.replace(root, "<ROOT>").replace(root.replace("\\", "/"), "<ROOT>")
    return fold_separators(text)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fr435_warnings(said: list[str]) -> list[str]:
    """The plan lines FR-435 says, one per artifact, key and name."""
    return [text for text in said if "(FR-435)" in text]


def command_with_its_line(script: str, command: str) -> list[str]:
    """Each line naming ``command``, joined to the argument line that follows it."""
    lines = script.splitlines()
    return [
        f"{line} | {lines[index + 1] if index + 1 < len(lines) else ''}"
        for index, line in enumerate(lines)
        if line.split(" ")[0] == command
    ]


def without(text: str, line: str) -> str:
    """One artifact body with one of its lines removed, the line required to be there."""
    assert line in text, line
    return text.replace(line, "")


#: The six names the wing-body row skips, as its record states them, in build order.
WING_BODY_SKIPS = [
    {"artifact": "s001", "key": "delete_surfaces", "name": "Sting"},
    {"artifact": "p001", "key": "groups.TAIL", "name": "tail"},
    {"artifact": "p001", "key": "base_regions", "name": "TailBase"},
    {"artifact": "s001", "key": "vorticity_drag_families", "name": "HTail"},
    {"artifact": "s001", "key": "analysis_families", "name": "HTail"},
    {"artifact": "s001", "key": "analysis_families", "name": "VTail"},
]


@pytest.fixture(scope="module")
def run_of_the_study(tmp_path_factory):
    """The use case planned and run once: the workspace, the plan's lines and the records."""
    workspace, path = study(tmp_path_factory.mktemp("p0390_r02"))
    plan, said = planned(workspace, path)
    return workspace, plan, said, ran(workspace, path)


# --- FR-982: one set of files, every model READY --------------------------------


def test_every_model_of_the_study_plans_ready_from_one_set_of_files(run_of_the_study):
    """P0390-R02 (FR-982) both rows of the use case plan READY, every point of each."""
    _, plan, _, records = run_of_the_study
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2002": {PlanStatus.READY}}
    assert [record.status for record in records] == [RunStatus.CONVERGED, RunStatus.CONVERGED]


def test_the_wing_body_script_emits_nothing_of_the_tail(run_of_the_study):
    """P0390-R02 (FR-982) no removal, no tail base, and the selections without the tail.

    The wing-body mesh numbers Wing 1, Body 2 and Base 3: the base detection
    names Base alone, and the loads and vorticity selections keep the families
    the model carries in the order the setup writes them.
    """
    workspace, _, _, records = run_of_the_study
    script = script_of(workspace, records, "2001")
    lines = script.splitlines()
    assert not [line for line in lines if line.startswith("DELETE_SURFACES")]
    assert [line for line in lines if line.startswith("DETECT_BASE")] == [
        "DETECT_BASE_REGIONS_BY_SURFACE 3"
    ]
    assert (
        command_with_its_line(script, "SET_SOLVER_ANALYSIS_BOUNDARIES")
        == ["SET_SOLVER_ANALYSIS_BOUNDARIES 2 | 1,2"] * 2
    )
    assert command_with_its_line(script, "SET_VORTICITY_DRAG_BOUNDARIES") == [
        "SET_VORTICITY_DRAG_BOUNDARIES 1 | 1"
    ]
    # The control: the model carrying every name emits all of it.
    full = script_of(workspace, records, "2002").splitlines()
    assert [line for line in full if line.startswith("DELETE_SURFACES")] == ["DELETE_SURFACES 7"]
    assert [line for line in full if line.startswith("DETECT_BASE")] == [
        "DETECT_BASE_REGIONS_BY_SURFACE 3",
        "DETECT_BASE_REGIONS_BY_SURFACE 6",
    ]
    assert (
        command_with_its_line("\n".join(full), "SET_SOLVER_ANALYSIS_BOUNDARIES")
        == ["SET_SOLVER_ANALYSIS_BOUNDARIES 4 | 1,2,4,5"] * 2
    )


def test_a_third_model_carrying_the_wing_alone_plans_ready_with_no_edit(tmp_path):
    """P0390-R02 (FR-982) a wing alone joins the study with the same three files, unedited."""
    workspace, path = study(tmp_path, models=(WING_BODY, WING_BODY_TAIL, WING_ALONE))
    plan, said = planned(workspace, path)
    assert status_of(plan) == {
        "2001": {PlanStatus.READY},
        "2002": {PlanStatus.READY},
        "2003": {PlanStatus.READY},
    }
    sting = [text for text in fr435_warnings(said) if "delete_surfaces cites 'Sting'" in text]
    assert len(sting) == 1
    assert "2 rows do not carry it: '2001', '2003'" in sting[0]


# --- FR-987: one plan line per artifact, key and name ---------------------------


def test_the_plan_says_each_skip_once_naming_the_wing_body_row_alone(run_of_the_study):
    """P0390-R02 (FR-987) one WARNING per artifact, key and name; row 2002 is named in none.

    Each names the artifact with its file, the key (the group for a ``[groups]``
    member), the name, the reference whose vocabulary holds it and the row. A
    partly absent alias (``airframe`` on the wing-body) stays silent (FR-59),
    and ``all`` is never said.
    """
    _, _, said, _ = run_of_the_study
    lines = fr435_warnings(said)
    expected = [
        ("the setup artifact 's001' (inputs/setups/s001.toml)", "delete_surfaces", "Sting"),
        ("the pproc artifact 'p001' (inputs/pproc/p001.toml)", "groups.TAIL", "tail"),
        ("the pproc artifact 'p001' (inputs/pproc/p001.toml)", "base_regions", "TailBase"),
        ("the setup artifact 's001' (inputs/setups/s001.toml)", "vorticity_drag_families", "HTail"),
        ("the setup artifact 's001' (inputs/setups/s001.toml)", "analysis_families", "HTail"),
        ("the setup artifact 's001' (inputs/setups/s001.toml)", "analysis_families", "VTail"),
    ]
    assert len(lines) == len(expected), lines
    for (artifact, key, name), line in zip(expected, lines, strict=True):
        assert line.startswith(f"{artifact}: {key} cites {name!r}"), line
        assert "the reference artifact 'r001' (inputs/references/r001.toml)" in line
        assert "row '2001'" in line and "'2002'" not in line
    assert not [line for line in said if "'airframe'" in line or "'all'" in line]


def test_a_row_carrying_every_name_plans_with_no_new_line(tmp_path):
    """P0390-R02 (FR-990) the wing-body-tail row alone plans READY and says nothing new."""
    for reference in (REFERENCE + STUDY, REFERENCE):
        workspace, path = study(
            tmp_path / str(len(reference)), reference=reference, models=(WING_BODY_TAIL,)
        )
        plan, said = planned(workspace, path)
        assert status_of(plan) == {"2002": {PlanStatus.READY}}
        assert said == []


# --- FR-989: the record ---------------------------------------------------------


def test_the_wing_body_record_names_its_skips_and_the_full_model_record_has_no_field(
    run_of_the_study,
):
    """P0390-R02 (FR-989) skipped_names on each wing-body point; absent from the full model's.

    Read from ``runs.json`` as written: a point that skipped nothing records no
    such key at all, not an empty list, so its record keeps its 0.38.0 content.
    """
    workspace, _, _, _ = run_of_the_study
    rows = _read_record_rows(workspace.root / "runs.json")
    rows = rows if isinstance(rows, list) else rows["runs"]
    by_row = {row["sim_id"]: row for row in rows}
    assert by_row["2001"]["skipped_names"] == WING_BODY_SKIPS
    assert "skipped_names" not in by_row["2002"]
    points = [point for record in workspace.read_manifest() for point in record.as_points()]
    assert [point.skipped_names for point in points if point.sim_id == "2001"] == [
        WING_BODY_SKIPS
    ] * 2
    assert [point.skipped_names for point in points if point.sim_id == "2002"] == [None, None]


# --- FR-990: byte identity ------------------------------------------------------


def test_the_full_model_script_is_the_one_v0380_writes_from_the_same_files(tmp_path):
    """P0390-R02 (FR-990) wbt's script is byte for byte v0.38.0's, with and without [study]."""
    pinned = json.loads(WING_BODY_TAIL_SCRIPT_V0380.read_text(encoding="utf-8"))["sha256"]
    for reference in (REFERENCE + STUDY, REFERENCE):
        workspace, path = study(
            tmp_path / str(len(reference)), reference=reference, models=(WING_BODY_TAIL,)
        )
        records = ran(workspace, path)
        assert digest(script_of(workspace, records, "2002")) == pinned
        rows = _read_record_rows(workspace.root / "runs.json")
        rows = rows if isinstance(rows, list) else rows["runs"]
        assert all("skipped_names" not in row for row in rows)


# --- FR-981: no vocabulary, the 0.38.0 reading -----------------------------------


def test_without_a_study_the_two_measured_v0380_refusals_stand(tmp_path):
    """P0390-R02 (FR-981) without [study]: delete_surfaces refuses, then base_regions."""
    workspace, path = study(tmp_path / "first", reference=REFERENCE)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    assert (
        "CampaignConfigError: case '2001' states delete_surfaces with 'Sting', and the "
        "inventory declares no surface of that name, alias or family; it declares 'Wing', "
        "'Body', 'Base'. Write one of those, or a family name (the label without its "
        "trailing number)."
    ) == error_of(plan, "2001")
    assert fr435_warnings(said) == []
    setup = without(SETUP, 'delete_surfaces = ["Sting"]\n')
    workspace, path = study(tmp_path / "second", reference=REFERENCE, setup=setup)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    assert error_of(plan, "2001").startswith(
        "CampaignConfigError: case '2001' states BASE_REGIONS with 'TailBase', and the mesh "
        "block of wb.fsm declares no boundary of that name or family; it declares 'Wing', "
        "'Body', 'Base'."
    )
    assert fr435_warnings(said) == []


def test_a_rows_own_base_regions_keeps_its_refusal_beside_a_study(tmp_path):
    """P0390-R02 (FR-979) a row's own BASE_REGIONS is no study key: TailBase still refuses."""
    workspace, path = study(tmp_path, pproc=without(PPROC, 'base_regions = ["Base", "TailBase"]\n'))
    lines = [
        line.rsplit("|", 1)[0] + "| BASE_REGIONS: Base, TailBase"
        if line.startswith("2001")
        else line
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan, _ = planned(workspace, path)
    assert status_of(plan)["2001"] == {PlanStatus.BLOCKED}
    assert "states BASE_REGIONS with 'TailBase'" in error_of(plan, "2001")


# --- FR-984: a name the study does not hold is a misspelling ---------------------


@pytest.mark.parametrize(
    ("artifact", "old", "new", "key", "name"),
    [
        (
            "setup",
            'delete_surfaces = ["Sting"]',
            'delete_surfaces = ["Stinng"]',
            "delete_surfaces",
            "Stinng",
        ),
        (
            "setup",
            'analysis_families = ["Wing", "Body", "HTail", "VTail"]',
            'analysis_families = ["Wing", "Body", "HTial", "VTail"]',
            "analysis_families",
            "HTial",
        ),
        (
            "setup",
            'vorticity_drag_families = ["Wing", "HTail"]',
            'vorticity_drag_families = ["Wing", "Htial"]',
            "vorticity_drag_families",
            "Htial",
        ),
        (
            "pproc",
            'base_regions = ["Base", "TailBase"]',
            'base_regions = ["Base", "TailBse"]',
            "base_regions",
            "TailBse",
        ),
        ("pproc", 'TAIL = "tail"', 'TAIL = "tial"', "groups.TAIL", "tial"),
    ],
)
def test_a_misspelled_name_is_blocked_on_every_row_naming_the_vocabulary(
    tmp_path, artifact, old, new, key, name
):
    """P0390-R02 (FR-984) BLOCKED on both rows at either flag, naming key, name, vocabulary."""
    files = {"setup": SETUP, "pproc": PPROC}
    files[artifact] = files[artifact].replace(old, new)
    workspace, path = study(tmp_path, setup=files["setup"], pproc=files["pproc"])
    code = "s001" if artifact == "setup" else "p001"
    folder = "setups" if artifact == "setup" else "pproc"
    for options in ({}, {"ignore_missing_families": False}):
        plan, said = planned(workspace, path, **options)
        assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.BLOCKED}}
        # Under the flag the wing-body row is refused first for the Sting it skips
        # by default (FR-988), unless the misspelling is in that very key.
        rows = [("2001", "wb.fsm"), ("2002", "wbt.fsm")]
        if options and key != "delete_surfaces":
            rows = rows[1:]
        for row, geometry in rows:
            error = error_of(plan, row)
            assert f"the {artifact} artifact '{code}' (inputs/{folder}/{code}.toml)" in error
            assert f"cites {name!r} under {key}" in error
            assert f"row {row!r} ({geometry})" in error
            assert "the reference artifact 'r001' (inputs/references/r001.toml)" in error
            assert "'Wing', 'Body', 'Base', 'HTail', 'VTail', 'TailBase', 'Sting'" in error
            assert "[study] surfaces" in error
        assert fr435_warnings(said) == []


# --- FR-985, FR-986: the refusals that stand whatever the study holds ---------------


def test_a_family_list_every_name_of_which_is_absent_keeps_its_v0380_refusal(tmp_path):
    """P0390-R02 (FR-985) analysis_families of the tail alone: an empty selection is refused."""
    setup = SETUP.replace(
        'analysis_families = ["Wing", "Body", "HTail", "VTail"]',
        'analysis_families = ["HTail", "VTail"]',
    )
    workspace, path = study(tmp_path, setup=setup)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    assert error_of(plan, "2001") == (
        "CampaignConfigError: case '2001': the preset names analysis_families HTail, VTail and "
        "the opened geometry carries none of them (absent: HTail, VTail), so the selection would "
        "be empty. Name families the geometry carries, or drop analysis_families so every "
        "boundary enters the loads."
    )
    assert fr435_warnings(said) == []


def test_a_pproc_whose_only_group_is_the_tail_keeps_the_rpt044_refusal(tmp_path):
    """P0390-R02 (FR-986) no group selects a wing-body boundary: refused with its 0.38.0 text."""
    pproc = 'base_regions = ["Base", "TailBase"]\n[groups]\nTAIL = "tail"\n'
    workspace, path = study(tmp_path, pproc=pproc)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    assert error_of(plan, "2001").startswith(
        "CampaignConfigError: case '2001' names the pproc artifact 'p001' "
        "(inputs/pproc/p001.toml), whose groups cite 'tail', and the mesh block of wb.fsm "
        "declares none of those names or families; it declares 'Wing', 'Body', 'Base'."
    )
    assert fr435_warnings(said) == []


# --- FR-983: a skip that renumbers an indexed base region ------------------------

INDEXED = '[[base_region_operations]]\noperation = "set_pressure"\nindex = 1\nmodel = "EMPIRICAL"\n'
CREATE_TAIL_BASE = (
    '[[base_region_operations]]\noperation = "create"\nboundary = "TailBase"\n'
    'model = "EMPIRICAL"\ncp = -0.1\n'
)


def test_a_skipped_base_beside_an_index_addressed_operation_is_refused(tmp_path):
    """P0390-R02 (FR-983) TailBase skipped while base region 1 is addressed by index: refused."""
    workspace, path = study(tmp_path / "regions", setup=SETUP + INDEXED)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    error = error_of(plan, "2001")
    assert "base_regions cites 'TailBase'" in error
    assert "base_region_operations[1] addresses a base region by index 1" in error
    assert fr435_warnings(said) == []
    pproc = without(PPROC, 'base_regions = ["Base", "TailBase"]\n')
    workspace, path = study(
        tmp_path / "create", setup=SETUP + CREATE_TAIL_BASE + INDEXED, pproc=pproc
    )
    plan, _ = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    error = error_of(plan, "2001")
    assert "base_region_operations[1] cites 'TailBase'" in error
    assert "base_region_operations[2] addresses a base region by index 1" in error


def test_a_skipped_create_entry_is_not_emitted_and_is_said(tmp_path):
    """P0390-R02 (FR-982) a create over TailBase, nothing indexed: 2001 leaves it out, said."""
    pproc = without(PPROC, 'base_regions = ["Base", "TailBase"]\n')
    workspace, path = study(tmp_path, setup=SETUP + CREATE_TAIL_BASE, pproc=pproc)
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2002": {PlanStatus.READY}}
    assert [
        line
        for line in fr435_warnings(said)
        if "base_region_operations[1] cites 'TailBase'" in line
    ]
    records = ran(workspace, path)
    assert "CREATE_NEW_BASE_REGION" not in script_of(workspace, records, "2001")
    assert "CREATE_NEW_BASE_REGION" in script_of(workspace, records, "2002")


# --- FR-988: the flag that asks for the refusal ---------------------------------


@pytest.mark.parametrize(
    ("setup", "pproc", "key", "name", "reference"),
    [
        (SETUP, PPROC, "delete_surfaces", "Sting", REFERENCE + STUDY),
        (
            without(SETUP, 'delete_surfaces = ["Sting"]\n'),
            PPROC,
            "groups.TAIL",
            "tail",
            REFERENCE + STUDY,
        ),
        (
            without(SETUP, 'delete_surfaces = ["Sting"]\n'),
            'base_regions = ["Base", "TailBase"]\n[groups]\nTOTAL = "all"\n',
            "base_regions",
            "TailBase",
            REFERENCE + STUDY,
        ),
        (
            'iterations = 500\nanalysis_families = ["Wing", "HTail"]\n',
            '[groups]\nTOTAL = "all"\n',
            "analysis_families",
            "HTail",
            REFERENCE + STUDY,
        ),
        (
            'iterations = 500\nvorticity_drag_families = ["Wing", "HTail"]\n',
            '[groups]\nTOTAL = "all"\n',
            "vorticity_drag_families",
            "HTail",
            REFERENCE + STUDY,
        ),
        (
            "iterations = 500\n" + CREATE_TAIL_BASE,
            '[groups]\nTOTAL = "all"\n',
            "base_region_operations[1]",
            "TailBase",
            REFERENCE + STUDY,
        ),
        # Without [study] too: the setup family keys and the groups that 0.38.0
        # left out silently under the flag.
        (
            'iterations = 500\nanalysis_families = ["Wing", "HTail"]\n',
            '[groups]\nTOTAL = "all"\n',
            "analysis_families",
            "HTail",
            REFERENCE,
        ),
        (
            'iterations = 500\nvorticity_drag_families = ["Wing", "HTail"]\n',
            '[groups]\nTOTAL = "all"\n',
            "vorticity_drag_families",
            "HTail",
            REFERENCE,
        ),
        (
            "iterations = 500\n",
            '[groups]\nTOTAL = "all"\nTAIL = "tail"\n',
            "groups.TAIL",
            "tail",
            REFERENCE,
        ),
    ],
)
def test_the_flag_turns_each_skip_into_a_refusal_of_the_wing_body_row(
    tmp_path, setup, pproc, key, name, reference
):
    """P0390-R02 (FR-988) --ignore-missing-families false refuses row 2001 on each key of FR-979."""
    workspace, path = study(tmp_path, reference=reference, setup=setup, pproc=pproc)
    plan, said = planned(workspace, path, ignore_missing_families=False)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    error = error_of(plan, "2001")
    assert f"cites {name!r} under {key}" in error
    assert "ignore_missing_families (CLI: --ignore-missing-families) was given as false" in error
    assert fr435_warnings(said) == []
    plan, _ = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2002": {PlanStatus.READY}}


def test_the_flag_refuses_an_axial_separation_family_before_the_build_guard(tmp_path):
    """P0390-R02 (FR-988) axial_separation_families: the wing-body row refused by the flag.

    26.124 refuses the command itself on every row (RPT-018), so the full model
    is BLOCKED by its build; the wing-body row is refused first, for the name.
    """
    setup = 'iterations = 500\naxial_separation_families = ["Wing", "HTail"]\n'
    workspace, path = study(tmp_path, setup=setup, pproc='[groups]\nTOTAL = "all"\n')
    plan, _ = planned(workspace, path, ignore_missing_families=False)
    error = error_of(plan, "2001")
    assert "cites 'HTail' under axial_separation_families" in error
    assert "ignore_missing_families (CLI: --ignore-missing-families) was given as false" in error
    assert "cites 'HTail'" not in error_of(plan, "2002")


# --- FR-980: the vocabulary and its table ----------------------------------------


def test_the_vocabulary_is_the_surfaces_the_aliases_and_their_members(tmp_path):
    """P0390-R02 (FR-980) [study] reaches ReferenceArtifact.study; how a name is held."""
    from pyflightstream.cases._skipped_families import held_by_the_study
    from pyflightstream.workspace.inputs import resolve_reference

    workspace, _ = study(tmp_path)
    reference = resolve_reference(workspace.inputs_dir, "r001")
    assert reference.study is not None
    assert list(reference.study.surfaces) == STUDY_SURFACES
    vocabulary = [*STUDY_SURFACES, "airframe", "tail", "lifting"]
    assert held_by_the_study("sting", vocabulary)
    assert held_by_the_study("TAIL", vocabulary)
    assert not held_by_the_study("Stinng", vocabulary)
    assert held_by_the_study("Blade", ["Blade1"]) and not held_by_the_study("Blade2", ["Blade1"])


@pytest.mark.parametrize(
    ("table", "said"),
    [
        (
            '[study]\nsurfaces = ["Wing"]\nmodels = ["wb"]\n',
            "the key models, which it does not read",
        ),
        ("[study]\nsurfaces = []\n", "surfaces = [], which is not a non-empty list of names"),
        (
            '[study]\nsurfaces = "Wing"\n',
            "surfaces = 'Wing', which is not a non-empty list of names",
        ),
        (
            "[study]\nsurfaces = [1, 2]\n",
            "surfaces = [1, 2], which is not a non-empty list of names",
        ),
    ],
)
def test_a_study_table_of_another_shape_is_refused_naming_the_file_and_the_table(
    tmp_path, table, said
):
    """P0390-R02 (FR-980) another key, or surfaces that is not a list of names, is refused."""
    from pyflightstream.workspace import InputArtifactError
    from pyflightstream.workspace.inputs import resolve_reference

    workspace, _ = study(tmp_path, reference=REFERENCE + table)
    with pytest.raises(InputArtifactError) as refused:
        resolve_reference(workspace.inputs_dir, "r001")
    assert "r001.toml declares [study] with " + said in str(refused.value)


def test_a_study_table_stating_a_kind_is_the_block_it_was(tmp_path):
    """P0390-R02 (FR-980) a top-level [study] with a kind is a named point, as on 0.38.0."""
    from pyflightstream.workspace.inputs import resolve_reference

    table = '[study]\nkind = "airframe"\nx_m = 1.0\ny_m = 0.0\nz_m = 0.0\n'
    workspace, _ = study(tmp_path, reference=REFERENCE + table)
    reference = resolve_reference(workspace.inputs_dir, "r001")
    assert reference.study is None
    assert "study" in reference.points


# --- review fixes: the boundary list as the geometry opened it, one reader, one line ---


def test_a_name_the_setup_deleted_is_not_judged_a_name_the_model_lacks(tmp_path):
    """P0390-R02 (FR-982) vorticity_drag_families citing the deleted Sting: no line, no skip.

    The wing-body-tail model carries the Sting, the setup removes it, and a
    later key citing it is judged against the boundary list as the geometry
    opened it: the model does not lack it, so nothing is skipped or said.
    """
    setup = SETUP.replace(
        'vorticity_drag_families = ["Wing", "HTail"]',
        'vorticity_drag_families = ["Wing", "HTail", "Sting"]',
    )
    workspace, path = study(tmp_path, setup=setup, models=(WING_BODY_TAIL,))
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2002": {PlanStatus.READY}}
    assert fr435_warnings(said) == []
    ran(workspace, path)
    points = [point for record in workspace.read_manifest() for point in record.as_points()]
    assert [point.skipped_names for point in points] == [None, None]


def test_two_references_holding_one_name_are_listed_in_one_warning(tmp_path):
    """P0390-R02 (FR-987) two references, one line, both named."""
    workspace, path = study(tmp_path, models=(WING_BODY, WING_ALONE))
    other = workspace.inputs_dir / "references" / "r002.toml"
    other.write_text(REFERENCE + STUDY, encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line.replace("r001", "r002") if "w.fsm" in line else line for line in lines]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2003": {PlanStatus.READY}}
    sting = [text for text in fr435_warnings(said) if "delete_surfaces cites 'Sting'" in text]
    assert len(sting) == 1, sting
    assert "'r001'" in sting[0] and "'r002'" in sting[0]
    assert "'2001', '2003'" in sting[0]


def test_one_reader_of_the_flag_treats_absent_and_blank_alike():
    """P0390-R02 (FR-988) the flag's one reader: absent and blank skip, false refuses."""
    from pyflightstream.cases import ReferenceData, SimCase, SweepAxis
    from pyflightstream.cases._skipped_families import (
        ignores_missing_families,
        refuses_a_name_the_model_lacks,
    )

    def row(**variables):
        return SimCase(
            sim_id="1",
            aircraft="A",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            reference=ReferenceData(area=1.0, length=1.0),
            variables=variables,
        )

    assert ignores_missing_families(row()) is True
    assert ignores_missing_families(row(IGNORE_MISSING_FAMILIES="  ")) is True
    assert ignores_missing_families(row(IGNORE_MISSING_FAMILIES="false")) is False
    assert refuses_a_name_the_model_lacks(row(IGNORE_MISSING_FAMILIES="false")) is True
    from pyflightstream.cases.workflows import _names

    assert not hasattr(_names, "_ignore_missing_families")


def test_the_additional_post_judges_the_group_members_the_model_lacks(tmp_path):
    """P0390-R02 (FR-984, FR-986) the extraction refuses a misspelled member, skips a held one."""
    from pyflightstream.cases import CampaignConfigError, PprocSpec, workflows
    from pyflightstream.script import Script
    from tests.tier1_offline.test_additional_post import SAVED, STEM, a_point_of
    from tests.tier1_offline.test_saved_simulation import as_a_matrix_row

    run = as_a_matrix_row(a_point_of("steady", tmp_path), "steady", STEM)
    reference = run.reference.model_copy(update={"study_surfaces": ("W", "B", "Tail")})
    shadow = workflows.frames_of_the_run(run, BUILD)

    def extract(member: str):
        table = {"exports": {"tecplot": False}, "groups": {"1": "W", "2": member}}
        pproc = PprocSpec.model_validate(table)
        case = run.model_copy(
            update={
                "reference": reference,
                "pproc": pproc,
                "pproc_id": "p002",
                "outputs": list(workflows.additional_outputs(pproc, stem=STEM, unsteady=False)),
            }
        )
        workflows.build_additional_script(case, Script(BUILD), saved=SAVED, shadow=shadow)

    extract("Tail")
    with pytest.raises(CampaignConfigError, match="Tial"):
        extract("Tial")


# --- W3 review fixes: the model as it opened, the rotor names, the words, the flag ---

SUPPORT_ALIAS = 'support = ["Sting"]\n'


@pytest.mark.parametrize("member", ["Sting", "support"])
def test_a_group_citing_a_surface_the_setup_deleted_is_not_judged(tmp_path, member):
    """P0390-R02 (FR-982, FR-990) a [groups] member the setup removed: no line, no skip, no refusal.

    The wing-body-tail model carries the Sting and the setup removes it; a
    group citing it, by name or through an alias, is classified against the
    boundary list as the geometry opened it, so the model does not lack it. Under
    ``--ignore-missing-families false`` it is not refused either.
    """
    pproc = PPROC + f'SUPPORT = "{member}"\n'
    workspace, path = study(
        tmp_path,
        reference=REFERENCE + SUPPORT_ALIAS + STUDY,
        pproc=pproc,
        models=(WING_BODY_TAIL,),
    )
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2002": {PlanStatus.READY}}
    assert fr435_warnings(said) == []
    plan, _ = planned(workspace, path, ignore_missing_families=False)
    assert status_of(plan) == {"2002": {PlanStatus.READY}}
    ran(workspace, path)
    points = [point for record in workspace.read_manifest() for point in record.as_points()]
    assert [point.skipped_names for point in points] == [None, None]


ROTOR = (
    '[rotors.PUSHER]\nalias = "PUSHER"\naxis = "Z"\ndiameter_m = 1.0\n'
    'families_general = ["Spinner"]\nfamilies_blades = ["Prop1", "Prop2"]\n'
)
WING_BODY_PROP = ("2004", "wbp.fsm", ["Wing", "Body", "Base", "Spinner", "Prop1", "Prop2"])


def test_a_rotor_name_and_its_families_are_in_the_vocabulary(tmp_path):
    """P0390-R02 (FR-980, FR-982) a rotor block's own name: held by the study, selects its families.

    The study declares the wing-body surfaces alone; the reference's rotor
    block PUSHER names the propeller's families. ``analysis_families`` citing
    PUSHER is read as on 0.38.0 on the model carrying the propeller (it
    selects its families) and is skipped and said on the wing-body model,
    never refused as a misspelling; so is a blade family the rotor declares,
    cited by a group, and each family of the integration group the binder adds
    for the rotor (item 15).
    """
    study_table = '[study]\nsurfaces = ["Wing", "Body", "Base"]\n'
    pproc = 'base_regions = ["Base"]\n[groups]\nTOTAL = "all"\nP2 = "Prop2"\n'
    workspace, path = study(
        tmp_path,
        reference=REFERENCE + study_table + ROTOR,
        setup='iterations = 500\nanalysis_families = ["Wing", "Body", "PUSHER"]\n',
        pproc=pproc,
        models=(WING_BODY, WING_BODY_PROP),
    )
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2004": {PlanStatus.READY}}
    lines = fr435_warnings(said)
    said_skips = {
        (match.group(1), match.group(2))
        for line in lines
        for match in [re.search(r": (\S+) cites '(\w+)', which the study", line)]
        if match
    }
    assert said_skips == {
        ("analysis_families", "PUSHER"),
        ("groups.P2", "Prop2"),
        ("groups.PUSHER", "Spinner"),
        ("groups.PUSHER", "Prop1"),
        ("groups.PUSHER", "Prop2"),
    }, lines
    assert all("row '2001'" in line and "'2004'" not in line for line in lines), lines


@pytest.mark.parametrize(
    ("setup", "pproc", "v0380"),
    [
        (
            SETUP.replace('delete_surfaces = ["Sting"]', 'delete_surfaces = ["Sting", "each"]'),
            PPROC,
            "states delete_surfaces with 'each', and the inventory declares no surface",
        ),
        (
            without(SETUP, 'delete_surfaces = ["Sting"]\n'),
            PPROC.replace('base_regions = ["Base", "TailBase"]', 'base_regions = ["Base", "each"]'),
            "states BASE_REGIONS with 'each', and the mesh block of",
        ),
    ],
)
def test_the_words_that_name_no_set_are_never_judged_by_the_study(tmp_path, setup, pproc, v0380):
    """P0390-R02 (FR-982) ``each`` in delete_surfaces or base_regions keeps its 0.38.0 reading.

    The study never skips, refuses or says ``all``, ``each`` or
    ``each_blade``: the word is read as 0.38.0 reads it (here its refusal as a
    name no surface carries), on both rows and at either flag, and is never
    called a misspelling of the study's vocabulary.
    """
    workspace, path = study(tmp_path, setup=setup, pproc=pproc)
    for options in ({}, {"ignore_missing_families": False}):
        plan, said = planned(workspace, path, **options)
        assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.BLOCKED}}
        rows = ("2002",) if options else ("2001", "2002")
        for row in rows:
            error = error_of(plan, row)
            assert v0380 in error, error
            assert "cites 'each'" not in error and "(FR-435)" not in error, error
        assert not [line for line in fr435_warnings(said) if "'each'" in line]


@pytest.mark.parametrize(
    ("setup", "pproc", "key", "name", "v0380"),
    [
        (
            SETUP,
            PPROC,
            "delete_surfaces",
            "Sting",
            "states delete_surfaces with 'Sting', and the inventory declares no surface",
        ),
        (
            without(SETUP, 'delete_surfaces = ["Sting"]\n'),
            'base_regions = ["Base", "TailBase"]\n[groups]\nTOTAL = "all"\n',
            "base_regions",
            "TailBase",
            "states BASE_REGIONS with 'TailBase', and the mesh block of wb.fsm",
        ),
        (
            "iterations = 500\n" + CREATE_TAIL_BASE,
            '[groups]\nTOTAL = "all"\n',
            "base_region_operations[1]",
            "TailBase",
            "TailBase",
        ),
    ],
)
def test_the_flag_refuses_every_key_without_a_study(tmp_path, setup, pproc, key, name, v0380):
    """P0390-R02 (FR-988, FR-981) no [study]: the flag refuses delete_surfaces and the base keys.

    ``--ignore-missing-families false`` names the key the artifact writes (the
    pproc's ``base_regions``, not the row's ``BASE_REGIONS``), the name and the
    flag on a reference declaring no vocabulary; at the default flag the row
    keeps its 0.38.0 refusal, which names no flag.
    """
    workspace, path = study(tmp_path, reference=REFERENCE, setup=setup, pproc=pproc)
    plan, said = planned(workspace, path, ignore_missing_families=False)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    error = error_of(plan, "2001")
    assert f"cites {name!r} under {key}" in error, error
    assert "ignore_missing_families (CLI: --ignore-missing-families) was given as false" in error
    assert "BASE_REGIONS" not in error
    assert fr435_warnings(said) == []
    plan, said = planned(workspace, path)
    assert status_of(plan) == {"2001": {PlanStatus.BLOCKED}, "2002": {PlanStatus.READY}}
    error = error_of(plan, "2001")
    assert v0380 in error, error
    assert "ignore_missing_families" not in error and "(FR-435)" not in error, error
    assert fr435_warnings(said) == []
