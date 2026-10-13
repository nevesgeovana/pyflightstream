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
says, every pproc entry that names families (a section distribution and a
force plot group, both expanded by the one expansion this module decorates,
:func:`saying_the_families_each_row_skips`) notes, row by row, each name it
declares that the row's geometry does not carry and that the expansion did
not refuse (:func:`note_the_families_a_row_lacks`), and at the end of the plan ONE
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

FR-435 WIDENS THE SKIP TO THE SETUP AND THE PPROC KEYS, for a study. A setup,
a pproc and a reference written once for every model of one aircraft cite
names one model lacks: the wing-body row of a study whose wing-body-tail
carries a sting and a tail. Where the row's REFERENCE declares the study's
vocabulary (``[study] surfaces``, with its aliases and their members,
:func:`study_vocabulary`), a name a key of FR-435 R1 cites that selects
nothing on the row's model is skipped when the vocabulary holds it and refused
as a misspelling when it does not (:func:`judge_a_name_the_model_lacks`). Each
skip is noted for the build (:func:`collecting_the_study_skips`), so the run
records it on the point (``skipped_names``), and a plan says it once per
artifact, key and name, naming every row that lacks it
(:func:`saying_the_study_skips`, :func:`noting_the_study_skips`). A reference
declaring no vocabulary keeps the 0.38.0 reading of every name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from pathlib import PurePath
from typing import TYPE_CHECKING, Any, TypeVar, cast

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._fsm import family_of, names_of
from pyflightstream.cases import (
    CampaignConfigError,
    alias_members_missing,
    select_families,
    select_group_members,
)

if TYPE_CHECKING:
    from pyflightstream.cases import SimCase

