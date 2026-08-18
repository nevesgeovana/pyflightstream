"""The sha256 this package uses to say two runs used the same inputs.

Pipeline role: below every layer, imported by all of them. It imports
nothing from this package, which is the whole reason it exists as a
separate module and is exactly why :mod:`pyflightstream._errors` does
too: the workspace layer and the run layer both need this digest, and
neither may import the other to get it.

WHY IT IS A MODULE AND NOT THREE COPIES. NFR-07's claim is that two runs
with the same inputs are recognisably the same run, and until 2026-08-18
that claim rested on a definition written in three places:
``workspace._sha256``, ``run._file_digest`` and, for text, an inline
expression in ``run._recipe_digest`` and another in ``qa.probes``.
Nothing stopped two of them diverging and nothing would have noticed if
they had; the manifest would simply have said two identical runs were
different, or two different runs the same. The run layer had already
reached across a layer boundary to import ``workspace._sha256``, an
underscore-private name, rather than write a fourth.

THE TWO FILE FUNCTIONS DIFFER ONLY IN THEIR FAILURE POLICY, and that is
why there are two rather than a flag. :func:`file_sha256` raises;
:func:`optional_file_sha256` returns ``None``. A caller who picks the
wrong one gets either a run that dies on a provenance field or a
manifest that silently records nothing, so the policy is carried by the
NAME and stated in both docstrings rather than left to a keyword a
reader has to look up.

WHAT IS DELIBERATELY NOT HERE. ``fsi.config.config_hash`` also computes
a sha256, over a canonical JSON rendering of a configuration. It is not
a file digest and not the manifest checksum this module is about, and
folding it in would put a domain rule, what the canonical form of a
configuration IS, inside a module whose whole purpose is to hold no
domain rule. It is named rather than skipped so the omission does not
read as an oversight.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Bytes read per block. Not a tuning parameter: it is the value all
#: three former implementations already used, kept so that every digest
#: this package has ever written stays reproducible. The digest of a
#: file does not depend on it, but pinning it here stops a later reader
#: from thinking it might.
_BLOCK = 65536

__all__ = ["file_sha256", "optional_file_sha256", "text_sha256"]


def file_sha256(path: str | Path) -> str:
    """Return the sha256 of a file's bytes, reading it in blocks.

    Parameters
    ----------
    path : str or Path
        The file to hash. It is opened in binary mode and never
        decoded, so a text file's line endings are part of the digest,
        which is what makes the digest a statement about the FILE
        rather than about its content as read on one platform.

    Returns
    -------
    str
        Lowercase hexadecimal sha256.

    Raises
    ------
    OSError
        If the file cannot be opened or read. That is deliberate and is
        the whole difference from :func:`optional_file_sha256`: a
        workspace staging an input it cannot read has nothing to record
        and must say so, where a run recording the provenance of a
        solver executable must not die over it.

    See Also
    --------
    optional_file_sha256 : the same digest, ``None`` on ``OSError``.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def optional_file_sha256(path: str | Path) -> str | None:
    """Return the sha256 of a file's bytes, or ``None`` when unreadable.

    Parameters
    ----------
    path : str or Path
        The file to hash.

    Returns
    -------
    str or None
        Lowercase hexadecimal sha256, or ``None`` if the file could not
        be opened or read.

    Notes
    -----
    ``None`` rather than a raise, and the reason is a policy rather than
    a convenience: a missing or unreadable solver executable is the
    executor's problem to report, with the diagnosis it can give, and a
    PROVENANCE field must never be the thing that fails a run. A caller
    who needs the digest to exist wants :func:`file_sha256` instead.

    Where the digest is absent the record says so with ``None``, which
    is a different claim from recording a digest of nothing.
    """
    try:
        return file_sha256(path)
    except OSError:
        return None


def text_sha256(text: str) -> str:
    """Return the sha256 of a string's UTF-8 encoding.

    Parameters
    ----------
    text : str
        The text to hash, for example a rendered script or the source
        of a recipe function.

    Returns
    -------
    str
        Lowercase hexadecimal sha256.

    Notes
    -----
    UTF-8 is named here rather than left to a default because the
    digest is written into committed records: an encoding chosen by the
    platform would make the same text hash differently on two machines,
    which is the opposite of what a same-inputs claim needs.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
