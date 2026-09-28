"""A recorded skip is said on stderr by the CLI (PFS-2031.16, PFS-2031.19)."""

import json

from pyflightstream._cli import cli_entrypoint
from pyflightstream.run.cli import _report_skips
from pyflightstream.workspace import CampaignWorkspace


def _cli_report(tmp_path, argv):
    workspace = CampaignWorkspace(tmp_path)
    out = workspace.products_dir("m")
    out.mkdir(parents=True)
    (out / "products.json").write_text(
        json.dumps({"skipped": {"1001": "no polar under sideslip"}}), encoding="utf-8"
    )

    # The same wrapper `pyfs-matrix` main carries: it always sets the policy.
    @cli_entrypoint
    def main(argv):
        return _report_skips(workspace, ["m"])

    return main(argv), out / "products.json"


def test_a_recorded_skip_is_counted_on_stderr_by_default(tmp_path, capsys):
    count, manifest = _cli_report(tmp_path, ["post", "m"])
    assert count == 1
    err = capsys.readouterr().err
    assert f"1 recorded skip(s) of m; reasons in {manifest}" in err
    assert "no polar under sideslip" not in err, "detail stays quiet by default (0.29)"


def test_a_recorded_skip_is_printed_with_its_reason_under_pproc_warnings(tmp_path, capsys):
    count, _ = _cli_report(tmp_path, ["post", "m", "--pproc-warnings"])
    assert count == 1
    err = capsys.readouterr().err
    assert "skipped simulation 1001 of m: no polar under sideslip" in err
