"""Tier 1: command database integrity.

Two layers of guard: the raw-yaml structural tests keep failing loudly
even if the loader itself regresses, and the loader tests make pydantic
the enforced gate for every entry (schema, evidence rules, version
references).
"""

import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pyflightstream.commands import (
    ArgSpec,
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Phase,
    Status,
    VersionStatus,
)
from pyflightstream.versions import FsVersion

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
COMMANDS_DIR = REPO_ROOT / "src" / "pyflightstream" / "commands"
#: The canonical identifier scheme, YY.XXX: the vendor's two-digit
#: major, then three digits whose last indexes the hotfix build. It read
#: `^26\.\d{3}$` until 2026-08-09, when registering the 25 series made
#: the major a variable, which is what the scheme always meant; the
#: charter moved in the same change (CLAUDE.md invariant 4).
CANONICAL_PATTERN = re.compile(r"^\d{2}\.\d{3}$")
# A report is cited two ways in this database: as a repository-relative path
# with a suffix, and as the bare id alone (motion_definitions.yaml cites
# "reports/RPT-005", which is neither a real path nor a bare id). Resolving by
# id covers both, so a guard written for one form is not evaded by the other.
REPORT_ID_PATTERN = re.compile(r"((?:RPT|CMP|PHY|DRF)-[\d-]{3,})(?![\d-])")
REPORT_PATH_PATTERN = re.compile(r"reports/[\w./-]+\.(?:md|yaml)")
# Every entry carries a citation, and since 2026-08-06 it may be
# either kind: the manual page that documents the command, or a
# committed report measuring that the solver accepts one no edition
# documents. Exactly one, which the model enforces and
# test_every_entry_cites_one_kind_of_evidence asserts over the files.
#: A quoted phrase of two or more words. Double quotes were the whole
#: class until round three re-quoted a removed phrase with a SINGLE
#: quote and watched 57 tests stay green.
#:
#: The single-quote half needs word boundaries and the double-quote half
#: does not, which is the whole difficulty: adding a bare ``'`` to one
#: character class made every English apostrophe an opening delimiter,
#: so "the manual's own row" and everything after it up to the next
#: apostrophe became a quoted phrase, and the guard reported sixteen
#: offenders in accurate prose. An opening single quote is preceded by a
#: non-word character and a closing one is followed by a non-word
#: character; an apostrophe is neither.
#: The 100-character bound is the splice guard, not a judgement about
#: length. Within one comment block a non-greedy span still runs from
#: the CLOSING quote of one short quotation to the OPENING quote of the
#: next, and reported the 300 characters of accurate prose between them.
#: A quotation of vendor wording short enough to matter here is short.
QUOTED_PHRASE = re.compile(
    r"[\"“]([^\"”\n]{0,100}?\s+[^\"”\n]{0,100}?)[\"”]"
    r"|(?<!\w)['‘]([^'’\n]{0,100}?\s+[^'’\n]{0,100}?)['’](?!\w)"
)
REQUIRED_ENTRY_KEYS = {"layout", "phase", "args", "versions"}
CITATION_KEYS = {"manual_ref", "probe_ref"}
KNOWN_LAYOUTS = {"bare", "inline", "param_lines", "payload_lines", "keyword_block"}


