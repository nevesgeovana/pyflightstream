"""Regression coverage grouped by subject."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import threading
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest
from pydantic import ValidationError

import pyflightstream.workspace as workspace_module
from pyflightstream._atmosphere import ISA
from pyflightstream._errors import InputArtifactError as _Workspace1CostsInputArtifactError
from pyflightstream._errors import InputArtifactError as _Workspace2BuildsInputArtifactError
from pyflightstream._errors import InputArtifactError as _Workspace2CostsInputArtifactError
from pyflightstream._errors import InputArtifactError as _Workspace2HpcInputArtifactError
from pyflightstream._errors import InputArtifactError as _Workspace2ReviewInputArtifactError
from pyflightstream._errors import InputArtifactError as _Workspace2SettingsFileInputArtifactError
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError as _Workspace2InputsCampaignConfigError
from pyflightstream.cases import RawMeshConditions, SimCase, SweepAxis, TrailingEdgeMarking
from pyflightstream.cases._skipped_families import (
    declared_names_the_geometry_lacks,
    names_no_boundary_answers,
)
from pyflightstream.cases.reference_blocks import (
    CampaignConfigError as _IntegfixStrictBoundaryCampaignConfigError,
)
from pyflightstream.cases.selection import resolve_alias, select_families, select_group_members
from pyflightstream.cases.workflows import build_script, row_ncpus, row_symmetry_loads
from pyflightstream.cases.workflows._geometry import _plan_import_operations
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.run import cli
from pyflightstream.run.cli import main as matrix_cli
from pyflightstream.script import Script
from pyflightstream.workspace import (
    CampaignWorkspace,
    PointName,
    WorkspaceError,
    _is_link,
    costs,
    hpc,
    refine_mesh,
    storage,
)
from pyflightstream.workspace import InputArtifactError as _Workspace1InputsInputArtifactError
from pyflightstream.workspace._degenerate import CHORD_PANELS, derive_thin_blade
from pyflightstream.workspace._refine._obj import read_te
from pyflightstream.workspace._script_comparison import compare_scripts, drift
from pyflightstream.workspace._settings_file import read_workspace_settings, settings_supplied
from pyflightstream.workspace._verdicts import DELETED_SIM_KEY, merge_runs
from pyflightstream.workspace.builds import resolve_build
from pyflightstream.workspace.costs import (
    priced_rows,
    read_cost_file,
    resolve_cost_file,
    select_cost_file,
)
from pyflightstream.workspace.fields import Field, subtract_fields
from pyflightstream.workspace.flight_condition import (
    PINNED_STATE_TOLERANCE,
    pinned_state_mismatch,
    resolve_flight_condition,
)
from pyflightstream.workspace.hpc import read_hpc_profile, resolve_hpc_profile, select_hpc_profile
from pyflightstream.workspace.inputs import (
    InputArtifactError as _Workspace1GeometryCleanInputArtifactError,
)
from pyflightstream.workspace.inputs import (
    InputArtifactError as _Workspace1TrailingEdgesInputArtifactError,
)
from pyflightstream.workspace.inputs import (
    RotorReference,
    clean_saved_actions,
    rotor_integration_groups,
)
from pyflightstream.workspace.matrix import resolve_matrix
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from pyflightstream.workspace.setup_inspection import inspect_case_setup
from pyflightstream.workspace.setup_standards import (
    render_guidelines,
    setup_entry_evidence,
    write_setup_library,
)
from pyflightstream.workspace.sidecars import (
    inventory_sidecar,
    read_inventory,
    read_mesh_import,
)
from pyflightstream.workspace.trailing_edges import extract_trailing_edge
from tests.p0380_mesh_fixtures import Composite as _Workspace2ReviewComposite
from tests.p0380_mesh_fixtures import sheet_with_strips as _workspace_2_review__sheet_with_strips
from tests.p0380_mesh_fixtures import write_source as _workspace_2_review__write_source
from tests.support_helpers import FIXTURE as _INTEGFIX_STATE_CONSISTENCY__FIXTURE
from tests.support_helpers import make_library as _integfix_state_consistency__make_library
from tests.tier1_offline.test_goal024_profile_log import PROFILE as _WORKSPACE_2_HPC__PROFILE
from tests.tier1_offline.test_goal035_storage import (
    _shared_product_workspace as _workspace_3_review___shared_product_workspace,
)
from tests.tier1_offline.test_goal035_storage import _sync_pair as _workspace_3_review___sync_pair
from tests.tier1_offline.test_goal035_storage import _write as _workspace_3_review___write
from tests.tier1_offline.test_goal035_storage import _ws as _workspace_3_review___ws
from tests.tier1_offline.test_inventory_cli import (
    _FR312_INVENTORY_CLEAN__TIER3 as _WORKSPACE_1_GEOMETRY_CLEAN__TIER3,
)
from tests.tier1_offline.test_inventory_cli import (
    _fr312_inventory_clean___dirty as _workspace_1_geometry_clean___dirty,
)
from tests.tier1_offline.test_inventory_cli import (
    _fr312_inventory_clean___text as _workspace_1_geometry_clean___text,
)
from tests.tier1_offline.test_p0340_thin_blade import CHORD as _WORKSPACE_1_DEGENERATE__CHORD
from tests.tier1_offline.test_p0340_thin_blade import RINGS as _WORKSPACE_1_DEGENERATE__RINGS
from tests.tier1_offline.test_p0340_thin_blade import ROOT as _WORKSPACE_1_DEGENERATE__ROOT
from tests.tier1_offline.test_p0340_thin_blade import (
    SIDE_POINTS as _WORKSPACE_1_DEGENERATE__SIDE_POINTS,
)
from tests.tier1_offline.test_p0340_thin_blade import TIP as _WORKSPACE_1_DEGENERATE__TIP
from tests.tier1_offline.test_p0340_thin_blade import _blade as _workspace_1_degenerate___blade
from tests.tier1_offline.test_p0340_thin_blade import _camber as _workspace_1_degenerate___camber
from tests.tier1_offline.test_p0340_thin_blade import (
    _half_thickness as _workspace_1_degenerate___half_thickness,
)
from tests.tier1_offline.test_p0340_thin_blade import (
    _read_obj as _workspace_1_degenerate___read_obj,
)
from tests.tier1_offline.test_p0340_thin_blade import (
    _stations as _workspace_1_degenerate___stations,
)
from tests.tier1_offline.test_p0340_thin_blade import (
    _write_obj as _workspace_1_degenerate___write_obj,
)
from tests.tier1_offline.test_p0350_cost_file import _FILE as _WORKSPACE_1_COSTS___FILE
from tests.tier1_offline.test_p0350_cost_file import _FILE as _WORKSPACE_2_COSTS___FILE
from tests.tier1_offline.test_p0350_cost_file import _inputs as _workspace_1_costs___inputs
from tests.tier1_offline.test_p0350_cost_file import _row as _workspace_1_costs___row
from tests.tier1_offline.test_post_superfile import (
    _workspace as _integfix_state_consistency___workspace,
)
from tests.tier1_offline.test_regression_workspace_refinement import (
    _workspace_2_refine_wing__wing as _workspace_2_review__wing,
)
from tests.tier1_offline.test_regression_workspace_storage import (
    _WORKSPACE_3_STORAGE__FULL as _WORKSPACE_3_REVIEW__FULL,
)
from tests.tier1_offline.test_regression_workspace_storage import (
    _workspace_3_storage___compacted as _workspace_3_review___compacted,
)
from tests.tier1_offline.test_regression_workspace_storage import (
    _workspace_3_storage___recorded_sim as _workspace_3_review___recorded_sim,
)
from tests.tier1_offline.test_regression_workspace_storage import (
    _workspace_3_storage___rows as _workspace_3_review___rows,
)
from tests.tier1_offline.test_trailing_edges import (
    _blade_file as _workspace_1_trailing_edges___blade_file,
)
from tests.tier1_offline.test_workflows import steady_case as _workspace_1_degenerate__steady_case
from tests.tier1_offline.test_workspace import make_record as _workspace_1_init__make_record

_INTEGFIX_SETUP_EVIDENCE__REPORT = "reports/compat/CMP-2026-09-27-setup-parser.md"


_INTEGFIX_SETUP_EVIDENCE__COMMANDS = {
    "wake_relaxation": "SET_WAKE_RELAXATION",
    "wake_streamwise_agglomeration": "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "adverse_gradient_boundary_layer": "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
}


class TestIntegfixSetupEvidence:
    """Tier 1, 0.40.0 integration fixes: the setup evidence reads the command database alone."""

    @staticmethod
    @pytest.mark.parametrize("key", sorted(_INTEGFIX_SETUP_EVIDENCE__COMMANDS))
    @pytest.mark.parametrize("build", ["26.123", "26.124"])
    def test_p0400_a_parser_refusal_is_a_database_row_not_a_literal(key, build):
        """P0400-SETUP-PARSER-ROWS (PFS-2084.002): the 26.123/26.124 refusals are version rows.

        The workspace layer appended the parser probe's evidence from a literal set of
        builds and keys while the command database held no row for either build; the
        database now records each as removed, citing the probe, and the evidence line
        reads it from there.
        """
        row = (
            CommandRegistry.load().commands[_INTEGFIX_SETUP_EVIDENCE__COMMANDS[key]].versions[build]
        )
        assert row.status is Status.REMOVED
        assert row.probe_ref == _INTEGFIX_SETUP_EVIDENCE__REPORT
        available, said = setup_entry_evidence(key, build)
        assert not available
        assert f"build {build}: removed" in said and _INTEGFIX_SETUP_EVIDENCE__REPORT in said, said

    @staticmethod
    def test_p0400_the_guidelines_carry_no_parser_literal():
        """P0400-SETUP-PARSER-ROWS (PFS-2084.002): render_guidelines repeated the literal."""
        assert "Native parser-only observations" not in render_guidelines("26.124")


_INTEGFIX_STATE_CONSISTENCY__R = ISA.gas_constant_j_per_kg_k


_INTEGFIX_STATE_CONSISTENCY__LAW = "p = rho R T"


_INTEGFIX_STATE_CONSISTENCY__STATED = "MACH:0.1441, REmi:4.38"


def _integfix_state_consistency___mismatch(
    density: float, temperature: float, pressure: float
) -> str:
    """The relative mismatch as the warning prints it."""
    return (
        f"{abs(pressure - density * _INTEGFIX_STATE_CONSISTENCY__R * temperature) / pressure:.2%}"
    )


# ------------------------------------------------------------------ the plan
def _integfix_state_consistency___planned(tmp_path: Path, cell: str) -> list[str]:
    """Resolve the fixture matrix with ``cell`` in place of its condition; the warnings."""
    workspace = _integfix_state_consistency__make_library(tmp_path)
    matrix = tmp_path / "matriz.fs"
    body = _INTEGFIX_STATE_CONSISTENCY__FIXTURE.read_text(encoding="utf-8")
    assert _INTEGFIX_STATE_CONSISTENCY__STATED in body
    matrix.write_text(body.replace(_INTEGFIX_STATE_CONSISTENCY__STATED, cell), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolve_matrix(
            matrix,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes={"003": "steady", "004": "steady"},
            fs_exe="C:/fs/FlightStream.exe",
        )
    return [
        str(w.message)
        for w in caught
        if issubclass(w.category, PyflightstreamWarning)
        and _INTEGFIX_STATE_CONSISTENCY__LAW in str(w.message)
    ]


# ------------------------------------------------------------------ the post
def _integfix_state_consistency___posted(tmp_path: Path, condition: dict[str, float] | None) -> str:
    """Post the recorded superfile campaign with sim 6001's condition replaced; post.log."""
    workspace = _integfix_state_consistency___workspace(tmp_path)
    if condition is not None:
        raw = _read_record_rows(workspace.manifest_path)
        for row in raw:
            if str(row["sim_id"]) == "6001":
                row["flight_condition"] = condition
        workspace._replace_manifest(raw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert cli.main(["post", "matriz", "--workspace", str(workspace.root)]) == 0
    return (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")


class TestIntegfixStateConsistency:
    """Tier 1, 0.40.0: a fully pinned gas state at odds with p = rho R T is WARNED, P0400-STATECONS.

    A session decision of the 0.40.0 integration lane, under the owner's physics
    autonomy: when density, temperature and pressure are ALL pinned for a point
    (``RHOkgm3``, ``TK`` and ``PPA``, by the row or by its setup's defaults), the
    plan and the post warn when ``|p - rho R T| / p`` exceeds half a percent,
    naming the three values, the gas constant the package uses for air and the
    relative mismatch. Nothing is refused or withheld: the pins are emitted as
    written. A state with any of the three derived satisfies the law by
    construction and is never checked. The plan and the post call one function,
    :func:`pyflightstream.workspace.flight_condition.pinned_state_mismatch`.

    Every fixture is synthetic.
    """

    @staticmethod
    # ------------------------------------------------------------- the one check
    def test_p0400_statecons_a_consistent_pinned_triple_is_not_warned():
        """P0400-STATECONS: 1.225 kg/m3, 288.15 K and 101325 Pa agree; nothing is said."""
        state = resolve_flight_condition(
            {"MACH": 0.2, "RHOkgm3": 1.225, "TK": 288.15, "PPA": 101325.0}, pol="P1"
        )
        assert state.pinned == ("RHOkgm3", "TK", "PPA")
        assert pinned_state_mismatch(state, pol="P1") is None

    @staticmethod
    def test_p0400_statecons_an_inconsistent_pinned_triple_names_the_values_r_and_the_mismatch():
        """P0400-STATECONS: the message names the three pins, R and the relative mismatch."""
        state = resolve_flight_condition(
            {"MACH": 0.2, "RHOkgm3": 1.0, "TK": 288.15, "PPA": 101325.0}, pol="P1"
        )
        message = pinned_state_mismatch(state, pol="P1")
        assert message is not None
        for named in (
            "POL P1",
            "RHOkgm3:1,",
            "TK:288.15",
            "PPA:101325",
            f"R = {_INTEGFIX_STATE_CONSISTENCY__R}",
            _INTEGFIX_STATE_CONSISTENCY__LAW,
        ):
            assert named in message, named
        assert _integfix_state_consistency___mismatch(1.0, 288.15, 101325.0) in message
        # THE PINS ARE EMITTED AS WRITTEN: the check refuses and corrects nothing.
        assert (state.density_kg_m3, state.temperature_k, state.pressure_pa) == (
            1.0,
            288.15,
            101325.0,
        )

    @staticmethod
    def test_p0400_statecons_the_tolerance_is_half_a_percent_either_side():
        """P0400-STATECONS: 0.4 percent off is quiet, 0.6 percent off is warned."""
        exact = 101325.0 / (_INTEGFIX_STATE_CONSISTENCY__R * 288.15)
        for factor, warned in ((1.004, False), (0.996, False), (1.006, True), (0.994, True)):
            state = resolve_flight_condition(
                {"MACH": 0.2, "RHOkgm3": exact * factor, "TK": 288.15, "PPA": 101325.0}, pol="P1"
            )
            assert (pinned_state_mismatch(state, pol="P1") is not None) is warned, factor
        assert PINNED_STATE_TOLERANCE == 0.005

    @staticmethod
    @pytest.mark.parametrize(
        "cell",
        [
            {"MACH": 0.2, "RHOkgm3": 1.0, "TK": 288.15},  # pressure derived
            {"MACH": 0.2, "RHOkgm3": 1.0, "PPA": 101325.0},  # temperature from the atmosphere
            {"MACH": 0.2, "TK": 250.0, "PPA": 101325.0},  # density derived
            {"MACH": 0.2, "REmi": 4.38, "TK": 250.0, "PPA": 101325.0},  # density solved
        ],
    )
    def test_p0400_statecons_a_state_with_one_of_the_three_derived_is_not_checked(cell):
        """P0400-STATECONS: only a state pinning all three is checked."""
        state = resolve_flight_condition(cell, pol="P1", reference_length_m=1.0)
        assert pinned_state_mismatch(state, pol="P1") is None

    @staticmethod
    def test_p0400_statecons_the_plan_warns_an_inconsistent_pinned_row(tmp_path):
        """P0400-STATECONS: the plan warns, naming the row, the three values and the mismatch."""
        said = _integfix_state_consistency___planned(
            tmp_path, "MACH:0.1441, RHOkgm3:1.0, TK:288.15, PPA:101325"
        )
        (message,) = [m for m in said if "POL 9001" in m]
        for named in (
            "RHOkgm3:1,",
            "TK:288.15",
            "PPA:101325",
            f"R = {_INTEGFIX_STATE_CONSISTENCY__R}",
        ):
            assert named in message, named
        assert _integfix_state_consistency___mismatch(1.0, 288.15, 101325.0) in message

    @staticmethod
    def test_p0400_statecons_the_plan_is_quiet_for_a_consistent_or_derived_state(tmp_path):
        """P0400-STATECONS: a consistent triple, and a solved density beside TK and PPA, say nothing."""  # noqa: E501
        assert (
            _integfix_state_consistency___planned(
                tmp_path / "a", "MACH:0.1441, RHOkgm3:1.225, TK:288.15, PPA:101325"
            )
            == []
        )
        assert (
            _integfix_state_consistency___planned(
                tmp_path / "b", "MACH:0.1441, REmi:4.38, TK:250, PPA:101325"
            )
            == []
        )

    @staticmethod
    def test_p0400_statecons_the_post_logs_an_inconsistent_pinned_point(tmp_path):
        """P0400-STATECONS: post.log names it once; TK and PPA come from the setup's defaults."""
        log = _integfix_state_consistency___posted(tmp_path, {"MACH": 0.2, "RHOkgm3": 1.0})
        lines = [line for line in log.splitlines() if _INTEGFIX_STATE_CONSISTENCY__LAW in line]
        # Two recorded points of one simulation, one state: said ONCE.
        assert len(lines) == 1, lines
        (line,) = lines
        for named in (
            "POL 6001",
            "RHOkgm3:1,",
            "TK:288.15",
            "PPA:101325",
            f"R = {_INTEGFIX_STATE_CONSISTENCY__R}",
        ):
            assert named in line, named
        assert _integfix_state_consistency___mismatch(1.0, 288.15, 101325.0) in line
        # NOTHING IS WITHHELD: the simulation's polar is still written.
        assert list((tmp_path / "camp" / "post" / "matriz").glob("polars/P6001-*_g02.csv"))

    @staticmethod
    def test_p0400_statecons_the_post_is_quiet_for_a_consistent_or_derived_state(tmp_path):
        """P0400-STATECONS: the fixture's solved density, and a consistent triple, log nothing."""
        assert _INTEGFIX_STATE_CONSISTENCY__LAW not in _integfix_state_consistency___posted(
            tmp_path / "a", None
        )
        assert _INTEGFIX_STATE_CONSISTENCY__LAW not in _integfix_state_consistency___posted(
            tmp_path / "b", {"MACH": 0.2, "RHOkgm3": 1.225}
        )


_INTEGFIX_STRICT_BOUNDARY__ROUTES = ["family", "list", "group", "alias"]


_INTEGFIX_STRICT_BOUNDARY__ALONE = ["family", "list", "group"]


_INTEGFIX_STRICT_BOUNDARY__SECTOR = ["Hub", "Blade1", "Blade2"]


_INTEGFIX_STRICT_BOUNDARY__SIX_BLADES = [f"Blade{number}" for number in range(1, 7)]


def _integfix_strict_boundary___select(route: str, inventory: list[str]) -> object:
    if route == "group":
        return select_group_members(["Blade1"], inventory)
    if route == "alias":
        return resolve_alias("blades_a", inventory, {"blades_a": ["Blade1"]})
    selection = "Blade1" if route == "family" else ["Blade1"]
    return select_families(selection, inventory, lambda name: False)


class TestIntegfixStrictBoundary:
    """P0400-STRICT-BOUNDARY: an absent numbered boundary is refused only by a known inventory.

    The refusal of PFS-2029.25 (a cell citing Hub1 over a geometry with Hub2 and
    Hub3 is refused by exact name) fired on an EMPTY inventory as well, where
    nothing is known about the geometry (an offline render), and so refused every
    numbered cell of every row. A known inventory that lacks the name refuses; an
    empty one keeps the behaviour from before the refusal: the token selects
    nothing and the caller decides.

    The decision of 2026-10-12 bounds the refusal to a token cited ALONE (a matrix
    cell, a bare families word, a one-word list or group). A MEMBER of a longer
    list, of a group or of an alias selects its exact name only and is never
    refused for lacking it: FR-320 warns and plans READY, and the alias decision of
    2026-09-09 ignores a member the file lacks.
    """

    @staticmethod
    @pytest.mark.parametrize("route", _INTEGFIX_STRICT_BOUNDARY__ALONE)
    def test_p0400_strict_boundary_known_inventory_refuses(route):
        """P0400-STRICT-BOUNDARY (PFS-2029.25): a known inventory lacking Blade1 refuses it."""
        with pytest.raises(
            _IntegfixStrictBoundaryCampaignConfigError, match=r"Blade1.*Blade2.*Blade3"
        ):
            _integfix_strict_boundary___select(route, ["Blade2", "Blade3", "Hub"])

    @staticmethod
    @pytest.mark.parametrize("route", _INTEGFIX_STRICT_BOUNDARY__ROUTES)
    def test_p0400_strict_boundary_empty_inventory_is_not_refused(route):
        """P0400-STRICT-BOUNDARY (PFS-2029.25): an empty inventory is unknown, not lacking."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = _integfix_strict_boundary___select(route, [])
        assert result == []

    @staticmethod
    def test_p0400_strict_boundary_a_position_is_not_a_numbered_name():
        """P0400-STRICT-BOUNDARY (PFS-2029.25): ``1`` is a position, never refused as a name."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert select_group_members(["1"], ["Blade1", "S", "N"]) == []

    @staticmethod
    def test_p0400_strict_boundary_a_name_under_another_case_is_that_name():
        """P0400-STRICT-BOUNDARY (PFS-2029.25): ``blade1`` over ``Blade1`` selects it, as names_of."""  # noqa: E501
        assert select_group_members(["blade1"], ["Blade1", "Hub"]) == ["Blade1"]

    @staticmethod
    @pytest.mark.parametrize("strict", [True, False])
    def test_p0400_strict_boundary_a_sector_row_list_selects_what_it_carries(strict):
        """P0400-STRICT-BOUNDARY (PFS-2029.25): six blades over a two-blade sector, no refusal.

        FR-320: a sector row lacking four blades warns and plans READY, never refuses.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert select_families(
                _INTEGFIX_STRICT_BOUNDARY__SIX_BLADES,
                _INTEGFIX_STRICT_BOUNDARY__SECTOR,
                lambda name: False,
                strict=strict,
            ) == [["Blade1", "Blade2"]]
            assert select_group_members(
                _INTEGFIX_STRICT_BOUNDARY__SIX_BLADES,
                _INTEGFIX_STRICT_BOUNDARY__SECTOR,
                strict=strict,
            ) == ["Blade1", "Blade2"]
        # FR-320 R4: the plan's warning names each lacked blade, and the refusal of
        # --ignore-missing-families false does not catch one whose family answers.
        lacked = [(None, f"Blade{number}") for number in range(3, 7)]
        assert (
            declared_names_the_geometry_lacks(
                _INTEGFIX_STRICT_BOUNDARY__SIX_BLADES, _INTEGFIX_STRICT_BOUNDARY__SECTOR, {}
            )
            == lacked
        )
        assert (
            names_no_boundary_answers(
                _INTEGFIX_STRICT_BOUNDARY__SIX_BLADES,
                _INTEGFIX_STRICT_BOUNDARY__SECTOR,
                {},
                lambda name: False,
            )
            == []
        )

    @staticmethod
    @pytest.mark.parametrize("strict", [True, False])
    def test_p0400_strict_boundary_an_alias_member_is_ignored(strict):
        """P0400-STRICT-BOUNDARY (PFS-2029.25): an alias's absent numbered member is ignored.

        The alias decision of 2026-09-09: a member the file lacks is ignored, and a
        numbered member never selects its numbered siblings, nested or not.
        """
        aliases = {"rotor": ["blades_a", "Hub"], "blades_a": _INTEGFIX_STRICT_BOUNDARY__SIX_BLADES}
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert resolve_alias("blades_a", _INTEGFIX_STRICT_BOUNDARY__SECTOR, aliases) == [
                "Blade1",
                "Blade2",
            ]
            assert select_families(
                "rotor",
                _INTEGFIX_STRICT_BOUNDARY__SECTOR,
                lambda name: False,
                aliases,
                strict=strict,
            ) == [["Blade1", "Blade2", "Hub"]]
            assert select_group_members(
                ["rotor"], _INTEGFIX_STRICT_BOUNDARY__SECTOR, aliases, strict=strict
            ) == [
                "Blade1",
                "Blade2",
                "Hub",
            ]
            assert resolve_alias("hubs", ["Hub2", "Hub3"], {"hubs": ["Hub1"]}) == []
        assert declared_names_the_geometry_lacks(
            "rotor", _INTEGFIX_STRICT_BOUNDARY__SECTOR, aliases
        ) == [("blades_a", f"Blade{number}") for number in range(3, 7)]
        assert (
            names_no_boundary_answers(
                "rotor", _INTEGFIX_STRICT_BOUNDARY__SECTOR, aliases, lambda name: False
            )
            == []
        )

    @staticmethod
    def test_p0400_strict_boundary_a_list_member_never_selects_its_siblings():
        """P0400-STRICT-BOUNDARY (PFS-2029.25): ``Hub1`` beside ``Wing`` selects Wing alone."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert select_group_members(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"]) == ["Wing"]
            assert select_families(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], bool) == [["Wing"]]
        assert declared_names_the_geometry_lacks(
            ["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], {}
        ) == [(None, "Hub1")]
        assert names_no_boundary_answers(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], {}, bool) == []


