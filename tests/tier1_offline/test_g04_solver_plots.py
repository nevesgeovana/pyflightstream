"""Tier 1: a steady point saves the solver's own plots (0.27.0, G04).

The decision, held by a test on each of its links:

* a steady row saves the residual and the load histories by default, and the
  section Cp when its pproc declares sections; each is an ``[exports]`` kind
  that can be switched off;
* the script saves each plot after the exports and before the log, choosing
  the plot and then naming the file on the line after the save, which is where
  and how RPT-067 ran them on 26.124;
* an unsteady row saves none, and a pproc stating one true on such a row is
  refused, because an unsteady point already exports its histories through
  ``UNSTEADY_SOLVER_EXPORT_PLOTS``;
* the files are collected and hashed as products of the point and are never
  read as a loads table or as the solver log (a plot is a display of the solve,
  never a coefficient source);
* the database records both commands verified on 26.124, from the
  compat-format transcription of RPT-067's run.

The three fixtures ``plot_*_26.124.txt`` are REDUCTIONS of the files RPT-067's
run wrote on 26.124: the header, the column line, the first three rows and the
units footer, with the simulation file name made generic. Every other byte is
the solver's.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import PprocSpec, classify_outputs, default_outputs
from pyflightstream.cases.workflows import (
    WORKFLOWS,
    WorkflowConventions,
    action_export_lines,
    build_script,
    build_steady_sweep,
    workflow_registry,
)
from pyflightstream.commands import CommandRegistry, Phase, Status
from pyflightstream.results import parse_loads
from pyflightstream.run import LoadsAssessor, _reads_as_residual_history
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)
from tests.tier1_offline.test_saved_simulation import CELLS, as_a_matrix_row
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

FIXTURES = Path(__file__).resolve().parent / "fixtures"
#: The three plots, their SET_PLOT_TYPE token and their suffix, written here
#: rather than imported, so the test states the contract the code must meet.
PLOTS = {
    "plot_residuals": ("RESIDUALS", "_plot_residuals.txt"),
    "plot_loads": ("LOADS", "_plot_loads.txt"),
    "plot_sections_cp": ("SECTIONS_CP", "_plot_cp_sections.txt"),
}
STEADY_BUILDS = [build for name, build in CELLS if name == "steady"]
SECTIONS = {"distributions": [{"families": "all", "planes": ["XZ"]}]}


def _saves(lines: list[str], stem: str, *kinds: str) -> list[str]:
    """The lines a script writes to save ``kinds``, in that order."""
    block: list[str] = []
    for kind in kinds:
        token, suffix = PLOTS[kind]
        block += [f"SET_PLOT_TYPE {token}", "SAVE_PLOT_TO_FILE", f"{stem}{suffix}", ""]
    return block


def _between(lines: list[str], first: str, last: str) -> list[str]:
    """The lines after the block ``first`` opens and before ``last``."""
    start = lines.index(first)
    # the export's name and the blank line closing its block
    return lines[start + 3 : lines.index(last)]


# --------------------------------------------------------------- the default --


def test_g04_a_steady_row_declares_its_residual_and_load_plots_by_default():
    """Two plots always on a steady row, the third only where sections exist."""
    plain = PprocSpec().outputs(unsteady=False)
    assert "{name}_plot_residuals.txt" in plain, plain
    assert "{name}_plot_loads.txt" in plain, plain
    assert "{name}_plot_cp_sections.txt" not in plain, plain
    with_sections = PprocSpec.model_validate({"sections": SECTIONS}).outputs(unsteady=False)
    assert "{name}_plot_cp_sections.txt" in with_sections, with_sections


def test_g04_each_plot_can_be_turned_off_in_exports():
    """``[exports] <kind> = false`` drops that plot and keeps the others."""
    for kind, (_, suffix) in PLOTS.items():
        spec = PprocSpec.model_validate({"sections": SECTIONS, "exports": {kind: False}})
        outputs = spec.outputs(unsteady=False)
        assert f"{{name}}{suffix}" not in outputs, (kind, outputs)
        others = [other for other in PLOTS if other != kind]
        for other in others:
            assert f"{{name}}{PLOTS[other][1]}" in outputs, (kind, other, outputs)


def test_g04_the_sections_plot_stated_true_without_sections_is_refused():
    """An explicit true the pproc cannot honour is refused, naming [sections]."""
    with pytest.raises(ValueError, match=r"plot_sections_cp.*\[\[sections\.distributions\]\]"):
        PprocSpec.model_validate({"exports": {"plot_sections_cp": True}})
    # The control: with sections it is accepted, and the default already says true.
    PprocSpec.model_validate({"sections": SECTIONS, "exports": {"plot_sections_cp": True}})


# ---------------------------------------------------------------- the script --


@pytest.mark.parametrize("build", STEADY_BUILDS)
def test_g04_the_script_saves_each_plot_after_the_exports_with_its_path_on_the_next_line(build):
    """After the probe export, before the log: T13's position and grammar (RPT-067)."""
    stem = "P7002-M100AL+000"
    case = as_a_matrix_row(steady_case(), "steady", stem)
    script = Script(build)
    build_script(case, script)
    lines = script.render().splitlines()
    assert _between(lines, "EXPORT_PROBE_POINTS", "EXPORT_LOG") == _saves(
        lines, stem, "plot_residuals", "plot_loads"
    ), f"on {build} the plots are not saved between the probe export and the log"


