"""Tier 1: the house conventions render everywhere and hold in the code.

Pipeline role: quality gate on PLN-032. The conventions have one home
(``pyflightstream.reference.CONVENTIONS``); both delivery layers are
checked here, and the mechanical rules are audited against the code:
every float field of a pydantic model either carries an SI unit suffix
or appears in the commented dimensionless/debt whitelist below, so a
new unsuffixed physical quantity fails the suite.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import warnings
from pathlib import Path

import pytest
from pydantic import BaseModel
from test_public_api import PUBLIC_MODULES

import pyflightstream
from pyflightstream.overview import _CORE_LAYERS
from pyflightstream.reference import CONVENTIONS, conventions_markdown, render_html

# --- the conventions section renders in both layers -------------------------


def test_the_rotor_sign_convention_is_published():
    """FR-42 claims the package names the rotor-rotation sign.

    It claimed that from 2026-07-27 while `CONVENTIONS` carried no rotor
    entry at all, and a reviewer pass found that rather than a guard.
    Adding the entry without this case leaves the same hole: delete it
    again and the badge stays green and the suite stays green.

    What is pinned is the DISTINCTION the entry exists to publish, not
    its prose. A rotor entry that dropped either half would be a
    convention that no longer says which sign is derived and which is
    measured, which is the confusion the whole release round was spent
    on.
    """
    entry = next((body for title, body in CONVENTIONS if "Rotor sign" in title), "")
    assert entry, (
        "CONVENTIONS carries no rotor-sign entry, and FR-42 is badged implemented on "
        "the claim that the package names the rotor-rotation sign"
    )
    lowered = entry.lower()
    for token, why in (
        ("azimuth increment", "the derived quantity is not named"),
        ("rotor speed", "the measured quantity is not named"),
        ("rotation_sense_sign", "the home of the derivation is not named"),
        ("rpm_sign_installed", "the fields that record the measurement are not named"),
        ("rpt-036", "what is still open is not addressed to the report that holds it"),
    ):
        assert token in lowered, f"the rotor-sign convention is published and {why}"


def test_conventions_have_titles_and_prose():
    assert len(CONVENTIONS) >= 8
    for title, text in CONVENTIONS:
        assert title and text and len(text) > 40, f"convention {title!r} is a stub"


def test_help_html_carries_the_conventions_section():
    page = render_html()
    assert "<h2>Naming conventions</h2>" in page
    for title, _ in CONVENTIONS:
        assert title in page


def test_conventions_markdown_mirrors_the_same_home():
    text = conventions_markdown()
    assert text.startswith("## Naming conventions")
    for title, _ in CONVENTIONS:
        assert f"### {title}" in text


# --- mechanical adherence audit: units ride the names -----------------------

#: Accepted SI unit suffixes of float-valued model fields.
_UNIT_SUFFIX = re.compile(
    r"_(m|m2|m3|mm|um|deg|rad|s|hz|n|pa|kg|kg_m|kg_per_m|n_m2|per_m"
    r"|rad_per_s|m_per_s|millions)$"
)

#: Field names accepted without a unit suffix, each with its reason.
#: Class (a): dimensionless by physics. Class (b): naming debt pinned
#: by a released file format or interface; renaming one is a public
#: rename announced in the changelog's API surface delta, and a
#: deprecation cycle is owed only from 1.0 (SRS NFR-20, which replaced
#: the 2026-07-23 posture this comment used to state). New entries join
#: with a stated reason.
_DIMENSIONLESS_OR_DEBT = {
    # (a) dimensionless by physics or by construction
    "stiffness_scale_factor",  # multiplier on EI/GJ
    "node_offset_chord_fraction",  # fraction of local chord
    "wake_development_revolutions",  # revolutions are counts
    "coupling_relaxation",  # relaxation factor in (0, 1]
    "thrust_tolerance_fraction",  # relative change of integrated force, N/N
    "averaging_window_revolutions",  # revolutions are counts
    "recording_revolutions",  # revolutions are counts
    "ratio",  # geometric spacing ratio (AxisSpec)
    "reynolds",  # dimensionless by definition
    "mach",  # dimensionless by definition
    "convergence",  # solver residual target, dimensionless
    "variables",  # free per-case table, values untyped
    "point",  # sweep point: axis name to value
    "values",  # sweep values along a declared axis
    "default",  # command-schema default, type per command
    "residual",  # RunRecord: solver residual, dimensionless
    # (b) naming debt pinned by released formats or frames
    "area",  # campaign.toml key (ReferenceData), m2 in docs
    "length",  # campaign.toml key (ReferenceData), m in docs
    "velocity",  # campaign.toml key, m/s in docs
    "start",  # AxisSpec, frame units (m) stated in docstring
    "stop",  # AxisSpec, frame units (m) stated in docstring
    "spacing",  # AxisSpec, frame units (m) stated in docstring
    "origin",  # FrameDefinition, m stated in docstring
    "x_axis",  # FrameDefinition, unit vector
    "y_axis",  # FrameDefinition, unit vector
    "band_distance",  # GeometryGateReport, m stated in docstring
    "standoff",  # GeometryGateReport, m stated in docstring
    "distance",  # RefinementBand, m stated in docstring
    "diameter",  # BulkSeparation, m stated in docstring
    "tip_radius",  # ProbeLattice, m stated in docstring
    "stations",  # ProbeLattice, fractions of tip radius
    "ring_edges",  # ProbeLattice, fractions of tip radius
    "lateral_radius",  # ProbeLattice, m stated in docstring
    "lateral_stations",  # ProbeLattice, fractions
    "previous_displacements",  # FsiState, m per the FSIDisp contract
    # WakeEdgeImport: the solver's own argument name, and its unit is the
    # SIMULATION's length unit rather than a fixed SI one, which is what
    # `wake_edges.tolerance_unit()` reports out of the command database.
    # A `_m` suffix here would be a claim the command does not make.
    "tolerance",
}


def _model_float_fields() -> list[tuple[str, str]]:
    """Every (model, field) pair with float content in public modules."""
    pairs: list[tuple[str, str]] = []
    seen: set[type] = set()
    for name in PUBLIC_MODULES:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                module = importlib.import_module(name)
        except ImportError:
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, BaseModel)
                and cls is not BaseModel
                and cls.__module__.startswith("pyflightstream")
                and cls not in seen
            ):
                seen.add(cls)
                for field_name, field in cls.model_fields.items():
                    if "float" in str(field.annotation):
                        pairs.append((f"{cls.__module__}.{cls.__name__}", field_name))
    return pairs


def test_float_model_fields_carry_units_or_a_stated_reason():
    violations = [
        f"{model}.{field}"
        for model, field in _model_float_fields()
        if not _UNIT_SUFFIX.search(field) and field not in _DIMENSIONLESS_OR_DEBT
    ]
    assert not violations, (
        f"float fields {violations} have neither an SI unit suffix nor an "
        "entry in the dimensionless/debt whitelist; units ride the names "
        "(house convention). Suffix the field, or whitelist it with a "
        "stated reason."
    )


# --- mechanical adherence audit: diagnostics versus validators --------------


def _imported_module_names(source: str, package: str) -> set[str]:
    """Every module ``source`` imports, as absolute dotted names.

    Normalised rather than collected raw, which is the difference between
    a guard and a guard-shaped thing. ``from X import y`` may import the
    NAME y from module X or the MODULE X.y, and the source alone cannot
    tell which, so both readings are recorded; a false positive here
    would only over-refuse an import direction, while the false negative
    the raw version had let the reversal through.

    Parameters
    ----------
    source : str
        Python source text.
    package : str
        Dotted package the source lives in, used to resolve the leading
        dots of a relative import.

    Returns
    -------
    set of str
        Absolute dotted module names, plus ``module.name`` for every
        name a ``from`` import binds.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                base = f"{base}.{node.module}" if node.module else base
            else:
                base = node.module or ""
            if not base:
                continue
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def test_check_prefixed_functions_return_nothing():
    """The check_ prefix promises a refusal, not a measurement.

    Half of the diagnostics-versus-validators convention is mechanical:
    a function named check_ exists to raise, so it must not also hand
    back a value that a caller could mistake for the measurement. The
    noun half (a measurement is named for what it returns) is not
    mechanically decidable and stays prose.
    """
    offenders = []
    inspected = set()
    for name in PUBLIC_MODULES:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                module = importlib.import_module(name)
        except ImportError:
            continue
        # Methods too, not only module-level functions: inspect.isfunction
        # over a MODULE does not return them, and half of this package's
        # check_ callables are methods (Entities.check_index,
        # Entities.check_boundary_count). A QA pass measured the earlier
        # version staying green while check_index was given a return
        # annotation.
        candidates = list(inspect.getmembers(module, inspect.isfunction))
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if getattr(cls, "__module__", "").startswith("pyflightstream"):
                candidates.extend(inspect.getmembers(cls, inspect.isfunction))
        for attr, obj in candidates:
            if not attr.startswith("check_") or not obj.__module__.startswith("pyflightstream"):
                continue
            inspected.add(f"{obj.__module__}.{obj.__qualname__}")
            annotation = inspect.signature(obj).return_annotation
            if annotation not in (None, "None", inspect.Signature.empty):
                offenders.append(f"{obj.__module__}.{obj.__qualname__} -> {annotation}")
    # Non-vacuity: the walk swallows ImportError per module, so a scan that
    # found nothing would report green. Four check_ callables are known to
    # exist; fewer means the scan stopped seeing them, not that they left.
    assert len(inspected) >= 4, (
        f"the scan found only {sorted(inspected)}; at least four check_ callables "
        "exist in this package, so a smaller number means the walk is broken "
        "rather than that the convention is satisfied"
    )
    assert not offenders, (
        f"check_ functions {offenders} return a value; a check_ function refuses "
        "and returns nothing (house convention). Name a function that MEASURES "
        "for the quantity it returns instead."
    )


