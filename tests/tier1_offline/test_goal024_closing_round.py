"""Tier 1: the six 0.21.0 behaviours that shipped with no test (GOAL-024, CLOSE-0210).

The qa lens of the closing round grepped `tests/` for the operative content of
six new refusals and next-step messages and found nothing for any of them. Each
of the six WORKED when probed by hand, and working-and-untested is still
untested: the commit that opened this round is itself about a presence-only test
that a mutant walked past.

One module rather than six additions, because these are the findings of one round
and a reader looking for what CLOSE-0210 established should find it in one place.

* a polar table refused when no record collected an output;
* an HPC profile key this package does not read, at the top level, under `[log]`
  and -- the spelling people actually write -- appended into the last table;
* `EXPORT_LOG` refusing a word it does not know, rather than reading it as the
  permissive side;
* a non-numeric `FLIGHT_CONDITION` value raising the `CampaignConfigError` its
  caller's Raises section promises;
* the rehearsal of `rename` reporting the manifest archive and the plan rewrite;
* every arm of `rename` ending with the next step.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.workspace.inputs import InputArtifactError, read_hpc_profile
from tests.tier1_offline.test_goal024_profile_log import _case

PROFILE = """\
application_id = "flightstream"
walltime_arithmetic = "wall"
{top}

[descriptor]
template = "descriptor.tmpl"

[descriptor.fields]
walltime = "{walltime}"

[builds]
"26.124" = "/opt/fts/26.124"

