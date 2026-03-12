"""Zhipu MaaS Cloud OCR engine with exponential backoff retry.

Reference skill: .agent/skills/glm_ocr_protocol.json
"""
from __future__ import annotations

import base64
import json
import logging
import random
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from core.config import Config
from ocr.base_engine import BaseOCREngine, BoundingBox, OcrNetworkError, OcrResult

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_OCR_PROMPT = (
    "Please perform OCR on this document image. "
    "Return ONLY a valid JSON object (no markdown fences) with the following structure:\n"
    "{\n"
    '  "full_text": "<complete document text as a single string>",\n'
    '  "bounding_boxes": [\n'
    '    {"text": "...", "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0, "confidence": 1.0}\n'
    "  ],\n"
    '  "structured_fields": {\n'
    '    "date": null, "invoice_number": null, "total_amount": null,\n'
    '    "vendor_name": null, "stamp_detected": false\n'
    "  }\n"
    "}"
)


def _encode_image(image_path: str, max_side: int, quality: int) -> tuple[str, int, int]:
    """Return (base64_jpeg_string, width_px, height_px)."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        ratio = max_side / max(w, h)
        if ratio < 1.0:
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            w, h = img.size
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode(), w, h


class ZhipuCloudEngine(BaseOCREngine):
    """Calls the Zhipu GLM-4V (vision) API to perform OCR."""

    def __init__(self) -> None:
        cfg = Config.instance()
        self._api_key: str = cfg.get("ocr.api_key", "")
        self._endpoint: str = cfg.get(
            "ocr.cloud_endpoint",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )
        self._model: str = cfg.get("ocr.cloud_model", "glm-4v")
        self._max_side: int = int(cfg.get("ocr.max_image_side_px", 4096))
        self._quality: int = int(cfg.get("ocr.jpeg_quality", 85))
        self._timeout: float = float(cfg.get("ocr.timeout_seconds", 60))
        self._max_retries: int = int(cfg.get("ocr.max_retries", 4))
        self._base_delay: float = float(cfg.get("ocr.retry_base_delay", 1.0))
        self._backoff: float = float(cfg.get("ocr.retry_backoff_factor", 2.0))

    @property
    def name(self) -> str:
        return "ZhipuCloud"

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_key != "your_api_key_here")

    def run(self, image_path: str) -> OcrResult:
        if not self.is_available():
            raise OcrNetworkError("Zhipu API key not configured.")

        b64, img_w, img_h = _encode_image(image_path, self._max_side, self._quality)

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {"type": "text", "text": _OCR_PROMPT},
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        delay = self._base_delay
        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                if resp.status_code == 200:
                    return self._parse_response(resp.json(), img_w, img_h)
                if resp.status_code in _RETRYABLE_STATUS and attempt < self._max_retries:
                    log.warning(
                        "Zhipu API returned %d — retry %d/%d in %.1fs",
                        resp.status_code, attempt + 1, self._max_retries, delay,
                    )
                else:
                    raise OcrNetworkError(
                        f"Zhipu API error {resp.status_code}: {resp.text[:300]}"
                    )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise OcrNetworkError(f"Network error: {exc}") from exc
                log.warning("Network error, retry %d: %s", attempt + 1, exc)

            # Exponential back-off with jitter
            time.sleep(delay + random.uniform(0, delay * 0.3))
            delay *= self._backoff

        raise OcrNetworkError("Max retries exceeded.")

    # ── Parsing ───────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_response(body: dict, img_w: int, img_h: int) -> OcrResult:
        try:
            content: str = body["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])
            data: dict = json.loads(content)
        except (KeyError, json.JSONDecodeError) as exc:
            log.error("Failed to parse GLM response: %s", exc)
            data = {}

        boxes = [
            BoundingBox(
                text=bb.get("text", ""),
                x=float(bb.get("x", 0)),
                y=float(bb.get("y", 0)),
                w=float(bb.get("w", 0)),
                h=float(bb.get("h", 0)),
                confidence=float(bb.get("confidence", 1.0)),
            )
            for bb in data.get("bounding_boxes", [])
        ]

        return OcrResult(
            full_text=data.get("full_text", ""),
            bounding_boxes=boxes,
            structured_fields=data.get("structured_fields", {}),
            raw_json=data,
            engine_name="ZhipuCloud",
            image_width=img_w,
            image_height=img_h,
        )
