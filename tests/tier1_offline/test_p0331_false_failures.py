"""Tier 1: the two false FAILED_INCOMPLETE_OUTPUT verdicts that 0.33.1 removes.

Both were measured offline on the recorded outputs of complete steady points
(the replay of 2026-10-01), and both exist in 0.32.0 and 0.33.0 alike.

The first, here: a steady row's points run as ONE job in one solver session,
and each point's ``EXPORT_LOG`` writes the session's log so far, so the log of
point k holds k solves with the iteration counter starting again at 1 for each.
The package read as the log only a file holding ONE solve, so from point 2 on
no log was read, the trailing-edge count of a row importing its edges from a
file could not be checked, and a converged point was recorded
FAILED_INCOMPLETE_OUTPUT with its log on disk. The log the stand-in writes for
point 2 is the recorded one of such a job on 26.124 (the licence lines dropped
and the script path neutral): 8 trailing edges imported, a solve of 28
iterations, then one of 25. RPT-139 is the measurement of that behaviour and
names the source of this log by its digest.

The second, below: a post-processing artifact whose section distributions cut
a wing, cited by a row whose geometry is a body alone. The builder leaves every
distribution out and warns, as one artifact serving several geometries asks,
but the row still declared the section Cp plot and its script still exported
it; with no section the solver writes no such file, and every point was
recorded FAILED_INCOMPLETE_OUTPUT for it. The declaration now follows the
builder's family selection over the row's geometry, and the export follows the
declaration.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-55 and FR-51 (both amended 0.33.1).

from __future__ import annotations

import csv
import json
import sys
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import (
    EXPORT_KINDS,
    PprocSpec,
    RotorBlock,
    SimCase,
    SweepAxis,
    default_outputs,
)
from pyflightstream.cases.matrix import MATRIX_COLUMNS
from pyflightstream.cases.workflows import row_outputs, workflow_registry
from pyflightstream.run import Assessment, CampaignErrors, LocalExecutor
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run._wake_edge_verdict import collected_solver_log
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import STUB_BODY, make_library
from tests.tier1_offline.test_raw_mesh_conditions import (
    FILE_ROUTE,
    MIDPOINTS,
    RECIPES,
    ROW,
    WITH_LOG,
    _library,
    _named_node_file,
    _points_in,
    _points_text,
    write_matrix,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: The recorded log of point 2 of a steady job: two solves, one import line.
TWO_SOLVES = FIXTURES / "log_steady_job_two_solves_26.124.txt"

#: The stand-in for the solver of a steady job. It writes the loads table the
#: script asks for and, at the k-th EXPORT_LOG, the k-th log it is handed: the
#: session's log as it stood after k solves, which is what the solver writes.
JOB_STUB = """
import pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
logs = [pathlib.Path(name).read_text(encoding="utf-8") for name in sys.argv[2:]]
exported = 0
for index, line in enumerate(lines):
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text("LOADS", encoding="utf-8")
    if line == "EXPORT_LOG":
        text = logs[min(exported, len(logs) - 1)]
        pathlib.Path(lines[index + 1]).write_text(text, encoding="utf-8")
        exported += 1
