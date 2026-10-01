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
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.cases.acoustics",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.cases.ccs_fuselage",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.cases.ccs_revolution",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.cases.ccs_wing",
    # 0.31.0 (P0310-CAL-SCHEMA): the quasi-steady wheel's correction choice and
    # its calibration file. PUBLIC deliberately: a user writing or checking a
    # calibration reads it with `read_calibration` here.
    "pyflightstream.cases.corrections",
    "pyflightstream.cases.field_coverage",
    "pyflightstream.cases.freestream",
    "pyflightstream.cases.fsi_workspace",
    "pyflightstream.cases.matrix",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.mesh",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.naming",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.pproc",
    # 0.30.0: the quasi-steady rotor's arithmetic, clocking and 1P reduced
    # frequency. PUBLIC deliberately: a user checking a blade's k by hand, or the
    # clockings of a wheel, calls it.
    "pyflightstream.cases.qsteady",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.reference_blocks",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.selection",
    # 0.34.0 (AD-16): a model module cut out of the root, which re-exports its names.
    "pyflightstream.cases.settings",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.cases.setup_surfaces",
    # 0.24.0: the one resolver of an unsteady row's averaging window. PUBLIC
    # deliberately: a post-processing choice needs no new run, so a user who
    # recomputes a window off a recorded plan calls `averaging_steps` here.
    "pyflightstream.cases.windows",
    "pyflightstream.cases.workflows",
    "pyflightstream.commands",
    "pyflightstream.exceptions",
    "pyflightstream.extras",
    "pyflightstream.farfield",
    "pyflightstream.fsi",
    "pyflightstream.fsi.beam",
    "pyflightstream.fsi.calibration",
    "pyflightstream.fsi.centrifugal",
    "pyflightstream.fsi.cli",
    "pyflightstream.fsi.config",
    "pyflightstream.fsi.driver",
    "pyflightstream.fsi.errors",
    "pyflightstream.fsi.kinematics",
    "pyflightstream.fsi.loads",
    # 0.28.0 (G41): the versioned materials database and the solid-section
    # calculator that turns a blade's geometry into its structural
    # distributions. PUBLIC deliberately, and NOT extra-gated: both need
    # numpy only, so a blade's properties can be generated on a base
    # install; the beam that consumes them is what needs `[fsi]`.
    "pyflightstream.fsi.materials",
    "pyflightstream.fsi.nodes",
    "pyflightstream.fsi.sections",
    "pyflightstream.fsi.state",
    # 0.30.0 (FSI-G): the fixed wing's structural solve, its own weight.
    "pyflightstream.fsi.wing",
    "pyflightstream.options",
    "pyflightstream.overview",
    "pyflightstream.post",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.post.acoustics",
    # 0.24.0: the one home of the frame conventions. PUBLIC deliberately: a
    # user checking which frame a published axis column is in, or turning a
    # vector of their own the way the polar does, calls `polar_axis_coefficients`.
    "pyflightstream.post.axes",
    "pyflightstream.post.boundary_layer",
    # 0.31.0 (P0310-ROUTE2): the quasi-steady wheel's corrected products and
    # diagnostic. PUBLIC deliberately: `sector_offset_calibration` is what a user
    # calls to build a route 2 file from her recorded runs.
    "pyflightstream.post.corrections",
    "pyflightstream.post.custom_polar",
    # 0.24.0: the evaluator of a pproc `[equations]` table. PUBLIC deliberately:
    # `resolve_symbol` IS the rule by which a symbol finds its column, the
    # generated guide and the workspace page both state it, and a user asking
    # why `CL` read `CL_WING` is who calls it.
    "pyflightstream.post.diagnostics",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.post.disc_maps",
    "pyflightstream.post.equations",
    # v0.23.0 item 11: the generated pproc guides. PUBLIC deliberately: a
    # user who wants the variable reference and the equation guide beside
    # her pproc is who calls it. It lives in `post` and not in `workspace`
    # because it documents the pproc spec AND the products, and the layer
    # test refused the other placement -- deferring an import to call time
    # does not change its direction.
    "pyflightstream.post.field_frames",
    # 0.33.0 (AD-11): the input glossary, cut out of post.guides, which
    # re-exports every public name of it at its 0.32.0 path.
    "pyflightstream.post.glossary",
    "pyflightstream.post.guides",
    # 0.31.0 (P0310-HARMONICS): the per-station harmonic product. PUBLIC
    # deliberately: its least-squares fit is what a user checks a station of
    # the product against, on samples of her own.
    "pyflightstream.post.harmonics",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.post.inflow_tools",
    # 0.33.0 (AD-11): the input template, cut out of post.guides, which
    # re-exports every public name of it at its 0.32.0 path.
    "pyflightstream.post.input_template",
    # 0.33.0 (AD-13, WP5): the product families cut out of post.products, which
    # re-exports every name of their __all__ at its 0.32.0 path; with polar,
    # rotor_table and unsteady_polar below.
    "pyflightstream.post.point_tables",
    "pyflightstream.post.polar",
    "pyflightstream.post.probe_fields",
    "pyflightstream.post.products",
    "pyflightstream.post.provenance",
    # 0.30.0: the quasi-steady rotor's clockings and average tables. PUBLIC
    # deliberately: its readers of a point's record are what a user re-posting a
    # wheel by hand calls.
    "pyflightstream.post.qsteady",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.post.qsteady_noise",
    "pyflightstream.post.reductions",
    "pyflightstream.post.rotor_table",
    "pyflightstream.post.section_distributions",
    "pyflightstream.post.series",
    "pyflightstream.post.settings_table",
    "pyflightstream.post.superfile",
    # G25 of 0.28.0: the surface averaged by the package over a window of per-step
    # exports. PUBLIC deliberately: the average a campaign writes is one a user can
    # take of per-step exports of her own, with the writer every Tecplot uses.
    "pyflightstream.post.surfaces",
    "pyflightstream.post.unsteady",
    "pyflightstream.post.unsteady_polar",
    "pyflightstream.post.writers",
    "pyflightstream.probes",
    "pyflightstream.probes.errors",
    "pyflightstream.probes.geometry",
    "pyflightstream.probes.planar",
    "pyflightstream.qa",
    "pyflightstream.qa.cli",
    "pyflightstream.qa.compat",
    "pyflightstream.qa.cost",
    "pyflightstream.qa.drift",
    "pyflightstream.qa.errors",
    "pyflightstream.qa.geometry",
    # PFS-2031.17: the driver that reads the physics cases out of a
    # campaign workspace, the library half of `pyfs-qa physics`.
    "pyflightstream.qa.matrix",
    "pyflightstream.qa.physics",
    "pyflightstream.qa.probes",
    "pyflightstream.qa.reports",
    "pyflightstream.qa.specs",
    "pyflightstream.reference",
    "pyflightstream.results",
    "pyflightstream.results.conditions",
    # 0.33.0 (AD-11): the four modules cut out of the results root (core,
    # exports, loads, log), which re-exports every public name of them at
    # its 0.32.0 path.
    "pyflightstream.results.core",
    "pyflightstream.results.exports",
    "pyflightstream.results.loads",
    "pyflightstream.results.log",
    # G45 of 0.28.0: the surface solution read from the solver's VTK and written
    # as Tecplot. PUBLIC deliberately: the translation a campaign runs on every
    # point is one a user can run on a VTK of her own, and the time-averaged
    # surface is written by the same writer.
    "pyflightstream.results.native_surface",
    # 0.33.0 (AD-10, P0330-WP2): the sectional loads parser moved here from
    # fsi.loads, which re-exports it; PUBLIC because the export conversion
    # table names this module as the parser's home.
    "pyflightstream.results.sectional_loads",
    "pyflightstream.results.surface",
    "pyflightstream.results.tables",
    "pyflightstream.run",
    "pyflightstream.run.cli",
    # FR-99 at 0.18.0. PUBLIC deliberately: the collect stage is a thing a
    # user drives, from `pyfs-matrix collect` or from a cron that imports
    # `collect_once` and schedules its own polling, which is half the point
    # of one-shot being the primitive.
    "pyflightstream.run.collect",
    "pyflightstream.run.matrix",
    # 0.32.0 preparation (P0): a contract module, its body filled by its work package.
    "pyflightstream.run.records",
    # 0.21.0: the renaming command's module. PUBLIC deliberately, for the same
    # reason as the collect stage: `rename_workspace` is a thing a user drives,
    # from `pyfs-matrix rename` or from a script that moves several workspaces.
    "pyflightstream.run.rename",
    "pyflightstream.script",
    "pyflightstream.script.entities",
    "pyflightstream.script.helpers",
    "pyflightstream.script.motion",
    "pyflightstream.script.rotor_vocabulary",
    "pyflightstream.script.solver_setup",
    "pyflightstream.script.toggles",
    "pyflightstream.support",
    "pyflightstream.testing",
    "pyflightstream.utils",
    "pyflightstream.utils.cli",
    "pyflightstream.utils.database",
    "pyflightstream.utils.errors",
    "pyflightstream.utils.manual",
    "pyflightstream.versions",
    "pyflightstream.workspace",
    # 0.33.0 (AD-11): the build registry, cut out of workspace.inputs, which
    # re-exports every public name of it at its 0.32.0 path.
    "pyflightstream.workspace.builds",
    "pyflightstream.workspace.cli",
    "pyflightstream.workspace.excel",
    "pyflightstream.workspace.excel_bridge",
    "pyflightstream.workspace.excel_file",
    "pyflightstream.workspace.excel_sync",
    # 0.31.0 (G3): the field operations behind `pyfs-workspace field` (mirror,
    # move, subtract, time mean) that build a custom free-stream file. PUBLIC
    # deliberately: a script composes them on fields it already holds, the
    # same reason `storage` is public.
    "pyflightstream.workspace.fields",
    "pyflightstream.workspace.flight_condition",
    "pyflightstream.workspace.fsi_setup",
    # 0.33.0 (AD-11): the HPC profile, cut out of workspace.inputs, which
    # re-exports every public name of it at its 0.32.0 path.
    "pyflightstream.workspace.hpc",
    "pyflightstream.workspace.inputs",
    "pyflightstream.workspace.matrix",
    "pyflightstream.workspace.naming",
    # v0.23.0 item 14: the migration that moves a workspace's polar products
    # from the numbered group suffix onto the group's own name. PUBLIC
    # deliberately: a user holding products from an earlier release is who
    # runs it, and a migration nobody can reach is a migration that does not
    # happen. Its changelog entry is in the [Unreleased] breaking section.
    "pyflightstream.workspace.rename_groups",
    # PFS-2025.20: the trailing-edge extraction. Public deliberately, and
    # NOT in EXTRA_GATED_MODULES: after the trimesh promotion it must
    # import on a base install with no extras, which is the whole point
    # of the promotion and what PFS-2025.20.03 measures.
    # 0.33.0 (AD-11): the rule on empty entity selections, cut out of
    # workspace.inputs, which re-exports every public name of it.
    "pyflightstream.workspace.selections",
    "pyflightstream.workspace.setup_inspection",
    "pyflightstream.workspace.setup_standards",
    # 0.33.0 (AD-11): the geometry sidecars, cut out of workspace.inputs,
    # which re-exports every public name of them at their 0.32.0 path.
    "pyflightstream.workspace.sidecars",
    # 0.30.0: the four `pyfs-matrix` storage commands (space-in-use,
    # free-space, delete-sims, sync). PUBLIC deliberately: it is the home of
    # the storage/sync functions a script calls directly, the same reason
    # `matrix` and `excel_sync` are public.
    "pyflightstream.workspace.storage",
    "pyflightstream.workspace.trailing_edges",
    "pyflightstream.workspace.wake_edges",
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
    "pyflightstream.fsi.wing",  # imports beam
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
