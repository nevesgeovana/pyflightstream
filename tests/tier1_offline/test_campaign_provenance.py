"""Tier 1: whether a campaign file was generated, and by what.

One rule with three faces (PFS-2009.07.01, .02, .03):

* a campaign file the package WROTE says so IN the file, so a copy
  carried out of its folder still says so;
* a derived campaign whose text no longer matches what was generated is
  REFUSED at load, naming the matrix and telling the user to edit that;
* a campaign nobody generated is the SOURCE: it loads with nothing said
  about it and reads back as the source it is.

The third is what keeps the second honest. The refusal fires only on a
file that CARRIES the marker, so every hand-written campaign in
existence loads exactly as it did before; a refusal written the other
way round would have refused all of them.

The writer of the marker, ``stamp_derived_campaign``, had no caller in the
package or the estate and was deleted in 0.33.0 (decision 9 of the scope,
P0330-WP2); the READER of the marker stays, because campaign files stamped
by earlier releases exist. These tests therefore write the marker the way
those releases did, with :func:`_stamp` below, and hold the reader to it.

The matrix here is hashed, never parsed: the marker records the BYTES
of the file the conversion read, so these tests write a short text file
rather than a 15-column matrix and stay independent of the reader.
"""

import warnings

import pytest

import pyflightstream.cases as cases_module
from pyflightstream._digest import file_sha256
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    derived_body_sha256,
    load_campaign,
)

MATRIX_TEXT = "POL | RUN\n9001 | 1\n"

AUTHORED = """
[campaign]
name = "wing_steady"
fs_version = "26.120"
fs_exe = "FlightStream.exe"

[[sim]]
sim_id = "9001"
aircraft = "TestWing"
sweep = {type = "alpha", values = [0.0, 2.0]}
recipe = "recipes.steady_polar:build"
outputs = ["loads_{point}.txt"]
[sim.variables]
matrix_fs_script = "003"
"""


@pytest.fixture(autouse=True)
def _in_the_campaign_folder(tmp_path, monkeypatch):
    """Run every test from the folder the campaign and matrix sit in.

    That is where ``pyfs-matrix convert matrix.fs -o campaign.toml`` is
    run, so the marker records a RELATIVE matrix path, which is the case
    that has to keep working when the pair is copied somewhere else.
    """
    monkeypatch.chdir(tmp_path)


def _stamp(text, matrix, *, generated_at="2026-09-30T12:00:00Z"):
    """Write the ``[campaign.derived_from]`` marker the way releases up to 0.32.0 did.

    The marker table goes right after the ``[campaign]`` scalars (TOML puts
    a sub-table there), or at the end when no table follows; the content
    digest is taken with :func:`pyflightstream.cases.derived_body_sha256`
    over the text without its own line, which is what the reader recomputes.
    """
    table = [
        "[campaign.derived_from]",
        f'matrix = "{matrix}"',
        f'matrix_sha256 = "{file_sha256(matrix)}"',
        f'generated_at = "{generated_at}"',
    ]
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "[campaign]")
    insert_at = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    head = lines[:insert_at]
    while head and not head[-1].strip():
        head.pop()
    tail = lines[insert_at:]
    digest = derived_body_sha256("\n".join(head + [""] + table + [""] + tail))
    stamped = head + [""] + table + [f'content_sha256 = "{digest}"', ""] + tail
    return "\n".join(stamped).rstrip("\n") + "\n"


def _derived_campaign(tmp_path, *, text=AUTHORED, matrix_text=MATRIX_TEXT):
    """Write a matrix and the derived campaign beside it; return both paths."""
    matrix = tmp_path / "matrix.fs"
    matrix.write_text(matrix_text, encoding="utf-8")
    campaign = tmp_path / "campaign.toml"
    campaign.write_text(_stamp(text, matrix.name), encoding="utf-8")
    return matrix, campaign


# --- PFS-2009.07.01: the file says it was generated ------------------------


def test_a_generated_campaign_names_the_matrix_and_the_moment(tmp_path):
    """The marker travels IN the file, not in its location.

    A generated campaign that is byte-indistinguishable from an authored
    one will be edited by someone who believes it is input, and the
    marker is what makes the rule enforceable instead of conventional. It
    has to be in the file because a file gets copied out of its folder.
    """
    matrix, campaign_path = _derived_campaign(tmp_path)
    campaign = load_campaign(campaign_path)

    assert getattr(campaign, "is_derived", None) is True, (
        "a campaign the package generated does not report itself as derived"
    )
    marker = campaign.derived_from
    assert marker is not None
    assert marker.matrix == "matrix.fs", "the marker does not name the matrix it came from"
    # The MATRIX digest is over raw bytes, which is what `file_sha256`
    # promises and is why this compares against the file rather than
    # against MATRIX_TEXT: `write_text` turns each newline into CRLF on
    # Windows, so the two differ and the file is the honest reference.
    assert marker.matrix_sha256 == file_sha256(matrix)
    # A moment, in UTC, that a reader can parse rather than guess at.
    assert marker.generated_at.endswith("Z")
    assert marker.generated_at[:4].isdigit()


