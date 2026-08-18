"""Tier 1: compat report writing, reading, and status promotion."""

import re

import pytest
import yaml

from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.qa import (
    COMPAT_SCHEMA,
    ProbeOutcome,
    ProbeResult,
    ProbeRun,
    apply_compat,
    compat_report_paths,
    read_compat_report,
    write_compat_report,
)
from pyflightstream.qa.compat import _NOTE_CUT_MARKER, _NOTE_LIMIT, _one_line_note

# A chapter fixture with documented statuses, independent of the live
# database files (which carry real promotions as evidence lands).
CHAPTER_FIXTURE = """\
# Chapter: fixture for apply-compat tests.

STOP:
  layout: bare
  phase: control
  args: []
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}

PRINT:
  layout: inline
  phase: control
  args:
    - name: message
      type: str
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}

RUN_SCRIPT:
  layout: param_lines
  phase: control
  args:
    - name: script_path
      type: path
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}
"""


#: The fixture tree carries its own ordered version list, because the
#: promotion reads the release order from the directory it EDITS rather
#: than from the installed package: pointing apply_compat at a copy and
#: ordering the edit by another tree's registry is two authorities for
#: one edit, and the installed one is process-cached besides.
META_FIXTURE = """\
versions:
  - canonical: "26.120"
    alias: "26.12"
  - canonical: "26.121"
    alias: "26.12"
"""


def write_chapter_fixture(commands_dir):
    commands_dir.mkdir()
    (commands_dir / "script_controls.yaml").write_text(CHAPTER_FIXTURE, encoding="utf-8")
    (commands_dir / "_meta.yaml").write_text(META_FIXTURE, encoding="utf-8")


def make_run():
    return ProbeRun(
        version="26.120",
        solver_identity=("FlightStream version 26.1 build #0000000",),
        fs_exe_name="Fake.exe",
        package_version="0.0.1.dev0",
        results=(
            ProbeResult(
                "PRINT",
                ProbeOutcome.VERIFIED,
                "effect observed",
                sentinel_before=True,
                sentinel_after=True,
                effect=True,
                wall_time_s=0.051,
                return_code=0,
                script_sha256="abc123",
            ),
            ProbeResult("STOP", ProbeOutcome.BROKEN, 'did not halt | "quoted"'),
            ProbeResult("OPEN", ProbeOutcome.UNPROBED, "no probe specification yet"),
        ),
    )


def test_report_pair_round_trips(tmp_path):
    yaml_path, md_path = write_compat_report(make_run(), tmp_path, date="2026-07-21")
    assert yaml_path.name == "CMP-26120_2026-07-21.yaml"
    report = read_compat_report(yaml_path)
    assert report["fs_version"] == "26.120"
    # One key per outcome, derived from the enum rather than listed, so
    # a new outcome appears in every report instead of being dropped by
    # a hardcoded triple. `removed` joined at PLN-20260809-0300.
    assert report["summary"] == {"verified": 1, "broken": 1, "removed": 0, "unprobed": 1}
    assert report["commands"]["PRINT"]["signals"]["effect"] is True
    assert report["commands"]["PRINT"]["wall_time_s"] == 0.05
    markdown = md_path.read_text(encoding="utf-8")
    assert "| PRINT | verified | effect observed |" in markdown
    assert "did not halt \\|" in markdown


def test_the_writer_stamps_one_date_in_the_stem_the_body_and_the_header(tmp_path):
    """One fact written in three places, and NO test called the default path.

    Every existing test of this writer passes `date=` explicitly, so the
    branch a real run takes, the one that defaults to today, was never
    executed by tier 1. On 2026-08-17 that branch was briefly broken
    while the collision check was being moved ahead of the solver: the
    defaulting moved into `compat_report_paths` and was not yet restored
    beside it, so a licensed probe run wrote a report whose STEM carried
    the date and whose BODY carried null, and whose Markdown header
    rendered `(None)`. 85 database rows cite that file
    (INC-20260817-2210-pyflightstream).

    So this calls the writer with no date at all, which is what a run
    does, and requires the three copies to agree.
    """
    import datetime

    yaml_path, md_path = write_compat_report(make_run(), tmp_path, label="defaulted")
    today = datetime.date.today().isoformat()

    stem = re.match(r"^CMP-\d+_(\d{4}-\d{2}-\d{2})_defaulted$", yaml_path.stem)
    assert stem, yaml_path.stem
    assert stem.group(1) == today

    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["date"] == today, (
        "the body carries a different date from the file name, which is the shape that "
        "reached a committed evidence file and cannot be repaired by editing it"
    )
    assert today in md_path.read_text(encoding="utf-8").splitlines()[0]


def test_the_path_helper_defaults_its_date_the_same_way(tmp_path):
    """The mirror image of the defect above, and it is not decoration.

    The one-arm version of the guard above is holed: the mutation that
    keeps the default in the WRITER and drops it from the helper leaves
    the written report perfectly dated and corrupts the PRE-FLIGHT
    instead. `_cmd_probe` calls this helper with no date to ask whether a
    report already exists, so a stem of `CMP-26123_None_full-sim` matches
    nothing, the collision check never fires, and a licensed run is spent
    and then discarded at write time. That is the incident the pre-flight
    was added to prevent, arriving through the guard meant to prove it.
    """
    import datetime

    yaml_path, md_path = compat_report_paths("26.120", tmp_path, label="probe")
    today = datetime.date.today().isoformat()
    assert yaml_path.name == f"CMP-26120_{today}_probe.yaml"
    assert md_path.name == f"CMP-26120_{today}_probe.md"


def test_the_writer_lands_exactly_where_the_pre_flight_looked(tmp_path):
    """The compat half of the pairing the other two writers now assert.

    This series had its helper from 2026-08-17 and the CLI already used
    it, so this arm was the sound one; it is written down anyway, because
    the guard that exists in two of three places is the shape that let
    the original defect survive a repair.
    """
    run = make_run()
    yaml_path, md_path = write_compat_report(run, tmp_path, date="2026-07-21", label="pinned")
    assert (yaml_path, md_path) == compat_report_paths(
        run.version, tmp_path, date="2026-07-21", label="pinned"
    )


