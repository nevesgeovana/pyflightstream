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
import re
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
    """One except clause must catch every CATALOGUED exception (FR-39).

    What it does not catch is the residual of bare standard-library
    raises named in the ``_RATCHET`` below, which is why the word
    matters here as much as in the three shipped documents that point
    at this file.

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
        "CommandDatabaseError": ValueError,
        "CommandNotInVersionError": LookupError,
        "ExecutorConfigurationError": ValueError,
        "FarfieldInputError": ValueError,
        "FieldNotInExportError": KeyError,
        "FsiInputError": ValueError,
        "GeometryEngineMissingError": ImportError,
        "IncompleteOutputError": ValueError,
        "InputArtifactError": RuntimeError,
        "LoadsNotFoundError": ValueError,
        "MalformedOutputError": ValueError,
        "ManualDraftError": ValueError,
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
#
# WIDENED TWICE ON 2026-08-04 and 70 is no longer the population: first to
# the modules that declare no `__all__`, which found 46 more, then to
# REACHABILITY through a module-private helper a public definition calls,
# which found 21 more. 137 measured, 113 fixed, 24 in the ratchet below.
# SRS FR-39 carries the three numbers and the walk's stated reach; this
# file carries the residual itself.

_BARE = {"ValueError", "RuntimeError", "TypeError", "KeyError", "LookupError", "ImportError"}


#: Decorators after which a bare ``ValueError`` is the documented way to
#: signal failure: pydantic converts it into ``ValidationError`` before
#: any caller sees it, so the raise never reaches the public surface as
#: a bare standard-library error. Everything else is in scope.
_WRAPPED_BY_PYDANTIC = {"field_validator", "model_validator", "validator", "root_validator"}


def _is_validator(node) -> bool:
    """Whether this definition's raises are converted by pydantic."""
    import ast

    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = getattr(target, "id", None) or getattr(target, "attr", "")
        if name in _WRAPPED_BY_PYDANTIC:
            return True
    return False


def _bare_raises_in(module_name: str, filename: str, source: str, exported: set[str]) -> list[str]:
    """Every bare stdlib raise inside a public callable of one module.

    Separated from the walk over modules so the guard and its mutation
    proof run the SAME code. They did not: the proof re-implemented the
    walk inline over a synthetic tree and never called the detector, so
    replacing the detector with ``lambda: []`` passed every test in this
    file. Its own docstring said that was the failure it existed to
    prevent (QA pass, 2026-08-03).

    ``exported`` is the module's ``__all__``. An EMPTY set means the
    module declares none, and then every non-underscore top-level
    definition is public, because that is Python's own default and what
    ``from module import *`` and ``help()`` present. Skipping those
    modules is how the first version of this guard measured 70 offenders
    while 27 public modules and about 50 further sites sat outside its
    reach, with FR-39 published as implemented over the gap.
    """
    import ast

    offenders: list[str] = []
    tree = ast.parse(source)
    # Names registered as ``validator=<name>`` somewhere in this module.
    # The registry that consumes them catches ValueError and re-raises
    # the catalogued class (`options.py:151`), so a bare raise inside one
    # never reaches a caller bare. Detected rather than allowlisted: an
    # allowlist would need editing every time a validator is added, and
    # the edit that forgets is invisible.
    wrapped_validators = {
        keyword.value.id
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "validator" and isinstance(keyword.value, ast.Name)
    }
    # Module-private helpers CALLED from a public definition. FR-39 asks
    # for a property of what the public API raises, which is
    # REACHABILITY; walking only where the raise is written measures
    # lexical enclosure instead, and a bare raise inside a private helper
    # reaches the caller exactly as before. The architect and
    # API-designer passes measured the difference at four modules
    # (2026-08-03). One level, which closes every site they named.
    defined = {
        node.name: node
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    reachable: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        public = node.name in exported if exported else not node.name.startswith("_")
        if not public:
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call):
                called = getattr(call.func, "id", None)
                if called and called.startswith("_") and called in defined:
                    reachable.add(called)

    for node in ast.iter_child_nodes(tree):
        if node.__class__.__name__ in {"FunctionDef", "AsyncFunctionDef"} and (
            node.name in wrapped_validators
        ):
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        public = node.name in exported if exported else not node.name.startswith("_")
        if not public and node.name not in reachable:
            continue
        for sub in ast.walk(node):
            if _is_validator(sub) and sub is not node:
                continue
            if not (isinstance(sub, ast.Raise) and isinstance(sub.exc, ast.Call)):
                continue
            owner = sub
            raised = getattr(sub.exc.func, "id", None) or getattr(sub.exc.func, "attr", "")
            if raised not in _BARE:
                continue
            # A raise inside a validator method of a public model is
            # pydantic's own idiom; find the nearest enclosing def.
            enclosing = [
                child
                for child in ast.walk(node)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(owner is inner for inner in ast.walk(child))
            ]
            if any(_is_validator(child) for child in enclosing):
                continue
            offenders.append(f"{module_name}.{node.name} -> {raised} ({filename}:{sub.lineno})")
    return offenders