def test_an_authored_campaign_carries_no_marker_and_no_message(tmp_path):
    """The other half of "reading either back reports which kind it is".

    Nothing about the authored path may feel deprecated while it is
    supported, so this asserts silence as well as the flag: a user who
    has never written a matrix must be able to state a study and hear
    nothing about it.
    """
    path = tmp_path / "campaign.toml"
    path.write_text(AUTHORED, encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        campaign = load_campaign(path)

    assert getattr(campaign, "is_derived", None) is False, (
        "an authored campaign reports itself as derived (or cannot answer at "
        "all), so the two kinds of file cannot be told apart"
    )
    assert campaign.derived_from is None
    assert [str(entry.message) for entry in caught] == [], (
        "loading an authored campaign said something about it; the authored "
        "path is supported, not deprecated"
    )


# --- PFS-2009.07.02: an edited derived campaign is refused -----------------


@pytest.mark.parametrize(
    ("original", "replacement", "what"),
    [
        ('fs_exe = "FlightStream.exe"', 'fs_exe = "D:/other/FlightStream.exe"', "fs_exe"),
        ('fs_version = "26.120"', 'fs_version = "26.121"', "fs_version"),
        (
            'recipe = "recipes.steady_polar:build"',
            'recipe = "recipes.other:build"',
            "recipe",
        ),
        (
            'outputs = ["loads_{point}.txt"]',
            'outputs = ["loads_{point}.txt", "cp_{point}.txt"]',
            "outputs",
        ),
        ('aircraft = "TestWing"', 'aircraft = "OtherWing"', "a case field"),
    ],
)
def test_an_edited_derived_campaign_is_refused_naming_the_matrix(
    tmp_path, original, replacement, what
):
    """Every edited field, not only the ones a re-derivation could see.

    A check that re-derives the campaign from the matrix cannot see an
    edited fs_exe, fs_version or recipe at all: those three are handed to
    the conversion rather than read from the matrix, so the re-derivation
    would be seeded from the file under test and they would be equal BY
    CONSTRUCTION. This compares the file against a digest taken when it
    was generated, so every field is covered the same way.
    """
    _, campaign_path = _derived_campaign(tmp_path)
    text = campaign_path.read_text(encoding="utf-8")
    assert text.count(original) == 1, f"the edit anchor {original!r} is not unique"
    campaign_path.write_text(text.replace(original, replacement), encoding="utf-8")

    with pytest.raises(CampaignConfigError) as caught:
        load_campaign(campaign_path)
    message = str(caught.value)
    assert "matrix.fs" in message, (
        f"the refusal for an edited {what} does not name the matrix, so the user "
        "is not told where the edit belongs"
    )
    assert "campaign.toml" in message


def test_a_derived_campaign_that_still_matches_loads_normally(tmp_path):
    """The control, without which the refusal above is satisfied by refusing all."""
    _, campaign_path = _derived_campaign(tmp_path)
    campaign = load_campaign(campaign_path)
    assert campaign.name == "wing_steady"
    assert [case.sim_id for case in campaign.sims] == ["9001"]


def test_a_derived_campaign_survives_windows_line_endings(tmp_path):
    """The digest answers about content, not about how a file was written.

    ``open(..., 'w')`` turns every newline into CRLF on Windows, so a
    digest taken over the raw bytes would refuse the very file the
    package had just written.
    """
    _, campaign_path = _derived_campaign(tmp_path)
    text = campaign_path.read_text(encoding="utf-8")
    campaign_path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert load_campaign(campaign_path).is_derived is True


def test_trailing_whitespace_is_not_a_reason_to_refuse_a_campaign(tmp_path):
    """The half the line-ending test does NOT measure, measured.

    ``splitlines()`` already drops the line terminator, so the CRLF case
    above passes with the right-strip removed; a mutation run showed
    exactly that. What the strip is for is trailing spaces, which no
    reader can see and which several editors add or remove on save. A
    refusal on those would be a mystery refusal.
    """
    _, campaign_path = _derived_campaign(tmp_path)
    padded = "\n".join(
        line + "   " for line in campaign_path.read_text(encoding="utf-8").splitlines()
    )
    campaign_path.write_text(padded + "\n", encoding="utf-8")
    assert load_campaign(campaign_path).is_derived is True


def test_a_case_variable_spelled_like_the_digest_key_hides_no_edit(tmp_path):
    """The canonical form drops ONE line, and a sim variable is not it.

    Case variables are emitted quoted, so a variable named for the digest
    key cannot be mistaken for it; if it could, an edit made anywhere
    else in the file would still have to be refused.
    """
    text = AUTHORED.replace(
        'matrix_fs_script = "003"',
        'matrix_fs_script = "003"\n"content_sha256" = "not the digest"',
    )
    _, campaign_path = _derived_campaign(tmp_path, text=text)
    assert load_campaign(campaign_path).is_derived is True

    edited = campaign_path.read_text(encoding="utf-8").replace(
        'aircraft = "TestWing"', 'aircraft = "OtherWing"'
    )
    campaign_path.write_text(edited, encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="matrix.fs"):
        load_campaign(campaign_path)


def test_an_edited_matrix_makes_the_derived_campaign_stale(tmp_path):
    """The second digest: the campaign no longer describes the matrix it names."""
    matrix, campaign_path = _derived_campaign(tmp_path)
    matrix.write_text(MATRIX_TEXT + "9002 | 1\n", encoding="utf-8")
    with pytest.raises(CampaignConfigError) as caught:
        load_campaign(campaign_path)
    assert "matrix.fs" in str(caught.value)


def test_a_derived_campaign_whose_matrix_is_absent_still_loads(tmp_path):
    """The marker exists to survive the file being copied out of its folder.

    Refusing an unreadable matrix would make the marker the reason a
    perfectly good campaign stops loading, which is the opposite of what
    it is for. The content digest still applies; only the staleness half
    is skipped.
    """
    matrix, campaign_path = _derived_campaign(tmp_path)
    matrix.unlink()
    assert load_campaign(campaign_path).is_derived is True


# --- PFS-2009.07.03: an authored campaign is the source --------------------


def test_a_loaded_campaign_knows_the_file_it_came_from(tmp_path):
    """The study source, for the record that will carry it.

    Set only by ``load_campaign``, so a campaign file cannot declare a
    source it did not come from: the TOML surface is untouched and a
    campaign built in Python has no source at all.
    """
    path = tmp_path / "campaign.toml"
    path.write_text(AUTHORED, encoding="utf-8")
    campaign = load_campaign(path)

    assert getattr(campaign, "source_path", None) == str(path), (
        "a loaded campaign cannot say which file it came from, so a run "
        "record has nothing to name as the study source"
    )
    in_python = Campaign(
        name="camp", fs_version="26.120", fs_exe="FlightStream.exe", sims=campaign.sims
    )
    assert getattr(in_python, "source_path", "unset") is None, (
        "a campaign nobody loaded from a file reports one anyway"
    )


def test_the_source_survives_the_copy_the_matrix_resolution_makes(tmp_path):
    """``resolve_matrix`` rebuilds the campaign with ``model_copy``.

    A source that is lost by the copy is a source the run record never
    sees, because every matrix-driven campaign reaches the loop through
    one.
    """
    path = tmp_path / "campaign.toml"
    path.write_text(AUTHORED, encoding="utf-8")
    campaign = load_campaign(path)
    copied = campaign.model_copy(update={"sims": list(campaign.sims)})
    assert getattr(copied, "source_path", None) == str(path)


def test_a_campaign_with_no_cases_still_takes_the_marker_at_the_end(tmp_path):
    """A marker at the end of the file, where no table follows [campaign].

    A campaign declaring no case is degenerate but legitimate, and the
    marker has nowhere to be inserted BEFORE, so it lands at the end; the
    reader has to find it there too.
    """
    matrix = tmp_path / "matrix.fs"
    matrix.write_text(MATRIX_TEXT, encoding="utf-8")
    text = '[campaign]\nname = "empty"\nfs_version = "26.120"\nfs_exe = "FlightStream.exe"\n'
    path = tmp_path / "campaign.toml"
    path.write_text(_stamp(text, matrix.name), encoding="utf-8")
    campaign = load_campaign(path)
    assert campaign.is_derived is True
    assert campaign.sims == []


def test_the_marker_writer_is_deleted_and_its_reader_stays():
    # P0330-WP2 (decision 9 of the 0.33.0 scope, AD-10): the writer had no
    # caller and left the package with a CHANGELOG Removed entry; the reader,
    # which the tests above hold to the marker, is still public.
    assert not hasattr(cases_module, "stamp_derived_campaign")
    assert "stamp_derived_campaign" not in cases_module.__all__
    assert "derived_body_sha256" in cases_module.__all__
    assert "DerivedFrom" in cases_module.__all__


def test_a_campaign_file_cannot_declare_its_own_source(tmp_path):
    """``source_path`` is knowledge, not a field somebody can write."""
    path = tmp_path / "campaign.toml"
    path.write_text(AUTHORED.replace("[campaign]", '[campaign]\nsource_path = "lie.toml"'))
    with pytest.raises(ValueError, match="source_path"):
        load_campaign(path)
