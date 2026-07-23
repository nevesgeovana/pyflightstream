"""Tier 1: the options registry (D1 adoption, pandas register_option model).

Pipeline role: quality gate on the package's declared knobs. The
registry serves exact keys only (no pattern matching, by design), and
its refusals follow the openmdao message contract: unknown keys list
every registered key, rejected values name the option, the received
value, and the accepted form. The first consumer is the pyfs-qa CLI,
whose machine knobs (scratch root, timeouts) default from here.
"""

from __future__ import annotations

import pytest

from pyflightstream import options
from pyflightstream.options import (
    OptionError,
    describe_option,
    get_option,
    option_context,
    register_option,
    reset_option,
    set_option,
)

# --- exact keys, get/set/reset ----------------------------------------------


def test_set_get_reset_round_trip():
    assert get_option("qa.probe_timeout_s") == 120.0
    set_option("qa.probe_timeout_s", 30.0)
    assert get_option("qa.probe_timeout_s") == 30.0
    reset_option("qa.probe_timeout_s")
    assert get_option("qa.probe_timeout_s") == 120.0


def test_unknown_key_lists_the_registered_keys():
    with pytest.raises(
        OptionError,
        match=r"no option is registered under 'qa\.nonexistent'.*Keys are exact.*"
        r"Registered keys: .*qa\.scratch_root",
    ):
        get_option("qa.nonexistent")


def test_partial_keys_never_match():
    """Deliberate difference from pandas: a prefix is an unknown key."""
    with pytest.raises(OptionError, match="Keys are exact"):
        get_option("qa.probe")
    with pytest.raises(OptionError, match="Keys are exact"):
        set_option("qa", 1.0)


# --- validation and the message contract ------------------------------------


def test_rejected_value_names_option_value_and_accepted_form():
    with pytest.raises(
        OptionError,
        match=r"option 'qa\.probe_timeout_s' rejects value -3\.0: a strictly "
        r"positive number of seconds is required",
    ):
        set_option("qa.probe_timeout_s", -3.0)


def test_bool_is_not_a_number_of_seconds():
    with pytest.raises(OptionError, match="rejects value True"):
        set_option("qa.case_timeout_s", True)


def test_scratch_root_requires_non_empty_path_text():
    with pytest.raises(OptionError, match=r"rejects value '': a non-empty path string"):
        set_option("qa.scratch_root", "")


def test_registering_a_default_that_fails_its_own_validator_is_refused():
    with pytest.raises(OptionError, match="rejects value -1"):
        register_option(
            "test.bad_default", default=-1, doc="doc", validator=options.positive_seconds
        )
    # The failed registration left nothing behind.
    with pytest.raises(OptionError, match="no option is registered"):
        get_option("test.bad_default")


def test_duplicate_registration_is_refused():
    register_option("test.once", default=1, doc="declared once")
    with pytest.raises(OptionError, match=r"'test\.once' is already registered"):
        register_option("test.once", default=2, doc="declared twice")


def test_register_option_fields_are_keyword_only():
    """default and doc would swap silently for string options if positional."""
    with pytest.raises(TypeError):
        register_option("test.positional", "value", "doc")  # noqa: PLE0101


def test_path_options_accept_pathlib_paths():
    from pathlib import Path

    set_option("qa.scratch_root", Path("D:/scratch"))
    assert str(get_option("qa.scratch_root")) in ("D:\\scratch", "D:/scratch")


def test_reset_and_describe_refuse_unknown_keys():
    with pytest.raises(OptionError, match="Keys are exact"):
        reset_option("qa.nope")
    with pytest.raises(OptionError, match="Keys are exact"):
        describe_option("qa.nope")


def test_option_context_refuses_unknown_keys_untouched():
    with pytest.raises(OptionError, match="Keys are exact"):
        with option_context("qa.nope", 1.0):
            pass  # pragma: no cover - never entered


# --- option_context ---------------------------------------------------------


def test_option_context_sets_and_restores():
    set_option("qa.probe_timeout_s", 60.0)
    with option_context("qa.probe_timeout_s", 5.0, "qa.scratch_root", "elsewhere"):
        assert get_option("qa.probe_timeout_s") == 5.0
        assert get_option("qa.scratch_root") == "elsewhere"
    assert get_option("qa.probe_timeout_s") == 60.0
    assert get_option("qa.scratch_root") == "runs"


def test_option_context_validates_before_changing_anything():
    with pytest.raises(OptionError, match="rejects value -1"):
        with option_context("qa.scratch_root", "elsewhere", "qa.probe_timeout_s", -1):
            pass  # pragma: no cover - never entered
    # The valid first pair was not applied either.
    assert get_option("qa.scratch_root") == "runs"


def test_option_context_refuses_odd_arguments():
    with pytest.raises(OptionError, match="alternating key and value"):
        with option_context("qa.probe_timeout_s"):
            pass  # pragma: no cover - never entered


# --- describe_option --------------------------------------------------------


def test_describe_option_shows_value_default_and_doc():
    set_option("qa.probe_timeout_s", 45.0)
    text = describe_option("qa.probe_timeout_s")
    assert "qa.probe_timeout_s: 45.0 (default 120.0)" in text
    assert "wall-clock limit" in text
    everything = describe_option()
    assert "qa.scratch_root" in everything and "qa.case_timeout_s" in everything


# --- the first consumer: pyfs-qa defaults -----------------------------------


def test_qa_cli_defaults_follow_the_options():
    from pyflightstream.qa import cli

    with option_context(
        "qa.scratch_root", "scratch", "qa.probe_timeout_s", 7.0, "qa.case_timeout_s", 11.0
    ):
        parser = cli._build_parser()
    probe = parser._subparsers._group_actions[0].choices["probe"]
    physics = parser._subparsers._group_actions[0].choices["physics"]
    drift = parser._subparsers._group_actions[0].choices["drift"]
    assert probe.get_default("workroot") == "scratch/probes"
    assert probe.get_default("timeout") == 7.0
    assert physics.get_default("workroot") == "scratch/physics"
    assert physics.get_default("timeout") == 11.0
    assert drift.get_default("workroot") == "scratch/drift"
    assert drift.get_default("timeout") == 11.0
