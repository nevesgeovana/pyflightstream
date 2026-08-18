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

# WIDENED A THIRD TIME ON 2026-08-17, by one name. `FileExistsError` was
# not in this set, so the walk could not SEE the bare raises of it and
# they were neither fixed nor ratcheted: they were invisible, which is a
# worse state than either, because the ratchet below reads as the
# complete residual. A review pass found one, not the guard. Every site
# it now reaches is either catalogued or named in the ratchet with its
# reason, which is the property this file claims about itself.
_BARE = {
    "ValueError",
    "RuntimeError",
    "TypeError",
    "KeyError",
    "LookupError",
    "ImportError",
    "FileExistsError",
}


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
            offenders.append(f"{module_name}.{node.name} -> {raised}")
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
    """Every `raise BareStdlibError(...)` inside a public name.

    ONE ENTRY PER (definition, exception type), and it carried the LINE
    NUMBER until 2026-08-18. Two things were wrong with that and the
    ratchet's own comment already named the worse one.

    It CHURNED: any edit above a raise, a comment or a docstring
    paragraph, turned the suite red on a file whose behaviour had not
    moved. The entry for `refuse_existing_report` moved five times on
    2026-08-18 alone, every one a docstring edit. A maintainer who meets
    that four times learns to update the number without reading, which
    is the reflex a ratchet exists to prevent.

    And it could EXEMPT A SITE NOBODY READ. Insertions above a function
    shifted eight sites at v0.5.0 and the shifted set overlapped the
    recorded one, so an entry recorded for one raise silently came to
    name a different one.

    Dropping the line reopens exactly one hole, a SECOND bare raise of
    the same type appearing in an already-exempted definition, and
    `_bare_raises_in` returns one entry per raise, so the count below
    closes it: the walk's multiset is compared against the ratchet, not
    just its set.
    """
    offenders: list[str] = []
    for name, filename, source, exported in _public_module_sources():
        offenders += _bare_raises_in(name, filename, source, exported)
    return offenders


