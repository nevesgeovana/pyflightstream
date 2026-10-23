"""Regression coverage grouped by subject."""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import ProductExistsError, PyflightstreamWarning
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.results import (
    REDUCTION_CODES,
    REDUCTION_WINDOW_CODES,
    VersionMismatchWarning,
    VtkSurface,
    parse_force_distributions,
    parse_loads,
    parse_off_body_streamlines,
    parse_run_loads,
    parse_surface_sections,
    read_vtk_surface,
    sweep_table,
    to_csv,
    to_table,
    translate_surface_exports,
    write_table,
)
from pyflightstream.results import tables as tables_module
from pyflightstream.results.core import (
    IncompleteOutputError,
    MalformedOutputError,
    parse_count,
    parse_number,
)
from pyflightstream.results.native_surface import read_native_tecplot_surface
from pyflightstream.results.tables import AmbiguousLoadsError
from pyflightstream.workspace import CampaignWorkspace, PointName
from tests.tier1_offline.test_native_nodal_surface import _native as _results_surface___native
from tests.tier1_offline.test_tables import (
    build_sweep_workspace as _results_sweep__build_sweep_workspace,
)
from tests.tier1_offline.test_tables import collect_text as _results_tables__collect_text
from tests.tier1_offline.test_tables import make_record as _results_loads_support__make_record
from tests.tier1_offline.test_tables import make_record as _results_tables__make_record
from tests.tier1_offline.test_tables import read_fixture as _results_detection__read_fixture
from tests.tier1_offline.test_tables import read_fixture as _results_loads_support__read_fixture


class TestResultsCore:
    """P0400-RESULTS: the shared parsers of the results package (PFS-2095.048)."""

    @staticmethod
    @pytest.mark.parametrize("token", ["nan", "inf", "-Infinity", "NaN"])
    def test_p0400_results_parse_count_refuses_a_non_finite_value(token):
        """P0400-RESULTS (PFS-2095.048): a printed NaN or infinity is a malformed count, not a crash."""  # noqa: E501
        with pytest.raises(MalformedOutputError, match="Total iterations"):
            parse_count(token, label="Total iterations")

    @staticmethod
    @pytest.mark.parametrize("token", ["1_000", "1_0.5", "+2_5E-3"])
    def test_p0400_results_parse_number_refuses_a_digit_separator(token):
        """P0400-RESULTS (PFS-2095.048): Python's '1_000' is not a form the solver prints."""
        with pytest.raises(MalformedOutputError, match="not a solver-printed number"):
            parse_number(token)

    @staticmethod
    def test_p0400_results_parse_number_still_reads_the_solver_forms():
        """P0400-RESULTS (PFS-2095.048): control, the documented forms still parse."""
        assert parse_number(".000") == 0.0
        assert parse_number("4380000.") == 4380000.0
        assert parse_number("1.000E-05") == 1e-05
        assert parse_number("0.2964-322") == float("0.2964e-322")
        assert parse_count("312", label="Total iterations") == 312
        for token in ("nan", "inf", "-Infinity", "NaN"):
            with pytest.raises(MalformedOutputError, match="Total iterations"):
                parse_count(token, label="Total iterations")
        for token in ("1_000", "1_0.5", "+2_5E-3"):
            with pytest.raises(MalformedOutputError, match="not a solver-printed number"):
                parse_number(token)


