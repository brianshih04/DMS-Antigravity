"""Local OCR engine — calls a vLLM/ONNX OpenAI-compatible HTTP server.

Falls back gracefully if the local server is unreachable.
Configure ``ocr.local_endpoint`` in settings.yaml.
"""
from __future__ import annotations

import base64
import json
import logging
from io import BytesIO

import requests
from PIL import Image

from core.config import Config
from ocr.base_engine import BaseOCREngine, BoundingBox, OcrLocalError, OcrResult
from ocr.cloud_engine import _OCR_PROMPT  # reuse the same prompt

log = logging.getLogger(__name__)


def _encode_image_local(image_path: str) -> tuple[str, int, int]:
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode(), w, h


class LocalOCREngine(BaseOCREngine):
    """Routes OCR to a locally running vLLM / ONNX inference server."""

    def __init__(self) -> None:
        cfg = Config.instance()
        self._endpoint: str = cfg.get(
            "ocr.local_endpoint", "http://localhost:8000/v1/chat/completions"
        )
        self._health_url: str = self._endpoint.rsplit("/", 3)[0] + "/health"
        self._model: str = cfg.get("ocr.local_model_path", "local-glm-ocr")

    @property
    def name(self) -> str:
        return "LocalOCR"

    def is_available(self) -> bool:
        """Probe the health endpoint with a short timeout."""
        try:
            resp = requests.get(self._health_url, timeout=2.0)
            return resp.status_code in (200, 204)
        except requests.RequestException:
            return False

    def run(self, image_path: str) -> OcrResult:
        if not self.is_available():
            raise OcrLocalError(
                f"Local OCR server not reachable at {self._endpoint}. "
                "Check that the vLLM/ONNX server is running."
            )

        b64, img_w, img_h = _encode_image_local(image_path)

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

        try:
            resp = requests.post(self._endpoint, json=payload, timeout=120)
            if resp.status_code != 200:
                raise OcrLocalError(f"Local inference error {resp.status_code}: {resp.text[:300]}")
            return self._parse(resp.json(), img_w, img_h)
        except requests.RequestException as exc:
            raise OcrLocalError(f"Local server connection failed: {exc}") from exc

    @staticmethod
    def _parse(body: dict, img_w: int, img_h: int) -> OcrResult:
        try:
            content = body["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])
            data: dict = json.loads(content)
        except (KeyError, json.JSONDecodeError) as exc:
            log.error("Failed to parse local OCR response: %s", exc)
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
            engine_name="LocalOCR",
            image_width=img_w,
            image_height=img_h,
        )