def test_g04_the_sections_plot_follows_the_other_two_after_the_section_update():
    """With sections declared, the SECTIONS_CP save comes third, after the update."""
    stem = "P7002-M100AL+000"
    outputs = PprocSpec.model_validate({"sections": SECTIONS}).outputs(unsteady=False)
    case = steady_case().model_copy(
        update={"outputs": [name.replace("{name}", stem) for name in outputs]}
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    assert _between(lines, "EXPORT_PROBE_POINTS", "EXPORT_LOG") == _saves(
        lines, stem, "plot_residuals", "plot_loads", "plot_sections_cp"
    )
    assert lines.index("UPDATE_ALL_SURFACE_SECTIONS") < lines.index("SET_PLOT_TYPE SECTIONS_CP")


def test_g04_each_point_of_a_steady_sweep_saves_its_own_plots():
    """A warm sweep is one script; every point saves its plots under its own name."""
    stems = [f"P7002-M100AL+{10 * angle:03d}" for angle in (0, 2, 4)]
    cases = [
        as_a_matrix_row(steady_case(), "steady", stem).model_copy(
            update={"point": {"alpha": float(angle)}}
        )
        for stem, angle in zip(stems, (0, 2, 4), strict=True)
    ]
    script = Script("26.124")
    build_steady_sweep(cases, script)
    lines = script.render().splitlines()
    saved = [lines[index + 1] for index, line in enumerate(lines) if line == "SAVE_PLOT_TO_FILE"]
    assert saved == [
        f"{stem}{PLOTS[kind][1]}" for stem in stems for kind in ("plot_residuals", "plot_loads")
    ], saved


def test_g04_classify_outputs_gives_every_plot_its_own_kind_in_any_order():
    """No plot name is ever claimed as the loads table, whatever order it is listed in."""
    names = ["P.txt", "P_plot_residuals.txt", "P_plot_loads.txt", "P_plot_cp_sections.txt"]
    names += ["P_cp.txt", "P_log.txt"]
    for order in itertools.permutations(names):
        claimed = classify_outputs(list(order))
        assert claimed.get("loads") == "P.txt", (order, claimed)
        assert claimed.get("sections") == "P_cp.txt", (order, claimed)
        for kind, (_, suffix) in PLOTS.items():
            assert claimed.get(kind) == f"P{suffix}", (order, claimed)


def test_g04_no_export_suffix_ends_with_another_but_a_bare_extension():
    """A suffix ending in another kind's suffix is claimed by the longer one only by luck.

    ``_plot_sections_cp.txt`` would end with the sections kind's ``_cp.txt`` and
    ``_residual_plots.txt`` with the unsteady plots kind's ``_plots.txt``; a bare
    extension (the loads table's ``.txt``) is the one overlap the longest-first
    rule is built for.
    """
    from pyflightstream import cases

    bare = {".txt", ".dat", ".vtk", ".csv", ".fsm"}
    suffixes = [suffix for _, suffix, _, _ in cases.EXPORT_KINDS]
    clashes = [
        (longer, shorter)
        for longer in suffixes
        for shorter in suffixes
        if longer != shorter and longer.endswith(shorter) and shorter not in bare
    ]
    assert not clashes, clashes
    assert len(suffixes) >= 13, f"the walk saw {len(suffixes)} suffixes; it read the wrong table"


# -------------------------------------------------------------- the unsteady --


def test_g04_an_unsteady_row_saves_no_solver_plot():
    """Not declared, not rendered, and never in a per-step or rescue action."""
    for outputs in (default_outputs(True), PprocSpec().outputs(unsteady=True)):
        assert not [name for name in outputs if "_plot_" in name], outputs
    stem = "P7003-M100AL+000"
    declared = [
        name.replace("{name}", stem)
        for name in PprocSpec.model_validate({"sections": SECTIONS}).outputs(unsteady=False)
    ]
    for make in (unsteady_case, rotor_case):
        case = make().model_copy(update={"outputs": declared})
        script = Script("26.124")
        build_script(case, script)
        assert "SET_PLOT_TYPE" not in script.render(), make.__name__
        for whole_run in (False, True):
            lines = action_export_lines(
                WorkflowConventions(), case, whole_run=whole_run, version="26.124"
            )
            assert not [line for line in lines if "PLOT_TYPE" in line or "_plot_" in line], (
                make.__name__,
                whole_run,
                lines,
            )


def test_g04_a_plot_stated_true_on_an_unsteady_row_is_refused():
    """An explicit true a march cannot honour is refused at plan, naming why."""
    from pyflightstream.cases import CampaignConfigError

    pproc = PprocSpec.model_validate({"exports": {"plot_residuals": True}})
    case = unsteady_case().model_copy(
        update={"pproc": pproc, "outputs": ["P.txt", "P.fsm", "P_log.txt"]}
    )
    with pytest.raises(CampaignConfigError) as raised:
        build_script(case, Script("26.124"))
    text = str(raised.value)
    assert "plot_residuals" in text and "'unsteady'" in text and "RPT-067" in text, text


# ----------------------------------------------------------------- the files --


def test_g04_a_plot_file_is_neither_a_loads_table_nor_a_solver_log(tmp_path):
    """The assessor finds the loads table and the log by content; a plot is neither."""
    plots = [FIXTURES / f"plot_{kind}_26.124.txt" for kind in ("residuals", "loads", "sections_cp")]
    for path in plots:
        text = path.read_text(encoding="utf-8")
        assert "FlightStream plot" in text, path.name
        with pytest.raises(ValueError):
            parse_loads(text)
        assert not _reads_as_residual_history(path), path.name
    # The judgment of a point folder with and without them is the same.
    verdicts = []
    for with_plots in (False, True):
        sim = tmp_path / f"with_{with_plots}"
        folder = sim / "outputs"
        folder.mkdir(parents=True)
        (folder / "P.txt").write_bytes((FIXTURES / "loads_steady_26.120.txt").read_bytes())
        (folder / "P_log.txt").write_bytes((FIXTURES / "log_residuals_26.120.txt").read_bytes())
        if with_plots:
            for path in plots:
                (folder / f"P_{path.stem.rsplit('_', 1)[0]}.txt").write_bytes(path.read_bytes())
        verdicts.append(LoadsAssessor()(None, None, sim))
    without, with_them = verdicts
    assert with_them.status is without.status, (without, with_them)
    assert with_them.log_file_used == without.log_file_used == "P_log.txt", with_them


def test_g04_the_plot_files_are_collected_and_hashed(tmp_path):
    """Each point's two plots land in its folder and the record hashes them."""
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="-2.0,0.0"
    )
    records = run_matrix(
        matrix,
        workspace,
        name="plots",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert records, "the row ran no point"
    saved = []
    for record in records:
        assert record.status is RunStatus.CONVERGED, record.error
        for name in record.outputs:
            if "_plot_" not in str(name):
                continue
            assert re.fullmatch(
                r"datapoints/DP-(?P<tag>[^/]+)/P3207-(?P=tag)_plot_(residuals|loads)\.txt", name
            ), name
            on_disk = workspace.sim_dir("3207") / name
            assert record.outputs_sha256[name] == file_sha256(on_disk), name
            saved.append(name)
    assert len(saved) == 2 * 2, f"2 plot files per point expected and the records name {saved}"


# ------------------------------------------------------------- the database --


def test_g04_the_plot_commands_are_verified_on_26124_by_the_t13_transcription():
    """Promoted by pyfs-qa apply-compat from the transcription, never by hand."""
    registry = CommandRegistry.load()
    for name in ("SET_PLOT_TYPE", "SAVE_PLOT_TO_FILE"):
        entry = registry.commands[name]
        row = entry.versions["26.124"]
        assert row.status is Status.VERIFIED, (name, row.status)
        assert row.report == "reports/compat/CMP-26124_2026-09-24_plots.yaml", row.report
        assert entry.phase is Phase.EXPORT, (name, entry.phase)
    (file_arg,) = registry.commands["SAVE_PLOT_TO_FILE"].args
    assert file_arg.own_line, "the path goes on the line after the save (RPT-067)"
    steady = WORKFLOWS["steady"].commands
    assert steady.index("SAVE_PLOT_TO_FILE") < steady.index("EXPORT_LOG"), steady
