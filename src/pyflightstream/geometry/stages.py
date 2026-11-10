"""The pure stages of the geometry pipeline, for the workspace and the command line.

Pipeline role: the one public home of the numerical building blocks that the kernel stages
(:mod:`pyflightstream.workspace.geometry_pipeline`) and the ``geometry`` verbs of the command
line call: the B-spline :class:`Patch`, the generation of the components of a resolved
configuration and their regions, the body and lifting-surface skins and the flat tip cap, the
placement of a wing in the frame of its body, the mesh spacing rules and the mesh checks, the
OBJ writer, the mathematics of reading a lifting surface back from sections, the record
boundary (schema export, pin verification, configuration writing), and ``junctions``, the
namespace of the measured checks and limits of the S10 junction sub-steps.

The pin check of a component record and the configuration writer are defined here; the other
names are defined in the private modules of this package and re-exported, so a caller in
another package imports this module and no private path. The functions import no geometry
kernel and no solver; they need numpy and scipy only. The names that matter to a user are the
entry points of :mod:`pyflightstream.workspace.geometry_pipeline` and the configuration
boundary of :mod:`pyflightstream.geometry`; the rest is the contract between the two
packages and may change between releases while the module is provisional.

Examples
--------
>>> from pyflightstream.geometry.stages import Mesh, Patch
>>> Patch.__name__, Mesh.__name__
('Patch', 'Mesh')
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pyflightstream._errors import InputValueError
from pyflightstream._textio import write_text
from pyflightstream.geometry import _junctions as junctions
from pyflightstream.geometry._blister import blister_model
from pyflightstream.geometry._bodies import body
from pyflightstream.geometry._boundary import export_schema, sha256_file, unpack
from pyflightstream.geometry._caps import tip_cap
from pyflightstream.geometry._fillet import fillet_model
from pyflightstream.geometry._generation import assembly_regions, generate_components
from pyflightstream.geometry._identity import parameter_id
from pyflightstream.geometry._lifting import lifting_surface
from pyflightstream.geometry._mesh_rules import (
    check_body,
    check_lifting,
    chord_fraction,
    chord_nodes,
    constant,
    count_classes,
    insert_seed,
    load_mesh_controls,
    tip_refinement,
)
from pyflightstream.geometry._mesh_topology import (
    Mesh,
    check_mesh,
    orient_mesh,
    oriented_source_normals,
    repair_inverted,
    write_obj,
)
from pyflightstream.geometry._patch import Patch, evaluate_patch
from pyflightstream.geometry._placement import wing_in_body_frame
from pyflightstream.geometry._records import (
    CheckFailedError,
    check_entry,
    exit_code,
    geometry_report,
    stage_record,
    write_record,
)
from pyflightstream.geometry._reverse import (
    clean_band,
    closed_contour,
    contour_features,
    cosine,
    fit_section,
    leading_extension,
    reference_planform,
    refine_tip,
)
from pyflightstream.geometry._stage_table import STAGE_ROWS, StageRow, stage_index, stage_row
from pyflightstream.geometry._toml_keys import adopt_surface_file
from pyflightstream.geometry.component import ComponentRecord

__all__ = [
    "CheckFailedError",
    "Mesh",
    "Patch",
    "STAGE_ROWS",
    "StageRow",
    "adopt_surface_file",
    "assembly_regions",
    "blister_model",
    "body",
    "check_body",
    "check_entry",
    "check_lifting",
    "check_mesh",
    "chord_fraction",
    "chord_nodes",
    "clean_band",
    "closed_contour",
    "constant",
    "contour_features",
    "cosine",
    "count_classes",
    "evaluate_patch",
    "exit_code",
    "export_schema",
    "fillet_model",
    "fit_section",
    "generate_components",
    "geometry_report",
    "insert_seed",
    "junctions",
    "leading_extension",
    "lifting_surface",
    "load_mesh_controls",
    "orient_mesh",
    "oriented_source_normals",
    "parameter_id",
    "reference_planform",
    "refine_tip",
    "repair_inverted",
    "stage_index",
    "stage_record",
    "stage_row",
    "tip_cap",
    "tip_refinement",
    "unpack",
    "verify_pins",
    "wing_in_body_frame",
    "write_config",
    "write_obj",
    "write_record",
]


def _toml_value(value):
    """Render a plain value as an inline TOML value."""
    if isinstance(value, dict):
        return (
            "{ " + ", ".join(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in value.items()) + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return repr(value)
    raise InputValueError(f"Unsupported TOML value: {value!r}")


def write_config(config, path):
    """Write a resolved configuration as TOML that :func:`load_config` reads back unchanged.

    Parameters
    ----------
    config : dict
        Resolved configuration of plain values.
    path : str or Path
        File to write.
    """
    text = "\n".join(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in config.items()) + "\n"
    write_text(path, text)


def verify_pins(record: ComponentRecord, asset_root: str | Path) -> list[str]:
    """Check every referenced file against its pin; return one message per failure.

    Paths resolve against ``asset_root``. An empty list means every referenced
    file exists with matching bytes. A path that escapes the root is a failure.

    Parameters
    ----------
    record : ComponentRecord
        The component record whose referenced files are checked.
    asset_root : str or Path
        Directory against which the referenced paths resolve.

    Returns
    -------
    list of str
        One message per failure; empty when every pin holds.
    """
    root = Path(asset_root).resolve()
    problems: list[str] = []
    for reference in record.referenced_files():
        target = (root / reference.path).resolve()
        if root != target and root not in target.parents:
            problems.append(f"{reference.path}: outside the asset root")
        elif not target.is_file():
            problems.append(f"{reference.path}: missing")
        elif sha256_file(target) != reference.sha256:
            problems.append(f"{reference.path}: SHA-256 differs from the pin")
    return problems
