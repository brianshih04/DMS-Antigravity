"""Shared pytest fixtures for DMS tests."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture(scope="session")
def sample_image_path(tmp_path_factory) -> str:
    """Create a small JPEG test image once per session."""
    folder = tmp_path_factory.mktemp("img")
    img_path = folder / "test_doc.jpg"
    img = Image.new("RGB", (200, 150), color=(200, 200, 200))
    # Draw some text-like black rectangles
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 190, 25], fill=(20, 20, 20))
    draw.rectangle([10, 35, 150, 50], fill=(20, 20, 20))
    img.save(str(img_path), "JPEG")
    return str(img_path)


@pytest.fixture
def tmp_watch_folder(tmp_path) -> str:
    folder = tmp_path / "watch"
    folder.mkdir()
    return str(folder)


@pytest.fixture
def mock_ocr_result():
    """A deterministic OcrResult for use in tests."""
    from ocr.base_engine import BoundingBox, OcrResult
    return OcrResult(
        full_text="Invoice INV-2024-0001 from Acme Corp dated 2024-01-15",
        bounding_boxes=[
            BoundingBox(text="Invoice", x=0.05, y=0.05, w=0.2, h=0.08),
            BoundingBox(text="INV-2024-0001", x=0.05, y=0.15, w=0.4, h=0.08),
        ],
        structured_fields={
            "date": "2024-01-15",
            "invoice_number": "INV-2024-0001",
            "total_amount": "1500.00",
            "vendor_name": "Acme Corp",
            "stamp_detected": False,
        },
        engine_name="TestEngine",
        image_width=200,
        image_height=150,
    )


@pytest.fixture(scope="session")
def app():
    """QApplication fixture (session-scoped, reused across all UI tests)."""
    import sys
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing:
        yield existing
    else:
        _app = QApplication(sys.argv)
        yield _app
