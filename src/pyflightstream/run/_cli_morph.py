"""The ``pyfs-workspace geometry`` verbs that write a new mesh and print its record.

Pipeline role: the run layer's parsers and handlers for the verbs a morphing control file
drives, ``repitch``, ``collapse-te``, ``hub-rings``, ``morph`` and ``scale`` (PFS-2189, PFS-2193,
PFS-2222), and for
the verbs that read named IGES files, ``iges-grid`` and ``iges-convert`` (PFS-2198, PFS-2199,
on the gmsh kernel), and ``prop-slice``, which cuts a propeller into sections (PFS-2223). The
work is the workspace layer's
(:mod:`pyflightstream.workspace.repitch`, :mod:`pyflightstream.workspace.collapse_te`,
:mod:`pyflightstream.workspace.hub_rings`, :mod:`pyflightstream.workspace.morph`,
:mod:`pyflightstream.workspace.iges_grid`, :mod:`pyflightstream.workspace.iges_convert`,
:mod:`pyflightstream.workspace.prop_slice`); this
module only reads the command line, calls it, prints the checks or the record it returns and
gives the exit code: 0 when the output was written, 2 when the input is refused or the gmsh
library cannot load, with the message on standard error and nothing written. Each parser names its
handler as the ``mesh_command`` default, which :mod:`pyflightstream.run._cli_geometry` calls, so
the group adds every verb of this module through :func:`add_morph_verbs` and lists them by
:data:`MORPH_VERBS`, which also carries ``mesh-generated`` and ``mesh`` (strategy 1 from
per-component mesh controls, PFS-2214).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.run._geom_cli_moved import report_of, write_json

__all__ = ["MORPH_VERBS", "add_morph_verbs"]


def print_checks(work: Callable[[], dict[str, Any]]) -> int:
    """Run one verb, print the checks it returns and return the exit code."""
    try:
        report = work()
    except (OSError, PyflightstreamError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, default=str))
    return 0


def add_repitch_parser(subparsers: Any) -> None:
    """Add the rigid-blade repitch verb with its morphing control file."""
    parser = subparsers.add_parser(
        "repitch",
        help="rigidly repitch blades and rebuild the named hub around their roots",
        description=(
            "MESH is an OBJ or a saved simulation (.fsm). The [repitch] table of the morphing "
            "file names the blades, the hub and the angle; each blade turns rigidly about its "
            "pitch axis; [repitch] hub_method chooses how the hub follows: its complete quad "
            "rings move (rings), the band around each turned root is remeshed quad-dominant "
            "(remesh, OBJ only), or auto picks one. The checks are written to "
            "<out>.repitch.json. Quality findings are warned with their numbers and the mesh "
            "is written; a broken input or invariant refuses and nothing is written "
            "(docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj or .fsm, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [repitch] table")
    parser.add_argument("--out", required=True, help="new mesh of the same kind")
    parser.set_defaults(mesh_command=run_repitch)


def run_repitch(args: argparse.Namespace) -> int:
    """Run repitch and print the checks written beside its output."""
    from pyflightstream.workspace.repitch import repitch_mesh

    return print_checks(lambda: repitch_mesh(args.mesh, args.morphing, args.out))


def add_collapse_te_parser(subparsers: Any) -> None:
    """Add the verb that collapses a blunt trailing edge, with its morphing control file."""
    parser = subparsers.add_parser(
        "collapse-te",
        help="collapse the blunt trailing edge of named blades of an OBJ",
        description=(
            "MESH is an OBJ. The [collapse_te] table of the morphing file names the blades; "
            "each pair of rim nodes across a blade's one-cell base strip merges at its "
            "midpoint and the strip leaves. Every other node and face keeps its place; the "
            "boundaries file gets one trailing-edge line per blade and the checks are written "
            "to <out>.collapse.json. Quality findings (a face the merge turns over) are warned "
            "with their numbers and the mesh is written; a broken input or invariant refuses "
            "and nothing is written (docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [collapse_te] table")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_collapse_te)


def run_collapse_te(args: argparse.Namespace) -> int:
    """Run collapse-te and print the checks written beside its output."""
    from pyflightstream.workspace.collapse_te import collapse_trailing_edge

    return print_checks(lambda: collapse_trailing_edge(args.mesh, args.morphing, args.out))


def add_hub_rings_parser(subparsers: Any) -> None:
    """Add the verb that rebuilds a hub around blade roots as rings of quads."""
    parser = subparsers.add_parser(
        "hub-rings",
        help="rebuild the named hub around blade roots as rings of quads, on an OBJ",
        description=(
            "MESH is an OBJ. The [hub_rings] table of the morphing file states rings (and "
            "optionally band_width); blades and hub sit at the top or in the table. Per "
            "blade, rings rows of quads are marched outward from the root on the hub, the hub "
            "faces they reach plus one layer leave, and the band between them is remeshed "
            "quad-dominant. Blade nodes, other families and the hub's seams stay to the bit; the "
            "checks are written to <out>.hub_rings.json. Quality findings are warned with their "
            "numbers and the mesh is written; a broken input or invariant refuses and nothing "
            "is written (docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [hub_rings] table")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_hub_rings)


def run_hub_rings(args: argparse.Namespace) -> int:
    """Run hub-rings and print the checks written beside its output."""
    from pyflightstream.workspace.hub_rings import hub_rings_mesh

    return print_checks(lambda: hub_rings_mesh(args.mesh, args.morphing, args.out))


def add_morph_parser(subparsers: Any) -> None:
    """Add the verb that applies every table of a morphing control file, in its fixed order."""
    parser = subparsers.add_parser(
        "morph",
        help="apply the morphing file's tables in order: hub rings, repitch, collapse, wheel",
        description=(
            "MESH is an OBJ, a sector or a full wheel. The tables the morphing file holds are "
            "applied in one fixed order: [hub_rings], [repitch], [collapse_te], [wheel] (a "
            "sector only), each with its own checks; blades and hub sit at the top of the file. "
            "One OBJ is written with its boundaries file, its points files and "
            "<out>.morph.json. Each step warns of quality with its numbers and goes on; "
            "nothing is written when a step refuses a broken input or invariant "
            "(docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML control file of the chain")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_morph)


def run_morph(args: argparse.Namespace) -> int:
    """Run the morphing chain and print the record written beside its output."""
    from pyflightstream.workspace.morph import morph_mesh

    return print_checks(lambda: morph_mesh(args.mesh, args.morphing, args.out))


def add_scale_parser(subparsers: Any) -> None:
    """Add the verb that scales an OBJ uniformly into a new output folder."""
    parser = subparsers.add_parser(
        "scale",
        help="scale every vertex of an OBJ by a factor about a point, into a new folder",
        description=(
            "FACTOR is a positive number (0.5 halves every length). Every vertex of the OBJ "
            "given by --mesh is scaled about the origin, or about --about x,y,z; face order, "
            "groups, normals and comments stay byte for byte; for a .fsm only the x, y and z "
            "node rows of the mesh block change. --out names an output folder, "
            "created with its parents, that receives the scaled OBJ under the input name and "
            "<name>.scale.json (input digest, factor, centre, counts, bounding boxes before "
            "and after). Default folder: <stem>_scaled<factor> beside the input. The input is "
            "never overwritten; an existing same-name file in the folder is refused unless "
            "--force (docs/geometry.md)."
        ),
    )
    parser.add_argument("factor", help="positive uniform scale factor, for example 0.5")
    parser.add_argument("--mesh", required=True, help="source .obj or .fsm, read only")
    parser.add_argument("--out", help="output folder, created; default <stem>_scaled<factor>")
    parser.add_argument("--about", help="scale centre x,y,z (default 0,0,0)")
    parser.add_argument("--force", action="store_true", help="replace same-name files in --out")
    parser.set_defaults(mesh_command=run_scale)


def run_scale(args: argparse.Namespace) -> int:
    """Run scale and print the record written beside the scaled OBJ."""
    from pyflightstream.workspace.scale import scale_mesh

    return print_checks(
        lambda: scale_mesh(args.mesh, args.factor, out=args.out, about=args.about, force=args.force)
    )


def _add_name_encoding(parser: Any) -> None:
    parser.add_argument(
        "--name-encoding",
        default="latin-1",
        help=(
            "text encoding of the NAME bytes in the IGES files (default latin-1, one "
            "character per byte; use utf-8 for UTF-8 names). Never guessed: a name invalid "
            "in the encoding is refused"
        ),
    )


def add_iges_grid_parser(subparsers: Any) -> None:
    """Add the verb that grids named IGES components into one OBJ."""
    parser = subparsers.add_parser(
        "iges-grid",
        help="grid the named components of IGES files into one OBJ (uses the gmsh kernel)",
        description=(
            "Each component the IGES files name (the NAME of a level) becomes one family of the "
            "OBJ. Faces are joined so shared edges are conformal; four-sided patches follow the "
            "laws of the grid control file and become quads, other patches are quad-dominant at "
            "the component's size. Writes the OBJ, <out>.boundaries.toml for mark-boundaries, "
            "one points file per trailing edge found and the record <out>.json. Each junction of "
            "two components is measured against the original faces of both. Quality is "
            "warned, never refused (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--grid", required=True, help="grid control file (TOML)")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.add_argument(
        "--component",
        dest="components",
        action="append",
        metavar="NAME",
        help=(
            "grid only this component, named as the files name it (repeatable); the others "
            "leave the model before the join. An unknown or ambiguous name is refused with the "
            "names found. Default: every component"
        ),
    )
    _add_name_encoding(parser)
    parser.set_defaults(mesh_command=run_iges_grid)


def run_iges_grid(args: argparse.Namespace) -> int:
    """Run iges-grid and print the record written beside its output."""
    from pyflightstream.workspace.iges_grid import grid_iges

    return print_checks(
        lambda: grid_iges(
            args.iges,
            args.grid,
            args.out,
            name_encoding=args.name_encoding,
            components=args.components,
        )
    )


def add_iges_convert_parser(subparsers: Any) -> None:
    """Add the verb that rewrites named IGES files as one IGES of B-spline faces."""
    parser = subparsers.add_parser(
        "iges-convert",
        help="rewrite IGES files as one IGES of B-spline faces, names kept (uses the gmsh kernel)",
        description=(
            "Every face of the IGES files is converted to a B-spline surface and written to one "
            "IGES, each component on its own level with one NAME, so the solver's CAD import "
            "and this package read the same components back. The first file's length unit is "
            "kept. Writes the IGES and the record <out>.json (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--out", required=True, help="new .igs")
    _add_name_encoding(parser)
    parser.set_defaults(mesh_command=run_iges_convert)


def run_iges_convert(args: argparse.Namespace) -> int:
    """Run iges-convert and print the record written beside its output."""
    from pyflightstream.workspace.iges_convert import convert_iges

    return print_checks(lambda: convert_iges(args.iges, args.out, name_encoding=args.name_encoding))


def add_mesh_generated_parser(subparsers: Any) -> None:
    """Add the verb that meshes a parametric configuration into an all-quad OBJ."""
    parser = subparsers.add_parser(
        "mesh-generated",
        help="mesh a parametric configuration into an all-quad OBJ (uses the gmsh kernel)",
        description=(
            "Resolves the configuration and meshes its patches from their role: constant "
            "spanwise width with a refined tip, chordwise growth from the leading edge, "
            "constant azimuth and axial step on a body, a planar all-quad flat tip cap and, "
            "for a wing on a body, the fairing as one quad-dominant transition ring. The "
            "orientation is outward. The record (counts, the acceptance checks, the spacing "
            "rules) is printed; the OBJ holds one group per component."
        ),
    )
    parser.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
    parser.add_argument("--obj", required=True, help="new .obj")
    parser.add_argument(
        "--component",
        metavar="NAME",
        help="mesh this body or lifting surface alone, in its own frame (default: the assembly)",
    )
    parser.add_argument(
        "--controls",
        metavar="TOML",
        help="mesh controls overriding the defaults, by table: lifting_surface, body, checks, "
        "assembly",
    )
    parser.add_argument("--out", metavar="JSON", help="also write the record to this file")
    parser.set_defaults(mesh_command=run_mesh_generated)


def run_mesh_generated(args: argparse.Namespace) -> int:
    """Run mesh-generated: write the OBJ and print the record of its checks."""
    from pyflightstream.geometry import load_config
    from pyflightstream.workspace.geometry_pipeline import mesh_generated

    def work() -> dict[str, Any]:
        resolved = load_config(args.config)
        result = mesh_generated(
            resolved, component=args.component, controls=args.controls, obj=args.obj
        )
        record = {"obj": args.obj, **result.record}
        write_json(args.out, record)
        return record

    return report_of(work)


def add_prop_slice_parser(subparsers: Any) -> None:
    """Add the verb that slices a propeller into sections and the G17 builder's inputs."""
    parser = subparsers.add_parser(
        "prop-slice",
        help="cut a propeller OBJ or IGES into blade sections and a G17 definition",
        description=(
            "Isolates one blade about the axis, cuts it at radial stations by the planes the "
            "G17 builder places its sections in, and writes to --out the normalized profile of "
            "each station (sections/sNN.dat), the table over r/R of chord, pitch angle, "
            "thickness, camber, skew and rake (table.csv), the G17 definition that rebuilds "
            "the propeller (propeller.toml) and the record prop-slice.json. An IGES is read "
            "by the gmsh kernel (docs/propeller.md)."
        ),
    )
    parser.add_argument("--geometry", required=True, help="the propeller, .obj, .igs or .iges")
    parser.add_argument("--blades", required=True, type=int, help="the number of blades")
    parser.add_argument(
        "--axis",
        nargs=3,
        type=float,
        metavar=("DX", "DY", "DZ"),
        help="thrust direction, the builder's frame.thrust_dir (default -1 0 0)",
    )
    parser.add_argument(
        "--origin",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="a point of the shaft in mm (default 0 0 0)",
    )
    parser.add_argument(
        "--blade-dir",
        nargs=3,
        type=float,
        metavar=("DX", "DY", "DZ"),
        help="reference blade direction; blade 0 is the nearest (default 0 0 1)",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        type=float,
        metavar="R_R",
        help="r/R of the sections (default 21 steps from the root to the tip, and 0.7)",
    )
    parser.add_argument(
        "--unit", default="mm", choices=("mm", "cm", "m", "in"), help="OBJ length unit (mm)"
    )
    parser.add_argument("--out", required=True, help="the folder to write")
    parser.set_defaults(mesh_command=run_prop_slice)