def test_the_fsi_state_module_does_not_import_its_config_module():
    """The layering constraint the validator convention must not break.

    check_state_matches_config takes two integer counts rather than the
    FsiConfig that holds them, so fsi.state keeps its import surface to
    pydantic. A convention saying "pass the object, not its fields"
    would quietly undo that, so the direction is pinned here rather than
    trusted to prose.

    NOT the reason, stated because an earlier wording of the convention
    claimed it and a review pass measured it false: this does NOT keep
    pyflightstream.exceptions importable without the [fsi] extra. The
    catalog imports fsi.loads and fsi.state, which executes the fsi
    package __init__, which imports fsi.config regardless. Verified by
    importing the catalog and reading sys.modules.
    """
    module_name = "pyflightstream.fsi.state"
    package = module_name.rsplit(".", 1)[0]
    source = Path(inspect.getfile(importlib.import_module(module_name)))
    imported = _imported_module_names(source.read_text(encoding="utf-8"), package)
    assert "pyflightstream.fsi.config" not in imported, (
        "pyflightstream.fsi.state imports pyflightstream.fsi.config; that "
        "reverses the dependency direction and drags the config model into "
        "every import of the exception catalog. Pass the fields, not the object."
    )


def test_the_import_scan_sees_the_spelling_this_package_actually_uses():
    """Mutation proof for the scan above, on the form that defeated it.

    The first version collected `node.module` alone, so it caught
    `from pyflightstream.fsi.config import FsiConfig` and MISSED
    `from pyflightstream.fsi import config`. That miss is not exotic: it
    is this package's own idiom, written exactly that way in
    fsi/centrifugal.py and fsi/driver.py. A QA pass added the missed
    spelling to state.py and the guard stayed green, which makes it a
    guard that could not fail against the import a reader would write.

    Every spelling below must be seen, so the scan is proved against the
    forms rather than against one of them.
    """
    package = "pyflightstream.fsi"
    target = "pyflightstream.fsi.config"
    for source in (
        "from pyflightstream.fsi.config import FsiConfig",
        "import pyflightstream.fsi.config",
        "from pyflightstream.fsi import config",
        "from .config import FsiConfig",
        "from . import config",
        "from pyflightstream.fsi import beam, config",
    ):
        assert target in _imported_module_names(source, package), (
            f"the scan does not see {source!r} as importing {target}"
        )
    # And it must not fire on an import that is genuinely something else,
    # or it would refuse the module's real dependencies.
    for source in (
        "from pyflightstream.fsi import beam",
        "from pydantic import BaseModel",
        "from . import nodes",
    ):
        assert target not in _imported_module_names(source, package), (
            f"the scan wrongly reads {source!r} as importing {target}"
        )


