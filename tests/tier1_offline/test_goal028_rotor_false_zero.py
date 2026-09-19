"""A rotor whose families select NO surface of the export is refused, never CT 0 (WT-02).

THE DEFECT. `rotor_shaft_loads` sums the rotor's families over the export's
surfaces. When none of them is in the export (a renamed family, a reference
cited against another mesh) the sum is zero, and the rotor table published
``CT 0.00000`` down the whole sweep with `skipped` empty. The function fills
`families_used` and nothing read it. A zero is a value a rotor can genuinely
have, so it is exactly the number a reader believes.

The expectation is the package's own rule, stated on the definitions page: the
token for a value that does not exist is ``NA``, never a zero, and a product not
written is a product explained.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces  # noqa: E402

from pyflightstream.post.products import write_rotor_table  # noqa: E402


def _row(surfaces):
    return {
        "run_id": "camp/sim_1/P1",
        "surfaces": surfaces,
        "condition": {"MACH": 0.15, "ALPHA": 0.0},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 40.0,
    }


def test_a_rotor_that_selects_no_surface_is_left_out_with_its_reason(tmp_path):
    left_out: list[tuple[str, str]] = []
    runs: list[str] = []
    written = write_rotor_table(
        tmp_path / "P0001-PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        # The rotor's family is Blade1; this export carries a wing alone.
        rows=[_row(_surfaces(Wing={"Cz": 0.5}))],
        reference=_reference(),
        left_out=left_out,
        written_runs=runs,
    )
    assert written is None, "a table of one false zero was written"
    assert runs == []
    assert len(left_out) == 1, left_out
    run_id, reason = left_out[0]
    assert run_id == "camp/sim_1/P1"
    assert "Blade1" in reason and "Wing" in reason, reason


def test_the_row_beside_it_that_does_select_a_surface_is_still_written(tmp_path):
    left_out: list[tuple[str, str]] = []
    runs: list[str] = []
    good = {**_row(_surfaces(Blade1={"Cz": 0.5})), "run_id": "camp/sim_1/P2"}
    written = write_rotor_table(
        tmp_path / "P0001-PUSHER_rotor.csv",
        rotor=_rotor("Z"),
        rows=[_row(_surfaces(Wing={"Cz": 0.5})), good],
        reference=_reference(),
        left_out=left_out,
        written_runs=runs,
    )
    assert written is not None and written.is_file()
    assert runs == ["camp/sim_1/P2"], runs
    assert [run for run, _why in left_out] == ["camp/sim_1/P1"]