def _results_loads_support___one_run(tmp_path, *outputs, **overrides):
    """A workspace of one steady run whose collected outputs are ``(datapoint, name, text)``."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    collected: list[str] = []
    for number, (datapoint, name, text) in enumerate(outputs):
        source = tmp_path / f"src{number}"
        source.mkdir()
        (source / name).write_text(text, encoding="utf-8")
        collected += workspace.collect_outputs(
            "9001", [source / name], datapoint=PointName(datapoint)
        )
    record = _results_loads_support__make_record(
        run_id="camp/sim_9001/AL+020",
        point_name="AL+020",
        sweep_name="AL+020",
        point={"alpha": 2.0},
        outputs=collected,
        **overrides,
    )
    workspace.append_record(record)
    return workspace, record


_RESULTS_LOADS_SUPPORT__STEADY = _results_loads_support__read_fixture("loads_steady_26.120.txt")


_RESULTS_LOADS_SUPPORT__TRUNCATED = _RESULTS_LOADS_SUPPORT__STEADY[
    : _RESULTS_LOADS_SUPPORT__STEADY.index("Force Units")
]


class TestResultsLoadsSupport:
    """Shared recorded loads and workspace builders for the results regressions."""


#: A two-triangle solver surface: the layout of the reader's own example.
_RESULTS_SURFACE__VTK = (
    "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
    "POINTS 4 float\n0 0 0\n1 0 0\n0 1 0\n1 1 0\nPOLYGONS 2 8\n3 0 1 2\n3 1 3 2\n"
    "CELL_DATA 2\nSCALARS Cp_reference FLOAT\nLOOKUP_TABLE default\n-0.5\n0.25\n"
)


#: One translation, placed in the reference frame itself.
_RESULTS_SURFACE__TRANSLATIONS = [
    {
        "vtk": "surface.vtk",
        "dat": "surface.dat",
        "frame": {"origin": [0, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    }
]


class TestResultsSurface:
    """P0400-RESULTS: the VTK surface reader and the surface translations of 0.40.0 (lane results)."""  # noqa: E501

    @staticmethod
    # --- PFS-2095.023: truncated or malformed VTK header lines raise catalogued errors ---
    @pytest.mark.parametrize(
        ("text", "error", "message"),
        [
            (
                _RESULTS_SURFACE__VTK.split("POINTS")[0] + "POINTS\n",
                IncompleteOutputError,
                "POINTS.*states no count.*truncated",
            ),
            (
                _RESULTS_SURFACE__VTK.split("POLYGONS")[0] + "POLYGONS 2\n",
                IncompleteOutputError,
                "POLYGONS.*states no count.*truncated",
            ),
            (
                _RESULTS_SURFACE__VTK.split("CELL_DATA")[0] + "CELL_DATA\n",
                IncompleteOutputError,
                "CELL_DATA.*states no count.*truncated",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("POINTS 4 float", "POINTS four float"),
                MalformedOutputError,
                "POINTS.*'four'.*whole count",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("POINTS 4 float", "POINTS -4 float"),
                MalformedOutputError,
                "POINTS.*negative count -4.*nonnegative",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("POLYGONS 2 8", "POLYGONS 2"),
                MalformedOutputError,
                "POLYGONS.*states no count",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("POLYGONS 2 8", "POLYGONS 2 8.5"),
                MalformedOutputError,
                "POLYGONS.*'8.5'.*whole count",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("CELL_DATA 2", "CELL_DATA two"),
                MalformedOutputError,
                "CELL_DATA.*'two'.*whole count",
            ),
            (
                _RESULTS_SURFACE__VTK.replace("Cp_reference FLOAT", "Cp_reference FLOAT one"),
                MalformedOutputError,
                "SCALARS.*Cp_reference.*'one'.*component count",
            ),
        ],
        ids=[
            "cut-after-POINTS",
            "cut-inside-POLYGONS",
            "cut-after-CELL_DATA",
            "mangled-POINTS",
            "negative-POINTS",
            "short-POLYGONS",
            "fractional-POLYGONS",
            "mangled-CELL_DATA",
            "mangled-SCALARS-components",
        ],
    )
    def test_p0400_results_a_cut_or_mangled_vtk_header_is_a_catalogued_refusal(
        tmp_path, text, error, message
    ):
        """P0400-RESULTS (PFS-2095.023): no bare IndexError or ValueError escapes the reader."""
        path = tmp_path / "surface.vtk"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(error, match=message):
            read_vtk_surface(path)

    @staticmethod
    def test_p0400_results_the_vtk_fixture_reads(tmp_path):
        """P0400-RESULTS (PFS-2095.023): control, the unmangled surface reads."""
        path = tmp_path / "surface.vtk"
        path.write_text(_RESULTS_SURFACE__VTK, encoding="utf-8")
        surface = read_vtk_surface(path)
        assert (surface.n_points, surface.n_cells) == (4, 2)

    @staticmethod
    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ("variables", "VARIABLES needs an equals sign.*quoted variable names"),
            ("location", "variable location.*invalid index.*whole index"),
            ("encoding", "Singularity_strength contains invalid values"),
            ("count", "NODES count cannot be read as a whole number"),
        ],
    )
    def test_p0400_results_malformed_native_headers_raise_catalogued_errors(
        tmp_path, change, message
    ):
        """P0400-RESULTS-SURFACE (PFS-2095.023): native text cannot raise a raw parser error."""
        path = _results_surface___native(tmp_path / "native.dat")
        content = path.read_bytes()
        if change == "variables":
            content = content.replace(b"VARIABLES=", b"VARIABLES ")
        elif change == "location":
            content = content.replace(b"FACES=4,", b"FACES=4, VARLOCATION=([-1]=CELLCENTERED),")
        elif change == "count":
            content = content.replace(b"NODES=4", b"NODES=" + b"9" * 4500)
        else:
            content = content.replace(b"30 10 40 20", b"30 10 40 " + bytes([255]))
        path.write_bytes(content)
        with pytest.raises(MalformedOutputError, match=message):
            read_native_tecplot_surface(path)


class TestResultsSweep:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    def test_p0400_results_one_unreadable_record_does_not_abort_the_sweep(tmp_path):
        """P0400-RESULTS (PFS-2095.025): a deleted output keeps its row, NaN, warned by run id."""
        workspace = _results_sweep__build_sweep_workspace(tmp_path)
        steady = next(r for r in workspace.read_manifest() if r.run_id == "camp/sim_9001/AL+020")
        (workspace.sim_dir(steady.sim_id) / steady.outputs[0]).unlink()
        with pytest.warns(
            PyflightstreamWarning, match="loads of run 'camp/sim_9001/AL\\+020' could"
        ):
            table = sweep_table(workspace, require_loads=False)
        assert table["run_id"].tolist() == [
            "camp/sim_9001/AL+020",
            "camp/sim_9001/AL+000",
            "camp/sim_9001/AL+040",
        ]
        assert math.isnan(table["CL"].iloc[0]) and not math.isnan(table["CL"].iloc[1])
        with pytest.raises(FileNotFoundError):
            sweep_table(workspace, require_loads=True)


_RESULTS_TABLES__FIXTURES = Path(__file__).parent / "fixtures"


def _results_tables___fixture(name: str) -> str:
    return (_RESULTS_TABLES__FIXTURES / name).read_text(encoding="utf-8")


def _results_tables___unsteady(text: str) -> str:
    """The same export printed by an unsteady run: only the mode line moves."""
    moved, count = re.subn(r"(Solver mode:\s+)Steady", r"\1Unsteady", text)
    assert count == 1, "the fixture must print exactly one steady solver mode"
    return moved


class TestResultsTables:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    def test_p0400_results_a_recorded_unsteady_loads_export_is_labelled_last_step(tmp_path):
        """P0400-RESULTS (PFS-2105.043, PFS-2105.046): the recorded unsteady export, read back."""
        pd = pytest.importorskip("pandas")
        # Actual RPT-133 arm B output, with its recorded coefficient values.
        report = parse_loads(_results_tables___fixture("rpt133/B_final.txt"))
        assert report.solver_mode.strip().lower() == "unsteady", (
            "the control: a recorded unsteady run"
        )
        back = pd.read_csv(to_csv(report, tmp_path / "loads.csv"))
        assert set(zip(back["reduction"], back["reduction_window"], strict=True)) == {
            ("last_step", "last_time_step")
        }

    @staticmethod
    def test_p0400_results_an_unsteady_sectional_export_is_labelled_last_step():
        """P0400-RESULTS (PFS-2105.043): the synthetic unsteady sectional loads of 26.125."""
        frame = to_table(
            parse_sectional_loads(_results_tables___fixture("s10_26125/sloads_26.125.txt"))
        )
        assert set(zip(frame["reduction"], frame["reduction_window"], strict=True)) == {
            ("last_step", "last_time_step")
        }

    @staticmethod
    @pytest.mark.parametrize(
        ("fixture", "parse"),
        [
            ("force_distributions_26.123.txt", parse_force_distributions),
            ("off_body_streamlines_26.123.txt", parse_off_body_streamlines),
            ("all_surface_sections_26.123.txt", parse_surface_sections),
        ],
    )
    def test_p0400_results_no_unsteady_solver_export_is_labelled_time_average(fixture, parse):
        """P0400-RESULTS (PFS-2105.043): force distribution, streamline and section exports."""
        steady = to_table(parse(_results_tables___fixture(fixture)))
        assert set(steady["reduction"]) == {"none"}, "the control: the steady export"
        frame = to_table(parse(_results_tables___unsteady(_results_tables___fixture(fixture))))
        assert set(zip(frame["reduction"], frame["reduction_window"], strict=True)) == {
            ("last_step", "last_time_step")
        }

    @staticmethod
    def test_p0400_results_the_last_step_tokens_are_appended_and_paired(tmp_path):
        """P0400-RESULTS (PFS-2105.043): appended codes, and each token refuses another partner."""
        pd = pytest.importorskip("pandas")
        assert REDUCTION_CODES["last_step"] == 3
        assert REDUCTION_WINDOW_CODES["last_time_step"] == 3
        for reduction, window in (("last_step", "not_printed"), ("time_average", "last_time_step")):
            frame = pd.DataFrame(
                {
                    "CL": [0.4],
                    "data_origin": ["raw"],
                    "reduction": [reduction],
                    "reduction_window": [window],
                }
            )
            with pytest.raises(MalformedOutputError, match="last_step with last_time_step"):
                write_table(frame, tmp_path / f"{reduction}.csv")

    @staticmethod
    def test_p0400_results_a_sweep_labels_its_recorded_unsteady_loads_last_step(tmp_path):
        """P0400-RESULTS-TABLES (PFS-2105.046): a sweep row is the native export's instant."""
        workspace = CampaignWorkspace(tmp_path / "camp")
        outputs = _results_tables__collect_text(
            workspace,
            "9001",
            tmp_path,
            "loads.txt",
            _results_tables___fixture("rpt133/B_final.txt"),
        )
        workspace.append_record(
            _results_tables__make_record(
                run_id="camp/sim_9001/AL+000",
                point_name="AL+000",
                point={"alpha": 0.0},
                fs_version_requested="26.124",
                outputs=outputs,
            )
        )
        table = sweep_table(workspace)
        row = table.loc[table["run_id"] == "camp/sim_9001/AL+000"].iloc[0]
        assert (row["reduction"], row["reduction_window"]) == ("last_step", "last_time_step")


