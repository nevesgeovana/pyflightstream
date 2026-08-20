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

WHAT IS DELIBERATELY NOT HERE. ``fsi.config.config_sha256`` also computes
a sha256, over a canonical JSON rendering of a configuration. It is not
a file digest and not the manifest checksum this module is about, and
folding it in would put a domain rule, what the canonical form of a
configuration IS, inside a module whose whole purpose is to hold no
domain rule. It is named rather than skipped so the omission does not
read as an oversight.

THE HASHING RULE ITSELF (NFR-15), stated here because this is the module
that answers for it. Three parts, and the second is the one that was
missing:

* THE ALGORITHM is sha256, everywhere, and it is :data:`ALGORITHM`
  rather than a sentence, so a test can spend it. Nothing in this
  package computes a digest under another algorithm, and none picks its
  constructor at run time: an algorithm chosen from a variable is a
  property of the input rather than of the code, and a value written
  into a committed manifest and cited by a publication cannot be that.
* THE CANONICAL FORM is per digest, and that is why it is a MAPPING and
  not a paragraph. "sha256" says nothing about whether two identical
  runs agree; what decides that is the exact byte string fed to the
  hash. :data:`CANONICAL_FORMS` names it for every module in this
  package that computes one, and ``tests/test_digest.py`` fails when a
  module hashes without declaring one. A rule written only as prose
  cannot notice a fourth site appearing.
* THE EXCLUSIONS, :data:`EXCLUDED_FROM_EVERY_DIGEST`, hold for all of
  them: no wall-clock time, no elapsed time, no absolute path, nothing
  about the machine or the user. Those are the fields that differ
  between two runs which are otherwise the same run, so admitting one
  would make the digest answer a question nobody asked. They are absent
  by CONSTRUCTION rather than by filtering: every canonical form below
  is either the raw bytes of a file or a text this package renders from
  validated data, and none of them reads a clock, a path or an
  environment. Each entry is SPENT rather than declared:
  ``tests/test_digest.py`` requires one demonstration per entry, three
  of them by hashing (a modification time that moves, the same bytes
  under two names, two files hashed in both orders) and two by scanning
  this module's own source, because no fixture can show that a clock
  was not read. An exclusion cannot be added, narrowed or deleted
  without a measurement moving with it.

WHERE THE RULE IS STATED FOR A USER. This docstring is the home of the
rule, and a user staging a mesh does not read it. ``docs/mesh-inputs.md``
is the page that asks a reader to rely on the manifest checksum, so it
names the algorithm and the exclusions in prose and points back here;
``tests/test_digest.py`` fails on a docs page that promises a content
hash and names neither, so the page cannot go stale quietly and a
changed :data:`ALGORITHM` breaks it rather than agreeing with it.

The boundary, stated rather than implied: the digest is reproducible for
one canonical form, not across platforms for one CONCEPT. A file digest
reads bytes, so a text file checked out with different line endings on
two platforms is a different file and hashes differently. That is the
digest being correct about the file rather than wrong about the content,
and the choice is deliberate; where a comparison must survive that,
:func:`text_sha256` over decoded text is the tool.
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

#: The one hash algorithm this package computes, as a value a test can
#: spend rather than a word in a docstring. Changing it changes every
#: digest in every committed manifest, so it is a public break with a
#: changelog entry, never an edit.
ALGORITHM = "sha256"

#: What is kept OUT of every digest, whatever its canonical form. These
#: are precisely the fields that differ between two runs which are the
#: same run, so admitting one would make the digest disagree about runs
#: that agree. Stated as data so the rule has one home.
EXCLUDED_FROM_EVERY_DIGEST = (
    "wall-clock timestamps",
    "elapsed and wall time",
    "absolute paths, and any path at all",
    "the machine, the user and the environment the run happened on",
    "the order in which files were staged",
)

#: The canonical form each digest-computing module of this package feeds
#: to :data:`ALGORITHM`, keyed by module path under ``src/pyflightstream``.
#:
#: This is the part of the rule that was never written down, and the
#: reason it is a mapping is that "sha256" alone decides nothing: two
#: runs agree exactly when the BYTE STRING handed to the hash agrees, and
#: that is chosen at the call site. ``tests/test_digest.py`` walks the
#: package for every ``hashlib`` call and fails on a module absent here,
#: so a new digest cannot enter with its canonical form unstated.
CANONICAL_FORMS = {
    "_digest.py": (
        "the raw bytes of a file, read in blocks and never decoded; or the "
        "UTF-8 encoding of a string. Nothing else is read: not the path, not "
        "the size, not any timestamp. This is the manifest checksum, the one "
        "every input, output, staged script and solver executable is recorded "
        "under."
    ),
    "fsi/config.py": (
        "the JSON rendering of a validated FsiConfig with sorted keys and no "
        "whitespace, UTF-8 encoded. A domain rule rather than a file digest: "
        "it says two CONFIGURATIONS are the same physics, so it is deliberately "
        "independent of field order and formatting, which a byte digest of "
        "config.json would not be."
    ),
    "qa/physics.py": (
        "the raw bytes of the geometry file a QA reference was measured on. It "
        "identifies the case behind a committed reference without committing "
        "the geometry, which invariant 5 forbids; it is not a manifest field "
        "and never enters a run record."
    ),
}

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