def test_reports_are_never_overwritten(tmp_path):
    write_compat_report(make_run(), tmp_path, date="2026-07-21")
    with pytest.raises(FileExistsError, match="never\n?.*overwritten"):
        write_compat_report(make_run(), tmp_path, date="2026-07-21")


def test_read_refuses_a_non_report_file(tmp_path):
    stray = tmp_path / "stray.yaml"
    stray.write_text("just: data\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a compat report"):
        read_compat_report(stray)


def write_report(tmp_path, commands, version="26.120"):
    report_dir = tmp_path / "reports" / "compat"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"CMP-{version.replace('.', '')}_2026-07-21.yaml"
    document = {"schema": COMPAT_SCHEMA, "fs_version": version, "commands": commands}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_apply_compat_promotes_citing_the_report(tmp_path):
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(
        tmp_path,
        {
            "PRINT": {"outcome": "verified", "detail": "effect observed"},
            "STOP": {"outcome": "broken", "detail": 'no halt, "quoted" detail'},
            "RUN_SCRIPT": {"outcome": "unprobed", "detail": "not probed"},
        },
    )
    promotions = apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert sorted(promotions) == [
        ("PRINT", "verified", "script_controls.yaml"),
        ("STOP", "broken", "script_controls.yaml"),
    ]
    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    citation = "reports/compat/CMP-26120_2026-07-21.yaml"
    assert f'"26.120": {{status: verified, report: "{citation}"}}' in text
    assert "note: \"no halt, 'quoted' detail\"" in text
    # The chapter comments and the untouched entry survive the edit.
    assert text.startswith("# Chapter: fixture for apply-compat tests.")
    data = yaml.safe_load(text)
    assert data["RUN_SCRIPT"]["versions"]["26.120"] == {"status": "documented"}
    for name in ("PRINT", "STOP", "RUN_SCRIPT"):
        CommandEntry(name=name, chapter="script_controls", **data[name])
    assert data["PRINT"]["versions"]["26.120"]["report"] == citation


