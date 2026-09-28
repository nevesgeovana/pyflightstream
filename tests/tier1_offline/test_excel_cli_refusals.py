"""Expected input refusals are CLI results, while library calls keep typed errors."""

import json

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.workspace import excel
from pyflightstream.workspace.excel_sync import ExcelSyncError


def test_existing_workbook_is_a_cli_refusal_not_a_traceback(tmp_path, capsys):
    output = tmp_path / "existing.xlsx"
    original = b"original workbook bytes"
    output.write_bytes(original)
    assert excel.main(["create", str(output), "--workspace", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "existing files are never overwritten" in captured.err
    assert "Command failed" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_bytes() == original
    with pytest.raises(ExcelSyncError, match="never overwritten"):
        excel.create_workbook(output, workspace=tmp_path)


def test_missing_workbook_is_a_named_cli_filesystem_refusal(tmp_path, capsys):
    path = tmp_path / "missing.xlsx"
    assert excel.main(["check", str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing.xlsx" in captured.err
    assert "Excel command not completed" in captured.err
    assert not path.exists()


@pytest.mark.parametrize("action", ["apply", "cancel"])
def test_consumed_preview_is_refused_without_rewriting_it(action, tmp_path, capsys):
    batch = tmp_path / "preview.json"
    original = json.dumps({"schema": 1, "status": "cancelled"}).encode()
    batch.write_bytes(original)
    assert excel.main([action, str(batch)]) == 2
    assert "create a new preview" in capsys.readouterr().err
    assert batch.read_bytes() == original


def test_shared_package_refusal_is_reported_by_excel_cli(monkeypatch, tmp_path, capsys):
    def refused(*args, **kwargs):
        raise PyflightstreamError("Install the requested optional dependency")

    monkeypatch.setattr(excel, "create_workbook", refused)
    assert excel.main(["create", str(tmp_path / "new.xlsx"), "--workspace", str(tmp_path)]) == 2
    assert "Install the requested optional dependency" in capsys.readouterr().err
    assert not (tmp_path / "new.xlsx").exists()
