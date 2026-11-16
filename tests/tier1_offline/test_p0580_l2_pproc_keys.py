"""The pproc keys of the 0.58.0 polar files (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, section 7.2 and the 2.3 migration
map). A ``[groups]`` key naming TOTAL or AIRFRAME is refused by name, and so is a
key spelled as a file-name prefix (FAM, GRP) or opening with P and a digit.
``superfile_format`` reads as ``polar_format`` and ``trim_moment = "CMB25"`` as
``CmB``, each with its warning; the default trim moment is ``CmB``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec, ProductsSpec
from tests.tier1_offline.test_post_products import _unsteady_workspace

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-PPROC-KEYS")])


@pytest.mark.parametrize("key", ["TOTAL", "airframe", "Total"])
def test_a_groups_key_naming_a_default_group_is_refused_by_name(key):
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate({"groups": {key: "W"}})
    text = str(caught.value)
    assert f"[groups] declares {key}, a default group pyflightstream writes for every polar" in text
    assert "Remove the entry; the group file is written without it." in text


@pytest.mark.parametrize("key", ["FAM", "grp", "P1", "p0001x"])
def test_a_groups_key_the_file_names_cannot_carry_is_refused(key):
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate({"groups": {key: "W"}})
    assert f"[groups] declares {key}" in str(caught.value)


def test_an_ordinary_group_name_is_read():
    assert PprocSpec.model_validate({"groups": {"WING": "W", "PODS": "B"}}).groups == {
        "WING": ["W"],
        "PODS": ["B"],
    }


def test_superfile_format_reads_as_polar_format_with_its_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = ProductsSpec(superfile_format="legacy_polar")
    assert spec.polar_format == "legacy_polar"
    assert any(
        "superfile_format is now polar_format and applies to the FAM and group files."
        in str(w.message)
        for w in caught
    )
    with pytest.raises(ValidationError):
        ProductsSpec(polar_format="tecplot")


def test_trim_moment_cmb25_is_now_spelled_cmb_and_the_default_is_cmb():
    assert ProductsSpec().trim_moment == "CmB"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        spec = ProductsSpec(trim_moment="CMB25")
    assert spec.trim_moment == "CmB"
    assert any("trim_moment CMB25 is now spelled CmB." in str(w.message) for w in caught)


@pytest.mark.parametrize(
    "command", ["init-dummy", "step"], ids=["P0581-DIR-INIT", "P0581-DIR-STEP"]
)
def test_p0581_fix_retained_dir_flag_warns_once_by_default(tmp_path, command):
    env = dict(os.environ)
    env.pop("PYTHONWARNINGS", None)
    script = (
        "from pathlib import Path; "
        "from pyflightstream.fsi.cli import init_dummy, main; "
        "import sys; "
        "init_dummy(Path(sys.argv[-1]), 2); "
        "raise SystemExit(main(sys.argv[1:]))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            command,
            *(["--node-count", "2"] if command == "init-dummy" else []),
            "--dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr.count("--dir is deprecated") == 1, result.stderr
    assert "use --out" in result.stderr


@pytest.mark.parametrize(
    "policy", ["default", "warning-off", "ignore"], ids=lambda p: f"P0581-TOML-{p}"
)
def test_p0581_fix_post_shows_retained_toml_renames_once_by_default(tmp_path, policy):
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    pproc = workspace.inputs_dir / "pproc" / "p001.toml"
    pproc.write_text(
        '[groups]\n"1" = "all"\n[products]\n'
        'superfile_format = "legacy_polar"\ntrim_moment = "CMB25"\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop("PYTHONWARNINGS", None)
    if policy == "ignore":
        env["PYTHONWARNINGS"] = "ignore"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pyflightstream.run.cli import main; raise SystemExit(main())",
            *(["--warning-off"] if policy == "warning-off" else []),
            "post",
            "--workspace",
            str(workspace.root),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = int(policy == "default")
    assert result.stderr.count("superfile_format is now polar_format") == expected, result.stderr
    assert result.stderr.count("trim_moment CMB25 is now spelled CmB") == expected, result.stderr
    log = (workspace.products_dir(None) / "post.log.json").read_text(encoding="utf-8")
    assert "superfile_format is now polar_format" in log
    assert "trim_moment CMB25 is now spelled CmB" in log


@pytest.mark.parametrize((), [pytest.param(id="P0581-TOML-DEFAULT-FILTERS")])
def test_p0581_fix_python_toml_reader_names_each_rename_once(tmp_path):
    pproc = tmp_path / "pproc"
    pproc.mkdir()
    (pproc / "p001.toml").write_text(
        '[products]\nsuperfile_format = "legacy_polar"\ntrim_moment = "CMB25"\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop("PYTHONWARNINGS", None)
    script = (
        "from pathlib import Path; import sys; "
        "from pyflightstream.workspace.inputs import resolve_pproc; "
        "[resolve_pproc(Path(sys.argv[1]), 'p001') for _ in range(2)]"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr.count("superfile_format is now polar_format") == 1, result.stderr
    assert result.stderr.count("trim_moment CMB25 is now spelled CmB") == 1, result.stderr
