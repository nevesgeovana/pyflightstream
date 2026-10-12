"""P0400-FFTABLE: the ``[farfield]`` table of the pproc artifact (FR-454)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec
from pyflightstream.cases._farfield_spec import BALANCES, FarfieldSpec, LatticeShape


def _pproc(farfield: object | None = None, **extra: object) -> PprocSpec:
    data: dict[str, object] = {"groups": {"1": "all"}, **extra}
    if farfield is not None:
        data["farfield"] = farfield
    return PprocSpec.model_validate(data)


@pytest.mark.requirement("FR-454")
def test_p0400_fftable_keys_and_defaults():
    """P0400-FFTABLE (FR-454 R1): each key with its type and default."""
    spec = _pproc({"families": "all", "trefftz": {"variant": "sections"}}).farfield
    assert spec is not None and spec.trefftz is not None
    assert spec.trefftz.variant == ["sections"]
    assert spec.trefftz.stations == 80
    assert spec.trefftz.distance_bref == 0.25
    assert spec.trefftz.plane_bref() == (0.75, 0.5, 0.01)
    assert spec.trefftz.station is None
    assert spec.ledgers is None
    ledgers = _pproc({"families": "W", "ledgers": {"rotor": "ROTOR"}}).farfield.ledgers
    assert ledgers.balances == list(BALANCES) and ledgers.m_max == 6
    assert ledgers.build(2.0).tip_radius == 2.0


@pytest.mark.requirement("FR-454")
def test_p0400_fftable_variant_is_a_word_or_a_list():
    """P0400-FFTABLE (FR-454 R3): ``variant`` reads like ``families``."""
    word = FarfieldSpec.model_validate({"families": "all", "trefftz": {"variant": "wake"}})
    many = FarfieldSpec.model_validate(
        {"families": ["W", "HT"], "trefftz": {"variant": ["sections", "wake", "plane"]}}
    )
    assert word.trefftz.variant == ["wake"]
    assert many.trefftz.variant == ["sections", "wake", "plane"]


@pytest.mark.parametrize(
    ("farfield", "words"),
    [
        ({"families": "all", "trefftz": {"variant": "sections"}, "extra": 1}, "extra"),
        ({"families": "all", "trefftz": {"variant": "sections", "stationz": 3}}, "stationz"),
        ({"families": "all", "trefftz": {"variant": "helix"}}, "variant"),
        ({"families": "all", "trefftz": {"variant": ["wake", "wake"]}}, "wake"),
        ({"families": "all", "trefftz": {}}, "variant"),
        ({"families": "all", "trefftz": {"variant": "plane", "stations": 1}}, "stations"),
        ({"families": "all", "trefftz": {"variant": "plane", "distance_bref": 0}}, "distance"),
        ({"families": "all", "trefftz": {"variant": "plane", "spacing_bref": "nan"}}, "spacing"),
        ({"families": "all"}, "selects no analysis"),
        ({"families": [], "trefftz": {"variant": "sections"}}, "families"),
        ({"families": "all", "ledgers": {}}, "rotor"),
        ({"families": "all", "ledgers": {"rotor": "R", "frame": "F"}}, "rotor"),
        ({"families": "all", "ledgers": {"rotor": "R", "balances": ["mass", "mass"]}}, "mass"),
        ({"families": "all", "ledgers": {"rotor": "R", "balances": ["drag"]}}, "balances"),
        ({"families": "all", "ledgers": {"rotor": "R", "m_max": 40}}, "m_max"),
        (
            {"families": "all", "ledgers": {"rotor": "R", "r_inner": 2.0, "r_outer": 1.0}},
            "ring_edges",
        ),
    ],
)
@pytest.mark.requirement("FR-454")
def test_p0400_fftable_refusals_name_the_key(farfield, words):
    """P0400-FFTABLE (FR-454 R2): each malformed table is refused at load, naming its key."""
    with pytest.raises((ValidationError, ValueError)) as caught:
        _pproc(farfield)
    assert words in str(caught.value)


@pytest.mark.requirement("FR-454")
def test_p0400_fftable_without_farfield_dumps_as_before():
    """P0400-FFTABLE (FR-454): an artifact without ``[farfield]`` dumps as 0.39.0 did."""
    spec = _pproc()
    assert spec.farfield is None
    dumped = spec.model_dump(exclude_defaults=True)
    assert "farfield" not in dumped
    assert all(not entry.lattices for entry in spec.probes)


@pytest.mark.requirement("FR-454")
def test_p0400_fftable_a_lattice_is_a_probe_shape():
    """P0400-FFTABLE and FR-459 R2: ``[[probes]] lattices`` takes the ledgers' geometry keys."""
    spec = _pproc(
        None,
        probes=[{"frame": "REFERENCE", "lattices": [{"rotor": "ROTOR", "n_psi": 24}]}],
    )
    (shape,) = spec.probes[0].lattices
    assert isinstance(shape, LatticeShape) and shape.build(1.0).n_psi == 24
    with pytest.raises(ValidationError, match="tip_radius_m"):
        LatticeShape(frame="F")


@pytest.mark.requirement("FR-454")
def test_p0400_fftable_the_planted_unknown_key_is_refused():
    """P0400-FFTABLE: the mutant that accepts an unknown key is caught by ``extra='forbid'``."""
    for model in (FarfieldSpec, LatticeShape):
        assert model.model_config.get("extra") == "forbid"
        assert model.model_config.get("allow_inf_nan") is False
