"""0.57.0 PFS-2201.02: the command line spells the parallel count."""

import argparse

import pytest

from pyflightstream.run._cli_parsers import _parallel_count
from pyflightstream.run.cli import _build_parser


def test_p0570_e2201_the_flag_takes_a_positive_count_or_auto():
    assert _parallel_count("auto") == "auto"
    assert _parallel_count("3") == 3
    for bad in ("0", "-1", "two"):
        with pytest.raises(argparse.ArgumentTypeError):
            _parallel_count(bad)


def test_p0570_e2201_run_accepts_parallel_and_defaults_to_the_setup():
    parser = _build_parser()
    assert parser.parse_args(["run", "m.xlsx", "--parallel", "auto"]).parallel == "auto"
    assert parser.parse_args(["run", "m.xlsx", "--parallel", "2"]).parallel == 2
    assert parser.parse_args(["run", "m.xlsx"]).parallel is None