# --- mechanical adherence audit: the layer rule, with no exception list -----

#: The installed package tree, walked by the layering guards below.
_SRC = Path(pyflightstream.__file__).parent

#: Layer row of every top-level name the core stack declares, smallest
#: index highest. Read from `pyflightstream.overview._CORE_LAYERS`, which
#: the SRS architecture chapter and the CLAUDE.md layout rule are both
#: derived from, so this guard spells no layer name of its own. A name
#: with no row here (a side branch such as `fsi`, or a module below the
#: stack such as `_errors`) is deliberately absent: the rule orders the
#: pipeline, and a branch outside it has no direction to violate.
_LAYER_ROW: dict[str, int] = {
    name: row for row, (names, _) in enumerate(_CORE_LAYERS) for name in names
}


def _layer_row(dotted: str) -> int | None:
    """Row of the module ``dotted`` names, or None when it has no layer."""
    parts = dotted.split(".")
    if len(parts) < 2 or parts[0] != "pyflightstream":
        return None
    return _LAYER_ROW.get(parts[1])


def _function_body_imports(source: str, package: str) -> list[tuple[str, int, set[str]]]:
    """Every import written inside a function body, with where it sits.

    ``ast.walk`` alone records no enclosing scope, so this descends from
    each :class:`ast.FunctionDef` and :class:`ast.AsyncFunctionDef`
    instead and collects the import nodes underneath it. A module-level
    ``if TYPE_CHECKING`` block is not a function body and is therefore
    never reached, which is what keeps annotation-only imports out of
    this scan without an exception for them.

    Parameters
    ----------
    source : str
        Python source text.
    package : str
        Dotted package the source lives in, used to resolve the leading
        dots of a relative import.

    Returns
    -------
    list of (str, int, set of str)
        One entry per import statement inside a function: the function
        name, the statement's line number, and the absolute dotted
        module names it may name (both readings of a ``from`` import,
        as in :func:`_imported_module_names`).
    """
    found: list[tuple[str, int, set[str]]] = []
    for outer in ast.walk(ast.parse(source)):
        if not isinstance(outer, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(outer):
            if isinstance(node, ast.Import):
                found.append((outer.name, node.lineno, {alias.name for alias in node.names}))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".")
                    base = ".".join(parts[: len(parts) - node.level + 1])
                    base = f"{base}.{node.module}" if node.module else base
                else:
                    base = node.module or ""
                if not base:
                    continue
                names = {base}
                names.update(f"{base}.{alias.name}" for alias in node.names)
                found.append((outer.name, node.lineno, names))
    return found


