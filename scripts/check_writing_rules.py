"""Measure SRS writing rules; lexical flags require review, not automatic rewriting.

Run without options for working-tree counts. Use --baseline for the ratchet and
--receipt PATH to attest the clean committed tree against that baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from ._requirements_paths import REQUIREMENTS_DIR, read_requirements, requirement_rows
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _requirements_paths import REQUIREMENTS_DIR, read_requirements, requirement_rows

VAGUE = (
    "adequate appropriate easy efficient fast flexible sufficient significant "
    "user-friendly quickly normally typically several some"
).split()
ESCAPE = (
    "if necessary|as appropriate|where possible|when possible|as required|"
    "if practicable|as needed|when available|where available|to the extent possible"
).split("|")
OPEN = "including but not limited to|and so on|etc|such as|for example".split("|")
IMPL = (
    "numpy|pandas|pydantic|pyyaml|trimesh|subprocess|thread|mutex|singleton|"
    "regular expression|regex|dictionary|dataclass"
).split("|")
PRONOUN = "it its they them their this these those someone something".split()
VERBS = (
    "(?:accept|add|allow|apply|check|collect|compute|create|delete|emit|ensure|expose|fail|"
    "identify|keep|name|preserve|produce|read|record|refuse|reject|remove|report|return|run|"
    "save|select|store|support|validate|verify|write)(?:s|es)?"
)
RULES = {
    "W01": ("R1; R18", "Exactly one shall", "lexical"),
    "W02": ("R18; R19", "Multiple-obligation cues", "heuristic"),
    "W03": ("R7", "Vague lexicon", "lexical-review"),
    "W04": ("R8", "Escape-clause lexicon", "lexical-review"),
    "W05": ("R15; R17", "Ambiguous and/or", "lexical"),
    "W06": ("R9; R22", "Unbounded-list cues", "lexical-review"),
    "W07": ("R2; R3", "System subject and active-form cues", "heuristic"),
    "W08": ("R24", "Pronoun antecedent review", "heuristic"),
    "W09": ("R31", "Implementation-prescription cues", "heuristic"),
    "W10": ("A8 (attribute, not R rule)", "Explicit verification method", "metadata"),
    "W11": ("R18; R39 (local threshold)", "More than 40 words", "local-metric"),
}


def plain(t):
    """Normalize Markdown literal delimiters and whitespace for lexical matching."""
    return re.sub("\\s+", " ", t.replace(chr(96), "")).strip()


def hits(t, lex):
    """Find lexicon entries on word boundaries."""
    return [v for v in lex if re.search("(?<!\\w)" + re.escape(v) + "(?!\\w)", t, re.I)]


def words(t):
    """Count words using the research checker's local token convention."""
    return re.findall("[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)*", plain(t))


def check(r):
    """Return writing-rule flags for one authored statement and its metadata."""
    t = plain(r["statement"])
    low = t.lower()
    f = {}
    n = len(re.findall("\\bshall\\b", low))
    if n != 1:
        f["W01"] = f"shall_count={n}"
    cues = []
    if len(re.findall("\\b(?:shall|must)\\b", low)) > 1:
        cues.append("multiple obligation modals")
    if re.search("[.!?]\\s+[A-Z]", t):
        cues.append("multiple sentence cue")
    if re.search("\\b(?:and|then|but|otherwise)\\s+(?:shall\\s+|must\\s+)?" + VERBS + "\\b", low):
        cues.append("joined action cue")
    if cues:
        f["W02"] = "; ".join(cues)
    for rule, lex in (("W03", VAGUE), ("W04", ESCAPE), ("W06", OPEN)):
        h = hits(t, lex)
        if h:
            f[rule] = "; ".join(h)
    if re.search("\\band\\s*/\\s*or\\b", low):
        f["W05"] = "and/or"
    subject = re.search("(?:^|,\\s*)(?:the system|pyflightstream|the package)\\s+shall\\b", low)
    passive = re.search(
        "\\bshall\\s+(?:not\\s+)?be\\s+(?:\\w+ly\\s+)?(?:\\w+ed|written|shown|given|known|built|read|run|held|taken|made)\\b",
        low,
    )
    if not subject or passive:
        f["W07"] = "; ".join(
            x
            for x in (
                "no approved system subject before shall" if not subject else "",
                "passive-form cue" if passive else "",
            )
            if x
        )
    h = hits(t, PRONOUN)
    if h:
        f["W08"] = "antecedent requires review: " + "; ".join(h)
    h = hits(t, IMPL)
    internal = [
        v
        for v in re.findall(chr(96) + "([^" + chr(96) + "]+)" + chr(96), r["statement"])
        if re.search("(?:\\w+\\.\\w+\\(|^_|::|\\.py\\b)", v)
    ]
    if h or internal:
        f["W09"] = "design-constraint rationale requires review: " + "; ".join(h + internal)
    if r.get("verification_method", "").lower() not in {
        "test",
        "analysis",
        "inspection",
        "demonstration",
    }:
        f["W10"] = "no explicit authored verification method"
    if len(words(t)) > 40:
        f["W11"] = f"word_count={len(words(t))}; threshold=40"
    return f


