"""Strategy-pattern OCR engine router.

Selection logic (``ocr.mode`` in settings.yaml):
  - ``"cloud"``  → always use ZhipuCloudEngine
  - ``"local"``  → always use LocalOCREngine
  - ``"auto"``   → probe local first; fall back to cloud if unavailable
"""
from __future__ import annotations

import logging

from core.config import Config
from ocr.base_engine import BaseOCREngine, OcrLocalError, OcrNetworkError, OcrResult
from ocr.cloud_engine import ZhipuCloudEngine
from ocr.local_engine import LocalOCREngine

log = logging.getLogger(__name__)


class OCREngineRouter:
    """Selects and invokes the appropriate OCR engine per the configured strategy."""

    def __init__(self) -> None:
        self._cfg = Config.instance()
        self._cloud = ZhipuCloudEngine()
        self._local = LocalOCREngine()

    def _select_engine(self) -> BaseOCREngine:
        mode: str = self._cfg.get("ocr.mode", "auto").lower()

        if mode == "cloud":
            return self._cloud
        if mode == "local":
            return self._local

        # "auto" — prefer local; fall back to cloud
        if self._local.is_available():
            log.debug("Router: using local engine.")
            return self._local
        log.debug("Router: local unavailable, using cloud engine.")
        return self._cloud

    def process(self, image_path: str) -> OcrResult:
        """Run OCR on *image_path* using the selected engine."""
        engine = self._select_engine()
        log.info("OCR engine selected: %s for %s", engine.name, image_path)
        try:
            result = engine.run(image_path)
            log.info(
                "OCR complete via %s: %d chars, %d boxes",
                engine.name, len(result.full_text), len(result.bounding_boxes),
            )
            return result
        except (OcrNetworkError, OcrLocalError) as exc:
            # If auto-mode and cloud failed after trying cloud, propagate
            log.error("OCR engine %s failed: %s", engine.name, exc)
            raise
