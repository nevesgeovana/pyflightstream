"""P0410-CL-EX: campaign files are refused; the matrix declares a campaign."""

import pytest

from pyflightstream.cases import Campaign, CampaignConfigError, load_campaign
from pyflightstream.cases.matrix import MatrixError, convert_matrix
from pyflightstream.run.cli import main


@pytest.mark.parametrize("suffix", ["toml", "py"], ids=["P0410-TOML", "P0410-PYTHON"])
def test_p0410_cl_ex_campaign_file_refusal_names_matrix(tmp_path, suffix):
    path = tmp_path / f"campaign.{suffix}"
    path.write_text(
        '[campaign]\nname = "study"\nfs_version = "26.124"\nfs_exe = "FlightStream.exe"\n',
        encoding="utf-8",
    )
    with pytest.raises(CampaignConfigError, match="matrix.*sole campaign declaration"):
        load_campaign(path)


def test_p0410_cl_ex_convert_refusal_names_matrix(capsys):
    assert (
        main(
            [
                "convert",
                "matrix.fs",
                "--name",
                "study",
                "--fs-version",
                "26.124",
                "--fs-exe",
                "FlightStream.exe",
            ]
        )
        == 2
    )
    assert "matrix is the sole campaign declaration" in capsys.readouterr().err


def test_p0410_cl_ex_ordinary_python_campaign_still_constructs():
    campaign = Campaign(name="study", fs_version="26.124", fs_exe="FlightStream.exe", sims=[])
    assert campaign.name == "study"


def test_p0410_cl_ex_python_converter_refuses_without_writing(tmp_path):
    with pytest.raises(MatrixError, match="matrix.*sole campaign declaration"):
        convert_matrix(
            tmp_path / "matrix.fs",
            name="study",
            fs_version="26.124",
            fs_exe="FlightStream.exe",
            recipes={},
        )
    assert list(tmp_path.iterdir()) == []
