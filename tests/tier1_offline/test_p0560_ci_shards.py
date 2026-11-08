"""P0560 CI sharding: PYFS_SHARD=1/3 pytest --collect-only -q.

Collection-only subprocesses exercise the actual hook without running bodies.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _hook():
    spec = importlib.util.spec_from_file_location("shard_conftest", ROOT / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def unchanged(config, items):
        yield

    return getattr(module, "pytest_collection_modifyitems", unchanged)


def test_p0560_ci_selector_complete_disjoint_stable(monkeypatch):
    hook = _hook()
    original = [SimpleNamespace(nodeid=f"test_{i:03d}") for i in reversed(range(31))]
    for n in (2, 3):
        shards = []
        for i in range(1, n + 1):
            results = []
            for incoming in (original, list(reversed(original))):
                monkeypatch.setenv("PYFS_SHARD", f"{i}/{n}")
                deselected = []
                config = SimpleNamespace(
                    hook=SimpleNamespace(
                        pytest_deselected=lambda items, out=deselected: out.extend(items)
                    )
                )
                items = list(incoming)
                wrapper = hook(config, items)
                next(wrapper)
                with pytest.raises(StopIteration):
                    next(wrapper)
                results.append([item.nodeid for item in items])
                assert len(items) + len(deselected) == len(original)
                assert "PYFS_SHARD" not in os.environ
            assert results[0] == results[1]
            assert results[0] == sorted(x.nodeid for x in original)[i - 1 :: n]
            shards.append(set(results[0]))
        assert set.union(*shards) == {item.nodeid for item in original}
        assert sum(map(len, shards)) == len(set.union(*shards))


EVENT_GATED = ("test-lean", "test-ceilings")
EVENT_GATE = "(github.event_name == 'schedule' || startsWith(github.ref, 'refs/tags/v'))"


def test_p0560_ci_workflow_shape_by_event():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["test"]["strategy"]["matrix"]["os"] == ["windows-latest"]
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["tags"] == ["v*"]
    assert triggers["schedule"] == [{"cron": "0 6 * * 1"}]
    for name in EVENT_GATED:
        # No job-level condition: a skipped job would fail the release check's all-green rule.
        assert "if" not in jobs[name]
        assert all(EVENT_GATE in step["if"] for step in jobs[name]["steps"]), name
    caps = [s for s in jobs["test-all-extras"]["steps"] if "lean_caps" in s.get("run", "")]
    assert len(caps) == 1
    assert not any("lean_caps" in s.get("run", "") for s in jobs["test"]["steps"])


def test_p0560_ci_workflow_shards():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    for name, count in (
        ("test", 3),
        ("test-all-extras", 3),
        ("test-floors", 3),
        ("test-lean", 2),
        ("test-ceilings", 2),
    ):
        job = jobs[name]
        assert job.get("strategy", {}).get("matrix", {}).get("shard") == list(range(1, count + 1))
        assert job["strategy"]["fail-fast"] is False
        assert "PYFS_SHARD" not in job.get("env", {})
        for step in job["steps"]:
            command = step.get("run", "")
            if command.startswith("pytest -n auto"):
                assert step["env"]["PYFS_SHARD"] == "${{ matrix.shard }}/" + str(count)
                if name in EVENT_GATED:
                    assert step["if"] == "${{ " + EVENT_GATE + " }}"
                else:
                    assert "if" not in step
            elif command.startswith(("pytest", "ruff")):
                assert "matrix.shard == 1" in step.get("if", "")
                if name in EVENT_GATED:
                    assert EVENT_GATE in step["if"]
                assert "PYFS_SHARD" not in step.get("env", {})


def test_p0560_ci_unset_preserves_collection(monkeypatch):
    monkeypatch.delenv("PYFS_SHARD", raising=False)
    items = [SimpleNamespace(nodeid="z"), SimpleNamespace(nodeid="a")]
    original = list(items)
    wrapper = _hook()(None, items)
    next(wrapper)
    with pytest.raises(StopIteration):
        next(wrapper)
    assert items == original


@pytest.mark.parametrize("shard", ["", "0/3", "4/3", "1/0", "1", "a/3", "1/2/3"])
def test_p0560_ci_invalid_shard_refused(monkeypatch, shard):
    monkeypatch.setenv("PYFS_SHARD", shard)
    wrapper = _hook()(None, [])
    next(wrapper)
    with pytest.raises(pytest.UsageError, match="PYFS_SHARD"):
        next(wrapper)


def _collect(shard, output):
    _wait_for_memory()
    env = os.environ.copy()
    env.pop("PYFS_SHARD", None)
    if shard:
        env["PYFS_SHARD"] = shard
    # This plugin records the final selection, after every collection hook.
    # Bind this checkout's namespace explicitly: an unrelated installed
    # regular package named scripts otherwise wins over its namespace folder.
    script = (
        "import importlib.machinery, importlib.util, json, pathlib, pytest, sys; "
        "spec = importlib.machinery.PathFinder.find_spec('scripts', [str(pathlib.Path.cwd())]); "
        "sys.modules['scripts'] = importlib.util.module_from_spec(spec); "
        "plugin = type('Capture', (), {'pytest_collection_finish': "
        "lambda self, session: pathlib.Path(sys.argv[1]).write_text("
        "json.dumps([item.nodeid for item in session.items]))})(); "
        "raise SystemExit(pytest.main(['--collect-only', '-q', 'tests/tier1_offline'], "
        "plugins=[plugin]))"
    )
    done = subprocess.run(
        [sys.executable, "-c", script, str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stdout[-12000:] + done.stderr
    return json.loads(output.read_text())


def _wait_for_memory():
    """Read available RAM before each nested pytest, without another dependency."""
    while True:
        if sys.platform == "win32":
            import ctypes
            import struct

            status = ctypes.create_string_buffer(64)
            struct.pack_into("I", status, 0, 64)
            assert ctypes.windll.kernel32.GlobalMemoryStatusEx(status)
            available = struct.unpack_from("Q", status, 16)[0]
        else:
            memory = Path("/proc/meminfo").read_text()
            available = int(memory.split("MemAvailable:")[1].split()[0]) * 1024
        print(f"Collection memory gate: {available / 2**30:.2f} GiB free", flush=True)
        if available >= 1.2 * 2**30:
            return
        time.sleep(10)


def test_p0560_ci_real_collection_complete_disjoint(tmp_path):
    full = _collect(None, tmp_path / "full.json")
    assert full and len(full) == len(set(full))
    for n in (2, 3):
        shards = [_collect(f"{i}/{n}", tmp_path / f"{i}-{n}.json") for i in range(1, n + 1)]
        combined = [node for shard in shards for node in shard]
        assert len(combined) == len(set(combined))
        assert set(combined) == set(full)
        print(f"P0560 n={n}: counts={[len(s) for s in shards]}, total={len(full)}")
