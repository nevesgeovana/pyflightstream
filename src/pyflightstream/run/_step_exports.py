"""Diagnostics of the package's own post-processing, shared by local runs and collection.

Two of them, and neither changes the solver's status: the missing-action
diagnostic, and the Tecplot surfaces the package failed to write from sources
the solver did write (0.30.0).
"""

from collections.abc import Mapping, Sequence
from pathlib import PurePath


def missing_step_warning(
    action_program: str | None,
    action_count: int | None,
    export_window: Mapping[str, object] | None,
    time_steps: int | None = None,
) -> str | None:
    """Warn when requested per-step actions have no recorded invocation.

    No warning is invented for steady runs or a run stopped before its requested
    export window. This says what the missing counter cannot establish; it does
    not assert that a file inspection or convergence assessment was performed.
    """
    if not action_program or not export_window or (action_count is not None and action_count > 0):
        return None
    first = export_window.get("first_step")
    if time_steps is not None and isinstance(first, (int, float)) and time_steps < first:
        return None
    return (
        "Missing per-step action evidence: the requested export counter recorded no completed "
        "step, so per-step exports are not confirmed. Final loads retain their assessed status. "
        f"Inspect the counter program {action_program} and its run log before using a step series."
    )


def untranslated_surfaces(
    translations: object, missing: Sequence[str], collected: Sequence[str]
) -> list[str] | None:
    """Say which missing outputs are only surfaces the package failed to translate.

    A declared Tecplot surface is written by the PACKAGE from the VTK (and the
    native Tecplot) the solver exported (G45 of 0.28.0), so a ``.dat`` that is
    missing after a translation failed is not an output the solver failed to
    produce: the solve completed, and demoting it to FAILED_INCOMPLETE_OUTPUT
    records a post-processing failure as the solver's (measured on 0.29.0 with
    a periodic row, 2026-09-28). The point keeps the solver's status and the
    record carries these sentences in ``warnings``.

    Parameters
    ----------
    translations : object
        The run's ``surface_translations`` after the translation pass, each with
        ``dat``, ``vtk``, optionally ``native_tecplot``, and ``problems``.
    missing : sequence of str
        The declared outputs that do not exist, as ``MissingOutputsError``
        names them.
    collected : sequence of str
        The outputs that were filed.

    Returns
    -------
    list of str or None
        One sentence per missing surface, naming the problems the translation
        recorded; None when any missing output is not such a surface, or when a
        source the solver was to write for it was not filed. A missing solver
        output then fails the point exactly as before.
    """
    if not missing or not isinstance(translations, list):
        return None
    entries = [entry for entry in translations if isinstance(entry, Mapping) and entry.get("dat")]
    by_name = {PurePath(str(entry["dat"])).name: entry for entry in entries}
    filed = {PurePath(str(name)).name for name in collected}
    said: list[str] = []
    for name in (PurePath(str(path)).name for path in missing):
        entry = by_name.get(name)
        if entry is None:
            return None
        sources = [
            PurePath(str(entry[key])).name
            for key in ("vtk", "native_tecplot")
            if entry.get(key) is not None
        ]
        if not sources or any(source not in filed for source in sources):
            return None
        problems = [str(problem) for problem in entry.get("problems") or []]
        said.append(
            f"{name} was not written: the solver completed and wrote "
            f"{' and '.join(sources)}, which are filed with the point, and the package's "
            "own translation of them failed ("
            + ("; ".join(problems) or "no reason was recorded")
            + "). The point keeps the solver's status."
        )
    return said
