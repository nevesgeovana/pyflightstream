"""The post stage says what it could not read, and its manifest survives its own crash.

- PO-06. `matrix_rows` returns `{}` for a matrix it cannot read, in silence, and
  every post-only choice then falls back to the run records: the edit to the
  window does nothing, the rotor tables leave the disk and the manifest, and the
  stage prints "N product(s) written", exit 0.
- PO-05. The stage resolved the pproc the RECORD names while the row's PPROC cell
  was in scope and used only to stamp the super file: point the row at another
  pproc, post, and everything still came from the old one.
- MT-08. `products.json` is written ONCE, last, after every existing product has
  been moved to `archive/`. A rebuild that dies on anything but a `ProductError`
  left the PREVIOUS manifest naming files the archiver had just moved away: the
  one mechanism found for a manifest that claims a file which is not on disk.
- MT-02. The sections report sat inside `if drafts:`, and a windowed unsteady
  campaign produces no super file draft, so it never got one.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

import pyflightstream.post.products as products
from tests.tier1_offline.test_post_superfile import _MATRIX, _post, _workspace


def _said(workspace) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    return [str(w.message) for w in caught]


def test_a_matrix_that_cannot_be_read_is_said_and_not_swallowed(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.root / "matriz.fs").write_text(
        "POL | RUN\nthis is not | a matrix | at all\n", "utf-8"
    )
    said = [message for message in _said(workspace) if "matriz.fs" in message]
    assert len(said) == 1, said
    assert "run records" in said[0]


def test_a_matrix_that_is_not_where_the_records_say_is_said_too(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace.root / "matriz.fs").unlink()
    said = [message for message in _said(workspace) if "matriz.fs" in message]
    assert len(said) == 1, said


def test_the_products_follow_the_pproc_the_row_names_today(tmp_path):
    workspace = _workspace(tmp_path)
    # The run recorded p001 for simulation 6001. The row is pointed at p002, whose
    # one group is named differently, and only `post` is run.
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text('[groups]\nONLY = "W"\n', "utf-8")
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6001"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.replace("| p001 |", "| p002 |")), encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path).name for path in _post(workspace)]
    assert any(name.startswith("P6001-") and name.endswith("_ONLY.csv") for name in written), (
        written
    )
    assert not any(name.startswith("P6001-") and "_g01" in name for name in written), written
    said = [str(w.message) for w in caught if "p002" in str(w.message) and "p001" in str(w.message)]
    assert len(said) == 1, [str(w.message) for w in caught]


def test_a_rebuild_that_dies_leaves_a_manifest_of_what_is_on_disk(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    _post(workspace)
    out = workspace.root / "post" / "matriz"
    first = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert first["products"], "the fixture must have products to disown"

    def _dies(*_args, **_kwargs):
        raise OSError("the disk went away")  # NOT a ProductError: nothing catches it

    monkeypatch.setattr(products, "write_superfiles", _dies)
    with pytest.raises(OSError):
        _post(workspace)
    after = json.loads((out / "products.json").read_text(encoding="utf-8"))
    assert after.get("complete") is False, after.keys()
    assert "the disk went away" in str(after.get("interrupted"))
    for relative in after["products"]:
        assert (out / relative).is_file(), f"the manifest claims {relative} and it is not on disk"