def _results_topology___strip(cells: int) -> VtkSurface:
    """A strip of ``cells`` triangles over ``cells + 2`` nodes."""
    connectivity = np.array(
        [node for cell in range(cells) for node in (cell, cell + 1, cell + 2)], dtype=np.int64
    )
    return VtkSurface(
        points=np.zeros((cells + 2, 3)),
        offsets=np.arange(0, 3 * cells + 1, 3, dtype=np.int64),
        connectivity=connectivity,
    )


class TestResultsTopology:
    """Results regressions for 0.40.0."""

    @staticmethod
    def test_p0400_results_topology_differs_is_linear_in_the_polygons(monkeypatch):
        """P0400-RESULTS (PFS-2101.002): np.diff runs a fixed number of times, not once per polygon."""  # noqa: E501
        mine, theirs = _results_topology___strip(400), _results_topology___strip(400)
        theirs.connectivity[-1] = 0  # the last polygon joins another node
        calls = []
        original = np.diff

        def counted(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(np, "diff", counted)
        assert mine.topology_differs(theirs) == "polygon 400 joins other nodes"
        assert len(calls) <= 2, f"np.diff ran {len(calls)} times for 400 polygons"


class TestResultsAmbiguity:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    def test_p0400_results_loads_file_naming_two_outputs_is_ambiguous(tmp_path):
        """P0400-RESULTS (PFS-2105.045): two outputs share the base name; both are named."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
            ("AL+000", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
        )
        with pytest.raises(AmbiguousLoadsError) as caught:
            parse_run_loads(workspace, record, loads_file="loads.txt")
        for name in record.outputs:
            assert name in str(caught.value)

    @staticmethod
    def test_f_1444_the_recorded_path_selects_one_of_two_outputs_sharing_a_name(tmp_path):
        """F-1444: the diagnostic's selector can select; the base name alone cannot."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
            ("AL+000", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
        )
        for name in record.outputs:
            assert parse_run_loads(workspace, record, loads_file=name) is not None
        with pytest.raises(AmbiguousLoadsError, match="recorded path"):
            parse_run_loads(workspace, record, loads_file="loads.txt")

    @staticmethod
    def test_f_819_a_continued_run_is_not_answered_with_its_continuations_numbers(tmp_path):
        """F-819: the direct lookup agrees with sweep_table about a superseded run."""
        from pyflightstream.results.tables import LoadsNotFoundError

        workspace, record = _results_loads_support___one_run(
            tmp_path, ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY)
        )
        later = _results_loads_support__make_record(
            run_id="camp/sim_9001/AL+020#2",
            point_name="AL+020",
            sweep_name="AL+020",
            point={"alpha": 2.0},
            outputs=record.outputs,
            continues=record.run_id,
        )
        workspace.append_record(later)
        with pytest.raises(LoadsNotFoundError, match="continued by run"):
            parse_run_loads(workspace, record)
        assert parse_run_loads(workspace, later) is not None

    @staticmethod
    def test_f_1445_the_sweep_table_docstring_points_at_the_guarded_writer():
        """F-1445: the one write path is write_table, not DataFrame.to_csv."""
        assert "DataFrame.to_csv" not in (sweep_table.__doc__ or "")
        assert "write_table" in (sweep_table.__doc__ or "")


