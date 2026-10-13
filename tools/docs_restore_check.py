"""Audit the parenthesised groups removed by the published Docs Q5 pass.

Compare each touched page at 9c59050a^ and 9c59050a, excluding unpublished
pages. Whitespace is folded for comparison, while every reported group keeps
its original bytes. Balanced outer groups include nested examples and public
Markdown link destinations. Groups containing private locators stay removed.
The check is read-only and exits nonzero for any missing public occurrence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "9c59050a"
LOCATOR = re.compile(
    r"RPT-|PFS-|\b(?:N?FR|PLN|OPS|GOAL|GEO|QA|PYFS|AD|REV|DEC|SRS|SRC)-\d"
    r"|reports/|coordination/|C:/|C:\\|\bsession\b|\blane\b"
    r"|\b(?:WP\d|S\d|G\d+)\b|test_\w+",
    re.IGNORECASE,
)


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), *args]
    ).decode("utf-8")


def groups(text: str) -> list[tuple[int, int, str]]:
    """Read balanced outer groups, without crossing a paragraph boundary."""
    stack: list[int] = []
    found = []
    for offset, char in enumerate(text):
        if char == "\n" and offset and text[offset - 1] == "\n":
            stack.clear()
        if char == "(":
            stack.append(offset)
        elif char == ")" and stack:
            start = stack.pop()
            if not stack:
                found.append((start, offset + 1, text[start : offset + 1]))
    return found


def key(text: str) -> str:
    return re.sub(r"\s+", "", text)


def audit(current_ref: str | None = None) -> dict:
    pages = []
    for page in git("diff", "--name-only", f"{REVISION}^", REVISION, "--", "docs/").splitlines():
        if page.startswith("docs/unpublished/"):
            continue
        before = git("show", f"{REVISION}^:{page}")
        after = git("show", f"{REVISION}:{page}")
        available = Counter(key(group) for _, _, group in groups(after))
        current = key(
            git("show", f"{current_ref}:{page}")
            if current_ref
            else (ROOT / page).read_text(encoding="utf-8")
        )
        old_counts = Counter(key(group) for _, _, group in groups(before))
        surviving = Counter(key(group) for _, _, group in groups(after))
        restored = {group: max(0, current.count(group) - surviving[group]) for group in old_counts}
        removed = []
        for start, _, group in groups(before):
            normalized = key(group)
            if available[normalized]:
                available[normalized] -= 1
                continue
            if LOCATOR.search(group):
                continue
            present = restored[normalized] > 0
            restored[normalized] = max(0, restored[normalized] - 1)
            removed.append(
                {
                    "group": group,
                    "line": before.count("\n", 0, start) + 1,
                    "present": present,
                }
            )
        pages.append({"page": page, "groups": removed})
    return {
        "revision": REVISION,
        "pages": pages,
        "total": sum(len(page["groups"]) for page in pages),
        "missing": sum(not group["present"] for page in pages for group in page["groups"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the machine-readable audit")
    parser.add_argument("--current-ref", help="audit a Git revision instead of working-tree pages")
    args = parser.parse_args()
    result = audit(args.current_ref)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for page in result["pages"]:
            print(f"{page['page']}: {len(page['groups'])} removed non-locator groups")
            for group in page["groups"]:
                state = "present" if group["present"] else "MISSING"
                print(f"  line {group['line']}: {state} {group['group']!r}")
        print(f"Total: {result['total']} groups; {result['missing']} missing")
    return int(result["missing"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
