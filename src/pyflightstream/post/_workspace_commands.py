"""Post-owned workspace verbs registered below the post layer."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.post.corrections import sector_offset_calibration
from pyflightstream.workspace.cli import register_command_group


def _add_calibrate(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "calibrate", help="derive a sector-offset calibration from two recorded rotor points"
    )
    parser.add_argument("calibration_id")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--wheel-run", required=True)
    parser.add_argument("--sector-run", required=True)
    parser.add_argument("--rotor", dest="rotor_name")
    parser.add_argument("--matrix")
    parser.add_argument("--overwrite", action="store_true")


def _calibrate(args: argparse.Namespace) -> int:
    try:
        path = sector_offset_calibration(
            args.workspace,
            wheel_run_id=args.wheel_run,
            sector_run_id=args.sector_run,
            calibration_id=args.calibration_id,
            rotor=args.rotor_name,
            matrix_stem=args.matrix,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, PyflightstreamError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"{path}: sector-offset route, not validated")
    return 0


register_command_group("calibrate", _add_calibrate, _calibrate)
