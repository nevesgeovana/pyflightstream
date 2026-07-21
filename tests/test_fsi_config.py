"""Tier 1: FsiConfig schema, validation, and round-trip IO (WP0)."""

import pytest
from conftest import make_uniform_blade_config
from pydantic import ValidationError

from pyflightstream.fsi.config import FsiConfig, config_hash, dump_config, load_config


def test_round_trip_load_validate_dump(tmp_path, uniform_blade_config):
    """WP0 verification: load, validate, dump reproduces the config."""
    path = tmp_path / "config.json"
    dump_config(uniform_blade_config, path)
    loaded = load_config(path)
    assert loaded == uniform_blade_config
    # A second round trip is byte-stable.
    path2 = tmp_path / "config2.json"
    dump_config(loaded, path2)
    assert path2.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_config_hash_stable_across_round_trip(tmp_path, uniform_blade_config):
    """The hash identifies the configuration, not its file formatting."""
    path = tmp_path / "config.json"
    dump_config(uniform_blade_config, path)
    assert config_hash(load_config(path)) == config_hash(uniform_blade_config)
    # Reformatting the JSON (indentation, key order) keeps the hash.
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    reordered = {k: raw[k] for k in sorted(raw, reverse=True)}
    path.write_text(json.dumps(reordered), encoding="utf-8")
    assert config_hash(load_config(path)) == config_hash(uniform_blade_config)


def test_config_hash_changes_with_a_value(uniform_blade_config):
    """Any physical change must change the traceability hash (FSI-R15)."""
    faster = uniform_blade_config.model_copy(update={"omega_rad_per_s": 100.0})
    assert config_hash(faster) != config_hash(uniform_blade_config)


def test_station_count_mismatch_names_the_field():
    """The error must name the offending distribution, not just fail."""
    cfg = make_uniform_blade_config()
    data = cfg.model_dump()
    data["blade"]["chord_m"] = data["blade"]["chord_m"][:-1]
    with pytest.raises(ValidationError, match="chord_m"):
        FsiConfig.model_validate(data)


def test_radii_must_increase_root_to_tip():
    """Stations out of order describe no physical blade."""
    cfg = make_uniform_blade_config()
    data = cfg.model_dump()
    radii = data["blade"]["station_radii_m"]
    radii[2], radii[3] = radii[3], radii[2]
    with pytest.raises(ValidationError, match="strictly increase"):
        FsiConfig.model_validate(data)


def test_zero_stiffness_rejected_with_physical_cause():
    """Zero EI makes the static solve singular; the message says so."""
    cfg = make_uniform_blade_config()
    data = cfg.model_dump()
    data["blade"]["bending_stiffness_n_m2"][0] = 0.0
    with pytest.raises(ValidationError, match="singular"):
        FsiConfig.model_validate(data)


def test_unknown_field_rejected():
    """Typos in config.json must fail loudly, not be ignored."""
    cfg = make_uniform_blade_config()
    data = cfg.model_dump()
    data["omega_rpm"] = 2000.0
    with pytest.raises(ValidationError):
        FsiConfig.model_validate(data)


def test_relaxation_factor_bounded():
    """lambda outside (0, 1] is not a relaxation, it is divergence."""
    cfg = make_uniform_blade_config()
    data = cfg.model_dump()
    data["phases"]["coupling_relaxation"] = 1.5
    with pytest.raises(ValidationError):
        FsiConfig.model_validate(data)
