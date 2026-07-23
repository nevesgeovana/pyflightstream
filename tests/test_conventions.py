"""Tier 1: the house conventions render everywhere and hold in the code.

Pipeline role: quality gate on PLN-032. The conventions have one home
(``pyflightstream.reference.CONVENTIONS``); both delivery layers are
checked here, and the mechanical rules are audited against the code:
every float field of a pydantic model either carries an SI unit suffix
or appears in the commented dimensionless/debt whitelist below, so a
new unsuffixed physical quantity fails the suite.
"""

from __future__ import annotations

import importlib
import inspect
import re
import warnings

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
#: by a released file format or interface; renaming needs its own
#: deprecation cycle (registered with lane C at the 2026-07-23 session,
#: candidate plan item). New entries join with a stated reason.
_DIMENSIONLESS_OR_DEBT = {
    # (a) dimensionless by physics or by construction
    "stiffness_scale_factor",  # multiplier on EI/GJ
    "node_offset_chord_fraction",  # fraction of local chord
    "wake_development_revolutions",  # revolutions are counts
    "coupling_relaxation",  # relaxation factor in (0, 1]
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
