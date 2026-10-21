"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import inspect
import json
import math
import warnings
from pathlib import Path
from typing import NoReturn, get_type_hints

import pytest
from pydantic import ValidationError

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import (
    CampaignConfigError,
    RotorBlock,
    SimCase,
    SolverSettings,
    SweepAxis,
    acoustics,
    pproc,
)
from pyflightstream.cases import PprocSpec as _CasesReviewPprocSpec
from pyflightstream.cases._ccs import CcsControlSurface, ccs_component_names
from pyflightstream.cases._setup_link import family_indices
from pyflightstream.cases.acoustics import read_observers_file
from pyflightstream.cases.corrections import CalibrationRow, calibration_text, parse_calibration
from pyflightstream.cases.matrix import (
    MATRIX_COLUMNS,
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)
from pyflightstream.cases.naming import name_field
from pyflightstream.cases.pproc import (
    PhaseLockedSpec,
    ProbeCircle,
    ProbeLine,
    ProbeRectangle,
    ProbesSpec,
    SurfaceProbeSpec,
    classify_outputs,
)
from pyflightstream.cases.pproc import PprocSpec as _CasesPprocPprocSpec
from pyflightstream.cases.selection import (
    alias_members_missing,
    resolve_alias,
    select_families,
    select_group_members,
    warn_a_selector_that_guesses,
)
from pyflightstream.cases.windows import averaging_steps, phase_locked_entry, replan, stated_key
from pyflightstream.cases.workflows import build_script, reduction_windows
from pyflightstream.post.products import write_campaign_products
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import resolve_pproc
from tests.tier1_offline.test_goal028_window_resolver import _matrix as _cases_review__window_matrix
from tests.tier1_offline.test_post_products import (
    _unsteady_workspace as _cases_review___unsteady_workspace,
)
from tests.tier1_offline.test_workflows import _case_for as _cases_review___case_for
from tests.tier1_offline.test_workflows import _wb_geometry as _cases_pproc___wb_geometry
from tests.tier1_offline.test_workflows import _wb_geometry as _cases_review___wb_geometry
from tests.tier1_offline.test_workflows import _with_pproc as _cases_pproc___with_pproc
from tests.tier1_offline.test_workflows import _with_pproc as _cases_review___with_pproc
from tests.tier1_offline.test_workflows import rotor_case as _cases_review__rotor_case
from tests.tier1_offline.test_workflows import steady_case as _cases_pproc__steady_case


class TestCasesAcoustics:
    """Tier 1: a byte order mark opens an observer file or a CCS file without changing it (0.40.0)."""  # noqa: E501

    @staticmethod
    def test_p0400_observer_file_with_a_byte_order_mark_is_read(tmp_path):
        """P0400-BOM (PFS-2095.039): Excel's CSV UTF-8 still opens with a count of observers."""
        path = tmp_path / "observers.csv"
        path.write_bytes(b"\xef\xbb\xbf2\r\n0.0,0.0,1.0\r\n1.0,0.0,0.0\r\n")
        assert read_observers_file(path) == ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))

    @staticmethod
    def test_p0400_ccs_component_count_reads_past_a_byte_order_mark():
        """P0400-BOM (PFS-2095.039): the first Component line counts, BOM or not."""
        text = "\ufeffComponent;WING\nsection data\nComponent;TAIL\n"
        assert ccs_component_names(text) == ("WING", "TAIL")


class TestCasesCcs:
    """Tier 1: the CCS control-surface range refusal names the form the plan accepts (0.40.0)."""

    @staticmethod
    def test_p0400_ccs_parametric_range_refusal_names_span_fractions():
        """P0400-CCS-REMEDY (PFS-2100.008): never steer to space = "REAL", which the plan refuses."""  # noqa: E501
        with pytest.raises(ValidationError) as caught:
            CcsControlSurface(
                name="AIL",
                v0=2.0,
                v1=3.6,
                u0=0.25,
                u1=0.25,
                hinge_height=0.5,
                angle_deg=20.0,
                slot_gap_pct=1.0,
            )
        text = str(caught.value)
        assert "fractions of the span between 0 and 1" in text
        assert 'write space = "REAL"' not in text
        assert CcsControlSurface.__doc__ is not None and "refused" in CcsControlSurface.__doc__


def _cases_corrections___phase_at(phases, j):
    rows = [
        CalibrationRow("THRUST", 0.5, 0.0, 0.0, 0.0, 1.0, 1.0, phases[0]),
        CalibrationRow("THRUST", 0.7, 0.0, 0.0, 0.0, 1.0, 1.0, phases[1]),
    ]
    return parse_calibration(calibration_text("table", rows)).lookup("THRUST", {"J": j})