def test_apply_compat_refuses_unknown_commands(tmp_path):
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(tmp_path, {"NOT_A_COMMAND": {"outcome": "verified", "detail": "x"}})
    with pytest.raises(ValueError, match="NOT_A_COMMAND"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def _fake_chapter(commands_dir, versions: str) -> None:
    commands_dir.mkdir(exist_ok=True)
    (commands_dir / "_meta.yaml").write_text(META_FIXTURE, encoding="utf-8")
    (commands_dir / "fake.yaml").write_text(
        "FAKE_CMD:\n"
        "  layout: bare\n"
        "  phase: control\n"
        "  args: []\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n" + versions,
        encoding="utf-8",
    )


def test_apply_compat_refuses_to_promote_over_a_multiline_block(tmp_path):
    """The promotion must not write the same version key twice.

    A version already recorded as a BLOCK is invisible to the one-line
    matcher, so the promotion used to insert a SECOND key beside it.
    YAML keeps the last and drops the first without complaining, and on
    2026-08-08 that nearly erased a hand-authored per-version GRAMMAR:
    SOLVER_PROXIMAL_BOUNDARIES records a different argument list on
    26.121, and the inserted line would have silenced it.

    Refused rather than rewritten, because the block carries a note and
    possibly an argument override this function cannot preserve, and
    dropping either is the same silent loss somewhere else.
    """
    commands_dir = tmp_path / "commands"
    _fake_chapter(
        commands_dir,
        '    "26.120":\n'
        "      status: documented\n"
        "      note: >-\n"
        "        a hand-authored block carrying something worth keeping\n",
    )
    report_path = write_report(tmp_path, {"FAKE_CMD": {"outcome": "verified", "detail": "x"}})
    with pytest.raises(ValueError, match="already records '26.120' as a multi-line block"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_apply_compat_refuses_when_no_line_shows_it_the_shape(tmp_path):
    """The older refusal, still reachable and still its own case.

    Here the block belongs to a DIFFERENT version, so there is no
    collision to refuse and also no single-line entry whose shape the
    new one could copy.
    """
    commands_dir = tmp_path / "commands"
    _fake_chapter(commands_dir, '    "26.101":\n      status: documented\n')
    report_path = write_report(tmp_path, {"FAKE_CMD": {"outcome": "verified", "detail": "x"}})
    with pytest.raises(ValueError, match="records no version as a single-line entry"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_apply_compat_onboards_a_version_the_command_does_not_record_yet(tmp_path):
    """The first probe run of a new version judges commands with no line for it.

    A version starts life recorded only in _meta.yaml, so every command
    still carries lines for the older versions alone. Refusing there
    would leave a whole licensed run unpromotable, and the only route
    left would be a hand edit, which invariant 3 forbids. The new line
    is inserted at its release position among the ones already there.
    """
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(
        tmp_path,
        {
            "PRINT": {"outcome": "verified", "detail": "effect observed"},
            "STOP": {"outcome": "broken", "detail": "did not halt"},
        },
        version="26.121",
    )

    promotions = apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert sorted(promotions) == [
        ("PRINT", "verified", "script_controls.yaml"),
        ("STOP", "broken", "script_controls.yaml"),
    ]

    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()

    # The older evidence survives untouched, and the new line sits after
    # it, at the same indentation, in release order.
    for command, status in (("PRINT", "verified"), ("STOP", "broken")):
        block = lines[lines.index(f"{command}:") :]
        recorded = [line for line in block[:12] if '": {status' in line]
        assert recorded[0].strip().startswith('"26.120": {status: documented}'), recorded
        assert recorded[1].strip().startswith(f'"26.121": {{status: {status},'), recorded
        assert recorded[1].startswith("    "), recorded[1]
        assert "CMP-" in recorded[1]

    # RUN_SCRIPT was not judged, so it gains nothing.
    run_block = lines[lines.index("RUN_SCRIPT:") :]
    assert not [line for line in run_block if "26.121" in line]


def test_apply_compat_still_refuses_a_block_with_no_line_to_pattern_on(tmp_path):
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "_meta.yaml").write_text(META_FIXTURE, encoding="utf-8")
    (commands_dir / "fake.yaml").write_text(
        "FAKE_CMD:\n"
        "  layout: bare\n"
        "  phase: control\n"
        "  args: []\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n"
        '    "26.120":\n'
        "      status: documented\n",
        encoding="utf-8",
    )
    report_path = write_report(
        tmp_path,
        {"FAKE_CMD": {"outcome": "verified", "detail": "x"}},
        version="26.121",
    )
    with pytest.raises(ValueError) as caught:
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    message = str(caught.value)
    # Pin the REMEDY, not only the diagnosis. The first wording of this
    # refusal said "promote this entry manually reviewable or normalize the
    # block first", whose only actionable reading told the user to hand-edit
    # a status, which invariant 3 forbids outright. Only the diagnosis half
    # was pinned, so the broken half was free to drift.
    assert "no line to copy the shape" in message
    assert "one line per version" in message
    assert "never hand-edited" in message
    assert "manually" not in message


def test_apply_compat_refuses_a_report_naming_an_unregistered_version(tmp_path):
    """An unregistered version must be named, not raise a bare KeyError.

    The release position of the line being inserted is looked up in the
    tree's own ordered version list. Before the architect pass that
    lookup was an unguarded subscript, so a report naming a version the
    registry does not carry escaped `apply_compat` as KeyError('26.130'),
    from a public function whose Raises section promises ValueError and
    whose siblings all name their cause.
    """
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_report(
        tmp_path,
        {"PRINT": {"outcome": "verified", "detail": "effect observed"}},
        version="26.130",
    )
    with pytest.raises(ValueError, match="does not list"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    # Nothing was written before the refusal.
    assert "26.130" not in (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")


def test_apply_compat_orders_by_the_tree_it_edits_not_the_installed_registry(tmp_path):
    """The ordering authority is the _meta.yaml beside the chapters.

    Pointing apply_compat at a copy and ordering the edit by the
    INSTALLED registry is two authorities for one edit. Here the copy
    declares a release order the installed package does not have, and
    the inserted line must follow the copy.
    """
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    # A tree in which 26.121 is OLDER than 26.120, which the installed
    # registry says the opposite of. The insert must follow this file.
    (commands_dir / "_meta.yaml").write_text(
        'versions:\n  - canonical: "26.121"\n    alias: "a"\n'
        '  - canonical: "26.120"\n    alias: "b"\n',
        encoding="utf-8",
    )
    report_path = write_report(
        tmp_path,
        {"PRINT": {"outcome": "verified", "detail": "effect observed"}},
        version="26.121",
    )
    apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)

    lines = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8").splitlines()
    block = lines[lines.index("PRINT:") :]
    recorded = [line.strip() for line in block[:12] if '": {status' in line]
    assert recorded[0].startswith('"26.121"'), recorded
    assert recorded[1].startswith('"26.120"'), recorded


# --- a capped note that hides its own cap ----------------------------------


def test_a_note_too_long_for_one_line_says_that_it_was_cut():
    """The cap is fine; a cap that hides itself is not.

    A `note` lives on one flow-mapping line, so it is capped at 140
    characters. The cap used to cut mid-word and say nothing: the
    AIR_ALTITUDE entry read "reports the 5000 m standa", dropping the
    sentence that carried the measured diagnosis (1.056 kg/m^3 observed
    against 0.736 expected, which is the 5000 ft standard state). That
    note is not decoration any more, because FR-48's refusal shows it to
    whoever tried to emit the command, and a refusal that looks like a
    corrupt database is one that gets worked around.
    """
    detail = (
        "the command ran (script processing continued past it) but its effect was "
        "not observed; expected: the settings dump reports the 5000 m standard "
        "atmosphere density"
    )
    note = _one_line_note(detail)
    assert len(note) <= 140
    assert note.endswith(" [...]"), note
    # Cut at a word boundary, so the last word of the extract is a word.
    assert not note.removesuffix(" [...]").endswith(("stand", "standa", "standar")), note
    assert detail.startswith(note.removesuffix(" [...]"))


def test_a_note_that_fits_is_left_exactly_as_it_is():
    """The control.

    Without it, a mutation that marks every note as cut would leave the
    test above green while every short note in the database grew a
    trailing marker claiming text that does not exist.
    """
    detail = "script processing aborted at the command: the END sentinel never appeared"
    assert _one_line_note(detail) == detail
    assert "[...]" not in _one_line_note(detail)


def test_a_note_is_safe_to_embed_in_a_double_quoted_scalar():
    """Quotes and newlines would end the scalar or break the line."""
    note = _one_line_note('the dump said "5000" and\nthen  stopped')
    assert '"' not in note
    assert note == "the dump said '5000' and then stopped"


def test_the_live_database_carries_no_note_cut_mid_word():
    """The data, not only the renderer.

    Fixing the function leaves every note promoted before it untouched,
    so this walks what actually ships. AIR_ALTITUDE's was repaired by
    re-running apply-compat over the committed report, which is the only
    sanctioned write path for a status or its note (CLAUDE.md invariant
    3), never by editing the YAML.

    Keyed on the length being EXACTLY the cap, which is the old
    truncator's fingerprint: it sliced at ``[:140]``, so every note it
    cut is 140 characters and every note it left alone is shorter. Notes
    longer than the cap exist and are fine, because a `removed` note is
    written by hand rather than promoted from a report and never passes
    through this renderer. The residual, stated rather than hidden: a
    hand-written note of exactly 140 characters would trip this
    falsely, and clearing it costs one word.
    """
    registry = CommandRegistry.load()
    cut_short = [
        (name, canonical, record.note)
        for name, entry in registry.commands.items()
        for canonical, record in entry.versions.items()
        if record.note is not None
        and len(record.note) == _NOTE_LIMIT
        and not record.note.endswith(_NOTE_CUT_MARKER)
    ]
    assert not cut_short, (
        f"these notes sit exactly on the one-line cap with no {_NOTE_CUT_MARKER} "
        f"marker, so they were cut and say nothing about it: {cut_short}"
    )
    # The control: without it, a database whose notes were all short (or
    # all absent) would report green over nothing at all.
    promoted = [
        record.note
        for entry in registry.commands.values()
        for record in entry.versions.values()
        if record.note is not None and record.report is not None
    ]
    assert len(promoted) >= 5, (
        f"too few promoted notes for this guard to mean anything: {len(promoted)}"
    )


#: A chapter whose version rows carry the keys a promotion does not own.
#: Both notes are the shape the v0.5.0 backfill wrote 122 of.
KEYS_FIXTURE = """\
# Chapter: fixture for the key-preservation tests.

PRINT:
  layout: inline
  phase: control
  args:
    - name: message
      type: str
  manual_ref: "SRC-003 p.281"
  versions:
    "26.100": {status: documented, note: "SRC-741 p.278, same grammar as 26.120"}
    "26.120": {status: documented, note: "carried through untouched"}
"""

#: The same, with a MEASURED removal recorded for the build being probed.
CONTRADICTION_FIXTURE = """\
# Chapter: fixture for the contradicting-measurement refusal.

PRINT:
  layout: inline
  phase: control
  args:
    - name: message
      type: str
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: removed, note: "Measured: solver refuses it.", probe_ref: "reports/R.md"}
"""


def _chapter(tmp_path, body):
    """Write a one-chapter fixture tree and return its commands directory."""
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    (commands_dir / "script_controls.yaml").unlink()
    (commands_dir / "fixture.yaml").write_text(body, encoding="utf-8")
    return commands_dir


def test_a_promotion_keeps_the_keys_it_does_not_own(tmp_path):
    """The silent half of the defect whose loud half this release fixed.

    A promotion used to rewrite the whole version line from `status` and
    `report`, discarding every other key on it: a `note`, a `successor`,
    a `probe_ref`, an inline `args` override. `_validate_chapter`
    re-parses the result and passes, because what is left is well-formed
    YAML saying less, so the loss had nothing to report it.

    The exposed population is not small and it is the most expensive
    data in this database. Most rows carry a note, and those notes are
    the per-edition page citations the v0.5.0 backfill read 122 manual
    pages to write; the pages are licensed and uncommittable, so nothing
    in this repository could put them back. One probe run on an older
    build would have erased a chapter's worth with every guard green.
    """
    commands_dir = _chapter(tmp_path, KEYS_FIXTURE)
    report_path = write_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "effect observed"}}
    )
    apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    text = (commands_dir / "fixture.yaml").read_text(encoding="utf-8")

    assert "carried through untouched" in text, (
        "the promoted row lost its note, which is a manual page citation, and no guard "
        "downstream can tell it was ever there"
    )
    assert "SRC-741 p.278" in text, "a row this run never probed was rewritten"
    promoted = yaml.safe_load(text)["PRINT"]["versions"]["26.120"]
    assert promoted["status"] == "verified"
    assert promoted["report"].endswith(".yaml")
    assert promoted["note"] == "carried through untouched"


