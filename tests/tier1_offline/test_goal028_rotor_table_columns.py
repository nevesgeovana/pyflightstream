"""The rotor table states what it divided by, and the advance ratio is the free stream's.

- CC-03. Every coefficient of this table divides by `rho n^2 D^4` or `rho n^2 D^5`,
  and the table stated none of the three. With `RHO` in the shared block (0.24.0)
  it still owed the rotor's own speed and diameter.
- NL-09, the owner's answer: BOTH advance ratios stay, `J` as the row REQUESTED it
  and `J_<alias>` as COMPUTED; the coefficients use the computed one, and the
  stage says so when the two differ on the rotor the row sweeps.
- `J = V / (n D)` is a ratio of the FREE STREAM, so it is computed with the
  export's free-stream velocity, not with the reference velocity the solver
  normalises forces by. The two are equal in every campaign recorded so far.

Expected values are the definitions, computed here from the row's own inputs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_goal026_item06_rotor_loads import _reference, _rotor, _surfaces  # noqa: E402

from pyflightstream.post.products import read_csv_table, write_rotor_table  # noqa: E402


def _row(**update):
    row = {
        "run_id": "camp/sim_1/P1",
        "surfaces": _surfaces(Blade1={"Cz": 0.5}),
        "condition": {"MACH": 0.15, "ALPHA": 0.0, "VINF": 40.0, "J": 0.5},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 80.0,  # the REFERENCE velocity, deliberately not the free stream
        "free_stream": 40.0,
    }
    row.update(update)
    return row


def test_the_table_states_the_speed_and_the_diameter_it_divided_by(tmp_path):
    rotor = _rotor("Z")
    written = write_rotor_table(
        tmp_path / "P1-PUSHER_rotor.csv", rotor=rotor, rows=[_row()], reference=_reference()
    )
    columns, rows = read_csv_table(written, skip=1)
    assert "RPM_PUSHER" in columns and "DIAMETER_PUSHER" in columns, columns
    assert float(rows[0]["RPM_PUSHER"]) == pytest.approx(3000.0)
    assert float(rows[0]["DIAMETER_PUSHER"]) == pytest.approx(rotor.diameter_m)
    assert columns.index("RPM_PUSHER") < columns.index("J_PUSHER")


def test_the_advance_ratio_is_the_free_streams_and_the_forces_are_the_reference_velocitys(
    tmp_path,
):
    rotor = _rotor("Z")
    written = write_rotor_table(
        tmp_path / "P1-PUSHER_rotor.csv", rotor=rotor, rows=[_row()], reference=_reference()
    )
    _columns, rows = read_csv_table(written, skip=1)
    n = 3000.0 / 60.0
    assert float(rows[0]["J_PUSHER"]) == pytest.approx(40.0 / (n * rotor.diameter_m), rel=1e-5)
    # The force was normalised by the solver with VREF, so it comes back with VREF.
    reference = _reference()
    thrust = 0.5 * 0.5 * 1.225 * 80.0**2 * reference.sref_m2
    expected = thrust / (1.225 * n**2 * rotor.diameter_m**4)
    assert float(rows[0]["CT_PUSHER"]) == pytest.approx(expected, rel=1e-4)


def _posted_with_a_rotor(tmp_path, diameter: float) -> list[str]:
    """Post the recorded two-simulation campaign with one rotor of ``diameter`` declared."""
    import warnings

    from test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "\n".join(
            [
                "area_m2 = 50.0",
                "chord_m = 2.526",
                "span_m = 20.0",
                "",
                "[rotors.PUSHER]",
                'alias = "PUSHER"',
                "x_m = 0.0",
                "y_m = 0.0",
                "z_m = 0.0",
                'axis = "X"',
                "rpm_sign = 1",
                f"diameter_m = {diameter}",
                'families_blades = ["B"]',
                'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
                "",
            ]
        ),
        encoding="utf-8",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    return [str(w.message) for w in caught if "J_PUSHER" in str(w.message)]


def test_the_stage_says_so_when_the_rotor_did_not_run_at_the_ratio_the_row_asked_for(tmp_path):
    # The row asks J 1.7 at 49.036 m/s and 2200 rev/min. With D = 1.2 m the rotor
    # ran at 49.036 / (36.667 * 1.2) = 1.1145.
    said = _posted_with_a_rotor(tmp_path, 1.2)
    assert len(said) == 1, said
    assert "1.7" in said[0] and "1.1145" in said[0], said[0]


def test_it_says_nothing_when_the_two_agree(tmp_path):
    # D = V / (n J) = 49.036 / (36.6667 * 1.7) = 0.78667 m makes them agree.
    assert _posted_with_a_rotor(tmp_path, 49.036 / ((2200.0 / 60.0) * 1.7)) == []
