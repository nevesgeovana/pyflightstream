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

from pydantic import BaseModel
from test_public_api import PUBLIC_MODULES

from pyflightstream.reference import CONVENTIONS, conventions_markdown, render_html

# --- the conventions section renders in both layers -------------------------


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