def _upward_function_body_imports(path: Path) -> list[str]:
    """Report every function-body import of ``path`` that points upward."""
    dotted = "pyflightstream." + path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")
    dotted = dotted.removesuffix(".__init__")
    own = _layer_row(dotted)
    if own is None:
        return []
    package = dotted.rsplit(".", 1)[0] if path.name != "__init__.py" else dotted
    offenders = []
    for function, lineno, targets in _function_body_imports(
        path.read_text(encoding="utf-8"), package
    ):
        rows = {row for row in (_layer_row(target) for target in targets) if row is not None}
        higher = [row for row in rows if row < own]
        if higher:
            names = sorted(
                target
                for target in targets
                if (_layer_row(target) is not None and _layer_row(target) < own)
            )
            offenders.append(
                f"{path.relative_to(_SRC).as_posix()}:{lineno} in {function}() imports "
                f"{', '.join(names)}"
            )
    return offenders


@pytest.mark.requirement("NFR-23")
def test_no_function_body_import_reaches_a_higher_layer():
    """The layer rule, with an EMPTY permitted set (OPS-2007.02.03).

    Dependencies flow downward (CLAUDE.md, "Layout"), and a function-body
    import does not make an upward one legal: deferring the import to
    call time hides the direction from every module-level reader without
    changing it. This guard therefore carries no allowlist, no per-module
    skip and no permitted set, because a guard carrying a list is a guard
    whose list grows.

    What it deliberately does NOT fire on, each because the layer rule
    says nothing about it rather than because it was excused: an import
    of a module with no core-stack row (a side branch such as
    `pyflightstream.fsi`, or `pyflightstream.extras`), an import inside
    the SAME row (`qa` reaching `qa`, `script` reaching `script`), and a
    third-party or standard-library import.
    """
    offenders: list[str] = []
    walked = 0
    for module in sorted(_SRC.rglob("*.py")):
        walked += 1
        offenders.extend(_upward_function_body_imports(module))
    # Non-vacuity: a walk that found no file would report green.
    assert walked >= 40, (
        f"the walk reached only {walked} modules under {_SRC}; the package has "
        "many more, so a smaller number means the walk is broken rather than "
        "that the rule is satisfied"
    )
    assert not offenders, (
        "these function-body imports point at a HIGHER layer:\n  "
        + "\n  ".join(offenders)
        + "\nDeferring an import to call time does not change its direction. "
        "Move the code to the layer that owns the dependency, or move the "
        "shared name below both. There is no permitted set to add it to."
    )


