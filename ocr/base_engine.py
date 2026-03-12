"""Abstract base class and shared data model for OCR engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BoundingBox:
    """A single recognized text region.

    Coordinates are **normalized** (0–1 relative to image size).
    """
    text: str
    x: float         # left edge
    y: float         # top edge
    w: float         # width
    h: float         # height
    confidence: float = 1.0


@dataclass
class OcrResult:
    """Complete output from any OCR engine."""
    full_text: str
    bounding_boxes: list[BoundingBox] = field(default_factory=list)
    structured_fields: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)
    engine_name: str = ""
    image_width: int = 0
    image_height: int = 0


class OcrNetworkError(RuntimeError):
    """Raised when the cloud OCR endpoint is unreachable or returns an error."""


class OcrLocalError(RuntimeError):
    """Raised when the local inference server fails."""


class BaseOCREngine(ABC):
    """Strategy interface — all engines implement this contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine identifier."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this engine can service a request right now."""

    @abstractmethod
    def run(self, image_path: str) -> OcrResult:
        """Perform OCR on *image_path* and return structured results."""
