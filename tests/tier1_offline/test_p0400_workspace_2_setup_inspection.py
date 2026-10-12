"""P0400-SETUPINSPECT: the setup inspection reports the row override the builder uses."""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import row_ncpus, row_symmetry_loads
from pyflightstream.workspace.setup_inspection import inspect_case_setup


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
