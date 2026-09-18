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
    plain_files, _, plain = write_superfiles(_drafts(tmp_path / "a"), target=_maker(tmp_path / "a"))
    legacy_files, _, legacy = write_superfiles(
        _drafts(tmp_path / "b"), target=_maker(tmp_path / "b"), fmt="legacy_polar"
    )
    assert plain == legacy, (plain, legacy)

    # THE RETURNED TUPLE IS NOT THE FILE, and comparing it was the whole of this
    # test until the QA lens of REL-0230 scored a mutant against it: the tuple is
    # built BEFORE the format branch, so truncating `_write_legacy_polar` to one
    # column left the assertion above green. A legacy file dropping 627 of 628
    # columns shipped with this test passing.
    #
    # So the columns are counted IN THE BYTES each writer produced. The two
    # formats spell a header differently by design, which is why the assertion
    # is on the COUNT of the declared columns appearing rather than on equal
    # text: what must not differ is how much of the workspace each file carries.
    assert plain_files and legacy_files, (plain_files, legacy_files)
    for written in (plain_files[0], legacy_files[0]):
        text = written.read_text(encoding="utf-8")
        missing = [name for name in plain if name not in text]
        assert not missing, (
            f"{written.name} carries {len(plain) - len(missing)} of {len(plain)} columns; "
            f"the first few missing are {missing[:5]}"
        )


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


def test_a_pproc_can_ask_for_the_legacy_format(tmp_path):
    """ITEM 7 THROUGH THE PPROC, which is the only way a user reaches it.

    `SUPERFILE_FORMATS` declared two formats and `write_superfiles` took `fmt`,
    and the ONE production call omitted it -- so every campaign got `csv` and
    `legacy_polar` was a constant nobody could select. That answers her question
    ("como configuro para o super file tambem sair em formato custom?") with a
    format she has no way to configure.

    It is a FIELD on `[products]` rather than a flag, because the neighbouring
    `custom_polar_format` is already a `[products]` key and a user choosing how
    her products are written should find both in one table.
    """
    from pyflightstream.cases import ProductsSpec

    assert ProductsSpec().superfile_format == "csv", "the default may not move"
    assert ProductsSpec(superfile_format="legacy_polar").superfile_format == "legacy_polar"


def test_a_format_the_package_does_not_offer_is_refused_at_the_pproc(tmp_path):
    """Refused where it is WRITTEN, not where it is used.

    The writer already refuses an unknown format naming the ones that exist, and
    that refusal fires after a campaign has been planned and a seat possibly
    spent. A typo in a pproc file is a typo the loader can see.
    """
    import pytest as _pytest
    from pydantic import ValidationError

    from pyflightstream.cases import ProductsSpec

    with _pytest.raises(ValidationError) as caught:
        ProductsSpec(superfile_format="tecplot")
    message = str(caught.value)
    assert "tecplot" in message, message
    for name in SUPERFILE_FORMATS:
        assert name in message, (name, message)


def test_a_pproc_asking_for_the_legacy_format_gets_it_from_the_post_stage(tmp_path):
    """ITEM 7 END TO END, which is the only claim that answers her question.

    The two tests above assert the FIELD and the writer. Neither runs the stage,
    and the stage was exactly what omitted the argument -- so both would pass
    over a release where `legacy_polar` is still unreachable. This runs
    `write_campaign_products` over a recorded workspace whose pproc asks for it,
    and looks at the bytes.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    for code in ("p001", "p002"):
        path = workspace.inputs_dir / "pproc" / f"{code}.toml"
        path.write_text(
            path.read_text(encoding="utf-8") + '\n[products]\nsuperfile_format = "legacy_polar"\n',
            encoding="utf-8",
        )

    written = _post(workspace)
    supers = [Path(p) for p in written if Path(p).name.startswith("SUPER-")]
    assert supers, sorted(Path(p).name for p in written)

    header = supers[0].read_text(encoding="utf-8").splitlines()[0]
    assert "," not in header, (
        f"the pproc asked for the legacy format and the stage wrote a CSV header: {header[:120]}"
    )
