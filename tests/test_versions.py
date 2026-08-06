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
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.versions import (
    AmbiguousVersionAliasError,
    FsVersion,
    UnknownVersionError,
    known_versions,
    resolve,
)


def test_known_versions_ordered_by_list_position():
    versions = known_versions()
    assert [v.canonical for v in versions] == ["26.000", "26.100", "26.101", "26.120", "26.121"]
    assert [v.index for v in versions] == [0, 1, 2, 3, 4]
    assert versions[0] < versions[1] < versions[2] < versions[3] < versions[4]
    assert versions[4] >= versions[3] >= versions[2] >= versions[1] >= versions[0]


def test_resolve_accepts_canonical_and_instance():
    """The alias is no longer among them, and that is the point.

    Until 2026-08-04 ``resolve("26.1")`` returned 26.100, because only one
    registered build carried that vendor name. The February 2026 build was
    then added and the May build appended beside it, so two builds share
    "26.1" exactly as 26.120 and 26.121 share "26.12". The alias stopped
    selecting one and the refusal below is what a caller now gets. The
    companion test asserts that refusal names both candidates.
    """
    by_canonical = resolve("26.100")
    assert by_canonical.canonical == "26.100"
    assert by_canonical.alias == "26.1"
    assert resolve(by_canonical) is by_canonical
    assert resolve("26.101").canonical == "26.101"


def test_resolve_unknown_version_lists_known_ones():
    with pytest.raises(UnknownVersionError) as excinfo:
        resolve("25.3")
    message = str(excinfo.value)
    assert "25.3" in message
    for canonical in ("26.000", "26.100", "26.101", "26.120", "26.121"):
        assert canonical in message


def test_ordering_is_not_string_or_float_ordering():
    # "26.1" < "26.12" would hold for strings and floats alike; the
    # registry must order by release position even if the scheme changed.
    # By canonical, not by alias: "26.1" stopped selecting one build on
    # 2026-08-04, when the February 2026 install was registered beside
    # the May one.
    v26_100 = resolve("26.100")
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
    content. A QA pass measured it unasserted: making the note return
    one constant left the whole suite green while the refusal named two
    candidates and helped with neither.

    What the parenthetical CARRIES changed on 2026-08-05. It used to
    read "the official release" and "hotfix build N", which is a
    statement about the identifier, and for the 26.1 pair that statement
    is false: 26.100 and 26.101 are the February and May 2026 releases,
    not a release and its hotfix, which is the whole reason
    `FsVersion.inherits_base` exists. The refusal was teaching the
    descent claim the registry had just been changed to deny. It carries
    the vendor build number now, which is what the two solvers print and
    the only thing a user holding two installs can match.
    """
    with pytest.raises(AmbiguousVersionAliasError) as excinfo:
        resolve("26.12")
    message = str(excinfo.value)
    assert "26.120 (vendor build 7012026)" in message, message
    assert "26.121 (vendor build 7262026)" in message, message
    assert "hotfix build" not in message, message

    # The 26.1 pair is the case the wording was corrected for, and one of
    # its builds has no recorded number, so the message says that rather
    # than leaving the parenthetical empty.
    with pytest.raises(AmbiguousVersionAliasError) as excinfo:
        resolve("26.1")
    message = str(excinfo.value)
    assert "26.100 (no vendor build recorded here yet)" in message, message
    assert "26.101 (vendor build 5012026)" in message, message


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


def test_a_hand_built_hotfix_version_must_state_its_descent():
    """The refusal has to live on the VALUE OBJECT, not only in the loader.

    Round 1 of this review put it in the YAML reader alone. `FsVersion`
    kept `inherits_base = True` as its default, `Script` accepts an
    `FsVersion` in its documented signature, and `resolve` returns a
    hand-built one unchanged, so the original defect stayed reachable
    through the public surface:
    `Script(FsVersion(canonical="26.101", ...))` emitted
    SET_AXIAL_SEPARATION_BOUNDARIES, a February-only command, onto a May
    build. The attribute docstring said the silent default had been
    removed while line 168 offered it.
    """
    with pytest.raises(UnknownVersionError, match="states no inherits_base"):
        FsVersion(canonical="26.101", alias="26.1", index=2)
    # Stating it either way is accepted: the refusal is against silence,
    # not against inheriting.
    assert FsVersion(canonical="26.101", alias="26.1", index=2, inherits_base=True).inherits_base
    assert not FsVersion(
        canonical="26.101", alias="26.1", index=2, inherits_base=False
    ).inherits_base
    # A base release has nothing to inherit from, so it needs no flag and
    # settles to True inert. Without this control the fix could have been
    # "refuse every version that omits the flag", which would refuse the
    # three quarters of the registry that cannot use it.
    assert FsVersion(canonical="26.120", alias="26.12", index=3).inherits_base


def test_the_emitter_refuses_a_february_command_on_a_hand_built_may_version():
    """The defect end to end, through the public constructor.

    `Script` documents `str | FsVersion`, so this is the supported input
    type rather than a back door, and it is how the round-1 fix was
    measured incomplete.
    """
    from pyflightstream.script import Script, helpers

    with pytest.raises(UnknownVersionError, match="states no inherits_base"):
        Script(version=FsVersion(canonical="26.101", alias="26.1", index=2))

    stated = FsVersion(canonical="26.101", alias="26.1", index=2, inherits_base=False)
    script = Script(version=stated)
    with pytest.raises(CommandNotInVersionError, match="SET_AXIAL_SEPARATION_BOUNDARIES"):
        helpers.solver_settings(script, axial_separation_boundaries=[1])


def test_resolve_replaces_a_hand_built_version_that_names_a_registered_build():
    """The constructor refusal rejects SILENCE; this rejects a wrong statement.

    Round two put the refusal in `FsVersion.__post_init__`, so a hotfix
    index had to state `inherits_base`. It could state it wrongly:
    `FsVersion(canonical="26.101", ..., inherits_base=True)` passed the
    constructor, `resolve` handed it straight back, and the emitter wrote
    the February commands onto a May build again, one keyword away from
    the guard. The registry is the authority for every field that
    describes a BUILD rather than an identifier, so resolve returns the
    registry's own object for a registered canonical.
    """
    lying = FsVersion(canonical="26.101", alias="26.1", index=99, inherits_base=True)
    resolved = resolve(lying)
    assert resolved.inherits_base is False
    assert resolved.index == resolve("26.101").index
    assert resolved.build == "5012026"
    assert resolved is resolve("26.101")


def test_an_unregistered_version_object_passes_through_unchanged():
    """The control, and the reason reconciliation is not a refusal.

    Synthetic versions are built deliberately by the test suites of this
    package, and refusing them would make a fixture registry impossible.
    Only a REGISTERED canonical is replaced.
    """
    synthetic = FsVersion(canonical="26.900", alias="26.9", index=42)
    assert resolve(synthetic) is synthetic


def test_the_emitter_cannot_be_told_a_registered_build_inherits_when_it_does_not():
    """End to end, through the documented `Script(version=...)` input."""
    from pyflightstream.script import Script, helpers

    lying = FsVersion(canonical="26.101", alias="26.1", index=2, inherits_base=True)
    script = Script(version=lying)
    with pytest.raises(CommandNotInVersionError, match="SET_AXIAL_SEPARATION_BOUNDARIES"):
        helpers.solver_settings(script, axial_separation_boundaries=[1])
