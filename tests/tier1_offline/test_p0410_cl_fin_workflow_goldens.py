"""CL-01: every logical case renders, and shared payloads must agree."""

import importlib.util
from pathlib import Path

import pytest


def _generator():
    path = Path(__file__).resolve().parents[2] / "scripts/gen_workflow_goldens.py"
    spec = importlib.util.spec_from_file_location("workflow_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0410_shared_payloads_keep_every_execution(monkeypatch):
    module = _generator()
    calls = []
    original = module.render_or_refusal

    def render(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(module, "render_or_refusal", render)
    rendered = module.build()
    assert calls == module.GOLDEN_RENDERS
    assert len(rendered) == 27
    assert all(path.read_bytes() == data for path, data in rendered.items())


def test_p0410_divergent_shared_payload_is_refused(monkeypatch):
    module = _generator()
    original = module.render_or_refusal

    def render(name, label, build):
        text = original(name, label, build)
        if (name, label, build) == ("steady", "bare", "26.000"):
            return text + "CHANGED\n"
        return text

    monkeypatch.setattr(module, "render_or_refusal", render)
    with pytest.raises(SystemExit, match="shared payload"):
        module.build()