class TestResultsDetection:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    def test_p0400_results_a_truncated_loads_spreadsheet_is_refused_not_skipped(tmp_path):
        """P0400-RESULTS (PFS-2105.025, PFS-2081.24): the truncation is named, not 'no loads'."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__TRUNCATED),
            ("AL+020", "probes.txt", _results_detection__read_fixture("probe_points_26.120.txt")),
        )
        with pytest.raises(IncompleteOutputError):
            parse_run_loads(workspace, record)
        with pytest.warns(
            PyflightstreamWarning, match="loads of run 'camp/sim_9001/AL\\+020' could"
        ):
            table = sweep_table(workspace, require_loads=False)
        assert table["run_id"].tolist() == ["camp/sim_9001/AL+020"]
        assert "CL" not in table.columns, "no coefficient was read off the truncated file"

    @staticmethod
    def test_p0400_results_a_file_that_is_no_loads_spreadsheet_is_still_skipped(tmp_path):
        """P0400-RESULTS (PFS-2105.025): control, a probe export beside the loads is no refusal."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
            ("AL+020", "probes.txt", _results_detection__read_fixture("probe_points_26.120.txt")),
        )
        assert parse_run_loads(workspace, record).total["CL"] == pytest.approx(0.4308)

    @staticmethod
    def test_p0400_results_a_malformed_loads_spreadsheet_is_refused_not_skipped(tmp_path):
        """P0400-RESULTS-TABLES (PFS-2105.025): duplicated totals are loads errors."""
        lines = _RESULTS_LOADS_SUPPORT__STEADY.splitlines(keepends=True)
        total = next(line for line in lines if line.strip().startswith("Total,"))
        duplicated = _RESULTS_LOADS_SUPPORT__STEADY.replace(total, total + total)
        workspace, record = _results_loads_support___one_run(
            tmp_path, ("AL+020", "loads.txt", duplicated)
        )
        with pytest.raises(MalformedOutputError, match="Total"):
            parse_run_loads(workspace, record)

    @staticmethod
    def test_p0400_results_auto_detection_reads_only_the_loads_spreadsheet_whole(
        tmp_path, monkeypatch
    ):
        """P0400-RESULTS (PFS-2085.007): outputs that fail the head check are never read whole."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
            ("AL+020", "surface.vtk", "# vtk DataFile Version 3.0\n" + "0 0 0\n" * 5000),
            ("AL+020", "probes.txt", _results_detection__read_fixture("probe_points_26.120.txt")),
        )
        read: list[str] = []
        original = tables_module._read_output

        def recorded(sim_dir, name, record):
            read.append(Path(name).name)
            return original(sim_dir, name, record)

        monkeypatch.setattr(tables_module, "_read_output", recorded)
        parse_run_loads(workspace, record)
        assert read == ["loads.txt"]


class TestResultsReview:
    """Review regressions: read_vtk_surface and repeated translate_surface_exports calls."""

    @staticmethod
    @pytest.mark.parametrize("token", [str(2**63), str(-(2**63) - 1)])
    def test_p0400_results_polygon_integer_overflow_is_catalogued(tmp_path, token):
        """An out-of-range node integer must not escape translation's error catalogue."""
        source = tmp_path / "surface.vtk"
        source.write_text(
            _RESULTS_SURFACE__VTK.replace("3 0 1 2", f"3 0 1 {token}"), encoding="utf-8"
        )
        with pytest.raises(MalformedOutputError, match="POLYGONS"):
            read_vtk_surface(source)
        [record] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert record["written"] == []
        assert "POLYGONS" in record["problems"][0]

    @staticmethod
    @pytest.mark.parametrize("damage", ["truncated", "changed"])
    def test_p0400_results_matching_translation_header_does_not_prove_payload(tmp_path, damage):
        """Keep the genuine provenance header, then damage its translated data."""
        (tmp_path / "surface.vtk").write_text(_RESULTS_SURFACE__VTK, encoding="utf-8")
        [first] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert first["written"] == ["surface.dat"] and first["problems"] == []
        target = tmp_path / "surface.dat"
        lines = target.read_bytes().splitlines(keepends=True)
        zone = next(i for i, line in enumerate(lines) if line.startswith(b"ZONE"))
        if damage == "truncated":
            damaged = b"".join(lines[: zone + 1])
        else:
            lines[zone + 1] = b"999 " + lines[zone + 1]
            damaged = b"".join(lines)
        target.write_bytes(damaged)
        [again] = translate_surface_exports(tmp_path, [first])
        assert again["written"] == []
        assert "preserved" in again["problems"][0]
        assert target.read_bytes() == damaged


