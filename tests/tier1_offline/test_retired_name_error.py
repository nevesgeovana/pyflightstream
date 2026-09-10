"""A retired NAME refuses in a way a caller can catch with one except.

WHY THIS FILE EXISTS. ``engine_point`` was kept so that it could refuse,
and it raised a bare ``AttributeError``. That is correct about what the
attribute is and wrong about who is listening: a caller who wraps
workspace work in ``except PyflightstreamError`` -- the one category this
package tells people to catch -- got a traceback instead of the sentence
the retirement registry wrote for exactly this moment.

The house pattern already answers it. ``MatrixError`` inherits BOTH
``PyflightstreamError`` and ``ValueError``, so a caller may select it by
the package or by the shape of the mistake, and neither reading is
privileged. A retired name is the same situation with ``AttributeError``
in the second seat.

The three cases below are the three ways a caller can reasonably reach
for it, and the fourth asserts the message is still the registry's own
rather than a new sentence written at the raise site.
"""

from __future__ import annotations

import pytest

from pyflightstream._retired_names import WORKSPACE_ENGINE_POINT, RetiredAttributeError
from pyflightstream.exceptions import PyflightstreamError
from pyflightstream.workspace import CampaignWorkspace


def _workspace(tmp_path):
    (tmp_path / "inputs").mkdir()
    return CampaignWorkspace(tmp_path)


def test_a_retired_method_is_caught_by_the_package_category(tmp_path):
    """The category the package tells callers to catch reaches it."""
    with pytest.raises(PyflightstreamError):
        _workspace(tmp_path).engine_point("HUB")


def test_a_retired_method_is_still_caught_as_an_attribute_error(tmp_path):
    """The old reading keeps working, so no caller is broken by the fix."""
    with pytest.raises(AttributeError):
        _workspace(tmp_path).engine_point("HUB")


def test_the_error_carries_both_parents(tmp_path):
    """Stated as a property, because either half alone is a regression."""
    assert issubclass(RetiredAttributeError, AttributeError)
    assert issubclass(RetiredAttributeError, PyflightstreamError)


def test_the_message_is_the_registrys_own(tmp_path):
    """The raise site quotes the registry; it does not paraphrase it."""
    with pytest.raises(RetiredAttributeError) as caught:
        _workspace(tmp_path).engine_point("HUB")
    message = str(caught.value)
    assert message == WORKSPACE_ENGINE_POINT.message()
    assert "rotor_point" in message
    assert "no longer accepted" in message


def test_the_error_is_reachable_from_the_public_exceptions_module():
    """A caller who wants the narrow class should not import a private name."""
    import pyflightstream.exceptions as public

    assert public.RetiredAttributeError is RetiredAttributeError


def test_the_package_base_is_named_first_as_every_sibling_names_it():
    """The ORDER, not only the membership, because the order is the finding.

    Round one of the 0.15.0 release review found this class written
    `(AttributeError, PyflightstreamError)` while its own docstring claimed
    it followed `MatrixError`, and every dual-base error in the catalogue
    names the package base first. The order was corrected; a mutation run
    then reverted it and the whole tier-one suite stayed green, so nothing
    held the correction. This does.

    It is asserted against the SIBLINGS rather than against a literal, so a
    later class that changes the house shape has to change it here too
    rather than finding a copy of the old shape frozen in a test.
    """
    from pyflightstream._errors import InputArtifactError, PyflightstreamError
    from pyflightstream.cases.matrix import MatrixError
    from pyflightstream.post.writers import OutputExistsError
    from pyflightstream.utils.errors import ManualCallError

    siblings = (MatrixError, ManualCallError, OutputExistsError, InputArtifactError)
    for sibling in siblings:
        assert sibling.__bases__[0] is PyflightstreamError, (
            f"{sibling.__name__} no longer names the package base first, so the "
            "house shape this case measures against has moved"
        )
    assert RetiredAttributeError.__bases__ == (PyflightstreamError, AttributeError)


def test_the_class_is_on_both_surfaces_that_re_export_it():
    """A name another module imports is a name its own __all__ must state.

    Dropping it from either list left the suite green in a mutation run,
    which is what an unstated public name looks like from the inside.
    """
    from pyflightstream import _retired_names, exceptions

    assert "RetiredAttributeError" in _retired_names.__all__
    assert "RetiredAttributeError" in exceptions.__all__
    for module in (_retired_names, exceptions):
        names = list(module.__all__)
        assert names == sorted(names), f"{module.__name__}.__all__ is unsorted"
