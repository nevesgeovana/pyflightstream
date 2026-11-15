"""AD-20: matrix binding preserves the results captured from 42cf219a."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix
from tests.tier1_offline.test_matrix_run import RECIPES, make_library

FIXTURES = Path(__file__).parent / "fixtures"

#: The solver-settings fields 0.58.0 removed with their setup keys (PFS-2176 review).
REMOVED_SOLVER_FIELDS = (
    "physics_auto_trailing_edges",
    "physics_auto_wake_nodes",
    "sonic_velocity_m_per_s",
    "symmetry_loads",
    "thin_boundaries",
)


@pytest.mark.parametrize("fixture", ["matrix.fs", "matrix_registry.fs"])
def test_resolve_matrix_matches_before_the_cut(tmp_path, fixture):
    """P0360-W9c, AD-20: both committed matrices retain their complete binding."""
    workspace = make_library(tmp_path, register_build=("26.120", "FlightStream.exe"))
    resolved = resolve_matrix(
        FIXTURES / fixture,
        workspace,
        name="matrix",
        fs_version="26.120",
        recipes=RECIPES,
        fs_exe="FlightStream.exe" if fixture == "matrix.fs" else None,
    )
    actual = json.loads(TypeAdapter(ResolvedMatrix).dump_json(resolved))
    # Re-pinned at 0.39.0 for three additive fields at their defaults, nothing else
    # moved: `study` of each reference artifact and `study_surfaces` of each case's
    # reference (FR-435, None when the artifact declares no study), and
    # `accept_unregistered_build` of each build (FR-998, False unless a file accepts it).
    # P0410 adds exactly two optional pproc defaults: noise=None and
    # products.polar_axes=None. The fixture amendment states those defaults;
    # it does not recapture the implementation's output. F-1290 (0.43.0) changes one
    # serialization and nothing else: a pproc group dumps as the one alias string it
    # was written as, since the member-list form is refused on reading. Two more optional
    # pproc defaults of 0.43.0, nothing else moved: refinement=None (NL-TRST-7) and
    # products.trimmed_polar=False (FR-2302).
    expected = json.loads((FIXTURES / "p0360_w9c.json").read_text(encoding="utf-8"))

    # D0 replaces the absent singular table with an empty entry list; retain
    # the complete historical binding comparison, changing only that default.
    def migrate_default(value):
        if isinstance(value, dict):
            if "farfield" in value:
                assert value.pop("farfield") is None
                value["farfields"] = []
                value["polar_at"] = []
            if "trimmed_polar" in value:
                # 0.58.0 (PFS-2231): the trim moment is spelled CmB, and superfile_format
                # is polar_format with the same value.
                value["trim_moment"] = "CmB"
                value["trim_axis"] = "ALPHA"
                if "superfile_format" in value:
                    value["polar_format"] = value.pop("superfile_format")
                # 0.54.0 adds one optional product default, rotor_cn_slope=False (FR-3502);
                # nothing else moved.
                value["rotor_cn_slope"] = False
                # 0.55.0 adds two more optional product defaults, FR-3511 and FR-3512.
                value["merged_polar"] = False
                value["rotate_columns"] = {}
            for child in value.values():
                migrate_default(child)
        elif isinstance(value, list):
            for child in value:
                migrate_default(child)

    migrate_default(expected[fixture])
    # D7 removes the raw-route field and adds the optional sidecar identity.
    for case in expected[fixture]["campaign"]["sims"]:
        assert case.pop("raw_mesh_conditions") is None
        case["boundaries_file"] = None
        # PFS-2256: the thin boundaries a boundaries file marks; these fixtures mark none.
        case["thin_boundaries"] = None
        # 0.58.0 (PFS-2176 review): the setup keys whose condition has another home
        # leave the solver settings; these fixtures state none of them.
        for key in REMOVED_SOLVER_FIELDS:
            assert case["solver"].pop(key) is None
        if case.get("pproc") is not None:
            assert case["pproc"].pop("base_regions") == []
    # PFS-2252 (0.58.0): a pproc declares no base region; these fixtures declared none.
    for pproc in expected[fixture]["pprocs"].values():
        assert pproc.pop("base_regions") == []
    # PFS-2170 records rejected default pins; these fixtures reject none.
    for condition in expected[fixture]["conditions"].values():
        condition["dropped_defaults"] = {}
    # PFS-2214 (0.57.0) records the rows whose generated geometry failed; these
    # fixtures generate none, so the one new field is empty and nothing else moved.
    assert "geometry_failures" not in expected[fixture]
    expected[fixture]["geometry_failures"] = {}
    assert actual == expected[fixture]
