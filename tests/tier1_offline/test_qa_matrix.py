"""Tier 1: ``pyfs-qa physics`` reads the workspace (PFS-2031.17, GOAL-012).

Her decision B of 2026-09-08 (design study 66): the command runs
``matriz_physics.fs`` through the run layer, reduces the records with the
qa functions and writes the same ``PHY-*`` report the hand-built scripts
wrote; the hand-built builders retire; ``drift`` is two runs of the matrix
under two registries and a diff of the two reductions.

The solver is one python process standing in for FlightStream: it reads
the script each point receives, writes the loads table the script exports
with coefficients that are known functions of the angle of attack, and
nothing else. The workspace is a copy of the tier-3 library with the
export set narrowed to the loads table, and the matrix is the tier-3
physics matrix itself, so the rows the licensed machine runs are the rows
this test runs.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import yaml

import pyflightstream

HERE = Path(__file__).resolve().parent
TIER3 = HERE.parent / "tier3_licensed"
GOLDENS = HERE / "goldens" / "qa_matrix"
LOADS_FIXTURE = HERE / "fixtures" / "loads_steady_26.120.txt"
SRC = Path(pyflightstream.__file__).resolve().parent

#: The stand-in solver. It reads the point's script, takes the angle of
#: attack, the sideslip and the velocity off the lines the workflow
#: emitted, and writes the loads table the script exports. The wing's
#: coefficients are linear in alpha with the slope of the committed
#: PHY-01 reference, the mirrored half carries a slightly larger slope so
#: the PHY-02 deltas are nonzero, and a script that creates a motion is
#: the rotor and writes the PHY-05 reference values. Every other export
#: the script names is left unwritten, which is why the workspace below
#: narrows the export set to the loads table.
STUB_SOLVER = """
import pathlib
import re
import sys

script = pathlib.Path(sys.argv[1])
fixture = pathlib.Path(sys.argv[2])
lines = script.read_text(encoding="utf-8").splitlines()


def value(command, default):
    for line in lines:
        if line.startswith(command + " "):
            return float(line.split()[1])
    return default


alpha = value("SOLVER_SET_AOA", 0.0)
beta = value("SOLVER_SET_SIDESLIP", 0.0)
velocity = value("SOLVER_SET_VELOCITY", 30.0)
unsteady = "SET_SOLVER_UNSTEADY" in lines
rotor = any(line.startswith("CREATE_NEW_MOTION") for line in lines)
mirror = "SYMMETRY MIRROR" in lines

if rotor:
    surface = "Blade1"
    total = {"Cx": 0.0451749, "Cy": 0.0, "Cz": -0.0001012, "CL": -0.0001012,
             "CDi": -0.0451749, "CDo": 0.0007011, "CMx": 0.0, "CMy": 0.0286429, "CMz": 0.0}
else:
    surface = "Wing"
    slope = 0.0846 if mirror else 0.08425
    lift = slope * alpha
    total = {"Cx": 0.0, "Cy": 0.0, "Cz": lift, "CL": lift,
             "CDi": 0.0049 * (alpha / 4.0) ** 2, "CDo": 0.0007,
             "CMx": 0.0, "CMy": -0.0212 * alpha, "CMz": 0.0}

row = ",".join("%+.7f" % total[key]
               for key in ("Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz"))
body = fixture.read_text(encoding="utf-8")


def stamp(label, text):
    global body
    body = re.sub(r"(" + re.escape(label) + r"\\s+)\\S.*", lambda m: m.group(1) + text, body)


stamp("Angle of attack (Deg)", "%.3f" % alpha)
stamp("Side-slip angle (Deg)", "%.3f" % beta)
stamp("Freestream velocity (m/s)", "%.3f" % velocity)
stamp("Reference velocity (m/s)", "%.3f" % velocity)
stamp("Solver mode:", "Unsteady" if unsteady else "Steady")
stamp("Current solver iteration number:", "500" if unsteady else "312")
body = re.sub(r"^\\s*Wing,.*$", "     " + surface + "," + row, body, flags=re.M)
body = re.sub(r"^\\s*Total,.*$", "     Total," + row, body, flags=re.M)

