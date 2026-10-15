"""P0410: two failed dummy calls must retain evidence from both calls."""

from pyflightstream.fsi.cli import ERROR_LOG, dummy_step


def test_p0410_fx3_dummy_failures_append_per_call(tmp_path):
    log = tmp_path / ERROR_LOG
    log.write_text("earlier coupled failure\n", encoding="utf-8")
    assert dummy_step(tmp_path, ("first-call",)) == 1
    first = log.read_text(encoding="utf-8")
    assert dummy_step(tmp_path, ("second-call",)) == 1
    second = log.read_text(encoding="utf-8")
    assert first.startswith("earlier coupled failure\n")
    assert second.startswith(first)
    assert "first-call" in second
    assert "second-call" in second