class TestResultsTranslation:
    """Results regressions for 0.40.0."""

    @staticmethod
    def test_p0400_results_a_stale_dat_with_no_native_source_is_preserved_not_written(tmp_path):
        """P0400-RESULTS (PFS-2105.024): the real translation, on a stale .dat beside a valid VTK."""  # noqa: E501
        (tmp_path / "surface.vtk").write_text(_RESULTS_SURFACE__VTK, encoding="utf-8")
        (tmp_path / "surface.dat").write_text("stale", encoding="utf-8")
        [record] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert record["written"] == []
        assert record["problems"] == [
            "surface.dat is preserved: source, frame or output provenance changed"
        ]
        assert (tmp_path / "surface.dat").read_text(encoding="utf-8") == "stale"

    @staticmethod
    def test_p0400_results_a_dat_this_translation_wrote_is_found_written(tmp_path):
        """P0400-RESULTS (PFS-2105.024): control, a second pass over its own output accepts it."""
        (tmp_path / "surface.vtk").write_text(_RESULTS_SURFACE__VTK, encoding="utf-8")
        [first] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert (first["written"], first["problems"]) == (["surface.dat"], [])
        [again] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert (again["written"], again["problems"]) == (["surface.dat"], [])
        (tmp_path / "surface.vtk").write_text(
            _RESULTS_SURFACE__VTK.replace("0.25", "0.75"), encoding="utf-8"
        )
        [changed] = translate_surface_exports(tmp_path, _RESULTS_SURFACE__TRANSLATIONS)
        assert changed["written"] == [] and "preserved" in changed["problems"][0]