"""


class _JobSolver(LocalExecutor):
    """Runs the stand-in above with the logs it writes, in order."""

    def __init__(self, stub: Path, logs: list[Path]):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub, self.logs = stub, logs

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path), *map(str, self.logs)]


def _names_no_log(case, execution, sim_dir):
    """A converged verdict that does not say which file it read as the log."""
    return Assessment(status=RunStatus.CONVERGED, iterations=25, residual=None)


#: The logs the job stand-in writes, in order: after one solve, after two.
JOB_LOGS = ("log_after_one_solve.txt", "log_after_two_solves.txt")


def _steady_job_of_two_points(tmp_path, job_stub=JOB_STUB):
    """Run a two-point steady job importing 8 trailing edges; return its workspace and record."""
    workspace = _library(tmp_path, FILE_ROUTE, points=_points_text(MIDPOINTS[:8]))
    text = TWO_SOLVES.read_text(encoding="utf-8")
    first = text.index("Angle of attack (Deg)")
    logs = [tmp_path / name for name in JOB_LOGS]
    logs[0].write_text(text[: text.index("Angle of attack (Deg)", first + 1)], encoding="utf-8")
    logs[1].write_text(text, encoding="utf-8")
    (tmp_path / "job_stub.py").write_text(job_stub, encoding="utf-8")
    row = ROW.format(build="26.124", outputs=WITH_LOG, geometry="wing.stl", tail="")
    write_matrix(tmp_path / "job.fs", [row.replace("| AL | 0.0 |", "| AL | 0.0,2.0 |")])
    return workspace, _run_steady_job(tmp_path, workspace)


def _run_steady_job(tmp_path, workspace, **again):
    """Run, or with ``again`` re-run, the job of ``tmp_path``; return its one record."""
    logs = [tmp_path / name for name in JOB_LOGS]
    try:
        run_matrix(
            tmp_path / "job.fs",
            workspace,
            name="matrix",
            default_fs_version="26.124",
            recipes=RECIPES,
            assess=_names_no_log,
            executor=_JobSolver(tmp_path / "job_stub.py", logs),
            recipe_registry=workflow_registry(),
            **again,
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return record


def test_point_2_of_a_steady_job_reads_its_cumulative_log_and_converges(tmp_path):
    # P0331-SWEEP-LOG (FR-55, amended 0.33.1): point 2's collected _log.txt
    # holds two solves, so the one-solve content rule finds no log; the point's
    # single collected _log.txt is then its log, its "8 trailing edges imported"
    # line meets the wake_edge_points the script wrote, and the point keeps its
    # CONVERGED verdict.
    text = TWO_SOLVES.read_text(encoding="utf-8")
    assert text.count("8 trailing edges imported for boundary Wing") == 1, "the fixture moved"
    assert "\n28 " in text and "\n1 " in text, "the fixture lost its counter reset"
    workspace, record = _steady_job_of_two_points(tmp_path)
    wake_edge_points = len(_points_in(_named_node_file(workspace, record)))
    assert wake_edge_points == 8, wake_edge_points
    statuses = [entry["status"] for entry in record.points_ran]
    assert len(statuses) == 2, record.points_ran
    assert statuses == [RunStatus.CONVERGED.value, RunStatus.CONVERGED.value], (
        statuses,
        record.error,
    )
    assert "no solver log was read" not in (record.error or ""), record.error


def _first_solve(text: str) -> str:
    """The log as it stood after the first solve: the fixture cut at its second solve."""
    first = text.index("Angle of attack (Deg)")
    return text[: text.index("Angle of attack (Deg)", first + 1)]


def test_two_collected_logs_neither_one_solve_is_no_log_one_that_is_is_the_log(tmp_path):
    # P0331-SWEEP-LOG (FR-55, amended 0.33.1): the fallback takes the ONE
    # collected _log.txt when no collected file parses as one solve. Two such
    # files, each holding the two-solve fixture text, are still a guess, and
    # the answer is None. Control: where one of the two holds a single solve,
    # the content rule finds it and that file is returned.
    text = TWO_SOLVES.read_text(encoding="utf-8")
    for name in ("a_log.txt", "b_log.txt"):
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert collected_solver_log(tmp_path, ["a_log.txt", "b_log.txt"], None) is None

    one = _first_solve(text)
    (tmp_path / "a_log.txt").write_text(one, encoding="utf-8")
    assert collected_solver_log(tmp_path, ["a_log.txt", "b_log.txt"], None) == one


# --- the second: the section Cp plot of a family the geometry does not carry ----------

#: A post-processing artifact whose one section distribution cuts the wing,
#: in the common moment frame, and declares nothing about the section Cp plot,
#: which it therefore asks for where it declares sections.
WING_SECTIONS_PPROC = (
    '[groups]\n"1" = "all"\n\n[exports]\ntecplot = false\n\n'
    "[sections]\ncount = 40\nplot_direction = 1\ninclude_symmetry = false\n\n"
    '[[sections.distributions]]\nfamilies = ["Wing", "W"]\nframe = "MRP"\nplanes = ["XZ"]\n'
)

#: The two geometries, by stem: a body alone, and the same body with a wing.
INVENTORIES = {"body": ["Fuselage"], "wingbody": ["Wing", "Fuselage"]}

#: The stand-in for the solver of a steady row. It writes the file named on the
#: line after every export verb, as the solver does, except the section Cp plot
#: of a script that creates no surface section: with no section the solver has
#: nothing to plot and writes no file, which is what a body row met.
SECTIONS_STUB = """
import pathlib, sys
verbs = {verbs!r}
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
cuts = any(line.split(" ")[0] == "NEW_SURFACE_SECTION_DISTRIBUTION" for line in lines)
for i, line in enumerate(lines[:-1]):
    if line.split(" ")[0] not in verbs:
        continue
    plotting = " ".join(lines[max(0, i - 2) : i])
    if line.startswith("SAVE_PLOT_TO_FILE") and "SECTIONS_CP" in plotting and not cuts:
        continue
    pathlib.Path(lines[i + 1]).write_text({body})