def run_prop_slice(args: argparse.Namespace) -> int:
    """Run prop-slice and print the record written to the folder."""
    from pyflightstream.workspace.prop_slice import slice_propeller

    return print_checks(
        lambda: slice_propeller(
            args.geometry,
            blades=args.blades,
            out=args.out,
            axis=args.axis,
            origin=args.origin,
            blade_dir=args.blade_dir,
            stations=args.stations,
            unit=args.unit,
        )
    )


def add_mesh_parser(subparsers: Any) -> None:
    """Add ``geometry mesh``: a configuration meshed by strategy 1 from its mesh controls."""
    mesh = subparsers.add_parser(
        "mesh",
        help="mesh a parametric configuration from its mesh controls (strategy 1 or 2, gmsh)",
        description=(
            "Validates the mesh controls against the configuration (errors E01 to E16 refuse "
            "by name, W01 warns), plans every component's counts, meshes the configuration "
            "with strategy 1, or strategy 2 (full grid) when mesh.strategy = 2, and measures the "
            "acceptance table of that strategy on the realized mesh. With "
            "--dry-run it prints the plan and the warnings and writes nothing. With --out it "
            "writes <descriptor>.obj, <descriptor>.mesh.json and, with --fsm-template, "
            "<descriptor>.fsm. One of --out and --dry-run is required, and --descriptor and "
            "--fsm-template need --out (docs/geometry-mesh.md)."
        ),
    )
    mesh.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
    mesh.add_argument("--controls", required=True, metavar="TOML", help="the mesh controls")
    mesh.add_argument(
        "--dry-run", action="store_true", help="validate and print the planned counts only"
    )
    mesh.add_argument("--out", metavar="DIR", help="folder of the written mesh and record")
    mesh.add_argument("--descriptor", metavar="NAME", help="file stem (mesh.output.descriptor)")
    mesh.add_argument(
        "--fsm-template",
        metavar="FSM",
        help="a fresh saved simulation of the target build; writes <descriptor>.fsm",
    )
    mesh.set_defaults(mesh_command=run_mesh)


