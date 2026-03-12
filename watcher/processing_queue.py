"""Thread-safe processing queue — dispatches stable files to the thread pool.

Listens on ``AppSignals.file_ready`` and submits OCR + classification jobs
to ``QThreadPool``.  A ``_processing`` set prevents duplicate jobs for the
same file path.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from PySide6.QtCore import QThreadPool

from core.config import Config
from core.signals import AppSignals
from core.threadpool import BaseWorker

log = logging.getLogger(__name__)


class ProcessingQueue:
    """Connects the watch-folder pipeline to the OCR worker thread pool."""

    def __init__(self) -> None:
        self._signals = AppSignals.instance()
        self._processing: set[str] = set()
        self._lock = threading.Lock()
        self._pool = QThreadPool.globalInstance()

        # Configure thread count from settings
        cfg = Config.instance()
        max_threads = int(cfg.get("threading.max_worker_threads", 4))
        if max_threads <= 0:
            max_threads = min(4, os.cpu_count() or 2)
        self._pool.setMaxThreadCount(max_threads)

        self._signals.file_ready.connect(self._enqueue)

    def _enqueue(self, path: str) -> None:
        with self._lock:
            if path in self._processing:
                log.debug("Already processing, skipping: %s", path)
                return
            self._processing.add(path)

        log.info("Enqueuing for OCR: %s", path)
        self._signals.file_queued.emit(path)
        self._signals.status_message.emit(f"Queued: {path}")

        # Import here to avoid circular imports at module load time
        from ocr.engine_router import OCREngineRouter
        from ocr.pdf_builder import PdfBuilder
        from classifier.feature_extractor import FeatureExtractor
        from classifier.file_router import FileRouter

        router = OCREngineRouter()
        pdf_builder = PdfBuilder()
        extractor = FeatureExtractor()
        file_router = FileRouter()

        def _process(path: str) -> None:
            try:
                self._signals.ocr_started.emit(path)
                result = router.process(path)
                self._signals.ocr_complete.emit(path, result)

                # Build searchable PDF
                output_pdf = pdf_builder.build(path, result)
                log.info("Searchable PDF: %s", output_pdf)

                # Save OCR text to OCR_Result folder
                self._save_ocr_text(path, result)

                # Classify
                features = extractor.extract(path, result)
                file_router.route(path, features)
            finally:
                with self._lock:
                    self._processing.discard(path)

        worker = BaseWorker(_process, path)
        worker.signals.error.connect(
            lambda err: self._on_error(path, err)
        )
        self._pool.start(worker)

    def _save_ocr_text(self, image_path: str, result) -> None:
        """Save OCR-extracted text to OCR_Result folder.
        
        Creates the OCR_Result subfolder under the configured output directory
        and saves the text file with the same name as the original file but
        with .txt extension.
        """
        cfg = Config.instance()
        output_base_dir = cfg.get("output.ocr_output_dir", "./processed")
        
        # Create OCR_Result subfolder
        ocr_result_dir = Path(output_base_dir) / "OCR_Result"
        ocr_result_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate output filename with .txt extension
        original_name = Path(image_path).stem
        output_file = ocr_result_dir / f"{original_name}.txt"
        
        # Write OCR text to file
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.full_text)
            log.info("OCR text saved to: %s", output_file)
            self._signals.status_message.emit(f"OCR text saved: {output_file.name}")
        except IOError as exc:
            log.error("Failed to save OCR text to %s: %s", output_file, exc)

    def _on_error(self, path: str, err: tuple) -> None:
        _, exc_value, tb = err
        msg = f"{exc_value}"
        log.error("Processing failed for %s:\n%s", path, tb)
        self._signals.ocr_failed.emit(path, msg)
        with self._lock:
            self._processing.discard(path)