def _workspace_1_costs___write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "c001.toml"
    path.write_text(text, encoding="utf-8")
    return path


class TestWorkspace1Costs:
    """P0400-WSCOST: the per-machine cost file (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSCOST")

    @staticmethod
    @pytest.fixture(autouse=True)
    def _clear_selection():
        select_cost_file(None)
        select_hpc_profile(None)
        yield
        select_cost_file(None)
        select_hpc_profile(None)

    @staticmethod
    def test_p0400_wscost_the_cost_file_selection_ends_with_its_command(tmp_path):
        """P0400-WSCOST (PFS-2094.045): a pyfs-matrix call leaves no --cost-file behind it."""
        inputs = _workspace_1_costs___inputs(tmp_path, "c001", "c002")
        for argv in (
            ["plan", "--cost-file", "c002", "--workspace", str(tmp_path)],
            ["plan", "--workspace", str(tmp_path)],
        ):
            try:
                matrix_cli(argv)
            except SystemExit:
                pass
            with pytest.raises(
                _Workspace1CostsInputArtifactError, match="nothing says which machine"
            ):
                resolve_cost_file(inputs)

    @staticmethod
    def test_p0400_wscost_the_hpc_selection_ends_with_its_command(tmp_path):
        """P0400-WSCOST (PFS-2094.045): a second invocation inherits no --hpc."""
        try:
            matrix_cli(["plan", "--hpc", "h002", "--workspace", str(tmp_path)])
        except SystemExit:
            pass
        assert resolve_hpc_profile(tmp_path / "inputs") is None

    @staticmethod
    @pytest.mark.parametrize(
        ("value", "seconds"),
        [
            ("DISABLE", 100.0),
            ("disable", 100.0),
            ("OFF", 100.0),
            ("false", 100.0),
            ("0.0", 100.0),
            ("ENABLE", 300.0),
            (" enable ", 300.0),
            (True, 300.0),
        ],
    )
    def test_p0400_wscost_only_an_enabled_row_flag_is_priced(tmp_path, value, seconds):
        """P0400-WSCOST (PFS-2094.046): DISABLE, OFF, false or 0.0 applies no flag multiplier."""
        inputs = _workspace_1_costs___inputs(tmp_path, "c001")
        case = SimpleNamespace(solver=None, variables={"VISCOUS_COUPLING": value})
        (priced,) = priced_rows([_workspace_1_costs___row()], {"r1": case}, inputs)
        assert priced.seconds == seconds

    @staticmethod
    @pytest.mark.parametrize(
        ("old", "new", "named"),
        [
            ("mesh_faces = 1000", "mesh_faces = 0", "[reference] mesh_faces"),
            ("steps = 10", "steps = 0", "[reference] steps"),
            ("steps = 10", 'steps = "10"', "[reference] steps"),
            ("wall_time_s = 100.0", "wall_time_s = -1.0", "[reference] wall_time_s"),
            ("ncpus = 4\n", "ncpus = 0\n", "[reference] ncpus"),
            ("speedup = [1.0, 2.0, 6.0]", 'speedup = ["1", "2", "6"]', "speedup entry"),
            ("ncpus = [2, 4, 8]", 'ncpus = ["a", 4, 8]', "[parallel] ncpus"),
            ("speedup = [1.0, 2.0, 6.0]", "speedup = [1.0, 2.0, nan]", "speedup entry"),
            ("ncpus = [2, 4, 8]", "ncpus = [true, 4, 8]", "[parallel] ncpus"),
        ],
    )
    def test_p0400_wscost_a_malformed_reference_or_curve_is_refused_by_name(
        tmp_path, old, new, named
    ):
        """P0400-WSCOST (PFS-2097.019): a zero, text or nan figure is refused naming [table] key."""
        assert old in _WORKSPACE_1_COSTS___FILE
        path = _workspace_1_costs___write(tmp_path, _WORKSPACE_1_COSTS___FILE.replace(old, new, 1))
        with pytest.raises(_Workspace1CostsInputArtifactError, match=re.escape(named)):
            read_cost_file(path)


def _workspace_1_degenerate___rows(result):
    return _workspace_1_degenerate___read_obj(result.mesh).reshape(
        result.stations, CHORD_PANELS + 1, 3
    )


#: The half thickness of the blunt trailing edge's base, a fraction of the chord.
_WORKSPACE_1_DEGENERATE__BASE = 0.01


def _workspace_1_degenerate___blunt_blade():
    """The oracle blade with an open trailing edge closed by a straight base."""
    x = _workspace_1_degenerate___stations()
    inner = x[1:]
    half = _workspace_1_degenerate___half_thickness(inner) + _WORKSPACE_1_DEGENERATE__BASE * inner
    upper = numpy.column_stack([inner, _workspace_1_degenerate___camber(inner) + half])
    lower = numpy.column_stack([inner, _workspace_1_degenerate___camber(inner) - half])
    section = numpy.vstack([[0.0, 0.0], upper, lower[::-1]])
    n = len(section)
    vertices = [
        [(px - 0.25) * _WORKSPACE_1_DEGENERATE__CHORD, py * _WORKSPACE_1_DEGENERATE__CHORD, z]
        for z in numpy.linspace(
            _WORKSPACE_1_DEGENERATE__ROOT,
            _WORKSPACE_1_DEGENERATE__TIP,
            _WORKSPACE_1_DEGENERATE__RINGS,
        )
        for px, py in section
    ]
    faces = []
    for k in range(_WORKSPACE_1_DEGENERATE__RINGS - 1):
        for j in range(n):
            a, b = k * n + j, k * n + (j + 1) % n
            faces += [[a, b, b + n], [a, b + n, a + n]]
    for k, z in (
        (0, _WORKSPACE_1_DEGENERATE__ROOT),
        (_WORKSPACE_1_DEGENERATE__RINGS - 1, _WORKSPACE_1_DEGENERATE__TIP),
    ):
        centre = len(vertices)
        vertices.append([*(section.mean(axis=0) - [0.25, 0.0]) * _WORKSPACE_1_DEGENERATE__CHORD, z])
        faces += [[centre, k * n + (j + 1) % n, k * n + j] for j in range(n)]
    return numpy.asarray(vertices), faces


def _workspace_1_degenerate___two_bodies(tmp_path):
    vertices, faces = _workspace_1_degenerate___blade()
    source = _workspace_1_degenerate___write_obj(
        tmp_path / "rotor.obj", vertices, faces, group="Blade"
    )
    spinner = [[0.0, 0.0, 0.0], [0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 0.05]]
    first = len(vertices) + 1
    lines = ["o Spinner", *(f"v {x!r} {y!r} {z!r}" for x, y, z in spinner)]
    lines += [
        f"f {first + a} {first + b} {first + c}"
        for a, b, c in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
    ]
    with source.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    inventory_sidecar(source).write_text(
        'boundaries = ["Blade", "Spinner"]\n\n[import]\nunits = "meter"\n\n'
        '[[import.operations]]\nop = "rename"\nsurface = "Spinner"\nto = "Hub"\n\n'
        '[[import.operations]]\nop = "mirror"\nsurface = "Hub"\nplane = "XZ"\n\n'
        '[[import.operations]]\nop = "rename"\nsurface = "Blade"\nto = "Blade1"\n\n'
        '[[import.operations]]\nop = "mirror"\nsurface = "Blade1"\nplane = "XZ"\n\n'
        '[[import.operations]]\nop = "translate"\nvector = [0, 0, 1]\n',
        encoding="utf-8",
    )
    return source


class TestWorkspace1Degenerate:
    """P0400-WSTHIN: the thin blade's rows, its blunt trailing edge and its operations.

    0.40.0 lane workspace-1. Each test is the regression of one planning node and
    fails on the code before its fix. The blade is the built oracle of
    ``test_p0340_thin_blade``: a cambered section whose mean surface is known.
    """

    pytestmark = pytest.mark.requirement("P0400-WSTHIN")

    @staticmethod
    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_p0400_wsthin_every_row_runs_from_the_leading_edge_whatever_the_face_order(
        tmp_path, seed
    ):
        """P0400-WSTHIN (PFS-2099.001): shuffled faces leave rows[k, 0] at the leading edge."""
        vertices, faces = _workspace_1_degenerate___blade()
        shuffled = [faces[i] for i in numpy.random.default_rng(seed).permutation(len(faces))]
        result = derive_thin_blade(
            _workspace_1_degenerate___write_obj(tmp_path / "blade.obj", vertices, shuffled),
            root_offset=0.05,
        )
        xi = _workspace_1_degenerate___rows(result)[:, :, 0] / _WORKSPACE_1_DEGENERATE__CHORD + 0.25
        assert numpy.abs(xi[:, 0]).max() <= 1e-9, xi[:, 0]
        assert numpy.abs(xi[:, -1] - 1.0).max() <= 1e-9, xi[:, -1]

    @staticmethod
    def test_p0400_wsthin_a_blunt_trailing_edge_ends_at_its_base_midpoint(tmp_path):
        """P0400-WSTHIN (PFS-2099.002): the sheet's trailing edge is the base's midpoint."""
        assert len(_workspace_1_degenerate___stations()) == _WORKSPACE_1_DEGENERATE__SIDE_POINTS + 1
        vertices, faces = _workspace_1_degenerate___blunt_blade()
        result = derive_thin_blade(
            _workspace_1_degenerate___write_obj(tmp_path / "blunt.obj", vertices, faces),
            root_offset=0.05,
        )
        rows = _workspace_1_degenerate___rows(result)
        trailing = rows[:, -1]
        assert numpy.abs(trailing[:, 0] - 0.75 * _WORKSPACE_1_DEGENERATE__CHORD).max() <= 1e-9
        assert (
            numpy.abs(
                trailing[:, 1]
                - _WORKSPACE_1_DEGENERATE__CHORD
                * _workspace_1_degenerate___camber(numpy.array(1.0))
            ).max()
            <= 1e-9
        )
        leading = rows[:, 0]
        assert numpy.abs(leading[:, 0] + 0.25 * _WORKSPACE_1_DEGENERATE__CHORD).max() <= 1e-9

    @staticmethod
    def test_p0400_wsthin_a_sharp_trailing_edge_is_not_read_as_a_base(tmp_path):
        """P0400-WSTHIN (PFS-2099.002): the control, the closed oracle keeps its own edges."""
        vertices, faces = _workspace_1_degenerate___blade()
        source = _workspace_1_degenerate___write_obj(tmp_path / "sharp.obj", vertices, faces)
        rows = _workspace_1_degenerate___rows(derive_thin_blade(source, root_offset=0.05))
        xi = rows[:, :, 0] / _WORKSPACE_1_DEGENERATE__CHORD + 0.25
        assert numpy.abs(xi[:, 0]).max() <= 1e-9 and numpy.abs(xi[:, -1] - 1.0).max() <= 1e-9

    @staticmethod
    def test_p0400_wsthin_a_thin_blade_keeps_only_the_operations_on_itself(tmp_path):
        """P0400-WSTHIN (PFS-2099.003, PFS-2099.013): every carried operation names a surface
        the thin blade holds at its step, as the plan resolves them, and the rest are named."""
        result = derive_thin_blade(
            _workspace_1_degenerate___two_bodies(tmp_path), root_offset=0.05, boundary="Blade"
        )
        carried = read_mesh_import(result.sidecar)
        assert carried is not None
        names = list(read_inventory(result.sidecar))
        for operation in carried.operations:
            assert operation.surface == "all" or operation.surface in names, (operation, names)
            if operation.op == "rename":
                names = [operation.to if name == operation.surface else name for name in names]
        assert [(op.op, op.surface) for op in carried.operations] == [
            ("rename", "Blade"),
            ("mirror", "Blade1"),
            ("translate", "all"),
        ]
        case = _workspace_1_degenerate__steady_case().model_copy(
            update={
                "geometry": str(result.mesh),
                "mesh_import": carried,
                "inventory": tuple(read_inventory(result.sidecar)),
                "inventory_source": "sidecar",
                "raw_mesh_conditions": RawMeshConditions(
                    trailing_edges=TrailingEdgeMarking(route="detect")
                ),
            }
        )
        steps, final_names = _plan_import_operations(case, Script("26.124"), str(result.sidecar))
        assert len(steps) == 3 and final_names == ("Blade1",)
        script = Script("26.124")
        build_script(case, script)
        assert "START_SOLVER" in script.render() and "Spinner" not in script.render()
        text = result.sidecar.read_text(encoding="utf-8")
        assert "operation 1 (rename of 'Spinner')" in text
        assert "operation 2 (mirror of 'Hub')" in text


class TestWorkspace1GeometryClean:
    """P0400-WSCLEAN: a geometry clean whose write is refused (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSCLEAN")

    @staticmethod
    def test_p0400_wsclean_a_held_file_is_a_refusal_and_leaves_no_temporary(tmp_path, monkeypatch):
        """P0400-WSCLEAN (PFS-2099.012): a refused replace names the file and leaves no .tmp."""
        target = tmp_path / "10_WING.fsm"
        target.write_bytes(
            _workspace_1_geometry_clean___dirty(
                _workspace_1_geometry_clean___text(
                    _WORKSPACE_1_GEOMETRY_CLEAN__TIER3 / "10_WING.fsm"
                )
            ).encode("latin-1")
        )
        before = target.read_bytes()
        real = os.replace

        def held(source, destination, *args, **kwargs):
            if Path(destination) == target:
                raise PermissionError(13, "The process cannot access the file", str(target))
            return real(source, destination, *args, **kwargs)

        monkeypatch.setattr(os, "replace", held)
        with pytest.raises(_Workspace1GeometryCleanInputArtifactError, match="10_WING.fsm"):
            clean_saved_actions(target, stamp="20261012-000000")
        assert target.read_bytes() == before
        assert not list(tmp_path.glob("*.tmp"))

    @staticmethod
    def test_p0400_wsclean_a_refused_cleanup_is_named_in_the_same_error_class(
        tmp_path, monkeypatch
    ):
        """P0400-WSCLEAN (PFS-2099.012): a held temporary file never leaks a raw OSError."""
        target = tmp_path / "10_WING.fsm"
        target.write_bytes(
            _workspace_1_geometry_clean___dirty(
                _workspace_1_geometry_clean___text(
                    _WORKSPACE_1_GEOMETRY_CLEAN__TIER3 / "10_WING.fsm"
                )
            ).encode("latin-1")
        )
        before = target.read_bytes()
        real_unlink = Path.unlink

        def held_replace(source, destination, *args, **kwargs):
            raise PermissionError("geometry held")

        def held_unlink(path, *args, **kwargs):
            if path.name.endswith(".tmp"):
                raise PermissionError("temporary held")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "replace", held_replace)
        monkeypatch.setattr(Path, "unlink", held_unlink)
        with pytest.raises(
            _Workspace1GeometryCleanInputArtifactError, match="temporary file.*could not be removed"
        ):
            clean_saved_actions(target, stamp="20261012-000000")
        assert target.read_bytes() == before