class TestCasesCorrections:
    """Tier 1: the calibration interpolates its phase as an angle and writes valid TOML (0.40.0)."""

    @staticmethod
    def test_p0400_phase_straddling_the_wrap_interpolates_through_zero():
        """P0400-PHASE-WRAP (PFS-2081.18): 350 and 10 degrees meet at 0, not at 180."""
        phase = _cases_corrections___phase_at((350.0, 10.0), 0.6).coefficients[3]
        assert math.isclose(math.cos(math.radians(phase)), 1.0, abs_tol=1e-9), phase
        quarter = _cases_corrections___phase_at((350.0, 10.0), 0.55).coefficients[3]
        assert math.isclose(quarter % 360.0, 355.0, abs_tol=1e-9), quarter

    @staticmethod
    def test_p0400_phase_within_half_a_turn_interpolates_as_plain_numbers():
        """P0400-PHASE-WRAP (PFS-2081.18): a cell with no wrap gives exactly what it gave before."""
        assert (
            _cases_corrections___phase_at((10.0, 30.0), 0.6).coefficients[3]
            == 0.5 * 10.0 + 0.5 * 30.0
        )
        assert _cases_corrections___phase_at((-10.0, 10.0), 0.6).coefficients[3] == 0.0

    @staticmethod
    def test_p0400_calibration_text_escapes_control_characters():
        """P0400-CALIBRATION-TOML (PFS-2095.040): a newline or tab in free text reads back unchanged."""  # noqa: E501
        row = CalibrationRow("THRUST", 0.6, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0)
        text = calibration_text(
            "sector_offset", [row], source_run_id="run\t1", description='line1\nline2 "q" \\ \x01'
        )
        read = parse_calibration(text)
        assert read.description == 'line1\nline2 "q" \\ \x01'
        assert read.source_run_id == "run\t1"


_CASES_LOAD_CAMPAIGN__CAMPAIGN_TOML = """
[campaign]
name = "wing_steady_sweep"
fs_version = "26.120"
fs_exe = 'C:/FlightStream/FlightStream.exe'

[[sim]]
sim_id = "9001"
aircraft = "TestWing"
description = "steady polar"
reynolds = 4.38e6
mach = 0.1441
sweep = {type = "alpha", values = [0.0, 2.0]}
recipe = "recipes.steady_polar:build"
outputs = ["loads_{point}.txt"]
"""


#: The header of v0.15.0 to v0.16.0, as those releases wrote it.
_CASES_MATRIX__LAYOUT_0_15_0 = (
    "POL | AIRCRAFT | DESCRIPTION | FLIGHT_CONDITION | SWEEP_VALUES | REF | SET | PPROC "
    "| FS_BUILD | HIDDEN | RUN | WORKFLOW | VAR_NAMES_VALUES"
)


_CASES_MATRIX__CAMPAIGN = {
    "name": "polar",
    "fs_version": "26.124",
    "fs_exe": "FlightStream.exe",
    "recipes": {},
}


def _cases_matrix___matrix(tmp_path, **cells):
    """Write a one-row matrix at the current layout, overriding the named cells."""
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        AIRCRAFT="Wing",
        DESCRIPTION="POLAR",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.0,2.0",
        FS_BUILD="MANUAL",
        WORKFLOW="unsteady",
        VAR_NAMES_VALUES="",
    )
    row.update(cells)
    path = tmp_path / "matrix.fs"
    path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
    return path


