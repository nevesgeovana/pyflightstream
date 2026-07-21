"""Tier 1: version registry behavior.

Ordering must come from the list position in ``commands/_meta.yaml``,
never from string or float comparison of the identifiers.
"""

import pytest

from pyflightstream.versions import FsVersion, UnknownVersionError, known_versions, resolve


def test_known_versions_ordered_by_list_position():
    versions = known_versions()
    assert [v.canonical for v in versions] == ["26.000", "26.100", "26.120"]
    assert [v.index for v in versions] == [0, 1, 2]
    assert versions[0] < versions[1] < versions[2]
    assert versions[2] >= versions[1] >= versions[0]


def test_resolve_accepts_canonical_alias_and_instance():
    by_alias = resolve("26.12")
    by_canonical = resolve("26.120")
    assert by_alias == by_canonical
    assert by_alias.canonical == "26.120"
    assert by_alias.alias == "26.12"
    assert resolve(by_alias) is by_alias


def test_resolve_unknown_version_lists_known_ones():
    with pytest.raises(UnknownVersionError) as excinfo:
        resolve("25.3")
    message = str(excinfo.value)
    assert "25.3" in message
    for canonical in ("26.000", "26.100", "26.120"):
        assert canonical in message


def test_ordering_is_not_string_or_float_ordering():
    # "26.1" < "26.12" would hold for strings and floats alike; the
    # registry must order by release position even if the scheme changed.
    v26_100 = resolve("26.1")
    v26_120 = resolve("26.12")
    assert v26_100 < v26_120
    assert sorted([v26_120, v26_100]) == [v26_100, v26_120]


def test_str_returns_canonical():
    assert str(resolve("26.12")) == "26.120"


def test_hand_built_version_must_follow_the_scheme():
    with pytest.raises(UnknownVersionError):
        FsVersion(canonical="26.12", alias="26.12", index=0)


def test_comparison_with_other_types_is_rejected():
    with pytest.raises(TypeError):
        resolve("26.12") < "26.120"  # noqa: B015
