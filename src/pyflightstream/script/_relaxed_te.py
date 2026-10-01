"""The relaxed trailing-edge component specification, read and written (AD-17).

A private module of the ``script`` package since 0.34.0: the block moved
out of :mod:`pyflightstream.script.helpers` whole and unchanged (GOAL-039,
work package WP9a), and every name below is still imported from
``pyflightstream.script.helpers``, which is the public path. The pair
emits nothing: it reads and writes the ``Relaxed_TE;u;v1;v2;direction``
line a CCS file writes where a component is defined (SRC-752 p.85).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from pyflightstream.script import CommandArgumentError

# --- PFS-2026.06: the relaxed trailing-edge specification's direction value -----
#
# THIS PAIR EMITS NOTHING, which is the one surprise worth stating before
# the code. Every other curated helper of `script.helpers` turns typed
# arguments into `script.emit()` calls. A relaxed-Kutta trailing edge can also be
# declared as a COMPONENT parameter, written where a component is defined
# rather than in a script, and no command on any registered build takes
# its fields (the reading is recorded on SET_TRAILING_EDGE_TYPE in the
# command database, and `tests/tier1_offline/test_wake_edges.py` pins it). So these
# read and write the specification TEXT, and take no `script`.

#: The keyword that opens the line in a CCS file: ``Relaxed_TE;u;v1;v2`` in
#: the editions up to SRC-750 p.85, ``Relaxed_TE;u;v1;v2;direction`` from
#: SRC-751 p.85 (SRC-752 p.85 unchanged). A specification may be written with
#: it or without it, and renders the way it was written.
RELAXED_TE_KEYWORD = "Relaxed_TE"

#: VALUE count of the specification AFTER the keyword: three (``u``, ``v1``,
#: ``v2``) in the form the earlier editions print, four once the shedding
#: direction is stated. Settled against SRC-752 p.85 in 0.32.0 (FR-244): until
#: then the helper counted four leading values and a fifth for the direction,
#: so the manual's ``0.5;0.2;0.8;1`` read as a line with no direction. The
#: three-value form stays valid, so both counts are accepted and neither is
#: converted into the other unasked.
RELAXED_TE_FIELDS_WITHOUT_DIRECTION = 3
RELAXED_TE_FIELDS_WITH_DIRECTION = 4

#: The direction the relaxed wake sheds, as the token this package takes
#: mapped to the integer the specification's direction value carries
#: (SRC-751 p.85). AXIAL is 0 AND is the default, which is what a
#: three-value specification already means; AZIMUTH is 1 and is the new
#: control, the one a rotor case wants.
RELAXED_SHEDDING_DIRECTIONS: Mapping[str, int] = {"AXIAL": 0, "AZIMUTH": 1}

#: The reverse lookup, built once. Written from the mapping above rather
#: than typed a second time, so the two can never disagree.
_SHEDDING_BY_FIELD: Mapping[int, str] = {
    field: token for token, field in RELAXED_SHEDDING_DIRECTIONS.items()
}

#: The direction a specification that states no direction value means.
DEFAULT_SHEDDING_DIRECTION = "AXIAL"


def _shedding_vocabulary() -> str:
    """Render the accepted directions the way every refusal names them."""
    return " or ".join(
        f"{field} ({token})" for token, field in sorted(RELAXED_SHEDDING_DIRECTIONS.items())
    )


def resolve_shedding_direction(value: str | int, *, context: str) -> str:
    """Resolve one relaxed-wake shedding direction to its token.

    Takes either vocabulary, because the specification writes the
    integer and a caller reads the word: ``0`` and ``"AXIAL"`` are the
    same request, as are ``1`` and ``"AZIMUTH"``. Tokens are matched
    without regard to case and a numeric string is read as the integer
    it spells, which is what a matrix cell carries.

    Parameters
    ----------
    value : str or int
        The direction, as a token or as the integer the direction value
        carries.
    context : str
        What is being resolved, prefixed to the refusal so the caller
        learns which call refused. A helper passes its own name; a
        campaign passes the case and the key.

    Returns
    -------
    str
        ``"AXIAL"`` or ``"AZIMUTH"``.

    Raises
    ------
    CommandArgumentError
        If the value is neither. The message names the value received
        and both accepted directions, because there is no third: the
        field is an integer with exactly two documented values, and a
        direction outside them would make the solver read a wake
        shedding in a direction the manual does not define.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> helpers.resolve_shedding_direction(1, context="rotor")
    'AZIMUTH'
    >>> helpers.resolve_shedding_direction("axial", context="rotor")
    'AXIAL'
    """
    token: str | None = None
    if isinstance(value, bool):
        # bool is an int in Python, so True would otherwise resolve to
        # AZIMUTH. A direction is not a switch, and the caller who wrote
        # True meant something this package cannot know.
        token = None
    elif isinstance(value, int):
        token = _SHEDDING_BY_FIELD.get(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.upper() in RELAXED_SHEDDING_DIRECTIONS:
            token = text.upper()
        elif text.isascii() and text.isdigit():
            # ASCII DIGITS ONLY, and the guard is not decoration.
            # `int()` reads any Unicode decimal digit, so the
            # Arabic-Indic ONE resolved to AZIMUTH and a field spelled
            # in a script the manual never uses became a direction the
            # solver would shed a wake along. It also read `+1`, which
            # no tool writes and which the manual's "integer, 0 or 1"
            # does not describe. Both are accidents of the conversion
            # rather than decisions, and a refusal naming both accepted
            # values is a better answer than either.
            token = _SHEDDING_BY_FIELD.get(int(text))
    if token is None:
        raise CommandArgumentError(
            f"{context}: the relaxed wake sheds in one of two directions and "
            f"{value!r} is neither. The direction value of the relaxed trailing-edge "
            f"component specification takes {_shedding_vocabulary()}, the axial "
            "direction being the default and the one a three-value specification "
            "already means (SRC-751 p.85). Write the integer or the word; there is "
            "no third direction to fall back to, and shedding a rotor wake the wrong "
            "way round changes the induced velocity at every blade"
        )
    return token


@dataclass(frozen=True)
class RelaxedTrailingEdge:
    """One relaxed trailing-edge component specification, read apart.

    The specification is the line a CCS file writes where a component is
    defined, not a script line: ``Relaxed_TE;u;v1;v2;direction``
    (SRC-752 p.85). ``u`` is a chordwise or radial location and ``v1``,
    ``v2`` the spanwise or axial bounds; this package does not interpret
    them and carries them verbatim, because the edition that added the
    direction changed nothing about them. The keyword may be written or
    left out, and the specification renders the way it was written.

    THE THREE-VALUE FORM IS NOT SILENTLY WIDENED. A specification parsed
    with three values renders with three, so an artifact written before
    26.123 stays readable by the builds that wrote it; the direction
    appears only where one was read or one was asked for.

    Attributes
    ----------
    fields : tuple of str
        The three values ``u``, ``v1``, ``v2``, verbatim apart from the
        whitespace around each one, which is not part of a value.
    direction : str or None
        ``"AXIAL"`` or ``"AZIMUTH"`` where the specification carries the
        direction value, and None where it carries three. None is not the
        same statement as ``"AXIAL"``: both MEAN the axial direction, and
        only one of them writes a value.
    keyword : bool
        Whether the text opened with ``Relaxed_TE``, which the rendering
        then writes again.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> edge = helpers.parse_relaxed_trailing_edge("0.5;0.1;0.9")
    >>> edge.direction is None
    True
    >>> edge.shedding_direction
    'AXIAL'
    >>> edge.render()
    '0.5;0.1;0.9'
    >>> edge.with_shedding("AZIMUTH").render()
    '0.5;0.1;0.9;1'
    >>> helpers.parse_relaxed_trailing_edge("Relaxed_TE;0.5;0.1;0.9;1").render()
    'Relaxed_TE;0.5;0.1;0.9;1'
    """

    fields: tuple[str, ...]
    direction: str | None = None
    keyword: bool = False

    def __post_init__(self) -> None:
        """Normalize the values and refuse a record that cannot render.

        The record is public and constructible directly, so the two
        invariants rendering rests on are checked here rather than only
        in the parser: exactly the three values, and a direction the
        direction value can spell.
        """
        object.__setattr__(self, "fields", tuple(str(field).strip() for field in self.fields))
        if len(self.fields) != RELAXED_TE_FIELDS_WITHOUT_DIRECTION:
            raise CommandArgumentError(
                f"RelaxedTrailingEdge holds the {RELAXED_TE_FIELDS_WITHOUT_DIRECTION} "
                f"leading fields of the specification (u, v1, v2) and was given "
                f"{len(self.fields)}: {self.fields!r}. The shedding direction is the "
                "`direction` attribute and never a fourth entry here, so that rendering "
                "can tell a specification that states the direction from one that leaves "
                "it at the default (SRC-752 p.85)"
            )
        if self.direction is not None and self.direction not in RELAXED_SHEDDING_DIRECTIONS:
            raise CommandArgumentError(
                f"RelaxedTrailingEdge direction is {self.direction!r}, and the direction "
                f"value of the specification takes {_shedding_vocabulary()} "
                "(SRC-751 p.85). Pass None to leave the value unwritten, which means "
                "the axial direction"
            )

    @property
    def shedding_direction(self) -> str:
        """The direction this specification MEANS, stated or defaulted.

        Returns
        -------
        str
            ``"AXIAL"`` or ``"AZIMUTH"``. A specification carrying three
            values reads as ``"AXIAL"``, because that is the direction's
            documented default (SRC-751 p.85); use :attr:`direction` to
            tell that case from one that wrote the 0.
        """
        return self.direction or DEFAULT_SHEDDING_DIRECTION

    def with_shedding(self, direction: str | int) -> RelaxedTrailingEdge:
        """Return this specification stating one shedding direction.

        Parameters
        ----------
        direction : str or int
            ``"AXIAL"``/0 or ``"AZIMUTH"``/1, resolved by
            :func:`resolve_shedding_direction`.

        Returns
        -------
        RelaxedTrailingEdge
            A new specification. Asking for the axial direction on one
            that already leaves the direction unwritten returns it
            UNCHANGED, at three values: the two say the same thing, and
            writing the 0 would hand a four-value specification to a
            build that reads three.

        Raises
        ------
        CommandArgumentError
            If the direction is neither, naming the value and both.
        """
        token = resolve_shedding_direction(direction, context="with_shedding")
        if token == DEFAULT_SHEDDING_DIRECTION and self.direction is None:
            return self
        return replace(self, direction=token)

    def render(self) -> str:
        """Return the specification as a component definition writes it.

        Returns
        -------
        str
            The values, semicolon separated, with the direction's integer
            appended only where :attr:`direction` states one, and the
            ``Relaxed_TE`` keyword first where the text carried it.
        """
        fields = list(self.fields)
        if self.direction is not None:
            fields.append(str(RELAXED_SHEDDING_DIRECTIONS[self.direction]))
        if self.keyword:
            fields.insert(0, RELAXED_TE_KEYWORD)
        return ";".join(fields)


def parse_relaxed_trailing_edge(specification: str) -> RelaxedTrailingEdge:
    """Read one relaxed trailing-edge component specification.

    Accepts both shapes the editions print, with or without the leading
    ``Relaxed_TE`` keyword: the three values of SRC-750 p.85 (``u``,
    ``v1``, ``v2``) and the four of SRC-751 p.85, whose last value is the
    direction the relaxed wake sheds (SRC-752 p.85 unchanged).

    Parameters
    ----------
    specification : str
        The semicolon-separated line, as a component definition carries
        it, or its values without the keyword. Whitespace around a value
        is not part of it.

    Returns
    -------
    RelaxedTrailingEdge
        The parsed specification, whose :attr:`~RelaxedTrailingEdge.direction`
        is None where the text carried three values.

    Raises
    ------
    CommandArgumentError
        If the text is not a string, if it carries a value count that is
        neither of the two documented ones, if a value is blank, or if
        the direction is one the edition does not define. The direction
        refusal names the value and both accepted directions.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> helpers.parse_relaxed_trailing_edge("0.5; 0.1; 0.9; 1").shedding_direction
    'AZIMUTH'
    """
    if not isinstance(specification, str):
        raise CommandArgumentError(
            "parse_relaxed_trailing_edge takes the specification TEXT, a "
            "semicolon-separated field list as a component definition carries it, and "
            f"was given {type(specification).__name__} {specification!r}. This is a "
            "component-file field and not a command, so there is no emitter to convert "
            "typed arguments for it (SRC-752 p.85)"
        )
    fields = [field.strip() for field in specification.split(";")]
    keyword = fields[0].casefold() == RELAXED_TE_KEYWORD.casefold()
    if keyword:
        fields = fields[1:]
    if len(fields) not in (RELAXED_TE_FIELDS_WITHOUT_DIRECTION, RELAXED_TE_FIELDS_WITH_DIRECTION):
        raise CommandArgumentError(
            f"parse_relaxed_trailing_edge: {specification!r} carries {len(fields)} "
            f"value(s) after the {RELAXED_TE_KEYWORD} keyword, and the relaxed "
            f"trailing-edge component specification carries "
            f"{RELAXED_TE_FIELDS_WITHOUT_DIRECTION} (u, a chordwise or radial location, "
            f"and v1, v2, two bounds) or {RELAXED_TE_FIELDS_WITH_DIRECTION}, the last "
            "being the direction the relaxed wake sheds, which SRC-751 p.85 adds and "
            "SRC-750 p.85 does not print (SRC-752 p.85: Relaxed_TE;u;v1;v2;direction)"
        )
    blank = [position for position, field in enumerate(fields, start=1) if not field]
    if blank:
        raise CommandArgumentError(
            f"parse_relaxed_trailing_edge: {specification!r} leaves value(s) "
            f"{', '.join(str(position) for position in blank)} blank. Every value of "
            "the specification is written, so a blank one is a separator too many "
            "rather than a value left at its default; the only value with a default is "
            "the direction, and it is defaulted by leaving it OUT (SRC-752 p.85)"
        )
    if len(fields) == RELAXED_TE_FIELDS_WITHOUT_DIRECTION:
        return RelaxedTrailingEdge(fields=tuple(fields), keyword=keyword)
    direction = resolve_shedding_direction(
        fields[-1], context=f"parse_relaxed_trailing_edge: {specification!r}"
    )
    return RelaxedTrailingEdge(
        fields=tuple(fields[:RELAXED_TE_FIELDS_WITHOUT_DIRECTION]),
        direction=direction,
        keyword=keyword,
    )
