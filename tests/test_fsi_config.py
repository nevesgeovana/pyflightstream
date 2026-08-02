"""Tier 1: FsiConfig schema, validation, and round-trip IO (WP0)."""

import pytest
from conftest import make_uniform_blade_config
from pydantic import ValidationError

from pyflightstream.fsi.config import (
    BladeProperties,
    FsiConfig,
    config_hash,
    dump_config,
    load_config,
)
from pyflightstream.fsi.state import FsiState, check_state_matches_config


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


# PYFS-012, the REV-002 blocker. Its probe was designed by PFS-0 rather than
# published by the review, and both halves of the claim held.


def _uniform_blade_kwargs(n=4):
    """The smallest valid blade, as a plain dict, for mutation per field."""
    return dict(
        station_radii_m=[0.2 + 0.2 * i for i in range(n)],
        chord_m=[0.1] * n,
        mass_per_length_kg_per_m=[2.0] * n,
        inertia_major_kg_m=[1.0e-3] * n,
        inertia_minor_kg_m=[2.0e-4] * n,
        bending_stiffness_n_m2=[120.0] * n,
        torsion_stiffness_n_m2=[40.0] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    )


def test_an_all_nan_blade_is_refused():
    """PFS-0's probe: every distribution NaN, and nothing complained.

    NaN is not a near miss here, it is the single value that satisfies EVERY
    check in the model at once, because each of them is a comparison and a
    comparison against NaN is False. Radii "strictly increase", chord is
    "positive", stiffness is "positive", inertia is "nonnegative".
    """
    kwargs = {name: [float("nan")] * 4 for name in _uniform_blade_kwargs()}
    with pytest.raises(ValidationError, match="non-finite"):
        BladeProperties(**kwargs)


@pytest.mark.parametrize("field", sorted(_uniform_blade_kwargs()))
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_single_non_finite_entry_is_refused_in_every_distribution(field, bad):
    """One bad value in any one of the twelve distributions.

    Parametrized over every field rather than sampling one, because the
    defect was that the checks are per-field comparisons: a guard written
    for the fields someone happened to think of would leave the rest open.
    """
    kwargs = _uniform_blade_kwargs()
    kwargs[field] = list(kwargs[field])
    kwargs[field][2] = bad
    with pytest.raises(ValidationError, match="non-finite"):
        BladeProperties(**kwargs)


def test_an_ordinary_blade_is_still_accepted():
    """The control: the guard must cost a real blade nothing."""
    blade = BladeProperties(**_uniform_blade_kwargs())
    assert len(blade.station_radii_m) == 4


def test_the_ordinary_physical_refusals_still_fire():
    """The other control.

    A guard that ran first and swallowed everything would satisfy the tests
    above while removing the checks it was added in front of.
    """
    kwargs = _uniform_blade_kwargs()
    kwargs["chord_m"] = [0.1, -0.1, 0.1, 0.1]
    with pytest.raises(ValidationError, match="positive"):
        BladeProperties(**kwargs)

    kwargs = _uniform_blade_kwargs()
    kwargs["station_radii_m"] = [0.2, 0.2, 0.6, 0.8]
    with pytest.raises(ValidationError, match="strictly increase"):
        BladeProperties(**kwargs)


def test_a_state_from_a_different_blade_shape_is_refused():
    """The second half: resume validated the state's TYPES, never its SHAPE.

    PFS-0 measured a 5-station, 3-blade config resuming on a 3-station,
    2-blade state with nothing raised. The arrays are consumed positionally,
    so the run keeps producing plausible numbers from memory belonging to a
    structure that does not exist.
    """
    state = FsiState(previous_twist_rad=[[0.0] * 3, [0.0] * 3])
    with pytest.raises(ValueError, match="does not describe the configured blade"):
        check_state_matches_config(state, blade_count=3, station_count=5)

    # blade count alone
    with pytest.raises(ValueError, match="blade"):
        check_state_matches_config(state, blade_count=3, station_count=3)
    # station count alone
    with pytest.raises(ValueError, match="station"):
        check_state_matches_config(state, blade_count=2, station_count=5)


def test_a_matching_state_passes_and_an_empty_one_is_not_a_mismatch():
    """The control, including the first call of a run, which has no memory."""
    check_state_matches_config(
        FsiState(previous_twist_rad=[[0.0] * 3, [0.0] * 3]),
        blade_count=2,
        station_count=3,
    )
    check_state_matches_config(FsiState(), blade_count=3, station_count=5)


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_scalar_is_refused_too(bad):
    """The SCALAR half of PYFS-012, closed after the QA re-run pass argued it.

    The list guard covers the per-station distributions. The scalar fields
    were left to their pydantic bounds, and a bound is a comparison:
    Field(ge=0.0) accepts infinity, because inf >= 0 is True. So
    omega_rad_per_s could be infinite, which is the centrifugal-tension
    source, one line above the fields the guard was written for. NaN happened
    to be caught by the same bound, which is what made the hole look closed.
    """
    with pytest.raises(ValidationError):
        make_uniform_blade_config().model_copy(
            update={"omega_rad_per_s": bad}
        ).__class__.model_validate(
            make_uniform_blade_config().model_dump() | {"omega_rad_per_s": bad}
        )


def test_check_state_matches_config_refuses_positional_counts():
    """The keyword-only guard, which had no test.

    Its whole justification is that two same-typed ints transposed silently
    give either a spurious refusal or a silent acceptance of the exact
    mismatch the function exists to catch.
    """
    with pytest.raises(TypeError):
        check_state_matches_config(FsiState(), 3, 11)
