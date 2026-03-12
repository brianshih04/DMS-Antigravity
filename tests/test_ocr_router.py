"""Tests for the dual-track OCR engine strategy and retry logic."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from ocr.base_engine import OcrResult


# ── Engine router strategy ─────────────────────────────────────────────────

def test_router_selects_local_when_available():
    """When local engine is_available, router should choose it."""
    from ocr.engine_router import OCREngineRouter
    router = OCREngineRouter()
    with patch.object(router._local, "is_available", return_value=True), \
         patch.object(router._cloud, "is_available", return_value=True):
        with patch.object(router._cfg, "get", return_value="auto"):
            engine = router._select_engine()
    assert engine is router._local


def test_router_falls_back_to_cloud():
    """When local is unavailable in auto mode, cloud engine should be selected."""
    from ocr.engine_router import OCREngineRouter
    router = OCREngineRouter()
    with patch.object(router._local, "is_available", return_value=False), \
         patch.object(router._cfg, "get", return_value="auto"):
        engine = router._select_engine()
    assert engine is router._cloud


def test_router_forced_cloud_mode():
    """ocr.mode='cloud' should always return cloud engine."""
    from ocr.engine_router import OCREngineRouter
    router = OCREngineRouter()
    with patch.object(router._cfg, "get", return_value="cloud"):
        engine = router._select_engine()
    assert engine is router._cloud


def test_router_forced_local_mode():
    """ocr.mode='local' should always return local engine."""
    from ocr.engine_router import OCREngineRouter
    router = OCREngineRouter()
    with patch.object(router._cfg, "get", return_value="local"):
        engine = router._select_engine()
    assert engine is router._local


# ── Cloud engine retry logic ───────────────────────────────────────────────

def test_cloud_engine_retries_on_503_then_succeeds(tmp_path, mock_ocr_result):
    """Cloud engine should retry on 503, succeed on 4th attempt."""
    from ocr.cloud_engine import ZhipuCloudEngine

    engine = ZhipuCloudEngine()
    engine._api_key = "fake-key-for-test"
    engine._max_retries = 3
    engine._base_delay = 0.01  # Speed up for tests

    # Build a plausible 200 response body
    import json
    good_content = json.dumps({
        "full_text": "Hello World",
        "bounding_boxes": [],
        "structured_fields": {"stamp_detected": False},
    })
    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.json.return_value = {
        "choices": [{"message": {"content": good_content}}]
    }

    fail_resp = MagicMock()
    fail_resp.status_code = 503
    fail_resp.text = "Service Unavailable"

    img = tmp_path / "test.jpg"
    from PIL import Image
    Image.new("RGB", (50, 50)).save(str(img))

    with patch("requests.post", side_effect=[fail_resp, fail_resp, fail_resp, good_resp]):
        result = engine.run(str(img))

    assert isinstance(result, OcrResult)
    assert result.full_text == "Hello World"


def test_cloud_engine_raises_after_max_retries(tmp_path):
    """After exhausting retries, OcrNetworkError should be raised."""
    from ocr.cloud_engine import ZhipuCloudEngine
    from ocr.base_engine import OcrNetworkError

    engine = ZhipuCloudEngine()
    engine._api_key = "fake-key"
    engine._max_retries = 2
    engine._base_delay = 0.01

    fail_resp = MagicMock()
    fail_resp.status_code = 503
    fail_resp.text = ""

    img = tmp_path / "test.jpg"
    from PIL import Image
    Image.new("RGB", (50, 50)).save(str(img))

    with patch("requests.post", return_value=fail_resp):
        with pytest.raises(OcrNetworkError):
            engine.run(str(img))


# ── Local engine availability ──────────────────────────────────────────────

def test_local_engine_unavailable_without_transformers():
    """Local engine should be unavailable if transformers is not installed."""
    from ocr.local_engine import LocalOCREngine
    import sys
    engine = LocalOCREngine()
    with patch.dict(sys.modules, {"transformers": None, "torch": None}):
        assert engine.is_available() is False