def _public_module_sources() -> list[tuple[str, str, str, set[str]]]:
    """Every importable public module as (name, filename, source, __all__)."""
    import importlib
    import warnings

    from test_public_api import PUBLIC_MODULES

    found = []
    for name in PUBLIC_MODULES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue  # an extra is not installed; covered by test_extras
        if not getattr(module, "__file__", None):
            continue
        source = Path(module.__file__)
        found.append(
            (
                name,
                source.name,
                source.read_text(encoding="utf-8"),
                set(getattr(module, "__all__", []) or []),
            )
        )
    return found


def _exported_bare_raises() -> list[str]:
    """Every `raise BareStdlibError(...)` inside a public name."""
    offenders: list[str] = []
    for name, filename, source, exported in _public_module_sources():
        offenders += _bare_raises_in(name, filename, source, exported)
    return offenders


#: The sites FR-39 does not yet cover, named one by one with the reason
#: and the plan row that closes them. A RATCHET, in the shape NFR-27
#: already uses for the type checker: the list IS the debt, it is
#: countable, and any site THE WALK REACHES that is not on it fails
#: today. That qualifier is load-bearing and was missing here while this
#: file was being named, in three shipped documents, as the single home
#: of the residual. A definition omitted from its own module's
#: ``__all__`` is invisible to the walk: ``script.solver_setup.
#: build_setup`` raises a bare ``RuntimeError``, is reachable through a
#: cross-module caller, is on no list and does not fail today
#: (PLN-20260804-1130).
#:
#: The set holds 27 entries in two tranches. The FIRST THREE raise
#: ``TypeError`` for an argument of a type the function does not accept;
#: the other 24 are the reachability tranche and are almost all
#: ``ValueError``. Re-basing the TypeError three onto a catalogued class
#: is not the
#: one-line change the ValueError sites were: ``except TypeError`` is
#: how a caller distinguishes "I passed the wrong kind of thing" from "I
#: passed a bad value", and the catalogued classes this package has are
#: all ``ValueError``-based, so the fix needs a new base and a decision
#: about what it means. Deferred rather than rushed the night before a
#: tag (PLN-20260803-2340).
_RATCHET = {
    # TypeError for an argument of an unaccepted type. The catalogue is
    # entirely ValueError-based, so re-basing these needs a new base and
    # a decision about what it means (PLN-20260803-2340).
    "pyflightstream.results.tables.to_table -> TypeError (tables.py:161)",
    "pyflightstream.results.tables.to_table -> TypeError (tables.py:174)",
    "pyflightstream.script.entities.EntityRegistry -> TypeError (entities.py:282)",
    # The REACHABILITY tranche, measured 2026-08-04: a bare stdlib raise
    # inside a module-private helper that a public definition calls
    # reaches a caller exactly as an exported one does. The walk used to
    # measure where a raise is WRITTEN; FR-39 asks what the public API
    # RAISES. The author's decision: measure now, fix at v0.5, so the
    # number is the debt and it is countable (PLN-20260804-0130).
    "pyflightstream.cases.cli._parse_recipes -> ValueError (cli.py:33)",
    # SEVEN sites on the pydantic validation path, where ValueError IS the
    # protocol. They move down the file whenever anything is inserted
    # above them, and did so twice: on 2026-08-07 when the all-entities
    # sentinel, the entity citation and the fixed payload length joined
    # ArgSpec, and again on 2026-08-08 when the Mesh Wrapper chapter
    # needed `on_command_line` and brought two new layout rules with it.
    # The ratchet keys on the line number, so re-anchoring is deliberate
    # friction rather than a defect: a moved raise should be re-read.
    #
    # The count went 5 to 7 in that second move, which is new debt and
    # not only a re-anchor. It is taken deliberately: these two refusals
    # sit beside five that already raise the same way on the same path,
    # and giving two of a family a catalogued base while five keep the
    # bare one would make the family harder to read, not easier. They go
    # with the rest under PLN-20260804-0130.
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:429)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:431)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:433)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:441)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:455)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:461)",
    "pyflightstream.commands._check_layout_rules -> ValueError (__init__.py:471)",
    "pyflightstream.farfield._delta_psi -> ValueError (__init__.py:152)",
    "pyflightstream.fsi.driver._verified_layout -> ValueError (driver.py:338)",
    "pyflightstream.fsi.loads._validate_block_boundaries -> ValueError (loads.py:397)",
    "pyflightstream.fsi.loads._validate_block_boundaries -> ValueError (loads.py:409)",
    # This one moved from 124 to 125 when a row was added to
    # _SIDE_BRANCHES above it, and the edit failed the stale-exemption
    # test and the uncovered-site test at once. That is how a moved debt
    # site announces itself, and why both directions are asserted.
    "pyflightstream.overview._module_doc -> RuntimeError (overview.py:125)",
    "pyflightstream.post.writers._checked -> ValueError (writers.py:34)",
    "pyflightstream.post.writers._checked -> ValueError (writers.py:39)",
    "pyflightstream.probes.planar._unit -> ValueError (planar.py:50)",
    "pyflightstream.qa.compat._rewrite_version_line -> ValueError (compat.py:381)",
    "pyflightstream.qa.compat._rewrite_version_line -> ValueError (compat.py:399)",
    "pyflightstream.results._parse_solver_flag -> ValueError (__init__.py:503)",
    "pyflightstream.results.tables._as_record -> ValueError (tables.py:538)",
    "pyflightstream.results.tables._check_point_printback -> ValueError (tables.py:572)",
    "pyflightstream.results.tables._run_row -> ValueError (tables.py:486)",
    "pyflightstream.results.tables._run_row -> ValueError (tables.py:506)",
    "pyflightstream.results.tables._sectional_loads_frame -> ValueError (tables.py:448)",
}