for index, line in enumerate(lines):
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text(body, encoding="utf-8")
"""

#: The post-processing artifact of the stub workspace: the groups the
#: products are written per, and every export but the loads table
#: switched off, because the stand-in solver writes the loads table alone
#: and a declared export that is not there fails the point.
STUB_PPROC = (
    '[groups]\n"1" = ["Wing", "Blade1"]\n\n[exports]\nsimulation = false\ntecplot = false\n'
    "sections = false\nsectional_loads = false\nprobes = false\nplots = false\nlog = false\n"
)


@pytest.fixture
def stub_workspace(tmp_path, monkeypatch) -> Path:
    """A workspace holding the tier-3 library and physics matrix, on a stand-in solver."""
    from pyflightstream.run import LocalExecutor

    root = tmp_path / "ws"
    shutil.copytree(
        TIER3 / "inputs", root / "inputs", ignore=shutil.ignore_patterns("*.local.toml")
    )
    for artifact in ("p001", "p002"):
        (root / "inputs" / "pproc" / f"{artifact}.toml").write_text(STUB_PPROC, encoding="utf-8")
    shutil.copy(TIER3 / "matriz_physics.fs", root / "matriz_physics.fs")
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB_SOLVER, encoding="utf-8")

    class StubSolver(LocalExecutor):
        def __init__(self, *args, **kwargs):
            super().__init__(fs_exe=sys.executable, hidden=True)

        def _argv(self, script_path: Path) -> list[str]:
            return [sys.executable, str(stub), str(script_path), str(LOADS_FIXTURE)]

    # `run_matrix` builds its own executor from the registry, so the
    # replacement is made where it constructs one, as test_run_cli does.
    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", StubSolver)
    return root


def _cli(argv: list[str]) -> int:
    """Run ``pyfs-qa`` and return its exit code, an argparse exit included.

    Argparse leaves through SystemExit on an unknown flag; catching it here
    is what lets the assertions below fail on the exit code rather than on
    the parser, which is the RED this module was measured with.
    """
    from pyflightstream.qa.cli import main

    try:
        return main(argv)
    except SystemExit as leaving:
        return int(leaving.code or 0)


def _report_pair(report_dir: Path, series: str) -> tuple[Path, Path]:
    yamls = sorted(report_dir.glob(f"{series}-*.yaml"))
    assert len(yamls) == 1, f"expected one {series} report under {report_dir}, found {yamls}"
    return yamls[0], yamls[0].with_suffix(".md")


def _filled_golden(name: str, document: dict) -> str:
    """The committed report shape with the run's two volatile values put in.

    The executable is the registry's placeholder name and carries no
    digest, because the stand-in solver replaces the executor and never
    the registry, so both are literal in the golden; the date and the
    package version move with every day and every release.
    """
    text = (GOLDENS / name).read_text(encoding="utf-8")
    for placeholder, value in (
        ("{date}", document["date"]),
        ("{package_version}", document["package_version"]),
    ):
        text = text.replace(placeholder, str(value))
    return text


def test_pyfs_qa_physics_runs_the_matrix_and_writes_the_report_in_the_committed_shape(
    stub_workspace, tmp_path
):
    """The acceptance of PFS-2031.17, end to end over the stand-in solver.

    The Markdown face is compared to a committed golden with the two
    values that differ per day and per release put in from the YAML face,
    the date and the package version. Everything else, headings, table
    columns, point labels, metric names, references, bands and verdict
    words, is the shape the hand-built scripts wrote and must stay.
    """
    reports = tmp_path / "reports"
    code = _cli(["physics", "--workspace", str(stub_workspace), "--report-dir", str(reports)])
    assert code == 0, "pyfs-qa physics --workspace did not run the matrix and exit 0"
    yaml_path, md_path = _report_pair(reports, "PHY")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["schema"] == "pyflightstream-physics-report/1"
    assert document["fs_version"] == "26.120"
    assert md_path.read_text(encoding="utf-8") == _filled_golden("PHY-stub-workspace.md", document)


def test_the_report_reduces_every_case_the_matrix_states_with_the_qa_functions(
    stub_workspace, tmp_path
):
    """One case per PHY id the rows name, every metric of its reference judged."""
    from pyflightstream.qa.physics import load_reference

    reports = tmp_path / "reports"
    assert _cli(["physics", "--workspace", str(stub_workspace), "--report-dir", str(reports)]) == 0
    document = yaml.safe_load(_report_pair(reports, "PHY")[0].read_text(encoding="utf-8"))
    assert list(document["cases"]) == ["PHY-01", "PHY-02", "PHY-05", "PHY-06"]
    for case_id, body in document["cases"].items():
        reference = load_reference(case_id)
        assert reference is not None
        assert body["error"] is None, (case_id, body["error"])
        assert set(body["metrics"]) == set(reference.metrics), case_id
        assert set(body["verdicts"].values()) == {"pass"}, (case_id, body["verdicts"])
    # The point rows carry the workspace's own identities: the row and the point.
    labels = [point["label"] for point in document["cases"]["PHY-01"]["points"]]
    assert labels == ["sim_5001/a+00.0", "sim_5001/a+02.0", "sim_5001/a+04.0", "sim_5001/a+06.0"]
    # PHY-06 is the unsteady row against the steady polar of the PHY-01 row.
    assert len(document["cases"]["PHY-06"]["points"]) == 8
    assert document["summary"] == {"pass": 30, "warn": 0, "fail": 0, "no_reference": 0}
    assert document["source"] == "matriz_physics.fs in workspace ws"


def test_resume_reduces_the_recorded_run_without_spending_a_second_seat(stub_workspace, tmp_path):
    """The command on the licensed machine after ``pyfs-matrix run``.

    A recorded point is refused by the run layer unless the run resumes,
    and a resumed run over a complete manifest executes nothing; the
    report is then the reduction of what the workspace recorded, which is
    what ``pyfs-qa physics --resume`` is for on a workspace whose physics
    matrix already ran.
    """
    from pyflightstream.workspace import CampaignWorkspace

    reports = tmp_path / "reports"
    assert _cli(["physics", "--workspace", str(stub_workspace), "--report-dir", str(reports)]) == 0
    recorded = len(CampaignWorkspace(stub_workspace).read_manifest())
    assert recorded == 11
    # Without --resume the run layer refuses the recorded points, before
    # any solver process, and the report is not written.
    code = _cli(
        [
            "physics",
            "--workspace",
            str(stub_workspace),
            "--report-dir",
            str(reports),
            "--label",
            "again",
        ]
    )
    assert code == 2
    assert not list(reports.glob("*_again.yaml"))
    code = _cli(
        [
            "physics",
            "--workspace",
            str(stub_workspace),
            "--report-dir",
            str(reports),
            "--label",
            "again",
            "--resume",
        ]
    )
    assert code == 0
    assert len(CampaignWorkspace(stub_workspace).read_manifest()) == recorded
    document = yaml.safe_load(next(reports.glob("*_again.yaml")).read_text(encoding="utf-8"))
    assert document["summary"]["pass"] == 30


def test_drift_is_two_runs_of_the_matrix_under_two_registries_and_a_diff(stub_workspace, tmp_path):
    """FR-27 through the workspace: the same rows, two executables, one diff.

    The degenerate self-comparison, the same version on both sides, is
    the form that proves the machinery: every delta lands at zero. Each
    side is its own workspace under the workroot, a copy of the library
    with an overlay registry sending every build the rows name to that
    side's executable, so the two manifests and the two sweep tables are
    kept apart and both survive the run.
    """
    reports = tmp_path / "reports"
    workroot = tmp_path / "drift"
    code = _cli(
        [
            "drift",
            "--workspace",
            str(stub_workspace),
            "--fs-versions",
            "26.120,26.120",
            "--fs-exe",
            f"26.120={sys.executable}",
            "--workroot",
            str(workroot),
            "--report-dir",
            str(reports),
        ]
    )
    assert code == 0, "pyfs-qa drift --workspace did not run the matrix twice and exit 0"
    yaml_path, md_path = _report_pair(reports, "DRF")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["schema"] == "pyflightstream-drift-report/1"
    assert list(document["cases"]) == ["PHY-01", "PHY-02", "PHY-05", "PHY-06"]
    for case_id, body in document["cases"].items():
        assert body["error"] is None, (case_id, body["error"])
        for name, metric in body["metrics"].items():
            assert metric["delta"] == 0.0, (case_id, name, metric)
            assert metric["verdict"] == "pass", (case_id, name, metric)
    assert document["summary"] == {"pass": 30, "warn": 0, "fail": 0, "no_reference": 0}
    sides = sorted(path.name for path in workroot.iterdir() if path.is_dir())
    assert sides == ["a_26120", "b_26120"]
    for side in sides:
        assert (workroot / side / "runs.json").is_file(), side
        assert (workroot / side / "post" / "matriz_physics" / "campaign_sweep.csv").is_file()
        overlay = (workroot / side / "inputs" / "executables.local.toml").read_text(
            encoding="utf-8"
        )
        assert '"26.120" = { path = ' in overlay and 'version = "26.120" }' in overlay
    assert "## PHY-06:" in md_path.read_text(encoding="utf-8")


def test_a_workspace_without_the_matrix_is_refused_naming_the_matrices_it_holds(
    stub_workspace, tmp_path, capsys
):
    (stub_workspace / "matriz_physics.fs").rename(stub_workspace / "matriz_other.fs")
    code = _cli(["physics", "--workspace", str(stub_workspace), "--report-dir", str(tmp_path)])
    error = capsys.readouterr().err
    assert code == 2
    assert "matriz_physics.fs" in error and "matriz_other.fs" in error, error
    assert "--matrix" in error, "the refusal does not name the flag that picks another matrix"


def test_rows_naming_two_builds_are_refused_before_anything_runs(stub_workspace, tmp_path, capsys):
    """A PHY report is evidence of ONE build; two builds is a drift, not a report."""
    matrix = stub_workspace / "matriz_physics.fs"
    text = matrix.read_text(encoding="utf-8")
    assert text.count("| 26.120   |") == 5
    matrix.write_text(text.replace("| 26.120   |", "| 26.123   |", 1), encoding="utf-8")
    code = _cli(["physics", "--workspace", str(stub_workspace), "--report-dir", str(tmp_path)])
    error = capsys.readouterr().err
    assert code == 2
    assert "26.120" in error and "26.123" in error and "drift" in error, error
    assert not list(tmp_path.glob("PHY-*")), "a report was written for a run that was refused"


# --- the reductions moved into the package ------------------------------------


def test_phy05_and_phy06_reductions_are_package_functions():
    """The reductions the tier-3 test carried inline, now where the driver reads them."""
    from pyflightstream.qa.physics import PointResult, phy05_metrics, phy06_metrics

    rotor = PointResult(
        0.0, {"CL": -0.0001, "CDi": -0.0452, "CDo": 0.0007, "CMy": 0.0286}, 54, True
    )
    assert phy05_metrics(rotor) == {"CL": -0.0001, "CDi": -0.0452, "CDo": 0.0007, "CMy": 0.0286}

    def polar(scale: float, label: str) -> list[PointResult]:
        return [
            PointResult(
                alpha,
                {"CL": scale * 0.0875 * alpha, "CDi": 0.001, "CDo": 0.0006, "CMy": -0.02 * alpha},
                300,
                True,
                label=f"{label}_{alpha:g}",
            )
            for alpha in (0.0, 2.0, 4.0, 6.0)
        ]

    steady = polar(1.0, "steady")
    unsteady = polar(1.01, "unsteady")
    metrics = phy06_metrics(steady, unsteady)
    assert len(metrics) == 16
    assert metrics["delta_CL_a4"] == pytest.approx(0.0035)
    assert metrics["delta_CD_a4"] == pytest.approx(0.0)
    assert metrics["delta_CMy_a6"] == pytest.approx(0.0)
    assert metrics["CL_slope_steady_per_rad"] == pytest.approx(5.01, abs=0.02)
    assert metrics["CL_slope_unsteady_per_rad"] == pytest.approx(5.06, abs=0.02)
    assert metrics["CMy_slope_steady_per_rad"] == pytest.approx(-1.146, abs=0.01)
    # The two polars are matched by angle, so a march at an angle the
    # steady polar did not solve is a refusal rather than a silent skip.
    with pytest.raises(ValueError, match="steady"):
        phy06_metrics(steady[:3], unsteady)


# --- the dependency direction the design settles --------------------------------


def _module_level_imports(source: str) -> set[str]:
    """Every dotted name a module imports at its top level."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_driver_sits_in_the_qa_layer_and_nothing_below_imports_it():
    """Where the driver lives, measured against the package's own layer table.

    The design study feared that reading the workspace would invert the
    direction, with the qa layer depending on the workspace layer. The
    layer table (`pyflightstream.overview._CORE_LAYERS`) says qa sits on
    the TOP row beside post, above run and workspace, so the driver's
    imports of the run and workspace layers run DOWNWARD and the fear
    rested on a misreading. What must hold is the converse: no module of
    the layers below may import the qa package back, and the driver
    imports what it composes at module level rather than inside a
    function body.
    """
    from pyflightstream.overview import _CORE_LAYERS

    spec = importlib.util.find_spec("pyflightstream.qa.matrix")
    assert spec is not None and spec.origin, (
        "the workspace driver of pyfs-qa physics, pyflightstream.qa.matrix, does not exist"
    )
    imported = _module_level_imports(Path(spec.origin).read_text(encoding="utf-8"))
    assert "pyflightstream.run.matrix" in imported, "the driver does not run the matrix"
    assert "pyflightstream.workspace" in imported, "the driver does not read the workspace"
    assert "pyflightstream.qa.physics" in imported, "the driver does not reduce with qa"
    rows = {name: row for row, (names, _) in enumerate(_CORE_LAYERS) for name in names}
    assert rows["qa"] < rows["run"] == rows["workspace"], (
        "the layer table no longer puts qa above run and workspace, so the "
        "direction this module measures needs re-deciding rather than re-asserting"
    )
    below = [name for name, row in rows.items() if row > rows["qa"]]
    offenders = []
    for layer in below:
        for module in sorted((SRC / layer).rglob("*.py")):
            back = {
                name
                for name in _module_level_imports(module.read_text(encoding="utf-8"))
                if name == "pyflightstream.qa" or name.startswith("pyflightstream.qa.")
            }
            if back:
                offenders.append(f"{module.relative_to(SRC).as_posix()} imports {sorted(back)}")
    assert not offenders, "a layer below qa imports it back:\n  " + "\n  ".join(offenders)
