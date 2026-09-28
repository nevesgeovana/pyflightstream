"""Post warnings stay in durable records even when terminal reporting is disabled."""

import json
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.post import products
from pyflightstream.workspace import CampaignWorkspace


@pytest.mark.parametrize("obligation", ["stable_categories", "post_log_json"])
def test_post_log_classifies_each_record_without_losing_detail(tmp_path, monkeypatch, obligation):
    # GOAL033:logging:checks:stable_categories
    # GOAL033:logging:checks:post_log_json
    workspace = CampaignWorkspace(tmp_path)

    expected = {
        "section-layout": "recorded layout has no blocks",
        "reference-frame": "unknown frame",
        "convergence": "residual unavailable",
        "translation": "vtk variable unavailable",
        "missing-data": "missing input",
        "configuration": "configuration incomplete",
        "postprocessing": "unexpected numerical result",
    }

    def stage(*_args, **_kwargs):
        for message in expected.values():
            warn(f"point=run/one product=control: {message}", PyflightstreamWarning, stacklevel=1)
        return []

    monkeypatch.setattr(products, "_campaign_products", stage)
    with warnings.catch_warnings(record=True):
        products.write_campaign_products(workspace, matrix_stem="matrix")
    document = json.loads((workspace.products_dir("matrix") / "post.log.json").read_text())
    assert len(document["records"]) == len(expected)
    if obligation == "stable_categories":
        assert {record["category"] for record in document["records"]} == set(expected)
    else:
        for record, message in zip(document["records"], expected.values(), strict=True):
            assert record["severity"] == "warning"
            assert record["point"] == "run/one"
            assert message in record["message"]


@pytest.mark.parametrize(
    "enabled", [False, True], ids=["warnings_default_off", "pproc_warnings_opt_in"]
)
def test_cli_quiet_default_retains_all_warnings_and_opt_in_groups(
    tmp_path, monkeypatch, capsys, enabled
):
    # GOAL033:logging:checks:warnings_default_off
    # GOAL033:logging:checks:pproc_warnings_opt_in
    from pyflightstream._cli import cli_entrypoint

    messages = {
        "section-layout": "layout mismatch",
        "reference-frame": "unknown frame",
        "convergence": "residual unavailable",
        "translation": "vtk variable unavailable",
        "missing-data": "missing input",
        "configuration": "configuration incomplete",
        "postprocessing": "unexpected numerical result",
    }

    def stage(*_args, **_kwargs):
        for message in messages.values():
            warn(f"point=run/one product=control: {message}", PyflightstreamWarning)
        return []

    monkeypatch.setattr(products, "_campaign_products", stage)
    workspace = CampaignWorkspace(tmp_path)

    @cli_entrypoint
    def command(argv):
        products.write_campaign_products(workspace, matrix_stem="matrix")
        return 0

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert command(["--pproc-warnings"] if enabled else []) == 0
    assert not caught
    terminal = capsys.readouterr()
    for category, message in messages.items():
        if enabled:
            assert f"pproc warning [{category}]: 1" in terminal.err
        else:
            assert "pproc warning" not in terminal.err and message not in terminal.err
    data = json.loads((workspace.products_dir("matrix") / "post.log.json").read_text())
    assert len(data["records"]) == len(messages)
    assert {record["category"] for record in data["records"]} == set(messages)


def test_diagnostics_reads_complete_record_without_mutating_any_file(tmp_path):
    # GOAL033:capability_ids:items:G59
    # GOAL033:logging:checks:markdown_diagnostics
    from pyflightstream.post.diagnostics import render_post_diagnostics

    log = tmp_path / "post.log.json"
    document = {
        "time": "2026-09-27T12:00:00Z",
        "version": "test",
        "records": [
            {
                "point": "point-a",
                "product": "sections",
                "message": "layout mismatch",
                "remedy": "restore the recorded layout",
            },
            {"point": "point-b", "product": "loads", "message": "missing input"},
        ],
    }
    log.write_text(json.dumps(document))
    product = tmp_path / "answer.csv"
    product.write_bytes(b"x,y\n1,2\n")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    report = render_post_diagnostics([log, tmp_path / "missing.json"])
    assert report.startswith("# Recorded postprocessing diagnostics\n\n")
    assert f"## {log}" in report
    assert "2026-09-27T12:00:00Z" in report
    assert "layout mismatch" in report and "missing input" in report
    assert "restore the recorded layout" in report
    assert "No recorded postprocessing log" in report
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}


def test_cli_diagnostics_does_not_invoke_stages(tmp_path, monkeypatch, capsys):
    # GOAL033:logging:checks:diagnostics_no_product_mutation
    from pyflightstream.run.cli import main
    from tests.tier1_offline.test_post_log import _post_workspace

    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    folder = workspace.products_dir(None)
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "post.log.json"
    log.write_text(
        json.dumps(
            {
                "time": "recorded-test-time",
                "records": [{"point": "point-a", "product": "loads", "message": "missing data"}],
            }
        )
    )

    def forbidden():
        raise AssertionError("diagnostics must not ask for product stages")

    monkeypatch.setattr("pyflightstream.workspace.post_stages", forbidden)
    before = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in workspace.root.rglob("*") if p.is_file()
    }
    assert main(["post", "--workspace", str(workspace.root), "--diagnostics"]) == 0
    output = capsys.readouterr()
    assert "recorded-test-time" in output.out
    assert "missing data" in output.out
    assert "Ass: geoversegoddes" not in output.out
    after = {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in workspace.root.rglob("*") if p.is_file()
    }
    assert before == after
