"""The ``pyfs-geom`` command line: run, loop, inspect and move the geometry pipeline.

Pipeline role: thin. Each verb parses its arguments, calls the entry of
:mod:`pyflightstream.workspace.geometry_pipeline` (or reads the pure configuration boundary of
:mod:`pyflightstream.geometry`), prints the record it returns as JSON and exits 0, 1 or 2.

``run CONFIG --out DIR`` runs the stages S0 to S13 (``--until`` ends earlier, ``--set
component.key=value`` overrides a value, ``--configuration`` and ``--variant`` choose what is
built). ``doe CONFIG SETS --out DIR`` runs one report per parameter set of ``SETS``, a TOML
file with one ``[[sets]]`` table per set whose keys are the override paths, and continues
after a failed set. ``validate`` resolves the configuration and prints every value with its
source; ``configurations`` and ``stages`` list what a configuration and the pipeline hold;
``schema``, ``identify`` and ``check`` read a component record or an original IGES;
``add-control-surface`` and ``split-symmetry`` edit a written IGES.

Exit codes: 0 accepted, 1 a run failed at a stage (the report names the stage and the check),
2 an input is refused or the gmsh library cannot load, with the message on standard error,
3 incomplete: no check failed but a check of the stage table was not measured (a stage not
built), and the report lists each one in ``not_run``. For ``doe`` the code is the worst of its
sets, refused over failed over incomplete over accepted.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from pyflightstream._cli import cli_entrypoint
from pyflightstream._errors import InputValueError, PyflightstreamError
from pyflightstream.geometry.stages import STAGE_ROWS, exit_code
from pyflightstream.run._geom_cli_moved import add_moved_verbs, report_of

__all__ = ["main"]


def _value(text: str) -> Any:
    """Return a TOML value read from ``text``, or the text itself when it is not TOML."""
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def _overrides(items: list[str] | None) -> dict[str, Any]:
    """Return ``{path: value}`` from ``--set path=value`` items; a repeat or a bare path refuses."""
    found: dict[str, Any] = {}
    for item in items or []:
        key, separator, text = item.partition("=")
        if not separator or not key:
            raise InputValueError(f"--set {item!r}: expected component.key=value")
        if key in found:
            raise InputValueError(f"--set {key}: given twice")
        found[key] = _value(text)
    return found


def _read_sets(path: str) -> list[dict[str, Any]]:
    """Read the parameter sets of a ``[[sets]]`` file; a misspelt table or key is refused."""
    with Path(path).open("rb") as stream:
        data = tomllib.load(stream)
    extra = sorted(set(data) - {"sets"})
    if extra or not isinstance(data.get("sets"), list) or not data["sets"]:
        raise InputValueError(
            f"{path}: expected one or more [[sets]] tables and nothing else "
            f"(other keys: {extra or 'none'})"
        )
    return [_flat(row) for row in data["sets"]]


def _flat(row: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Return the overrides of one set with a nested table read as its dotted paths.

    ``FUS.length = 2.5`` written unquoted is the table ``{"FUS": {"length": 2.5}}`` in TOML,
    and means the same override as ``"FUS.length" = 2.5``.
    """
    found: dict[str, Any] = {}
    for key, value in row.items():
        path = f"{prefix}{key}"
        pairs = _flat(value, f"{path}.") if isinstance(value, dict) else {path: value}
        for leaf, item in pairs.items():
            if leaf in found:
                raise InputValueError(f"[[sets]]: {leaf} given twice")
            found[leaf] = item
    return found


#: The order of the exit codes from best to worst, for the code of a loop of sets.
_RANK = (0, 3, 1, 2)


def _print_report(report: dict[str, Any]) -> int:
    print(json.dumps(report, indent=2, default=str))
    return exit_code(report)


