"""S02: extracting product writers preserves their existing import spellings."""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

from pyflightstream.post import products
from tests.tier1_offline.test_public_api import PUBLIC_MODULES

# Captured with git show HEAD:src/pyflightstream/post/products.py before S02, plus
# ProductArgumentError, which the exceptions catalogue added in the same release.
# Keep the order too: the extraction must not edit the existing export inventory.
_ORIGINAL_ALL = [
    "ADVANCE_RATIO_COLUMN",
    "COEFFICIENT_COLUMNS",
    "CONDITION_KEY_ALIASES",
    "CONTEXT_COLUMNS",
    "FLIGHT_CONDITION_COLUMNS",
    "REFERENCE_LENGTH_COLUMNS",
    "ROTOR_TABLE_LEAD_LINES",
    "ROTOR_TABLE_SUFFIX",
    "UNSTEADY_AXIS_COLUMNS",
    "context_row",
    "renamed_columns",
    "section_identity",
    "NOT_APPLICABLE",
    "POLAR_COLUMNS",
    "SWEEP_AXES",
    "POLARS_DIR",
    "PROBES_DIR",
    "PROVENANCE_DIR",
    "PROVENANCE_SUFFIX",
    "SECTIONS_DIR",
    "SECTION_COLUMNS",
    "GroupCoefficients",
    "CustomPolarTable",
    "PRODUCTS_MANIFEST",
    "PER_BLADE_COLUMNS",
    "REDUCTION_COLUMNS",
    "PolarPoint",
    "ProductArgumentError",
    "ProductError",
    "ProductExistsError",
    "ReferenceValues",
    "group_coefficients",
    "custom_polar_file_name",
    "plots_table_series",
    "point_name_of",
    "polar_file_name",
    "polar_row",
    "swept_axes",
    "swept_polar_file_name",
    "unsteady_polar_file_name",
    "write_unsteady_polar",
    "GEOMETRY_ANALYSIS_FRAMES",
    "provenance_file_name",
    "read_csv_table",
    "read_custom_polar_format",
    "write_csv_table",
    "write_custom_polar_format",
    "write_plots_table",
    "write_probes_table",
    "write_per_blade_table",
    "write_phase_locked_table",
    "write_reduction_table",
    "write_polar_table",
    "write_campaign_products",
    "write_recorded_polar",
    "write_sections_table",
]


# Public helpers in the extracted modules retain their private products aliases.
_PRODUCTS_PRIVATE_ALIASES = {
    "CUSTOM_DATE_FORMAT": "_CUSTOM_DATE_FORMAT",
    "CUSTOM_REFERENCE_COLUMNS": "_CUSTOM_REFERENCE_COLUMNS",
    "CUSTOM_TITLE_PREFIX": "_CUSTOM_TITLE_PREFIX",
    "CUSTOM_WIDTH": "_CUSTOM_WIDTH",
    "custom_count": "_custom_count",
    "custom_field": "_custom_field",
    "group_number": "_group_number",
    "PROV_PREFIX": "_PROV_PREFIX",
    "SCRIPT_SUFFIX": "_SCRIPT_SUFFIX",
    "attributes": "_attributes",
    "prov_document": "_prov_document",
    "refuse_an_existing_product": "_refuse_an_existing_product",
    "run_provenance": "_run_provenance",
}


def test_extracted_product_modules_preserve_the_public_surface():
    module_names = ("pyflightstream.post.custom_polar", "pyflightstream.post.provenance")
    missing = [name for name in module_names if importlib.util.find_spec(name) is None]
    assert not missing, f"missing extracted product modules: {missing}"
    assert all(name in PUBLIC_MODULES for name in module_names)
    assert PUBLIC_MODULES == sorted(PUBLIC_MODULES)
    assert products.__all__ == _ORIGINAL_ALL
    assert all(hasattr(products, name) for name in _ORIGINAL_ALL)

    for module_name in module_names:
        module = importlib.import_module(module_name)
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        defined = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, ast.Assign | ast.AnnAssign):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                defined.update(
                    target.id
                    for target in targets
                    if isinstance(target, ast.Name) and target.id != "__all__"
                )
        assert defined, f"{module_name} defines no extracted names"
        for name in sorted(defined):
            product_name = _PRODUCTS_PRIVATE_ALIASES.get(name, name)
            assert hasattr(products, product_name), (
                f"post.products no longer binds {module_name}.{name}"
            )
            assert getattr(products, product_name) is getattr(module, name), (
                f"post.products.{product_name} must re-export "
                f"the same object as {module_name}.{name}"
            )


@pytest.mark.parametrize(
    ("module_name", "expected"),
    [
        (
            "custom_polar",
            {
                "CUSTOM_DATE_FORMAT",
                "CUSTOM_REFERENCE_COLUMNS",
                "CUSTOM_TITLE_PREFIX",
                "CUSTOM_WIDTH",
                "custom_count",
                "custom_field",
                "group_number",
                "CustomPolarTable",
                "custom_polar_file_name",
                "read_custom_polar_format",
                "write_custom_polar_format",
            },
        ),
        (
            "provenance",
            {
                "PROV_PREFIX",
                "SCRIPT_SUFFIX",
                "attributes",
                "prov_document",
                "refuse_an_existing_product",
                "run_provenance",
                "PRODUCT_ARCHIVE_DIR",
                "PRODUCT_ARCHIVE_STAMP",
                "PROVENANCE_DIR",
                "PROVENANCE_SUFFIX",
                "operator_agent",
                "point_name_of",
                "product_archive_dir",
                "provenance_file_name",
            },
        ),
        ("section_distributions", {"write_section_distributions"}),
    ],
)
def test_product_module_export_inventory(module_name, expected):
    """Each public module limits wildcard imports to its intended product API."""
    qualified = f"pyflightstream.post.{module_name}"
    assert qualified in PUBLIC_MODULES
    module = importlib.import_module(qualified)
    assert hasattr(module, "__all__"), f"{qualified} must declare __all__"
    assert set(module.__all__) == expected
    assert len(module.__all__) == len(expected), f"{qualified} repeats an export"
    namespace = {}
    exec(f"from {qualified} import *", namespace)
    assert namespace.keys() - {"__builtins__"} == expected
    for name in expected:
        product_name = _PRODUCTS_PRIVATE_ALIASES.get(name, name)
        assert namespace[name] is getattr(products, product_name), (
            f"post.products.{product_name} must preserve the same exported object"
        )