def test_a_promotion_that_contradicts_a_measured_removal_is_refused(tmp_path):
    """Two runs disagreeing about whether the build carries the command.

    A measured removal cites its run through `probe_ref`, which the
    model admits for `removed` alone. Promoting over it would either
    write a row the loader refuses or drop the citation, and choosing
    between those is not mechanical: a probe that RUNS a command
    recorded as absent means one of the two measurements is wrong about
    the build itself, which is a person's call.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = _chapter(tmp_path, CONTRADICTION_FIXTURE)
    report_path = write_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "effect observed"}}
    )
    with pytest.raises(QaEvidenceError, match="One of the two measurements is wrong"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


# --------------------------------------------------------------------------
# Supersession (PLN-20260804-1500): re-applying an older report must not
# silently revert a status a later run already moved.
# --------------------------------------------------------------------------


def write_dated_report(tmp_path, commands, *, date, label="", version="26.120"):
    """Write one report carrying a date, the field supersession orders by."""
    report_dir = tmp_path / "reports" / "compat"
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"CMP-{version.replace('.', '')}_{date}" + (f"_{label}" if label else "")
    path = report_dir / f"{stem}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": COMPAT_SCHEMA,
                "fs_version": version,
                "date": date,
                "commands": commands,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_re_applying_a_superseded_report_is_refused(tmp_path):
    """The measured case, in fixture form, and the reason this row exists.

    `NEW_SURFACE_SECTION_DISTRIBUTION` at 26.120 is broken in the
    2026-07-21 report and verified in the 2026-07-23 re-probe. Before
    this guard, handing the older report back to the ONLY sanctioned
    write path reverted the record to broken, wrote a citation that
    agreed with itself, and left the whole guard family green: the
    citation named the right build, the status equalled that report's
    outcome, and the note guard saw nothing. A reverted status makes the
    emitter refuse a command that works.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    older = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "broken", "detail": "no effect"}}, date="2026-07-21"
    )
    newer = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "effect observed"}}, date="2026-07-23"
    )

    apply_compat(newer, repo_root=tmp_path, commands_dir=commands_dir)
    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    assert "status: verified" in text

    with pytest.raises(QaEvidenceError, match="superseded evidence"):
        apply_compat(older, repo_root=tmp_path, commands_dir=commands_dir)

    assert (commands_dir / "script_controls.yaml").read_text(encoding="utf-8") == text, (
        "the refusal must write nothing at all; a partly applied report is a worse "
        "state than either applying it or refusing it"
    )


