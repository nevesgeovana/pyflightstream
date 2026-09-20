"""GH-02 of the independent review of GitHub main, 2026-09-20.

A refused rebuild retires its product.

The retirement pass read each skip key as a file name, cutting it at `#`. A rotor table's skip
is `polars/<sim>#rotor_tables` and its files are `polars/P<sim>-<alias>_rotor.csv`, which share
no prefix with it, so the refusal was recorded in the manifest and the table it refused stayed
on disk. A reader opening `polars/` finds a current-looking file holding the numbers the refusal
says cannot be trusted -- the same shape as a stale product left beside a new one, which this
module already guards for a renamed unsteady polar and for a refused distribution.
"""

from __future__ import annotations

from pyflightstream.post.products import POLARS_DIR, ROTOR_TABLE_SUFFIX, products_to_retire

SIM = "6002"
ROTOR_TABLE = f"{POLARS_DIR}/P{SIM}-HUB_PUSHER{ROTOR_TABLE_SUFFIX}"
PREVIOUS = {
    ROTOR_TABLE: {"sim_id": SIM, "runs": [f"camp/sim_{SIM}/AL-020"]},
    f"{POLARS_DIR}/P{SIM}-sweep.csv": {"sim_id": SIM, "runs": [f"camp/sim_{SIM}/AL-020"]},
}


def test_a_refused_rotor_plan_retires_the_rotor_table_it_refuses():
    """The skip names the simulation; the file names the alias. The identity is the sim_id."""
    skipped = {f"{POLARS_DIR}/{SIM}#rotor_tables": "no matrix row for this simulation"}
    assert ROTOR_TABLE in products_to_retire(skipped, PREVIOUS)


def test_a_rotor_table_of_another_simulation_is_left_alone():
    """A retirement that reaches past its own refusal deletes a product nobody refused."""
    skipped = {f"{POLARS_DIR}/7777#rotor_tables": "no matrix row for this simulation"}
    assert ROTOR_TABLE not in products_to_retire(skipped, PREVIOUS)


def test_the_shapes_that_already_worked_still_do():
    """A skip named after its own file, and a refused distribution family, keep their behaviour."""
    named = f"{POLARS_DIR}/P{SIM}-sweep.csv"
    assert named in products_to_retire({named: "unreadable export"}, PREVIOUS)
    previous = {"sections/AL-020_sloads_ROTOR.csv": {"sim_id": SIM}}
    retired = products_to_retire({"sections/AL-020_sloads#distributions": "no layout"}, previous)
    assert "sections/AL-020_sloads_ROTOR.csv" in retired
