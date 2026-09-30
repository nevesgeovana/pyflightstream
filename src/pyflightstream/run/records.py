"""The run records of a workspace: which manifest, its restore and its rebuild.

Pipeline role: the run row, beside the manifest the run stage writes. It is
the 0.32.0 home of three operations on the records of a campaign workspace,
laid down as a contract before the work package that fills it (B1), so the
packages that call it (B2, the sync; B3, the post and collect with
``--runs``) code against fixed signatures:

* :func:`resolve_manifest` names the manifest file a command reads: the
  default ``runs.json``, or another file directly in the workspace root
  (``pyfs-matrix post --runs NAME`` and its siblings). It is implemented.
* :func:`restore` brings a file of the records family back from the
  workspace's ``archive/``: the manifest, the storage record, a matrix's
  products record, the plan receipt or the additional-post record (the
  kinds of :data:`RESTORE_KINDS`). A contract stub until B1 fills it.
* :func:`rebuild` reconstructs run records from the simulation folders under
  ``sims/``. A contract stub until B1 fills it.

Every stub refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError` and the words
"not implemented yet (0.32.0 contract)". A refused manifest name is a
:class:`RunsManifestError`.

The module imports only the floor, so the workspace row may import it too.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import ContractNotImplementedError, PyflightstreamError

#: The manifest a workspace keeps its run records in, and the name
#: :func:`resolve_manifest` returns when no other is named.
DEFAULT_MANIFEST = "runs.json"

#: The file kinds :func:`restore` brings back from ``archive/``.
RESTORE_KINDS = ("runs", "storage", "products", "plan", "additional")

_NOT_YET = "not implemented yet (0.32.0 contract)"


class RunsManifestError(PyflightstreamError, ValueError):
    """A manifest name that does not name a file directly in the workspace root.

    ValueError because the refused thing is the NAME a caller passed, before
    any file is read.
    """


def resolve_manifest(root: str | Path, runs: str | None = None) -> Path:
    """Return the manifest file a command reads in the workspace ``root``.

    Parameters
    ----------
    root : str or Path
        The workspace root, the folder that holds ``runs.json``.
    runs : str, optional
        The manifest's file name. None means ``runs.json``. A name is a file
        directly in ``root``: it must end in ``.json`` and carry no path
        separator, no drive and nothing that leaves the root.

    Returns
    -------
    Path
        ``root / runs``. Whether the file exists is not asked: a command that
        writes a new manifest resolves its name here too.

    Raises
    ------
    RunsManifestError
        When ``runs`` is empty, carries a separator or a drive, does not end in
        ``.json``, has no name before ``.json``, or resolves outside ``root``.
    """
    base = Path(root)
    if runs is None:
        return base / DEFAULT_MANIFEST
    separators = {"/", "\\", os.sep, *([os.altsep] if os.altsep else [])}
    if not runs or any(mark in runs for mark in separators):
        raise RunsManifestError(
            f"the manifest name {runs!r} is not a file name: name a file directly in the "
            f"workspace root {base}, such as runs-rebuilt.json, with no folder in it"
        )
    if not runs.endswith(".json") or runs == ".json":
        raise RunsManifestError(
            f"the manifest name {runs!r} does not end in .json: a manifest is a JSON file "
            f"directly in the workspace root {base}"
        )
    candidate = base / runs
    inside = Path(os.path.abspath(candidate)).parent == Path(os.path.abspath(base))
    if Path(runs).drive or Path(runs).anchor or not inside:
        raise RunsManifestError(
            f"the manifest name {runs!r} resolves outside the workspace root {base}; name a "
            "file directly in it"
        )
    return candidate


def restore(
    root: str | Path,
    kind: str,
    *,
    stamp: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Restore one file of the records family from the workspace's ``archive/``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    kind : str
        One of :data:`RESTORE_KINDS`.
    stamp : str, optional
        The archive stamp to restore from.
    apply : bool, default False
        Change files; without it the call previews and changes nothing.

    Returns
    -------
    dict
        The record of what was restored, or would be.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package B1 fills this body.
    """
    raise ContractNotImplementedError(f"pyflightstream.run.records.restore: {_NOT_YET}")


def rebuild(
    root: str | Path,
    *,
    out: str | None = None,
    all_sims: bool = False,
    sims: Sequence[str] | None = None,
    build_alias: Mapping[str, str] | None = None,
    matrix: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Rebuild run records from the simulation folders under ``sims/``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    out : str, optional
        The manifest file the rebuilt records go to, a name
        :func:`resolve_manifest` accepts.
    all_sims : bool, default False
        Rebuild every simulation folder on disk, recorded or not.
    sims : sequence of str, optional
        The simulation ids to rebuild.
    build_alias : mapping of str to str, optional
        The scheduler name of a solver build, keyed by the build.
    matrix : str or Path, optional
        The matrix revision the simulations ran from.
    apply : bool, default False
        Write files; without it the call previews and writes nothing.

    Returns
    -------
    dict
        The record of what was rebuilt, or would be.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package B1 fills this body.
    """
    raise ContractNotImplementedError(f"pyflightstream.run.records.rebuild: {_NOT_YET}")
