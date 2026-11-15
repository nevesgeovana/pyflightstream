"""Tier 1, v0.23.0 item 7: the polar files can be written in the legacy polar format.

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

THE COLUMN SET IS THE SAME IN BOTH. That is the property worth asserting: a
second FORMAT that quietly carried a different SET of columns would break the
file's claim while looking like a formatting option.

0.58.0: the super file is retired. `[products] superfile_format` reads as
`polar_format` and selects the format of the FAM and group files (design page of
the post outputs, section 2.3). The writer-level cases that built
draft objects went with the writer; the format is now chosen only
through the pproc and reaches the bytes only through the post stage, so the
cases below run that stage.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pyflightstream.cases import SUPERFILE_FORMATS


def test_both_formats_are_offered_and_named():
    assert "csv" in SUPERFILE_FORMATS, SUPERFILE_FORMATS
    assert "legacy_polar" in SUPERFILE_FORMATS, SUPERFILE_FORMATS


def test_a_pproc_can_ask_for_the_legacy_format():
    """ITEM 7 THROUGH THE PPROC, which is the only way a user reaches it.

    The field is `[products] polar_format` now; the former key `superfile_format`
    is read as it, with a warning (tested in test_p0580_l2_pproc_keys). The
    default is the format she already reads.
    """
    from pyflightstream.cases import ProductsSpec

    assert ProductsSpec().polar_format == "csv", "the default may not move"
    assert ProductsSpec(polar_format="legacy_polar").polar_format == "legacy_polar"


def test_a_format_the_package_does_not_offer_is_refused_at_the_pproc():
    """Refused where it is WRITTEN, not where it is used.

    A typo in a pproc file is a typo the loader can see, before a campaign has
    been planned and a seat possibly spent.
    """
    from pydantic import ValidationError

    from pyflightstream.cases import ProductsSpec

    with pytest.raises(ValidationError) as caught:
        ProductsSpec(polar_format="tecplot")
    message = str(caught.value)
    assert "tecplot" in message, message
    for name in SUPERFILE_FORMATS:
        assert name in message, (name, message)


def _posted(tmp_path, polar_format: str | None) -> list[Path]:
    """Post the recorded two-polar campaign with the pproc stating (or not) a polar format."""
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    if polar_format is not None:
        for code in ("p001", "p002"):
            path = workspace.inputs_dir / "pproc" / f"{code}.toml"
            path.write_text(
                path.read_text(encoding="utf-8")
                + f'\n[products]\npolar_format = "{polar_format}"\n',
                encoding="utf-8",
            )
    return [Path(p) for p in _post(workspace)]


def _polar_files(written: list[Path]) -> list[Path]:
    return [
        path for path in written if path.name.startswith(("FAM-", "P60")) and path.suffix == ".csv"
    ]


@pytest.mark.parametrize(
    ("stated", "commas"), [(None, True), ("csv", True), ("legacy_polar", False)]
)
def test_a_pproc_asking_for_a_format_gets_it_from_the_post_stage(tmp_path, stated, commas):
    """ITEM 7 END TO END, which is the only claim that answers her question.

    The field tests above assert the FIELD; the stage was exactly what once
    omitted the argument, so a release where `legacy_polar` is unreachable would
    pass them. This runs the stage over a recorded workspace and looks at the
    bytes of every FAM and group file. A pproc that CHOSE `csv` and one that said
    nothing both write the csv header.
    """
    files = _polar_files(_posted(tmp_path, stated))
    assert files, "the stage wrote no polar file"
    for path in files:
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert ("," in header) is commas, (path.name, header[:120])


def test_the_two_formats_carry_the_same_columns(tmp_path):
    """The property that makes this a format and not a different product.

    The two formats spell a header differently by design, so the columns are
    counted IN THE BYTES each file holds: the legacy file must carry every column
    name of the csv file of the same name, and the same number of rows.
    """
    plain = {p.name: p for p in _polar_files(_posted(tmp_path / "a", "csv"))}
    legacy = {p.name: p for p in _polar_files(_posted(tmp_path / "b", "legacy_polar"))}
    assert plain and plain.keys() == legacy.keys(), (sorted(plain), sorted(legacy))
    for name, path in plain.items():
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        columns, body = rows[0], rows[1:]
        text = legacy[name].read_text(encoding="utf-8")
        missing = [column for column in columns if column not in text]
        assert not missing, (
            f"{name} in the legacy format carries {len(columns) - len(missing)} of "
            f"{len(columns)} columns; the first few missing are {missing[:5]}"
        )
        # One header line, then the rows, in the legacy file as in the csv one.
        assert len(text.splitlines()) == len(body) + 1, (name, len(text.splitlines()), len(body))
