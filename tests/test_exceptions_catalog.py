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
from pathlib import Path

import pytest
from test_public_api import PUBLIC_MODULES

from pyflightstream import exceptions
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError


def _defined_exception_classes() -> dict[str, type]:
    """Every exception class visible in a public pyflightstream module.

    The scan walks PUBLIC_MODULES members: an exception defined in an
    underscore-private module and never re-exported publicly would
    escape it, so that pattern is banned by convention (refusals are
    public surface; define them in, or re-export them into, a public
    module).
    """
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


@pytest.mark.requirement("FR-39")
def test_every_catalogued_exception_descends_from_the_package_base():
    """One except clause must catch everything the package raises (FR-39).

    The totality companion of the membership test above: that one fails
    when a class does not JOIN the catalog, this one fails when a class
    joins it without joining the hierarchy. Both are needed, because a
    catalogued class that derives only from a builtin is invisible to
    `except PyflightstreamError` while looking perfectly present in
    `__all__`.

    Warnings are deliberately outside the hierarchy. FR-39 asks for a
    base of every raised EXCEPTION and a catalog of every exception AND
    warning; those are two different sets, and a warning delivered
    through the warnings machinery and selected by category is not an
    Error whatever else it is.
    """
    catalogued = {name: getattr(exceptions, name) for name in exceptions.__all__}
    errors = {
        name: cls
        for name, cls in catalogued.items()
        if not (isinstance(cls, type) and issubclass(cls, Warning))
    }
    assert errors, "the catalog holds no exceptions at all; the scan is broken"

    orphans = {
        name: [base.__name__ for base in cls.__mro__[1:] if base is not object]
        for name, cls in errors.items()
        if not issubclass(cls, exceptions.PyflightstreamError)
    }
    assert not orphans, (
        f"catalogued exceptions {sorted(orphans)} do not descend from "
        "PyflightstreamError, so `except PyflightstreamError` misses them; give "
        "each the base as its FIRST base and keep its standard-library base as "
        f"the second. Their bases today: {orphans}"
    )