def test_the_function_body_scanner_reports_a_restored_deferral():
    """Mutation proof for the guard above, on the deferrals it replaced.

    The success condition here is the scanner FIRING: one of the five
    call-time imports the matrix reader used to carry is restored as a
    fixture and must be reported. Without this, a scanner that silently
    stopped descending into function bodies would leave the guard above
    green with every original defect back in place.
    """
    restored = (
        "def plan_matrix(path):\n"
        "    from pyflightstream.run import plan_campaign\n"
        "    return plan_campaign(path)\n"
    )
    found = _function_body_imports(restored, "pyflightstream.cases")
    assert [(name, sorted(targets)) for name, _, targets in found] == [
        ("plan_matrix", ["pyflightstream.run", "pyflightstream.run.plan_campaign"])
    ]
    # NESTED, and this half was added because the adversarial pass got the
    # scanner past the fixture above: replacing its `ast.walk(outer)` with
    # `outer.body` reports a deferral written at the top of a function and
    # MISSES every one written inside a branch, a loop, a `try` or an inner
    # function. That is not an exotic shape: `_sectional_loads_type` in
    # results/tables.py writes its import inside a `try`, so the very
    # module this guard was built against uses it. Each spelling below must
    # be seen, or the guard has a hole with no exception list to name it.
    for source in (
        "def f(x):\n"
        "    if x:\n"
        "        from pyflightstream.run import plan_campaign\n"
        "    return x\n",
        "def f(x):\n"
        "    try:\n"
        "        from pyflightstream.run import plan_campaign\n"
        "    except ImportError:\n"
        "        return None\n",
        "def f(x):\n    for _ in range(x):\n        from pyflightstream.run import plan_campaign\n",
        "def f(x):\n"
        "    def inner():\n"
        "        from pyflightstream.run import plan_campaign\n"
        "    return inner\n",
        "class C:\n    def method(self):\n        from pyflightstream.run import plan_campaign\n",
        "def f(x):\n    import pyflightstream.run\n",
    ):
        targets = {name for _, _, names in _function_body_imports(source, "x") for name in names}
        assert "pyflightstream.run" in targets, (
            f"the scanner does not see the deferral in:\n{source}"
        )

    # RELATIVE spellings, which are how the same upward import is written
    # from inside the package and which resolve to nothing unless the
    # leading dots are counted against the importing package. `from ..run
    # import plan_campaign` inside cases/matrix.py is the exact deferral
    # this lane deleted, written the other way.
    #
    # Checked by LAYER ROW rather than by the exact dotted name, because
    # `from ..run.matrix import run_matrix` resolves to
    # `pyflightstream.run.matrix` and never to `pyflightstream.run`, and
    # what the guard reads is the row a name sits in. An assertion on the
    # spelling would fail on a scanner that is right.
    run_row = _layer_row("pyflightstream.run")
    for source, package in (
        ("def f(x):\n    from ..run import plan_campaign\n", "pyflightstream.cases"),
        ("def f(x):\n    from .. import run\n", "pyflightstream.cases"),
        ("def f(x):\n    from ..run.matrix import run_matrix\n", "pyflightstream.cases"),
        ("def f(x):\n    from .run import plan_campaign\n", "pyflightstream"),
        ("def f(x):\n    from ..workspace.inputs import resolve_setup\n", "pyflightstream.cases"),
    ):
        targets = {
            name for _, _, names in _function_body_imports(source, package) for name in names
        }
        assert run_row in {_layer_row(name) for name in targets}, (
            f"the scanner does not resolve the relative deferral in:\n{source}"
            f"(package {package}); it saw {sorted(targets)}"
        )
    assert _layer_row("pyflightstream.run") < _layer_row("pyflightstream.cases"), (
        "the layer rows say `run` is not above `cases`, so the guard could "
        "not refuse the deferral this package spent three releases carrying"
    )
    # And the same statement at MODULE level is not this guard's business:
    # it is the direction guard's, and a scanner that reported it here
    # would fire on every legal import in the package.
    assert _function_body_imports("from pyflightstream.run import plan_campaign", "x") == []