def load_meta():
    with open(COMMANDS_DIR / "_meta.yaml", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_meta_versions_are_canonical_and_aliased():
    meta = load_meta()
    versions = meta["versions"]
    assert versions, "_meta.yaml must list at least one version"
    for entry in versions:
        assert CANONICAL_PATTERN.match(entry["canonical"]), entry
        assert entry["alias"], entry


def test_meta_canonical_identifiers_are_unique():
    # Canonical identifiers must stay unique: they are the key every
    # command's `versions:` block cites and the only thing that selects
    # one build.
    #
    # Display aliases are NOT asserted unique, and that is the vendor's
    # doing rather than a relaxation: 26.120 and 26.121 both ship under
    # the one vendor name, so recording that name means recording a
    # duplicate. The duplicate is refused where it would do harm, at
    # resolution time, and the guards for that live in
    # tests/test_versions.py (test_a_shared_alias_is_refused_and_names_
    # every_candidate and its non-vacuity companion). Asserting
    # uniqueness here instead would force the registry to invent a name
    # the vendor never used.
    meta = load_meta()
    canonicals = [entry["canonical"] for entry in meta["versions"]]
    assert len(canonicals) == len(set(canonicals))


def test_every_alias_is_the_vendor_name_of_its_own_canonical():
    """An alias must be a prefix of the canonical it belongs to.

    This replaces what the alias-uniqueness assertion used to catch, and
    it is needed because dropping that assertion left the alias DATA with
    no guard at all: the behavioural tests in tests/test_versions.py
    derive the shared and unique sets from whatever is registered, so
    they accommodate a duplicate rather than judging it.

    A QA pass measured the hole by onboarding a synthetic 26.130 whose
    alias was pasted from its neighbour as "26.12" instead of "26.13",
    updating only the two hardcoded version lists a real onboarding
    touches. The whole suite passed. Three things would then be wrong at
    once: resolve("26.13") refuses the name the vendor printed on that
    build, resolve("26.12") refuses while naming a build that never
    shipped under it, and the published compatibility matrix prints the
    wrong vendor name.

    The prefix rule holds for the deliberate duplicate, which is the
    point: 26.120 and 26.121 both legitimately carry "26.12", and both
    start with it. A pasted "26.12" on 26.130 does not.
    """
    meta = load_meta()
    wrong = [
        f"{entry['canonical']} carries alias {entry['alias']!r}"
        for entry in meta["versions"]
        if not entry["canonical"].startswith(str(entry["alias"]))
    ]
    assert not wrong, (
        "these aliases are not a prefix of their own canonical identifier, so "
        "they name a different build than the entry they sit on: "
        + "; ".join(wrong)
        + ". The alias records the vendor's release name for THIS build; two "
        "entries may share one (a hotfix ships under its base release's name), "
        "but an alias belonging to another release is a paste."
    )


def test_command_files_satisfy_schema():
    meta = load_meta()
    known_versions = {entry["canonical"] for entry in meta["versions"]}
    for yaml_file in sorted(COMMANDS_DIR.glob("*.yaml")):
        if yaml_file.name == "_meta.yaml":
            continue
        with open(yaml_file, encoding="utf-8") as handle:
            entries = yaml.safe_load(handle) or {}
        for name, entry in entries.items():
            missing = REQUIRED_ENTRY_KEYS.difference(entry)
            assert not missing, f"{yaml_file.name}:{name} missing keys {sorted(missing)}"
            assert entry["layout"] in KNOWN_LAYOUTS, f"{yaml_file.name}:{name}"
            cited = {key for key in CITATION_KEYS if entry.get(key)}
            assert len(cited) == 1, (
                f"{yaml_file.name}:{name} carries {sorted(cited) or 'no'} citation. Every "
                "entry rests on exactly one: manual_ref for a command an edition "
                "documents, probe_ref for one a committed report measured the solver "
                "accepting where no edition documents it. Neither is an assertion; both "
                "leaves a reader unable to say which the entry rests on."
            )
            unknown = set(entry["versions"]).difference(known_versions)
            assert not unknown, f"{yaml_file.name}:{name} references unknown versions {unknown}"


def test_every_probe_citation_names_a_report_that_exists_and_names_the_command():
    """A probe citation is only worth its file.

    ``probe_ref`` was added on 2026-08-06 so a command the solver accepts
    and no manual edition documents could be recorded at all, instead of
    being pushed to ``Script.raw()``, which is the one emission path with
    no validation. The citation is the whole evidence for such an entry,
    so it is checked the way a status report citation is: the file must
    exist and must NAME the command, which is what stops a citation being
    pasted from a sibling.

    The floor is deliberate. Today one entry uses this field, and a walk
    that silently reached zero would pass while guarding nothing.
    """
    registry = CommandRegistry.load()
    cited = [
        (name, entry.probe_ref) for name, entry in registry.commands.items() if entry.probe_ref
    ]
    assert cited, "no entry carries a probe_ref; this guard is walking nothing"
    for name, ref in cited:
        path = REPO_ROOT / ref
        assert path.is_file(), f"{name} cites missing report {ref}"
        assert name in path.read_text(encoding="utf-8"), (
            f"{name} cites {ref}, which never names it. A report that does not mention "
            "the command is not evidence that the command exists."
        )


def make_entry(**overrides):
    body = {
        "name": "SET_EXAMPLE",
        "layout": "inline",
        "phase": "setup",
        "args": [{"name": "value", "type": "float", "unit": "m/s"}],
        "manual_ref": "SRC-003 p.328",
        "versions": {"26.120": {"status": "documented"}},
    }
    body.update(overrides)
    return CommandEntry(**body)


def test_registry_loads_and_every_entry_validates():
    registry = CommandRegistry.load()
    for name, entry in registry.commands.items():
        assert entry.name == name
        assert isinstance(entry.phase, Phase)


def test_verified_and_broken_require_a_report():
    for status in ("verified", "broken"):
        with pytest.raises(ValidationError, match="probe report"):
            make_entry(versions={"26.120": {"status": status}})


def test_committed_reports_cited_by_statuses_exist():
    registry = CommandRegistry.load()
    for entry in registry.commands.values():
        for record in entry.versions.values():
            if record.report is not None:
                assert (REPO_ROOT / record.report).is_file(), (
                    f"{entry.name} cites missing report {record.report}"
                )


def test_successor_only_for_removed():
    with pytest.raises(ValidationError, match="removed"):
        VersionStatus(status="documented", successor="SET_OTHER")


def test_enum_args_carry_values_and_others_do_not():
    with pytest.raises(ValidationError, match="must list its values"):
        ArgSpec(name="variables", type="enum_list")
    with pytest.raises(ValidationError, match="must not list values"):
        ArgSpec(name="count", type="int", values=["A"])


def test_bare_layout_takes_no_args():
    with pytest.raises(ValidationError, match="layout bare"):
        make_entry(layout="bare")


def test_joins_previous_rejects_lists_and_needs_a_preceding_keyword_line():
    with pytest.raises(ValidationError, match="cannot join the previous line"):
        ArgSpec(name="indices", type="int_list", joins_previous=True)
    with pytest.raises(ValidationError, match="keyword_block layout and a preceding"):
        make_entry(args=[{"name": "copies", "type": "int", "joins_previous": True}])
    with pytest.raises(ValidationError, match="keyword_block layout and a preceding"):
        make_entry(
            layout="keyword_block",
            args=[{"name": "copies", "type": "int", "joins_previous": True}],
        )


def test_str_list_arguments_hold_strings():
    spec = ArgSpec(name="surface_toggles", type="str_list", separator="newline", required=False)
    assert spec.is_list


def test_unquoted_yaml_version_keys_are_rejected():
    with pytest.raises(ValidationError, match="quote canonical identifiers"):
        make_entry(versions={26.12: {"status": "documented"}})


def test_unregistered_version_keys_are_rejected():
    with pytest.raises(ValidationError, match="unregistered versions"):
        make_entry(versions={"27.000": {"status": "documented"}})


def test_manual_ref_must_cite_a_page():
    with pytest.raises(ValidationError, match="cite a source and page"):
        make_entry(manual_ref="the manual")


def test_view_raises_for_absent_evidence_and_removed():
    removed = make_entry(
        name="SONIC_VELOCITY",
        versions={
            "26.100": {"status": "documented"},
            "26.120": {"status": "removed", "note": "no longer supported"},
        },
    )
    registry = CommandRegistry(commands={"SONIC_VELOCITY": removed})
    with pytest.raises(CommandNotInVersionError, match="removed in FlightStream 26.120"):
        registry.for_version("26.120")["SONIC_VELOCITY"]
    with pytest.raises(CommandNotInVersionError, match="Last documented in 26.100"):
        registry.for_version("26.120")["SONIC_VELOCITY"]
    assert registry.for_version("26.100")["SONIC_VELOCITY"] is removed
    with pytest.raises(CommandNotInVersionError, match="no recorded evidence"):
        registry.for_version("26.0")["SONIC_VELOCITY"]
    # MATCHED ON THE OPERATIVE CLAUSE, not on the substring that did not
    # change. The sentence used to claim every command a registered
    # edition documents is recorded, which SRC-751 falsified by
    # documenting SET_OUTLET_TRAILING_EDGES: a 26.123 user copying that
    # name out of their own manual was told it was "usually a spelling
    # error". Reverting the correction left 421 tests green, because the
    # only assertion on this message was the half that did not move.
    with pytest.raises(CommandNotInVersionError, match="not entered yet"):
        registry.for_version("26.120")["NEVER_DRAFTED"]


def test_a_machine_promoted_removal_cites_its_run_and_not_the_manual_page():
    """The refusal must not send a reader to a page that contradicts it.

    A measured removal could only cite `probe_ref` while the harness had
    no `removed` outcome; `apply_compat` now writes the compat yaml
    through `report` and never sets `probe_ref`. Reading only the older
    field would have fallen back to `entry.citation`, the page of an
    EDITION THAT DOCUMENTS THE COMMAND, printed beside a sentence saying
    the solver refused the name. That is the exact contradiction the
    fallback order exists to prevent, one field further along.
    """
    promoted = make_entry(
        name="SONIC_VELOCITY",
        manual_ref="SRC-003 p.281",
        versions={
            "26.100": {"status": "documented"},
            "26.120": {
                "status": "removed",
                "note": "measured 2026-08-11: the solver refused the name",
                "report": "reports/compat/CMP-26120_2026-08-11_full.yaml",
            },
        },
    )
    registry = CommandRegistry(commands={"SONIC_VELOCITY": promoted})
    with pytest.raises(CommandNotInVersionError) as caught:
        registry.for_version("26.120")["SONIC_VELOCITY"]
    message = str(caught.value)
    assert "CMP-26120_2026-08-11_full.yaml" in message, message
    assert "SRC-003 p.281" not in message, message


def test_view_contains_and_iter():
    entry = make_entry()
    registry = CommandRegistry(commands={"SET_EXAMPLE": entry})
    view = registry.for_version("26.120")
    assert "SET_EXAMPLE" in view
    assert list(view) == ["SET_EXAMPLE"]
    assert "SET_EXAMPLE" not in registry.for_version("26.0")


def test_core_steady_path_is_available_in_26_120():
    view = CommandRegistry.load().for_version("26.120")
    core = [
        "OPEN",
        "SET_FREESTREAM",
        "CREATE_NEW_ACTUATOR",
        "INITIALIZE_SOLVER",
        "SOLVER_SET_AOA",
        "START_SOLVER",
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    ]
    for name in core:
        assert name in view, f"{name} missing from the 26.120 view"
    with pytest.raises(CommandNotInVersionError, match="removed in FlightStream 26.120"):
        view["SONIC_VELOCITY"]


def test_version_args_override_resolves_through_the_view():
    entry = make_entry(
        versions={
            "26.100": {
                "status": "documented",
                "args": [
                    {"name": "value", "type": "float", "unit": "m/s"},
                    {"name": "extra", "type": "int"},
                ],
            },
            "26.120": {"status": "documented"},
        }
    )
    registry = CommandRegistry(commands={"SET_EXAMPLE": entry})
    assert [spec.name for spec in registry.for_version("26.120")["SET_EXAMPLE"].args] == ["value"]
    assert [spec.name for spec in registry.for_version("26.100")["SET_EXAMPLE"].args] == [
        "value",
        "extra",
    ]


def test_version_args_override_is_rejected_for_removed():
    with pytest.raises(ValidationError, match="removed version has no grammar"):
        VersionStatus(status="removed", args=({"name": "value", "type": "float"},))


def test_version_args_override_obeys_the_layout_rules():
    with pytest.raises(ValidationError, match="own_line only applies"):
        make_entry(
            layout="param_lines",
            args=[{"name": "filename", "type": "path"}],
            versions={
                "26.120": {
                    "status": "documented",
                    "args": [{"name": "filename", "type": "path", "own_line": True}],
                }
            },
        )


def test_bulk_separation_grammar_is_version_sensitive():
    registry = CommandRegistry.load()
    in_26120 = [spec.name for spec in registry.for_version("26.120")["CREATE_BULK_SEPARATION"].args]
    in_26101 = [spec.name for spec in registry.for_version("26.101")["CREATE_BULK_SEPARATION"].args]
    assert "separation_type" in in_26120
    assert "separation_type" not in in_26101
    assert in_26101 == ["name", "num_boundaries", "diameter", "boundary_indices"]


def test_default_metadata_requires_its_citation():
    with pytest.raises(ValidationError, match="must carry its page citation"):
        make_entry(default=3)
    with pytest.raises(ValidationError, match="both travel together"):
        make_entry(default_ref="SRC-003 p.344")
    with pytest.raises(ValidationError, match="cite a source and page"):
        make_entry(default=3, default_ref="somewhere")
    entry = make_entry(default=3, default_ref="SRC-003 p.344")
    assert entry.default == 3


def test_enum_default_must_be_a_documented_token():
    enum_args = [{"name": "type", "type": "enum", "values": ["A", "B"]}]
    with pytest.raises(ValidationError, match="not one of the documented tokens"):
        make_entry(args=enum_args, default="C", default_ref="SRC-003 p.203")
    entry = make_entry(args=enum_args, default="B", default_ref="SRC-003 p.203")
    assert entry.default == "B"


def test_seeded_defaults_carry_their_recorded_evidence():
    registry = CommandRegistry.load()
    minimum_cp = registry.commands["SOLVER_MINIMUM_CP"]
    assert minimum_cp.default == -20
    assert minimum_cp.default_ref == "SRC-003 p.221"
    boundary_layer = registry.commands["SET_BOUNDARY_LAYER_TYPE"]
    assert boundary_layer.default == "TRANSITIONAL"
    assert boundary_layer.default_ref == "SRC-003 p.203"
    farfield = registry.commands["SOLVER_SET_FARFIELD_LAYERS"]
    assert farfield.default == 3
    assert farfield.default_ref == "SRC-003 p.344"


def test_hotfix_inherits_base_release_until_overridden():
    entry = make_entry()
    # inherits_base is stated rather than defaulted since 2026-08-05:
    # building a hotfix index without it is refused, because the silent
    # default made 26.101 inherit the February commands.
    hotfix = FsVersion(canonical="26.121", alias="26.12 hotfix 1", index=3, inherits_base=True)
    assert entry.status_in(hotfix) is entry.versions["26.120"]
    # THE REGISTRY ANSWERS, not the object handed in. A caller that
    # states the opposite of the registry is ignored in both directions,
    # which is the 2026-08-06 correction: reading the field off the
    # argument let a freely-constructible value object decide a fact the
    # ordering authority owns.
    lying = FsVersion(canonical="26.121", alias="26.12 hotfix 1", index=3, inherits_base=False)
    assert entry.status_in(lying) is entry.versions["26.120"]
    # And a canonical the registry has never heard of inherits NOTHING,
    # however it is built. An unregistered hotfix index used to receive
    # the whole 26.120 command set while the same string raised for not
    # being registered, so the two input types of one parameter
    # disagreed about whether a build exists.
    #
    # The example was 26.122 until 2026-08-10, when the vendor shipped
    # that build and it stopped being unregistered. An example chosen
    # for not existing has a shelf life, so this one sits far up the
    # series rather than one step past the newest.
    unregistered = FsVersion(canonical="26.199", alias="26.19", index=99, inherits_base=True)
    assert entry.status_in(unregistered) is None
    overridden = make_entry(
        versions={
            "26.120": {"status": "documented"},
        }
    )
    base = FsVersion(canonical="26.120", alias="26.12", index=2)
    assert overridden.status_in(base) is overridden.versions["26.120"]


def _records_with_a_citation(registry):
    """Every (command, build, record) whose ``report`` field is set."""
    return [
        (name, canonical, record)
        for name, entry in registry.commands.items()
        for canonical, record in entry.versions.items()
        if record.report
    ]


def _record_count_at_status(registry, status):
    """How many records the database holds at one status."""
    return sum(
        1
        for entry in registry.commands.values()
        for record in entry.versions.values()
        if record.status is status
    )


def _evidence_backed_count(registry):
    """How many records hold a status the evidence rule requires a report for.

    Derived from the schema rather than from the walk, so it is an
    INDEPENDENT statement of what the citation guards must reach. The
    model validator refuses ``verified`` and ``broken`` without a report,
    so every one of these is a citation that has to exist.
    """
    return _record_count_at_status(registry, Status.VERIFIED) + _record_count_at_status(
        registry, Status.BROKEN
    )


#: The one committed compat report whose body carries no date, exempted
#: BY NAME and with an erratum beside it rather than by relaxing the rule.
#:
#: It is the report that promoted 85 statuses on 26.123, and it was
#: written by an uncommitted intermediate state of `write_compat_report`
#: in which the date defaulting had moved into `compat_report_paths` and
#: not yet been restored beside it: the stem got a date and the body did
#: not. Both committed files reproduce byte for byte from deleting that
#: one line, which is how the cause was established rather than guessed
#: (INC-20260817-2210-pyflightstream).
#:
#: WHY IT IS EXEMPTED AND NOT REPAIRED. A committed compat report states
#: what ran on the day it was written and this lane may not edit one. The
#: repair that remains, re-emitting the same run under a new label so the
#: 85 rows cite a dated report, creates a SECOND committed report of one
#: licensed run and is the author's call; the erratum beside the file
#: states both options and the measurement behind each.
#:
#: A RATCHET, not a switch. The list may not grow: a second entry is a
#: second undated report, which after the guard below cannot be written
#: by any code path, so it would mean the guard was bypassed.
_UNDATED_REPORT_ERRATUM = {"CMP-26123_2026-08-17_full-sim.yaml"}


def test_the_undated_report_exemption_has_not_grown() -> None:
    """A ratchet is a mechanism; the comment above the set is not one.

    ``_UNDATED_REPORT_ERRATUM``'s own comment says "A RATCHET, not a
    switch. The list may not grow", and until this test nothing enforced
    it: adding a name cost one line, plus any file matching the erratum
    glob. The battery beside it mutates the set to EMPTY and proves the
    walk still sees what it exempts; it never mutated it LARGER, which is
    the direction the comment forbids.

    One entry, named, forever. A second undated report cannot be written
    by any code path after ``INC-20260817-2210-pyflightstream``, so a
    second entry would mean the writer-side guard was bypassed rather
    than that another report needs excusing.
    """
    assert _UNDATED_REPORT_ERRATUM == {"CMP-26123_2026-08-17_full-sim.yaml"}, (
        "the undated-report exemption changed. It is a ratchet of exactly one file, "
        "recorded in INC-20260817-2210-pyflightstream; a second entry means a second "
        "report was written with no date, which the writer-side guard makes impossible, "
        "so the guard was bypassed rather than the list needing to grow"
    )


def test_every_compat_report_carries_the_date_its_own_name_claims() -> None:
    """One fact, written in two places, and nothing compared them.

    The date of a compat report lives in its FILENAME and in its BODY,
    and until 2026-08-17 no test read the body's copy at all: a grep for
    a `date` key across the whole suite returned nothing. The sibling
    guard above compares the BUILD in the stem against the build in the
    body and stops there, one field short.

    What that cost is not cosmetic. `Judgment.date` reads a missing date
    as the empty string, `contradicting_evidence` orders supersession on
    it, and an empty date sorts oldest, so every row citing an undated
    report is superseded by evidence OLDER than itself. The published
    Markdown renders `(None)` on its first line.

    The walk is over EVERY committed compat report and not only the cited
    ones, because an uncited report today is a cited one after the next
    promotion, and the reach floor below stops it passing on an empty
    directory.
    """
    reports = sorted((REPO_ROOT / "reports" / "compat").glob("CMP-*.yaml"))
    stem_date = re.compile(r"^CMP-\d+_(\d{4}-\d{2}-\d{2})(?:_.+)?$")
    offenders = []
    for path in reports:
        if path.name in _UNDATED_REPORT_ERRATUM:
            erratum = sorted(path.parent.glob(f"{path.stem}_erratum_*.md"))
            assert erratum, (
                f"{path.name} is exempted from the date rule and carries no erratum "
                "beside it, so the exemption records nothing a reader can check"
            )
            continue
        match = stem_date.match(path.stem)
        if match is None:
            offenders.append(f"{path.name}: the stem carries no ISO date")
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        body = document.get("date")
        stamped = match.group(1)
        if not body:
            offenders.append(f"{path.name}: body date is {body!r}, and the stem says {stamped}")
            continue
        if str(body) != stamped:
            offenders.append(f"{path.name}: body date {body} against stem date {stamped}")
            continue
        # THE PAIR IS MANDATORY. `write_compat_report` writes a YAML and
        # a Markdown together and its docstring says so, and this arm
        # used to read a MISSING Markdown as satisfied, which is the
        # absence-as-permission shape the charter names: the rendered
        # half could be deleted and nothing anywhere noticed.
        markdown = path.with_suffix(".md")
        if not markdown.is_file():
            offenders.append(f"{markdown.name}: the rendered half of the pair is missing")
        elif stamped not in markdown.read_text(encoding="utf-8"):
            offenders.append(f"{markdown.name}: the rendered header does not carry the date")
    assert not offenders, (
        "a compat report disagrees with its own name about when it was written, and a "
        "row citing it is then superseded by older evidence: " + "; ".join(offenders)
    )
    assert len(reports) > 20, (
        f"the walk reached {len(reports)} compat reports, which is too few to be the "
        "committed population; an empty scope reads as a clean one"
    )


def test_every_citation_is_a_compat_report_for_its_own_build() -> None:
    """A citation must come from the sanctioned writer and name this build.

    Guard for a contamination that reached a commit on 2026-08-04: a
    concurrent reviewer's mutation of this database was live on disk
    when an unrelated commit staged the tree, and it went in. It had
    invented a ``26.100`` record citing a report whose name says
    ``CMP-26121``. Nothing was watching, because the schema validates
    that a report is CITED and never that the citation belongs to the
    record.

    Two rules, both about the citation's NAME and nothing else.

    It is written by ``pyfs-qa apply-compat``, which builds the stem as
    ``CMP-{version}_{date}`` under ``reports/compat/``, so a citation
    shaped any other way did not come from the promotion path. This was
    a `continue` and that was a hole: ``RPT-014_26121-...`` exists,
    carries ``26121`` in its own name, and passed both this guard and
    the existence check.

    And the build in that stem is the record's own. Exact equality, so a
    prefix cannot match.

    SCOPE, stated as its own claim because the first version of this
    guard had none and was read as wider than it is. This reads the file
    NAME. It does not open the report, so it cannot see a status its
    evidence contradicts; the sibling below does that. It does not read
    prose, so it cannot see a citation inside a ``note``; the second
    sibling does that.
    """
    registry = CommandRegistry.load()
    population = _records_with_a_citation(registry)
    offenders = []
    checked = 0
    for name, canonical, record in population:
        checked += 1
        report = record.report
        if not report.startswith("reports/compat/CMP-"):
            offenders.append(
                f"{name} at {canonical} cites {report}: not a compat report under "
                "reports/compat/, so it was not written by pyfs-qa apply-compat. Cite "
                "the compat report for this build, or leave the record unpromoted"
            )
            continue
        tag = Path(report).name.split("CMP-", 1)[1].split("_", 1)[0]
        if tag != canonical.replace(".", ""):
            offenders.append(
                f"{name} at {canonical} cites {Path(report).name}: that report was run "
                f"on {tag}, not on this record's build. Cite the report for "
                f"{canonical}, or record the evidence under the build it belongs to"
            )
    # Offenders first. A real evidence defect must say what it is; the
    # reach assertions below blame the WALK, and printing that over a
    # hand edit sends the reader to the wrong place.
    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
    # Reach, derived from the registry rather than typed. A constant
    # floor is one a shrinking walk grows into: it was 130, which is the
    # verified population exactly, so the whole broken population could
    # have dropped out unseen. The validator guarantees a verified or
    # broken record carries a report, so that count is what the citation
    # population must at least contain, and a narrowing of
    # _records_with_a_citation makes the two sides disagree.
    assert checked == len(population), (
        f"the walk inspected {checked} of {len(population)} citing records; a record "
        "skipped by the loop is a citation nobody checked, so fix the walk before "
        "trusting this pass"
    )
    assert len(population) >= _evidence_backed_count(registry), (
        f"the walk saw {len(population)} citing records while the database holds "
        f"{_evidence_backed_count(registry)} records whose status requires one; the citation "
        "predicate has been narrowed and no longer reaches every evidence-backed record"
    )
    # A THIRD question, and it is not the one above. Both sides of that
    # comparison come from one CommandRegistry.load(), which skips
    # anything not named *.yaml without a word, so a chapter file that
    # stops shipping shrinks both sides in lockstep and the inequality
    # holds all the way down to one record. This constant is the only
    # assertion in tier 1 that the database is LARGE, and it is typed on
    # purpose: 136 citations measured 2026-08-04.
    assert len(population) >= 130, (
        f"the registry loaded only {len(population)} citing records; the database is "
        "not resolving, which is a packaging or loader failure rather than an "
        "evidence one"
    )


def test_every_citation_records_the_status_the_record_claims() -> None:
    """A status must be what the report it cites actually recorded.

    The sibling above checks a citation's NAME. That is half of the
    contamination of 2026-08-04 and it is the less likely half: the
    mutant also flipped ``SET_MOTION_START_TIME`` at 26.121 from
    ``broken`` to ``verified`` while leaving the correctly named
    ``CMP-26121`` report in place, and a name check passes that
    unchanged. Measured: reverting only that half leaves the name guard
    green, and a fabricated ``verified`` on a command the report records
    ``unprobed`` failed exactly one test in the whole suite, this one.

    So this opens the report. A compat report is machine readable and
    records an ``outcome`` per command, which makes a status checkable
    against its own evidence rather than against the fact that some
    evidence was cited. That is invariant 3 as written: a status is
    promoted from a report by ``pyfs-qa apply-compat`` and never edited
    by hand.

    It walks every record carrying a CITATION rather than every record
    claiming a probe outcome, and the difference is a real hole rather
    than tidiness: a status edited DOWN, from ``verified`` to
    ``documented``, keeps its citation and is invisible to a walk keyed
    on the claimed status. Zero records are in that state today, so the
    widening costs nothing and closes the demotion.

    SCOPE. A demotion that also DROPS the report field leaves nothing to
    check and this guard cannot see it; walking the reports back into
    the database is the converse and is registered, not done. Nor does
    this compare dates: a record citing a SUPERSEDED report for its
    build passes, which is registered with the measurement.
    """
    registry = CommandRegistry.load()
    population = _records_with_a_citation(registry)
    documents: dict[str, dict] = {}
    offenders = []
    checked = 0
    seen_broken = 0

    for name, canonical, record in population:
        report = record.report
        if not report.endswith(".yaml"):
            offenders.append(
                f"{name} at {canonical} cites {report}, which is not machine readable, "
                "so its status cannot be checked against it. Cite the .yaml the probe "
                "harness wrote, not its rendering"
            )
            continue
        if report not in documents:
            path = REPO_ROOT / report
            assert path.exists(), f"{name} at {canonical} cites missing {report}"
            documents[report] = yaml.safe_load(path.read_text(encoding="utf-8"))
        document = documents[report]
        # The premise the sibling guard rests on, checked here because
        # this is where the document is already open: a compat report's
        # file name carries the build it ran on. A copied and renamed
        # report would otherwise certify a whole build's worth of
        # commands on another build's run, with every guard green.
        stated = str(document.get("fs_version", "")).replace(".", "")
        named = Path(report).name.split("CMP-", 1)[-1].split("_", 1)[0]
        if stated != named:
            offenders.append(
                f"{report} is named for build {named} and records fs_version "
                f"{document.get('fs_version')!r} inside; the file name is what every "
                "citation is checked against, so the two cannot disagree"
            )
            continue
        probed = (document.get("commands") or {}).get(name)
        if probed is None:
            offenders.append(
                f"{name} at {canonical} cites {report}, which never probed it. A "
                "status needs evidence about its own command"
            )
            continue
        checked += 1
        if record.status is Status.BROKEN:
            seen_broken += 1
        if probed.get("outcome") != record.status.value:
            offenders.append(
                f"{name} at {canonical} is recorded {record.status.value} while "
                f"{report} recorded {probed.get('outcome')}. A status is promoted from "
                "a report by pyfs-qa apply-compat and never edited by hand "
                "(CLAUDE.md invariant 3)"
            )

    # Offenders first, and this ORDER is the point rather than a style
    # choice. Three of the branches above append an offender and skip the
    # increment, so a reach assertion placed first fires on every real
    # evidence defect and prints "a walk that stops reaching them proves
    # nothing", which blames the walk for a hand edit. Round 5 measured
    # exactly that: the mutant this guard was written for was caught by
    # the wrong assertion and the message credited with catching it never
    # printed.
    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
    assert checked == len(population), (
        f"the walk compared {checked} of {len(population)} citing records against "
        "their reports; a record skipped by the loop is a status nobody checked, so "
        "fix the walk before trusting this pass"
    )
    assert len(population) >= _evidence_backed_count(registry), (
        f"the walk saw {len(population)} citing records while the database holds "
        f"{_evidence_backed_count(registry)} records whose status requires one; the citation "
        "predicate has been narrowed"
    )
    # The load, as in the sibling above and for the same reason: the two
    # derived counts fall together when the registry does.
    assert len(population) >= 130, (
        f"the registry loaded only {len(population)} citing records; the database is not resolving"
    )
    # Derived from the registry, not the typed >= 1 it replaces: a walk
    # that silently stopped reaching broken records would satisfy any
    # floor above zero, and broken is the status this guard exists for.
    expected_broken = _record_count_at_status(registry, Status.BROKEN)
    assert seen_broken == expected_broken >= 1, (
        f"the walk compared {seen_broken} broken records and the database holds "
        f"{expected_broken}; the status this guard exists for was not fully covered"
    )


def test_no_citation_is_contradicted_by_newer_evidence() -> None:
    """The fourth of the family, and the one that closes the SCOPE note above.

    The sibling compares a record to the report it CITES. That is the
    wrong question once two reports disagree, because after a revert the
    record cites the older report and agrees with it perfectly: the
    citation names the right build, the status equals that report's
    outcome, and every guard in this family stays green. The question
    this one asks is whether a LATER run has since said something else.

    MEASURED, which is what makes the row real rather than theoretical.
    ``NEW_SURFACE_SECTION_DISTRIBUTION`` at 26.120 is ``broken`` in the
    2026-07-21 report and ``verified`` in the 2026-07-23 re-probe.
    Handing the older report back to ``pyfs-qa apply-compat``, the only
    write path invariant 3 sanctions, reverted the record with evidence
    and nothing objected. A reverted status makes the emitter refuse a
    command that works.

    WHY THIS IS NOT "the citation must be the newest report", which is
    what ``PLN-20260804-1500`` asked for. Measured on the corpus of
    2026-08-11: 137 pairs are judged by more than one report and exactly
    ONE of them disagrees, while four rows cite a full run that a later
    ``--identity-only`` run of the same build also judges, because the
    baseline probe exercises ``PRINT``. The strict rule paints those
    four red while nothing is wrong with them, and a guard red on a
    correct database is a guard that gets switched off. Agreement is not
    supersession.
    """
    from pyflightstream.qa.compat import Judgment, contradicting_evidence, read_compat_reports

    judgments = read_compat_reports(REPO_ROOT / "reports" / "compat", repo_root=REPO_ROOT)
    assert judgments, (
        "the committed evidence indexed no promotable judgment at all; this guard "
        "would pass vacuously, so the report reader is what to fix"
    )

    registry = CommandRegistry.load()
    population = _records_with_a_citation(registry)
    offenders = []
    checked = 0
    for name, canonical, record in population:
        for_pair = judgments.get((name, canonical), ())
        cited = next((j for j in for_pair if j.report == record.report), None)
        if cited is None:
            # The sibling guard owns "cites a report that never probed
            # it"; duplicating its complaint here would report one
            # defect twice and blame this walk for the other's finding.
            continue
        checked += 1
        contradicting = contradicting_evidence(
            judgments,
            incoming=Judgment(
                command=name,
                fs_version=canonical,
                outcome=record.status.value,
                date=cited.date,
                report=cited.report,
            ),
        )
        if contradicting:
            offenders.append(
                f"{name} at {canonical} is recorded {record.status.value} citing "
                f"{cited.report} ({cited.date}), and "
                + ", ".join(f"{j.report} ({j.date}) records {j.outcome}" for j in contradicting)
                + ". The cited report is superseded, so this row states an outcome a "
                "later run already moved. Re-run pyfs-qa apply-compat on the newest "
                "report, or re-probe if the older reading is the right one"
            )

    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
    assert checked == len(population), (
        f"the walk reached {checked} of {len(population)} citing records against the "
        "corpus. Every citing record must be indexed, since a record the corpus does "
        "not know is a record this guard cannot compare"
    )
    # Derived per outcome, not a single floor. Measured: a corpus reader
    # that stopped indexing BROKEN judgments drops `checked` from 291 to
    # 281 and leaves a bare floor of 130 green, so all ten broken records
    # would silently stop being checked. Broken is the status a revert
    # most damages, because the emitter refuses on it.
    for status in (Status.VERIFIED, Status.BROKEN):
        expected = _record_count_at_status(registry, status)
        seen = sum(
            1
            for name, canonical, record in population
            if record.status is status and (name, canonical) in judgments
        )
        assert seen == expected, (
            f"the corpus indexed {seen} of the database's {expected} {status.value} "
            "records; a reader that stopped indexing one outcome would leave this "
            "guard green while no longer checking that outcome at all"
        )


def test_every_report_a_note_cites_names_the_command_it_is_attached_to() -> None:
    """A note may not attribute one command's evidence to another.

    Third guard of this family, and it exists because the commit that
    added the first one introduced this defect inside its own diff. A
    note reading "every documented form was rejected by the solver
    (RPT-015)" was attached to ``SET_BOUNDARY_LAYER_TYPE``, four
    commands above the intended target, because the anchor string
    occurs four times in that file and the edit took the first. RPT-015
    probed the bulk-separation family and never names
    ``SET_BOUNDARY_LAYER_TYPE`` anywhere. The status was ``documented``,
    so the schema did not look and neither sibling guard could: both
    read the ``report`` field and this citation lived in prose.

    The rule is the weakest one that catches it and needs no judgement:
    a report cited in a note must mention the command the note belongs
    to. It does not check that the report says what the note claims. It
    checks that the report is about this command at all.

    Two things learned by attacking it. A citation written as a full
    PATH is checked against THAT file, not against every file sharing
    its id: ``CMP-26120`` resolves to six reports naming 142 of 147
    commands between them, so the id union is nearly vacuous and is
    kept only as the fallback the suffix-less form needs. And the name
    match is word-bounded, because five command names contain another
    (``IMPORT`` inside ``IMPORT_AEROELASTIC_STRUCTURAL_NODES`` is live
    in five committed reports), so a substring test would accept a
    report about the sibling.

    SCOPE. Only report families are resolved: RPT, CMP, PHY, DRF. A
    manual source (SRC), a plan row (PLN) and a handoff (HND) also
    appear in these notes and are not reports. A note that makes an
    evidence claim with NO citation at all is outside this guard
    entirely.
    """
    reports_by_id: dict[str, list[Path]] = {}
    for path in REPORTS_DIR.rglob("*"):
        if path.is_file() and path.suffix in (".md", ".yaml"):
            for token in REPORT_ID_PATTERN.findall(path.name):
                reports_by_id.setdefault(token, []).append(path)
    assert reports_by_id, "no committed report resolved by id, so the index is empty"

    text: dict[Path, str] = {}

    def names_the_command(path: Path, command: str) -> bool:
        if path not in text:
            text[path] = path.read_text(encoding="utf-8", errors="replace")
        # Word bounded: SET_MOTION_FSI_EXECUTABLE contains no other
        # command name, but IMPORT does, and a report about the longer
        # one would otherwise vouch for the shorter.
        return (
            re.search(rf"(?<![A-Z0-9_]){re.escape(command)}(?![A-Z0-9_])", text[path]) is not None
        )

    registry = CommandRegistry.load()
    offenders = []
    by_path_checked = 0
    by_id_checked = 0

    for name, entry in registry.commands.items():
        prose = [entry.notes] + [record.note for record in entry.versions.values()]
        for note in prose:
            if not note:
                continue
            by_path = REPORT_PATH_PATTERN.findall(note)
            for cited in by_path:
                by_path_checked += 1
                path = REPO_ROOT / cited
                if not path.exists():
                    offenders.append(f"{name} cites the path {cited}, which does not exist")
                elif not names_the_command(path, name):
                    offenders.append(
                        f"{name} cites {cited}, which never names it. A note is the "
                        "paraphrase a reader gets instead of the report, so a citation "
                        "belonging to another command is evidence for a claim nobody made"
                    )
            for token in sorted(set(REPORT_ID_PATTERN.findall(note))):
                # A token already resolved as a path was checked against
                # the exact file; resolving it again through the id union
                # would only weaken that answer.
                if any(token in cited for cited in by_path):
                    continue
                by_id_checked += 1
                found = reports_by_id.get(token)
                if not found:
                    offenders.append(f"{name} cites {token}, which resolves to no report")
                elif not any(names_the_command(path, name) for path in found):
                    offenders.append(
                        f"{name} cites {token} ({', '.join(p.name for p in found)}), "
                        f"which never names {name}"
                    )

    assert not offenders, "\n  " + "\n  ".join(sorted(offenders))
    # Two counters, not one, and the second is the reason. A single total
    # was measured green with REPORT_PATH_PATTERN dead: every report file
    # name carries its own id, so the id fallback recovers the token out
    # of the path text and the total is conserved BY CONSTRUCTION. The
    # strong half of this guard, the path checked against that exact
    # file, would have been silently switched off. Counting the branches
    # separately is what makes the total mean anything.
    assert by_path_checked >= 1, (
        "no citation was checked as a PATH, so the branch this guard calls its "
        "strong half is not running; a bare id resolves to every report sharing "
        "it, which for CMP-26120 is six files naming 142 of 147 commands"
    )
    assert by_id_checked >= 1, (
        "no citation was resolved by bare id, so the fallback the suffix-less "
        "reports/RPT-005 form needs is not running"
    )
    assert by_path_checked + by_id_checked >= 9, (
        f"only {by_path_checked + by_id_checked} cited reports were resolved and "
        "the database carries at least 9, so the walk stopped reaching the notes "
        "it is written for"
    )


def test_a_report_stem_and_the_version_it_records_agree_or_say_why():
    """A file name that names the wrong build certifies the wrong run.

    `test_every_citation_is_a_compat_report_for_its_own_build` states the
    reason for compat reports: "a copied and renamed report would
    otherwise certify a whole build's worth of commands on another
    build's run, with every guard green." Its scope is
    ``reports/compat/CMP-*`` cited by a status, and the physics and drift
    reports under ``reports/physics/`` sat outside it.

    The collision stopped being theoretical on 2026-08-04. The
    renumbering rewrote `fs_version` inside three of those files and left
    their stems, because ids are cited elsewhere, so `PHY-26100_...yaml`
    now records `26.101` and `26100` is a REAL registered build that
    never produced those numbers. That is a defensible state and an
    undocumented one is not, so a disagreeing pair must carry a dated
    note inside the file saying the value was edited.
    """
    physics = REPORTS_DIR / "physics"
    offenders = []
    checked = 0
    for path in sorted(physics.glob("*.yaml")):
        digits = re.match(r"(?:PHY|DRF|TRI)-(\d{5})", path.name)
        if digits is None:
            continue
        text = path.read_text(encoding="utf-8")
        recorded = re.search(r"^fs_version(?:_a)?: '([\d.]+)'", text, re.MULTILINE)
        if recorded is None:
            continue
        checked += 1
        stem_version = f"{digits.group(1)[:2]}.{digits.group(1)[2:]}"
        if stem_version == recorded.group(1):
            continue
        if "RELABELLED" not in text:
            offenders.append(
                f"{path.name}: stem names {stem_version}, fs_version records "
                f"{recorded.group(1)}, and the file says nothing about it"
            )
    assert not offenders, (
        "these reports name one build in their file name and record another, with no "
        "note inside saying the value was edited: " + "; ".join(offenders)
    )
    assert checked >= 6, (
        f"the walk read {checked} physics reports, fewer than the six that carried a "
        "version when this floor was set; a glob that stops matching guards nothing"
    )


# --- citations against the registered page range ----------------------------


def _registered_edition_ranges() -> dict[str, tuple[int, int, str]]:
    """Scripting-reference page range per manual source, from _meta.yaml."""
    from pyflightstream.versions import manual_editions

    source_pattern = re.compile(r"SRC-\d{3}")
    range_pattern = re.compile(r"pp\.?\s*(\d+)\s*-\s*(\d+)")
    ranges: dict[str, tuple[int, int, str]] = {}
    for canonical, edition in manual_editions().items():
        source = source_pattern.search(edition)
        span = range_pattern.search(edition)
        if source and span:
            ranges[source.group(0)] = (int(span.group(1)), int(span.group(2)), canonical)
    return ranges


def test_every_evidence_citation_falls_inside_its_edition_page_range():
    """Two committed facts that must agree, checkable without the manual.

    The page range lives in ``commands/_meta.yaml`` and the citations
    live in the entries, so a wrong range shows up here as a citation
    outside it and no pdf is needed to see it. That is the whole reason
    this guard is possible: the manual is licensed and absent from CI,
    but the database's disagreement with its own metadata is not.

    It was wrong. On 2026-08-06 the registered SRC-003 range was
    pp.286-371 against a measured pp.281-376, and SRC-740 was short by
    the same five pages at each end. Twenty-two SRC-003 citations sat
    outside it, and the published manual-coverage page reported them as
    material beyond the reference chapter while listing ten real
    reference pages as uncited.

    Scope is deliberate. ``manual_ref`` and the per-version ``note`` are
    EVIDENCE citations and must point into the scripting reference. The
    free-text ``notes`` are excluded, because a note legitimately cites
    a toolbox narrative, a GUI chapter or a worked example to explain
    what the reference page leaves unsaid, and the coverage page already
    reports those separately.
    """
    registry = CommandRegistry.load()
    ranges = _registered_edition_ranges()

    # DERIVED from the registered editions, not listed. The hardcoded
    # four went stale the moment three more editions were registered,
    # and a list that has to be retyped is a list that eventually is not:
    # the failure it protects against is an edition whose range the
    # parser cannot read, which then goes unchecked in silence, and a
    # stale literal cannot tell that apart from an edition that is
    # simply new.
    from pyflightstream.versions import known_versions, manual_editions

    declared = {
        match.group(1)
        for text in manual_editions().values()
        if (match := re.match(r"\s*(SRC-\d{3})\b", text))
    }
    assert declared, "no edition declares a source id; this guard would read nothing"
    # And the population is anchored on the REGISTRY, because both sides
    # above read `manual_editions()`: a registered build with no entry in
    # that mapping at all appears on neither side, so the comparison
    # would agree about a build it never saw. Every build has a row
    # today, which is what this asserts rather than assumes.
    # By NAME, not by count, which is the weakening this repository had
    # just been corrected for elsewhere and which this line reproduced:
    # a count encodes the unstated invariant "exactly one distinct source
    # id per build" and names nobody when it fires.
    registered = {version.canonical for version in known_versions()}
    assert set(manual_editions()) == registered, (
        f"these builds have no manual_editions entry: "
        f"{sorted(registered - set(manual_editions()))}; and these entries name no "
        f"registered build: {sorted(set(manual_editions()) - registered)}. Either way "
        "the comparison below reads that mapping on both sides, so such a build is "
        "invisible to it"
    )
    assert sorted(ranges) == sorted(declared), (
        f"the guard read ranges for {sorted(ranges)} and the registry declares "
        f"{sorted(declared)}; an edition whose range it cannot parse is an edition it "
        "silently stops checking"
    )
    citation = re.compile(r"(SRC-\d{3})\s+pp?\.\s*(\d+)(?:\s*-\s*(\d+))?")
    offenders = []
    # Counted SEPARATELY, and the reason is that counting them together
    # gave the floor about 163 counts of slack: the note citations alone
    # cleared a floor derived from the manual_ref population, so dropping
    # manual_ref from the walk entirely left the assertion true and its
    # message ("at least one manual_ref went unparsed") false.
    manual_refs_read = 0
    notes_read = 0
    for name, entry in sorted(registry.commands.items()):
        evidence = [("manual_ref", entry.manual_ref or "")]
        evidence += [
            (f"{canonical} note", record.note or "") for canonical, record in entry.versions.items()
        ]
        for field, text in evidence:
            found = citation.findall(text)
            if field == "manual_ref" and found:
                manual_refs_read += 1
            elif found:
                notes_read += 1
            for source, first, last in found:
                if source not in ranges:
                    continue
                low, high, canonical = ranges[source]
                for page in {int(first), int(last or first)}:
                    if not low <= page <= high:
                        offenders.append(
                            f"{name} ({field}) cites {source} p.{page}, outside the "
                            f"pp.{low}-{high} registered for {canonical}"
                        )
    assert not offenders, (
        "these evidence citations fall outside the scripting-reference range their "
        "edition registers in commands/_meta.yaml. Either the citation is wrong or "
        "the range is: " + "; ".join(offenders)
    )
    expected = sum(1 for entry in registry.commands.values() if entry.manual_ref)
    assert manual_refs_read == expected, (
        f"the walk read a citation out of {manual_refs_read} manual_ref fields against "
        f"{expected} entries carrying one, so {expected - manual_refs_read} went "
        "unparsed and unchecked. Equality, not a floor: a floor is met by any other "
        "population the walk happens to count"
    )
    assert notes_read > 0, (
        "no per-version note yielded a citation; the note half of the walk is dead"
    )


def test_an_inline_list_may_not_declare_a_separator_the_renderer_ignores():
    """The declaration must be honoured or refused, never quietly dropped.

    ``_render_command`` joins an inline list with a space and never
    consults ``spec.separator``; ``_list_lines``, which does consult it,
    serves the other layouts. So an inline list declaring ``comma``
    rendered spaces and said nothing, which is how both SWEEPER sweep
    commands shipped a grammar statement that was right only by
    accident.
    """
    with pytest.raises(ValidationError, match="cannot do otherwise"):
        CommandEntry(
            name="X_CMD",
            layout="inline",
            phase="geometry",
            args=[ArgSpec(name="values", type="float_list", separator="comma")],
            manual_ref="SRC-003 p.300",
            versions={"26.120": {"status": "documented"}},
        )
    accepted = CommandEntry(
        name="X_CMD",
        layout="inline",
        phase="geometry",
        args=[ArgSpec(name="values", type="float_list", separator="space")],
        manual_ref="SRC-003 p.300",
        versions={"26.120": {"status": "documented"}},
    )
    assert accepted.args[0].separator == "space"


def test_a_non_inline_list_still_takes_the_separator_it_declares():
    """The refusal is about the inline renderer, not about commas.

    Without this the test above passes just as well under a rule that
    banned every comma-separated list, which would be wrong: the
    manual's own boundary selections are comma separated on their own
    data line, and that layout honours the declaration.
    """
    entry = CommandEntry(
        name="X_CMD",
        layout="param_lines",
        phase="geometry",
        args=[ArgSpec(name="indices", type="int_list", separator="comma")],
        manual_ref="SRC-003 p.300",
        versions={"26.120": {"status": "documented"}},
    )
    assert entry.args[0].separator == "comma"


def test_a_version_grammar_override_carries_that_version_citation():
    """An overridden grammar must not be refused against another edition's page.

    CREATE_NEW_MOTION is the case: 26.100 names the first motion type
    EUCLIDEAN and every later edition names it ROTARY, so emitting
    ROTARY on 26.100 is refused with the February token list. The
    citation used to come from the entry, which points at the CURRENT
    manual, so the message listed February's tokens beside a page that
    prints May's. A reader who follows a wrong page number is worse off
    than one given none.
    """
    registry = CommandRegistry.load()
    february = registry.for_version("26.100")["CREATE_NEW_MOTION"]
    current = registry.for_version("26.120")["CREATE_NEW_MOTION"]

    assert february.args[0].values == ("EUCLIDEAN", "6DOF", "CUSTOM")
    assert current.args[0].values == ("ROTARY", "6DOF", "CUSTOM")
    assert february.citation == "SRC-741 p.328, the 26.100 grammar"
    assert current.citation == "SRC-003 p.332", (
        "a version with no override must keep the entry citation untouched"
    )


def test_the_entry_citation_reaches_for_whichever_kind_the_entry_carries():
    """manual_ref or probe_ref, never an empty pair of brackets.

    Refusal messages interpolate the citation, and an entry resting on a
    probe report has no manual_ref at all, so a message built from that
    field alone printed "()".
    """
    documented = CommandEntry(
        name="X_CMD",
        layout="bare",
        phase="geometry",
        args=[],
        manual_ref="SRC-003 p.300",
        versions={"26.120": {"status": "documented"}},
    )
    assert documented.citation == "SRC-003 p.300"
    probed = CommandEntry(
        name="X_CMD",
        layout="bare",
        phase="geometry",
        args=[],
        probe_ref="reports/RPT-018_separation-family-across-builds_2026-08-05.md",
        versions={"26.120": {"status": "documented"}},
    )
    assert probed.citation.startswith("reports/RPT-018")


def test_no_consumer_of_a_citation_prints_an_empty_one():
    """The CONSUMERS, not the property, which is what the defect was.

    Adding `citation` and converting one call site left the empty
    brackets in every other refusal and an empty cell on a published
    page, while the test named for the defect asserted only that the
    property returned the right string. It would have stayed green with
    every consumer still reading `manual_ref`. This walks the two
    surfaces a person actually sees.
    """
    from pyflightstream.reference import markdown_reference_pages
    from pyflightstream.script import CommandArgumentError, Script

    registry = CommandRegistry.load()
    probe_only = sorted(name for name, entry in registry.commands.items() if entry.probe_ref)
    assert probe_only, "no entry rests on a probe report; this guard walks nothing"

    for name in probe_only:
        entry = registry.commands[name]
        version = sorted(entry.versions)[0]
        with pytest.raises(CommandArgumentError) as caught:
            Script(version=version).emit(name, "an argument it does not take")
        assert entry.probe_ref in str(caught.value), (
            f"the refusal for {name} cites nothing: {caught.value}"
        )

    # BOTH rendering layers, because there are two and the first repair
    # converted one. render_html is the offline fallback help() opens in
    # a browser, and it printed a probe report under a column headed
    # "Manual ref" while the markdown layer had already been fixed.
    from pyflightstream.reference import render_html

    rendered = "\n".join(markdown_reference_pages().values())
    assert "Manual: ." not in rendered
    assert "Manual: \n" not in rendered
    for name in probe_only:
        entry = registry.commands[name]
        assert f"Probe report: {entry.probe_ref}" in rendered, (
            f"the markdown reference does not name {name}'s evidence as a probe report"
        )

    page = render_html()
    assert "<th>Manual ref</th>" not in page, (
        "the HTML column asserts every citation is a manual page, and one is not"
    )
    for name in probe_only:
        entry = registry.commands[name]
        assert f"Probe report: {entry.probe_ref}" in page, (
            f"the HTML reference prints {name}'s report without saying it is one"
        )


def test_an_entry_must_cite_exactly_one_kind_of_evidence():
    """The three load-time refusals of the probe_ref field, none of which had a test.

    The walk over the YAML files asserted the property over the files
    that exist, so it passed on whatever the model already accepted;
    nothing constructed the three refused shapes. Deleting all three
    validators left the suite green while the CHANGELOG said "enforced
    by the model and by a walk over the files".

    Asserted as ``ValidationError`` because that is what a caller
    catches: ``CommandDatabaseError`` is raised inside the validator and
    pydantic wraps it, which is the same reason every other validator
    refusal in this file is asserted this way.
    """
    common = {
        "name": "X_CMD",
        "layout": "bare",
        "phase": "geometry",
        "args": [],
        "versions": {"26.120": {"status": "documented"}},
    }
    report = "reports/RPT-018_separation-family-across-builds_2026-08-05.md"

    with pytest.raises(ValidationError, match="cites both"):
        CommandEntry(**common, manual_ref="SRC-003 p.300", probe_ref=report)
    with pytest.raises(ValidationError, match="cites no evidence"):
        CommandEntry(**common)
    with pytest.raises(ValidationError, match="repository-relative path"):
        CommandEntry(**common, probe_ref="RPT-018")
    with pytest.raises(ValidationError, match="must cite a source and page"):
        CommandEntry(**common, manual_ref="the manual, somewhere")

    assert CommandEntry(**common, probe_ref=report).probe_ref == report


@pytest.mark.parametrize(
    "note",
    [
        "measured on the February build",
        "SRC-741 p.320: the February build takes one token",
    ],
)
def test_a_probe_cited_entry_with_a_version_override_keeps_one_citation(note):
    """The override citation goes into the field the entry already uses.

    ``model_copy`` runs no validator, so writing the per-version
    citation into ``manual_ref`` unconditionally would hand a
    probe-cited entry both fields at once, which is exactly the state
    the validator above refuses, and a ``manual_ref`` that fails its own
    pattern. Nothing in the database combines the two today, which is
    why this is constructed rather than loaded.

    It goes through ``VersionView`` rather than calling ``model_copy``
    and ``_override_citation`` by hand, and the difference is the whole
    test. Written the direct way it never reached the line that chooses
    the field, so reverting that line to write ``manual_ref``
    unconditionally left it green: the ``model_copy`` assertion cannot
    fail, because that copy never touches a citation field, and the
    helper is a different function from the branch that calls it.
    """
    report = "reports/RPT-018_separation-family-across-builds_2026-08-05.md"
    entry = CommandEntry(
        name="X_CMD",
        layout="inline",
        phase="geometry",
        args=[ArgSpec(name="mode", type="enum", values=("A", "B"))],
        probe_ref=report,
        versions={
            "26.100": VersionStatus(
                status=Status.DOCUMENTED,
                note=note,
                args=(ArgSpec(name="mode", type="enum", values=("A",)),),
            ),
            "26.120": VersionStatus(status=Status.DOCUMENTED),
        },
    )
    view = CommandRegistry(commands={"X_CMD": entry}).for_version("26.100")
    resolved = view["X_CMD"]

    assert resolved.args[0].values == ("A",), "the override grammar did not resolve"
    assert resolved.manual_ref == "", (
        "a probe-cited entry was handed a manual_ref by the override, which is the "
        "both-citations state the model refuses and which model_copy cannot catch"
    )
    assert resolved.probe_ref.startswith(report), (
        "the note's own manual page was taken as this entry's citation, so probe_ref "
        "now holds a page reference that fails its repository-relative-path rule. "
        "The second parameter of this test is that case: a note may mention a manual "
        "page even when the entry rests on a report"
    )
    assert resolved.probe_ref.endswith("the 26.100 grammar")
    assert resolved.citation == resolved.probe_ref


def test_no_database_note_quotes_the_manual():
    """Invariant 1, on the surface this repository writes prose into.

    Manual facts appear only as paraphrase with a page citation. The
    failure mode is not subtle and it recurred three times in two days:
    a note presents a fragment of the vendor's parameter table in
    quotation marks and attributes it, which is reproducing manual text
    however short the fragment is.

    Round one rewrote six such sites by hand and added no guard, so
    three more existed by round two, one of them introduced BY the
    rewrite. That is the argument for a guard rather than another sweep.

    SCOPE, stated because it is narrower than the invariant. This walks
    the prose of the command database: the parsed ``notes``, the
    per-version ``note``, and the files' own COMMENT lines. A text scan
    over source code cannot do this job, and two candidate rules drowned
    trying: flattening a file to find a quoted span joins the closing
    quote of one string literal to the opening quote of the next.
    Docstrings and markdown are NOT covered and the residual is real.

    The comment lines were added after round three, which defeated the
    first version twice: moving a quoted phrase from a note UP into the
    comment above the entry left the guard green with the text still
    shipping as package data, and re-quoting it with a single quote left
    it green too. Both are covered now and both are pinned below.

    A quoted span of two or more words is the signal. Single-word quotes
    are left alone deliberately: a command's tokens are its grammar, are
    already public in ``values``, and are legitimately quoted in prose.
    """
    offenders = []
    walked = 0
    for path in sorted(COMMANDS_DIR.glob("*.yaml")):
        entries = (
            {}
            if path.name == "_meta.yaml"
            else yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        )
        prose = []
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            prose.append((f"{name} notes", entry.get("notes") or ""))
            prose += [
                (f"{name} {canonical} note", (record or {}).get("note") or "")
                for canonical, record in (entry.get("versions") or {}).items()
                if isinstance(record, dict)
            ]
        # Comment BLOCKS, joined only within a run of consecutive comment
        # lines: joining across a gap would splice the closing quote of
        # one block to the opening quote of the next, which is the defect
        # that killed the two source-scanning candidates.
        block: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                block.append(line.lstrip().lstrip("#").strip())
            elif block:
                prose.append(("comment block", " ".join(block)))
                block = []
        if block:
            prose.append(("comment block", " ".join(block)))

        for field, text in prose:
            if not str(text).strip():
                continue
            walked += 1
            for match in QUOTED_PHRASE.finditer(" ".join(str(text).split())):
                offenders.append(f"{path.name}:{field} quotes {match.group(0)}")
    assert not offenders, (
        "these command-database prose fields carry a quoted phrase. Manual facts are "
        "paraphrased with a page citation and never reproduced (CLAUDE.md "
        "invariant 1); if the phrase is this repository's own wording, say it "
        "without the quotes so the two cannot be confused: " + "; ".join(offenders)
    )
    assert walked >= 200, (
        f"the walk read {walked} prose fields, fewer than the 200 the database carried "
        "when this floor was set; a walk that stops finding notes guards nothing"
    )


@pytest.mark.parametrize(
    "quoting",
    ['"the CAD body being scaled"', "'the CAD body being scaled'", "‘the CAD body being scaled’"],
)
def test_the_quotation_guard_reads_every_quote_style(quoting):
    """Changing the quote character defeated the first version.

    The phrase below is the one removed from CAD_BODY_DELETE's note; a
    QA pass put it back in single quotes and 57 tests stayed green.
    """
    assert QUOTED_PHRASE.search(quoting), f"{quoting} is not read as a quoted phrase"


def test_the_quotation_guard_leaves_a_single_word_alone():
    """The control: a token in quotes is grammar, not prose.

    Without this the parametrised test above passes under a rule that
    flagged every quotation mark in the database, which would make the
    token vocabulary unwritable in a note.
    """
    assert not QUOTED_PHRASE.search('the "RETAIN" token')


# --- the three ArgSpec declarations added on 2026-08-07 ----------------------


def test_a_sentinel_without_a_citation_is_refused_at_load():
    """An inert declaration is the defect the field was added to end.

    The sentinel is consulted only where the emitter knows which
    inventory the index belongs to, so one declared on an argument that
    cites nothing would be silently ignored. The validator's message
    used to state this rule without enforcing it, which the 2026-08-07
    architecture and API passes both found independently.
    """
    with pytest.raises(ValueError, match="cites no entity"):
        ArgSpec(name="surface", type="int", all_sentinel=0)

    # The control: the same declaration with a citation is accepted, so
    # the refusal is about the missing citation and not about the field.
    accepted = ArgSpec(name="surface", type="int", cites="boundaries", all_sentinel=0)
    assert accepted.all_sentinel == 0


def test_a_sentinel_on_a_non_index_type_is_refused_by_the_citation_rule():
    """The sentinel needs no type check of its own, and has none.

    A sentinel requires a citation and a citation requires an index
    type, so a sentinel on a str argument is refused one rule earlier.
    The sentinel validator carried a duplicate type branch until
    2026-08-07; no input could reach it, and writing this test is what
    showed that, so the branch was deleted rather than covered.
    """
    with pytest.raises(ValueError, match="cannot cite an entity"):
        ArgSpec(name="units", type="str", cites="boundaries", all_sentinel=0)


def test_a_citation_on_a_non_index_type_is_refused_at_load():
    """An entity is cited by a 1-based integer, never by a name or path."""
    with pytest.raises(ValueError, match="cannot cite an entity"):
        ArgSpec(name="name", type="str", cites="boundaries")

    for good in ("int", "int_list"):
        assert ArgSpec(name="surface", type=good, cites="boundaries").cites == "boundaries"


def test_a_fixed_length_is_refused_on_a_scalar_and_below_one():
    """The length states how many payload lines the solver reads."""
    with pytest.raises(ValueError, match="cannot fix a list length"):
        ArgSpec(name="motion_id", type="int", fixed_length=6)
    with pytest.raises(ValueError, match="must be at least 1"):
        ArgSpec(name="variables", type="str_list", separator="newline", fixed_length=0)

    accepted = ArgSpec(name="variables", type="str_list", separator="newline", fixed_length=6)
    assert accepted.fixed_length == 6


def test_every_declared_sentinel_and_length_is_reachable_from_the_database():
    """The declarations exist on the entries that need them, still.

    Deleting a declaration from the yaml is the mutation that must not
    pass unnoticed; the behavioural guards live in tests/test_script.py
    and this is the inventory beside them, so a silent removal shows up
    as a count as well as a behaviour.
    """
    registry = CommandRegistry.load()
    sentinels = {
        (name, spec.name)
        for name, entry in registry.commands.items()
        for spec in entry.args
        if spec.all_sentinel is not None
    }
    assert sentinels == {
        # Zero, stated on these two alone (SRC-003 p.309).
        ("TRANSLATE_SURFACE_IN_FRAME", "surface"),
        ("TRANSLATE_SURFACE_BY_FRAME", "surface"),
        # Minus one, each stated on its own page: SRC-003 pp.307 and
        # 310-311, SRC-741 p.305, and SRC-740 p.316 for DELETE_SURFACES,
        # whose table on p.315 states none and whose sample states it.
        ("SURFACE_SCALE", "surface"),
        ("SURFACE_INVERT", "index"),
        ("SURFACE_CUT_BY_PLANE", "surface"),
        ("SURFACE_SELECT_BY_ID", "surface"),
        ("SELECT_GEOMETRY_BY_ID", "surface"),
        ("DELETE_SURFACES", "index"),
        ("EXPORT_SURFACE_MESH", "surface"),
        # And the first one that is not a surface at all: a BASE REGION
        # boundary, stated on SRC-750 p.331. The sentinel is declared
        # here because it sits on an index that cites an inventory, and
        # base regions are boundaries; the entry arrived with the 26.122
        # edition, which is the first to document the command.
        ("SET_OUTFLOW_TRAILING_EDGES", "base_region_boundary"),
    }, (
        "every boundary index that states an all-form declares it, and no other does: "
        "absent means the page states none, so SURFACE_RENAME and SURFACE_MIRROR refuse "
        "-1. A change here is a manual claim and needs its page"
    )

    lengths = {
        (name, spec.name, spec.fixed_length)
        for name, entry in registry.commands.items()
        for spec in entry.args
        if spec.fixed_length is not None
    }
    assert lengths == {("SET_MOTION_6DOF_ACTIVE_VARIABLES", "variables", 6)}


def test_no_chapter_file_records_a_version_twice():
    """A duplicate version key is a silent overwrite, not a syntax error.

    YAML keeps the LAST of two identical keys and says nothing, so a
    command carrying two rows for one build loads with one of them and
    the other is simply gone. On 2026-08-08 `pyfs-qa apply-compat`
    produced exactly that: its matcher only sees a version row written
    as a single-line flow mapping, so a hand-authored BLOCK row for the
    same build was invisible and it inserted a second one. The block
    carried a per-version grammar, which the inserted line would have
    silenced.

    Guarded here rather than only at the tool, because the class is
    wider than its cause: any editor of these files, human or scripted,
    can write the same key twice.
    """
    import re
    from pathlib import Path

    key = re.compile(r'^    "(\d+\.\d+)":')
    offenders = []
    root = Path(__file__).parents[1] / "src" / "pyflightstream" / "commands"
    for path in sorted(root.glob("*.yaml")):
        if path.name == "_meta.yaml":
            continue
        command = None
        seen: dict[str, set[str]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line[:1].isalpha() and line.endswith(":"):
                command = line[:-1]
                continue
            match = key.match(line)
            if match is None or command is None:
                continue
            recorded = seen.setdefault(command, set())
            if match.group(1) in recorded:
                offenders.append(f"{path.name}: {command} records {match.group(1)} twice")
            recorded.add(match.group(1))
    assert not offenders, (
        "these entries record one FlightStream version twice, so the loader keeps "
        f"the second and drops the first without complaining: {offenders}"
    )


# --- what `removed` is allowed to rest on ------------------------------------
#
# Three different situations reach this one status, and the database
# said all three in the same word before this release: an edition STATES
# a withdrawal, an edition STOPS PRINTING a command, or a probe MEASURES
# the solver refusing the name. Only the third observes the solver, and
# it was the third that shipped uncited, in a row whose own entry notes
# argued at length that measured-versus-silent is exactly the
# distinction that matters. The model refuses the uncited form; these
# pin it across the whole database.


_NOTE_CITATION_IN_TEST = re.compile(r"SRC-\d{3}\s+pp?\.\s*\d+")


def _removed_rows():
    """Every (command, version, row) whose status is removed."""
    registry = CommandRegistry.load()
    return [
        (name, version, row)
        for name, entry in registry.commands.items()
        for version, row in entry.versions.items()
        if row.status is Status.REMOVED
    ]


#: How a `removed` note is read. The left column must be recognised as
#: a claim ABOUT THE SOLVER and so require a citation of a run; the
#: right column is a reading of a document and must not.
#:
#: This table exists because the two obvious tests here cannot fail. A
#: walk over the loaded database looking for a bare `removed`, or for a
#: measured one with no citation, finds zero by construction: the model
#: refuses both at load, so the walk is over a population the loader has
#: already emptied. What the model CANNOT check is the reach of its own
#: pattern, which is a closed list of wordings whose comment asks for it
#: to be widened as new ones appear. Two phrasings already in the tree
#: sit in the right column and are admissible only because they also
#: carry a page; had they not, nothing would have objected.
MEASUREMENT_WORDINGS = (
    "Measured 2026-08-08: the solver answers with an unrecognised command",
    "Probed on the licensed build and the name is not recognised",
    "The solver refuses the name on this build",
    "The solver answers the line with an error",
    "Observed on build #7262026: the command is gone",
)

READING_WORDINGS = (
    "Withdrawn at SRC-003 p.328; no successor is documented",
    "Absent from the 26.12 manual: the family no longer lists it (SRC-003 p.366)",
    "No longer supported; the manual states the removal (SRC-725 p.327)",
    # The two live in the tree today, on SET_SONIC_VELOCITY. Both DESCRIBE
    # solver behaviour and neither claims to have watched it: they read a
    # page that says what the solver does. The pattern does not match
    # "warns" or "throws" and should not, since forcing a probe report
    # for a documented statement makes the honest form unwritable.
    "Already deprecated in 26.1: the solver warns and ignores the value (SRC-725 p.327)",
    "No longer supported; the solver throws a deprecation warning (SRC-003 p.328)",
)


@pytest.mark.parametrize("note", MEASUREMENT_WORDINGS)
def test_a_note_claiming_the_solver_was_run_is_read_as_a_measurement(note):
    """Widening the pattern is what makes this table grow, and the point.

    SET_JET_WAKE_FILAMENTS_GRID_INDUCTION shipped `removed` on 26.121
    with a note beginning `Measured 2026-08-08` and no citation at all,
    while the same entry's own notes explained at length that a claim
    about the solver may not rest on a document's silence. The status
    rule had never covered `removed`, so nothing objected. The rule now
    exists; its blind spot is any wording it does not recognise.
    """
    with pytest.raises(ValidationError, match="claims a measurement"):
        VersionStatus(status=Status.REMOVED, note=note)
    VersionStatus(status=Status.REMOVED, note=note, probe_ref="reports/RPT-021.md")


@pytest.mark.parametrize("note", READING_WORDINGS)
def test_a_note_reading_a_page_is_not_forced_to_cite_a_run(note):
    """The other side, which a pattern that guessed would break.

    An edition stating a withdrawal is evidence, and demanding a probe
    report for it would make the honest form unwritable. That is why the
    pattern is a closed list rather than a general reading of the
    sentence: a false positive here refuses a true row.
    """
    VersionStatus(status=Status.REMOVED, note=note)


def test_a_removed_row_that_reads_a_page_cites_the_page():
    """The other two cases are readings, and a reading cites its edition."""
    uncited = [
        f"{name} on {version}"
        for name, version, row in _removed_rows()
        if row.note
        and not (row.report or row.probe_ref)
        and not _NOTE_CITATION_IN_TEST.search(row.note)
    ]
    assert not uncited, (
        "these removed rows rest on a manual edition and name no page, so the claim "
        f"cannot be re-checked against the edition that makes it: {uncited}"
    )


def test_every_narrative_citation_names_a_report_that_exists():
    """A narrative citation is not opened by the compat guard, so it is opened here.

    ``report`` is checked against its own contents by
    ``test_every_citation_records_the_status_the_record_claims``, which
    skips anything that is not machine readable. ``probe_ref`` is
    precisely the not-machine-readable kind, so the one thing that CAN
    be checked mechanically about it, that the file is really committed,
    has to be checked somewhere, and this is the somewhere.
    """
    cited = [(name, version, row) for name, version, row in _removed_rows() if row.probe_ref]
    # The floor, for the reason the entry-level sibling states: deleting
    # the one row that uses the field leaves this walking an empty list
    # and reporting green, and a guard is not allowed to pass by having
    # nothing to check.
    assert cited, (
        "no removed row carries a probe_ref; this guard walks nothing. THE HARNESS "
        "GAINED THE OUTCOME ON 2026-08-11 AND THE FIELD STAYED: it holds the removals "
        "recorded before that, a finite set. Delete this guard when that set empties "
        "and not before, and re-read PLN-20260809-0300 first"
    )
    missing = [
        f"{name} on {version} cites {row.probe_ref}"
        for name, version, row in cited
        if not (REPO_ROOT / row.probe_ref).exists()
    ]
    assert not missing, f"these rows cite a narrative report that is not committed: {missing}"
    # And that the report is about THIS command, which is what stops a
    # citation being pasted across from a sibling row. The measured case
    # is the one where that matters most: the claim is about the solver,
    # so a report that never mentions the command supports nothing.
    silent = [
        f"{name} on {version} cites {row.probe_ref}"
        for name, version, row in cited
        if name not in (REPO_ROOT / row.probe_ref).read_text(encoding="utf-8")
    ]
    assert not silent, (
        f"these rows cite a report that never names the command they sit on: {silent}"
    )


def test_a_narrative_citation_is_admissible_for_removed_alone():
    """The line that keeps `probe_ref` from becoming a way around the harness.

    Every status the harness can write must keep citing the compat yaml,
    because the guard that compares a status against its evidence can
    only open a yaml. Allowing prose to support ``verified`` would leave
    that guard walking a shrinking population and reporting green.
    """
    for status in (Status.VERIFIED, Status.BROKEN, Status.DOCUMENTED):
        with pytest.raises(ValidationError, match="admissible for removed alone"):
            VersionStatus(
                status=status,
                report="reports/compat/CMP-26121_2026-08-08_full.yaml",
                probe_ref="reports/RPT-021_chapter-questions-measured_2026-08-08.md",
            )


def test_the_model_refuses_a_measured_removal_that_cites_no_run():
    """The guard itself, at the layer no chapter file can bypass."""
    with pytest.raises(ValidationError, match="claims a measurement"):
        VersionStatus(status=Status.REMOVED, note="Measured 2026-08-08: the solver refuses it.")
    with pytest.raises(ValidationError, match="requires a note"):
        VersionStatus(status=Status.REMOVED)
    with pytest.raises(ValidationError, match="not a repository-relative path"):
        VersionStatus(status=Status.REMOVED, note="Withdrawn at SRC-003 p.1.", probe_ref="RPT-021")
    # And the three honest forms load.
    VersionStatus(
        status=Status.REMOVED,
        note="Measured 2026-08-08: the solver refuses it.",
        probe_ref="reports/RPT-021_chapter-questions-measured_2026-08-08.md",
    )
    VersionStatus(status=Status.REMOVED, note="Withdrawn at SRC-003 p.328; no successor.")
    VersionStatus(
        status=Status.REMOVED,
        note="Stops being printed at SRC-003 pp.366-367; no successor in the family.",
    )


def test_no_consumer_of_a_version_row_citation_prints_the_claim_without_it():
    """The same walk, one level down, where the class recurred.

    Its sibling above was written when a citation added to the ENTRY was
    consumed at one call site and dropped by every other, so the pages a
    person reads printed the claim and not the evidence. That guard was
    keyed on `entry.probe_ref` and did not generalise, and within one
    release the identical thing happened to `VersionStatus.probe_ref`:
    the reference page rendered the measurement sentence beside the
    manual page of an edition that DOCUMENTS the command, and the
    removal refusal did the same, with the run that measured it named
    nowhere. Adding the field is not the work; being read is.
    """
    from pyflightstream.reference import markdown_reference_pages, render_html
    from pyflightstream.script import Script

    registry = CommandRegistry.load()
    cited = sorted(
        (name, canonical)
        for name, entry in registry.commands.items()
        for canonical, record in entry.versions.items()
        if record.probe_ref
    )
    assert cited, (
        "no version row carries a probe_ref; this guard walks nothing. The harness "
        "gained a removed outcome on 2026-08-11 and the field stayed for the rows "
        "written before it; delete this guard when those rows are re-probed away, and "
        "do not leave it green"
    )

    rendered = "\n".join(markdown_reference_pages().values())
    page = render_html()
    for name, canonical in cited:
        record = registry.commands[name].versions[canonical]
        with pytest.raises(CommandNotInVersionError) as caught:
            Script(version=canonical).emit(name)
        assert record.probe_ref in str(caught.value), (
            f"the refusal for {name} on {canonical} asserts the solver was measured and "
            f"cites {record.probe_ref!r} nowhere: {caught.value}"
        )
        # And it must not cite the entry-level page INSTEAD, which is the
        # page of an edition documenting the command: a reader who follows
        # it finds the command described as present.
        entry_page = registry.commands[name].manual_ref
        if entry_page:
            assert entry_page not in str(caught.value), (
                f"the refusal for {name} on {canonical} sends the reader to {entry_page}, "
                "which documents the command as available"
            )
        for surface, text in (("markdown", rendered), ("html", page)):
            assert record.probe_ref in text, (
                f"the {surface} reference prints {name}'s measured removal without the "
                "report that measured it"
            )


@pytest.mark.parametrize(
    "note",
    [
        # A count of a DOCUMENT, which is what the four 26.122 rows make.
        "SRC-750 p.283, the edition does not print it; counted over the ten it adds.",
        # A disclaimer, in the wordings this database uses for one.
        "SRC-750 p.283, the edition does not print it; no probe has asked this build.",
        "SRC-750 p.283, the edition does not print it; the successor is untested here.",
    ],
)
def test_a_removed_note_that_claims_nothing_about_the_solver_loads(note):
    """The guard is a closed list and stays one, which costs a wording.

    A negation pass was tried on 2026-08-10 so that a row could say "is
    not measured" and load. It let genuine claims through: its window
    spanned the sentence, so an opening "the edition does not print it"
    reached forward and the subtraction removed the negator, the claim
    word and everything between, and "and the solver was observed
    refusing it" loaded with no claim left in it. Withdrawn the same
    day. A count of a document says counted; only a claim about the
    solver says measured.
    """
    VersionStatus(status=Status.REMOVED, note=note)


def test_a_removed_note_still_cannot_claim_a_measurement_without_a_run():
    """The other side, and the two the withdrawn pass would have let in."""
    for note in (
        "Measured 2026-08-10: the solver refuses the name (SRC-003 p.1).",
        "SRC-003 p.1, and a probe observed the abort.",
        # Both of these loaded while the negation pass was in place.
        "SRC-750 p.1, the edition does not print it, and the solver was observed refusing it.",
        "SRC-750 p.1, no page prints it; the solver was observed rejecting the name.",
    ):
        with pytest.raises(ValueError, match="claims a measurement and cites no run"):
            VersionStatus(status=Status.REMOVED, note=note)