class TestResultsVersion:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    @pytest.mark.parametrize("requested", ["unstated", "99.999", "26.12"])
    def test_p0400_results_an_unresolvable_requested_version_still_yields_the_loads(
        tmp_path, requested
    ):
        """P0400-RESULTS (PFS-2095.024): 'unstated' warns and keeps the coefficients."""
        workspace, record = _results_loads_support___one_run(
            tmp_path,
            ("AL+020", "loads.txt", _RESULTS_LOADS_SUPPORT__STEADY),
            fs_version_requested=requested,
        )
        with pytest.warns(VersionMismatchWarning, match="could not be resolved"):
            table = sweep_table(workspace)
        assert table["CL"].tolist() == [pytest.approx(0.4308)]
        with pytest.warns(VersionMismatchWarning, match="could not be resolved"):
            loads = parse_run_loads(workspace, record, loads_file="loads.txt")
        assert loads.fs_version_reported == "26.1"
        assert loads.total["CL"] == pytest.approx(0.4308)


class TestResultsWriters:
    """P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

    @staticmethod
    def test_p0400_results_to_csv_can_refuse_to_overwrite(tmp_path):
        """P0400-RESULTS (PFS-2096.030): to_csv offers the choice write_table offers."""
        report = parse_loads(_RESULTS_LOADS_SUPPORT__STEADY)
        target = to_csv(report, tmp_path / "loads.csv")
        before = target.read_bytes()
        with pytest.raises(ProductExistsError, match="already exists"):
            to_csv(report, target)
        with pytest.raises(ProductExistsError, match="already exists"):
            write_table(to_table(report), target)
        assert target.read_bytes() == before
        assert to_csv(report, target, overwrite=True) == target
        assert write_table(to_table(report), target, overwrite=True) == target


def _f7_0203_residual_page(header, rows):
    rule = "-" * 60
    body = "\n".join(f"{i}  {v}  {p}" for i, v, p in rows)
    return f"{header}\n\n{rule}\n\n{body}\n\n{rule}\n\n"


def test_f7_0203_an_indented_residual_header_still_opens_its_page():
    """F-809: a page whose Iteration header is indented is read, not lost."""
    from pyflightstream.results import parse_residual_history

    text = _f7_0203_residual_page(
        "Iteration  Res. Vel.  Res. Pres.", [(1, "+1.0E-3", "+1.0E-3"), (2, "+1.0E-4", "+1.0E-4")]
    ) + _f7_0203_residual_page(
        "   Iteration  Res. Vel.  Res. Pres.",
        [(3, "+1.0E-5", "+1.0E-5"), (4, "+1.0E-6", "+1.0E-6")],
    )
    assert [sample.iteration for sample in parse_residual_history(text)] == [1, 2, 3, 4]


_F7_0203_LOADS = (
    "Angle of attack (Deg)  2.000\n"
    "Side-slip angle (Deg)  .000\n"
    "Freestream velocity (m/s)  30.000\n"
    "Requested solver iterations  500\n"
    "Solver convergence limit  1.000E-05\n"
    "Force solver to run all iterations  F\n"
    "Solver mode:  Steady\n"
    "Current solver iteration number:  312\n"
    "Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz\n"
    "-----------------\n"
    "Wing,+0.01,+0.0,+0.43,+0.43,+0.009,+0.006,+0.0,-0.09,+0.0\n"
    "Total,+0.01,+0.0,+0.43,+0.43,+0.009,+0.006,+0.0,-0.09,+0.0\n"
    "-----------------\n"
    "Force Units: Coefficients\n"
    "Moment Units: Coefficients\n"
    "Software : Flightstream version 26.1, build #7012026\n"
)


def test_f7_0203_a_second_export_cut_before_its_footer_is_refused():
    """F-810: the second export's solution block shows it, footer or no footer."""
    from pyflightstream.results import parse_loads
    from pyflightstream.results.core import MalformedOutputError

    assert parse_loads(_F7_0203_LOADS).angle_of_attack_deg == 2.0
    truncated = _F7_0203_LOADS + _F7_0203_LOADS.split("Surface,")[0].replace("2.000", "3.000")
    with pytest.raises(MalformedOutputError, match="second export"):
        parse_loads(truncated)