def test_the_function_body_scanner_leaves_the_legitimate_shapes_alone():
    """The four shapes that must NOT fire, proved one by one.

    A guard with no exception list is only honest if it never needed one,
    so each shape the package legitimately writes is measured here rather
    than asserted in prose. A scanner that over-refused would otherwise
    be repaired by adding the permitted set this item exists to refuse.
    """
    same_layer = (
        "def probe_version(v):\n    from pyflightstream.qa import specs\n    return specs\n"
    )
    assert _function_body_imports(same_layer, "pyflightstream.qa")
    assert _layer_row("pyflightstream.qa") == _layer_row("pyflightstream.post")
    # A side branch has no row at all, so nothing about it can point "up".
    assert _layer_row("pyflightstream.fsi") is None
    assert _layer_row("pyflightstream.extras") is None
    assert _layer_row("pyflightstream.utils") is None
    # And the base-exception module is below the stack rather than in it.
    assert _layer_row("pyflightstream._errors") is None
    # Third party and standard library resolve to no row either.
    assert _layer_row("trimesh") is None
    assert _layer_row("pathlib") is None


def test_an_exception_more_than_one_layer_names_is_defined_below_them_all():
    """OPS-2007.02.01: a shared refusal is vocabulary, not an upward reach.

    `InputArtifactError` was defined in `pyflightstream.workspace.inputs`,
    which is the layer that RAISES it, while the layers that bind a run
    matrix to the input library CATCH it and re-raise with the row and
    the file they were resolving. Reaching up for the type alone is what
    three of the five call-time imports in `cases/matrix.py` were, and
    the hoist removed those three by moving the code rather than by
    fixing the reason, so the reason is fixed here: the class lives in
    `pyflightstream._errors`, which sits below every layer and imports
    nothing from this package.

    Asserted as a PROPERTY rather than as a path, so the rule survives
    the class moving again: whatever module defines it must carry no
    core-stack layer row at all, which is what "below every layer" means
    in the terms this file already uses.

    Nothing a user writes changes. The name is re-exported by
    `pyflightstream.workspace` and by the catalog, both bases are kept,
    and the three attributes are kept; all four are asserted here rather
    than left to the docstring, because "the public names are unchanged"
    is half of this item's acceptance.
    """
    import pyflightstream.exceptions as catalog
    import pyflightstream.workspace as workspace_package
    import pyflightstream.workspace.inputs as inputs_module

    catalogued = catalog.InputArtifactError
    assert catalogued is workspace_package.InputArtifactError is inputs_module.InputArtifactError, (
        "the three public spellings of InputArtifactError no longer name one "
        "class, so which one a caller caught decides whether they catch it"
    )
    assert _layer_row(catalogued.__module__) is None, (
        f"InputArtifactError is defined in {catalogued.__module__}, which sits "
        f"in layer row {_layer_row(catalogued.__module__)} of the core stack. "
        "An exception type that more than one layer names has to live BELOW "
        "all of them, or the lower one reaches upward for the name and pays "
        "for it with an import deferred to call time."
    )
    assert catalogued.__module__.rsplit(".", 1)[-1].startswith("_"), (
        f"{catalogued.__module__} is a public module; the shared-refusal home "
        "is private, and the class is reached through the catalog or through "
        "the layer that owns what it describes"
    )
    # The bases a caller already writes `except` against, and the three
    # attributes the message promises are readable without parsing it.
    assert issubclass(catalogued, RuntimeError)
    assert issubclass(catalogued, catalog.PyflightstreamError)
    error = catalogued("x", kind="reference", artifact_id="9001", available=("a",))
    assert (error.kind, error.artifact_id, error.available) == ("reference", "9001", ("a",))


