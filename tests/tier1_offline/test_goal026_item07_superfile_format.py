"""Tier 1, v0.23.0 item 7: the super file can be written in the legacy polar format.

THE OWNER'S QUESTION, 2026-09-17, and it is the message that opened this whole
release:

    "Como configuro para o super file tambem sair em formato custom? Além
    disso, o super file tá saindo com campos vazios e isso quebra meu leitor de
    csv."

The second half became item 4 and shipped. This is the first half.

THE FORMAT IS SELECTED, NOT GUESSED. A writer that decided the format from the
file name or from what the workspace happened to contain would be a writer
nobody can predict; the pproc says which, and the default is the format she
already reads so nothing changes under an existing workspace.

THE COLUMN SET IS THE SAME IN BOTH. That is the property worth asserting: the
super file's whole claim is that it carries everything the workspace knows
about a simulation, and a second FORMAT that quietly carried a different SET
would break that claim while looking like a formatting option.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.superfile import SUPERFILE_FORMATS, SuperfileDraft, write_superfiles


def _drafts(tmp_path):
    return [
        SuperfileDraft(
            path=tmp_path / "SUPER-0001-M150_PUSHER.csv",
            rows=[{"POLAR": "0001", "ALPHA": -2.0, "CT_PUSHER": 0.12}],
            entry={"runs": ["camp/sim_1/P"]},
        )
    ]


def test_both_formats_are_offered_and_named():
    assert "csv" in SUPERFILE_FORMATS, SUPERFILE_FORMATS
    assert "legacy_polar" in SUPERFILE_FORMATS, SUPERFILE_FORMATS


def test_the_default_is_the_format_she_already_reads(tmp_path):
    """Adding a format may not change what an existing workspace writes."""
    written, _, columns = write_superfiles(_drafts(tmp_path), target=lambda path: path)
    text = written[0].read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("POLAR,"), text.splitlines()[0]
    assert "ALPHA" in columns


def test_the_legacy_format_is_written_when_it_is_asked_for(tmp_path):
    written, _, _ = write_superfiles(
        _drafts(tmp_path), target=lambda path: path, fmt="legacy_polar"
    )
    text = written[0].read_text(encoding="utf-8")
    assert "," not in text.splitlines()[0], text.splitlines()[0]


def test_the_two_formats_carry_the_same_columns(tmp_path):
    """The property that makes this a format and not a different product.

    The super file's whole claim is that it carries everything the workspace
    knows about that simulation. A second format quietly carrying a different
    SET would break that claim while looking like a formatting option.
    """
    _, _, plain = write_superfiles(_drafts(tmp_path / "a"), target=_maker(tmp_path / "a"))
    _, _, legacy = write_superfiles(
        _drafts(tmp_path / "b"), target=_maker(tmp_path / "b"), fmt="legacy_polar"
    )
    assert plain == legacy, (plain, legacy)


def _maker(root):
    def target(path):
        root.mkdir(parents=True, exist_ok=True)
        return root / path.name

    return target


def test_a_format_nobody_offers_is_refused_naming_the_ones_that_exist(tmp_path):
    """Could-not-understand is never a silent fallback to the default."""
    with pytest.raises(ValueError) as caught:
        write_superfiles(_drafts(tmp_path), target=lambda path: path, fmt="tecplot")
    message = str(caught.value)
    assert "tecplot" in message
    for name in SUPERFILE_FORMATS:
        assert name in message, (name, message)
