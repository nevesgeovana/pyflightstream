"""Input declarations must retain one unambiguous meaning."""

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.post._tables import ProductError, renamed_columns
from pyflightstream.workspace.inputs import SetupArtifact
from pyflightstream.workspace.matrix import _solver_from_setup


@pytest.mark.parametrize("enabled", [True, False])
def test_stabilization_cannot_be_stated_through_both_interfaces(enabled):
    setup = SetupArtifact(
        settings={
            "stabilization": enabled,
            "stabilization_strength": 0.2,
            "solver_stabilization": 0.8,
        }
    )
    with pytest.raises(InputArtifactError, match="solver_stabilization"):
        _solver_from_setup(setup, "s900")


@pytest.mark.parametrize(
    "names",
    [
        {"FX_A": "FY_A", "FY_A": "SIDE"},
        {"FX_A": "FY_A", "FY_A": "FX_A"},
    ],
)
def test_names_cannot_take_an_existing_column_even_when_it_is_also_renamed(names):
    # The definition of record forbids a destination the table ALREADY carries.
    with pytest.raises(ProductError, match="already carries"):
        renamed_columns(("FX_A", "FY_A"), names, printed=("FX_A", "FY_A"), where="p.csv")


def test_identity_rename_and_fresh_names_remain_valid():
    assert renamed_columns(
        ("FX_A", "FY_A"),
        {"FX_A": "FX_A", "FY_A": "SIDE"},
        printed=("FX_A", "FY_A"),
        where="p.csv",
    ) == ("FX_A", "SIDE")