def test_the_ratchet_holds_only_sites_that_still_exist() -> None:
    """An exemption for a site that is gone is an exemption for nothing.

    A stale entry silently widens the guard: the next offender to land
    on that line number inherits the exemption. This is what makes the
    list a ratchet rather than a drawer.
    """
    stale = _RATCHET - set(_exported_bare_raises())
    assert not stale, (
        f"the FR-39 ratchet exempts {sorted(stale)}, which the walk no longer "
        "reports. Delete the entry: an exemption outliving its site is how a "
        "guard quietly stops guarding"
    )


def test_no_exported_public_name_raises_a_bare_stdlib_error() -> None:
    offenders = [entry for entry in _exported_bare_raises() if entry not in _RATCHET]
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

    It calls `_bare_raises_in`, the function the guard calls. The first
    version of this test re-implemented the walk inline and never
    touched the detector, so patching `_exported_bare_raises` to return
    an empty list passed every test in this file while its own docstring
    claimed that was the failure it prevented.
    """
    source = (
        "def f():\n"
        "    raise ValueError('x')\n"
        "def _g():\n"
        "    raise ValueError('y')\n"
        "def h():\n"
        "    raise CampaignConfigError('z')\n"
    )
    # With an __all__: only the exported name is walked.
    assert _bare_raises_in("m", "m.py", source, {"f"}) == ["m.f -> ValueError (m.py:2)"]
    # Without one: every non-underscore definition is public, and the
    # underscore-private one is still skipped.
    assert _bare_raises_in("m", "m.py", source, set()) == ["m.f -> ValueError (m.py:2)"]
    # A catalogued class is not an offender.
    catalogued = "def h():\n    raise CampaignConfigError('z')\n"
    assert _bare_raises_in("m", "m.py", catalogued, set()) == []


def test_the_detector_skips_what_pydantic_converts() -> None:
    """A validator's ValueError never reaches a caller as a bare one."""
    source = (
        "class M:\n"
        "    @field_validator('x')\n"
        "    def _check(cls, v):\n"
        "        raise ValueError('bad')\n"
        "    def method(self):\n"
        "        raise ValueError('reaches the caller')\n"
    )
    found = _bare_raises_in("m", "m.py", source, set())
    assert found == ["m.M -> ValueError (m.py:6)"], (
        f"expected only the plain method to be reported, got {found}. A validator's "
        "raise is converted into ValidationError by pydantic before any caller sees "
        "it; a plain method's is not"
    )


