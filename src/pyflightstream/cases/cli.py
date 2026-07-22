"""The ``pyfs-matrix`` command line.

Pipeline role: drives the legacy run matrix as a first-class interface
of the file-managed modality from a terminal. ``pyfs-matrix convert``
emits the native ``campaign.toml`` equivalent of a matrix (FR-11), the
canonical internal form; ``pyfs-matrix plan`` binds the matrix codes
to the workspace input library and pre-flights every point without
executing anything. There is deliberately no ``run`` subcommand:
execution stays a Python-API decision
(:func:`pyflightstream.cases.matrix_legacy.run_matrix`) with an
explicit executable path, because the solver quality judgment and the
recipe registry are code, not command-line strings.
"""

from __future__ import annotations

import argparse
import sys

from pyflightstream.cases.matrix_legacy import (
    LegacyMatrixError,
    convert_matrix,
    plan_matrix,
)


def _parse_recipes(pairs: list[str]) -> dict[str, str]:
    """Turn repeated ``CODE=module:function`` options into the mapping."""
    recipes: dict[str, str] = {}
    for item in pairs:
        code, separator, reference = item.partition("=")
        if not separator or not code or not reference:
            raise ValueError(
                f"--recipe expects CODE=module:function (the FS_SCRIPT code and the "
                f"recipe it maps to), got {item!r}"
            )
        recipes[code.strip()] = reference.strip()
    return recipes


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("matrix", help="the legacy pipe-delimited run matrix file")
    parser.add_argument(
        "--name",
        required=True,
        help="campaign name; the matrix has none, so it is explicit input",
    )
    parser.add_argument(
        "--fs-version",
        required=True,
        help="FlightStream version, canonical or alias (for example 26.120)",
    )
    parser.add_argument(
        "--recipe",
        action="append",
        default=[],
        metavar="CODE=MODULE:FUNCTION",
        help="FS_SCRIPT code to recipe reference (repeatable); replaces the legacy "
        "import-by-number system",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-matrix",
        description=(
            "Legacy run-matrix tooling: the matrix is a first-class interface of the "
            "file-managed modality, with campaign.toml as the canonical internal form."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    convert = subparsers.add_parser(
        "convert",
        help="emit the native campaign.toml equivalent of a matrix (FR-11)",
    )
    _add_common_arguments(convert)
    convert.add_argument(
        "--fs-exe",
        required=True,
        help="explicit path of the FlightStream executable (never guessed)",
    )
    convert.add_argument(
        "-o",
        "--output",
        help="write the campaign.toml here instead of standard output",
    )

    plan = subparsers.add_parser(
        "plan",
        help="bind the matrix to the workspace input library and pre-flight every "
        "point, executing nothing",
    )
    _add_common_arguments(plan)
    plan.add_argument(
        "--workspace",
        default=".",
        help="managed campaign root carrying the inputs/ library (default: the current directory)",
    )
    plan.add_argument(
        "--fs-exe",
        help="explicit executable override; mandatory for MANUAL rows, otherwise the "
        "FS_BUILD column resolves through inputs/executables.toml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-matrix``; returns the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        recipes = _parse_recipes(args.recipe)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.subcommand == "convert":
        return _cmd_convert(args, recipes)
    return _cmd_plan(args, recipes)


def _cmd_convert(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    try:
        text = convert_matrix(
            args.matrix,
            name=args.name,
            fs_version=args.fs_version,
            fs_exe=args.fs_exe,
            recipes=recipes,
        )
    except (LegacyMatrixError, OSError, ValueError) as error:
        print(f"matrix not converted: {error}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"campaign written: {args.output}")
    else:
        print(text, end="")
    return 0


def _cmd_plan(args: argparse.Namespace, recipes: dict[str, str]) -> int:
    from pyflightstream.workspace import CampaignWorkspace, InputArtifactError

    workspace = CampaignWorkspace(args.workspace)
    try:
        plan = plan_matrix(
            args.matrix,
            workspace,
            name=args.name,
            fs_version=args.fs_version,
            recipes=recipes,
            fs_exe=args.fs_exe,
        )
    except (LegacyMatrixError, InputArtifactError, OSError, ValueError) as error:
        print(f"matrix not planned: {error}", file=sys.stderr)
        return 2
    print(plan.summary())
    if plan.plan_file is not None:
        print(f"plan: {plan.plan_file}")
    return 1 if plan.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