def self_test():
    """Exercise a clean statement, eleven planted defects and boundary controls."""
    good = {
        "statement": "The system shall record the run identifier.",
        "verification_method": "test",
    }
    defects = {
        "W01": "The system records the run identifier.",
        "W02": "The system shall record the identifier and delete the input.",
        "W03": "The system shall produce adequate results.",
        "W04": "The system shall record the identifier if necessary.",
        "W05": "The system shall store text and/or numbers.",
        "W06": "The system shall store names, dates, etc.",
        "W07": "The result shall be written by the system.",
        "W08": "The system shall record it.",
        "W09": "The system shall use numpy to compute the result.",
        "W10": good["statement"],
        "W11": "The system shall record " + "identifier " * 41 + ".",
    }
    assert not check(good), check(good)
    controls = []
    for rule, t in defects.items():
        r = {**good, "statement": t}
        if rule == "W10":
            r["verification_method"] = ""
        f = check(r)
        assert rule in f, (rule, r)
        controls.append({"rule": rule, "planted": r, "refused": True, "reason": f[rule]})
    assert "W07" in check({**good, "statement": "The system shall be recorded."})
    assert "W07" not in check(
        {**good, "statement": "When the run ends, the system shall record the result."}
    )
    assert "W03" not in check({**good, "statement": "The system shall store the breakfast label."})
    assert "W09" not in check({**good, "statement": "The system shall store the JSON output."})
    assert "W08" in check({**good, "statement": "The system shall record its identifier."})
    assert "W11" not in check({**good, "statement": " ".join(["word"] * 40)})
    assert "W11" in check({**good, "statement": " ".join(["word"] * 41)})
    return controls


def controls():
    """Prove all eleven detectors against planted defects and a clean row."""
    return {row["rule"]: row["refused"] for row in self_test()}


def compare_baseline(counts, baseline):
    """Return all schema and ratchet failures, including absent rule counts."""
    limits = baseline.get("rules", {})
    if set(counts) != set(RULES) or set(limits) != set(RULES):
        return ["baseline and measurement must contain exactly W01 to W11"]
    return [
        f"{rule}: invalid count or baseline exceeded ({counts[rule]} > {limits[rule]})"
        for rule in RULES
        if type(counts[rule]) is not int
        or type(limits[rule]) is not int
        or counts[rule] < 0
        or limits[rule] < 0
        or counts[rule] > limits[rule]
    ]


def git(root, *args):
    """Read Git with the same UTF-8 stripped hash domain as the release reader."""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=os.environ.copy(),
    ).stdout.strip()


def digest(data):
    """Hash the exact supplied bytes."""
    return hashlib.sha256(data).hexdigest()


def committed_inputs(root, head):
    """Hash every input consumed by arm R and read statements from that commit."""
    paths = [
        path
        for path in git(
            root, "ls-tree", "-r", "--name-only", head, REQUIREMENTS_DIR.as_posix()
        ).splitlines()
        if path.endswith(".md")
    ]
    rows = []
    inputs = {}
    for path in paths:
        value = git(root, "show", f"{head}:{path}")
        inputs[path] = digest(value.encode("utf-8"))
        rows.extend(requirement_rows(value, path))
    if not rows or len({row["uid"] for row in rows}) != len(rows):
        raise ValueError("empty requirements or duplicate UID")
    for path in (
        "docs/srs/numerical-laboratory-method.md",
        "docs/srs/uid-migration.csv",
        "docs/srs/reserved-ids.json",
        "scripts/check_writing_rules.py",
    ):
        inputs[path] = digest(git(root, "show", f"{head}:{path}").encode("utf-8"))
    return [row for row in rows if row["status"] != "retired"], inputs


def main(argv=None):
    """Measure the working tree or attest a committed tree against a baseline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    tested = controls()
    if args.self_test:
        print(json.dumps({"controls": tested}, sort_keys=True))
        return 0
    root = args.root.resolve()
    inputs = {}
    head = git(root, "rev-parse", "HEAD")
    if args.receipt:
        if not args.baseline:
            parser.error("--receipt requires --baseline")
        if git(root, "status", "--porcelain"):
            parser.error("--receipt requires a clean committed tree")
        if Path(__file__).resolve() != root / "scripts/check_writing_rules.py":
            parser.error("receipt checker must execute from the measured tree")
        rows, inputs = committed_inputs(root, head)
    else:
        rows = read_requirements(root, live_only=True)
    findings = {row["uid"]: check(row) for row in rows}
    counts = {rule: sum(rule in found for found in findings.values()) for rule in RULES}
    baseline_bytes = args.baseline.read_bytes() if args.baseline else None
    failures = (
        compare_baseline(counts, json.loads(baseline_bytes)) if baseline_bytes is not None else []
    )
    result = {"rules": counts, "controls": tested, "live_rows": len(rows), "failures": failures}
    log = json.dumps(result, indent=2) + "\n"
    print(log, end="")
    status = int(bool(failures))
    if args.receipt:
        if git(root, "rev-parse", "HEAD") != head or git(root, "status", "--porcelain"):
            raise ValueError("tree changed during measurement")
        if args.baseline.read_bytes() != baseline_bytes:
            raise ValueError("baseline changed during measurement")
        destination = args.receipt.resolve()
        if destination.is_relative_to(root):
            parser.error("receipt must be outside the measured tree")
        destination.parent.mkdir(parents=True, exist_ok=True)
        log_path = destination.with_name(destination.name + ".log")
        log_bytes = log.encode("utf-8")
        log_path.write_bytes(log_bytes)
        receipt = {
            "check_id": "srs-writing-rules",
            "head": head,
            "rules": counts,
            "controls": tested,
            "checker": {
                "path": "scripts/check_writing_rules.py",
                "sha256": inputs["scripts/check_writing_rules.py"],
            },
            "inputs": inputs,
            "input_hash_domain": "git-show-utf8-stripped",
            "baseline_sha256": digest(baseline_bytes),
            "exit_status": status,
            "end_time": datetime.now(UTC).isoformat(),
            "hash_domain": "exact-file-bytes",
            "log": log_path.as_posix(),
            "log_sha256": digest(log_bytes),
        }
        destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