"""


class _SectionsSolver(LocalExecutor):
    """Runs the stand-in above in place of the solver."""

    def __init__(self, stub: Path):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub = stub

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path)]


def _converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


def _body_and_wing_body(tmp_path):
    """A workspace with both geometries and the artifact, and a matrix of one row each."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    (workspace.inputs_dir / "pproc" / "p020.toml").write_text(WING_SECTIONS_PPROC, encoding="utf-8")
    geometries = workspace.inputs_dir / "geometries"
    for stem, names in INVENTORIES.items():
        (geometries / f"{stem}.fsm").write_bytes(b"a saved simulation")
        (geometries / f"{stem}.boundaries.toml").write_text(
            f"boundaries = {names!r}\n".replace("'", '"'), encoding="utf-8"
        )
    rows = []
    for pol, stem in (("5201", "body"), ("5202", "wingbody")):
        cells = {
            "POL": pol,
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Body",
            "DESCRIPTION": stem.upper(),
            "FLIGHT_CONDITION": "MACH:0.1, REmi:2.3, ALPHA:sweep, BETA:0.0",
            "SWEEP_VALUES": "-2.0,0.0",
            "GEOMETRY": f"{stem}.fsm",
            "REF": "r003",
            "SET": "s002",
            "PPROC": "p020",
            "SYMMETRY": "NONE",
            "FS_BUILD": "26.120",
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": "",
        }
        rows.append(" | ".join(cells.get(name, "-") for name in MATRIX_COLUMNS))
    matrix = tmp_path / "sections.fs"
    lines = [" | ".join(MATRIX_COLUMNS), "-" * 40, *rows]
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return workspace, matrix