def _run(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    try:
        overrides = _overrides(args.set)
    except InputValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    report = run_geometry(
        args.config,
        out=args.out,
        configuration=args.configuration,
        variant=args.variant,
        overrides=overrides,
        until=args.until,
    )
    if report["status"] == "refused":
        print(report["message"], file=sys.stderr)
    return _print_report(report)


def _doe(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import run_doe

    def work() -> dict[str, Any]:
        sets = _read_sets(args.sets)
        names = [row.pop("name", f"set-{i + 1:04d}") for i, row in enumerate(sets)]
        reports = list(
            run_doe(
                args.config,
                sets,
                out=args.out,
                configuration=args.configuration,
                variant=args.variant,
                until=args.until,
                workers=args.workers,
            )
        )
        worst = max((exit_code(r) for r in reports), key=_RANK.index)
        return {
            "sets": [{"name": n, "report": r} for n, r in zip(names, reports, strict=True)],
            "accepted": worst == 0,
            "exit": worst,
        }

    try:
        record = work()
    except (OSError, PyflightstreamError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(record, indent=2, default=str))
    return int(record["exit"])


def _validate(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import describe_config

    return report_of(lambda: describe_config(args.config))


def _configurations(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import list_configurations

    return report_of(lambda: list_configurations(args.config))


def _stages(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import built_stages

    built = built_stages()
    rows = [
        {
            "stage": row.stage,
            "name": row.name,
            "kernel": row.kernel,
            "built": row.stage in built,
            "checks": [{"id": cid, "limit": limit} for cid, limit in row.checks],
        }
        for row in STAGE_ROWS
    ]
    return report_of(lambda: {"stages": rows})


def _add_control_surface(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import add_control_surfaces

    def work() -> dict[str, Any]:
        with Path(args.entry).open("rb") as stream:
            entry = tomllib.load(stream)
        return add_control_surfaces(args.iges, args.component, [entry], args.out)

    return report_of(work)


def _split_symmetry(args: argparse.Namespace) -> int:
    from pyflightstream.workspace.geometry_pipeline import split_symmetry

    return report_of(
        lambda: split_symmetry(args.iges, args.out, plane=args.plane, component=args.component)
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfs-geom", description="Parametric geometry pipeline of pyflightstream."
    )
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--configuration", metavar="NAME", help="entry of the configuration registry"
        )
        sub.add_argument("--variant", default="clean", metavar="V", help="variant (default: clean)")
        sub.add_argument(
            "--until",
            default="S13",
            metavar="Sxx",
            help="last stage to run, S0 to S13 (default S13; S9 needs no kernel)",
        )

    run = verbs.add_parser("run", help="run the stages S0 to S13 and write the report")
    run.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
    run.add_argument("--out", required=True, metavar="DIR", help="folder of the records and files")
    run.add_argument(
        "--set",
        action="append",
        metavar="K=V",
        help="override one value, component.key=value (repeatable; the value is TOML)",
    )
    common(run)
    run.set_defaults(handler=_run)

    doe = verbs.add_parser("doe", help="one report per parameter set; continues after a failure")
    doe.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
    doe.add_argument("sets", metavar="SETS", help="TOML with one [[sets]] table per parameter set")
    doe.add_argument(
        "--out", required=True, metavar="DIR", help="folder of set-0001, set-0002, ..."
    )
    doe.add_argument("--workers", type=int, default=1, metavar="N", help="sets in parallel")
    common(doe)
    doe.set_defaults(handler=_doe)

    for name, handler, text in (
        ("validate", _validate, "resolve the configuration and print every value with its source"),
        ("configurations", _configurations, "list the configurations, variants and members"),
    ):
        sub = verbs.add_parser(name, help=text)
        sub.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
        sub.set_defaults(handler=handler)

    stages = verbs.add_parser("stages", help="list the stages, their checks and limits")
    stages.set_defaults(handler=_stages)

    add_moved_verbs(verbs)

    control = verbs.add_parser("add-control-surface", help="add control surfaces to an IGES")
    control.add_argument("iges", metavar="IGES")
    control.add_argument("component", metavar="COMPONENT")
    control.add_argument("entry", metavar="ENTRY", help="the entry (TOML)")
    control.add_argument("--out", required=True, metavar="DIR")
    control.set_defaults(handler=_add_control_surface)

    split = verbs.add_parser("split-symmetry", help="cut a full model at its symmetry plane")
    split.add_argument("iges", metavar="IGES", help="the full model, read only")
    split.add_argument("--out", required=True, metavar="IGES", help="the half model to write")
    split.add_argument("--plane", default="y", choices=("x", "y", "z"), help="plane (default y)")
    split.add_argument("--component", metavar="NAME", help="cut this component only")
    split.set_defaults(handler=_split_symmetry)
    return parser


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-geom``; returns the exit code (0 accepted, 1 failed, 2 refused, 3 incomplete)."""
    args = _build_parser().parse_args(argv)
    handler = getattr(args, "handler", None) or args.mesh_command
    try:
        return int(handler(args))
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
