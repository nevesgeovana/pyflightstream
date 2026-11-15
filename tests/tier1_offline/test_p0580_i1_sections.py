"""The sections table names its rotor by ROTOR_ID; readers find the alias from the id.

THE REQUIREMENT (design of the post outputs, section 4.5): the sections table is
the run block, then ``FAMILY, FAMILY_ID, STEP, PLANE, ROTOR_ID, AZIMUTH``; "``ROTOR``
(alias) becomes ``ROTOR_ID``". A rotor block that declares no id is rotor 0 (D6).
The products cut from the table (harmonics, disc maps, corrections, the
quasi-steady wheel) still select a rotor's rows by its alias, which they read from
the id.
"""

from __future__ import annotations

import pytest

from pyflightstream.post._block_scope import rotor_ids_for, run_blocks, with_rotor_alias
from pyflightstream.post.products import SECTION_COLUMNS, read_csv_table, write_sections_table
from tests.tier1_offline.test_goal028_sections_identity import LAYOUT, ROTORS
from tests.tier1_offline.test_post_products import SLOADS

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-I1-SECTIONS")])


def test_p0580_the_sections_table_states_rotor_id_and_no_alias(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS,
        rotor_ids={"PUSHER": 3},
    )  # fmt: skip
    columns, rows = read_csv_table(written)
    assert "ROTOR" not in columns and "ROTOR" not in SECTION_COLUMNS
    assert [row["ROTOR_ID"] for row in rows] == ["NA", "3"]


def test_p0580_a_lone_rotor_that_declares_no_id_is_rotor_0(tmp_path):
    written = write_sections_table(
        tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS
    )
    _columns, rows = read_csv_table(written)
    assert [row["ROTOR_ID"] for row in rows] == ["NA", "0"]


def test_p0580_the_ids_of_the_post_are_used_where_the_writer_is_given_none(tmp_path):
    with run_blocks({"p": {"POL": "1"}}, {"PUSHER": 7}):
        written = write_sections_table(
            tmp_path / "p_sections.csv", SLOADS, mach=0.2, layout=LAYOUT, rotors=ROTORS
        )
        _columns, rows = read_csv_table(written)
        assert [row["ROTOR_ID"] for row in rows] == ["NA", "7"]
        assert [row.get("ROTOR") for row in with_rotor_alias(rows)] == [None, "PUSHER"]


def test_p0580_a_reader_resolves_the_alias_from_the_id():
    rows = [{"ROTOR_ID": "3"}, {"ROTOR_ID": "NA"}, {"ROTOR_ID": "0", "ROTOR": "KEPT"}]
    resolved = with_rotor_alias(rows, {"PUSHER": 3})
    assert [row.get("ROTOR") for row in resolved] == ["PUSHER", None, "KEPT"]
    assert with_rotor_alias([{"ROTOR_ID": "0"}], aliases=["PROP"])[0]["ROTOR"] == "PROP"
    # Two rotors no id names cannot be told apart: neither is resolved.
    assert rotor_ids_for(["A", "B"]) == {}
