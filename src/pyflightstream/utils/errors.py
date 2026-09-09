"""Refusals of the maintainer utilities.

Its own module for the reason ``probes.errors``, ``qa.errors`` and
``fsi.errors`` have theirs: :mod:`pyflightstream.utils.manual` sits at the
bottom of the layer rule and must not reach up into a layer to borrow an
exception. This module imports only the package base, which is below
everything.
"""

from __future__ import annotations

from pyflightstream._errors import PyflightstreamError

__all__ = ["ManualCallError", "ManualDraftError"]


class ManualDraftError(PyflightstreamError, ValueError):
    """A draft was asked for something a manual cannot support.

    Raised where the caller asks the drafting functions to record more
    than the source they are reading can justify, the sharp case being a
    ``verified`` or ``broken`` status: those are promoted from a
    committed probe report by ``pyfs-qa apply-compat``, never from a page
    citation (CONTRIBUTING.md invariant 3).

    ``ValueError`` as the second base, because that is what this refusal
    raised before the catalogue existed and what a caller written against
    it would still catch (FR-39).
    """


class ManualCallError(PyflightstreamError, TypeError):
    """A drafting function was called with the wrong argument shape.

    Raised by ``propose_type`` when its two strings arrive twice, or
    positionally with a count other than two, or not at all: the keyword
    form is the one that says which string is which (PFS-2022.05).

    ``TypeError`` as the second base, because that is what a wrong call
    shape raised before the catalogue held a class for it, and what a
    caller written against it would still catch (FR-39).
    """
