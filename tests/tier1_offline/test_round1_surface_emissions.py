"""Pin surface emissions to the command database's argument order and payloads.

The goldens cover the main script from surface initialization through close,
and the complete per-step export body. No interpreter-dependent paths occur.
"""

from pathlib import Path

import pytest

from pyflightstream.cases.workflows import unsteady_export_threshold
from tests.tier1_offline.test_surface_exports import _case, _script, _verified_registry

GOLDENS = Path(__file__).parent / "goldens"


def _emissions():
    case = _case(
        rotor=True,
        time_averaging={"last_revs": 1.5},
        vtk_variables=["X", "CP_FREESTREAM"],
        threshold={"EXPORT_UNSTEADY_AFTER_ITER": "91"},
    )
    # G25 of 0.28.0: nothing of the window is emitted (SOLVER_TIME_AVERAGING
    # hangs 26.124 and is never sent), even where the command is verified; the
    # main script is pinned from its initialisation on.
    main = _script(case, registry=_verified_registry()).render()
    return {
        "main": main[main.index("INITIALIZE_SOLVER") :],
        "action": unsteady_export_threshold(case, version="26.124").exports,
    }


@pytest.mark.parametrize("kind", ["main", "action"])
def test_surface_variables_precede_export(kind):
    text = _emissions()[kind]
    assert text.index("SET_VTK_EXPORT_VARIABLES") < text.index("EXPORT_SOLVER_ANALYSIS_VTK"), (
        f"{kind}: VTK variables configured after export"
    )


@pytest.mark.parametrize("kind", ["main", "action"])
def test_surface_emissions_match_database_golden(kind):
    assert (
        _emissions()[kind].encode("utf-8") == (GOLDENS / f"round1_surface_{kind}.txt").read_bytes()
    ), f"{kind}: surface emissions differ from reviewed command bytes"