class TestCasesMatrix:
    """Tier 1: the run-matrix reader and converter refuse by name and convert losslessly (0.40.0)."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        ("column", "value"), [("RUN", "NA"), ("RUN", "1.0"), ("HIDDEN", "yes")]
    )
    def test_p0400_run_and_hidden_cells_are_refused_naming_row_and_pol(tmp_path, column, value):
        """P0400-RUN-HIDDEN (PFS-2095.003): a RUN or HIDDEN value outside its form names row and POL."""  # noqa: E501
        with pytest.raises(MatrixError) as caught:
            read_matrix(_cases_matrix___matrix(tmp_path, **{column: value}), active_only=False)
        text = str(caught.value)
        assert (
            "data row 1" in text and "POL 9001" in text and column in text and repr(value) in text
        )

    @staticmethod
    def test_p0400_layout_0_15_0_is_recognised_naming_its_converter(tmp_path):
        """P0400-LAYOUT-0150 (PFS-2095.037): the 13-column layout is not told to restore a backup."""  # noqa: E501
        path = tmp_path / "m016.fs"
        path.write_text(_CASES_MATRIX__LAYOUT_0_15_0 + "\n", encoding="utf-8")
        with pytest.raises(MatrixError) as caught:
            read_matrix(path)
        text = str(caught.value)
        assert "predates 0.38.0" in text and "pyfs-workspace migrate" in text
        assert "WORKFLOW" in text and "PPROC" in text
        assert "restore the original" not in text

    @staticmethod
    @pytest.mark.parametrize("token", ["abc", "inf", "nan"])
    def test_p0400_sweep_value_that_is_not_a_finite_number_names_the_pol(tmp_path, token):
        """P0400-SWEEP-TOKEN (PFS-2095.002): a SWEEP_VALUES token is refused as a matrix error."""
        with pytest.raises(MatrixError) as caught:
            read_matrix(_cases_matrix___matrix(tmp_path, SWEEP_VALUES=f"0.0,{token}"))
        text = str(caught.value)
        assert "POL 9001" in text and "SWEEP_VALUES" in text and repr(token) in text
        assert "comma-separated numbers" in text

    @staticmethod
    def test_p0400_no_active_row_and_no_default_build_is_a_matrix_error(tmp_path):
        """P0400-NO-ACTIVE-ROW (PFS-2095.004): no StopIteration when every row is switched off."""
        path = _cases_matrix___matrix(tmp_path, RUN="0")
        with pytest.raises(MatrixError, match=r"no active row.*--fs-version"):
            to_campaign(path, **{**_CASES_MATRIX__CAMPAIGN, "fs_version": ""})

    @staticmethod
    def test_p0400_matrix_keeps_every_in_memory_record_list(tmp_path):
        """P0400-CONVERT-LOSSLESS: matrix rows preserve the in-memory record lists."""
        path = _cases_matrix___matrix(
            tmp_path,
            VAR_NAMES_VALUES=(
                "MOTIONS: {MOVING_BOUNDARIES: S / RPM_SIGN: 1 / ROTOR_AXIS: X}"
                " / ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S}"
                " / TRANSLATE: {DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: S}"
                " / RAW: {COMMAND: PRINT hello / BEFORE: init}"
            ),
        )
        case = to_campaign(path, **_CASES_MATRIX__CAMPAIGN).sims[0]
        assert case.motions and case.rotations and case.translations and case.raw_commands


_CASES_MATRIX_UPGRADE__FIXTURES = Path(__file__).parent / "fixtures"


class TestCasesMatrixUpgrade:
    """Tier 1: the matrix upgrade edits only what its stage names and counts data rows (0.40.0)."""

    pass

    pass

    pass


class TestCasesNaming:
    """Tier 1: point names keep the historical binary half-even rounding (0.40.0)."""

    @staticmethod
    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("ALPHA", 0.15, "AL+002"),
            ("ALPHA", 0.25, "AL+002"),
            ("ALPHA", 0.35, "AL+004"),
            ("ALPHA", -0.25, "AL-002"),
            ("ADVANCE_RATIO", 0.115, "J+012"),
            ("ADVANCE_RATIO", 0.125, "J+012"),
        ],
    )
    def test_p0400_name_field_keeps_historical_rounding(key, value, expected):
        """P0400-NAME-ROUNDING (PFS-2081.48): historical point names do not change."""
        assert name_field(key, value) == expected

    @staticmethod
    def test_p0400_sweep_values_with_distinct_historical_names_are_not_refused(tmp_path):
        """P0400-NAME-ROUNDING (PFS-2081.48): distinct historical names remain accepted."""
        row = dict.fromkeys(MATRIX_COLUMNS, "NA")
        row.update(
            POL="9001",
            HIDDEN="0",
            RUN="1",
            FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
            SWEEP_VALUES="0.0,0.1,0.2,0.3",
            FS_BUILD="MANUAL",
            WORKFLOW="unsteady",
            VAR_NAMES_VALUES="",
        )
        path = tmp_path / "matrix.fs"
        path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
        (read,) = read_matrix(path)
        assert read.sweep.values == [0.0, 0.1, 0.2, 0.3]

    @staticmethod
    def test_p0400_bgtests2_distinct_sweep_values_report_a_rounded_name_collision(tmp_path):
        """PFS-2095.038: distinct values that collide are described as rounding to one name."""
        row = dict.fromkeys(MATRIX_COLUMNS, "NA")
        row.update(
            POL="9001",
            HIDDEN="0",
            RUN="1",
            FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep, BETA:0",
            SWEEP_VALUES="0.11,0.12",
            FS_BUILD="MANUAL",
            WORKFLOW="unsteady",
            VAR_NAMES_VALUES="",
        )
        path = tmp_path / "matrix.fs"
        path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="0.11.*0.12.*round to the same name"):
            read_matrix(path)


_CASES_PPROC__SECTIONS = {"distributions": [{"families": "all", "planes": ["XZ"]}]}


_CASES_PPROC__SURFACE_PROBE = {
    "name": "upper_cp",
    "parameter": "CP_FREE",
    "frame": "REFERENCE",
    "point_m": [0.25, 0.1, 0.02],
}


_CASES_PPROC__NORMAL_PROBES = {
    "kind": "normal",
    "parameters": ["VX"],
    "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
}


class TestCasesPproc:
    """Tier 1: the pproc models refuse what they cannot honour and declare what they read (0.40.0)."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize("kind", ["vtk", "sections"])
    def test_p0400_boundary_layer_integrals_refuse_an_explicit_false_source(kind):
        """P0400-BL-SOURCES (PFS-2084.003): the product does not re-enable an export set false."""
        with pytest.raises(ValidationError) as caught:
            _CasesPprocPprocSpec.model_validate(
                {
                    "products": {"boundary_layer_integrals": True},
                    "sections": _CASES_PPROC__SECTIONS,
                    "exports": {kind: False},
                }
            )
        text = str(caught.value)
        assert "boundary_layer_integrals" in text and f"[exports] {kind} = false" in text

    @staticmethod
    def test_p0400_pproc_imports_no_acoustics_inside_a_function():
        """P0400-ACOUSTIC-CYCLE (PFS-2088.001): pproc holds the suffixes, acoustics publishes them."""  # noqa: E501
        tree = ast.parse(inspect.getsource(pproc))
        imported = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and "acoustics" in node.module
        ]
        assert imported == []
        assert acoustics.is_acoustic_output is pproc.is_acoustic_output
        assert acoustics.ACOUSTIC_SIGNALS_SUFFIX == pproc.ACOUSTIC_SIGNALS_SUFFIX
        assert classify_outputs(["P_acoustic_signals.txt", "P.txt"]) == {"loads": "P.txt"}

    @staticmethod
    @pytest.mark.parametrize(
        ("model", "data"),
        [
            (ProbeLine, {"start": [math.nan, 0, 0], "end": [1, 0, 0]}),
            (
                ProbeRectangle,
                {
                    "origin": [0, 0, 0],
                    "along_u": [math.inf, 0, 0],
                    "along_v": [0, 1, 0],
                    "points_u": 2,
                    "points_v": 2,
                },
            ),
            (
                ProbeCircle,
                {
                    "center": [0, 0, math.nan],
                    "normal": [0, 0, 1],
                    "radius": 1.0,
                    "points_radial": 2,
                    "points_azimuth": 3,
                },
            ),
        ],
    )
    def test_p0400_probe_shapes_refuse_non_finite_coordinates(model, data):
        """P0400-PROBE-FINITE (PFS-2093.008): a NaN or infinite coordinate is refused."""
        with pytest.raises(ValidationError, match="finite"):
            model.model_validate(data)

    @staticmethod
    @pytest.mark.parametrize("field", ["x_m", "y_m", "z_m", "diameter_m", "axis"])
    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_p0400_rotor_refuses_non_finite_geometry(field, value):
        """P0400-ROTOR-FINITE (PFS-2093.008): rotor coordinates and shaft components are finite."""
        data = {"alias": "ROTOR", "axis": "Z", "diameter_m": 1.0, "families_blades": ["Blade1"]}
        data[field] = [value, 0, 1] if field == "axis" else value
        with pytest.raises(ValidationError, match="finite"):
            RotorBlock.model_validate(data)

    @staticmethod
    def test_p0400_group_refusal_reaches_the_loader_with_the_artifact_path(tmp_path):
        """P0400-GROUPS-PATH (PFS-2100.001): the [groups] refusal names the artifact file."""
        path = tmp_path / "pproc" / "p001.toml"
        path.parent.mkdir()
        path.write_text('[groups]\ng1 = ["Wing", "Tail"]\n', encoding="utf-8")
        with pytest.raises(InputArtifactError) as caught:
            resolve_pproc(tmp_path, "p001")
        text = str(caught.value)
        assert str(path) in text and "member lists were removed" in text

    @staticmethod
    @pytest.mark.parametrize("stated", [3, True, {"alias": "wing"}])
    def test_p0400_group_that_is_not_a_string_is_refused_by_name(stated):
        """P0400-GROUPS-FORM (PFS-2100.002): no 'valid list' error on the entries that are right."""
        with pytest.raises(ValidationError) as caught:
            _CasesPprocPprocSpec.model_validate({"groups": {"g1": "wing", "g2": stated}})
        text = str(caught.value)
        assert "'g2'" in text and "a group names ONE alias as a string" in text
        assert "valid list" not in text

    @staticmethod
    def test_p0400_unsteady_surface_probes_declare_the_plots_export_with_normal_probes():
        """P0400-SURFACE-PLOTS (PFS-2105.002): the surface-probe history is in the plots export."""
        spec = _CasesPprocPprocSpec.model_validate(
            {
                "probes": [_CASES_PPROC__NORMAL_PROBES],
                "surface_probes": [_CASES_PPROC__SURFACE_PROBE],
                "exports": {"plots": False},
            }
        )
        assert "{name}_plots.txt" in spec.outputs(True)

    @staticmethod
    def test_p0400_probe_frame_written_empty_is_the_hub_frame():
        """P0400-PROBE-FRAME (PFS-2095.005): frame = "" means what the omitted key means."""
        assert ProbesSpec(frame="").frame == ProbesSpec().frame == ""
        assert ProbesSpec(frame="  ").frame == ""

    @staticmethod
    def test_p0400_classify_outputs_does_not_fall_through_to_a_shorter_suffix():
        """P0400-CLASSIFY-DUPLICATE (PFS-2105.001): a second _cp.txt does not claim the loads kind."""  # noqa: E501
        assert classify_outputs(["P_cp.txt", "P2_cp.txt", "P.txt"])["loads"] == "P.txt"
        assert "loads" not in classify_outputs(["{name}_cp.txt", "{name}_wing_cp.txt"])

    @staticmethod
    def test_p0400_vtk_variables_accept_every_build_and_any_case():
        """P0400-VTK-VARIABLES (PFS-2135.064): 26.125 tokens and lower case are the declared names."""  # noqa: E501
        spec = _CasesPprocPprocSpec(vtk_variables=["C_H", "cp_reference"])
        assert spec.vtk_variables == ["C_H", "CP_REFERENCE"]
        with pytest.raises(ValidationError, match="unknown variable"):
            _CasesPprocPprocSpec(vtk_variables=["NOT_A_VARIABLE"])
        with pytest.raises(ValidationError, match="distinct"):
            _CasesPprocPprocSpec(vtk_variables=["CP", "cp"])

    @staticmethod
    def test_p0400_surface_probe_parameter_accepts_lowercase():
        """P0400-SURFACE-TOKEN (PFS-2135.064): surface properties use the emitter's enum spelling."""  # noqa: E501
        assert (
            SurfaceProbeSpec(name="cp", parameter="cp_free", point_m=(0, 0, 0)).parameter
            == "CP_FREE"
        )

    @staticmethod
    def test_p0400_vtk_variables_are_refused_naming_the_target_build(tmp_path):
        """P0400-VTK-BUILD (PFS-2135.064): a union token is checked when the target is known."""
        case = _cases_pproc___with_pproc(
            _cases_pproc__steady_case(),
            _cases_pproc___wb_geometry(tmp_path),
            pproc=_CasesPprocPprocSpec(vtk_variables=["C_H"]),
        )
        case.outputs = ["P.txt", "P.vtk"]
        with pytest.raises(CampaignConfigError, match="C_H.*26.124"):
            build_script(case, Script("26.124"))
        script = Script("26.125")
        build_script(case, script)
        assert "C_H" in script.render()