def test_the_package_base_does_not_widen_what_the_builtin_bases_caught():
    """Adding the base must not have moved any class off its builtin.

    The whole promise of the change is that it is additive, so this
    pins the standard-library base of every catalogued exception. If a
    later edit re-parents one of these onto a different builtin (or
    drops the builtin entirely), code in the wild that catches
    ValueError or RuntimeError silently stops catching it.
    """
    expected_builtin = {
        "AmbiguousLoadsError": ValueError,
        "AmbiguousVersionAliasError": ValueError,
        "CampaignConfigError": ValueError,
        "AnchorNotFoundError": ValueError,
        "BrokenCommandError": RuntimeError,
        "CampaignErrors": RuntimeError,
        "CommandArgumentError": ValueError,
        "CommandNotInVersionError": LookupError,
        "ExecutorConfigurationError": ValueError,
        "FarfieldInputError": ValueError,
        "FieldNotInExportError": KeyError,
        "GeometryEngineMissingError": ImportError,
        "IncompleteOutputError": ValueError,
        "InputArtifactError": RuntimeError,
        "LoadsNotFoundError": ValueError,
        "MalformedOutputError": ValueError,
        "MatrixError": ValueError,
        "MissingExtraError": ImportError,
        "NamingTemplateError": ValueError,
        "OpenMeshError": ValueError,
        "OptionError": KeyError,
        "ProbeGeometryError": ValueError,
        "QaEvidenceError": ValueError,
        "PhysicsEnvironmentError": RuntimeError,
        "ProbeEnvironmentError": RuntimeError,
        "ScriptLabelError": ValueError,
        "ScriptLineBreakError": ValueError,
        "ScriptOrderError": ValueError,
        "ScriptReferenceError": ValueError,
        "StaleLoadsError": ValueError,
        "SurfaceMeshExportError": RuntimeError,
        "TwistIterationError": RuntimeError,
        "UnitsError": ValueError,
        "UnknownVersionError": ValueError,
        "UnknownExtraError": ValueError,
        "VersionMismatchWarning": UserWarning,
        "WorkspaceError": RuntimeError,
    }
    catalogued = set(exceptions.__all__) - {"PyflightstreamError"}
    assert catalogued == set(expected_builtin), (
        "the catalog changed without this table moving with it; add the new "
        "class and the standard-library base its users are entitled to keep"
    )
    for name, builtin in expected_builtin.items():
        assert issubclass(getattr(exceptions, name), builtin), (
            f"{name} no longer derives from {builtin.__name__}; that silently "
            "breaks every caller catching the builtin"
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
    from pyflightstream.versions import UnknownVersionError, known_versions, resolve

    with pytest.raises(UnknownVersionError) as caught:
        resolve("27.000")
    assert caught.value.version == "27.000"
    assert "26.120" in caught.value.known
    # Release order per the registered list, the only ordering authority.
    assert caught.value.known == tuple(v.canonical for v in known_versions())


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


# --- FR-39, the clause the class-level guards could not see ----------------
#
# The two guards above assert things about exception CLASSES: that each is
# catalogued and that each descends from the base. Neither looks at a
# `raise` statement, so a public function raising a bare ValueError was
# invisible to both, and FR-39's first clause ("every exception raised by
# the public API derives from a single documented base") was false in 70
# places while the requirement read implemented.
#
# Measured 2026-08-03 after an independent review flagged three of them.
# Three was the number I reported from reading the finding; 70 is the
# number from walking the tree, which is the difference this guard exists
# to remove.

_BARE = {"ValueError", "RuntimeError", "TypeError", "KeyError", "LookupError", "ImportError"}


def _exported_bare_raises() -> list[str]:
    """Every `raise BareStdlibError(...)` inside an exported public name."""
    import ast
    import importlib
    import warnings

    from test_public_api import PUBLIC_MODULES

    offenders: list[str] = []
    for name in PUBLIC_MODULES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue  # an extra is not installed; covered by test_extras
        exported = set(getattr(module, "__all__", []) or [])
        if not exported or not getattr(module, "__file__", None):
            continue
        source = Path(module.__file__)
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue
            if node.name not in exported:
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Call):
                    raised = getattr(sub.exc.func, "id", None) or getattr(sub.exc.func, "attr", "")
                    if raised in _BARE:
                        offenders.append(
                            f"{name}.{node.name} -> {raised} ({source.name}:{sub.lineno})"
                        )
    return offenders


def test_no_exported_public_name_raises_a_bare_stdlib_error() -> None:
    offenders = _exported_bare_raises()
    assert not offenders, (
        f"{len(offenders)} raise site(s) inside exported public names raise a bare "
        "standard-library exception, so `except PyflightstreamError` does not catch "
        "them and FR-39's first clause is false there. Raise the catalogued class "
        "for the condition; every one of them keeps its standard-library base, so "
        "an existing `except ValueError` catches exactly what it caught before.\n  "
        + "\n  ".join(sorted(offenders)[:15])
    )


def test_the_bare_raise_detector_can_find_one() -> None:
    """Mutation proof for the walker the guard rests on.

    Without it, a detector that returned an empty list would report the
    requirement satisfied forever, which is the shape this whole sweep
    was raised about.
    """
    import ast

    tree = ast.parse(
        "__all__ = ['f']\n"
        "def f():\n"
        "    raise ValueError('x')\n"
        "def _g():\n"
        "    raise ValueError('y')\n"
    )
    found = [
        sub
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "f"
        for sub in ast.walk(node)
        if isinstance(sub, ast.Raise)
        and isinstance(sub.exc, ast.Call)
        and getattr(sub.exc.func, "id", "") in _BARE
    ]
    assert len(found) == 1