def test_no_exempted_definition_grew_a_second_bare_raise_of_the_same_type() -> None:
    """The hole dropping the line number would otherwise open.

    Keying on (definition, type) means a second bare raise of the same
    type inside an already-exempted definition would inherit the
    exemption silently. The walk emits one entry per RAISE, so counting
    them closes it: an exempted pair may appear exactly as many times as
    the ratchet was measured against.
    """
    from collections import Counter

    counted = Counter(_exported_bare_raises())
    grown = {entry: seen for entry, seen in counted.items() if seen > _RATCHET_COUNTS.get(entry, 0)}
    assert not grown, (
        "an exempted definition raises the same bare type more often than the ratchet "
        "was measured against, so a NEW offender is inheriting an existing exemption: "
        + "; ".join(f"{entry} appears {seen} times" for entry, seen in sorted(grown.items()))
    )
    # AND THE COUNT IS TIGHT, not merely a ceiling. A `>` comparison alone
    # leaves a free exemption slot: re-base one of an exempted pair's two
    # raises onto a catalogued class and the entry still EXISTS, so the
    # stale-entry test passes, while the count stays at 2 over one real
    # raise and the next offender in that definition inherits the spare.
    # That is the same "an exemption outliving its site" failure the
    # sibling test exists for, one field over.
    slack = {
        entry: (recorded, counted.get(entry, 0))
        for entry, recorded in _RATCHET_COUNTS.items()
        if counted.get(entry, 0) < recorded
    }
    assert not slack, (
        "the ratchet reserves more raises than exist, which leaves a free exemption "
        "slot for the next offender in the same definition. That is PROGRESS: lower "
        "the number in the same commit, so the ratchet keeps ratcheting. "
        + "; ".join(
            f"{entry} reserves {recorded} and raises {seen}"
            for entry, (recorded, seen) in sorted(slack.items())
        )
    )


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
#: The set holds 15 entries in three tranches, over 19 raise sites: it
#: is keyed on (definition, exception type) since 2026-08-18, and FOUR
#: definitions raise the same type twice: `to_table`, `_run_row`,
#: `_checked` and `_validate_block_boundaries`. Fifteen pairs plus those
#: four second raises is nineteen. TWO pairs raise ``TypeError``
#: for an argument of a type the function does not accept; ONE raises
#: ``FileExistsError`` and is the evidence-overwrite refusal, added on
#: 2026-08-17 when the walk was widened to see that name at all and
#: reduced from three to one the same day when the three writers were
#: given one home; the other 12 are the reachability tranche and are
#: almost all ``ValueError``. Re-basing the TypeError three onto a catalogued class
#: is not the
#: one-line change the ValueError sites were: ``except TypeError`` is
#: how a caller distinguishes "I passed the wrong kind of thing" from "I
#: passed a bad value", and the catalogued classes this package has are
#: all ``ValueError``-based, so the fix needs a new base and a decision
#: about what it means. Deferred rather than rushed the night before a
#: tag (PLN-20260803-2340).
#:
#: It held 29 at v0.4.0. Eleven left. Eight were the whole
#: ``_check_layout_rules`` tranche, re-based onto ``CommandDatabaseError``
#: at v0.5.0, which is what the exemption's own comment had been asking
#: for: the class is already ``ValueError``-based, so pydantic's
#: validation protocol is unaffected and a caller's ``except ValueError``
#: catches exactly what it caught before. The occasion was three NEW
#: raises added to that same function this release, and the choice
#: between enlarging a ratchet and emptying it is not a close one.
#:
#: The re-anchoring friction found it, and found something sharper on
#: the way. Insertions above the function moved all eight sites, and the
#: shifted set OVERLAPPED the recorded one: the entry recorded for line
#: 455 kept matching, having silently come to name a different raise. A
#: line-keyed ratchet can therefore exempt a site nobody ever read.
#:
#: THAT WEAKNESS IS GONE as of 2026-08-18, and it was argued here as an
#: argument for emptying the set rather than re-keying it. Re-keying is
#: what happened, after the line number churned five times in one day on
#: docstring edits alone, which teaches a maintainer to update a number
#: without reading it. The key is now (definition, exception type) and
#: the per-pair counts below carry the one property the line number was
#: really holding. Emptying the set is still the goal; this only stops it
#: costing a re-anchor per comment.
_RATCHET = {
    # THE EVIDENCE-OVERWRITE ENTRY, and it was THREE for one day.
    # `FileExistsError` joined `_BARE` on 2026-08-17 and the walk found
    # three identical refusals, one per evidence writer; the review pass
    # that prompted the widening had named one of them, which is the whole
    # argument for widening a guard rather than fixing what a reviewer
    # points at. The three then became one, because three copies of one
    # rule is why a repair had reached only the probe path: the naming and
    # the refusal now live in `qa/reports.py` and the writers call it.
    #
    # It keeps the builtin ON PURPOSE and not from neglect, because
    # `except FileExistsError` is what a caller writing a file already has
    # around the call, and it predates the catalogue's reach.
    "pyflightstream.qa.reports.refuse_existing_report -> FileExistsError",
    # TypeError for an argument of an unaccepted type. The catalogue is
    # entirely ValueError-based, so re-basing these needs a new base and
    # a decision about what it means (PLN-20260803-2340).
    "pyflightstream.results.tables.to_table -> TypeError",
    "pyflightstream.script.entities.EntityRegistry -> TypeError",
    # The REACHABILITY tranche, measured 2026-08-04: a bare stdlib raise
    # inside a module-private helper that a public definition calls
    # reaches a caller exactly as an exported one does. The walk used to
    # measure where a raise is WRITTEN; FR-39 asks what the public API
    # RAISES. The author's decision: measure now, fix at v0.5, so the
    # number is the debt and it is countable (PLN-20260804-0130).
    "pyflightstream.cases.cli._parse_recipes -> ValueError",
    "pyflightstream.farfield._delta_psi -> ValueError",
    "pyflightstream.fsi.driver._verified_layout -> ValueError",
    "pyflightstream.fsi.loads._validate_block_boundaries -> ValueError",
    "pyflightstream.overview._module_doc -> RuntimeError",
    "pyflightstream.post.writers._checked -> ValueError",
    "pyflightstream.probes.planar._unit -> ValueError",
    # `qa.compat._rewrite_version_line` held three entries and holds none.
    # One left because the condition it reported turned out to be a real
    # evidence defect rather than a malformed line (apply-compat writing
    # a second `"26.121":` key into an entry that already had one). The
    # other two were re-based in the same release review, once the
    # insertion above them had moved them and they had to be re-read
    # anyway: both refuse to promote a committed report's evidence, which
    # is what `QaEvidenceError` is for, and it was already imported in
    # that module for the sibling refusal three lines away.
    "pyflightstream.results._parse_solver_flag -> ValueError",
    "pyflightstream.results.tables._as_record -> ValueError",
    "pyflightstream.results.tables._check_point_printback -> ValueError",
    "pyflightstream.results.tables._run_row -> ValueError",
    "pyflightstream.results.tables._sectional_loads_frame -> ValueError",
}