def test_a_body_row_declares_and_exports_no_section_plot_its_wing_body_control_keeps_both(
    tmp_path,
):
    # P0331-SECTIONS-ABSENT-FAMILY (FR-51, amended 0.33.1): the artifact's one
    # distribution cuts the wing. Over the body alone the builder leaves it out,
    # and warns; the row then declares no {name}_plot_cp_sections.txt and its
    # script carries no SECTIONS_CP export, so the points are CONVERGED rather
    # than FAILED_INCOMPLETE_OUTPUT for a plot the solver cannot write. The
    # wing-body control declares the plot, exports it and collects it.
    workspace, matrix = _body_and_wing_body(tmp_path)
    resolved = resolve_matrix(
        matrix, workspace, name="sections", fs_version="26.120", recipes=RECIPES
    )
    declared = {case.sim_id: case.outputs for case in resolved.campaign.sims}
    assert "{name}_plot_cp_sections.txt" not in declared["5201"], declared["5201"]
    assert "{name}_plot_cp_sections.txt" in declared["5202"], declared["5202"]
    others = [name for name in declared["5202"] if name != "{name}_plot_cp_sections.txt"]
    assert declared["5201"] == others, (declared["5201"], others)

    verbs = sorted({kind[2] for kind in EXPORT_KINDS})
    stub = tmp_path / "sections_stub.py"
    stub.write_text(SECTIONS_STUB.format(verbs=verbs, body=STUB_BODY), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            run_matrix(
                matrix,
                workspace,
                name="sections",
                default_fs_version="26.120",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=_converged,
                executor=_SectionsSolver(stub),
            )
        except CampaignErrors:
            pass  # a failed point is recorded in the manifest, which is what is read
    said = [str(warning.message) for warning in caught]
    assert any("5201" in text and "left out" in text for text in said), said

    records = {record.sim_id: record for record in workspace.read_manifest()}
    for sim_id, cuts in (("5201", False), ("5202", True)):
        record = records[sim_id]
        statuses = [entry["status"] for entry in record.points_ran]
        assert statuses == [RunStatus.CONVERGED.value] * 2, (sim_id, statuses, record.error)
        script = (workspace.sim_dir(sim_id) / record.script_path).read_text(encoding="utf-8")
        assert ("NEW_SURFACE_SECTION_DISTRIBUTION" in script) is cuts, sim_id
        assert ("SECTIONS_CP" in script) is cuts, (sim_id, script.count("SECTIONS_CP"))
        collected = [name for entry in record.points_ran for name in entry["outputs"]]
        plots = [name for name in collected if name.endswith("_plot_cp_sections.txt")]
        assert len(plots) == (2 if cuts else 0), (sim_id, plots)


# --- row_outputs, one case per branch -------------------------------------------------

#: The declared name of the section Cp plot.
PLOT = "{name}_plot_cp_sections.txt"

#: A rotor whose one blade family is Blade1.
PROP = RotorBlock(alias="PROP", axis="Z", diameter_m=1.0, families_blades=["Blade1"])


def _artifact(families: str | list[str], frame: str = "MRP", **exports: bool) -> PprocSpec:
    """An artifact of one section distribution over ``families`` in ``frame``."""
    entry = {"families": families, "frame": frame, "planes": ["XZ"]}
    table: dict[str, object] = {"sections": {"distributions": [entry]}}
    if exports:
        table["exports"] = exports
    return PprocSpec.model_validate(table)


def _row(pproc: PprocSpec | None, inventory: tuple[str, ...] | None, rotor: bool = False):
    """A bound row over ``inventory`` citing ``pproc``, carrying PROP where asked."""
    return SimCase(
        sim_id="5301",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        pproc=pproc,
        inventory=inventory,
        rotors={"PROP": PROP} if rotor else {},
    )


#: id -> (row, run type, whether the plot is declared). Every case but the
#: first expects the artifact's own outputs with or without the plot.
ROW_OUTPUT_CASES = {
    "pproc-none-default-outputs": (_row(None, ("Wing",)), "unsteady_rotor", False),
    "inventory-none-keeps-plot": (_row(_artifact(["Wing"]), None), "steady", True),
    "artifact-declares-no-plot": (
        _row(_artifact(["Wing"], plot_sections_cp=False), ("Fuselage",)),
        "steady",
        False,
    ),
    "expanding-frame-rotor-carried-keeps": (
        _row(_artifact(["Blade1"], "LOCAL_AXIS"), ("Blade1", "Fuselage"), rotor=True),
        "steady",
        True,
    ),
    "expanding-frame-no-rotor-family-drops": (
        _row(_artifact(["Blade1"], "LOCAL_AXIS"), ("Fuselage",), rotor=True),
        "steady",
        False,
    ),
    "selector-refused-keeps-plot": (_row(_artifact("airframe"), ("Fuselage",)), "steady", True),
    "rotor-alias-honoured-keeps": (
        _row(_artifact(["PROP"]), ("Blade1", "Fuselage"), rotor=True),
        "steady",
        True,
    ),
    "common-frame-absent-family-drops": (_row(_artifact(["Wing"]), ("Fuselage",)), "steady", False),
    "common-frame-carried-family-keeps": (
        _row(_artifact(["Wing"]), ("Wing", "Fuselage")),
        "steady",
        True,
    ),
}


@pytest.mark.parametrize("label", list(ROW_OUTPUT_CASES))
def test_row_outputs_leaves_the_section_plot_out_only_where_no_section_is_cut(label):
    # P0331-SECTIONS-ABSENT-FAMILY (FR-51, amended 0.33.1): one case per branch
    # of row_outputs and _cuts_a_section. No artifact gives the defaults of the
    # run type; an unknown inventory, an expanding frame over a carried rotor
    # family, a selector the builder refuses, a rotor's name read as its alias
    # and a common-frame family the geometry carries all keep the plot; an
    # expanding frame with no rotor family and a common-frame family the
    # geometry lacks drop it; an artifact declaring no plot is returned as is.
    case, workflow, declared = ROW_OUTPUT_CASES[label]
    unsteady = workflow.startswith("unsteady")
    got = row_outputs(case, workflow)
    if case.pproc is None:
        assert got == default_outputs(unsteady), got
        return
    full = case.pproc.outputs(unsteady)
    expected = full if declared else [name for name in full if name != PLOT]
    assert got == expected, (label, got)
    assert (PLOT in got) is declared, (label, got)


# --- a record 0.33.0 wrote: what post, collect, rebuild and a re-run do with it --------
#
# docs/migrating-to-0.33.1.md and the change log's [0.33.1] Migration cite these
# two tests (FR-55 and FR-51). Each makes the record as 0.33.0 made it: the run
# goes through 0.33.0's rule for its cause, the stand-ins write a real loads
# table, and every record of runs.json is stamped package_version 0.33.0 as a
# 0.33.0 run stamps it. Measured: post writes the failed points' polar rows
# and warns of their status; collect sweeps only SUBMITTED records and leaves
# the record as it is; the rebuild refuses the simulation and writes nothing;
# re-running the point with 0.33.1 (run --force-rerun) records it CONVERGED.

#: The loads table the stand-ins write, so that the post has rows to tabulate.
LOADS_TABLE = FIXTURES / "loads_steady_26.120.txt"

#: The warning the post writes for a point recorded failed (post.log).
FAILED_STATUS_WARNING = "the recorded status is FAILED_INCOMPLETE_OUTPUT"


def _with_loads(stub: str, placeholder: str, read: str) -> str:
    """Return ``stub`` with ``placeholder`` replaced by ``read``, which reads the table."""
    assert stub.count(placeholder) == 1, placeholder
    return stub.replace(placeholder, read)


def _stamped_0330(workspace) -> None:
    """Stamp every record of runs.json with the package_version a 0.33.0 run writes."""
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and rows, rows
    for row in rows:
        row["package_version"] = "0.33.0"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _statuses(workspace) -> dict[str, list[str]]:
    return {
        record.sim_id: [entry["status"] for entry in record.points_ran]
        for record in workspace.read_manifest()
    }


def _old_record_through_the_commands(workspace, matrix: Path, sim: str, capsys) -> list[str]:
    """Run post, collect and rebuild over the old record; return the rebuild's refusals.

    Asserts what each command does: post writes one polar row per point, the
    failed ones included, and warns of their status; neither post nor collect
    changes a status; the rebuild refuses ``sim`` and writes nothing.
    """
    recorded = _statuses(workspace)
    failed = recorded[sim].count(RunStatus.FAILED_INCOMPLETE_OUTPUT.value)
    assert failed, recorded

    assert matrix_cli.main(["post", str(matrix), "--workspace", str(workspace.root)]) == 0
    post = workspace.root / "post" / matrix.stem
    (polar,) = sorted((post / "polars").glob(f"P{sim}-*_g01.csv"))
    with polar.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["POL"] == sim]
    assert len(rows) == len(recorded[sim]), (polar.name, len(rows), recorded[sim])
    warned = [
        line
        for line in (post / "post.log").read_text(encoding="utf-8").splitlines()
        if f"/sim_{sim}/" in line and FAILED_STATUS_WARNING in line
    ]
    assert len(warned) == failed, warned
    assert _statuses(workspace) == recorded, "post changed a recorded status"

    assert matrix_cli.main(["collect", "--workspace", str(workspace.root), "--no-post"]) == 0
    assert _statuses(workspace) == recorded, "collect changed a recorded status"

    capsys.readouterr()
    rebuild = ["rebuild", "--workspace", str(workspace.root), "--out", "rebuilt.json"]
    rebuild += ["--all-sims", "--matrix", str(matrix)]
    assert matrix_cli.main(rebuild) == 0
    said = capsys.readouterr().out.splitlines()
    assert any("0 record(s) rebuilt" in line for line in said), said
    refusals = [line for line in said if line.strip().startswith(f"sim_{sim}: NOT RECOVERABLE")]
    assert len(refusals) == 1, said
    assert matrix_cli.main([*rebuild, "--apply"]) == 2
    assert not (workspace.root / "rebuilt.json").exists()
    assert _statuses(workspace) == recorded, "the rebuild changed a recorded status"
    return refusals


