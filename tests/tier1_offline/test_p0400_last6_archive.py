"""Every product rebuild uses the same opt-in archive policy."""

from types import SimpleNamespace

import pytest

from pyflightstream import workspace as workspace_module
from pyflightstream.run import cli, collect

pytestmark = pytest.mark.requirement("P0400-LAST6-ARCHIVE")


@pytest.mark.parametrize("archive", [False, True])
def test_p0400_last6_collect_archives_only_when_requested(tmp_path, monkeypatch, archive):
    seen = []
    report = SimpleNamespace(
        lines=lambda: [],
        failed_lines=lambda: [],
        collected=[],
        failed=[],
        outstanding=0,
        unknown=[],
    )

    def gathered(workspace, *, post_matrix, **kwargs):
        post_matrix(workspace, None)
        return report

    monkeypatch.setattr(collect, "collect_and_post", gathered)
    monkeypatch.setattr(
        workspace_module, "post_stages", lambda: [lambda ws, **kwargs: seen.append(kwargs)]
    )
    argv = ["collect", "--workspace", str(tmp_path)] + (["--archive"] if archive else [])
    assert cli.main(argv) == 0
    assert seen[0]["archive"] is archive, "P0400-LAST6-ARCHIVE"


def test_p0400_last6_refused_confirmation_names_the_overwrite_consequence(
    tmp_path, monkeypatch, capsys
):
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    monkeypatch.setattr(cli, "_confirmed_destruction", lambda yes: False)
    assert cli.main(["post", "--workspace", str(workspace.root), "--force-overwrite"]) == 2
    refusal = capsys.readouterr().err
    assert "without an archive" in refusal, "P0400-LAST6-ARCHIVE-REFUSAL"
    assert "--archive" in refusal


@pytest.mark.parametrize("archive", [False, True])
def test_p0400_last6_regeneration_archives_only_when_requested(tmp_path, monkeypatch, archive):
    from pyflightstream.workspace import storage
    from tests.tier1_offline.test_goal035_storage import _shared_product_workspace

    workspace = _shared_product_workspace(tmp_path, "regenerate")
    seen = []
    monkeypatch.setattr(storage, "post_stages", lambda: [lambda ws, **kwargs: seen.append(kwargs)])
    storage.delete_sims(
        workspace.root,
        ["3001"],
        matrix_products="regenerate",
        apply=True,
        **({"archive": True} if archive else {}),
    )
    assert seen[0]["archive"] is archive, "P0400-LAST6-REGENERATE-ARCHIVE"
