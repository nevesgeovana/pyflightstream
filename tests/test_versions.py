"""Tier 1: version registry behavior.

Ordering must come from the list position in ``commands/_meta.yaml``,
never from string or float comparison of the identifiers.

The alias tests below are the structural half of PFS-8. The vendor ships
every hotfix of a minor release under one release name, so two entries
legitimately carry the alias "26.12". Before the fix ``resolve`` matched
canonical-or-alias and returned the FIRST hit in release order, which
handed back the pre-hotfix build 26.120 for that name with no error at
all. Nothing noticed that two entries shared a name once the data was
allowed to contain one.
"""

import pytest

from pyflightstream import versions
from pyflightstream.versions import (
    AmbiguousVersionAliasError,
    FsVersion,
    UnknownVersionError,
    known_versions,
    resolve,
)


def test_known_versions_ordered_by_list_position():
    versions = known_versions()
    assert [v.canonical for v in versions] == ["26.000", "26.100", "26.120", "26.121"]
    assert [v.index for v in versions] == [0, 1, 2, 3]
    assert versions[0] < versions[1] < versions[2] < versions[3]
    assert versions[3] >= versions[2] >= versions[1] >= versions[0]


def test_resolve_accepts_canonical_alias_and_instance():
    by_alias = resolve("26.1")
    by_canonical = resolve("26.100")
    assert by_alias == by_canonical
    assert by_alias.canonical == "26.100"
    assert by_alias.alias == "26.1"
    assert resolve(by_alias) is by_alias


def test_resolve_unknown_version_lists_known_ones():
    with pytest.raises(UnknownVersionError) as excinfo:
        resolve("25.3")
    message = str(excinfo.value)
    assert "25.3" in message
    for canonical in ("26.000", "26.100", "26.120", "26.121"):
        assert canonical in message


def test_ordering_is_not_string_or_float_ordering():
    # "26.1" < "26.12" would hold for strings and floats alike; the
    # registry must order by release position even if the scheme changed.
    v26_100 = resolve("26.1")
    v26_120 = resolve("26.120")
    assert v26_100 < v26_120
    assert sorted([v26_120, v26_100]) == [v26_100, v26_120]


def test_str_returns_canonical():
    assert str(resolve("26.120")) == "26.120"


def test_hand_built_version_must_follow_the_scheme():
    with pytest.raises(UnknownVersionError):
        FsVersion(canonical="26.12", alias="26.12", index=0)


def test_comparison_with_other_types_is_rejected():
    with pytest.raises(TypeError):
        resolve("26.120") < "26.120"  # noqa: B015


# --------------------------------------------------------------------------
# The ambiguous-alias guard (PFS-8, 2026-08-02, implementing
# SEAT-FTSALIAS as the author answered it).
# --------------------------------------------------------------------------


def _aliases_by_count() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Split registered aliases into the unique ones and the shared ones.

    Returns
    -------
    tuple of dict
        ``(unique, shared)``, each mapping an alias to the canonical
        identifiers carrying it. Derived from the live registry, so the
        assertions below keep covering every version ever appended.
    """
    by_alias: dict[str, list[str]] = {}
    for version in known_versions():
        by_alias.setdefault(version.alias, []).append(version.canonical)
    unique = {alias: names for alias, names in by_alias.items() if len(names) == 1}
    shared = {alias: names for alias, names in by_alias.items() if len(names) > 1}
    return unique, shared


def test_the_registry_actually_contains_a_shared_alias():
    # Guards the two tests below against passing vacuously. 26.120 and
    # 26.121 are both shipped as "26.12"; if a later edit made every
    # alias unique again, the sharing test would assert over an empty
    # set and could no longer fail.
    _, shared = _aliases_by_count()
    assert shared, (
        "no registered alias is shared, so test_a_shared_alias_is_refused proves "
        "nothing; if the vendor stopped reusing release names, delete both tests "
        "deliberately rather than leaving one that cannot fail"
    )


def test_a_shared_alias_is_refused_and_names_every_candidate():
    _, shared = _aliases_by_count()
    for alias, canonicals in shared.items():
        with pytest.raises(AmbiguousVersionAliasError) as excinfo:
            resolve(alias)
        message = str(excinfo.value)
        for canonical in canonicals:
            assert canonical in message, (
                f"the refusal for {alias!r} must name {canonical} so the caller "
                f"can choose; it said: {message}"
            )
        assert excinfo.value.alias == alias
        assert set(excinfo.value.candidates) == set(canonicals)


def test_the_refusal_says_which_candidate_is_which_build():
    """Naming the candidates is not enough; the caller has to choose.

    The parenthetical after each identifier is the only thing in the
    message that distinguishes the builds, so it is the operative
    content. A QA pass measured it unasserted: making _build_note return
    "the official release" unconditionally left the whole suite green
    while the refusal read "26.120 (the official release) and 26.121
    (the official release)", which names two candidates and helps with
    neither.
    """
    with pytest.raises(AmbiguousVersionAliasError) as excinfo:
        resolve("26.12")
    message = str(excinfo.value)
    assert "26.120 (the official release)" in message, message
    assert "26.121 (hotfix build 1)" in message, message


@pytest.mark.parametrize(
    ("canonical", "expected"),
    [
        ("26.000", "the official release"),
        ("26.120", "the official release"),
        ("26.121", "hotfix build 1"),
        ("26.125", "hotfix build 5"),
    ],
)
def test_the_hotfix_digit_reads_as_the_build_it_indexes(canonical, expected):
    assert versions._build_note(canonical) == expected


def test_a_unique_alias_still_resolves_to_its_own_entry():
    unique, _ = _aliases_by_count()
    assert unique, "the registry must keep at least one unambiguous alias"
    for alias, (canonical,) in unique.items():
        assert resolve(alias).canonical == canonical


def test_every_canonical_resolves_to_itself():
    for version in known_versions():
        assert resolve(version.canonical) is version


def test_a_canonical_is_not_shadowed_by_an_earlier_entrys_alias(monkeypatch):
    # Canonical identifiers are matched across the WHOLE registry before
    # any alias is considered. The real registry cannot exercise that
    # ordering today (no alias equals another entry's canonical), so the
    # test above would pass on the pre-fix first-match-wins body and is a
    # regression check rather than a guard. This one is the guard: a
    # synthetic registry in which the first entry's alias is the second
    # entry's canonical. First-match-wins returns the wrong build here.
    shadowing = (
        FsVersion(canonical="26.900", alias="26.910", index=0),
        FsVersion(canonical="26.910", alias="26.91", index=1),
    )
    monkeypatch.setattr(versions, "known_versions", lambda: shadowing)
    assert resolve("26.910").canonical == "26.910"
    assert resolve("26.91").canonical == "26.910"
    assert resolve("26.900").canonical == "26.900"