def test_f7_0203_a_bare_numeric_table_is_not_an_unsteady_history():
    """F-812: the first row of a numeric table is not a header, so the table is refused."""
    from pyflightstream.results import parse_unsteady_plots
    from pyflightstream.results.core import AnchorNotFoundError

    with pytest.raises(AnchorNotFoundError, match="all numbers"):
        parse_unsteady_plots("1.0,2.0\n3.0,4.0\n5.0,6.0\n")
    assert (
        parse_unsteady_plots(
            "Time (sec), CL\n.000,1.0,\n.004,2.0,\n-----------\n"
            "Software : Flightstream version 26.1, build #7012026\n"
        ).steps
        == 2
    )


def test_f7_0203_a_second_table_after_the_closing_rule_is_refused():
    """F-813: rows after the rule that closes the table are not dropped silently."""
    from pyflightstream.results import parse_unsteady_plots
    from pyflightstream.results.core import MalformedOutputError

    first = "Time (sec), CL\n.000,1.0,\n.004,2.0,\n-----------\n"
    assert (
        parse_unsteady_plots(first + "Software : Flightstream version 26.1, build #7012026\n").steps
        == 2
    )
    with pytest.raises(MalformedOutputError, match="second table"):
        parse_unsteady_plots(first + "Time (sec), CL\n.008,3.0\n.012,4.0\n")


def _f7_0203_step(marker, rows=None):
    text = f"{marker}\n"
    if rows is not None:
        text += _f7_0203_residual_page("Iteration  Res. Vel.  Res. Pres.", rows)
    return text


_F7_0203_FROZEN = [(1, "+1.0E-3", "+1.0E-3"), (2, "+0.0E+0", "+0.0E+0")]


def test_f7_0203_the_freeze_detector_reads_the_marker_as_the_timing_does():
    """F-814: spaces inside the (k/N) marker do not hide a freeze."""
    from pyflightstream.results.log import frozen_time_steps

    for spelling in ("({k}/3)", "( {k} / 3 )"):
        text = "".join(
            _f7_0203_step(
                f"Solving unsteady time-step iteration {spelling.format(k=k)}", _F7_0203_FROZEN
            )
            for k in (1, 2, 3)
        )
        found = frozen_time_steps(text)
        assert found is not None and (found.first_step, found.count) == (1, 3)


def test_f7_0203_an_unreadable_interior_step_is_unjudged_not_healthy():
    """F-815: a middle marker with no page is reported, and breaks the streak."""
    from pyflightstream.results.core import IncompleteOutputError
    from pyflightstream.results.log import frozen_time_steps

    text = (
        _f7_0203_step("Solving unsteady time-step iteration (1/3)", _F7_0203_FROZEN)
        + _f7_0203_step("Solving unsteady time-step iteration (2/3)")
        + _f7_0203_step("Solving unsteady time-step iteration (3/3)", _F7_0203_FROZEN)
    )
    unjudged: list[int] = []
    assert frozen_time_steps(text, unjudged=unjudged) is None
    assert 2 in unjudged
    with pytest.raises(IncompleteOutputError, match="time step 2"):
        frozen_time_steps(text)


def test_f7_0203_a_malformed_residual_cell_is_not_a_healthy_step():
    """F-816: a cell that is neither a number nor an overflowed field is diagnosed."""
    from pyflightstream.results.core import MalformedOutputError
    from pyflightstream.results.log import frozen_time_steps

    bad = [(1, "+1.0E-3", "+1.0E-3"), (2, "abc", "+0.0E+0")]
    text = _f7_0203_step("Solving unsteady time-step iteration (1/2)", bad)
    unjudged: list[int] = []
    assert frozen_time_steps(text, unjudged=unjudged) is None
    assert unjudged == [1]
    with pytest.raises(MalformedOutputError, match="not numbers"):
        frozen_time_steps(text)
    overflow = [(1, "+1.0E-3", "+1.0E-3"), (2, "+1.0E-3", "*************")]
    assert (
        frozen_time_steps(_f7_0203_step("Solving unsteady time-step iteration (1/2)", overflow))
        is None
    )


