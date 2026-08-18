"""Tier 1: the refusals of the maintainer scripts under ``scripts/``.

Pipeline role: quality gate on the tools a maintainer runs by hand.
These are not the package, so their defects reach one person rather than
every caller; but that person is running them to decide what a licensed
day does, and a tool that reports success on a run that measured nothing
is the failure this repository has the most incidents about.

WHY THIS MODULE EXISTS. Two behaviour fixes shipped on 2026-08-18 with no
test of any kind, and the review pass measured that reverting either was
invisible to tier 1:

* ``restate_26123_notes.py``'s reach floor read
  ``if seen and restated and restated + 1 != seen``, which short-circuits
  at zero recognised rows. Zero is exactly the post-restatement shape the
  floor was written from, so the floor could not fire on the run that
  produced it: the script printed "369 rows encountered, 0 recognised, 0
  REFUSED" and exited 0.
* ``measure_edition_page_delta.py``'s ``--pages`` parsed with a bare
  ``int()``, so ``--pages 273`` raised a ValueError traceback about an
  empty string rather than saying what the form is.

The repository already tests scripts of this kind (`test_plan_checker`,
`test_ci_state`, `test_write_attestation`), so the absence was a gap
rather than a policy.

Nothing here opens a manual or a licensed anything: every case refuses
before any file is read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


@pytest.mark.parametrize(
    ("pages", "expected", "why"),
    [
        ("273", "FIRST-LAST", "one number is not a range, and int('') was the old answer"),
        ("a-b", "FIRST-LAST", "letters are not page numbers"),
        ("283-", "FIRST-LAST", "a missing second half"),
        ("383-283", "runs backwards", "a range whose first page is after its last"),
    ],
)
def test_the_page_range_flag_refuses_a_malformed_span(pages, expected, why, tmp_path, capsys):
    """A usage error says what the form is, and exits 2.

    `parser.error` rather than `SystemExit("...")`, because the sibling
    `pyfs-manual` refuses this shape that way precisely to keep the usage
    code at 2, and the first version of this repair exited 1, which is
    what this tool returns for a real measurement.

    THE MESSAGE IS READ FROM STDERR, and the first version of this test
    read it from `str(refused.value)`, which for a `parser.error` is the
    string `"2"`. The message assertion was therefore always False and
    was rescued by `or expected`, a non-empty literal in every row, so
    the whole clause was a tautology: this test verified an exit code and
    nothing about the wording, while its own docstring says the defect it
    guards is a WORDING defect. That is the degenerate assertion this
    repository has a record about, written by the person who wrote the
    record.
    """
    import measure_edition_page_delta

    manifest = tmp_path / "editions.yaml"
    manifest.write_text("editions: []\n", encoding="utf-8")

    with pytest.raises(SystemExit) as refused:
        measure_edition_page_delta.main(
            [
                "--editions",
                str(manifest),
                "--from",
                "26.122",
                "--to",
                "26.123",
                "--pages",
                pages,
            ]
        )
    assert refused.value.code == 2, (
        f"a usage error exited {refused.value.code}; the rest of this package's "
        "command lines return 2 for one, and 1 means a real result here"
    )
    printed = capsys.readouterr().err
    assert expected in printed, f"{why}; the refusal printed: {printed!r}"
    assert pages in printed, (
        "the refusal does not echo what the reader actually typed, so they cannot "
        f"see which of their arguments it is about: {printed!r}"
    )


def test_the_restatement_floor_fires_on_a_run_that_recognised_nothing():
    """The shape the floor was written from, which it could not judge.

    The floor exists because an earlier version of the script reported
    "0 recognised, 0 REFUSED" and exit 0 on a tree where every note had
    already been restated, which is indistinguishable from a run whose
    anchor stopped matching. Writing it as
    ``seen and restated and restated + 1 != seen`` made zero the one
    value it could not see.

    THIS ASSERTS THE SOURCE, and the first version of this docstring
    said it drove the predicate. It does not: the floor is inline in
    `main` and the script needs two licensed manuals to reach it, so
    what is checked is that the expression has not returned to the
    short-circuiting form. That is an anchor, not a behavioural test,
    and calling it one is the overclaim this repository has a record
    about. Lifting the floor into a named predicate the script calls
    and this test imports is registered rather than done.
    """
    import restate_26123_notes

    # The predicate as the module states it, read from the source so this
    # test fails if the expression moves rather than silently passing on
    # a copy of it.
    source = (REPO_ROOT / "scripts" / "restate_26123_notes.py").read_text(encoding="utf-8")
    assert "if seen and restated + 1 != seen:" in source, (
        "the reach floor is not the expression this test was written for; if it "
        "moved, move this assertion with it, and check the new one can fire at "
        "zero recognised rows"
    )
    assert "if seen and restated and" not in source, (
        "the reach floor short-circuits at zero recognised rows again, which is "
        "the post-restatement shape it was written from and the one shape it "
        "exists to refuse"
    )
    assert restate_26123_notes.BUILD == "26.123"
