"""The families a row's geometry does not carry, said once per matrix at plan (FR-320).

A ``families`` entry of a pproc artifact names families, and a family the
opened geometry does not carry is left out of that row's emission, which is
how one artifact serves a sector and a whole wheel, or a wing-body and an
isolated rotor (FR-73, the default skip). Until 0.32.0 the skip said nothing
whenever the entry still emitted something: a section distribution over
``Blade1`` to ``Blade5`` emitted one blade on a sector row whose mesh carries
``Blade1`` alone and five on the wheel row, every row planned READY, and the
plan named no family, no blade and no skip. A MISSPELLED family in a list
beside a good one vanished the same way.

The skip stays the default and is never a refusal. What this module adds is
the sentence: while a campaign is planned, whatever ``--ignore-missing-families``
says, every section distribution of a row the plan did not refuse notes,
row by row, each name it declares that the row's geometry does not carry
(:func:`note_the_families_a_row_lacks`), and at the end of the plan ONE
warning is raised per pproc artifact and per missing family, naming the
entries that declare it and the rows that lack it
(:func:`noting_the_families_rows_lack`). A row that carries the family is
named in none. No emitted byte depends on any of it.

TWO READINGS, because they answer two questions.
:func:`names_no_boundary_answers` is the refusal's (``--ignore-missing-families
false``, FR-73), moved here unchanged: a word is missing when the family
selector resolves nothing for it, so ``Blade2`` over a mesh carrying ``Blade1``
answers through its family ``Blade`` and is not refused.
:func:`declared_names_the_geometry_lacks` is the warning's: a NUMBERED name the
geometry does not carry by that name is missing even where its family answers,
because the entry declared that blade and the row cuts another or none.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._fsm import family_of, names_of
from pyflightstream.cases import alias_members_missing, select_families

__all__ = [
    "WORDS_THAT_NAME_NO_SET",
    "declared_names_the_geometry_lacks",
    "names_no_boundary_answers",
    "note_the_families_a_row_lacks",
    "noting_the_families_rows_lack",
]

#: The words a families entry may write that name no set of their own, so
#: a reader asking "does this name anything the geometry carries" would be
#: asking the wrong question of them. ``all`` is the command's own
#: every-boundary form and the two ``each`` words are one emission per family.
WORDS_THAT_NAME_NO_SET = frozenset({"all", "each", "each_blade"})
#: The two selector words that guess a set, which warn on their own when read
#: as selectors (``warn_a_selector_that_guesses``); the warning reader skips them.
_GUESSING_SELECTORS = frozenset({"airframe", "blades"})

#: A missing name: the alias that declares it, or None for a word the entry
#: wrote itself, and the name.
Lacked = tuple[str | None, str]
#: What one plan has noted: (artifact, missing name) to the entries declaring it
#: and the rows lacking it, each in the order first met. None outside a plan.
_Noted = dict[tuple[str, str], tuple[list[str], list[str]]]
_NOTED: ContextVar[_Noted | None] = ContextVar("pyflightstream_skipped_families", default=None)


def _cited(selection: str | Sequence[str]) -> list[str]:
    """Return the words of one ``families`` value, a bare word being a list of one."""
    return [selection] if isinstance(selection, str) else [str(item) for item in selection]


def names_no_boundary_answers(
    selection: str | Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    is_blade: Callable[[str], bool],
) -> list[Lacked]:
    """Return each word of one entry that the family selector resolves to nothing.

    The refusal's reading (FR-73, PFS-2035.13). An ALIAS is asked first and
    answers with the alias that DECLARES each absent member, because on a
    nested alias that is the table row a user edits; any other word is judged
    on its own, because a list aggregates into one set that is non-empty as
    soon as ONE member resolves and a misspelled member beside a good one
    passed in silence (the QA lens of 2026-09-10). A word that names no set
    is never reported. Each pair appears once, in the order the entry cites it.

    Examples
    --------
    >>> from pyflightstream.cases._skipped_families import names_no_boundary_answers
    >>> names_no_boundary_answers(["Blade2", "Rotor", "each"], ["Blade1"], {}, bool)
    [(None, 'Rotor')]
    """
    missing: list[Lacked] = []
    for token in _cited(selection):
        absent = alias_members_missing(token, inventory, aliases)
        if absent:
            missing.extend(pair for pair in absent if pair not in missing)
            continue
        if token.strip().casefold() in WORDS_THAT_NAME_NO_SET:
            continue
        if not select_families(token, inventory, is_blade, aliases=aliases):
            if (None, token) not in missing:
                missing.append((None, token))
    return missing


def _alias_named(token: str, aliases: Mapping[str, Sequence[str]]) -> str | None:
    """Return the alias one word names, the exact spelling first and case folded second."""
    if token in aliases:
        return token
    return next((name for name in aliases if name.casefold() == token.casefold()), None)


def declared_names_the_geometry_lacks(
    selection: str | Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
) -> list[Lacked]:
    """Return each name one entry declares that the geometry does not carry.

    The warning's reading (FR-320). Aliases are followed to the end in the
    resolver's order (a boundary the mesh carries first, then another alias,
    then the family), and every name reached is judged: carried when a
    boundary has that name, case folded; for a FAMILY word, one with no
    trailing number, also when its family answers. A numbered name such as
    ``Blade2`` is lacking on a mesh that carries ``Blade1`` alone, although the
    selector answers it through the family ``Blade``. The words that name no
    set and the two guessing selectors are never reported.

    Parameters
    ----------
    selection : str or sequence of str
        The entry's ``families`` value, as the artifact writes it.
    inventory : sequence of str
        The boundary labels of the opened geometry.
    aliases : mapping of str to sequence of str
        The names the row can cite: the setup's aliases and each rotor's own
        name for its families.

    Returns
    -------
    list of tuple
        ``(the alias declaring it or None, the name)``, each once, in the
        order the entry declares them; empty when the geometry carries all.

    Examples
    --------
    >>> from pyflightstream.cases._skipped_families import declared_names_the_geometry_lacks
    >>> declared_names_the_geometry_lacks(["Blade1", "Blade2", "each"], ["Hub", "Blade1"], {})
    [(None, 'Blade2')]
    """
    carried = {name.casefold() for name in inventory}
    missing: list[Lacked] = []

    def judge(owner: str | None, token: str, path: tuple[str, ...]) -> None:
        if token.casefold() in carried:
            return
        key = _alias_named(token, aliases)
        if key is not None and key not in path:
            for member in aliases[key]:
                judge(key, str(member), (*path, key))
            return
        word = token.strip().casefold()
        if owner is None and word in WORDS_THAT_NAME_NO_SET | _GUESSING_SELECTORS:
            return
        if family_of(token) == word and names_of(token, inventory):
            return
        if (owner, token) not in missing:
            missing.append((owner, token))

    for token in _cited(selection):
        judge(None, token, ())
    return missing


def note_the_families_a_row_lacks(
    row: str, artifact: str, what: str, lacked: Sequence[Lacked]
) -> None:
    """Note, inside a plan, the names one entry declares that one row's geometry lacks.

    Outside :func:`noting_the_families_rows_lack` this does nothing, so a
    script built on its own warns as it always did.

    Parameters
    ----------
    row : str
        The row's simulation id, as the plan names it.
    artifact : str
        The pproc artifact, as a message names it.
    what : str
        The entry, ``section distribution 2`` for instance.
    lacked : sequence of tuple
        The pairs :func:`declared_names_the_geometry_lacks` returned.
    """
    noted = _NOTED.get()
    if noted is None:
        return
    for owner, name in lacked:
        entry = what if owner is None else f"{what} (through {owner!r})"
        entries, rows = noted.setdefault((artifact, name), ([], []))
        if entry not in entries:
            entries.append(entry)
        if row not in rows:
            rows.append(row)


@contextmanager
def noting_the_families_rows_lack() -> Iterator[None]:
    """Collect what every row lacks while a campaign is planned, then warn once per family.

    On leaving the block normally, one :class:`PyflightstreamWarning` is raised
    per pproc artifact and per missing family, in the order first noted. A
    block left by an exception warns nothing: the plan did not complete, and
    its refusal is what the caller hears. A nested block notes into its own
    collection.

    Warns
    -----
    PyflightstreamWarning
        Naming the artifact, the family, the entries declaring it and every
        row whose geometry does not carry it. Never a refusal.
    """
    noted: _Noted = {}
    token = _NOTED.set(noted)
    try:
        yield
    finally:
        _NOTED.reset(token)
    for (artifact, name), (entries, rows) in noted.items():
        warn(_the_warning(artifact, name, entries, rows), PyflightstreamWarning, stacklevel=3)


def _the_warning(artifact: str, name: str, entries: Sequence[str], rows: Sequence[str]) -> str:
    """Word the one warning for one missing family of one artifact."""
    cite = "cites" if len(entries) == 1 else "cite"
    lacking = (
        f"the geometry of row {rows[0]!r} does not carry it"
        if len(rows) == 1
        else f"the geometries of {len(rows)} rows do not carry it: "
        + ", ".join(repr(row) for row in rows)
    )
    return (
        f"{artifact}: {' and '.join(entries)} {cite} {name!r}, and {lacking}. "
        f"{'That row emits' if len(rows) == 1 else 'Those rows emit'} the entry without it: "
        "a family the geometry does not carry is skipped, which is how one artifact serves "
        "several geometries, and a misspelled family name is skipped the same way. Correct "
        "the name if every row should carry it (FR-320)."
    )
