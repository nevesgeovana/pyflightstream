# GEOVERSE_HEADER
# file_version: 1.0.0
# last_modified_at: 2026-09-27T14:27:00+00:00
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [Python standard library]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Diagnose missing per-step action evidence without changing solver status.
# revision_source: git
"""The missing-action diagnostic shared by local runs and submitted collection."""

from collections.abc import Mapping


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