__all__ = [
    "PPROC_ARTIFACT",
    "SETUP_ARTIFACT",
    "WORDS_THAT_NAME_NO_SET",
    "StudySkip",
    "collecting_the_study_skips",
    "declared_names_the_geometry_lacks",
    "held_by_the_study",
    "ignores_missing_families",
    "judge_a_name_the_model_lacks",
    "names_a_row_can_cite",
    "names_no_boundary_answers",
    "note_the_families_a_row_lacks",
    "noting_the_families_rows_lack",
    "noting_the_study_skips",
    "refuses_a_name_the_model_lacks",
    "saying_the_families_each_row_skips",
    "saying_the_study_skips",
    "selects_nothing",
    "skips_a_name_the_model_lacks",
    "study_vocabulary",
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
#: The frames between the warning and the caller of the decorated plan: this
#: generator, contextlib's exit, the decorator's wrapper, then the caller.
_THE_PLANS_CALLER = 4
_Expansion = TypeVar("_Expansion", bound=Callable[..., Any])


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
        # THE FAMILY ANSWERS FIRST (FR-320 R4, R5). A numbered member whose
        # family the mesh carries selects its exact name only since 0.40.0
        # (PFS-2029.25), so it selects nothing on a sector, and it is still not
        # refused here: the plan's warning names it. Asked first, it also keeps
        # the cited-alone refusal of the selector out of this reader.
        if names_of(token, inventory, refuse_indexed=False):
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
        warn(
            _the_warning(artifact, name, entries, rows),
            PyflightstreamWarning,
            stacklevel=_THE_PLANS_CALLER,
        )


def saying_the_families_each_row_skips(
    names_of_row: Callable[[Any], Mapping[str, Sequence[str]]],
    artifact_of_row: Callable[[Any], str],
) -> Callable[[_Expansion], _Expansion]:
    """Decorate the expansion of a pproc entry so each row notes the names it lacks.

    The expansion takes the parameters ``case``, ``families``, ``inventory``
    and ``what``, by position or by name, which is how every consumer of a
    section distribution or a force plot group calls it. After it RETURNS,
    inside a plan, the names the entry declares and the row's geometry does
    not carry are noted for the row; an expansion that refuses notes nothing,
    so a refused row is not also warned about. Outside a plan the expansion
    runs alone.

    Parameters
    ----------
    names_of_row : callable
        The names a row can cite, from the row: its aliases and each rotor's
        own name for its families.
    artifact_of_row : callable
        The row's pproc artifact, as a message names it.

    Returns
    -------
    callable
        The decorator, which keeps the expansion's signature and result.
    """

    def decorate(expansion: _Expansion) -> _Expansion:
        parameters = signature(expansion)

        @wraps(expansion)
        def noting(*args: Any, **options: Any) -> Any:
            emitted = expansion(*args, **options)
            if _NOTED.get() is not None:
                given = parameters.bind(*args, **options).arguments
                case, inventory = given["case"], given["inventory"]
                lacked = declared_names_the_geometry_lacks(
                    given["families"], inventory, names_of_row(case)
                )
                note_the_families_a_row_lacks(
                    case.sim_id, artifact_of_row(case), given["what"], lacked
                )
            return emitted

        return cast(_Expansion, noting)

    return decorate


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


# --- FR-435: the names a study holds and a row's model lacks ------------------

#: The two kinds of artifact whose keys FR-435 R1 covers, as a skip names them.
SETUP_ARTIFACT = "setup"
PPROC_ARTIFACT = "pproc"


@dataclass(frozen=True)
class StudySkip:
    """One name a key cites, that the row's model lacks and its study holds (FR-435 R4).

    Attributes
    ----------
    artifact : str
        The id of the artifact citing it, ``s001`` or ``p001``.
    key : str
        The key citing it: ``groups.<GROUP>`` for a ``[groups]`` member and
        ``base_region_operations[<position from 1>]`` for an entry of that list.
    name : str
        The name as the artifact writes it.
    said : str
        The artifact as a message names it, with its file.
    reference : str
        The reference whose vocabulary holds the name, as a message names it.
    """

    artifact: str
    key: str
    name: str
    said: str
    reference: str

    def record(self) -> dict[str, str]:
        """Return the entry a point's run record carries for this skip (FR-435 R11)."""
        return {"artifact": self.artifact, "key": self.key, "name": self.name}


#: The skips of the build under way, None outside one.
_BUILD: ContextVar[list[StudySkip] | None] = ContextVar("pyflightstream_study_build", default=None)
#: What one plan has noted: each (artifact, key, name) to the skips it made (one per
#: reference holding the name) and the rows that made them, in the order first met.
_StudyNoted = dict[tuple[str, str, str], tuple[list[StudySkip], list[str]]]
_STUDY_PLAN: ContextVar[_StudyNoted | None] = ContextVar("pyflightstream_study_plan", default=None)


def names_a_row_can_cite(case: SimCase) -> dict[str, list[str]]:
    """Return the reference's aliases with each rotor block's own name added to them.

    A rotor's name is an alias for its own families (FR-60, FR-65), so a
    reference block ``PUSHER`` stands for its ``families_general`` and
    ``families_blades``. The reference's ``[aliases]`` table takes precedence,
    so a study that gives one of these names a meaning of its own keeps it.
    One map for every reader: the pproc expansions, the study vocabulary
    (FR-435 R2) and the classification of a cited name (FR-435 R4, R13).
    """
    return {
        **{
            name: [*block.families_general, *block.families_blades]
            for name, block in case.rotors.items()
        },
        **case.aliases,
    }


def study_vocabulary(case: SimCase) -> tuple[str, ...] | None:
    """Return the names a row's study holds, or None where its reference declares none.

    FR-435 R2: the reference's ``[study] surfaces``, then the names of its
    aliases (a rotor block's own name among them, :func:`names_a_row_can_cite`)
    and every member of each, so an alias followed to the end is in it too.
    Each once, case folded.

    Examples
    --------
    >>> from pyflightstream.cases import ReferenceData, SimCase, SweepAxis
    >>> from pyflightstream.cases._skipped_families import study_vocabulary
    >>> case = SimCase(
    ...     sim_id="1", aircraft="A", recipe="steady", sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     reference=ReferenceData(area=1.0, length=1.0, study_surfaces=("Wing", "Sting")),
    ...     aliases={"tail": ["HTail", "VTail"]},
    ... )
    >>> study_vocabulary(case)
    ('Wing', 'Sting', 'tail', 'HTail', 'VTail')
    """
    reference = case.reference
    surfaces = None if reference is None else reference.study_surfaces
    if surfaces is None:
        return None
    names = names_a_row_can_cite(case)
    members = [str(member) for listed in names.values() for member in listed]
    held: dict[str, str] = {}
    for name in (*surfaces, *names, *members):
        held.setdefault(name.casefold(), name)
    return tuple(held.values())


def held_by_the_study(token: str, vocabulary: Sequence[str]) -> bool:
    """Whether a study's vocabulary holds one cited name (FR-435 R2).

    Held when the name equals one of the vocabulary's, case folded, or is a
    FAMILY word (the label without its trailing number) one of them answers,
    the reading of FR-320 R2.

    Examples
    --------
    >>> from pyflightstream.cases._skipped_families import held_by_the_study
    >>> [held_by_the_study(name, ["Blade1", "Sting"]) for name in ("sting", "Blade", "Stinng")]
    [True, True, False]
    """
    word = token.strip().casefold()
    if any(name.casefold() == word for name in vocabulary):
        return True
    return family_of(token) == word and bool(names_of(token, vocabulary))


def selects_nothing(
    token: str, inventory: Sequence[str], aliases: Mapping[str, Sequence[str]]
) -> bool:
    """Whether one cited name selects no boundary of a model (FR-435 R4).

    No boundary has the name, case folded, no family the model carries answers
    it, and, for an alias, no member resolves: the reading every
    boundary-citing cell uses (:func:`pyflightstream.cases.select_group_members`).
    The words that name no set (``all``, ``each``, ``each_blade``) never do.

    Examples
    --------
    >>> from pyflightstream.cases._skipped_families import selects_nothing
    >>> [selects_nothing(name, ["Wing", "Body"], {"tail": ["HTail"]}) for name in ("tail", "wing")]
    [True, False]
    """
    if token.strip().casefold() in WORDS_THAT_NAME_NO_SET:
        return False
    return not select_group_members([token], list(inventory), aliases, strict=False)


def ignores_missing_families(case: SimCase) -> bool:
    """Whether a family the mesh lacks is skipped (the default) or refuses (FR-73).

    The one reader of ``IGNORE_MISSING_FAMILIES``, a per-invocation choice the
    command line writes onto the case's variables. Absent or blank, it is
    TRUE, which is what every row written before the flag means.
    """
    # Deferred: the workflows package imports this module while it loads, and
    # the variable's name and its reader live in its vocabulary, their one home.
    from pyflightstream.cases.workflows._vocabulary import (
        IGNORE_MISSING_FAMILIES_VARIABLE,
        read_a_choice,
    )

    stated = str(case.variables.get(IGNORE_MISSING_FAMILIES_VARIABLE) or "").strip()
    if not stated:
        return True
    try:
        return read_a_choice(
            stated, context=f"case {case.sim_id!r}: {IGNORE_MISSING_FAMILIES_VARIABLE}"
        )
    except ValueError as error:
        raise CampaignConfigError(str(error)) from None


def refuses_a_name_the_model_lacks(case: SimCase) -> bool:
    """Whether the run asked for the refusal rather than the skip (FR-73, FR-435 R10)."""
    return not ignores_missing_families(case)


def _artifact(case: SimCase, kind: str) -> tuple[str, str]:
    """Return one of a row's artifacts as (its id, the words a message names it with)."""
    if kind == PPROC_ARTIFACT:
        code = str(case.pproc_id or "").strip()
        folder = "pproc"
    else:
        code = str(case.variables.get("matrix_set") or "").strip()
        folder = "setups"
    if not code:
        return kind, f"the row's {kind} artifact"
    return code, f"the {kind} artifact {code!r} (inputs/{folder}/{code}.toml)"


def _reference(case: SimCase) -> str:
    """Name a row's reference artifact for a message, with its file where the id is known."""
    code = str(case.variables.get("matrix_ref") or "").strip()
    if not code:
        return "the row's reference"
    return f"the reference artifact {code!r} (inputs/references/{code}.toml)"


def _model(case: SimCase) -> str:
    """Name a row and the geometry it opens, for a message."""
    return f"row {case.sim_id!r} ({PurePath(str(case.geometry)).name})"


def judge_a_name_the_model_lacks(case: SimCase, kind: str, key: str, token: str) -> bool:
    """Skip one cited name the row's model lacks, or refuse it (FR-435 R4, R6, R10).

    Called for a token of a key of FR-435 R1 that selects nothing on the row's
    model (:func:`selects_nothing`). In order: a name the row's study does not
    hold is a misspelling and is refused at either value of
    ``--ignore-missing-families`` (R6); a run that asked for the refusal
    refuses it, whether or not the reference declares a vocabulary (R10); a
    name the study holds is skipped and noted for the build (R4, R9, R11).

    Parameters
    ----------
    case : SimCase
        The point's case.
    kind : str
        :data:`SETUP_ARTIFACT` or :data:`PPROC_ARTIFACT`, the artifact citing it.
    key : str
        The key citing it, as :class:`StudySkip` spells it.
    token : str
        The name as the artifact writes it.

    Returns
    -------
    bool
        True when the name is skipped; False when the reference declares no
        vocabulary and the run did not ask for the refusal, so the caller reads
        the name as 0.38.0 did (R3).

    Raises
    ------
    CampaignConfigError
        The study does not hold the name, or the run asked for the refusal.
    """
    vocabulary = study_vocabulary(case)
    code, said = _artifact(case, kind)
    if vocabulary is not None and not held_by_the_study(token, vocabulary):
        raise CampaignConfigError(_a_misspelling(case, said, key, token, vocabulary))
    if refuses_a_name_the_model_lacks(case):
        raise CampaignConfigError(_the_refusal_asked_for(case, said, key, token))
    if vocabulary is None:
        return False
    skip = StudySkip(code, key, token, said, _reference(case))
    collected = _BUILD.get()
    if collected is not None and skip not in collected:
        collected.append(skip)
    return True


def skips_a_name_the_model_lacks(
    case: SimCase, kind: str, key: str, token: str, inventory: Sequence[str]
) -> bool:
    """Classify one name a key of FR-435 R1 cites, against the model as it opened (R4, R13).

    The one classification every covered key routes through. A name that
    selects some boundary of ``inventory`` through the row's names
    (:func:`names_a_row_can_cite`), and the words that name no set (``all``,
    ``each``, ``each_blade``), are not judged: the caller reads them as 0.38.0
    did. Every other name is judged by :func:`judge_a_name_the_model_lacks`.

    Parameters
    ----------
    case : SimCase
        The point's case.
    kind : str
        :data:`SETUP_ARTIFACT` or :data:`PPROC_ARTIFACT`, the artifact citing it.
    key : str
        The key citing it, as :class:`StudySkip` spells it.
    token : str
        The name as the artifact writes it.
    inventory : sequence of str
        The boundary labels of the row's model in inventory order, as the
        geometry OPENED them: before ``delete_surfaces`` removed any, so a
        name the setup itself removed is not a name the model lacks.

    Returns
    -------
    bool
        True when the name is skipped; False when the caller reads it as on
        0.38.0.

    Raises
    ------
    CampaignConfigError
        As :func:`judge_a_name_the_model_lacks` does.

    Examples
    --------
    >>> from pyflightstream.cases import ReferenceData, SimCase, SweepAxis
    >>> from pyflightstream.cases._skipped_families import skips_a_name_the_model_lacks
    >>> case = SimCase(
    ...     sim_id="1", aircraft="A", recipe="steady", sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     reference=ReferenceData(area=1.0, length=1.0, study_surfaces=("Wing", "Sting")),
    ... )
    >>> def skips(name):
    ...     return skips_a_name_the_model_lacks(case, "setup", "k", name, ["Wing"])
    >>> [skips(name) for name in ("Sting", "each", "Wing")]
    [True, False, False]
    """
    if not selects_nothing(token, inventory, names_a_row_can_cite(case)):
        return False
    return judge_a_name_the_model_lacks(case, kind, key, token)


def _a_misspelling(
    case: SimCase, said: str, key: str, token: str, vocabulary: Sequence[str]
) -> str:
    """Word the refusal of a name neither the model nor the study carries (FR-435 R6)."""
    return (
        f"case {case.sim_id!r}: {said} cites {token!r} under {key}, and neither the "
        f"geometry of {_model(case)} nor the study vocabulary of {_reference(case)} "
        f"holds it; the vocabulary holds {', '.join(repr(name) for name in vocabulary)}. "
        "Correct the name, or add it to the reference's [study] surfaces if a model of "
        "the study carries it (FR-435)."
    )


def _the_refusal_asked_for(case: SimCase, said: str, key: str, token: str) -> str:
    """Word the refusal a run asked for instead of the skip (FR-435 R10, FR-73)."""
    return (
        f"case {case.sim_id!r}: {said} cites {token!r} under {key}, and the geometry of "
        f"{_model(case)} carries no boundary, family or alias member of that name. This "
        "run was asked for the refusal rather than the skip: ignore_missing_families "
        "(CLI: --ignore-missing-families) was given as false, so a name the model does "
        "not carry is an error here and not the difference between two models of one "
        "study (FR-435)."
    )


@contextmanager
def collecting_the_study_skips() -> Iterator[list[StudySkip]]:
    """Collect the skips of one build, in the order made (FR-435 R11).

    The list the block yields is filled while the block runs and is complete
    when it ends; a nested block collects into its own list.
    """
    collected: list[StudySkip] = []
    token = _BUILD.set(collected)
    try:
        yield collected
    finally:
        _BUILD.reset(token)


def saying_the_study_skips[Recipe: Callable[..., Any]](recipe: Recipe) -> Recipe:
    """Wrap a recipe so a plan notes what each row's build skipped (FR-435 R9).

    The skips of a build that RETURNS are noted for its row inside
    :func:`noting_the_study_skips`; a build that refuses notes nothing, so a
    row refused under R5 to R8 or R10 is not also warned about. Outside a
    plan the recipe runs as it would alone.
    """

    @wraps(recipe)
    def building(case: SimCase, script: Any) -> Any:
        with collecting_the_study_skips() as skips:
            built = recipe(case, script)
        noted = _STUDY_PLAN.get()
        if noted is not None:
            for skip in skips:
                held, rows = noted.setdefault((skip.artifact, skip.key, skip.name), ([], []))
                if skip not in held:
                    held.append(skip)
                if case.sim_id not in rows:
                    rows.append(case.sim_id)
        return built

    return cast(Recipe, building)


@contextmanager
def noting_the_study_skips() -> Iterator[None]:
    """Collect every row's skips while a campaign is planned, then warn once per name.

    On leaving the block normally, one :class:`PyflightstreamWarning` is raised
    per artifact, key and name, in the order first noted, naming every row
    whose model lacks it (FR-435 R9). It changes no plan status. A block left
    by an exception warns nothing.

    Warns
    -----
    PyflightstreamWarning
        Naming the artifact and its file, the key, the name, the reference
        whose vocabulary holds it, and the rows.
    """
    noted: _StudyNoted = {}
    token = _STUDY_PLAN.set(noted)
    try:
        yield
    finally:
        _STUDY_PLAN.reset(token)
    for held, rows in noted.values():
        warn(_the_study_warning(held, rows), PyflightstreamWarning, stacklevel=_THE_PLANS_CALLER)


def _the_study_warning(held: Sequence[StudySkip], rows: Sequence[str]) -> str:
    """Word the one warning for one name of one artifact's key (FR-435 R9).

    ``held`` is the skip once per reference whose vocabulary holds the name;
    the warning names every one of them.
    """
    skip = held[0]
    references = " and ".join(dict.fromkeys(item.reference for item in held))
    lacking = (
        f"the geometry of row {rows[0]!r} does not carry it"
        if len(rows) == 1
        else f"the geometries of {len(rows)} rows do not carry it: "
        + ", ".join(repr(row) for row in rows)
    )
    return (
        f"{skip.said}: {skip.key} cites {skip.name!r}, which the study vocabulary of "
        f"{references} holds, and {lacking}. "
        f"{'That row leaves' if len(rows) == 1 else 'Those rows leave'} it out of the key: "
        "a name the study holds and a model lacks is skipped, which is how one file serves "
        "every model of a study, and a name the study does not hold is refused (FR-435)."
    )