@pytest.mark.requirement("NFR-23")
def test_the_matrix_reader_imports_nothing_above_the_cases_layer():
    """OPS-2007.02.02: the reader stops reaching into run and workspace.

    `cases/matrix.py` used to carry seven indented imports of the two
    layers above it, five at call time and two under `TYPE_CHECKING`, and
    the count going to zero is this item's acceptance. Asserted at ANY
    level rather than at call time only, because the annotation-only pair
    recorded the same upward dependency in the type checker's view; the
    binding half of the module moved to `pyflightstream.workspace.matrix`
    and the execution half to `pyflightstream.run.matrix`, where each
    import is ordinary and points down or sideways.
    """
    module = _SRC / "cases" / "matrix.py"
    imported = _imported_module_names(module.read_text(encoding="utf-8"), "pyflightstream.cases")
    upward = sorted(
        name
        for name in imported
        if name == "pyflightstream.run"
        or name == "pyflightstream.workspace"
        or name.startswith(("pyflightstream.run.", "pyflightstream.workspace."))
    )
    assert not upward, (
        f"pyflightstream.cases.matrix imports {upward}; the run and workspace "
        "layers sit ABOVE cases, and an import under TYPE_CHECKING or inside a "
        "function body records the same dependency. The binding half belongs to "
        "pyflightstream.workspace.matrix and the execution half to "
        "pyflightstream.run.matrix."
    )


def _runtime_imported_module_names(
    source: str, package: str, *, module_level_only: bool
) -> set[str]:
    """Every module ``source`` imports AT RUNTIME, as absolute dotted names.

    The difference from :func:`_imported_module_names` is what it does
    NOT see. That helper walks the whole tree with ``ast.walk`` and knows
    nothing of nesting, so an annotation-only import inside
    ``if TYPE_CHECKING:`` is indistinguishable from one the interpreter
    executes. A guard about what a module DEPENDS ON at import time has
    to tell those apart, or it can neither go green on a module that
    keeps only the annotation nor refuse one that does not.

    Both readings of a ``from`` import are recorded, exactly as
    :func:`_imported_module_names` documents and for the same reason.

    Parameters
    ----------
    source : str
        Python source text.
    package : str
        Dotted package the source lives in, used to resolve the leading
        dots of a relative import.
    module_level_only : bool
        With True only top-level statements are read, which is the
        condition a deferred convenience import is judged against. With
        False every runtime import in the file is read, function bodies
        included. Keyword-only, so neither reading can hide in a call.

    Returns
    -------
    set of str
        Absolute dotted module names, plus ``module.name`` for every
        name a ``from`` import binds.
    """
    found: set[str] = set()

    def record(node: ast.Import | ast.ImportFrom) -> None:
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
            return
        if node.level:
            parts = package.split(".")
            base = ".".join(parts[: len(parts) - node.level + 1])
            base = f"{base}.{node.module}" if node.module else base
        else:
            base = node.module or ""
        if not base:
            return
        found.add(base)
        found.update(f"{base}.{alias.name}" for alias in node.names)

    def is_type_checking_guard(node: ast.stmt) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if isinstance(test, ast.Name):
            return test.id == "TYPE_CHECKING"
        return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"

    def visit(body: list[ast.stmt], *, top_level: bool) -> None:
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record(node)
            elif is_type_checking_guard(node):
                # Never descended into: the interpreter does not run it.
                continue
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not module_level_only:
                    visit(node.body, top_level=False)
            elif isinstance(node, ast.ClassDef):
                visit(node.body, top_level=top_level)
            elif hasattr(node, "body"):
                nested = getattr(node, "body", [])
                visit(list(nested), top_level=top_level)
                for attribute in ("orelse", "finalbody"):
                    visit(list(getattr(node, attribute, [])), top_level=top_level)
                for handler in getattr(node, "handlers", []):
                    visit(list(handler.body), top_level=top_level)

    visit(ast.parse(source).body, top_level=True)
    return found


