"""P0400-PRIMARY: a failed log or manifest write never replaces the error that stopped the post.

At the 0.40.0 base the post log was written in a ``finally`` with no guard and
the interrupted manifest in an ``except`` with none, so an OSError there (a
locked file, a full disk) replaced the error that stopped the post, and a
caller catching that error by its type received an OSError.
"""

from __future__ import annotations

from contextlib import contextmanager
from io import StringIO

import pytest

import pyflightstream._textio as textio
import pyflightstream.post.products as products
from pyflightstream.cases import CampaignConfigError
from tests.tier1_offline.test_post_products import _unsteady_workspace


def _refusing_writes(monkeypatch, name: str, armed=lambda: True):
    real = textio.write_text

    def write_text(path, *args, **kwargs):
        # The manifest is staged as products.json.tmp and then replaced (PFS-2096.019).
        if str(path).endswith((name, f"{name}.tmp")) and armed():
            raise OSError(f"{name} is locked")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(textio, "write_text", write_text)


def test_p0400_primary_a_post_log_write_failure_keeps_the_error(tmp_path, monkeypatch):
    """P0400-PRIMARY: the caller receives the CampaignConfigError, the log failure as a note."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)

    def stop(*_args, **_kwargs):
        raise CampaignConfigError("the stated input is wrong")

    monkeypatch.setattr(products, "_campaign_products", stop)
    _refusing_writes(monkeypatch, "post.log.json")
    with pytest.raises(CampaignConfigError, match="the stated input is wrong") as caught:
        products.write_campaign_products(workspace)
    assert any("post log could not be written" in note for note in caught.value.__notes__)


def test_p0400_primary_an_interrupted_manifest_write_failure_keeps_the_error(tmp_path, monkeypatch):
    """P0400-PRIMARY: the rewrite of products.json failing keeps the rebuild's own error."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    stopped: list[bool] = []

    def stop(*_args, **_kwargs):
        stopped.append(True)
        raise CampaignConfigError("a product cannot be built")

    monkeypatch.setattr(products, "_write_the_products", stop)
    _refusing_writes(monkeypatch, "products.json", armed=lambda: bool(stopped))
    with pytest.raises(CampaignConfigError, match="a product cannot be built") as caught:
        products.write_campaign_products(workspace)
    assert any("interrupted manifest" in note for note in caught.value.__notes__)


def test_p0400_primary_a_clean_post_still_raises_its_log_failure(tmp_path, monkeypatch):
    """P0400-PRIMARY control: with no error in flight, the log failure is the error."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    monkeypatch.setattr(products, "_campaign_products", lambda *_args, **_kwargs: [])
    _refusing_writes(monkeypatch, "post.log.json")
    with pytest.raises(OSError, match="locked"):
        products.write_campaign_products(workspace)


def test_p0400_primary_a_partial_manifest_write_keeps_the_error(tmp_path, monkeypatch):
    """P0400-PRIMARY: reading a partially written manifest cannot replace the post error."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    original = CampaignConfigError("a product cannot be built")
    stopped = []
    real = textio.write_text

    def stop(*_args, **_kwargs):
        stopped.append(True)
        raise original

    def partial_write(path, *args, **kwargs):
        if str(path).endswith("products.json.tmp") and stopped:
            real(path, "{")
            raise OSError("manifest write ran out of space")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(products, "_write_the_products", stop)
    monkeypatch.setattr(textio, "write_text", partial_write)
    with pytest.raises(CampaignConfigError) as caught:
        products.write_campaign_products(workspace)
    assert caught.value is original
    assert any("interrupted manifest" in note for note in caught.value.__notes__)
    # The manifest is staged and replaced whole (PFS-2096.019), so the half-written file never
    # stands at its name: the post log reader finds no truncated JSON and adds no note.
    assert not any("post log" in note for note in caught.value.__notes__)


@pytest.mark.parametrize("failure", [CampaignConfigError, KeyboardInterrupt])
def test_p0400_primary_log_close_failure_keeps_the_primary(tmp_path, monkeypatch, failure):
    """P0400-PRIMARY: a buffered write failing at close preserves the original error."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    original = failure("the post stopped")

    def stop(*_args, **_kwargs):
        raise original

    @contextmanager
    def broken_close(*_args, **_kwargs):
        try:
            yield StringIO()
        finally:
            raise OSError("post.log close failed")

    monkeypatch.setattr(products, "_campaign_products", stop)
    monkeypatch.setattr(textio, "open_text", broken_close)
    with pytest.raises(failure) as caught:
        products.write_campaign_products(workspace)
    assert caught.value is original
    assert any("post.log close failed" in note for note in caught.value.__notes__)


def test_p0400_primary_clean_post_reports_log_close_failure(tmp_path, monkeypatch):
    """P0400-PRIMARY: a close failure remains visible when the post succeeded."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)

    @contextmanager
    def broken_close(*_args, **_kwargs):
        yield StringIO()
        raise OSError("post.log close failed")

    monkeypatch.setattr(products, "_campaign_products", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(textio, "open_text", broken_close)
    with pytest.raises(OSError, match="post.log close failed"):
        products.write_campaign_products(workspace)
