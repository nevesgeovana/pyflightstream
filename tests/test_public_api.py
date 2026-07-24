"""Tier 1: the public module list, affirmed (D3, scipy _public_api model).

Pipeline role: quality gate on the package's import surface. The list
below is the affirmative declaration of every public module: a module
is public because it appears here, deprecated because the ledger of
:mod:`pyflightstream._deprecations` records it, or private because its
name starts with an underscore. A newly added module that fits none of
the three fails the classification test, so the public surface only
grows by conscious decision (and, after the v0.3 surface freeze, by a
new release's decision). Lazy loading is deliberately not part of this
adoption (D3 resolution: it waits for heavy extras).
"""

from __future__ import annotations

import importlib
import pkgutil
import warnings

import pyflightstream
from pyflightstream._deprecations import DEPRECATED_MODULES

#: The affirmed public import surface of the package. Order: sorted.
#: Every entry is a documented module a user may import directly; the
#: cli modules are listed public because the console entry points bind
#: to their dotted names.
PUBLIC_MODULES = [
    "pyflightstream.cases",
    "pyflightstream.cases.cli",
    "pyflightstream.cases.matrix",
    "pyflightstream.commands",
    "pyflightstream.exceptions",
    "pyflightstream.farfield",
    "pyflightstream.fsi",
    "pyflightstream.fsi.beam",
    "pyflightstream.fsi.centrifugal",
    "pyflightstream.fsi.cli",
    "pyflightstream.fsi.config",
    "pyflightstream.fsi.driver",
    "pyflightstream.fsi.kinematics",
    "pyflightstream.fsi.loads",
    "pyflightstream.fsi.nodes",
    "pyflightstream.fsi.state",
    "pyflightstream.options",
    "pyflightstream.overview",
    "pyflightstream.post",
    "pyflightstream.post.writers",
    "pyflightstream.probes",
    "pyflightstream.probes.geometry",
    "pyflightstream.probes.planar",
    "pyflightstream.qa",
    "pyflightstream.qa.cli",
    "pyflightstream.qa.compat",
    "pyflightstream.qa.drift",
    "pyflightstream.qa.geometry",
    "pyflightstream.qa.physics",
    "pyflightstream.qa.probes",
    "pyflightstream.qa.specs",
    "pyflightstream.reference",
    "pyflightstream.results",
    "pyflightstream.results.tables",
    "pyflightstream.run",
    "pyflightstream.script",
    "pyflightstream.script.entities",
    "pyflightstream.script.helpers",
    "pyflightstream.script.solver_setup",
    "pyflightstream.script.toggles",
    "pyflightstream.testing",
    "pyflightstream.versions",
    "pyflightstream.workspace",
    "pyflightstream.workspace.cli",
    "pyflightstream.workspace.inputs",
    "pyflightstream.workspace.naming",
]

DEPRECATED_MODULE_NAMES = {entry.module for entry in DEPRECATED_MODULES}

#: Modules an optional extra legitimately gates at import time: these
#: alone may refuse to import, and only with the didactic message
#: naming the install remedy. Everything else in PUBLIC_MODULES must
#: import unconditionally on a base install; in particular the
#: exception catalog and the whole workspace/script/results core.
EXTRA_GATED_MODULES = {
    "pyflightstream.fsi.beam",  # PyNite at import, didactic re-raise
    "pyflightstream.fsi.centrifugal",  # imports beam
    "pyflightstream.fsi.driver",  # imports beam
    "pyflightstream.fsi.cli",  # imports driver
}


def _discovered_modules() -> list[str]:
    """Walk the installed package and list every module.

    walk_packages imports subpackages to iterate them, which fires the
    deprecation shims' import warning; silenced here because listing is
    not use.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return sorted(
            info.name for info in pkgutil.walk_packages(pyflightstream.__path__, "pyflightstream.")
        )


def _is_private(name: str) -> bool:
    return any(part.startswith("_") for part in name.split(".")[1:])


def test_every_module_is_classified():
    """Public, deprecated, or underscored: a fourth state does not exist."""
    unclassified = [
        name
        for name in _discovered_modules()
        if name not in PUBLIC_MODULES
        and name not in DEPRECATED_MODULE_NAMES
        and not _is_private(name)
    ]
    assert not unclassified, (
        f"modules {unclassified} are neither in the affirmed PUBLIC_MODULES "
        "list, nor in the deprecation ledger, nor underscore-private. "
        "Classify each one deliberately: add it to PUBLIC_MODULES (a public "
        "surface change, changelog entry required) or rename it with a "
        "leading underscore."
    )


def test_the_affirmed_list_matches_reality():
    """Every affirmed public module exists; the list never goes stale."""
    discovered = set(_discovered_modules())
    ghosts = [name for name in PUBLIC_MODULES if name not in discovered]
    assert not ghosts, (
        f"PUBLIC_MODULES lists {ghosts} but the package does not provide "
        "them; removing a public module is a breaking surface change that "
        "updates this list, the changelog, and the docs together (NFR-11)."
    )
    assert PUBLIC_MODULES == sorted(PUBLIC_MODULES), (
        "keep PUBLIC_MODULES sorted; the list is read as an inventory"
    )


def test_deprecated_modules_stay_out_of_the_public_list():
    overlap = DEPRECATED_MODULE_NAMES.intersection(PUBLIC_MODULES)
    assert not overlap, (
        f"{sorted(overlap)} are in both PUBLIC_MODULES and the deprecation "
        "ledger; a deprecated module is documented by the ledger alone."
    )


def test_public_modules_import_and_carry_a_docstring():
    """The affirmed surface imports cleanly and is didactically documented.

    Only the modules in EXTRA_GATED_MODULES may refuse the import, and
    only with the documented didactic message naming the install
    remedy; a core module refusing to import is a defect, whatever the
    message says (the architect finding of 2026-07-23: a wrong install
    remedy for a core need is worse than no message).
    """
    for name in PUBLIC_MODULES:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                module = importlib.import_module(name)
        except ImportError as error:
            assert name in EXTRA_GATED_MODULES, (
                f"core module {name} must import on a base install but raised: {error}"
            )
            assert "pip install" in str(error), (
                f"{name} failed to import without naming its install remedy: {error}"
            )
            continue
        assert module.__doc__ and module.__doc__.strip(), (
            f"public module {name} has no docstring; the didactic policy "
            "requires the module top-docstring to state its pipeline role."
        )