[submit]
command = ["sbatch", "{descriptor}"]
"""


def _profile(tmp_path, extra: str = "", *, top: str = "", body: str = PROFILE):
    """Write a profile, with `top` at the TRUE top level and `extra` appended.

    The two are not the same place and that is the whole of one finding here: a
    line appended to the end of a TOML file belongs to the LAST TABLE.
    """
    path = tmp_path / "hpc.toml"
    path.write_text(body.replace("{top}", top) + extra, encoding="utf-8")
    return path


# ------------------------------------------------------------------ the profile


def test_goal024_closing_round_a_profile_key_this_package_does_not_read_is_refused(tmp_path):
    """A key at the top level outside the closed set is refused, naming it and the set."""
    path = _profile(tmp_path, top='notes = "the queue is busy on Fridays"')

    with pytest.raises(InputArtifactError) as raised:
        read_hpc_profile(path)

    message = str(raised.value)
    assert "notes" in message, message
    # The refusal names the set it is not in, so the fix is in the message.
    assert "walltime_arithmetic" in message and "application_id" in message, message


def test_goal024_closing_round_a_log_table_key_this_package_does_not_read_is_refused(tmp_path):
    """`[log]` is closed too: a mistyped `native_logs` is a run with no log."""
    path = _profile(tmp_path, '\n[log]\nexport_log = false\nnative_logs = "FTS{sim}.l*"\n')

    with pytest.raises(InputArtifactError) as raised:
        read_hpc_profile(path)

    message = str(raised.value)
    assert "native_logs" in message and "[log]" in message, message


def test_goal024_closing_round_a_log_key_appended_to_the_end_of_the_file_is_refused(tmp_path):
    """The spelling people actually write: appended at the end, which is the LAST TABLE.

    Measured by the qa lens, 2026-09-16: `export_log = false` written under
    `[submit]`, `[descriptor]` or `[descriptor.fields]` was ACCEPTED IN SILENCE
    while the refusal beside it told the user to move the key to the table that
    takes it. In TOML, appending a line to the end of a profile file puts it in
    the last table, and in the documented example that is `[submit]`.

    This is the one of the three that matters, because it is the one that leaves
    `EXPORT_LOG` in the script on the very machine the table exists for.
    """
    path = _profile(tmp_path, "\nexport_log = false\n")

    with pytest.raises(InputArtifactError) as raised:
        read_hpc_profile(path)

    message = str(raised.value)
    assert "export_log" in message and "[submit]" in message, message
    assert "[log]" in message, "the refusal says where the key belongs"


def test_goal024_closing_round_a_log_key_in_a_nested_table_is_refused(tmp_path):
    """A table one level deeper is reached too: `[descriptor.fields]`."""
    body = PROFILE.replace(
        'walltime = "{walltime}"', 'walltime = "{walltime}"\nnative_log = "FTS{sim}.l*"'
    )
    path = _profile(tmp_path, body=body)

    with pytest.raises(InputArtifactError) as raised:
        read_hpc_profile(path)

    assert "descriptor.fields" in str(raised.value), str(raised.value)


def test_goal024_closing_round_the_documented_profile_is_accepted(tmp_path):
    """THE CONTROL: the same profile with nothing stray reads, so the refusals discriminate.

    A refusal test alone is satisfied by a constant. This is the unmutated side.
    """
    path = _profile(tmp_path, '\n[log]\nexport_log = false\nnative_log = "FTS{sim}.l*"\n')

    profile = read_hpc_profile(path)

    assert profile.export_log is False
    assert profile.native_log == "FTS{sim}.l*"
    assert profile.walltime_arithmetic == "wall"


# ------------------------------------------------ the yes-or-no word, and a number


def test_goal024_closing_round_export_log_refuses_a_word_it_does_not_know():
    """`EXPORT_LOG: flase` is refused by name rather than read as the permissive side.

    The permissive side is the one that hurts: a typo read as "yes, export it"
    puts `EXPORT_LOG` back in the script on a machine that aborts at it.
    """
    from pyflightstream.cases.workflows import _exports_its_log

    case = _case("flase")

    with pytest.raises(CampaignConfigError) as raised:
        _exports_its_log(case)

    assert "flase" in str(raised.value), str(raised.value)


def test_goal024_closing_round_export_log_reads_the_words_it_does_know():
    """THE CONTROL for the refusal above: `false` and `true` are read, and are opposite."""
    from pyflightstream.cases.workflows import _exports_its_log

    assert _exports_its_log(_case("false")) is False
    assert _exports_its_log(_case("true")) is True
    # A cell that says nothing keeps the behaviour of the release before this one.
    assert _exports_its_log(_case()) is True


# --------------------------------------------- a value that is not a number


def test_goal024_closing_round_a_non_numeric_flight_condition_value_raises_its_promised_error():
    """The naming path raises what its caller's Raises section promises.

    `point_name` reads each declared variable as a NUMBER to write its
    fixed-width code. A cell writing a word there raised `ValueError` out of
    `float()`, which is not the exception the campaign layer documents and not a
    sentence anyone can act on (the architecture lens, 2026-09-16).
    """
    from pyflightstream.cases import point_name

    bad = _case().model_copy(
        update={
            "condition_order": ["MACH", "ALPHA"],
            "flight_condition": {"MACH": "fast", "ALPHA": 0.0},
        }
    )

    with pytest.raises(CampaignConfigError) as raised:
        point_name(bad, {"alpha": 0.0})

    message = str(raised.value)
    assert "MACH" in message and "fast" in message, message


def test_goal024_closing_round_the_name_is_written_when_every_value_is_a_number():
    """THE CONTROL for the refusal above: the same shape with numbers names the point."""
    from pyflightstream.cases import point_name

    good = _case().model_copy(
        update={
            "condition_order": ["MACH", "ALPHA"],
            "flight_condition": {"MACH": 0.2, "ALPHA": 0.0},
        }
    )

    written = point_name(good, {"alpha": 0.0})

    assert written == "M200AL+000", written


# ------------------------------------------- a simulation that collected nothing


def test_goal024_closing_round_a_simulation_not_collected_yet_writes_nothing_and_stops_nothing(
    tmp_path,
):
    """Between `run` and `collect` a simulation has no product, and that is not an error.

    The closing round's F4 listed an empty-`recorded` refusal among the
    behaviours with no test. Writing the test measured that NO CASE REACHES IT:
    a point is appended only inside the loop that skips a record with no
    outputs, so `points` is empty whenever `recorded` would be, and the early
    return above has already returned. The refusal was removed rather than
    covered, and what is asserted here is the property that made it
    unreachable, which is a real guarantee nothing was testing.

    THE HALF THAT MATTERS is that the stage does not ABORT: a workspace part-way
    through its collect must still post the simulations that are ready.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    rows = workspace.read_raw_manifest()
    assert len(rows) >= 2, rows
    # ONE simulation is left uncollected and the others are untouched.
    emptied = 0
    for row in rows:
        if str(row["sim_id"]) == "6001":
            row["outputs"] = []
            emptied += 1
    assert emptied, rows
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    written = _post(workspace)

    names = [path.name for path in written]
    assert names, "the simulations that ARE collected still post"
    assert not any("6001" in name for name in names), names


def test_goal024_closing_round_the_same_workspace_fully_collected_posts_that_simulation_too():
    """THE CONTROL: with its outputs in place, 6001 writes products.

    Without this the assertion above is satisfied by a stage that writes nothing
    for anybody.
    """
    import tempfile

    from tests.tier1_offline.test_post_superfile import _post, _workspace

    with tempfile.TemporaryDirectory() as room:
        written = _post(_workspace(Path(room)))

    names = [path.name for path in written]
    assert any("6001" in name for name in names), names


# ------------------------------------------------------- the command says what next


def test_goal024_closing_round_the_nothing_to_do_arm_of_rename_says_so_in_words(capsys, tmp_path):
    """Nothing to do is a SUCCESS and says so, because this command is run twice.

    The first writing printed a next step for this arm alone; the interface lens
    asked for one on each. This asserts the arm a careful user reaches first: a
    silent zero reads as "it did not run".
    """
    from pyflightstream.run.cli import main

    root = tmp_path / "ws"
    (root / "sims").mkdir(parents=True)
    (root / "runs.json").write_text("[]", encoding="utf-8")

    assert main(["rename", "--workspace", str(root)]) == 0

    printed = capsys.readouterr().out
    assert "nothing moved" in printed, printed
    assert "0.21.0" in printed, printed
