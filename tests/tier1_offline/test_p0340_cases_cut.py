"""Tier 1, 0.34.0 work package WP8 (AD-16): the models of the cases root live in six modules.

Until 0.34.0 the root of :mod:`pyflightstream.cases` held every model of a case
definition, 2316 code lines, the one module of the package over the hard limit
of AD-08. The cut of AD-16 moves the models to six public modules (``pproc``,
``reference_blocks``, ``settings``, ``mesh``, ``naming`` and ``selection``) and
the root re-exports them. What must stay true, each test carrying the marker
P0340-CASES-CUT and the decision AD-16 in its own source:

* the root's ``__all__`` keeps the content and the order of v0.33.0, and every
  public name the v0.33.0 root defined is still reachable from the root as the
  very object its new module defines, so ``isinstance`` and a patch see one
  thing at both paths;
* none of the six imports the root, module-level or deferred, and the six form
  no import cycle among themselves, with ``settings`` reading ``mesh`` and never
  the reverse; each reader runs once on a planted import as its control;
* the six are not exempt from the static type checker: the exemption list of
  ``pyproject.toml`` names none of them.
"""

from __future__ import annotations

import ast
import fnmatch
import importlib
import json
import tomllib
from pathlib import Path

import pytest

import pyflightstream.cases as cases

REPO = Path(__file__).resolve().parents[2]
CASES_DIR = Path(cases.__file__).parent
SIX = ("pproc", "reference_blocks", "settings", "mesh", "naming", "selection")
ROOT = "pyflightstream.cases"

# The __all__ of src/pyflightstream/cases/__init__.py at the tag v0.33.0
# (git show v0.33.0:src/pyflightstream/cases/__init__.py); the order is part of
# the contract.
_ORIGINAL_ALL = [
    "AXIS_UNIT_VECTORS",
    "AliasCycleError",
    "BladeDatum",
    "ROTOR_BLADE_ROTATION_AXIS",
    "RotorBlock",
    "ActuatorBlock",
    "ROTATION_OFFSET_KEY",
    "ROTATION_SWEEP_KEY",
    "Campaign",
    "CampaignConfigError",
    "DEFAULT_DRIFT_LIMIT_PCT",
    "DerivedFrom",
    "FluidState",
    "EVERY_SURFACE",
    "CadImportOptions",
    "MeshImport",
    "MeshOperation",
    "RawMeshConditions",
    "ReferenceData",
    "TrailingEdgeMarking",
    "ScriptRecipe",
    "SimCase",
    "BaseRegionOperation",
    "SolverSettings",
    "SolverToggle",
    "EXPORT_KINDS",
    "EXPORT_KIND_MEANINGS",
    "EXPORT_KIND_SINCE",
    "InputKey",
    "SOLVER_SETTING_COMMANDS",
    "OPT_IN_EXPORT_KINDS",
    "PLOT_TYPES",
    "STEADY_ONLY_EXPORT_KINDS",
    "FAMILY_SELECTORS",
    "FLUID_PLOT_PARAMETERS",
    "AXES_PLOT_COMPONENTS",
    "global_frame_plot_declarations",
    "AXES_PLOT_GROUP",
    "ROTOR_PLOT_GROUP_PREFIX",
    "FORCE_PLOT_PARAMETERS",
    "PPROC_FRAMES",
    "FrameSpec",
    "RAW_PHASES",
    "CustomFlag",
    "RawCommand",
    "PprocSpec",
    "SurfaceTimeAveragingSpec",
    "RESERVED_FRAME_NAMES",
    "SectionsSpec",
    "VOLUME_SECTION_KINDS",
    "VOLUME_SECTION_PRISMS",
    "VolumeSectionSpec",
    "PlotsSpec",
    "ProbesSpec",
    "SurfaceProbeSpec",
    "ProductsSpec",
    "ForcePlotGroup",
    "SectionDistribution",
    "ProbeLine",
    "select_families",
    "select_group_members",
    "resolve_alias",
    "BoundaryAliases",
    "EXPANDING_SELECTORS",
    "default_outputs",
    "classify_outputs",
    "SweepAxis",
    "check_recipe",
    "derived_body_sha256",
    "geometric_sweep_values",
    "load_campaign",
    "multiplied_sweep",
    "NameField",
    "POINT_AXIS_KEYS",
    "PointState",
    "case_at_point",
    "point_state_key",
    "POINT_NAME_FIELDS",
    "SWEEP_NAME_VALUE",
    "name_field",
    "point_name",
    "point_tag",
    "sweep_name",
    "resolve_recipe",
]