def _workspace_1_init___geometry(workspace: CampaignWorkspace, folder: str, name: str) -> Path:
    path = workspace.inputs_dir / "geometries" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake simulation " + name.encode())
    return path


def _workspace_1_init___refuse_removal(monkeypatch, inputs: Path) -> None:
    for name in ("rmdir", "unlink"):
        real = getattr(os, name)

        def held(path, *args, _real=real, **kwargs):
            if Path(path) == inputs:
                raise PermissionError(5, "Access is denied", str(path))
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(os, name, held)


class TestWorkspace1Init:
    """P0400-WSINIT: staging, collection and archiving of `CampaignWorkspace` (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("P0400-WSINIT")

    @staticmethod
    def test_p0400_wsinit_a_dangling_inputs_link_is_replaced_by_the_next_staging(tmp_path):
        """P0400-WSINIT (PFS-2095.056): the staged link's target is gone; staging again relinks."""
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        wing = _workspace_1_init___geometry(workspace, "wing", "wing.fsm")
        workspace.stage_inputs("9001", [wing])
        inputs = workspace.sim_dir("9001") / "inputs"
        assert _is_link(inputs)
        shutil.rmtree(wing.parent)
        tail = _workspace_1_init___geometry(workspace, "tail", "tail.fsm")
        workspace.stage_inputs("9001", [tail])
        assert _is_link(inputs) and (inputs / "tail.fsm").is_file()
        assert workspace.staged_as("9001") == ("link", None)

    @staticmethod
    def test_p0400_wsinit_create_sim_keeps_a_dangling_inputs_link(tmp_path):
        """P0400-WSINIT (PFS-2095.056): a script is written into a simulation with a dangling link."""  # noqa: E501
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        wing = _workspace_1_init___geometry(workspace, "wing", "wing.fsm")
        workspace.stage_inputs("9001", [wing])
        shutil.rmtree(wing.parent)
        workspace.write_script("9001", "point.txt", "START_SOLVER\n")
        assert (workspace.sim_dir("9001") / "scripts" / "point.txt").is_file()

    @staticmethod
    def test_p0400_wsinit_a_link_that_cannot_be_retargeted_is_a_reason_and_copies_nothing(
        tmp_path, monkeypatch
    ):
        """P0400-WSINIT (PFS-2095.062): a refused removal of a link to another geometry is named."""
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        wing = _workspace_1_init___geometry(workspace, "wing", "wing.fsm")
        workspace.stage_inputs("9001", [wing])
        tail = _workspace_1_init___geometry(workspace, "tail", "tail.fsm")
        inputs = workspace.sim_dir("9001") / "inputs"
        _workspace_1_init___refuse_removal(monkeypatch, inputs)
        mode, reason = workspace._link_inputs(inputs, [tail])
        assert mode == "copy" and "Access is denied" in str(reason), (mode, reason)
        with pytest.raises(WorkspaceError, match="no input was copied"):
            workspace.stage_inputs("9001", [tail])
        assert not (wing.parent / "tail.fsm").exists()

    @staticmethod
    def test_p0400_wsinit_a_link_that_cannot_be_removed_for_copies_is_a_reason(
        tmp_path, monkeypatch
    ):
        """P0400-WSINIT (PFS-2095.062): sources outside the library and a refused removal are named."""  # noqa: E501
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        wing = _workspace_1_init___geometry(workspace, "wing", "wing.fsm")
        workspace.stage_inputs("9001", [wing])
        outside = tmp_path / "outside.fsm"
        outside.write_bytes(b"outside")
        inputs = workspace.sim_dir("9001") / "inputs"
        _workspace_1_init___refuse_removal(monkeypatch, inputs)
        mode, reason = workspace._link_inputs(inputs, [outside])
        assert mode == "copy" and "Access is denied" in str(reason), (mode, reason)
        with pytest.raises(WorkspaceError, match="no input was copied"):
            workspace.stage_inputs("9001", [outside])
        assert not (wing.parent / "outside.fsm").exists()

    @staticmethod
    def test_p0400_wsinit_recreating_inputs_after_link_removal_has_a_copy_fallback(
        tmp_path, monkeypatch
    ):
        """P0400-WSINIT (PFS-2095.062): mkdir after a removed link returns the copy reason."""
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        wing = _workspace_1_init___geometry(workspace, "wing", "wing.fsm")
        workspace.stage_inputs("9001", [wing])
        outside = tmp_path / "outside.fsm"
        outside.write_bytes(b"outside")
        inputs = workspace.sim_dir("9001") / "inputs"
        real = Path.mkdir

        def held(path, *args, **kwargs):
            if path == inputs:
                raise PermissionError("cannot recreate inputs")
            return real(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", held)
        mode, reason = workspace._link_inputs(inputs, [outside])
        assert mode == "copy" and "cannot recreate inputs" in reason

    @staticmethod
    def test_p0400_wsinit_collect_names_moves_and_records_by_collection_name(tmp_path, monkeypatch):
        """P0400-WSINIT (PFS-2094.042): the held check, the move and the record take one rule."""
        workspace = CampaignWorkspace(tmp_path / "camp")
        produced = tmp_path / "loads.txt"
        produced.write_text("x", encoding="utf-8")
        rule = workspace_module.collection_name
        monkeypatch.setattr(workspace_module, "collection_name", lambda path: "ruled_" + rule(path))
        collected = workspace.collect_outputs("9001", [produced], datapoint=PointName("AL+000"))
        assert collected == ["datapoints/DP-AL+000/ruled_loads.txt"]
        folder = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
        assert (folder / "ruled_loads.txt").is_file()
        produced.write_text("y", encoding="utf-8")
        with pytest.raises(WorkspaceError, match="cannot collect ruled_loads.txt"):
            workspace.collect_outputs("9001", [produced], datapoint=PointName("AL+000"))

    @staticmethod
    def test_p0400_wsinit_a_failed_archive_leaves_no_fragment_and_a_retry_succeeds(
        tmp_path, monkeypatch
    ):
        """P0400-WSINIT (PFS-2096.010): a write that fails leaves no zip, and the retry archives."""
        workspace = CampaignWorkspace(tmp_path)
        workspace.write_script("9001", "point.txt", "START_SOLVER\n")
        workspace.write_script("9001", "other.txt", "START_SOLVER\n")
        workspace.append_record(_workspace_1_init__make_record())
        real_write = zipfile.ZipFile.write
        calls = {"n": 0}

        def failing(self, filename, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise PermissionError(13, "held by another process", str(filename))
            return real_write(self, filename, *args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "write", failing)
        with pytest.raises(WorkspaceError, match="No archive was written"):
            workspace.archive_sim("9001")
        assert list((tmp_path / "archive").iterdir()) == []
        assert (tmp_path / "sims" / "sim_9001" / "scripts" / "point.txt").is_file()
        monkeypatch.setattr(zipfile.ZipFile, "write", real_write)
        bundle = workspace.archive_sim("9001")
        with zipfile.ZipFile(bundle) as archive:
            assert "scripts/point.txt" in archive.namelist()


class TestWorkspace1Inputs:
    """P0400-WSINPUTS: the reference artifact's lifted tables (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSINPUTS")

    @staticmethod
    @pytest.mark.parametrize(
        ("text", "named"),
        [
            ('[frames]\nname = "F1"\norigin = [0.0, 0.0, 0.0]\n', r"\[\[frames\]\] once per frame"),
            ('aliases = ["a"]\n', r"\[aliases\] with \['a'\] not a list"),
            ('[aliases]\nlifters = "Wing"\n', r"\[aliases\] with lifters not a list"),
        ],
        ids=["frames-single-brackets", "aliases-a-list", "alias-not-a-list"],
    )
    def test_p0400_wsinputs_a_malformed_frames_or_aliases_table_is_refused(tmp_path, text, named):
        """P0400-WSINPUTS (PFS-2095.058): the reference refuses the shape, as the setup preset does."""  # noqa: E501
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        (workspace.inputs_dir / "references" / "r001.toml").write_text(text, encoding="utf-8")
        with pytest.raises(_Workspace1InputsInputArtifactError, match=named):
            workspace.resolve_reference("r001")


_WORKSPACE_1_TRAILING_EDGES__AXIS, _WORKSPACE_1_TRAILING_EDGES__HUB = (
    (0.0, 0.0, 1.0),
    (0.0, 0.0, 0.0),
)


class TestWorkspace1TrailingEdges:
    """P0400-WSTE: trailing-edge extraction takes any integer section count (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """  # noqa: E501

    pytestmark = pytest.mark.requirement("P0400-WSTE")

    @staticmethod
    @pytest.mark.parametrize("count", [numpy.int64(8), numpy.int32(8), 8])
    def test_p0400_wste_a_numpy_integer_section_count_is_an_integer(tmp_path, count):
        """P0400-WSTE (PFS-2095.061): numpy.int64(8) sections the span as 8 does."""
        path, _, _ = _workspace_1_trailing_edges___blade_file(tmp_path)
        edge = extract_trailing_edge(
            path,
            axis=_WORKSPACE_1_TRAILING_EDGES__AXIS,
            hub=_WORKSPACE_1_TRAILING_EDGES__HUB,
            sections=count,
        )
        assert edge.nodes.shape == (8, 3)

    @staticmethod
    @pytest.mark.parametrize("count", [True, numpy.bool_(True), 8.0, 1])
    def test_p0400_wste_a_boolean_float_or_single_count_is_still_refused(tmp_path, count):
        """P0400-WSTE (PFS-2095.061): the bool exclusion and the two-or-more floor stay."""
        path, _, _ = _workspace_1_trailing_edges___blade_file(tmp_path)
        with pytest.raises(_Workspace1TrailingEdgesInputArtifactError, match="chordwise sections"):
            extract_trailing_edge(
                path,
                axis=_WORKSPACE_1_TRAILING_EDGES__AXIS,
                hub=_WORKSPACE_1_TRAILING_EDGES__HUB,
                sections=count,
            )


class TestWorkspace2Builds:
    """P0400-BUILDS: a refusal about a build entry names the file the entry came from."""

    @staticmethod
    def test_p0400_builds_a_bad_overlay_version_names_the_overlay(tmp_path):
        """P0400-BUILDS (PFS-2100.007): an unknown version in the local overlay is refused naming
        executables.local.toml, the file the user has to edit, not the committed registry."""
        (tmp_path / "executables.toml").write_text(
            '"26.123" = { path = "C:/placeholder/FlightStream.exe", version = "26.123" }\n',
            encoding="utf-8",
        )
        (tmp_path / "executables.local.toml").write_text(
            '"26.123" = { path = "C:/fs/FlightStream.exe", version = "99.999" }\n', encoding="utf-8"
        )
        with pytest.raises(_Workspace2BuildsInputArtifactError) as caught:
            resolve_build(tmp_path, "26.123")
        message = str(caught.value)
        assert "'99.999'" in message, message
        assert "executables.local.toml declares" in message, message


class TestWorkspace2Costs:
    """P0400-COSTFILE: a cost file's reference values and curve entries are checked when it is read."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        ("old", "new", "named"),
        [
            ("mesh_faces = 1000", "mesh_faces = 0", "mesh_faces to be a positive number"),
            ("wall_time_s = 100.0", "wall_time_s = -1.0", "wall_time_s to be a positive number"),
            ("ncpus = 4\n", "ncpus = 0\n", "ncpus to be a positive number"),
            ("steps = 10", "steps = 0", "steps to be a positive number"),
            ("steps = 10", 'steps = "10"', "steps to be a positive number"),
            ("ncpus = [2, 4, 8]", 'ncpus = [2, "4", 8]', "entry to be a number"),
            ("speedup = [1.0, 2.0, 6.0]", 'speedup = [1.0, "2", 6.0]', "entry to be a number"),
        ],
    )
    def test_p0400_costfile_a_bad_reference_or_curve_entry_is_refused_by_name(
        tmp_path, old, new, named
    ):
        """P0400-COSTFILE (PFS-2097.012): a zero or negative reference value, a string steps and a
        non-number curve entry are InputArtifactError naming the key, never a ZeroDivisionError,
        ValueError or TypeError later in estimate_seconds."""
        assert old in _WORKSPACE_2_COSTS___FILE
        path = tmp_path / "c001.toml"
        path.write_text(_WORKSPACE_2_COSTS___FILE.replace(old, new, 1), encoding="utf-8")
        with pytest.raises(_Workspace2CostsInputArtifactError, match=named):
            read_cost_file(path)


_WORKSPACE_2_FIELDS___CHECK = """
from pyflightstream.workspace.fields import Field, subtract_fields
total = Field("UNSTRUCTURED", ((0.0, 0, 0, 1.0, 0, 0), (1.8e-6, 0, 0, 2.0, 0, 0)))
other = Field("UNSTRUCTURED", ((0.9e-6, 0, 0, 10.0, 0, 0), (2.7e-6, 0, 0, 20.0, 0, 0)))
rows = subtract_fields(total, other, reference_m_s=(0.0, 0.0, 0.0), tolerance_m=1e-6).rows
print([row[3] for row in rows])
"""


class TestWorkspace2Fields:
    """P0400-SUBTRACTMATCH: subtract_fields pairs the two grids one to one, never by an assert."""

    @staticmethod
    def test_p0400_subtractmatch_a_point_near_two_takes_the_one_left():
        """P0400-SUBTRACTMATCH (PFS-2086.001): total x = [0, 1.8e-6] and other x = [0.9e-6, 2.7e-6]
        at 1e-6 m pair 0-0 and 1-1 (the only pairing), where the first-candidate rule paired both
        with other's first point and raised a bare AssertionError."""
        total = Field("UNSTRUCTURED", ((0.0, 0, 0, 1.0, 0, 0), (1.8e-6, 0, 0, 2.0, 0, 0)))
        other = Field("UNSTRUCTURED", ((0.9e-6, 0, 0, 10.0, 0, 0), (2.7e-6, 0, 0, 20.0, 0, 0)))
        rows = subtract_fields(total, other, reference_m_s=(0.0, 0.0, 0.0), tolerance_m=1e-6).rows
        assert [row[3] for row in rows] == [-9.0, -18.0]

    @staticmethod
    def test_p0400_subtractmatch_the_same_outcome_under_python_o():
        """P0400-SUBTRACTMATCH (PFS-2086.001): under python -O, where an assert does not run, the
        pairing is the same and no row is subtracted from the wrong partner."""
        src = Path(__file__).resolve().parents[2] / "src"
        done = subprocess.run(
            [
                sys.executable,
                "-O",
                "-c",
                f"import sys; sys.path.insert(0, {str(src)!r})\n{_WORKSPACE_2_FIELDS___CHECK}",
            ],
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        assert done.stdout.strip() == "[-9.0, -18.0]", done.stdout + done.stderr


def _workspace_2_hpc___profile(tmp_path: Path, text: str, stem: str = "h001") -> Path:
    directory = tmp_path / "hpc"
    directory.mkdir(exist_ok=True)
    path = directory / f"{stem}.toml"
    path.write_text(text, encoding="utf-8")
    return path


class TestWorkspace2Hpc:
    """P0400-HPCPROFILE: an HPC profile's tables and booleans are typed; its selector is a stem."""

    @staticmethod
    @pytest.fixture(autouse=True)
    def _clear_selection():
        select_hpc_profile(None)
        select_cost_file(None)
        yield
        select_hpc_profile(None)
        select_cost_file(None)

    @staticmethod
    def test_p0400_hpcprofile_a_quoted_export_log_is_refused(tmp_path):
        """P0400-HPCPROFILE (PFS-2094.023, PFS-2095.032): export_log = "false" is refused as not
        a TOML boolean, where bool("false") kept EXPORT_LOG in the script."""
        path = _workspace_2_hpc___profile(
            tmp_path,
            _WORKSPACE_2_HPC__PROFILE + '\n[log]\nexport_log = "false"\nnative_log = "x.log"\n',
        )
        with pytest.raises(_Workspace2HpcInputArtifactError, match="true or false, unquoted"):
            read_hpc_profile(path)

    @staticmethod
    @pytest.mark.parametrize(
        ("old", "new", "table"),
        [
            ('[submit]\ncommand = ["esub", "{descriptor_path}"]\n', "", "submit"),
            ("[descriptor]\n", "", "descriptor"),
        ],
    )
    def test_p0400_hpcprofile_a_table_stated_as_a_value_is_refused_by_name(
        tmp_path, old, new, table
    ):
        """P0400-HPCPROFILE (PFS-2095.032): a top-level submit = [...] or descriptor = "..." is an
        InputArtifactError naming the profile and the table, never an AttributeError."""
        assert old in _WORKSPACE_2_HPC__PROFILE
        stated = '["esub", "{descriptor_path}"]' if table == "submit" else '"yaml"'
        text = f"{table} = {stated}\n" + _WORKSPACE_2_HPC__PROFILE.replace(old, new)
        if table == "descriptor":
            text = text.replace("[descriptor.fields]", "[fields_elsewhere]")
        path = _workspace_2_hpc___profile(tmp_path, text)
        with pytest.raises(_Workspace2HpcInputArtifactError) as caught:
            read_hpc_profile(path)
        message = str(caught.value)
        assert f"{table} entry that is not a table" in message and str(path) in message, message

    @staticmethod
    def test_p0400_hpcprofile_the_selector_takes_the_stem_of_a_named_file(tmp_path):
        """P0400-HPCPROFILE (PFS-2089.005): --hpc h002.toml selects h002, as --cost-file c002.toml
        selects c002."""
        _workspace_2_hpc___profile(tmp_path, _WORKSPACE_2_HPC__PROFILE, "h001")
        _workspace_2_hpc___profile(tmp_path, _WORKSPACE_2_HPC__PROFILE, "h002")
        select_hpc_profile("h002.toml")
        profile = resolve_hpc_profile(tmp_path)
        assert profile is not None and profile.path.name == "h002.toml"

    @staticmethod
    @pytest.mark.parametrize("table", ["descriptor", "submit", "defaults", "log"])
    @pytest.mark.parametrize("value", ['""', "false", "[]", "0"])
    def test_p0400_hpcprofile_an_empty_value_is_still_not_a_table(tmp_path, table, value):
        """P0400-HPCPROFILE (PFS-2095.032): falsey values cannot stand in for tables."""
        # Replace exactly one table without moving its fields into another table.
        path = _workspace_2_hpc___profile(tmp_path, _WORKSPACE_2_HPC__PROFILE)
        lines = [f"{table} = {value}", 'application_id = "solver"']
        if table != "descriptor":
            lines += ["[descriptor.fields]", 'job = "{sim}"']
        if table != "submit":
            lines += ["[submit]", 'command = ["esub", "{descriptor_path}"]']
        path.write_text(chr(10).join(lines), encoding="utf-8")
        with pytest.raises(
            _Workspace2HpcInputArtifactError, match=f"{table} entry that is not a table"
        ):
            read_hpc_profile(path)


class TestWorkspace2Inputs:
    """P0400-ROTORINPUTS: rotor input refusals name a remedy that works, and aliases fold case."""

    @staticmethod
    def test_p0400_rotorinputs_the_retired_facts_refusal_names_rpm_sign():
        """P0400-ROTORINPUTS (PFS-2100.020): the remedy names rpm_sign on the reference's rotor
        block and RPM as a magnitude, not the sign of RPM, which a row is refused for."""
        with pytest.raises(ValidationError) as caught:
            RotorReference.model_validate({"n_blades": 3, "rotation": "cw"})
        message = " ".join(str(caught.value).split())
        assert "rpm_sign on a rotor block of the reference" in message, message
        assert "RPM is a magnitude" in message, message
        assert "sign of RPM" not in message, message

    @staticmethod
    def test_p0400_rotorinputs_a_group_in_another_case_is_the_rotors_and_is_checked():
        """P0400-ROTORINPUTS (PFS-2104.049): a declared `pusher` for rotor PUSHER is checked against
        the rotor's families and no second group `PUSHER` is added."""
        rotors = {"PUSHER": SimpleNamespace(members=["B1", "B2"])}
        agreed = rotor_integration_groups(rotors, {"pusher": ["b1", "b2"]})
        assert agreed == {"pusher": ["b1", "b2"]}
        with pytest.raises(_Workspace2InputsCampaignConfigError, match="'pusher'"):
            rotor_integration_groups(rotors, {"pusher": ["WING"]})


class TestWorkspace2Review:
    """P0400-REVIEW: acceptance gaps exercised through their consumers."""

    @staticmethod
    @pytest.mark.parametrize("selector", ["hpc", "cost"])
    def test_p0400_review_cli_selection_is_restored(tmp_path, monkeypatch, selector):
        from pyflightstream.run import cli

        hpc.select_hpc_profile(None)
        costs.select_cost_file(None)
        observed = []
        monkeypatch.setattr(cli, "resolve_matrix_arguments", lambda args: None)
        monkeypatch.setattr(
            cli,
            "_cmd_plan",
            lambda *args: (
                observed.append((hpc._SELECTED_HPC.get(), costs._SELECTED_COST_FILE.get())) or 0
            ),
        )
        flag, name = ("--hpc", "h002") if selector == "hpc" else ("--cost-file", "c002")
        try:
            args = ["plan", "batch.fs", "--workspace", str(tmp_path)]
            assert cli.main([*args, flag, name]) == 0
            assert cli.main(args) == 0
            assert observed[0] == ((name, None) if selector == "hpc" else (None, name))
            assert observed[1] == (None, None)
        finally:
            hpc.select_hpc_profile(None)
            costs.select_cost_file(None)

    @staticmethod
    @pytest.mark.parametrize("reader", ["artifact", "reference_points"])
    def test_p0400_review_toml_encoding_refusal_names_file(tmp_path, reader):
        from pyflightstream.workspace.sidecars import load_toml

        path = tmp_path / "inputs" / "reference_points.toml"
        path.parent.mkdir()
        path.write_bytes(b"# " + bytes([233]))
        with pytest.raises(_Workspace2ReviewInputArtifactError, match="UTF-8") as caught:
            if reader == "artifact":
                load_toml(path, "reference")
            else:
                CampaignWorkspace(tmp_path).reference_points()
        assert str(path) in str(caught.value)

    @staticmethod
    def test_p0400_review_detected_points_require_mesh_units(tmp_path):
        mesh = _workspace_2_review__wing()
        mesh = _Workspace2ReviewComposite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
        src = _workspace_2_review__write_source(tmp_path / "src", "wing", mesh)
        src.with_suffix(".boundaries.toml").write_text(
            '[trailing_edges]\ndetect = { surfaces = ["U"] }\n', encoding="utf-8"
        )
        with pytest.raises(_Workspace2ReviewInputArtifactError, match=r"\[import\].*units"):
            refine_mesh(src, spanwise=2, families=["U"], keep_first_row=["U"])

    @staticmethod
    def test_p0400_review_remesh_does_not_invent_trailing_edges(tmp_path):
        points = numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
        te = numpy.array([[0.5, 0, 0], [0.5, 1, 0]])
        mesh = _Workspace2ReviewComposite(points, {"A": [[0, 1, 2, 3]]}, te, {})
        src = _workspace_2_review__write_source(
            tmp_path / "src",
            "plate",
            mesh,
            refine_toml='[families.A]\nfactor = 1\nmethod = "remesh"\n',
        )
        level = refine_mesh(src)
        _, actual = read_te(level.obj.with_suffix(".te.txt"))
        assert len(actual) == 2
        assert sorted(actual.tolist()) == sorted(te.tolist())

    @staticmethod
    def test_p0400_review_grid_does_not_fill_a_wake_gap(tmp_path):
        mesh = _workspace_2_review__wing(root=False)
        mesh = _Workspace2ReviewComposite(mesh.verts, mesh.families, mesh.te[[0, 2, 3]], {})
        src = _workspace_2_review__write_source(tmp_path / "src", "wing", mesh)
        level = refine_mesh(src, 1, families=["U"])
        _, actual = read_te(level.obj.with_suffix(".te.txt"))
        assert len(actual) == len(mesh.te)
        assert sorted(actual.tolist()) == sorted(mesh.te.tolist())

    @staticmethod
    @pytest.mark.parametrize("unit", ["MILLIMETER", None])
    def test_p0400_review_shared_target_has_honest_units(tmp_path, unit):
        """P0400-SHARED-UNITS (FR-432 R3): metres only when import units convert to metres."""
        mesh = _workspace_2_review__sheet_with_strips(
            (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),)
        )
        src = _workspace_2_review__write_source(tmp_path / "src", "wing", mesh)
        side = src.with_suffix(".boundaries.toml")
        text = side.read_text("utf-8")
        if unit is not None:
            text += f'\n[import]\nunits = "{unit}"\n'
        side.write_text(text, "utf-8")
        # Keep the points in the mesh's units as well.
        te = src.with_suffix(".te.txt")
        te.write_text(te.read_text("utf-8").replace("METER", unit or "METER"), "utf-8")
        level = refine_mesh(src, 2, families=["G"])
        entry = level.report["T"]
        if unit is None:
            assert "shared_edge_target_m" not in entry
            assert entry["shared_edge_target_mesh_units"]["max"] > 0
        else:
            assert entry["shared_edge_target_m"]["max"] < 0.001

    @staticmethod
    @pytest.mark.parametrize("angle", [0, 90, 180])
    @pytest.mark.parametrize("hand", [-1, 1])
    def test_p0400_review_trailing_edge_follows_family_orientation(tmp_path, angle, hand):
        """P0400-TE-ORIENTATION (FR-430): the sharp trailing edge follows the family direction."""
        from tests.tier1_offline.test_p0390_firstrow import _tube_source

        mesh = _tube_source(sharp_le=True)
        theta, tilt = numpy.radians([angle, 37])
        azimuth = numpy.array(
            [
                [numpy.cos(theta), -numpy.sin(theta), 0],
                [numpy.sin(theta), numpy.cos(theta), 0],
                [0, 0, 1],
            ]
        )
        inclined = numpy.array(
            [
                [numpy.cos(tilt), 0, numpy.sin(tilt)],
                [0, hand, 0],
                [-numpy.sin(tilt), 0, numpy.cos(tilt)],
            ]
        )
        rotation = azimuth @ inclined
        direction = rotation @ numpy.array([1.0, 0.0, 0.0])
        transformed = _Workspace2ReviewComposite(
            mesh.verts @ rotation.T, mesh.families, numpy.zeros((0, 3)), {}
        )
        config = (
            "[families.Wing]\nspanwise = 2\nkeep_first_row = true\n"
            f"trailing_edge_direction = {direction.tolist()}\n"
        )
        src = _workspace_2_review__write_source(
            tmp_path / "src", "wing", transformed, refine_toml=config
        )
        side = src.with_suffix(".boundaries.toml")
        side.write_text(
            side.read_text("utf-8") + '\n[import]\nunits = "METER"\n'
            '[trailing_edges]\ndetect = { surfaces = ["Wing"] }\n',
            "utf-8",
        )
        level = refine_mesh(src)
        _, actual = read_te(level.obj.with_suffix(".te.txt"))
        assert actual @ direction == pytest.approx(numpy.ones(len(actual)), abs=1e-8)

    @staticmethod
    def test_p0400_review_inspection_uses_shared_row_resolution():
        from pyflightstream.cases import SimCase, SweepAxis
        from pyflightstream.cases.workflows import row_solver_setting
        from pyflightstream.workspace.setup_inspection import inspect_case_setup

        case = SimCase(
            sim_id="9001",
            aircraft="Wing",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={"NCPUS": "4", "SYMMETRY_LOADS": " "},
            solver={"max_threads": 8, "symmetry_loads": True},
        )
        assert row_solver_setting(case, "max_threads") == (4, True)
        assert row_solver_setting(case, "symmetry_loads") == (True, False)
        settings = inspect_case_setup(case, "26.124")["settings"]
        assert settings["max_threads"]["value"] == 4
        assert settings["symmetry_loads"]["provenance"] == "setup"

    @staticmethod
    def test_p0400_review_ambiguous_sharp_edges_are_refused(tmp_path):
        from tests.tier1_offline.test_p0390_firstrow import _tube_source

        src = _workspace_2_review__write_source(
            tmp_path / "src",
            "wing",
            _tube_source(sharp_le=True),
            refine_toml="[families.Wing]\nspanwise = 2\nkeep_first_row = true\n",
        )
        side = src.with_suffix(".boundaries.toml")
        side.write_text(
            side.read_text("utf-8") + '\n[import]\nunits = "METER"\n'
            '[trailing_edges]\ndetect = { surfaces = ["Wing"] }\n',
            "utf-8",
        )
        with pytest.raises(_Workspace2ReviewInputArtifactError, match="trailing_edge_direction"):
            refine_mesh(src)


_WORKSPACE_2_SCRIPT_COMPARISON__EXECUTED = "SET_SOLVER_STEADY\nITERATIONS\n500\nSTART_SOLVER\n"


class TestWorkspace2ScriptComparison:
    """P0400-SCRIPTDRIFT: a command rendered after the last executed one is reported where it lands."""  # noqa: E501

    @staticmethod
    def test_p0400_scriptdrift_an_appended_command_is_not_reported_at_line_one(tmp_path):
        """P0400-SCRIPTDRIFT (PFS-2103.040): an insertion after the last executed command is at
        line 5 of a four-line script, not line 1."""
        comparison = compare_scripts(
            _WORKSPACE_2_SCRIPT_COMPARISON__EXECUTED + "EXPORT_SOLVER_ANALYSIS_VTK\n",
            _WORKSPACE_2_SCRIPT_COMPARISON__EXECUTED,
            tmp_path,
        )
        described = drift(comparison, tmp_path, [])
        assert described.startswith("line 5: ran '(nothing)', renders 'EXPORT_SOLVER"), described


class TestWorkspace2SettingsFile:
    """P0400-SETTINGSUTF8: a workspace settings file that is not UTF-8 is refused naming the file."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize("name", ["pyfs.toml", "pyfs.local.toml"])
    def test_p0400_settingsutf8_a_cp1252_settings_file_is_a_named_refusal(tmp_path, name):
        """P0400-SETTINGSUTF8 (PFS-2095.057): a cp1252 byte gives InputArtifactError naming the
        file and asking for UTF-8, never a bare UnicodeDecodeError; the pre-scan reads nothing."""
        (tmp_path / name).write_bytes('[log]\nlevel = "ação"\n'.encode("cp1252"))
        with pytest.raises(_Workspace2SettingsFileInputArtifactError) as caught:
            read_workspace_settings(tmp_path)
        message = str(caught.value)
        assert name in message and "UTF-8" in message, message
        assert settings_supplied(tmp_path) == {}


class TestWorkspace2SetupInspection:
    """P0400-SETUPINSPECT: the setup inspection reports the row override the builder uses."""

    @staticmethod
    @pytest.mark.parametrize(
        "variables",
        [
            {"SYMMETRY_LOADS": " ", "NCPUS": ""},
            {"symmetry_loads": "false", "ncpus": "2"},
        ],
        ids=["blank", "lower-case"],
    )
    def test_p0400_setupinspect_blank_and_lower_case_keys_are_not_overrides(variables):
        """P0400-SETUPINSPECT (PFS-2094.048): a blank cell or a lower-case key states nothing to
        the builder, so the inspection reports the setup's value and provenance, as the builder
        resolves them, not a row value labelled 'matrix row'."""
        case = SimCase(
            sim_id="9001",
            aircraft="Wing",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={"matrix_set": "s901", **variables},
            solver={"symmetry_loads": True, "max_threads": 8},
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = inspect_case_setup(case, "26.124")["settings"]
            built = {
                "symmetry_loads": row_symmetry_loads(case, case.solver.symmetry_loads),
                "max_threads": row_ncpus(case, case.solver.max_threads),
            }
        for key, value in built.items():
            assert settings[key]["value"] == value, (key, settings[key])
            assert settings[key]["provenance"] == "setup", (key, settings[key])


class TestWorkspace2Verdicts:
    """P0400-SYNCNOTES: a sync merge never imports the other workspace's delete-sims notes."""

    @staticmethod
    def test_p0400_syncnotes_a_deletion_note_of_the_other_workspace_is_not_merged():
        """P0400-SYNCNOTES (PFS-2103.038): the other workspace deleted sim 7 and left its note;
        main still holds sim 7's record, so the merge keeps that record, adds no note and
        reports the note as not applied."""
        live = {"run_id": "campaign/sim_7/a", "sim_id": 7, "status": "CONVERGED"}
        note = {
            "run_id": "deleted/sim_7/20261012T120000",
            DELETED_SIM_KEY: 7,
            "deleted_at": "2026-10-12T12:00:00",
            "deleted_run_ids": ["campaign/sim_7/a"],
            "note": "this simulation id belonged to a simulation deleted by pyfs-matrix delete-sims",  # noqa: E501
        }
        merged, added, replaced, conflicts = merge_runs([live], [note], prefer_other=False)
        assert merged == [live]
        assert added == [] and replaced == []
        assert [c["run_id"] for c in conflicts] == [note["run_id"]]
        assert "delete-sims note" in conflicts[0]["reason"]


class TestWorkspace3Review:
    """Adversarial regression cases for the workspace storage and migration lane."""

    @staticmethod
    def test_p0400_restore_reader_waits_after_folder_is_published(tmp_path, monkeypatch):
        workspace = _workspace_3_review___ws(tmp_path, "publish")
        _workspace_3_review___compacted(workspace, "5101", _WORKSPACE_3_REVIEW__FULL)
        results = []
        errors = []
        started = threading.Event()

        def reader():
            started.set()
            try:
                results.append(storage.ensure_sim_expanded(workspace, "5101", reason="second"))
            except BaseException as error:
                errors.append(error)

        second = threading.Thread(target=reader)
        real = Path.replace

        def publish(path, target):
            result = real(path, target)
            if Path(target) == workspace.sim_dir("5101"):
                second.start()
                assert started.wait(2)
                second.join(timeout=0.2)
            return result

        monkeypatch.setattr(Path, "replace", publish)
        assert storage.ensure_sim_expanded(workspace, "5101", reason="first")
        second.join(timeout=5)
        assert not second.is_alive()
        assert not errors
        assert results == [False]

    @staticmethod
    def test_p0400_delete_records_regeneration_failure(tmp_path):
        workspace = _workspace_3_review___shared_product_workspace(tmp_path, "regeneration")
        # A fresh interpreter isolates a public stage registration from the suite.
        code = """
import sys
from pyflightstream.workspace import register_post_stage
from pyflightstream.workspace.storage import delete_sims
@register_post_stage
def fails(*args, **kwargs):
    raise RuntimeError("post failed")
delete_sims(sys.argv[1], ["3001"], matrix_products="regenerate", apply=True)
"""
        result = subprocess.run(
            [sys.executable, "-c", code, str(workspace.root)],
            env={**os.environ, "PYTHONPATH": str(Path(storage.__file__).resolve().parents[2])},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1 and "post failed" in result.stderr, result.stderr
        calls = storage.read_storage_calls(workspace.root)
        assert calls[-1]["applied"] is True
        assert "interrupted" in calls[-1]
        assert "post failed" in calls[-1]["interrupted"]
        tombstone = next(
            row for row in _workspace_3_review___rows(workspace) if row.get("deleted_sim") == "3001"
        )
        assert calls[tombstone["storage_entry"]] == calls[-1]

    @staticmethod
    def test_p0400_sync_expands_under_runs_lease(tmp_path, monkeypatch):
        main, other = _workspace_3_review___sync_pair(tmp_path, "expandlease")
        _workspace_3_review___compacted(main, "5102", _WORKSPACE_3_REVIEW__FULL)
        _workspace_3_review___write(other.sim_dir("5102") / "scripts" / "point.fs", "s")
        held = []
        real = zipfile.ZipFile.extract

        def watching(*args, **kwargs):
            held.append((main.root / "runs.json.lock").is_file())
            return real(*args, **kwargs)

        monkeypatch.setattr(zipfile.ZipFile, "extract", watching)
        storage.sync_workspaces(main.root, "runs", apply=True)
        assert held and all(held)

    @staticmethod
    def test_p0400_sync_copy_failure_records_committed_runs(tmp_path, monkeypatch):
        main, other = _workspace_3_review___sync_pair(tmp_path, "copyfailure")
        _workspace_3_review___recorded_sim(other, "5103", _WORKSPACE_3_REVIEW__FULL)

        real = shutil.copy2

        def fails(source, *args, **kwargs):
            if other.sim_dir("5103") in Path(source).parents:
                raise OSError("copy failed")
            return real(source, *args, **kwargs)

        monkeypatch.setattr(shutil, "copy2", fails)
        with pytest.raises(OSError, match="copy failed"):
            storage.sync_workspaces(main.root, "runs", apply=True)
        entry = storage.read_storage_calls(main.root)[-1]
        assert "copy failed" in entry["interrupted"]
        assert "runs" in entry
        assert entry["runs"]["added"] == ["camp/sim_5103/AL+000"]
        assert entry["runs"]["records_after"] == len(_workspace_3_review___rows(main))

    @staticmethod
    def test_p0400_sync_preview_reads_conflicts_inside_compacted_sim(tmp_path):
        main, other = _workspace_3_review___sync_pair(tmp_path, "previewzip")
        archive = _workspace_3_review___compacted(main, "5105", _WORKSPACE_3_REVIEW__FULL)
        _workspace_3_review___write(other.sim_dir("5105") / "scripts" / "point.fs", "changed")
        preview = storage.sync_workspaces(main.root, "runs")[0]
        assert archive.is_file()
        applied = storage.sync_workspaces(main.root, "runs", apply=True)[0]
        assert preview["files"]["conflicts"] == applied["files"]["conflicts"]
        assert preview["files"]["to_copy"] == applied["files"]["to_copy"]

    @staticmethod
    @pytest.mark.parametrize("incoming_archive", [False, True])
    @pytest.mark.parametrize("apply", [False, True])
    def test_p0400_sync_refuses_folder_archive_collision(tmp_path, incoming_archive, apply):
        main, other = _workspace_3_review___sync_pair(tmp_path, "collision")
        if incoming_archive:
            _workspace_3_review___compacted(other, "5104", _WORKSPACE_3_REVIEW__FULL)
            _workspace_3_review___write(main.sim_dir("5104") / "keep.txt", "keep")
        else:
            _workspace_3_review___compacted(main, "5104", _WORKSPACE_3_REVIEW__FULL)
            _workspace_3_review___write(main.sim_dir("5104") / "keep.txt", "keep")
            _workspace_3_review___write(other.sim_dir("5104") / "scripts" / "point.fs", "incoming")
        before = (main.sim_dir("5104") / "keep.txt").read_bytes()
        with pytest.raises(storage.StorageError, match="5104"):
            storage.sync_workspaces(main.root, "all", apply=apply)
        assert (main.sim_dir("5104") / "keep.txt").read_bytes() == before

    pass

    @staticmethod
    def test_p0400_lane_regressions_carry_release_in_test_names():
        missing = []
        # The tests tree itself, not a path through the package: the release workflow runs
        # these tests against the installed wheel, where the package has no tests beside it.
        directory = Path(__file__).resolve().parent
        groups = [
            (path, node)
            for path in directory.glob("test_regression_workspace_*.py")
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.ClassDef) and node.name.startswith("TestWorkspace3")
        ]
        assert len(groups) >= 3
        for path, group in groups:
            for node in ast.walk(group):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    if not node.name.startswith("test_p0400_"):
                        missing.append(f"{path.name}:{node.name}")
        assert not missing, missing


class TestWorkspace3Setup:
    """P0400-WS3-SETUP: setup standards evidence and the setup library writer."""

    @staticmethod
    def test_p0400_alias_build_reports_the_canonical_rows_evidence():
        """P0400-SETUP-ALIAS (PFS-2094.025): a build named by alias reads its canonical version row."""  # noqa: E501
        available, evidence = setup_entry_evidence("wake_relaxation", "26.0")
        assert available
        assert "build 26.000: documented" in evidence, evidence
        assert "no recorded evidence" not in evidence
        assert setup_entry_evidence("wake_relaxation", "26.0") == setup_entry_evidence(
            "wake_relaxation", "26.000"
        )

    @staticmethod
    def test_p0400_existing_non_utf8_user_file_is_preserved(tmp_path: Path):
        """P0400-SETUP-CP1252 (PFS-2095.033): a cp1252 user file is reported preserved, not decoded."""  # noqa: E501
        destination = tmp_path / "inputs" / "setups"
        destination.mkdir(parents=True)
        user_file = destination / "SETUP_GUIDELINES.md"
        original = "Notes on the création of my standards\n".encode("cp1252")
        user_file.write_bytes(original)
        result = write_setup_library(tmp_path, fs_version="26.124", guidelines=True)
        assert result == {"SETUP_GUIDELINES.md": "preserved"}
        assert user_file.read_bytes() == original
        again = write_setup_library(tmp_path / "fresh", fs_version="26.124", guidelines=True)
        assert again == {"SETUP_GUIDELINES.md": "created"}
        twice = write_setup_library(tmp_path / "fresh", fs_version="26.124", guidelines=True)
        assert twice == {"SETUP_GUIDELINES.md": "unchanged"}
