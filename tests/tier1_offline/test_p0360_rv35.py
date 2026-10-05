"""Review regressions registered for 0.36.0, using synthetic inputs only."""

from __future__ import annotations

import ast
import importlib.util
import json
import operator
from dataclasses import replace
from pathlib import Path

import pytest

from pyflightstream.results.log import RESTART_MARKER, split_job_log
from pyflightstream.run._batch_split import split_polars
from pyflightstream.versions import SETUP_RESET_LOG_PREFIXES
from tests.support_helpers import grouped_plan_fixture as _fixture
from tests.tier1_offline.test_p0350_batch_plan import _plan
from tests.tier1_offline.test_p0350_batch_split import _unit

REPO = Path(__file__).resolve().parents[2]


def _licensed_imports(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            names = [prefix, *(f"{prefix}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            or isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
            and node.func.attr == "import_module"
        ):
            found.extend(
                arg.value
                for arg in [*node.args, *(keyword.value for keyword in node.keywords)]
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and "tier3_licensed" in arg.value
            )
            continue
        else:
            continue
        found.extend(name for name in names if "tier3_licensed" in name.split("."))
    return found


def test_tier1_never_imports_the_licensed_tier():
    """P0360-RV35-C2-ARCH-1 (NFR-41): all import depths stay independent of tier 3."""
    paths = sorted((REPO / "tests/tier1_offline").rglob("*.py"))
    paths += [REPO / "tests/support_tier3.py", REPO / "tests/support_helpers.py"]
    assert len(paths) > 100
    assert not {
        path.name: imports
        for path in paths
        if (imports := _licensed_imports(path.read_text(encoding="utf-8")))
    }
    controls = [
        "from tests.tier3_licensed.fsi_lq1 import one_pass",
        "import tests.tier3_licensed.offline as offline",
        "from tests import tier3_licensed",
        "def helper():\n    from tests.tier3_licensed import offline",
        "if TYPE_CHECKING:\n    from tests.tier3_licensed import offline",
        "from ..tier3_licensed import offline",
        'importlib.import_module("tests.tier3_licensed.offline")',
        '__import__("tests.tier3_licensed.offline")',
        'importlib.import_module(name="tests.tier3_licensed.offline")',
        'def helper():\n    __import__("tests.tier3_licensed.offline")',
    ]
    for source in controls:
        assert _licensed_imports(source), source
    assert not _licensed_imports("from tests.support_tier3 import one_pass")
    assert not _licensed_imports('importlib.import_module("tests.support_tier3")')
    assert not _licensed_imports('name = "tests.tier3_licensed.offline"')


@pytest.mark.parametrize(("mode", "batch"), [("batch", 1), ("batch", 2), ("polar_sweep", None)])
def test_command_line_alone_names_each_job_folder(tmp_path, mode, batch):
    """P0360-RV35-C2-QA-1 (FR-405): COMMAND_LINE alone names its resolving folder."""
    workspace, matrix = _fixture(tmp_path, walltimes=("1h", "1h"), sweep="0.0,2.0")
    setup = workspace.inputs_dir / "setups" / "s002.toml"
    setup.write_text(
        setup.read_text(encoding="utf-8") + '\n[[unsteady_solver_actions]]\ntype = "COMMAND_LINE"\n'
        'name = "marker"\nfilename = "python marker.py"\n',
        encoding="utf-8",
    )
    plan = _plan(workspace, matrix, mode=mode, batch=batch)
    assert not plan.blocked and plan.grouping.left_out == ()
    notes = [note for note in plan.grouping.warnings if "COMMAND_LINE" in note]
    assert len(notes) == len(plan.grouping.jobs) > 0
    for job in plan.grouping.jobs:
        (note,) = [note for note in notes if f"POL {', '.join(job.sims)}:" in note]
        assert f"resolves in '{job.dir}'" in note
        assert "Relative SCRIPT" not in note
    receipt = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    assert receipt["grouping"]["warnings"] == list(plan.grouping.warnings)


def test_custom_polar_time_rule_keeps_a_flightstream_titled_text_file():
    """P0360-RV35-O7-QA-1 (NFR-40): a non-.dat file keeps even a matching title and stamp."""
    spec = importlib.util.spec_from_file_location(
        "rv35_check_parity", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    data = (
        b"FlightStream - SYNTHETIC POLAR\n320720\nSat Oct 03 05:10:55  2026\n"
        b"007 01\nMNOM SREF CREF BREF XMOM YMOM ZMOM\n"
    )
    assert parity.normalize("matrix/polars/P4800-M144_g01.txt", data) == data
    assert b"<TIME>" in parity.normalize("matrix/polars/P4800-M144_g01.dat", data)


@pytest.mark.parametrize("requested", [1, 3, 4])
def test_acoustic_isolation_is_named_for_every_requested_job_count(requested):
    """P0360-RV35-R-API-1 (FR-406): ordinary polars share; acoustic polars run alone."""
    units = [
        replace(_unit("7001", 1, 1, points=2), acoustic=True),
        _unit("7002", 2, 1, points=2),
        _unit("7003", 3, 1, points=2),
        replace(_unit("7004", 4, 1, points=2), acoustic=True),
    ]
    if requested == 4:
        units.append(replace(_unit("7005", 5, 1, points=2), acoustic=True))
    jobs, notes = split_polars(units, requested)
    assert [note for note in notes if "FR-406" in note] == [
        f"POL {'7001, 7004, 7005' if requested == 4 else '7001, 7004'}: "
        "an acoustic polar runs in a job of its own, "
        "all its points together (FR-406)"
    ]
    assert [job.units for job in jobs] == [
        (units[0],),
        tuple(units[1:3]),
        *((unit,) for unit in units[3:]),
    ]
    assert [unit.run_ids for job in jobs for unit in job.units] == [unit.run_ids for unit in units]
    _, ordinary_notes = split_polars([replace(unit, acoustic=False) for unit in units], requested)
    assert not any("FR-406" in note for note in ordinary_notes)


def test_setup_reset_uses_the_build_vocabulary_and_stays_inside_the_point():
    """P0360-RV35-P1-ARCH-Q4 (FR-407): both neighbours come from the measured build table."""
    assert SETUP_RESET_LOG_PREFIXES["26.124"] == ("Solver mode:", "Symmetry is ")
    with pytest.raises(TypeError):
        operator.setitem(SETUP_RESET_LOG_PREFIXES, "26.124", ("changed", "changed"))
    tree = ast.parse((REPO / "src/pyflightstream/results/log.py").read_text(encoding="utf-8"))
    reset = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_initialization_reset"
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "SETUP_RESET_LOG_PREFIXES"
        for node in ast.walk(reset)
    )
    literals = [node.value for node in ast.walk(reset) if isinstance(node, ast.Constant)]
    assert all(prefix not in literals for prefix in SETUP_RESET_LOG_PREFIXES["26.124"])
    text = (
        f"opening\nSolver mode: Unsteady\n\n{RESTART_MARKER}\x00\n\n"
        f"Symmetry is disabled.\nsolve ended\n{RESTART_MARKER}\nnext point\n"
    )
    segments = split_job_log(text)
    assert [(s.first_line, s.last_line, s.complete) for s in segments] == [
        (0, 6, True),
        (8, 8, False),
    ]
    assert (
        RESTART_MARKER in text.splitlines()[segments[0].first_line : segments[0].last_line + 1][3]
    )


def test_solver_mode_without_following_symmetry_is_a_point_boundary():
    """GATEFIX mutant 7 (FR-407): solver mode alone cannot identify a setup reset."""
    text = f"opening\nSolver mode: Unsteady\n{RESTART_MARKER}\nnext model\nsolve ended\n"
    assert [(s.first_line, s.last_line, s.complete) for s in split_job_log(text)] == [
        (0, 1, True),
        (3, 4, False),
    ]
