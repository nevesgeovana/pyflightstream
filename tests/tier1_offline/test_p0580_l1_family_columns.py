"""PFS-2231 (0.58.0, lane L1): the column registry of the FAM, group, sections and Cp files.

The design of the 0.58.0 post outputs, sections 4.1 to 4.7: the columns of
each kind in order, their units and frames, the group ids of section 4.4,
and a definition for every column that resolves to an anchor of its page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post import _family_columns as registry
from pyflightstream.post.axes import frame_rotations, rotor_frame
from pyflightstream.post.rotor_table import rotor_frame_coefficients

ROOT = Path(__file__).resolve().parents[2]


def _names(columns):
    return list(registry.column_names(columns))


def test_dim_states_the_loads_in_the_export_frame_name():
    columns = registry.dim_columns("MRP")
    assert _names(columns) == [
        "FAMILY",
        "FAMILY_ID",
        "FX_MRP",
        "FY_MRP",
        "FZ_MRP",
        "MX_MRP",
        "MY_MRP",
        "MZ_MRP",
        "MESH_FACES",
    ]
    units = {spec.name: spec.unit for spec in columns}
    assert units["FX_MRP"] == "N" and units["MZ_MRP"] == "N m"
    assert {spec.frame for spec in columns if spec.name.endswith("_MRP")} == {"MRP"}


def test_acoef_writes_six_columns_per_frame_w_s_b_then_rotors_ascending():
    names = _names(registry.acoef_columns((1, 0)))
    stems = ("CD", "CY", "CL", "Cl", "Cm", "Cn")
    frames = ("W", "S", "B", "R0", "R1")
    assert names == [
        "FAMILY",
        "FAMILY_ID",
        *(f"{s}{f}" for f in frames for s in stems),
        "CD0",
        "CDI",
        "MESH_FACES",
    ]
    assert _names(registry.acoef_columns(drag_split=("CDV", "CDP")))[-3:-1] == ["CDV", "CDP"]


def test_acoef_signs_are_aft_up_right():
    signs = {spec.name: spec.sign for spec in registry.acoef_columns((0,))}
    for frame in ("W", "S", "B", "R0"):
        assert signs[f"CD{frame}"] == "positive aft"
        assert signs[f"CL{frame}"] == "positive up"
        assert signs[f"CY{frame}"] == "positive right"


def test_rcoef_order_and_units():
    columns = registry.rcoef_columns((0, 2))
    names = _names(columns)
    own = [
        "T",
        "Q",
        "P",
        "CT",
        "CQ",
        "CP",
        "CFZ",
        "CFY",
        "CMZ",
        "CMY",
        "ETA",
        "TC",
        "YC",
        "ZC",
        "QC",
        "NC",
        "MC",
        "TCA",
        "YCA",
        "ZCA",
        "QCA",
        "NCA",
        "MCA",
    ]
    per_frame = [f"{s}{f}" for f in ("W", "S", "B", "R0", "R2") for s in ("CT", "CQ", "ETA")]
    assert names == ["FAMILY", "FAMILY_ID", "ROTOR_ID", *own, *per_frame, "MESH_FACES"]
    units = {spec.name: spec.unit for spec in columns}
    assert (units["T"], units["Q"], units["P"], units["CT"]) == ("N", "N m", "kW", "-")


def test_rcoef_registry_matches_what_the_coefficients_return():
    frame = rotor_frame((-1.0, 0.0, 0.0), 0)
    row = rotor_frame_coefficients(
        force_n=(-1.0, 0.0, 0.0),
        moment_hub_nm=(-1.0, 0.0, 0.0),
        frame=frame,
        rotations=frame_rotations(0.0, 0.0, [frame]),
        rpm=600.0,
        diameter_m=1.0,
        density_kg_m3=1.0,
        vinf_m_s=10.0,
        sref_m2=1.0,
        cref_m=1.0,
        bref_m=1.0,
    )
    assert list(row) == _names(registry.rcoef_columns((0,)))[3:-1]


def test_rcoef_needs_a_rotor():
    with pytest.raises(ProductError):
        registry.rcoef_columns(())


def test_group_files_swap_the_identity():
    assert _names(registry.acoef_columns(entity="group"))[:2] == ["GROUP", "GROUP_ID"]
    assert _names(registry.rcoef_columns((0,), entity="group"))[:3] == [
        "GROUP",
        "GROUP_ID",
        "ROTOR_ID",
    ]


def test_group_ids():
    assert registry.group_id("TOTAL") == 0
    assert registry.group_id("AIRFRAME") == 1
    assert registry.group_id("rotor", rotor_id=0) == 10
    assert registry.group_id("rotor", rotor_id=3) == 13
    assert registry.group_id("declared", position=1) == 101
    with pytest.raises(ProductError):
        registry.group_id("declared")


def test_sections_and_cp_identity():
    assert _names(registry.sections_columns()) == [
        "FAMILY",
        "FAMILY_ID",
        "STEP",
        "PLANE",
        "ROTOR_ID",
        "AZIMUTH",
        "Offset",
        "Chord",
        "X_QC",
        "Z_QC",
        "Fx",
        "Fz",
        "Moment",
    ]
    assert _names(registry.sections_columns(integrated=True))[-4:] == [
        "Strip_length",
        "Fx_int",
        "Fz_int",
        "My_int",
    ]
    assert _names(registry.cp_columns()) == [
        "FAMILY",
        "FAMILY_ID",
        "STEP",
        "PLANE",
        "ROTOR_ID",
        "AZIMUTH",
        "SECTION",
    ]


def _anchors(page: Path) -> set[str]:
    text = page.read_text(encoding="utf-8")
    explicit = set(re.findall(r'<a id="([^"]+)"></a>', text))
    headings = {
        re.sub(r"[^a-z0-9 -]", "", line.lstrip("#").strip().lower()).replace(" ", "-")
        for line in text.splitlines()
        if line.startswith("#")
    }
    return explicit | headings


def test_every_definition_resolves_to_an_anchor_of_its_page():
    kinds = [
        registry.dim_columns("MRP"),
        registry.acoef_columns((0,)),
        registry.rcoef_columns((0,)),
        registry.acoef_columns((0,), entity="group"),
        registry.sections_columns(integrated=True),
        registry.cp_columns(),
    ]
    for columns in kinds:
        for spec in columns:
            page, _, anchor = spec.definition.partition("#")
            assert anchor in _anchors(ROOT / page), f"{spec.name}: {spec.definition}"