def test_the_runtime_import_scan_separates_deferred_from_annotation_only():
    """Mutation proof for the runtime scan, on the three cases that decide it.

    Written before the guard it serves, because the guard's whole value
    is the distinction: an annotation-only import must read ABSENT in
    both readings, a deferred one must read absent at module level and
    PRESENT whole-file, and a plain module-level one must read present in
    both. A scan that collapsed any pair would make the guard below
    unable to fail.
    """
    target = "pyflightstream.workspace"
    package = "pyflightstream.results"

    annotation_only = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from pyflightstream.workspace import CampaignWorkspace\n"
    )
    assert target not in _runtime_imported_module_names(
        annotation_only, package, module_level_only=True
    )
    assert target not in _runtime_imported_module_names(
        annotation_only, package, module_level_only=False
    )

    deferred = (
        "def _as_workspace(root):\n"
        "    from pyflightstream.workspace import CampaignWorkspace\n"
        "    return CampaignWorkspace(root)\n"
    )
    assert target not in _runtime_imported_module_names(deferred, package, module_level_only=True)
    assert target in _runtime_imported_module_names(deferred, package, module_level_only=False)

    plain = "from pyflightstream.workspace import CampaignWorkspace\n"
    assert target in _runtime_imported_module_names(plain, package, module_level_only=True)
    assert target in _runtime_imported_module_names(plain, package, module_level_only=False)

    # The dotted-attribute spelling of the guard, which this package also
    # writes, must be recognised as the same thing.
    dotted_guard = (
        "import typing\n"
        "if typing.TYPE_CHECKING:\n"
        "    from pyflightstream.workspace import CampaignWorkspace\n"
    )
    assert target not in _runtime_imported_module_names(
        dotted_guard, package, module_level_only=False
    )


@pytest.mark.requirement("NFR-23")
def test_the_results_tables_module_imports_the_workspace_layer_nowhere_at_runtime():
    """OPS-2009.02.05, taken on the DELETE branch rather than blessed.

    `results/tables.py` carried a convenience import of the execution
    layer inside `_as_workspace`, deferred to call time so that
    `parse_run_loads` and `sweep_table` could take a bare root path. That
    is the results layer reaching UPWARD into run/workspace, and the two
    readings of AD-01 were to bless it as a stated exception or to
    delete it. It is deleted: both entry points require a constructed
    `CampaignWorkspace`, which is what makes the empty permitted set of
    `test_no_function_body_import_reaches_a_higher_layer` able to go
    green at all.

    Whole-file absence, not module-level absence: the blessing rested on
    the import staying deferred, and there is no blessing left to rest
    on. The annotation-only import in the module's `TYPE_CHECKING` block
    stays and is outside both readings, which is exactly what the scan
    above is proved on.
    """
    module = _SRC / "results" / "tables.py"
    runtime = _runtime_imported_module_names(
        module.read_text(encoding="utf-8"), "pyflightstream.results", module_level_only=False
    )
    reaching = sorted(
        name
        for name in runtime
        if name == "pyflightstream.workspace" or name.startswith("pyflightstream.workspace.")
    )
    assert not reaching, (
        f"pyflightstream.results.tables imports {reaching} at runtime; the "
        "results layer sits BELOW run/workspace, and deferring the import to "
        "call time does not change that. Both public entry points take a "
        "constructed CampaignWorkspace, so the coercion helper has no reason "
        "to exist."
    )