# Every public name the v0.33.0 root bound by a def, a class or an assignment at
# its top level, in __all__ or not, by the module that defines it since the cut.
# A name absent here stayed in the root.
_MOVED = {
    "pproc": [
        "EXPORT_KINDS",
        "PLOT_TYPES",
        "VOLUME_SECTION_KINDS",
        "EXPORT_KIND_SINCE",
        "STEADY_ONLY_EXPORT_KINDS",
        "OPT_IN_EXPORT_KINDS",
        "EXPORT_KIND_MEANINGS",
        "default_outputs",
        "classify_outputs",
        "FORCE_PLOT_PARAMETERS",
        "AXES_PLOT_COMPONENTS",
        "AXES_PLOT_GROUP",
        "ROTOR_PLOT_GROUP_PREFIX",
        "FLUID_PLOT_PARAMETERS",
        "FAMILY_SELECTORS",
        "PPROC_FRAMES",
        "Plane",
        "SectionDistribution",
        "SectionsSpec",
        "VOLUME_SECTION_PRISMS",
        "VolumeSectionSpec",
        "EXPANDING_FRAMES",
        "global_frame_plot_declarations",
        "ForcePlotGroup",
        "PlotsSpec",
        "ProbeLine",
        "ProbeRectangle",
        "ProbeCircle",
        "ProbesSpec",
        "SUPERFILE_FORMATS",
        "ProductsSpec",
        "DEFAULT_DRIFT_LIMIT_PCT",
        "PerRevolutionSpec",
        "PhaseLockedSpec",
        "EquationSpec",
        "SurfaceTimeAveragingSpec",
        "SurfaceProbeSpec",
        "PprocSpec",
    ],
    "reference_blocks": [
        "CampaignConfigError",
        "AXIS_UNIT_VECTORS",
        "ROTOR_BLADE_ROTATION_AXIS",
        "BladeDatum",
        "RotorBlock",
        "ActuatorOperation",
        "ActuatorBlock",
        "frame_basis_for_shaft",
        "AliasCycleError",
    ],
    "settings": [
        "ReferenceData",
        "SolverToggle",
        "SolverSettings",
        "FluidState",
        "PointState",
        "point_state_key",
    ],
    "mesh": [
        "EVERY_SURFACE",
        "MeshOperation",
        "CadImportOptions",
        "MeshImport",
        "TrailingEdgeRoute",
        "TrailingEdgeMarking",
        "RadialBoundaryMesh",
        "BaseRegionOperation",
        "PortBoundary",
        "RawMeshConditions",
    ],
    "naming": [
        "ROTATION_OFFSET_KEY",
        "ROTATION_SWEEP_KEY",
        "NameField",
        "POINT_NAME_FIELDS",
        "POINT_AXIS_KEYS",
        "SWEEP_NAME_VALUE",
        "name_field",
        "point_name",
        "sweep_name",
        "point_tag",
        "geometric_sweep_values",
        "multiplied_sweep",
    ],
    "selection": [
        "warn_a_selector_that_guesses",
        "select_families",
        "EXPANDING_SELECTORS",
        "BoundaryAliases",
        "resolve_alias",
        "alias_members_missing",
        "EVERY_FAMILY",
        "select_group_members",
    ],
}
_MOVED_PAIRS = [(module, name) for module, names in _MOVED.items() for name in names]