def test_the_walk_reaches_the_whole_public_surface() -> None:
    """Floors, so a walk that stops matching is not a pass.

    The scope defect this file had was invisible precisely because the
    guard reported zero offenders over a shrinking surface. These
    numbers assert the surface, not the verdict.
    """
    sources = _public_module_sources()
    without_all = [name for name, _f, _s, exported in sources if not exported]
    assert len(sources) >= 40, (
        f"only {len(sources)} public module(s) were read; the walk has lost its "
        "subject and a clean verdict would mean nothing"
    )
    assert without_all, (
        "every public module now declares __all__, so the branch that made this "
        "guard blind to 27 of them is untested. Keep a case or drop the branch"
    )
    total_raises = sum(source.count("raise ") for _n, _f, source, _e in sources)
    assert total_raises >= 200, (
        f"the public modules hold {total_raises} raise statement(s), far fewer than "
        "this package has; the module list is probably not resolving"
    )


def test_no_keyerror_based_class_renders_its_message_in_quotes() -> None:
    """A didactic message must survive ``str()`` unchanged.

    ``KeyError.__str__`` is ``repr`` of its argument, so a catalogued
    class with ``KeyError`` as its second base prints its careful
    sentence wrapped in quotes, with any newline escaped. ``OptionError``
    solved this with a three-line ``__str__`` and nothing generalised
    it, so ``FieldNotInExportError`` shipped with the defect and the
    release audit found it. The rule is mechanical: derive from
    ``KeyError``, override ``__str__``.

    Invariant 8 is what this enforces. An error message that names the
    physical or version cause is worth nothing if the reader is shown
    ``"...\n..."`` instead of the sentence.
    """
    import pyflightstream.exceptions as catalog

    sentence = "the field is absent.\nDeclare it in the export first."
    offenders = []
    checked = 0
    for name in catalog.__all__:
        cls = getattr(catalog, name)
        if not isinstance(cls, type) or not issubclass(cls, KeyError):
            continue
        checked += 1
        if str(cls(sentence)) != sentence:
            offenders.append(f"{name} renders {str(cls(sentence))!r} for a plain sentence")
    assert checked >= 2, (
        f"only {checked} KeyError-based classes were found in the catalog; the walk "
        "is not reaching them"
    )
    assert not offenders, (
        "\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nKeyError.__str__ is repr of its argument, so these print their message "
        "in quotes with newlines escaped. Override __str__ as OptionError does."
    )


def test_the_ratchet_comment_counts_the_ratchet():
    """The debt count is stated in prose above a set that can change.

    Both numbers in that comment were hand-written and nothing read
    them, so adding the inline-separator refusal on 2026-08-06 left
    "24 entries" sitting above 25. The count is the one thing a reader
    checks the comment for, since the whole point of the ratchet is that
    the number goes down; a stale one reads as progress.

    The set is the single home and the comment is checked against it,
    rather than the two being maintained side by side.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    header = source.split("_RATCHET = {")[0]
    total = re.search(r"The set holds (\d+) entries", header)
    reachability = re.search(r"the other (\d+) are the reachability tranche", header)
    assert total and reachability, (
        "the ratchet comment no longer states its counts in the shape this test "
        "reads; state them or delete this guard, but do not leave it matching nothing"
    )
    type_errors = sum(1 for entry in _RATCHET if "-> TypeError" in entry)
    assert int(total.group(1)) == len(_RATCHET), (
        f"the comment says {total.group(1)} entries and the set holds {len(_RATCHET)}"
    )
    assert int(reachability.group(1)) == len(_RATCHET) - type_errors, (
        f"the comment says {reachability.group(1)} in the reachability tranche and the "
        f"set holds {len(_RATCHET) - type_errors} entries that are not TypeError"
    )