def test_an_old_sweep_record_keeps_its_status_until_its_job_is_run_again(
    tmp_path, monkeypatch, capsys
):
    # FR-55 (amended 0.33.1), cause 1: point 2 of a steady job recorded
    # FAILED_INCOMPLETE_OUTPUT by 0.33.0, its cumulative log among its outputs.
    # 0.33.0's rule: no fallback to the one collected _log.txt.
    monkeypatch.setattr(
        "pyflightstream.run._wake_edge_verdict._LOG_SUFFIX", "\0 no fallback in 0.33.0"
    )
    stub = _with_loads(
        JOB_STUB,
        'write_text("LOADS", encoding="utf-8")',
        f"write_text(pathlib.Path({str(LOADS_TABLE)!r}).read_text(encoding='utf-8'))",
    )
    workspace, record = _steady_job_of_two_points(tmp_path, stub)
    monkeypatch.undo()
    statuses = [entry["status"] for entry in record.points_ran]
    assert statuses == [RunStatus.CONVERGED.value, RunStatus.FAILED_INCOMPLETE_OUTPUT.value]
    assert "no solver log was read" in (record.error or ""), record.error
    _stamped_0330(workspace)

    _old_record_through_the_commands(workspace, tmp_path / "job.fs", record.sim_id, capsys)

    again = _run_steady_job(tmp_path, workspace, force_rerun=[record.run_id])
    assert [entry["status"] for entry in again.points_ran] == [RunStatus.CONVERGED.value] * 2
    assert again.package_version != "0.33.0", again.package_version


