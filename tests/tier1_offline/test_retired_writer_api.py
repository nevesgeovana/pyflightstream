"""LARCH-003: both former public imports explain the dataset-to-points replacement."""

# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.0
# last_modified_at: 2026-10-13T23:52:19-03:00
# last_modified_by: OpenAI / Codex / gpt-6-astra / architect-reviewer
# dependencies: [pytest, pyflightstream.post, pyflightstream.post.writers]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Check the retirement diagnostic at both former public import paths.
# revision_source: git
# GEOVERSE_HEADER_END

import importlib

import pytest

from pyflightstream.exceptions import RetiredAttributeError


@pytest.mark.parametrize("name", ["pyflightstream.post", "pyflightstream.post.writers"])
def test_dataset_to_points_retirement_names_the_replacement_at_each_public_path(name):
    """A removed name stays absent, while its diagnostic identifies the migration."""
    module = importlib.import_module(name)
    with pytest.raises(AttributeError) as caught:
        _ = module.dataset_to_points
    assert isinstance(caught.value, RetiredAttributeError), str(caught.value)
    message = str(caught.value)
    assert "LatticeFields.points()" in message
    assert "0.40.0" in message
    assert "dataset_to_points" not in module.__all__
    assert "dataset_to_points" not in vars(module)


def test_an_unknown_writer_name_remains_an_ordinary_attribute_error():
    module = importlib.import_module("pyflightstream.post.writers")
    with pytest.raises(AttributeError) as caught:
        _ = module.not_a_writer
    assert not isinstance(caught.value, RetiredAttributeError)
