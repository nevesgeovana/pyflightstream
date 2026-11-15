"""The polar files of the 0.57.0 layout, found beside the new ones (PFS-2231).

The post writes only the family and group files (:mod:`pyflightstream.post._family_polar`).
A file of the earlier layout already in ``polars/`` is LEFT UNTOUCHED: it is not
rewritten, archived or removed, and each kind is named once in one warning whose
text the post-output design states, each ending with the pointer to the upgrade
note. :func:`retired_polar_files` reads the folder; :func:`warn_retired_polar_files`
says it and returns the old path of each file with the new one, for the manifest.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamWarning, warn

__all__ = [
    "RetiredPolar",
    "is_retired_layout",
    "retired_polar_files",
    "warn_retired_polar_files",
]

#: What every warning of the migration ends with.
UPGRADE_POINTER = "See docs/upgrading.md#0580-post-tree."

#: The file names of the new layout, which are never the old one's.
_NEW = re.compile(
    r"^(FAM-(DIM|ACOEF|RCOEF)-P.+\.csv|P[^-]+-.+-(DIM|ACOEF|RCOEF)(_trim|_at_[^/]+|_merge)?\.(csv|dat))$"
)

#: The campaign sweep table of 0.57.0, beside the products of a matrix (design section 2.2).
_SWEEP_TABLE = "campaign_sweep.csv"
_SWEEP_SENTENCE = (
    "campaign_sweep.csv is retired: each polar's TOTAL group file is complete, and the guide "
    "(docs/pproc/index.md#joining-polars) joins several."
)

_SUPER = re.compile(r"^SUPER-(?P<sim>[^-]+)-.+\.(csv|dat)$")
_UNSTEADY = re.compile(r"^P(?P<sim>[^_/-]+)_(?P<name>.+)_uns_avg\.csv$")
_ROTOR = re.compile(r"^P(?P<sim>[^-]+)-(?P<alias>.+)_rotor\.csv$")
_NUMBERED = re.compile(
    r"^P(?P<sim>[^-]+)-(?P<sweep>[^_]+)_g(?P<number>[0-9]+)(?P<rest>_trim|_at_.+)?\.(csv|dat)$"
)
#: The sweep or point name of a 0.57.0 file holds no underscore, so the group is
#: everything after the first one (a group name may hold underscores).
_GROUP = re.compile(
    r"^P(?P<sim>[^-]+)-(?P<sweep>[^_]+)_(?P<group>.+?)(?P<rest>_trim|_at_.+)?\.(csv|dat)$"
)
#: Products derived from the 0.57.0 files whose writers are not this module's:
#: kept untouched, and not said here.
_KEPT_QUIET = re.compile(r"^P.+(_merge|_cn_slope)\.csv$")
#: The quasi-steady rotor tables, which 0.58.0 still writes under these names
#: (design section 1): current products, never of the earlier layout.
_CURRENT = re.compile(r"^P.+(_qs_avg|_qs_positions)\.csv$")


@dataclass(frozen=True)
class RetiredPolar:
    """One earlier-layout file: its kind, its name, its new counterpart and its sentence."""

    kind: str
    old: str
    new: str
    sentence: str


def is_retired_layout(name: str) -> bool:
    """Return whether a product path under ``polars/`` is a 0.57.0 polar file.

    Parameters
    ----------
    name : str
        The path relative to the products folder (``polars/<file>``).

    Returns
    -------
    bool
        Whether the file is of the earlier layout, which the post leaves untouched.

    Examples
    --------
    >>> is_retired_layout("polars/SUPER-6001-M200AL+sweepBE+000_WING.csv")
    True
    >>> is_retired_layout("polars/P6001-WING-ACOEF.csv")
    False
    """
    folder, _, file = name.partition("/")
    if folder != "polars" or not file or "/" in file:
        return False
    if _NEW.match(file) or _CURRENT.match(file):
        return False
    return _classify(file, lambda _sim, _alias: None) is not None or bool(_KEPT_QUIET.match(file))


def _classify(file: str, rotor_id: Callable[[str, str], int | None]) -> RetiredPolar | None:
    old = f"polars/{file}"
    if _CURRENT.match(file):
        return None
    if file == _SWEEP_TABLE:
        return RetiredPolar(
            "campaign_sweep",
            old,
            "polars/P<POL>-TOTAL-ACOEF.csv",
            _SWEEP_SENTENCE,
        )
    if match := _SUPER.match(file):
        pol = match["sim"]
        return RetiredPolar(
            "SUPER",
            old,
            f"polars/FAM-ACOEF-P{pol}.csv",
            f"The SUPER file is retired; every family is in FAM-DIM-P{pol}.csv and "
            f"FAM-ACOEF-P{pol}.csv, the run condition in their run block, and the setup codes "
            "in settings/.",
        )
    if match := _UNSTEADY.match(file):
        pol = match["sim"]
        return RetiredPolar(
            "uns_avg",
            old,
            f"polars/FAM-ACOEF-P{pol}.csv",
            f"{file} is the 0.57.0 unsteady polar; 0.58.0 writes the window average of every "
            f"family in FAM-*-P{pol}.csv and of every group in its group files, under the same "
            "names as a steady polar.",
        )
    if match := _ROTOR.match(file):
        pol, alias = match["sim"], match["alias"]
        new = f"P{pol}-{alias}-RCOEF.csv"
        stated = rotor_id(pol, alias)
        ident = "<id>" if stated is None else str(stated)
        return RetiredPolar(
            "rotor",
            old,
            f"polars/{new}",
            f"The rotor table is retired; rotor {alias} (id {ident}) is the group of its own "
            f"RCOEF file, {new}; its J, tip and helical Mach numbers are in the run block as "
            f"J{ident}, MTIP{ident}, MHEL{ident}.",
        )
    if _KEPT_QUIET.match(file):
        return None
    if match := _NUMBERED.match(file):
        pol, number = match["sim"], f"g{int(match['number']):02d}"
        return RetiredPolar(
            "numbered",
            old,
            f"polars/P{pol}-{number}-ACOEF.csv",
            f"{file} names its group by number; 0.58.0 writes it as group {number}; name the "
            "group in [groups] to name its files.",
        )
    if match := _GROUP.match(file):
        pol, group = match["sim"], match["group"]
        return RetiredPolar(
            "group",
            old,
            f"polars/P{pol}-{group}-ACOEF.csv",
            f"{file} is the 0.57.0 per-group, per-Mach polar; 0.58.0 writes one file set per "
            f"polar: the families in FAM-DIM, FAM-ACOEF and FAM-RCOEF-P{pol}.csv and the group "
            f"{group} in its own group files.",
        )
    return None


def retired_polar_files(
    out: Path, rotor_id: Callable[[str, str], int | None] | None = None
) -> list[RetiredPolar]:
    """Return every earlier-layout file under ``out/polars``, in name order.

    Parameters
    ----------
    out : Path
        The products folder of one matrix.
    rotor_id : callable, optional
        ``(pol, alias) -> id`` of a rotor the reference declares today, for the
        rotor table's sentence; None writes ``<id>``.

    Returns
    -------
    list of RetiredPolar
        The files found, each with its kind, its new counterpart and its sentence.
    """
    folder = out / "polars"
    lookup = rotor_id or (lambda _pol, _alias: None)
    found: list[RetiredPolar] = []
    if (out / _SWEEP_TABLE).is_file():
        found.append(
            RetiredPolar(
                "campaign_sweep", _SWEEP_TABLE, "polars/P<POL>-TOTAL-ACOEF.csv", _SWEEP_SENTENCE
            )
        )
    if not folder.is_dir():
        return found
    for path in sorted(folder.iterdir()):
        if not path.is_file() or _NEW.match(path.name):
            continue
        retired = _classify(path.name, lookup)
        if retired is not None:
            found.append(retired)
    return found


def warn_retired_polar_files(
    out: Path, rotor_id: Callable[[str, str], int | None] | None = None
) -> dict[str, str]:
    """Say the earlier-layout files of ``out/polars``, one warning per kind.

    Parameters
    ----------
    out : Path
        The products folder of one matrix.
    rotor_id : callable, optional
        As :func:`retired_polar_files`.

    Returns
    -------
    dict of str to str
        Each old path with its new counterpart, relative to ``out``.
    """
    found = retired_polar_files(out, rotor_id)
    by_kind: dict[str, list[RetiredPolar]] = {}
    for retired in found:
        by_kind.setdefault(retired.kind, []).append(retired)
    for retired_kind in by_kind.values():
        sentences = list(dict.fromkeys(retired.sentence for retired in retired_kind))
        warn(" ".join([*sentences, UPGRADE_POINTER]), PyflightstreamWarning, stacklevel=3)
    return {retired.old: retired.new for retired in found}


def rotor_ids_of(rotors: Mapping[str, object]) -> dict[str, int]:
    """Return each rotor's declared id by alias, case-folded."""
    return {
        str(alias).casefold(): int(getattr(block, "id", 0) or 0) for alias, block in rotors.items()
    }
