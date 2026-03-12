"""Local OCR engine — native Hugging Face Transformers execution for GLM-OCR.

Replaces the REST implementation to load THUDM/glm-ocr-0.9b directly into
the process memory for QThreadPool fast execution.
"""
from __future__ import annotations

import json
import logging
from threading import Lock

from PIL import Image

from core.config import Config
from ocr.base_engine import BaseOCREngine, BoundingBox, OcrLocalError, OcrResult

log = logging.getLogger(__name__)

# Global singletons to prevent multiple heavy loads of the model weights
_MODEL = None
_TOKENIZER = None
_MODEL_LOCK = Lock()


def _get_model_and_tokenizer(model_id: str):
    global _MODEL, _TOKENIZER
    with _MODEL_LOCK:
        if _MODEL is not None and _TOKENIZER is not None:
            return _MODEL, _TOKENIZER

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise OcrLocalError("Required packages 'transformers' or 'torch' are not installed.")

        log.info("Loading local GLM-OCR model %s into memory (this may take a while)...", model_id)

        try:
            _TOKENIZER = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            _MODEL = AutoModelForCausalLM.from_pretrained(
                model_id,
                trust_remote_code=True,
                device_map="auto",
                torch_dtype=torch.float16,
            ).eval()
            log.info("Local GLM-OCR model loaded successfully on device: %s", _MODEL.device)
        except Exception as exc:
            import traceback
            log.error("Failed to load local model: %s\n%s", exc, traceback.format_exc())
            raise OcrLocalError(f"Failed to load model: {exc}")

        return _MODEL, _TOKENIZER


class LocalOCREngine(BaseOCREngine):
    """Routes OCR tasks to the natively loaded Hugging Face vLLM transformer."""

    def __init__(self) -> None:
        cfg = Config.instance()
        self._model_id: str = cfg.get("ocr.local_model_path", "THUDM/glm-ocr-0.9b")

    @property
    def name(self) -> str:
        return "LocalOCR (Transformers)"

    def is_available(self) -> bool:
        """Check if both standard dependencies are present."""
        try:
            import transformers
            import torch
            return True
        except ImportError:
            return False

    def run(self, image_path: str) -> OcrResult:
        if not self.is_available():
            raise OcrLocalError("Transformers or PyTorch not installed for local OCR.")

        import torch

        # Lazy load weights during first run inside the background worker thread
        model, tokenizer = _get_model_and_tokenizer(self._model_id)

        try:
            image = Image.open(image_path).convert("RGB")
            img_w, img_h = image.size
        except Exception as exc:
            raise OcrLocalError(f"Failed to open image {image_path}: {exc}") from exc

        prompt = "Text Recognition:"

        # The image object must be passed so the Zhipu tokenizer can prepare visual inputs
        content_items = [
            {"type": "image", "image": image},
            {"type": "text", "text": prompt},
        ]

        inputs = tokenizer.apply_chat_template(
            [{"role": "user", "content": content_items}],
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
            return_dict=True
        ).to(model.device)

        try:
            with torch.no_grad():
                outputs = model.generate(**inputs, max_new_tokens=4096)
                # type checking ignores PyTorch dynamic slicing here
                response_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)  # type: ignore
        except Exception as exc:
            raise OcrLocalError(f"Local inference failed: {exc}") from exc

        return self._parse(response_text, img_w, img_h)

    @staticmethod
    def _parse(content: str, img_w: int, img_h: int) -> OcrResult:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:-1])

        try:
            data: dict = json.loads(cleaned)
        except json.JSONDecodeError:
            log.debug("Local OCR response is not JSON, treating as raw text.")
            data = {"full_text": content}

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
