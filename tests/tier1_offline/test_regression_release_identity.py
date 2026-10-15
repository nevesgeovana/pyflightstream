"""Regression coverage grouped by subject."""

from __future__ import annotations

import pytest

from pyflightstream.post import ProductError
from pyflightstream.post.superfile import release_tag


class TestIntegfixReleaseTag:
    """Tier 1, 0.40.0 integration fixes: the release tag of a pre-release version."""

    @staticmethod
    def test_p0400_a_release_candidate_never_takes_the_tag_of_a_patch_release():
        """P0400-RC-TAG (PFS-2081.46): ``0.40.0rc1`` was tagged ``0401``, the tag of 0.40.1.

        The digits of every part were joined, so the ``1`` of ``rc1`` became the patch
        number. A pre-release keeps its label after the three numbers.
        """
        assert release_tag("0.40.0rc1") == "0400rc1"
        assert release_tag("0.40.1") == "0401"
        assert release_tag("0.40.0rc1") != release_tag("0.40.1")
        assert release_tag("1.0.0b2") == "100b2"
        assert release_tag("0.40.0a1") != release_tag("0.40.1")
        # The forms a build already has keep their tags.
        assert release_tag("0.40.0.dev0") == "0400"
        assert release_tag("0.0.0+uninstalled") == "000"

    @staticmethod
    def test_p0400_a_patch_that_is_no_number_and_label_is_refused_by_name():
        """P0400-RC-TAG (PFS-2081.46): the control, a patch the tag cannot be read from."""
        with pytest.raises(ProductError, match="0.40.x"):
            release_tag("0.40.x")
