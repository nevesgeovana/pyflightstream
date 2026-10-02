"""FR-368: the cumulative log of a job cut into each point's own log (0.35.0).

Driven over the compacted transcripts of the licensed re-initialisation probes
of 2026-10-02 (build 8172026, `fixtures/batch0350/logs/PROVENANCE.md`): each
cumulative log against the logs of the same points run alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.results.log import (
    RESTART_MARKER,
    imported_trailing_edges,
    parse_log_times,
    parse_residual_history,
    point_log_text,
    split_job_log,
)

LOGS = Path(__file__).parent / "fixtures" / "batch0350" / "logs"
#: The OPEN echo: printed where a polar's model is opened, so a later point of
#: the polar carries it only through its polar's preamble. (The process banner
#: with the build is printed once per JOB, MEASURED in C2b and E2: a point of a
#: later polar does not carry it, and nothing of the package reads it off a log.)
OPEN_ECHO = "Simulation file opened from following location"

#: Each cumulative log: its fresh point logs in job order, and the order of the
#: first point of each point's polar (a re-initialisation stays in the polar; a
#: reopened model or a mesh change starts a new one).
CASES = {
    "A2.cumulative.txt": (("fresh_9811_AL+000.txt", 1), ("fresh_9812_AL+020.txt", 1)),
    "C2b.cumulative.txt": (
        ("fresh_9811_AL+000.txt", 1),
        ("fresh_9821_J+150.txt", 2),
        ("fresh_9821_J+190.txt", 2),
    ),
    "E2.cumulative.txt": (
        ("fresh_9811_AL+000.txt", 1),
        ("fresh_9841_AL+000.txt", 2),
        ("fresh_9841_AL+040.txt", 2),
    ),
}


def _read(name: str) -> str:
    return (LOGS / name).read_text(encoding="utf-8")


def _evidence(text: str) -> tuple[object, ...]:
    history = parse_residual_history(text)
    return (
        [(s.iteration, s.velocity_residual, s.pressure_residual) for s in history],
        parse_log_times(text).time_steps,
        imported_trailing_edges(text),
        OPEN_ECHO in text,
    )


@pytest.mark.parametrize("cumulative", sorted(CASES))
def test_p0350_log_fr368_segments_and_slices_match_the_fresh_points(cumulative):
    """P0350-COLLECT-LOG-SLICE (FR-368): every slice reads as its point run alone."""
    requirement = "FR-368"
    text = _read(cumulative)
    segments = split_job_log(text)
    assert len(segments) == len(CASES[cumulative]), requirement
    assert [s.complete for s in segments] == [True] * (len(segments) - 1) + [False]
    for segment, (fresh, start) in zip(segments, CASES[cumulative], strict=True):
        sliced = point_log_text(text, segment, polar_start=segments[start - 1])
        assert RESTART_MARKER not in sliced, requirement
        assert _evidence(sliced) == _evidence(_read(fresh)), (cumulative, fresh)


@pytest.mark.parametrize("cumulative", sorted(CASES))
def test_p0350_log_fr368_the_preamble_is_what_a_later_point_needs(cumulative):
    """P0350-COLLECT-LOG-SLICE (FR-368), the mutant: a slice without its polar's preamble.

    The second point of each log's last polar runs after a re-initialisation, so
    its own segment does not print the OPEN echo; cut without the preamble it
    loses what its fresh log carries, which is what the preamble is for. (None of
    these probe logs prints a wake-edge import line, whose count rides in the same
    preamble.)
    """
    requirement = "FR-368"
    text = _read(cumulative)
    segments = split_job_log(text)
    last = segments[-1]
    start = segments[CASES[cumulative][-1][1] - 1]
    assert start.index != last.index
    mutant = point_log_text(text, last, polar_start=last)
    assert OPEN_ECHO not in mutant, requirement
    assert _evidence(mutant) != _evidence(_read(CASES[cumulative][-1][0])), requirement
    kept = point_log_text(text, last, polar_start=start)
    assert OPEN_ECHO in kept, requirement


def test_p0350_log_fr368_idempotent_and_incomplete(tmp_path):
    """P0350-COLLECT-LOG-SLICE (FR-368): the same bytes twice; a running job's last segment."""
    requirement = "FR-368"
    text = _read("C2b.cumulative.txt")
    first = split_job_log(text)
    assert split_job_log(text) == first, requirement
    slices = [point_log_text(text, s, polar_start=first[0]) for s in first]
    assert slices == [point_log_text(text, s, polar_start=first[0]) for s in first]
    # A job still running: the log so far ends inside its second point, and that
    # segment has no later marker, so it is not complete.
    cut = text.index(RESTART_MARKER) + len(RESTART_MARKER)
    running = text[: cut + (len(text) - cut) // 3]
    segments = split_job_log(running)
    assert [s.complete for s in segments] == [True, False], requirement


def test_p0350_log_fr368_nul_bytes_and_empty_text():
    """The marker is found through the NUL bytes a hidden-mode log carries; no text, no segment."""
    requirement = "FR-368"
    text = "head\x00\nrun one\nSolution cleared.\x00 Initialization removed.\x00\nrun two\n"
    assert split_job_log("") == [], requirement
    assert len(split_job_log(text)) == 2, requirement
    marked = "a\n" + RESTART_MARKER + "\x00\nb\n"
    segments = split_job_log(marked)
    assert len(segments) == 2 and segments[0].complete and not segments[1].complete
    assert point_log_text(marked, segments[1], polar_start=segments[1]) == "b\n"