def test_a_newer_report_that_agrees_does_not_block_the_older_one(tmp_path):
    """Agreement never supersedes, and this shape is real, not invented.

    Measured on the committed corpus: four rows cite a full run while a
    later `--identity-only` run of the same build ALSO judges PRINT,
    because the baseline probe exercises it. The plan behind this guard
    asked for the strictly newest report to be the cited one, which
    would paint those four red while nothing is wrong with them. A
    guard red on a correct database is a guard that gets switched off.
    """
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    older = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "full run"}}, date="2026-08-08"
    )
    write_dated_report(
        tmp_path,
        {"PRINT": {"outcome": "verified", "detail": "baseline of the identity run"}},
        date="2026-08-09",
        label="identity",
    )

    promotions = apply_compat(older, repo_root=tmp_path, commands_dir=commands_dir)
    assert promotions == [("PRINT", "verified", "script_controls.yaml")]


def test_two_reports_of_one_day_that_disagree_are_refused(tmp_path):
    """A tie resolved silently by file order is the failure, not the tie.

    Same-date reports that AGREE are fine and the corpus has had them.
    Two of one day that disagree carry no ordering at all, so promoting
    either one is a coin flip wearing a citation.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    first = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "broken", "detail": "morning"}}, date="2026-08-08"
    )
    write_dated_report(
        tmp_path,
        {"PRINT": {"outcome": "verified", "detail": "afternoon"}},
        date="2026-08-08",
        label="second",
    )
    with pytest.raises(QaEvidenceError, match="superseded evidence"):
        apply_compat(first, repo_root=tmp_path, commands_dir=commands_dir)


def test_an_undated_report_never_supersedes_a_dated_one(tmp_path):
    """A report that cannot show it is newer is treated as not newer.

    Every report the harness writes carries a date, so an undated one is
    hand made. It still gets CHECKED against the corpus; what it cannot
    do is unseat a dated judgment by sorting ahead of it.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    dated = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-08"
    )
    apply_compat(dated, repo_root=tmp_path, commands_dir=commands_dir)

    undated = write_report(tmp_path, {"PRINT": {"outcome": "broken", "detail": "hand made"}})
    with pytest.raises(QaEvidenceError, match="superseded evidence"):
        apply_compat(undated, repo_root=tmp_path, commands_dir=commands_dir)


def test_the_corpus_index_skips_files_that_are_not_reports(tmp_path):
    """A README beside the reports must not stop a promotion."""
    from pyflightstream.qa.compat import read_compat_reports

    report_dir = tmp_path / "reports" / "compat"
    report_dir.mkdir(parents=True)
    (report_dir / "notes.yaml").write_text("just: data\n", encoding="utf-8")
    write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-08"
    )
    judgments = read_compat_reports(report_dir, repo_root=tmp_path)
    assert list(judgments) == [("PRINT", "26.120")]
    assert judgments[("PRINT", "26.120")][0].date == "2026-08-08"


def test_an_absent_reports_directory_is_the_first_report_case(tmp_path):
    """The DEFAULT location being absent is the first report of a fresh checkout.

    A path the caller typed is the opposite case and is refused, because
    an empty index reads as "nothing contradicts, promote it". The two
    used to be one branch, with the refusal living in `apply_compat`;
    the guard moved into this function when it became public, since the
    caller it protected was one of several.
    """
    from pyflightstream.qa.compat import read_compat_reports

    assert read_compat_reports(repo_root=tmp_path) == {}


def test_a_reports_directory_the_caller_typed_is_never_read_as_empty(tmp_path):
    """Including the one-character confusion with the singular reader."""
    from pyflightstream.qa.compat import read_compat_reports
    from pyflightstream.qa.errors import QaEvidenceError

    with pytest.raises(QaEvidenceError, match="not a directory"):
        read_compat_reports(tmp_path / "nowhere", repo_root=tmp_path)

    report = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-11"
    )
    with pytest.raises(QaEvidenceError, match="read_compat_report"):
        read_compat_reports(report, repo_root=tmp_path)


# --------------------------------------------------------------------------
# The removed outcome (PLN-20260809-0300) reaching the database.
# --------------------------------------------------------------------------

REMOVAL_FIXTURE = """\
# Chapter: fixture for removed promotions.

PRINT:
  layout: inline
  phase: control
  args:
    - name: message
      type: str
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented}

STOP:
  layout: bare
  phase: control
  args: []
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented, note: "SRC-741 p.358, this edition's own grammar"}

RUN_SCRIPT:
  layout: param_lines
  phase: control
  args:
    - name: script_path
      type: path
  manual_ref: "SRC-003 p.281"
  versions:
    "26.120": {status: documented, note: "carried", args: [{name: script_path, type: path}]}
"""


def _removal_chapter(tmp_path):
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "script_controls.yaml").write_text(REMOVAL_FIXTURE, encoding="utf-8")
    (commands_dir / "_meta.yaml").write_text(META_FIXTURE, encoding="utf-8")
    return commands_dir


def test_a_measured_removal_is_promoted_with_the_note_the_model_requires(tmp_path):
    """Removed is promotable evidence now, and it cannot be written bare.

    The model refuses a removed row without a note, because the status
    alone cannot say which of the three ways it arrived: an edition
    states the withdrawal, an edition stops printing the command, or a
    probe measures the solver refusing it. The probe detail says it was
    measured, and the report citation is what makes that checkable.
    """
    commands_dir = _removal_chapter(tmp_path)
    report_path = write_dated_report(
        tmp_path,
        {
            "PRINT": {
                "outcome": "removed",
                "detail": "the solver refused the name as an unrecognised command",
            }
        },
        date="2026-08-11",
    )
    promotions = apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert promotions == [("PRINT", "removed", "script_controls.yaml")]

    row = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
    promoted = row["PRINT"]["versions"]["26.120"]
    assert promoted["status"] == "removed"
    assert promoted["report"].endswith(".yaml")
    assert "unrecognised command" in promoted["note"]
    # The row must load, which is the real assertion: the model's own
    # rules for removed are stricter than any of the ones above.
    CommandEntry(name="PRINT", chapter="script_controls", **row["PRINT"])


