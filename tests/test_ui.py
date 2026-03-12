"""UI smoke tests using pytest-qt."""
from __future__ import annotations

import sys
import pytest


# Skip these tests in headless/CI environments
pytestmark = pytest.mark.skipif(
    "--no-header" in sys.argv or not any(
        k in __import__("os").environ for k in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM")
    ) and sys.platform != "win32",
    reason="No display available for GUI tests"
)


def test_main_window_creates(qtbot, tmp_path, monkeypatch):
    """MainWindow should instantiate without errors."""
    # Patch config to avoid reading real settings
    monkeypatch.setenv("ZHIPU_API_KEY", "")

    from core.config import Config
    cfg = Config.instance()

    # Override watch folders to a tmp dir to avoid real FS side effects
    monkeypatch.setattr(cfg, "get", lambda key, default=None: {
        "ui.window_title": "DMS Test",
        "ui.window_width": 800,
        "ui.window_height": 600,
        "ui.theme": "dark",
        "ui.thumbnail_size": 80,
        "ui.thumbnail_cache_max": 10,
        "watch_folders": [{"path": str(tmp_path), "recursive": False, "auto_create": True}],
        "threading.max_worker_threads": 1,
        "classification.enabled": False,
        "output.default_output_dir": str(tmp_path / "out"),
        "output.searchable_pdf_suffix": "_s",
    }.get(key, default))

    from ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    assert window.isVisible()


def test_folder_panel_model(qtbot):
    """FolderPanel should create a QFileSystemModel without crash."""
    from ui.folder_panel import FolderPanel
    panel = FolderPanel()
    qtbot.addWidget(panel)
    assert panel._model is not None
    assert panel._tree is not None


def test_thumbnail_panel_load_folder(qtbot, tmp_path):
    """ThumbnailPanel.load_folder on an empty directory should not crash."""
    from ui.thumbnail_panel import ThumbnailPanel
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_folder(str(tmp_path))
    assert panel._model.rowCount() == 0


def test_thumbnail_panel_with_images(qtbot, tmp_path):
    """ThumbnailPanel should populate model when folder contains images."""
    from PIL import Image
    for i in range(3):
        img = Image.new("RGB", (50, 50), color=(i * 80, 100, 200))
        img.save(str(tmp_path / f"doc_{i}.jpg"), "JPEG")

    from ui.thumbnail_panel import ThumbnailPanel
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_folder(str(tmp_path))

    assert panel._model.rowCount() == 3