#: HOW MANY RAISES EACH EXEMPTED PAIR COVERS, measured 2026-08-18. The
#: set above dropped the line number that day, for the two reasons
#: `_exported_bare_raises` states, and this is what replaces the property
#: the line number was carrying: a SECOND bare raise of the same type
#: appearing inside an already-exempted definition would otherwise
#: inherit the exemption in silence. Five definitions raise twice; the
#: rest raise once. Fifteen pairs, nineteen raises.
_RATCHET_COUNTS = {
    "pyflightstream.qa.reports.refuse_existing_report -> FileExistsError": 1,
    "pyflightstream.results.tables.to_table -> TypeError": 2,
    "pyflightstream.script.entities.EntityRegistry -> TypeError": 1,
    "pyflightstream.cases.cli._parse_recipes -> ValueError": 1,
    "pyflightstream.farfield._delta_psi -> ValueError": 1,
    "pyflightstream.fsi.driver._verified_layout -> ValueError": 1,
    "pyflightstream.fsi.loads._validate_block_boundaries -> ValueError": 2,
    "pyflightstream.overview._module_doc -> RuntimeError": 1,
    "pyflightstream.post.writers._checked -> ValueError": 2,
    "pyflightstream.probes.planar._unit -> ValueError": 1,
    "pyflightstream.results._parse_solver_flag -> ValueError": 1,
    "pyflightstream.results.tables._as_record -> ValueError": 1,
    "pyflightstream.results.tables._check_point_printback -> ValueError": 1,
    "pyflightstream.results.tables._run_row -> ValueError": 2,
    "pyflightstream.results.tables._sectional_loads_frame -> ValueError": 1,
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
    assert _bare_raises_in("m", "m.py", source, {"f"}) == ["m.f -> ValueError"]
    # Without one: every non-underscore definition is public, and the
    # underscore-private one is still skipped.
    assert _bare_raises_in("m", "m.py", source, set()) == ["m.f -> ValueError"]
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
    assert found == ["m.M -> ValueError"], (
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
    # EVERY NAMED TRANCHE IS SUBTRACTED, not just the first. The
    # reachability figure was computed as "everything that is not a
    # TypeError", so the FileExistsError tranche of 2026-08-17 would have
    # been silently counted as reachability and the comment would have
    # read correctly while meaning something false.
    type_errors = sum(1 for entry in _RATCHET if "-> TypeError" in entry)
    file_exists = sum(1 for entry in _RATCHET if "-> FileExistsError" in entry)
    assert int(total.group(1)) == len(_RATCHET), (
        f"the comment says {total.group(1)} entries and the set holds {len(_RATCHET)}"
    )
    assert int(reachability.group(1)) == len(_RATCHET) - type_errors - file_exists, (
        f"the comment says {reachability.group(1)} in the reachability tranche and the "
        f"set holds {len(_RATCHET) - type_errors - file_exists}. The message used to "
        f"drop the FileExistsError tranche, so it told the maintainer to write a "
        f"number this same assertion would then reject"
    )


def test_the_detector_emits_one_entry_per_raise_not_one_per_pair() -> None:
    """The multiplicity the counting guard rests on, asserted directly.

    `_exported_bare_raises`'s docstring makes the load-bearing claim that
    the walk "returns one entry per raise, so the count below closes it".
    Every other case in this file uses a source with at most one bare
    raise per definition and the stale-entry test compares SETS, so
    changing `_bare_raises_in` to `return sorted(set(offenders))` would
    collapse every count to one, empty the `grown` check forever, and
    leave this whole file green.
    """
    source = (
        "def f():\n    if a:\n        raise ValueError('first')\n    raise ValueError('second')\n"
    )
    found = _bare_raises_in("m", "m.py", source, {"f"})
    assert found == ["m.f -> ValueError", "m.f -> ValueError"], (
        "the walk collapsed two raises in one definition into one entry, so the "
        f"per-pair counts can no longer see a second offender: {found}"
    )