def test_a_removal_over_an_edition_that_documents_the_command_is_refused(tmp_path):
    """The manual says yes and the solver says no, and neither is mechanical.

    The solver's wording is IDENTICAL for a command the build does not
    carry and for a token that was never a command (measured, RPT-026),
    so a probe emitting a misspelling looks exactly like a withdrawal.
    Against a row carrying that edition's page citation, promoting would
    either record a manual defect or hide a spec defect, and choosing is
    a person's call.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = _removal_chapter(tmp_path)
    report_path = write_dated_report(
        tmp_path,
        {"STOP": {"outcome": "removed", "detail": "the solver refused the name"}},
        date="2026-08-11",
    )
    with pytest.raises(QaEvidenceError, match="manual defect"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_a_removal_over_a_per_version_grammar_is_refused(tmp_path):
    """A removed version has no grammar to emit, so the two cannot coexist.

    Without this the promotion writes the row and `_validate_chapter`
    rejects it afterwards, which leaves the chapter file MUTATED by a
    run that then raised. Refusing before the write is the difference
    between a refusal and a corruption.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = _removal_chapter(tmp_path)
    before = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    report_path = write_dated_report(
        tmp_path,
        {"RUN_SCRIPT": {"outcome": "removed", "detail": "the solver refused the name"}},
        date="2026-08-11",
    )
    with pytest.raises(QaEvidenceError, match="no grammar to emit"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert (commands_dir / "script_controls.yaml").read_text(encoding="utf-8") == before


def test_the_markdown_summary_names_every_outcome(tmp_path):
    """The human-readable half must not drop an outcome either.

    The YAML summary is derived from the enum and its sibling assertion
    says why. The Markdown Summary line was changed the same way in the
    same commit and nothing covered it, so reverting that line left the
    suite green while silently dropping `removed` from the rendered
    table of every future report.
    """
    _, md_path = write_compat_report(make_run(), tmp_path, date="2026-07-22")
    markdown = md_path.read_text(encoding="utf-8")
    assert "0 removed" in markdown, markdown


def test_a_removal_travels_the_whole_path_from_run_to_database(tmp_path):
    """Harness result to YAML to database, for the outcome that is new.

    Every other removal test hand-writes the report, so the writer and
    the reader were only ever exercised for the two older outcomes. A
    reader that mishandled the new member would have passed.
    """
    commands_dir = _removal_chapter(tmp_path)
    run = ProbeRun(
        version="26.120",
        solver_identity=("FlightStream version 26.1 build #0000000",),
        fs_exe_name="Fake.exe",
        package_version="0.0.1.dev0",
        results=(
            ProbeResult(
                "PRINT",
                ProbeOutcome.REMOVED,
                "the solver refused the name as an unrecognised command",
            ),
        ),
    )
    report_dir = tmp_path / "reports" / "compat"
    yaml_path, _ = write_compat_report(run, report_dir, date="2026-08-11")
    assert read_compat_report(yaml_path)["summary"]["removed"] == 1

    promotions = apply_compat(yaml_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert promotions == [("PRINT", "removed", "script_controls.yaml")]
    row = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
    CommandEntry(name="PRINT", chapter="script_controls", **row["PRINT"])


def test_an_explicit_reports_directory_that_is_missing_is_refused(tmp_path):
    """A guard that reads its own missing configuration as permission.

    An ABSENT default corpus is the first-report case and is tolerated.
    A path the caller typed is different: reading a typo as "nothing
    supersedes this" turns the only supersession check in the sanctioned
    write path into a no-op, with no output at all.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-11"
    )
    with pytest.raises(QaEvidenceError, match="not a directory"):
        apply_compat(
            report_path,
            repo_root=tmp_path,
            commands_dir=commands_dir,
            reports_dir=tmp_path / "typo",
        )


def test_a_report_outside_the_repository_is_refused_by_name(tmp_path):
    """The citation has to be a path a reader can follow.

    This used to raise a bare ValueError out of `relative_to`, which is
    the stdlib leaking through a public function with no statement of
    what to do about it.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    outside = tmp_path.parent / f"{tmp_path.name}_outside"
    outside.mkdir(exist_ok=True)
    stray = outside / "CMP-26120_2026-08-11.yaml"
    stray.write_text(
        yaml.safe_dump(
            {
                "schema": COMPAT_SCHEMA,
                "fs_version": "26.120",
                "date": "2026-08-11",
                "commands": {"PRINT": {"outcome": "verified", "detail": "x"}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(QaEvidenceError, match="outside"):
        apply_compat(stray, repo_root=tmp_path, commands_dir=commands_dir)


def test_a_refusal_in_the_second_chapter_leaves_the_first_untouched(tmp_path):
    """Atomicity across chapters, which is where the promise was false.

    The docstring says a refusal writes nothing. That held for the
    up-front checks and not for the loop: chapters were written one at a
    time, so a refusal raised while rewriting chapter n left chapters
    1..n-1 already promoted on disk, under a message naming one command
    in one file. The two removal refusals are exactly such raise sites.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    commands_dir.mkdir()
    (commands_dir / "_meta.yaml").write_text(META_FIXTURE, encoding="utf-8")
    # Sorted glob order puts a_first before z_second, so the refusal in
    # the second chapter comes after the first has been rewritten.
    (commands_dir / "a_first.yaml").write_text(
        "PRINT:\n"
        "  layout: inline\n"
        "  phase: control\n"
        "  args:\n"
        "    - name: message\n"
        "      type: str\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n"
        '    "26.120": {status: documented}\n',
        encoding="utf-8",
    )
    (commands_dir / "z_second.yaml").write_text(
        "STOP:\n"
        "  layout: bare\n"
        "  phase: control\n"
        "  args: []\n"
        '  manual_ref: "SRC-003 p.281"\n'
        "  versions:\n"
        '    "26.120": {status: documented, note: "SRC-741 p.358, this edition"}\n',
        encoding="utf-8",
    )
    before = (commands_dir / "a_first.yaml").read_text(encoding="utf-8")

    report_path = write_dated_report(
        tmp_path,
        {
            "PRINT": {"outcome": "verified", "detail": "effect observed"},
            "STOP": {"outcome": "removed", "detail": "the solver refused the name"},
        },
        date="2026-08-11",
    )
    with pytest.raises(QaEvidenceError, match="manual defect"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)

    assert (commands_dir / "a_first.yaml").read_text(encoding="utf-8") == before, (
        "the first chapter was promoted although the run was refused in the second; "
        "a partly promoted database is worse than either applying or refusing"
    )


def test_a_judgment_cannot_be_built_positionally():
    """Keyword-only is the guard, not the docstring that claims it.

    Five consecutive string fields: a swapped pair makes the corpus
    lookup miss and answer "nothing contradicts, promote it". The
    docstring says the record cannot be mis-ordered, and that sentence
    is only true while this holds.
    """
    from pyflightstream.qa.compat import Judgment

    with pytest.raises(TypeError):
        Judgment("PRINT", "26.120", "verified", "2026-08-11", "reports/compat/x.yaml")


def test_a_missing_report_path_is_refused_in_this_modules_own_type(tmp_path):
    """The escape class, fixed once rather than at the site review found.

    `apply_compat` documents QaEvidenceError and the CLI traps it. Three
    reachable inputs escaped both as stacks that say nothing about
    whether the database was written; a mistyped path is the likeliest.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    with pytest.raises(QaEvidenceError, match="cannot be read"):
        apply_compat(
            tmp_path / "reports" / "compat" / "CMP-26120_2026-08-11_typo.yaml",
            repo_root=tmp_path,
            commands_dir=commands_dir,
        )


def test_an_unparsable_file_in_the_reports_directory_is_refused_not_skipped(tmp_path):
    """Skipping it would lose whatever it judged, silently.

    A file that PARSES and is not a report is skipped by design, so a
    README beside the evidence cannot stop a promotion. A file that does
    not parse is a different thing: the supersession check would carry
    on without whatever that report said, which is a guard reading its
    own missing information as permission.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    report_path = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-11"
    )
    (report_path.parent / "broken.yaml").write_text("key: [unclosed\n", encoding="utf-8")
    with pytest.raises(QaEvidenceError, match="not parsable YAML"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_a_file_that_parses_and_is_not_a_report_is_still_skipped(tmp_path):
    """The other half, so the refusal above cannot widen into it."""
    from pyflightstream.qa.compat import read_compat_reports

    reports = tmp_path / "reports" / "compat"
    reports.mkdir(parents=True)
    (reports / "notes.yaml").write_text("just: data\n", encoding="utf-8")
    write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-11"
    )
    assert list(read_compat_reports(repo_root=tmp_path)) == [("PRINT", "26.120")]


def test_a_note_carrying_a_backslash_survives_a_yaml_round_trip():
    """The property the embed-safety test above only claimed to check.

    That test asserted the note carries no double quote and collapsed
    whitespace, and never round-tripped the rendered line. The note was
    interpolated between two quotes with no escaping while every other
    key went through `_flow_scalar`, so one backslash in a solver
    message produced a chapter file that `yaml.safe_load` refuses.
    Reachable: `_scan_errors` copies solver log lines verbatim and
    Windows paths appear in them.
    """
    from pyflightstream._yamlflow import flow_scalar
    from pyflightstream.qa.compat import _one_line_note

    detail = "the solver logged errors: cannot open " + chr(92).join(["C:", "runs", "s.txt"])
    note = flow_scalar(_one_line_note(detail))
    line = f'"26.122": {{status: broken, report: "r.yaml", note: {note}}}'
    parsed = yaml.safe_load("{" + line + "}")
    assert parsed["26.122"]["note"] == _one_line_note(detail)


def test_a_rewrite_that_fails_the_schema_refuses_in_this_modules_type(tmp_path):
    """The re-raise added in round two, which nothing reached.

    Its own comment names the path: a hand-written `removed` report with
    no `detail` yields an empty note, and the model refuses a removed
    row without one. Before the re-raise that escaped as pydantic's own
    type, past the documented contract and past the CLI trap.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = _removal_chapter(tmp_path)
    before = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    report_path = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "removed", "detail": ""}}, date="2026-08-11"
    )
    with pytest.raises(QaEvidenceError, match="does not satisfy the command schema"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert (commands_dir / "script_controls.yaml").read_text(encoding="utf-8") == before


def test_a_removal_is_inserted_at_its_release_position_on_a_build_with_no_row(tmp_path):
    """The path a real removal actually takes, which nothing exercised.

    Every one of the 84 promotions of 2026-08-11 was an insert, because
    a newly registered build records no line yet. The rewrite path was
    covered and the insert path was not, so a promotion of `removed`
    onto a new build could have lost its note and died at validation
    with the suite green.
    """
    commands_dir = _removal_chapter(tmp_path)
    (commands_dir / "_meta.yaml").write_text(
        'versions:\n  - canonical: "26.120"\n    alias: "26.12"\n'
        '  - canonical: "26.122"\n    alias: "26.12"\n',
        encoding="utf-8",
    )
    report_path = write_dated_report(
        tmp_path,
        {"PRINT": {"outcome": "removed", "detail": "the solver refused the name"}},
        date="2026-08-11",
        version="26.122",
    )
    promotions = apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)
    assert promotions == [("PRINT", "removed", "script_controls.yaml")]

    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    rows = yaml.safe_load(text)["PRINT"]["versions"]
    assert list(rows) == ["26.120", "26.122"], "the insert must land at its release position"
    assert rows["26.122"]["status"] == "removed"
    assert "refused the name" in rows["26.122"]["note"]
    CommandEntry(name="PRINT", chapter="script_controls", **yaml.safe_load(text)["PRINT"])


def test_the_args_refusal_is_the_compat_guard_and_not_the_schema_backstop(tmp_path):
    """The guard, not the net behind it.

    The model's own message carries the same phrase this test used to
    match on, so deleting the compat guard left the test green: the
    schema refused the write for its own reasons and the didactic
    refusal that names the decision to make was gone. Matching a
    sentence only the compat guard emits is what tells them apart.
    """
    from pyflightstream.qa.errors import QaEvidenceError

    commands_dir = _removal_chapter(tmp_path)
    report_path = write_dated_report(
        tmp_path,
        {"RUN_SCRIPT": {"outcome": "removed", "detail": "the solver refused the name"}},
        date="2026-08-11",
    )
    with pytest.raises(QaEvidenceError, match="declares a per-version argument grammar"):
        apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)


def test_a_report_never_supersedes_itself(tmp_path):
    """Documented on the public function, and unfalsified until now.

    Redundant inside `apply_compat`, where a report's own entry agrees
    with itself. Not redundant for a caller who re-judges from the same
    path, which is what the exported function invites.
    """
    from pyflightstream.qa.compat import Judgment, contradicting_evidence, read_compat_reports

    write_dated_report(
        tmp_path, {"PRINT": {"outcome": "verified", "detail": "measured"}}, date="2026-08-11"
    )
    judgments = read_compat_reports(repo_root=tmp_path)
    own = "reports/compat/CMP-26120_2026-08-11.yaml"
    assert (
        contradicting_evidence(
            judgments,
            incoming=Judgment(
                command="PRINT",
                fs_version="26.120",
                outcome="broken",
                date="2026-08-11",
                report=own,
            ),
        )
        == ()
    )


#: Characters a solver detail can carry into a flow mapping. `_scan_errors`
#: copies log lines verbatim, so this is the alphabet of the real input,
#: not a stress test. The backslash is first because it is the one that
#: shipped: four releases carried a note interpolated between two quotes
#: with no escaping.
_HOSTILE = (
    chr(92) + "runs" + chr(92) + "new" + chr(92) + "temp.txt",
    chr(92) + "t" + chr(92) + "n" + chr(92) + "r",
    "quote \" and apostrophe '",
    "braces {} and brackets [] and comma,",
    "colon: hash # pipe | gt > amp & star * pct % at @",
)


@pytest.mark.parametrize("hostile", _HOSTILE)
def test_a_promotion_survives_a_hostile_detail_through_the_whole_write_path(tmp_path, hostile):
    """Drive `apply_compat` itself, which is the only thing that counts.

    The guard this replaces round-tripped
    `_flow_scalar(_one_line_note(detail))`, the composition the FIXED
    code happens to use, and never called the emitter. Measured: with
    both note interpolations reverted to their shipped form, that guard
    passes, the whole suite passes, and the committed mutation battery
    reports every mutant dead. A guard scored against the helper cannot
    see a call site that skips the helper.

    Two failures are in scope and the second is the worse one. An
    unknown escape makes the chapter unparsable and aborts the
    promotion. A detail whose backslashes happen to precede VALID YAML
    escapes does not refuse at all: it writes, and the note silently
    gains a tab, a newline and a carriage return.
    """
    commands_dir = tmp_path / "commands"
    write_chapter_fixture(commands_dir)
    detail = f"the solver logged errors between the probe sentinels: {hostile}"
    report_path = write_dated_report(
        tmp_path, {"PRINT": {"outcome": "broken", "detail": detail}}, date="2026-08-11"
    )

    apply_compat(report_path, repo_root=tmp_path, commands_dir=commands_dir)

    text = (commands_dir / "script_controls.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert parsed["PRINT"]["versions"]["26.120"]["note"] == _one_line_note(detail), (
        "the note came back changed, so the promotion wrote something other than what "
        "the report says; an escape that YAML happens to understand corrupts silently"
    )
    CommandEntry(name="PRINT", chapter="script_controls", **parsed["PRINT"])


def test_an_unparsable_rewrite_refuses_in_this_modules_type():
    """The try scope, pinned without depending on the escaping being right.

    Moving `yaml.safe_load` back outside its try survives the whole
    suite otherwise, and with the note interpolation reverted the pair
    reproduces the original defect exactly: a bare scanner error out of
    a function documented to raise `QaEvidenceError`, past the CLI trap.
    Measured while writing this: an unknown escape fails to scan and
    aborts the promotion, while a backslash that happens to precede a
    VALID escape parses and corrupts the note silently.
    """
    from pyflightstream.qa.compat import _validate_chapter
    from pyflightstream.qa.errors import QaEvidenceError

    bad = 'PRINT:\n  versions:\n    "26.120": {note: "a' + chr(92) + 's b"}\n'
    with pytest.raises(QaEvidenceError, match="does not parse as YAML"):
        _validate_chapter("script_controls.yaml", bad, ["PRINT"])


def test_this_module_defines_no_renderer_of_its_own():
    """The escaper lives below every layer now, and this module uses it.

    THIS GUARD USED TO BE THE ONE-CALLER GUARD and it has moved, with
    its subject, to ``tests/test_yamlflow.py``. It is worth reading why
    rather than only where.

    The 2026-08-11 repair of ``INC-20260811-1511-both`` made this module
    the one home of the rendering and said so in the docstring: "there
    is now no site". That was true of this module and it was never true
    of the package. On 2026-08-17 ``pyfs-manual register`` began writing
    the same chapter files from ``pyflightstream.utils``, which sits
    BELOW ``qa`` and could not import the helper, so it built the
    mapping by concatenation and the whole class came back.

    A guard scoped to one module could not see that, which is exactly
    what happened: the old form of this test passed on the day the
    second site was written. So what is asserted HERE is only the half
    that is about this module, that it defines no renderer of its own,
    and the package-wide rule is asserted where the renderer now lives.
    """
    import ast
    import inspect

    from pyflightstream._yamlflow import flow_mapping
    from pyflightstream.qa import compat

    tree = ast.parse(inspect.getsource(compat))
    defined = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"_flow_mapping", "_flow_scalar"}
    ]
    assert not defined, (
        "qa.compat defines its own flow-mapping renderer again, so the package has two "
        "and they can disagree: " + ", ".join(defined)
    )
    assert compat._flow_mapping is flow_mapping
