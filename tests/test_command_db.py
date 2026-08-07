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
CANONICAL_PATTERN = re.compile(r"^26\.\d{3}$")
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
    with pytest.raises(CommandNotInVersionError, match="not in the command database"):
        registry.for_version("26.120")["NEVER_DRAFTED"]


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
    # however it is built. An unregistered 26.122 used to receive the
    # whole 26.120 command set while the string "26.122" raised for not
    # being registered, so the two input types of one parameter
    # disagreed about whether a build exists.
    unregistered = FsVersion(canonical="26.122", alias="26.12", index=99, inherits_base=True)
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
    assert sorted(ranges) == ["SRC-003", "SRC-725", "SRC-740", "SRC-741"], (
        f"the guard read ranges for {sorted(ranges)}; an edition whose range it "
        "cannot parse is an edition it silently stops checking"
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


def test_a_probe_cited_entry_with_a_version_override_keeps_one_citation():
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
                note="measured on the February build",
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
    assert resolved.probe_ref.startswith(report)
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
    the parsed ``notes`` and per-version ``note`` prose of the command
    database and nothing else. A text scan over source code cannot do
    this job: flattening a file to find a quoted span joins the closing
    quote of one string literal to the opening quote of the next, and
    two candidate rules drowned in that before this one. Docstrings and
    markdown are NOT covered, and the residual is real, so the rule for
    a person stays what it always was.

    A quoted span of two or more words is the signal. Single-word quotes
    are left alone deliberately: a command's tokens are its grammar, are
    already public in ``values``, and are legitimately quoted in prose.
    """
    quoted = re.compile(r"[\"“]([^\"”]*?\s+[^\"”]*?)[\"”]")
    offenders = []
    walked = 0
    for path in sorted(COMMANDS_DIR.glob("*.yaml")):
        if path.name == "_meta.yaml":
            continue
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, entry in entries.items():
            prose = [("notes", entry.get("notes") or "")]
            prose += [
                (f"{canonical} note", (record or {}).get("note") or "")
                for canonical, record in (entry.get("versions") or {}).items()
                if isinstance(record, dict)
            ]
            for field, text in prose:
                if not text:
                    continue
                walked += 1
                for match in quoted.finditer(" ".join(str(text).split())):
                    offenders.append(f"{path.name}:{name} ({field}) quotes {match.group(0)}")
    assert not offenders, (
        "these command-database notes carry a quoted phrase. Manual facts are "
        "paraphrased with a page citation and never reproduced (CLAUDE.md "
        "invariant 1); if the phrase is this repository's own wording, say it "
        "without the quotes so the two cannot be confused: " + "; ".join(offenders)
    )
    assert walked >= 200, (
        f"the walk read {walked} prose fields, fewer than the 200 the database carried "
        "when this floor was set; a walk that stops finding notes guards nothing"
    )
