"""Feature extractor — builds the features dict from file metadata + OcrResult.

Output structure::

    {
        "attr":   {"size_bytes": 1234, "extension": "jpg", ...},
        "text":   {"full_text": "..."},
        "struct": {"date": "...", "invoice_number": None, ...},
    }
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr.base_engine import OcrResult

Features = dict[str, dict[str, Any]]


class FeatureExtractor:
    """Extracts attr, text, and struct features for rule evaluation."""

    def extract(self, file_path: str, result: OcrResult) -> Features:
        return {
            "attr": self._attr(file_path),
            "text": self._text(result),
            "struct": self._struct(result),
        }

    # ── attr ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _attr(file_path: str) -> dict[str, Any]:
        p = Path(file_path)
        try:
            stat = os.stat(file_path)
            ctime = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            size = stat.st_size
        except OSError:
            ctime = mtime = ""
            size = 0

        return {
            "size_bytes": size,
            "extension": p.suffix.lstrip(".").lower(),
            "filename": p.stem,
            "ctime_iso": ctime,
            "mtime_iso": mtime,
        }

    # ── text ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _text(result: OcrResult) -> dict[str, Any]:
        return {"full_text": result.full_text}

    # ── struct ────────────────────────────────────────────────────────────────
    @staticmethod
    def _struct(result: OcrResult) -> dict[str, Any]:
        sf = result.structured_fields
        return {
            "date": sf.get("date"),
            "invoice_number": sf.get("invoice_number"),
            "total_amount": sf.get("total_amount"),
            "vendor_name": sf.get("vendor_name"),
            "stamp_detected": bool(sf.get("stamp_detected", False)),
        }
