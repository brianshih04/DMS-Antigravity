"""DMS — Document Management System entry point.

Usage:
    python main.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ── Ensure project root is on sys.path ─────────────────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.config import Config
from ui.styles import get_stylesheet


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ROOT / "dms.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    configure_logging()
    log = logging.getLogger("dms.main")
    log.info("Starting DMS …")

    # Enable High-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DMS")
    app.setOrganizationName("Antigravity")
    app.setApplicationDisplayName("Document Management System")

    # Apply Fluent Design stylesheet
    cfg = Config.instance()
    theme = cfg.get("ui.theme", "auto")
    app.setStyleSheet(get_stylesheet(theme))

    # Import here so QApplication exists first
    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    log.info("DMS window shown. Entering event loop.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