_CASES_SELECTION__INVENTORY = ["Wing", "Fuselage", "Blade1", "Blade2"]


def _cases_selection___is_blade(name):
    return name.startswith("Blade")


class TestCasesSelection:
    """Tier 1: families selection reads `all` alike everywhere and refuses retired words (0.40.0)."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize("selection", [["all"], ["Wing", "all"]])
    def test_p0400_all_in_a_families_list_selects_every_surface(selection):
        """P0400-ALL-IN-LIST (PFS-2104.002, PFS-2085.012): `all` in a list is not a family name."""
        assert select_families(
            selection, _CASES_SELECTION__INVENTORY, _cases_selection___is_blade
        ) == [_CASES_SELECTION__INVENTORY]
        assert (
            select_group_members(["all"], _CASES_SELECTION__INVENTORY)
            == _CASES_SELECTION__INVENTORY
        )
        # The bare word keeps the command's own every-boundary form.
        assert select_families("all", _CASES_SELECTION__INVENTORY, _cases_selection___is_blade) == [
            []
        ]

    @staticmethod
    def test_p0400_the_retired_selector_reader_is_declared_to_never_return():
        """P0400-SELECTOR-REFUSES (PFS-2095.063): it refuses, so nothing after it is selection code."""  # noqa: E501
        assert get_type_hints(warn_a_selector_that_guesses)["return"] is NoReturn
        assert warn_a_selector_that_guesses.__doc__.startswith("Refuse")
        for word in ("airframe", "blades"):
            with pytest.raises(CampaignConfigError, match="no longer accepted"):
                select_families(word, _CASES_SELECTION__INVENTORY, _cases_selection___is_blade)
            with pytest.raises(CampaignConfigError, match="no longer accepted"):
                select_families(
                    ["Wing", word], _CASES_SELECTION__INVENTORY, _cases_selection___is_blade
                )


class TestCasesSetupLink:
    """Tier 1: a setup family list reads each name as every cited name is read (0.40.0)."""

    @staticmethod
    @pytest.mark.parametrize(
        ("families", "expected"),
        [
            (["Hub", "Blade"], [1, 2, 3]),
            # A case variant of one label is that label (PFS-2104.001), not its family.
            (["Hub", "blade1"], [1, 2]),
            (["Blade"], [2, 3]),
            (["Hub", "rotor"], [1, 2, 3]),
        ],
    )
    def test_p0400_family_word_alias_and_case_variant_select_every_member(families, expected):
        """P0400-SETUP-FAMILIES (PFS-2104.028): no name of the list is dropped in silence."""
        case = SimCase(
            sim_id="9001",
            aircraft="Rotor",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            solver=SolverSettings(analysis_families=families),
            aliases={"rotor": ["Blade"]},
        )
        script = Script("26.124")
        script.declare_existing(boundaries={"Hub": 1, "Blade1": 2, "Blade2": 3})
        indices = family_indices(
            case,
            script,
            case.solver.analysis_families,
            keyword="analysis_boundaries",
            preset_key="analysis_families",
            dropped="every boundary is analysed",
        )
        assert indices == expected


class TestCasesWindows:
    """Tier 1: the phase-locked gate meets its minimum on a floating-point clock (0.40.0)."""

    @staticmethod
    def test_p0400_a_run_of_exactly_min_revolutions_is_not_skipped():
        """P0400-PHASE-GATE (PFS-2105.026): 1920 steps at 240.00000000000003 per turn are 8 turns."""  # noqa: E501
        gate = PhaseLockedSpec(min_revolutions=8, last_revolutions_avg=2)
        entry = phase_locked_entry(
            gate, last_step=1920, per_revolution=240.00000000000003, who="ROTOR"
        )
        assert "skipped" not in entry, entry.get("skipped")
        assert entry["windows"] == [[1441, 1920]]
        short = phase_locked_entry(gate, last_step=1919, per_revolution=240.0, who="ROTOR")
        assert "skipped" in short


_CASES_REVIEW__INVALID_WINDOWS = [
    {"LAST_REVS_AVG": "0.01"},
    {"LAST_REVS_AVG": "1", "LAST_ITERS_AVG": "10"},
    {"LAST_REVS_AVG": "inf"},
    {"LAST_ITERS_AVG": "0"},
    {"LAST_ITERS_AVG": "-1"},
    {"LAST_ITERS_AVG": "nan"},
]


class TestCasesReview:
    """P0400 adversarial regressions for the cases lane."""

    @staticmethod
    def test_p0400_review_probe_kind_decision_includes_volume_section(tmp_path):
        """P0400-REVIEW-PROBES: outputs and builders refuse the same mixed source."""
        spec = _CasesReviewPprocSpec.model_validate(
            {
                "probes": [_CASES_PPROC__NORMAL_PROBES],
                "volume_section": {
                    "shape": "rectangle",
                    "plane": "YZ",
                    "corners_m": [-1, -2, 1, 2],
                    "points": [2, 2],
                },
            }
        )
        case = _cases_review___with_pproc(
            _cases_review___case_for("unsteady"), _cases_review___wb_geometry(tmp_path), pproc=spec
        )
        with pytest.raises(CampaignConfigError, match="volume_section"):
            spec.outputs(True)
        with pytest.raises(CampaignConfigError, match="volume_section"):
            build_script(case, Script("26.124"))
        assert spec.outputs(False)

    @staticmethod
    @pytest.mark.parametrize("token", ["Wing", ["Wing"]])
    def test_p0400_review_boundary_alias_collision_has_one_meaning(token):
        """P0400-REVIEW-SELECTION: plots, groups and nested aliases select the exact label."""
        inventory = ["Wing", "Tail"]
        aliases = {"Wing": ["Tail"], "nested": ["Wing"]}
        assert select_families(token, inventory, lambda _: False, aliases) == [["Wing"]]
        assert select_group_members(["Wing"], inventory, aliases) == ["Wing"]
        assert resolve_alias("nested", inventory, aliases) == ["Wing"]
        assert alias_members_missing("Wing", inventory, {"Wing": ["Absent"]}) == []

    @staticmethod
    def test_p0400_review_conversion_refuses_to_drop_row_build(tmp_path):
        """P0400-REVIEW-BUILD: an unbound per-row installation cannot silently use the default."""
        path = _cases_matrix___matrix(tmp_path, FS_BUILD="26.125")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(MatrixError, match="matrix is the sole campaign declaration"):
                convert_matrix(path, **_CASES_MATRIX__CAMPAIGN)

    @staticmethod
    @pytest.mark.parametrize("j", [0.7, 0.6])
    def test_p0400_review_phase_wrap_uses_only_contributing_corners(j):
        """P0400-REVIEW-PHASE: a zero-weight corner cannot choose the other edge's arc."""
        rows = [
            CalibrationRow("THRUST", x, alpha, 0, 0, 1, 1, phase)
            for x, alpha, phase in [(0.5, 0, 0), (0.5, 1, 0), (0.7, 0, 170), (0.7, 1, 190)]
        ]
        calibration = parse_calibration(calibration_text("table", rows))
        found = calibration.lookup("THRUST", {"J": j, "ALPHA": 0.5})
        if j == 0.7:
            assert found.coefficients[3] % 360 == pytest.approx(180)
        else:
            assert found.coefficients is None
            assert "phase" in found.reason and "half a turn" in found.reason

    @staticmethod
    @pytest.mark.parametrize("variables", _CASES_REVIEW__INVALID_WINDOWS)
    def test_p0400_review_invalid_windows_refused_by_plan_and_post(variables):
        """P0400-REVIEW-WINDOW: invalid input never becomes a recorded or one-step window."""
        plan = {"time_iterations": 1000, "steps_per_revolution": 36.0}
        case = _cases_review__rotor_case(LAST_REVS_AVG=None, DELTA_TIME=str(60 / (1200 * 36)))
        case.variables.update(variables)
        with pytest.raises(CampaignConfigError, match="LAST_|averag"):
            averaging_steps(variables, per_revolution=36.0)
        # PFS-2095.007 (cases-workflows): the plan records an uninterpretable window as
        # a skip naming the row, every reduction alike, and never as a window; the build
        # refuses a declared value that is invalid in itself. A window shorter than one
        # step is judged against the clock, so the build passes it and the post skips it.
        recorded = reduction_windows(case)
        assert recorded is not None
        for reduction in ("time_average", "phase_locked", "per_blade"):
            assert "7001" in recorded[reduction]["skipped"]
            assert "windows" not in recorded[reduction]
        if variables != {"LAST_REVS_AVG": "0.01"}:
            with pytest.raises(CampaignConfigError, match="7001"):
                build_script(case, Script("26.124"))
        with pytest.raises(CampaignConfigError):
            replan(plan, variables)

    @staticmethod
    @pytest.mark.parametrize("value", ["inf", "nan", "0", "-1"])
    def test_p0400_review_stated_key_refuses_invalid_values(value):
        """P0400-REVIEW-WINDOW-KEY: a stated invalid value is not an absent window."""
        with pytest.raises(CampaignConfigError):
            stated_key({"LAST_REVS_AVG": value})

    @staticmethod
    @pytest.mark.parametrize(
        "window",
        ["LAST_ITERS_AVG: inf", "LAST_ITERS_AVG: 0.01", "LAST_ITERS_AVG: 4 / LAST_REVS_AVG: 1"],
    )
    def test_p0400_review_post_records_invalid_window_refusal(tmp_path, window):
        """P0400-REVIEW-POST-WINDOW: products.json and post.log name the invalid current row."""
        plan = {
            "window_stated": True,
            "time_iterations": 8,
            "steps_per_revolution": 36.0,
            "time_average": {"windows": [[5, 8]], "window_from": "recorded"},
        }
        workspace = _cases_review___unsteady_workspace(tmp_path, reductions=plan, recipe="unsteady")
        records = workspace.read_raw_manifest()
        container = records
        container[0]["matrix_stem"] = "matriz"
        workspace._replace_manifest(records)
        (workspace.root / "matriz.fs").write_text(
            _cases_review__window_matrix(window), encoding="utf-8"
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
        root = workspace.root / "post" / "matriz"
        result = json.loads((root / "products.json").read_text(encoding="utf-8"))
        reason = result["skipped"][f"runs/{container[0]['run_id']}"]
        assert "averaging window" in reason and "LAST_" in reason
        assert "averaging window" in (root / "post.log").read_text(encoding="utf-8")
        assert not any(name.endswith("_time_average.csv") for name in result.get("products", {}))

    @staticmethod
    @pytest.mark.requirement("FR-1610")
    def test_p0430_pprocspec_groups_survive_a_dump_and_validate_round_trip():
        """PFS-2124.012: a PprocSpec re-validates its own dump, in python and json mode."""
        from pyflightstream.cases.pproc import PprocSpec

        spec = PprocSpec(groups={"1": "wing", "2": "tail"})
        for mode in ("python", "json"):
            again = PprocSpec.model_validate(spec.model_dump(mode=mode))
            assert again.groups == spec.groups
        assert spec.model_dump()["groups"] == {"1": "wing", "2": "tail"}

    @staticmethod
    def test_p0430_a_probe_entry_that_draws_points_and_states_no_parameters_is_refused():
        """PFS-2119.018: refused at load, not dropped; field formats add VX, VY and VZ."""
        from pyflightstream.cases.pproc import ProbesSpec

        line = {"start": [0, 0, 0], "end": [1, 0, 0]}
        with pytest.raises(ValidationError, match="requires nonempty parameters"):
            ProbesSpec.model_validate({"lines": [line]})
        kept = ProbesSpec.model_validate({"lines": [line], "parameters": ["VX"]})
        assert kept.parameters == ["VX"]
        added = ProbesSpec.model_validate({"lines": [line], "field_formats": ["vtk"]})
        assert added.parameters == ["VX", "VY", "VZ"]


# ---------------------------------------------------------------------------
# GOAL-056 package F5-0708 (pyflightstream 0.43.0)
# ---------------------------------------------------------------------------


def _f5_rotor(**overrides):
    stated = {
        "alias": "A",
        "x_m": 0.0,
        "y_m": 0.0,
        "z_m": 0.0,
        "axis": "Z",
        "rpm_sign": 1,
        "diameter_m": 1.0,
        "families_blades": ["b"],
        "blade1": {"azimuth_deg": 0.0, "zero": "X"},
    }
    stated.update(overrides)
    return RotorBlock(**stated)


def test_f057_a_huge_finite_axis_normalizes_to_a_unit_vector():
    """F-057: the norm of (1e200, 1e200, 0) overflowed to infinity and the axis became zero."""
    axis = _f5_rotor(axis=[1e200, 1e200, 0.0], blade1={"azimuth_deg": 0.0, "zero": "Z"}).axis_vector
    assert axis == pytest.approx((math.sqrt(0.5), math.sqrt(0.5), 0.0))


def test_pfs_2126_008_read_qsteady_record_takes_a_string_path(tmp_path):
    """PFS-2126.008: a str path is refused as an absent record, not with an AttributeError."""
    from pyflightstream.cases.qsteady import QsteadyRecordError, read_qsteady_record

    with pytest.raises(QsteadyRecordError, match="not on disk"):
        read_qsteady_record(str(tmp_path / "p1_loads.csv"))


def test_pfs_2119_019_point_state_key_treats_negative_zero_as_zero():
    from pyflightstream.cases.settings import point_state_key

    assert point_state_key({"alpha": -0.0, "beta": 2.0}) == point_state_key(
        {"alpha": 0.0, "beta": 2.0}
    )
    assert point_state_key({"alpha": -0.0}) == "alpha=0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("density_kg_m3", 0.0),
        ("pressure_pa", -1.0),
        ("temperature_k", float("nan")),
        ("viscosity_pa_s", float("inf")),
        ("sonic_velocity_m_per_s", 0.0),
        ("velocity_m_per_s", -1.0),
    ],
)
def test_pfs_2119_020_fluid_state_refuses_a_non_physical_value(field, value):
    from pyflightstream.cases.settings import FluidState

    stated = {
        "velocity_m_per_s": 10.0,
        "density_kg_m3": 1.2,
        "pressure_pa": 101325.0,
        "temperature_k": 288.15,
        "viscosity_pa_s": 1.8e-5,
        "sonic_velocity_m_per_s": 340.0,
        "source": "atmosphere",
    }
    FluidState(**stated)
    stated[field] = value
    with pytest.raises(ValidationError):
        FluidState(**stated)


def test_f1310_aliases_differing_only_in_case_are_refused():
    from pyflightstream.cases.selection import _check_aliases

    _check_aliases({"Wing": ["W"], "Body": ["B"]})
    with pytest.raises(ValueError, match="more than once"):
        _check_aliases({"Wing": ["W1"], "wing": ["W2"]})


def test_f059_body_rates_differing_only_in_case_are_refused():
    from pyflightstream.cases.settings import ReferenceData

    with pytest.raises(ValidationError, match="more than once"):
        ReferenceData(area=1.0, length=1.0, body_axes={"roll": "X", "ROLL": "Y"})
    assert ReferenceData(area=1.0, length=1.0, body_axes={"roll": "X", "yaw": "Z"}).body_axes == {
        "roll": "X",
        "yaw": "Z",
    }