# The public names the v0.33.0 root defined and still defines.
_KEPT = [
    "InputKey",
    "ScriptRecipe",
    "SweepAxis",
    "RESERVED_FRAME_NAMES",
    "RESERVED_FRAME_PATTERN",
    "RAW_PHASES",
    "FLAG_PHASES",
    "CustomFlag",
    "RawCommand",
    "FrameSpec",
    "case_at_point",
    "SimCase",
    "DerivedFrom",
    "derived_body_sha256",
    "Campaign",
    "load_campaign",
    "resolve_recipe",
    "check_recipe",
]


def _imported_modules(source: str, own_package: str = ROOT) -> list[str]:
    """Return every module an import statement of ``source`` names, at any depth.

    Module-level and deferred (inside a function or a class) alike. ``from X
    import Y`` names ``X`` and, because ``Y`` may be a submodule, ``X.Y``; a
    relative import is resolved against ``own_package``.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = own_package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            found.append(module)
            found.extend(f"{module}.{alias.name}" for alias in node.names)
    return found


def _imports_the_root(source: str) -> bool:
    """Whether ``source`` imports the package root, the ``pyflightstream.cases`` facade."""
    return ROOT in _imported_modules(source)


def _edges(sources: dict[str, str]) -> dict[str, set[str]]:
    """Return the import edges among the six: module -> the six it imports."""
    return {
        name: {
            other
            for other in sources
            if other != name and f"{ROOT}.{other}" in _imported_modules(text)
        }
        for name, text in sources.items()
    }


def _a_cycle(edges: dict[str, set[str]]) -> list[str]:
    """Return one import cycle of ``edges`` as a path, or an empty list."""
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str]:
        state[node] = 1
        path.append(node)
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == 1:
                return path[path.index(nxt) :] + [nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        state[node] = 2
        path.pop()
        return []

    for node in sorted(edges):
        if node not in state:
            found = visit(node)
            if found:
                return found
    return []


def _sources() -> dict[str, str]:
    return {name: (CASES_DIR / f"{name}.py").read_text(encoding="utf-8") for name in SIX}


def test_the_root_keeps_its_all_in_content_and_order():
    # P0340-CASES-CUT (AD-16): the root's __all__ is v0.33.0's, name for name.
    assert list(cases.__all__) == _ORIGINAL_ALL


@pytest.mark.parametrize(("module", "name"), _MOVED_PAIRS)
def test_a_moved_name_is_one_object_at_both_paths(module, name):
    # P0340-CASES-CUT (AD-16): a moved name is supported at both paths, the
    # root re-export and its new module, and the two are the same object.
    home = importlib.import_module(f"{ROOT}.{module}")
    assert name in vars(home), f"{name} is not defined in {ROOT}.{module}"
    assert getattr(cases, name) is vars(home)[name]


@pytest.mark.parametrize("name", _KEPT)
def test_a_kept_name_is_still_the_roots_own(name):
    # P0340-CASES-CUT (AD-16): what the root keeps it still defines itself, and
    # none of the six defines it too.
    assert name in vars(cases)
    for module in SIX:
        assert name not in vars(importlib.import_module(f"{ROOT}.{module}")), (
            f"{name} stayed in the root and is defined in {ROOT}.{module} too"
        )


def test_each_model_module_states_its_surface_and_the_root_re_exports_it():
    # P0340-CASES-CUT (AD-16): each of the six declares __all__; every name in
    # it is in the root's __all__ and is the root's object, so the root's API
    # reference page and the module's say the same thing.
    for name in SIX:
        module = importlib.import_module(f"{ROOT}.{name}")
        surface = getattr(module, "__all__", None)
        assert surface, f"{ROOT}.{name} declares no __all__"
        for entry in surface:
            assert entry in cases.__all__, f"{ROOT}.{name} exports {entry}, which the root does not"
            assert getattr(module, entry) is getattr(cases, entry)
    covered = {entry for name in SIX for entry in importlib.import_module(f"{ROOT}.{name}").__all__}
    moved_public = {n for names in _MOVED.values() for n in names} & set(_ORIGINAL_ALL)
    assert moved_public <= covered, sorted(moved_public - covered)


def test_no_model_module_imports_the_root():
    # P0340-CASES-CUT (AD-16): none of the six imports pyflightstream.cases,
    # module-level or deferred. The reader is first run on planted sources: a
    # deferred import of the root must be seen, and an import of a sibling
    # module must not be taken for one.
    planted = "def late():\n    from pyflightstream.cases import SimCase\n    return SimCase\n"
    assert _imports_the_root(planted)
    assert _imports_the_root("import pyflightstream.cases\n")
    assert _imports_the_root("from pyflightstream import cases\n")
    assert not _imports_the_root("from pyflightstream.cases.mesh import PortBoundary\n")
    offenders = [name for name, text in _sources().items() if _imports_the_root(text)]
    assert offenders == [], f"these model modules import the root: {offenders}"


def test_the_six_form_no_import_cycle_and_settings_reads_mesh_one_way():
    # P0340-CASES-CUT (AD-16): the import graph of the six, deferred imports
    # included, is acyclic, and the one forward reference of the old root is
    # an import of mesh into settings, in that direction only. The cycle finder
    # first runs on the real graph with a planted reverse edge as its control.
    sources = _sources()
    edges = _edges(sources)
    planted = {name: set(targets) for name, targets in edges.items()}
    planted["mesh"].add("settings")
    assert _a_cycle(planted), "the cycle finder did not see a planted mesh -> settings cycle"
    assert _a_cycle(edges) == []
    assert "mesh" in edges["settings"]
    assert "settings" not in edges["mesh"]


def test_the_six_are_not_exempt_from_the_type_checker():
    # P0340-CASES-CUT (AD-16): the root is exempt and the six are not; the
    # override list of pyproject.toml names none of them.
    # A pattern is read by mypy's own rule, so a wildcard such as
    # "pyflightstream.cases.*" counts as naming all six.
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    overrides = config["tool"]["mypy"].get("overrides", [])
    patterns: list[str] = []
    for entry in overrides:
        modules = entry["module"]
        patterns.extend([modules] if isinstance(modules, str) else modules)
    assert _covered(ROOT, patterns), "the control: the root is still exempt at 0.34.0"
    planted = [f"{ROOT}.*"]
    assert all(_covered(f"{ROOT}.{name}", planted) for name in SIX), (
        "the control: a planted wildcard override must count as naming all six"
    )
    named = sorted(f"{ROOT}.{name}" for name in SIX if _covered(f"{ROOT}.{name}", patterns))
    assert named == [], f"the exemption list names {named}"


def _covered(module: str, patterns: list[str]) -> bool:
    """Return whether a mypy override pattern list covers ``module``.

    mypy's rule: a name matches itself, and a pattern ending in ``.*`` also
    matches the package it names and every submodule; a ``*`` inside a
    pattern stands for one or more components.
    """
    for pattern in patterns:
        if pattern == module:
            return True
        if "*" not in pattern:
            continue
        if pattern.endswith(".*") and module == pattern[:-2]:
            return True
        if fnmatch.fnmatchcase(module, pattern):
            return True
    return False


def test_the_root_left_the_size_table_and_its_facade_entry_fell():
    # P0340-CASES-CUT (AD-16): cases/__init__.py is off the G1 table, and its G8
    # facade entry is under the 4916 of v0.33.0.
    baselines = json.loads(
        (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert "cases/__init__.py" not in baselines["module_code_lines"]
    assert baselines["facade_lines"]["cases/__init__.py"] < 4916
