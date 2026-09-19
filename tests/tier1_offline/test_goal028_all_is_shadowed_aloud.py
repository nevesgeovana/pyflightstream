"""The group member `"all"` is every surface, unless a surface is called `all`, and then it says so.

`"all"` is what the deprecation of an empty `[groups]` list tells its owner to
write. It is tried LAST, after an exact surface name, an alias and a family, so a
geometry carrying a surface named `all` makes the group that one surface. The
release review of 0.24.0 (API-B9) found that happening in silence.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import EVERY_FAMILY, select_group_members


def test_all_on_a_geometry_with_no_surface_of_that_name_is_every_surface_and_quiet():
    inventory = ["Wing", "Fuselage", "Blade1"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert select_group_members([EVERY_FAMILY], inventory) == inventory


def test_all_shadowed_by_a_surface_of_that_name_selects_it_and_warns():
    inventory = ["Wing", "Fuselage", "all"]
    with pytest.warns(PyflightstreamWarning) as warned:
        chosen = select_group_members([EVERY_FAMILY], inventory)
    assert chosen == ["all"]
    (message,) = [str(record.message) for record in warned]
    assert "NOT every surface" in message and "['all']" in message