def test_an_old_body_row_record_keeps_its_status_until_it_is_run_again(
    tmp_path, monkeypatch, capsys
):
    # FR-51 (amended 0.33.1), cause 2: every point of a body row recorded
    # FAILED_INCOMPLETE_OUTPUT by 0.33.0, its declared outputs listing the
    # section Cp plot the solver could not write. 0.33.0's rule: the row
    # declares the artifact's outputs whatever its geometry carries.
    monkeypatch.setattr(
        "pyflightstream.workspace.matrix.row_outputs",
        lambda case, workflow: case.pproc.outputs(unsteady=workflow.startswith("unsteady")),
    )
    workspace, matrix = _body_and_wing_body(tmp_path)
    verbs = sorted({kind[2] for kind in EXPORT_KINDS})
    body = (
        f"(pathlib.Path({str(LOADS_TABLE)!r}).read_text(encoding='utf-8') "
        f"if line.split(' ')[0] == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET' else {STUB_BODY})"
    )
    stub = tmp_path / "sections_stub.py"
    stub.write_text(SECTIONS_STUB.format(verbs=verbs, body=body), encoding="utf-8")

    def run(**again):
        try:
            run_matrix(
                matrix,
                workspace,
                name="sections",
                default_fs_version="26.120",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=_converged,
                executor=_SectionsSolver(stub),
                **again,
            )
        except CampaignErrors:
            pass  # a failed point is recorded in the manifest, which is what is read
        return {record.sim_id: record for record in workspace.read_manifest()}

    records = run()
    monkeypatch.undo()
    old = records["5201"]
    assert "_plot_cp_sections.txt" in (old.error or ""), old.error
    assert [entry["status"] for entry in old.points_ran] == [
        RunStatus.FAILED_INCOMPLETE_OUTPUT.value
    ] * 2, (old.points_ran, old.error)
    _stamped_0330(workspace)

    (refusal,) = _old_record_through_the_commands(workspace, matrix, "5201", capsys)
    assert "recorded by pyflightstream 0.33.0" in refusal, refusal
    assert "rebuilt only by the version that ran" in refusal, refusal

    again = run(force_rerun=[old.run_id])["5201"]
    assert [entry["status"] for entry in again.points_ran] == [RunStatus.CONVERGED.value] * 2
    assert not any(name.endswith("_plot_cp_sections.txt") for name in again.outputs), again
