"""P0400-SCISSORS (PFS-2135.042): the trailer hook accepts a valid message under commit -v.

The hook dropped every ``#`` line, the scissors line included, so the diff
``git commit -v`` writes below it became the message's last paragraph and git
interpret-trailers no longer read the Clean-room trailer above it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "scripts" / "check_clean_room_trailer.py"
TRAILERS = (
    "Clean-room: emitter specified from the official manual and probe evidence only; "
    "no code, structure or docstrings from the AGPL predecessor\n"
    "Co-Authored-By: Someone <someone@example.com>\n"
)
VERBOSE = (
    "# Please enter the commit message for your changes.\n"
    "# ------------------------ >8 ------------------------\n"
    "# Do not modify or remove the line above.\n"
    "diff --git a/x.py b/x.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
    "@@ -1 +1 @@\n"
    "-a = 1\n"
    "+a = 2\n"
)


def _hook(tmp_path: Path, text: str) -> int:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(HOOK), str(message)], capture_output=True, check=False
    ).returncode


def test_p0400_scissors_a_valid_message_under_commit_v_passes(tmp_path: Path) -> None:
    """P0400-SCISSORS: the trailers stay the last paragraph; the diff below the cut is ignored."""
    assert _hook(tmp_path, f"subject\n\nbody.\n\n{TRAILERS}\n{VERBOSE}") == 0


def test_p0400_scissors_a_misplaced_trailer_is_still_refused(tmp_path: Path) -> None:
    """P0400-SCISSORS: the control: a trailer followed by another paragraph is still refused."""
    assert _hook(tmp_path, f"subject\n\n{TRAILERS}\nanother paragraph.\n\n{VERBOSE}") == 1
