"""GOAL-020 item 6: the offline half of the three board rows that are not a page.

FOUR ROWS WERE RULED ON BY THE OWNER on 2026-09-13 and each is proved in the
tier it can be proved in. PFS-2032.06 is a page-against-the-tree rule and
lives in ``test_generated_surface.py``. The other three are here:

  PFS-2032.07  the per-mesh folder, and the user being TOLD about it. Wholly
               offline: `init` writes the page or it does not.
  PFS-2033.03  a matrix row carrying a raw solver command, RUN on the seat.
               What tier 1 can hold is that the row still SAYS what the seat
               measured; the run itself is
               ``tests/tier3_licensed/test_studies.py``.
  PFS-2034.05  the rotation null test, RUN on the seat. What tier 1 can hold
               is that the three rows are still the experiment the report
               describes: a control, a derangement and a null pair.

WHY THE LAST TWO ARE HERE AT ALL, since neither can run the solver. A licensed
round's evidence is a report, and a report is a file that cannot notice when
the rows it describes are edited underneath it. These tests are what makes
RPT-047 and the raw-command round FALSIFIABLE from a clone with no seat: change
the angle of attack of row 9003 and this file goes red, where the report would
go on saying what it said.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace

REPO = Path(__file__).resolve().parents[2]
TIER3 = REPO / "tests" / "tier3_licensed"


# --- PFS-2032.07: the per-mesh folder, and telling the user -------------------


def test_goal020_board_items_init_tells_a_user_where_a_mesh_goes(tmp_path):
    """`init` leaves the page in the folder a user looking for one is standing in.

    HER RULE, of 2026-09-13: "a pasta por malha, e o usuario precisa ser
    instruido disso. No init voce pode criar um readme dentro de
    inputs/geometries". The page is asserted to be THERE and to name the
    layout, because a page that exists and does not say the thing is a page
    that was written to satisfy a test.
    """
    CampaignWorkspace.init(tmp_path / "ws")
    readme = tmp_path / "ws" / "inputs" / "geometries" / "README.md"
    assert readme.is_file(), "init left no page where a user puts a mesh"
    text = readme.read_text(encoding="utf-8")
    assert "One folder per mesh" in text
    # THE THREE THINGS A READER HAS TO LEAVE WITH, and each is a sentence the
    # owner's own question asked for: the layout, that their existing rows do
    # not change, and the one command that moves a flat library over.
    assert "boundaries.toml" in text, "the page does not say the sidecar travels with the mesh"
    assert "flat library still works" in text.lower(), (
        "the page does not say a flat layout still works"
    )
    assert "migrate-geometries" in text, "the page does not name the command that moves one over"


def test_goal020_board_items_init_does_not_overwrite_a_page_already_there(tmp_path):
    """Running `init` twice does not destroy what the user wrote in the meantime.

    `init` is run again on an existing workspace as a matter of course, so a
    page written unconditionally is a page that eats an edit. The guard in the
    source is `if not readme.exists()`, and this is what would notice it going.
    """
    root = tmp_path / "ws"
    CampaignWorkspace.init(root)
    readme = root / "inputs" / "geometries" / "README.md"
    readme.write_text("the user's own words\n", encoding="utf-8")
    CampaignWorkspace.init(root)
    assert readme.read_text(encoding="utf-8") == "the user's own words\n"


# --- PFS-2033.03: the row the seat measured -----------------------------------


def test_goal020_board_items_the_raw_command_row_still_states_what_the_seat_measured():
    """Row 2004 of matriz_setup.fs still carries the line the licensed round read.

    The round of 2026-09-13 measured that the solver took the raw line over
    the preset's own, 350 iterations against 300. That verdict is about THIS
    row; if the cell is edited, the tier-3 assertion is measuring something
    else and the report is describing a row that no longer exists.
    """
    text = (TIER3 / "matriz_setup.fs").read_text(encoding="utf-8")
    row = next((line for line in text.splitlines() if line.startswith("2004 ")), None)
    assert row is not None, "matriz_setup.fs no longer carries row 2004"
    cells = [cell.strip() for cell in row.split("|")]
    assert "s008" in cells, f"row 2004 no longer cites the setup that carries the raw line: {cells}"
    # THE BUILD IS 26.123, which is the owner's standing rule and not a
    # detail of this row: `--fs-version` fills EMPTY cells only, so a row
    # naming an older build runs on that build whatever the campaign asked.
    assert "26.123" in cells, "row 2004 does not name the build the seat runs"
    # THE LINE LIVES IN THE SETUP, not in the row, and that is the whole shape
    # of PFS-2033.01: a raw command is declared where the solver settings are,
    # and the run record carries the setup's id as the line's SOURCE. The
    # first writing of this test looked for it in the row and went red, which
    # is the test finding out where the feature is rather than asserting it.
    setup = (TIER3 / "inputs" / "setups" / "s008.toml").read_text(encoding="utf-8")
    assert 'command = "SOLVER_SET_ITERATIONS 350"' in setup
    assert 'before = "init"' in setup
    assert "NITER = 300" in setup, (
        "the preset's own iteration count is gone, so the row no longer measures "
        "which of the two the solver takes, which is the only question it exists to ask"
    )


# --- PFS-2034.05: the rotation null test's three rows -------------------------


@pytest.mark.parametrize(
    ("pol", "alpha", "turns"),
    [
        ("9001", "0.0", False),
        ("9002", "6.0", True),
        ("9003", "-6.0", True),
    ],
)
def test_goal020_board_items_the_rotation_null_rows_are_still_the_experiment(pol, alpha, turns):
    """The three rows of matriz_rotate.fs are still a control, a derangement and a null pair.

    RPT-047's whole verdict rests on the rows being these three and not two:
    9003 agreeing proves nothing on its own unless 9002, which differs from it
    ONLY in the sign of the angle of attack, disagrees. A later edit that made
    both rows state the same angle would leave a report claiming a
    discriminating test over a pair that no longer discriminates.
    """
    rows = {
        line.split("|")[0].strip(): line
        for line in (TIER3 / "matriz_rotate.fs").read_text(encoding="utf-8").splitlines()
        if line[:4].isdigit()
    }
    assert pol in rows, f"matriz_rotate.fs no longer carries row {pol}"
    row = rows[pol]
    cells = [cell.strip() for cell in row.split("|")]
    assert alpha in cells, f"row {pol} no longer sweeps {alpha} degrees; its cells are {cells[7]!r}"
    assert ("ROTATE:" in row) is turns, (
        f"row {pol} {'should' if turns else 'should not'} turn the mesh; "
        "the control turns nothing and both other rows turn it by the same angle"
    )
    if turns:
        # THE SAME ANGLE, THE SAME AXIS, AND THE WHOLE MESH. Two records
        # because no one alias owns every boundary: the rotor's alias carries
        # the blades and the frames placed from its hub, and `airframe`
        # carries the spinner. A row that turned only one of them would be
        # measuring a bent model, and would still produce numbers.
        assert row.count("ANGLE: 6") == 2, (
            f"row {pol} does not turn the mesh in two records of 6 degrees"
        )
        assert row.count("AXIS: HUB-Y") == 2, f"row {pol} does not turn both records about HUB-Y"
        assert "ALIAS: PUSHER" in row and "ALIAS: airframe" in row, (
            f"row {pol} does not turn both the rotor and the spinner"
        )


def test_goal020_board_items_the_null_pair_differs_from_the_derangement_only_in_the_flow():
    """9002 and 9003 are the same row but for the sign of the angle of attack.

    This is the property the report's claim actually rests on and it is the
    one no individual row can carry. It is asserted by DIFFERENCE rather than
    by restating both rows, so it cannot go on passing after someone changes
    the geometry, the setup or the clock of one of them.
    """
    rows = {
        line.split("|")[0].strip(): [cell.strip() for cell in line.split("|")]
        for line in (TIER3 / "matriz_rotate.fs").read_text(encoding="utf-8").splitlines()
        if line[:4].isdigit()
    }
    left, right = rows["9002"], rows["9003"]
    differing = [index for index, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
    header = [
        cell.strip()
        for cell in (TIER3 / "matriz_rotate.fs")
        .read_text(encoding="utf-8")
        .splitlines()[0]
        .split("|")
    ]
    named = sorted(header[index] for index in differing)
    assert named == ["DESCRIPTION", "POL", "SWEEP_VALUES"], (
        "9002 and 9003 differ in more than the angle of attack, so one failing and the "
        f"other passing says nothing about the rotation. They differ in: {named}"
    )
