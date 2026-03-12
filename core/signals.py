"""Central signal bus — all cross-module PySide6 signals live here."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """Singleton signal bus.  Access via ``AppSignals.instance()``."""

    # Watch-folder pipeline
    file_queued = Signal(str)          # path: a new file has been stabilized
    file_ready = Signal(str)           # path: ready for OCR / classification

    # OCR pipeline
    ocr_started = Signal(str)          # path
    ocr_progress = Signal(str, int)    # path, percent
    ocr_complete = Signal(str, object) # path, OcrResult
    ocr_failed = Signal(str, str)      # path, error_message

    # Classification
    classification_done = Signal(str, str, str)  # src_path, dest_path, rule_id
    classification_failed = Signal(str, str)      # path, error_message

    # Thumbnails
    thumbnail_ready = Signal(str, object)  # path, QImage

    # General
    error_occurred = Signal(str, str)  # component, message
    status_message = Signal(str)       # short status bar text

    _instance: "AppSignals | None" = None

    @classmethod
    def instance(cls) -> "AppSignals":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