def _mesh_arguments_refusal(args: argparse.Namespace) -> str:
    """Return why the arguments of ``geometry mesh`` cannot run, before the kernel opens."""
    stated = (("--descriptor", args.descriptor), ("--fsm-template", args.fsm_template))
    named = [flag for flag, value in stated if value is not None]
    if named and (args.dry_run or args.out is None):
        return (
            f"geometry mesh: {' and '.join(named)} name written files, so they need --out DIR "
            "and no --dry-run. Nothing was meshed."
        )
    if not args.dry_run and args.out is None:
        return (
            "geometry mesh: give --out DIR to write the mesh and its record, or --dry-run to "
            "print the plan only. Nothing was meshed."
        )
    return ""


def run_mesh(args: argparse.Namespace) -> int:
    """Plan or mesh a configuration; exit 0 accepted or planned, 1 not accepted, 2 refused."""
    refusal = _mesh_arguments_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    from pyflightstream.workspace.geometry_pipeline import mesh_configuration

    try:
        result = mesh_configuration(
            args.config,
            args.controls,
            dry_run=args.dry_run,
            out=args.out,
            descriptor=args.descriptor,
            fsm_template=args.fsm_template,
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    record = result.record
    for warning in record["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    shown = {k: record[k] for k in ("strategy", "variant", "members", "components")}
    if not args.dry_run:
        shown.update(counts=record["counts"], accepted=record["accepted"])
        shown["failed"] = [c["id"] for c in record["checks"] if c["status"] == "failed"]
    print(json.dumps(shown, indent=2, default=str))
    for path in result.written.values():
        print(path)
    return 0 if args.dry_run or record["accepted"] else 1


#: The parser of each verb this module adds, by its name in the group.
_PARSERS: dict[str, Callable[[Any], None]] = {
    "repitch": add_repitch_parser,
    "collapse-te": add_collapse_te_parser,
    "hub-rings": add_hub_rings_parser,
    "morph": add_morph_parser,
    "scale": add_scale_parser,
    "iges-grid": add_iges_grid_parser,
    "iges-convert": add_iges_convert_parser,
    "mesh-generated": add_mesh_generated_parser,
    "prop-slice": add_prop_slice_parser,
    "mesh": add_mesh_parser,
}

#: The verbs this module adds to the group.
MORPH_VERBS = tuple(_PARSERS)


def add_morph_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` group."""
    for add in _PARSERS.values():
        add(verbs)
