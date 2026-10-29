"""Refusals describe supported remedies and retain only live catalog entries."""

import ast as _e1_ast
import pathlib as _e1_pathlib
import warnings as _e1_warnings

import pytest
from pydantic import ValidationError as _E1ValidationError

import pyflightstream.cases as _e1_cases_package
from pyflightstream import _deprecations
from pyflightstream._errors import (
    DuplicateValueWarning,
    InputValueError,
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream.cases import CampaignConfigError, PprocSpec, SimCase, SweepAxis
from pyflightstream.cases._farfield_spec import TrefftzSpec
from pyflightstream.cases._setup_link import family_indices
from pyflightstream.cases.workflows import build_script
from pyflightstream.options import option_context
from pyflightstream.script import Script


def test_p0410_shedding_refusal_names_the_distinct_ccs_route():
    case = SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"ROTOR_SHEDDING": "AZIMUTH"},
    )
    with option_context("warning_refusals", True), pytest.raises(ValueError) as caught:
        build_script(case, Script(version="26.124"))
    message = str(caught.value)
    assert "7001" in message and "AZIMUTH" in message
    assert "CCS_SHEDDING" in message
    assert "planned for" not in message


def test_p0410_refusal_catalog_contains_only_live_refusals():
    assert set(_deprecations.REFUSED_IN_0_15_0) == {
        _deprecations.ROW_MOVING_BOUNDARIES,
        _deprecations.ROW_ROTATE_FAMILIES,
        _deprecations.ROW_EACH_BLADE,
        _deprecations.ROW_AIRFRAME_SELECTOR,
        _deprecations.ROW_BLADES_SELECTOR,
    }


# ---- lane E1, 0.50.0 (FR-3374 to FR-3380): the cases subpackage's refusals ----
_CASES = _e1_pathlib.Path(_e1_cases_package.__file__).parent


def _case() -> SimCase:
    return SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
    )


def test_fr3374_a_repeated_trefftz_variant_warns_and_is_read_once_or_refuses():
    with pytest.warns(DuplicateValueWarning, match="repeats wake"):
        spec = TrefftzSpec(variant=["wake", "wake"])
    assert list(spec.variant) == ["wake"]
    with option_context("warning_refusals", True):
        with pytest.raises(_E1ValidationError, match="repeats wake"):
            TrefftzSpec(variant=["wake", "wake"])


def test_fr3375_an_empty_preset_family_list_refuses_under_every_policy():
    kwargs = {"keyword": "families", "preset_key": "vorticity_drag_families", "dropped": "x"}
    with pytest.raises(CampaignConfigError, match="EMPTY selection"):
        family_indices(_case(), None, [], **kwargs)
    with option_context("warning_refusals", True):
        with pytest.raises(CampaignConfigError, match="EMPTY selection"):
            family_indices(_case(), None, [], **kwargs)


def test_fr3376_user_input_raises_of_cases_are_input_errors_keeping_their_base():
    offenders = []
    for path in sorted(_CASES.rglob("*.py")):
        for node in _e1_ast.walk(_e1_ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, _e1_ast.Raise) and isinstance(node.exc, _e1_ast.Call):
                name = getattr(node.exc.func, "id", "")
                if name in {"ValueError", "KeyError", "TypeError"}:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
    assert issubclass(InputValueError, (PyflightstreamError, ValueError))


def test_fr3377_a_pproc_validator_refusal_is_an_input_error_with_its_remedy():
    with pytest.raises(_E1ValidationError, match="Declare sections.distributions") as caught:
        PprocSpec.model_validate({"products": {"boundary_layer_integrals": True}})
    assert caught.value.errors()


def test_fr3378_every_warning_of_cases_passes_a_pyflightstream_category():
    untyped = []
    for path in sorted(_CASES.rglob("*.py")):
        for node in _e1_ast.walk(_e1_ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, _e1_ast.Call):
                func = node.func
                if (
                    isinstance(func, _e1_ast.Attribute)
                    and func.attr == "warn"
                    and getattr(func.value, "id", "") == "warnings"
                ):
                    untyped.append(f"{path.name}:{node.lineno}")
    assert untyped == []
    assert issubclass(DuplicateValueWarning, PyflightstreamWarning)


@pytest.mark.parametrize(
    "table,key,suggestion",
    [
        (
            {"sections": {"distributions": []}, "products": {"boundry_layer_integrals": True}},
            "boundry_layer_integrals",
            "boundary_layer_integrals",
        ),
        ({"sectoins": {}}, "sectoins", "sections"),
    ],
)
def test_fr3379_an_unknown_pproc_key_names_the_closest_known_key(table, key, suggestion):
    with pytest.raises(_E1ValidationError) as caught:
        PprocSpec.model_validate(table)
    errors = [e for e in caught.value.errors() if e["loc"][-1] == key]
    assert errors and errors[0]["type"] == "extra_forbidden"
    assert f"Did you mean '{suggestion}'?" in errors[0]["msg"]


def test_fr3380_an_unknown_pproc_key_with_no_close_name_names_none():
    with pytest.raises(_E1ValidationError) as caught:
        PprocSpec.model_validate({"zzzzqqqq": 1})
    message = caught.value.errors()[0]["msg"]
    assert "Did you mean" not in message
    assert message == "Extra inputs are not permitted"
    with _e1_warnings.catch_warnings():
        _e1_warnings.simplefilter("error")
        PprocSpec.model_validate({})
