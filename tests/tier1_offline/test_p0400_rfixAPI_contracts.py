"""Exercise post/build help, FSI external, missing area and geometry row refusals."""
# ruff: noqa: N999 - the assigned lane name is rfixAPI.

from argparse import Namespace
from inspect import Parameter, signature
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases.sixdof import SixDofCustomForce, SixDofFree
from pyflightstream.farfield import spurious_diagnostic, to_counts
from pyflightstream.fsi.cli import _build_parser as fsi_parser
from pyflightstream.run._cli_geometry import _print_rows, alias_warning
from pyflightstream.run._cli_parsers import _build_parser as matrix_parser
from pyflightstream.workspace._geometry_build import GeometryBuildPlan
from pyflightstream.workspace.cli import _build_parser as workspace_parser

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.requirement("P0400-RFIXAPI")


def help_text(parser, argv, capsys) -> str:
    with pytest.raises(SystemExit) as caught:
        parser.parse_args([*argv, "--help"])
    assert caught.value.code == 0
    return " ".join(capsys.readouterr().out.split())


@pytest.mark.requirement("FR-397")
def test_p0400_api001_post_and_build_help(capsys) -> None:
    post = help_text(matrix_parser(), ["post"], capsys)
    assert post.count("By default, rebuilds overwrite products in place without an archive.") == 1
    assert "deprecated" not in post.lower()
    assert "adds a confirmation before rebuilding" in post
    build = help_text(workspace_parser(), ["geometry", "build"], capsys)
    assert "Unlike post, a build refuses to replace outputs unless asked" in build
    assert "outputs are inputs of runs" in build
    assert "The deprecated `--force-overwrite`" not in (REPO / "docs/pproc-artifact.md").read_text()
    upgrading = (REPO / "docs/upgrading.md").read_text().split("## 0.39.0")[0]
    assert (
        upgrading.count("By default, rebuilds overwrite products in place without an archive.") == 1
    )


@pytest.mark.requirement("FR-477")
@pytest.mark.parametrize("verb", ["refine", "audit-mesh", "inventory", "degenerate"])
def test_p0400_api002_alias_deadline(verb) -> None:
    from pyflightstream._deprecations import DEPRECATIONS

    warning = alias_warning(verb)
    assert "removed in v1.0.0" in warning
    assert f"pyfs-matrix {verb}" in warning
    assert any(entry.subject == f"pyfs-matrix {verb}" for entry in DEPRECATIONS)
    for page in ("docs/geometry.md", "docs/upgrading.md"):
        assert "removed in v1.0.0" in (REPO / page).read_text()


@pytest.mark.requirement("FR-457")
@pytest.mark.parametrize("function,args", [(to_counts, (1.0,)), (spurious_diagnostic, (2.0, 1.0))])
def test_p0400_api003_missing_reference_area(function, args) -> None:
    with pytest.raises((TypeError, ValueError)) as caught:
        function(*args, rho_inf=1.2, v_inf=20.0)
    assert "s_ref" in str(caught.value)
    assert "reference area" in str(caught.value)
    assert "m2" in str(caught.value)
    assert signature(function).parameters["s_ref"].default is Parameter.empty
    assert "no safe default" in (REPO / "docs/upgrading.md").read_text()


@pytest.mark.requirement("FR-462")
def test_p0400_api004_external_accepts_only_out(capsys) -> None:
    parser = fsi_parser()
    assert "--dir" not in help_text(parser, ["external"], capsys)
    assert parser.parse_args(["external", "--out", "point"]).dir == Path("point")
    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["external", "--dir", "point"])
    assert caught.value.code == 2


@pytest.mark.requirement("FR-462")
def test_p0400_api004_callback_invokes_out(tmp_path) -> None:
    from pyflightstream.cases.fsi_workspace import CALLBACK_FILE
    from tests.tier1_offline.test_g06_actuator_disc import _lines
    from tests.tier1_offline.test_regression_fsi_integration import (
        _gaps_rt_fsiext___external_case as _external_case,
    )

    case, _ = _external_case(tmp_path)
    _, script = _lines(case)
    callback = script.pending_input_files[CALLBACK_FILE]
    assert "main(['external', '--out', '.'])" in callback
    assert "--dir" not in callback


@pytest.mark.requirement("FR-462")
def test_p0400_api005_external_help_has_no_requirement_id(capsys) -> None:
    assert "FR-462" not in help_text(fsi_parser(), [], capsys)


@pytest.mark.requirement("FR-461")
def test_p0400_api006_input_case_is_documented() -> None:
    page = (REPO / "docs/sixdof-motion.md").read_text()
    assert "case-sensitive" in page
    assert "`u`, `v`, `w`, `p`, `q`, `r`" in page
    assert "`external`, `spring`, `custom`" in page
    assert "`FORCE_VS_TIME` or `FORCE_VS_DISTANCE`" in page
    assert SixDofFree(q=True).q
    with pytest.raises(ValidationError):
        SixDofFree.model_validate({"Q": True})
    assert SixDofCustomForce(kind="custom", type="FORCE_VS_TIME", file="pulse.txt")
    with pytest.raises(ValidationError):
        SixDofCustomForce.model_validate(
            {"kind": "custom", "type": "force_vs_time", "file": "pulse.txt"}
        )


@pytest.mark.requirement("FR-472")
@pytest.mark.parametrize("rows,matrix", [("1", None), (None, Path("matrix.csv"))])
def test_p0400_api007_rows_refusal(rows, matrix) -> None:
    with pytest.raises(InputArtifactError) as caught:
        _print_rows(Mock(spec=GeometryBuildPlan), Namespace(rows=rows, matrix=matrix))
    assert str(caught.value) == (
        "--rows needs --matrix FILE, and --matrix needs --rows POL; give both or neither."
    )
