"""The pproc keys of the 0.58.0 polar files (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, section 7.2 and the 2.3 migration
map). A ``[groups]`` key naming TOTAL or AIRFRAME is refused by name, and so is a
key spelled as a file-name prefix (FAM, GRP) or opening with P and a digit.
``superfile_format`` reads as ``polar_format`` and ``trim_moment = "CMB25"`` as
``CmB``, each with its warning; the default trim moment is ``CmB``.
"""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec, ProductsSpec

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