_F7_0203_VTK = (
    "# vtk DataFile Version 3.0\nFlightStream vtk output\nASCII\nDATASET POLYDATA\n"
    "POINTS 3 float\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS 1 4\n3 0 1 2\n"
    "CELL_DATA 1\nSCALARS Cp_reference FLOAT\nLOOKUP_TABLE default\n-0.5\n"
)


@pytest.mark.parametrize(
    "damaged",
    [
        _F7_0203_VTK.replace("-0.5", "nan"),
        _F7_0203_VTK.replace("-0.5", "inf"),
        _F7_0203_VTK.replace("1 0 0\n0 1 0", "1e999 0 0\n0 1 0"),
    ],
    ids=["nan-scalar", "inf-scalar", "overflowing-point"],
)
def test_f7_0203_the_vtk_reader_refuses_values_that_are_not_finite(tmp_path, damaged):
    """F-250: NaN, infinity and overflowing values are refused in points and scalars."""
    from pyflightstream.results.core import MalformedOutputError
    from pyflightstream.results.surface import read_vtk_surface

    (tmp_path / "ok.vtk").write_text(_F7_0203_VTK, encoding="utf-8")
    assert read_vtk_surface(tmp_path / "ok.vtk").n_cells == 1
    (tmp_path / "bad.vtk").write_text(damaged, encoding="utf-8")
    with pytest.raises(MalformedOutputError, match="not finite"):
        read_vtk_surface(tmp_path / "bad.vtk")


def test_f7_0203_a_repeated_cell_data_section_is_refused(tmp_path):
    """F-818: a second CELL_DATA section does not replace the first one's scalars."""
    from pyflightstream.results.core import MalformedOutputError
    from pyflightstream.results.surface import read_vtk_surface

    repeated = _F7_0203_VTK + "CELL_DATA 1\nSCALARS Other FLOAT\nLOOKUP_TABLE default\n1.0\n"
    (tmp_path / "twice.vtk").write_text(repeated, encoding="utf-8")
    with pytest.raises(MalformedOutputError, match="more than one CELL_DATA"):
        read_vtk_surface(tmp_path / "twice.vtk")


_F7_0203_WAKE = (
    "# vtk DataFile Version 3.0\nwakes\nASCII\nDATASET POLYDATA\n"
    "POINTS 3 float\n0 0 0\n1 0 0\n2 0 0\nLINES 2 6\n2 0 1\n2 1 2\n"
    "CELL_DATA 2\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n0.5\n0.5\n"
)


def test_f7_0203_the_wake_reader_refuses_what_it_used_to_accept():
    """F-252 F-820 F-821: NaN strengths, a wrong component count and a repeated block."""
    from pyflightstream.results.core import MalformedOutputError
    from pyflightstream.results.wake import parse_wake_export

    assert len(parse_wake_export(_F7_0203_WAKE).lines) == 1
    with pytest.raises(MalformedOutputError, match="not finite"):
        parse_wake_export(_F7_0203_WAKE.replace("0.5\n0.5\n", "nan\n0.5\n"))
    with pytest.raises(MalformedOutputError, match="components"):
        parse_wake_export(_F7_0203_WAKE.replace("float 1", "float 3"))
    with pytest.raises(MalformedOutputError, match="second LINES"):
        parse_wake_export(_F7_0203_WAKE.replace("CELL_DATA", "LINES 2 6\n2 0 1\n2 1 2\nCELL_DATA"))


def test_f7_0203_single_segment_wake_lines_of_different_values_are_not_fused():
    """F-253: coordinate stitching joins nodes only between segments of one value."""
    from pyflightstream.results.wake import parse_wake_export

    text = (
        "# vtk DataFile Version 3.0\nwakes\nASCII\nDATASET POLYDATA\n"
        "POINTS 4 float\n0 0 0\n1 0 0\n1 0 0\n2 0 0\nLINES 2 6\n2 0 1\n2 2 3\n"
        "CELL_DATA 2\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n0.5\n-0.5\n"
    )
    wake = parse_wake_export(text)
    assert len(wake.lines) == 2
    assert sorted(wake.values.tolist()) == [-0.5, 0.5]
