"""Names this package has RETIRED: refused on sight, with the replacement named.

Pipeline role: cross-cutting support module (no solver semantics).

WHY THIS IS NOT THE DEPRECATION LEDGER, which sits beside it in
:mod:`pyflightstream._deprecations`. A deprecation is a PROMISE: the old name
keeps working, warns, and disappears at a stated release. A retirement is a
REFUSAL: the old name stops working now, and the only thing owed to whoever
typed it is a message that says what it became and why.

The author's instruction of 2026-09-10, in her own words: "nao é para aceitar
nomenclatura antiga, TUDO rotor, lembra que eu disse que nao é versao estavel
ainda", and then "nomenclatura antiga é para dar erro com mensagem que aquela
nomenclatura foi depreciada e como corrigir". This package has no stable
release, so it owes no compatibility window for a word it chose badly; what it
owes is a refusal a reader can act on without opening the changelog.

WHAT MAKES A RETIREMENT LEGITIMATE, so that this module does not become the
place a breaking change goes to look tidy. Every entry here renames a WORD and
nothing else: the file that used the old spelling means exactly the same thing
after a search and replace, and the fix is one line of `sed`. A change that
alters what a file MEANS is a deprecation with a deadline, and belongs in the
ledger next door where the Tier 1 guard can see it.

ONE WORD FOR THE ROTATING THING. Three words named one object across three
artifacts: a reference block said ``engine``, a reference length said
``propeller``, a frame said ``PROP``. A reader had to learn which file used
which, and every one of them was a guess about the configuration. Rotor is the
general one: a propeller is a rotor, and so is a lift fan or a ducted rotor,
so nothing has to be renamed again when the aircraft changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyflightstream._errors import PyflightstreamError


class RetiredNameError(AttributeError, PyflightstreamError):
    """A retired ATTRIBUTE was reached for, and the message says what to write.

    IT HAS TWO PARENTS BECAUSE TWO READINGS ARE BOTH RIGHT. Reaching for a
    name this package no longer defines is an attribute mistake, so
    ``except AttributeError`` must keep catching it; and it is also this
    package refusing something on purpose, so the one category the
    documentation tells callers to catch,
    :class:`~pyflightstream._errors.PyflightstreamError`, must reach it too.
    A caller who wraps workspace work in that category was getting a
    traceback rather than the sentence the registry wrote for the moment.

    This is not a new pattern. :class:`~pyflightstream.cases.MatrixError`
    already inherits both ``PyflightstreamError`` and ``ValueError`` for the
    same reason, and the public exceptions module documents that pairing as
    the house shape. Here the second seat is ``AttributeError`` because that
    is the shape of the mistake being made.

    It carries no attributes of its own: the facts belong to the
    :class:`RetiredName` entry that produced the message, which is the one
    home for them.
    """


@dataclass(frozen=True)
class RetiredName:
    """One spelling this package refuses, and what it became.

    Attributes
    ----------
    owner : str
        Where the old spelling appeared, as a user meets it: ``the
        reference artifact``, ``a probe table``.
    old : str
        The retired spelling, exactly as it is written in a file or in
        code, so a reader can match it against what they typed.
    new : str
        What to write instead.
    retired_in : str
        The package version that stopped accepting ``old``.
    why : str
        One sentence of reason. It is part of the message because a
        rename with no reason reads as churn, and the next reader
        reverts it.
    """

    owner: str
    old: str
    new: str
    retired_in: str
    why: str

    def message(self, wrote: str | None = None) -> str:
        """Render the refusal text, which names the fix before the reason.

        Parameters
        ----------
        wrote : str, optional
            The spelling the user actually wrote, where several reach one
            entry. Without it the message names `old`, and a user who wrote
            `RotorAxis1` was told about `PROP_MRP`: a sentence asserting
            they wrote something they did not (the interface lens of the
            0.15.0 release review).

        Notes
        -----
        THE REPLACEMENT IS INTERPOLATED ONCE. Where `new` is a shape rather
        than a token it is a sentence of its own, and rendering it twice
        read as a stutter.
        """
        said = wrote or self.old
        return (
            f"{said} of {self.owner} is no longer accepted since v{self.retired_in}. "
            f"Write {self.new}. {self.why}"
        )


#: The reason shared by every rotor-word retirement, written once.
_THE_ROTOR_WORD = (
    "This package says ROTOR everywhere since 0.15.0, one word for the block, "
    "the key, the frame and the point: a propeller is a rotor, and so is a "
    "lift fan, so the general word is the one that never has to change again."
)

REFERENCE_PROPELLER_DIAMETER = RetiredName(
    owner="the reference artifact",
    old="propeller_diameter_m",
    new="rotor_diameter_m",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
REFERENCE_PROPELLER_TABLE = RetiredName(
    owner="the reference artifact",
    old="[propeller]",
    new="[rotor]",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
POINT_KIND_ENGINE = RetiredName(
    owner="a point of inputs/reference_points.toml",
    old='kind = "engine"',
    new='kind = "rotor"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
BLOCK_KIND_ENGINE = RetiredName(
    owner="a rotor block of the reference artifact",
    old='kind = "engine"',
    new='kind = "rotor"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
PROBE_SCALE_PROPELLER_RADIUS = RetiredName(
    owner="a probe table",
    old='scale = "propeller_radius"',
    new='scale = "rotor_radius"',
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)
WORKSPACE_ENGINE_POINT = RetiredName(
    owner="CampaignWorkspace",
    old="engine_point",
    new="rotor_point",
    retired_in="0.15.0",
    why=_THE_ROTOR_WORD,
)


#: WHY EACH RETIRED FRAME SPELLING WENT, and they did not all go for the same
#: reason: `PROP_MRP` and `ROTOR_MRP` were the ONE package-level rotor frame,
#: which a reference declaring several rotors cannot have; `RotorAxis<k>` and
#: the numbered `PROP_MRP<k>` were POSITIONAL, so a post-processing entry
#: citing one silently followed the ORDER of the MOTIONS list. Giving both the
#: rotor-word reason was a non-sequitur for the two that already said rotor
#: (the interface lens of the 0.15.0 release review).
_ONE_FRAME_FOR_SEVERAL_ROTORS = (
    "It was the package's ONE rotor frame, which is the one-propulsor "
    "assumption spelled out: a reference declares a block per rotor since "
    "0.15.0, and each rotor carries its own frames."
)
_A_NAME_THAT_WAS_AN_INDEX = (
    "It read as a name and was an INDEX into the row's own MOTIONS list, so "
    "an entry citing it followed the ORDER the records happened to be "
    "written in, and reordering the row moved the plot to another rotor "
    "with nothing saying so."
)

#: EVERY SPELLING A FRAME CITATION MAY CARRY FROM BEFORE 0.15.0, mapped to the
#: retirement that explains it. A citation matching any of these is refused
#: naming the shape to write, rather than falling through to "this run created
#: no such frame", which is true and says nothing about the rename.
_THE_ROTOR_FRAMES = (
    "the rotor's own frames, <ALIAS>_SMRP for its hub or <ALIAS>_RMRP for the "
    "frame that turns with it, where <ALIAS> is the name the reference gives "
    "that rotor"
)
RETIRED_FRAME_CITATIONS: dict[str, RetiredName] = {
    "PROP_MRP": RetiredName(
        owner="a frame citation",
        old="PROP_MRP",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_ONE_FRAME_FOR_SEVERAL_ROTORS,
    ),
    "ROTOR_MRP": RetiredName(
        owner="a frame citation",
        old="ROTOR_MRP",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_ONE_FRAME_FOR_SEVERAL_ROTORS,
    ),
    "ROTORAXIS": RetiredName(
        owner="a frame citation",
        old="RotorAxis<k>",
        new=_THE_ROTOR_FRAMES,
        retired_in="0.15.0",
        why=_A_NAME_THAT_WAS_AN_INDEX,
    ),
}


def retired_frame(name: str) -> RetiredName | None:
    """Return the retirement a cited frame name carries, or None.

    Parameters
    ----------
    name : str
        A frame name as a post-processing artifact or a ROTATE record
        writes it. Matched case folded, and with any trailing index
        stripped, because the positional forms carried one.
    """
    token = name.strip().upper().rstrip("0123456789")
    return RETIRED_FRAME_CITATIONS.get(token)


#: Every retirement, one entry each. Iterated by the input readers, which
#: match a file's own text against :attr:`RetiredName.old`, and by the Tier 1
#: guard that proves each one refuses.
#: THE FRAME RETIREMENTS ARE SPLICED IN rather than listed again. They are
#: three entries with three reasons and they live in the mapping the frame
#: reader asks; a second object for one of them made `RETIRED` and the
#: mapping disagree about `PROP_MRP`, which is the second-home defect this
#: module is written against and which its own Tier 1 guard caught.
RETIRED: tuple[RetiredName, ...] = (
    REFERENCE_PROPELLER_DIAMETER,
    REFERENCE_PROPELLER_TABLE,
    POINT_KIND_ENGINE,
    BLOCK_KIND_ENGINE,
    PROBE_SCALE_PROPELLER_RADIUS,
    WORKSPACE_ENGINE_POINT,
    *RETIRED_FRAME_CITATIONS.values(),
)


def retired_key(key: str) -> RetiredName | None:
    """Return the retirement a top-level artifact key names, if any.

    Parameters
    ----------
    key : str
        A key or table name read out of an input artifact, without
        brackets: ``propeller_diameter_m``, ``propeller``.

    Returns
    -------
    RetiredName or None
        The entry whose ``old`` this key is, or None.
    """
    wanted = {key, f"[{key}]"}
    return next((entry for entry in RETIRED if entry.old in wanted), None)


__all__ = [
    "BLOCK_KIND_ENGINE",
    "POINT_KIND_ENGINE",
    "PROBE_SCALE_PROPELLER_RADIUS",
    "REFERENCE_PROPELLER_DIAMETER",
    "REFERENCE_PROPELLER_TABLE",
    "RETIRED",
    "RETIRED_FRAME_CITATIONS",
    "RetiredName",
    "WORKSPACE_ENGINE_POINT",
    "retired_frame",
    "retired_key",
]
