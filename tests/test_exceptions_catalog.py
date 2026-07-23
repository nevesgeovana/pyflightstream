"""Tier 1: the exception catalog is complete and structured (PLN-045).

Pipeline role: quality gate on the pandas-errors-model catalog of
:mod:`pyflightstream.exceptions`. Completeness is mechanical: every
exception or warning class defined anywhere in the package must be
importable from the catalog, so user code never hunts pipeline layers
for the right ``except`` clause. The structured refusals are checked
attribute by attribute.
"""

from __future__ import annotations

import importlib
import inspect
import warnings

import pytest
from test_public_api import PUBLIC_MODULES

from pyflightstream import exceptions
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError


def _defined_exception_classes() -> dict[str, type]:
    """Every exception class defined in a public pyflightstream module."""
    found: dict[str, type] = {}
    for name in PUBLIC_MODULES:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                module = importlib.import_module(name)
        except ImportError:  # optional extra absent; its didactic refusal
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseException)
                and obj.__module__.startswith("pyflightstream")
                and not obj.__name__.startswith("_")
            ):
                found[obj.__name__] = obj
    return found


def test_every_defined_exception_is_in_the_catalog():
    """A new exception class must join pyflightstream.exceptions."""
    missing = {
        name: cls.__module__
        for name, cls in _defined_exception_classes().items()
        if not hasattr(exceptions, name)
    }
    assert not missing, (
        f"exception classes {missing} are defined in the package but not "
        "importable from pyflightstream.exceptions; add each to the catalog "
        "in the same commit that defines it (single public catalog, "
        "pandas errors model)."
    )


def test_the_catalog_all_matches_its_names():
    for name in exceptions.__all__:
        cls = getattr(exceptions, name)
        assert issubclass(cls, BaseException), f"{name} in __all__ is not an exception"
    assert exceptions.__all__ == sorted(exceptions.__all__), (
        "keep the catalog __all__ sorted; it is read as an inventory"
    )


# --- structured refusals ----------------------------------------------------


def test_unknown_version_error_carries_version_and_known():
    from pyflightstream.versions import UnknownVersionError, resolve

    with pytest.raises(UnknownVersionError) as caught:
        resolve("27.000")
    assert caught.value.version == "27.000"
    assert "26.120" in caught.value.known
    assert caught.value.known == tuple(sorted(caught.value.known, key=caught.value.known.index))


def test_input_artifact_miss_carries_kind_id_and_available(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "references" / "wing_v2.toml").write_text("", encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        workspace.resolve_reference("wing_v9")
    assert caught.value.kind == "reference"
    assert caught.value.artifact_id == "wing_v9"
    assert caught.value.available == ("wing_v2",)


def test_input_artifact_id_refusal_carries_kind_and_id(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(InputArtifactError) as caught:
        workspace.resolve_reference("../outside")
    assert caught.value.kind == "reference"
    assert caught.value.artifact_id == "../outside"
    assert caught.value.available == ()
